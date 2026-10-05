from __future__ import annotations

import argparse
from collections import Counter
from dataclasses import asdict
import json
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from data.defaults import CREW_MEMBERS, PARTS, TRACKS
from models.domain import Team
from models.enums import CarArchetype, CrewSlot, PartSlot
from models.stats import DriverStats
from services.balance import build_strain, crew_effects, part_strain
from services.builds import BuildService
from services.race_engine import RaceEngine
from services.sponsors import SPONSORS

BALANCE_TARGETS = {
    "stock_archetype_min": 10.0,
    "stock_archetype_max": 18.0,
    "driver_profile_spread_max": 10.0,
    "developed_team_win_max": 35.0,
    "legal_part_slot_win_max": 30.0,
    "crew_member_win_max": 25.0,
    "sponsor_win_max": 25.0,
}

DRIVER_PROFILES = {
    "balanced": DriverStats(4, 4, 4, 4, 4, 4),
    "handler": DriverStats(4, 7, 2, 3, 6, 2),
    "aggressive": DriverStats(4, 3, 7, 3, 4, 3),
    "mechanic": DriverStats(4, 3, 2, 8, 4, 3),
    "nerve": DriverStats(8, 3, 2, 3, 5, 3),
    "showman": DriverStats(4, 3, 3, 3, 4, 7),
    "minmax": DriverStats(5, 8, 1, 1, 8, 1),
}

# Intentionally performance-leaning all-legal stress build. This is not meant
# to be the recommended setup; it exists to make stacking regressions obvious.
DEVELOPED_PARTS = [
    "blueprinted_flathead",
    "wide_whites",
    "coilover_conversion",
    "front_disc_conversion",
    "channeled_body",
    "close_ratio_box",
    "dual_carbs",
    "lucky_hula_girl",
]
DEVELOPED_CREW = {
    "crew_chief": "chief_mae_clipboard",
    "lead_mechanic": "mechanic_grace_grease",
    "tyre_changer": "tyre_lou_whitewall",
    "fuel_runner": "fuel_pops_stromberg",
    "spotter": "spotter_carla_corners",
}


def _team(
    team_id: int,
    identity: str,
    *,
    archetype: CarArchetype = CarArchetype.SEDAN,
    stats: DriverStats | None = None,
    parts: list[str] | None = None,
    crew: dict[str, str] | None = None,
    active_sponsor_key: str | None = None,
) -> Team:
    return Team(
        id=team_id,
        name=f"Team {identity}",
        driver_name=f"Driver {identity}",
        pit_crew_name=f"Crew {identity}",
        car_name=f"Rod {identity}",
        archetype=archetype,
        stats=stats or DriverStats(4, 4, 4, 4, 4, 4),
        parts=list(parts or []),
        owner_user_id=None,
        crew=dict(crew or {}),
        active_sponsor_key=active_sponsor_key,
    )


def _winner(results):
    finishers = [r for r in results if not r.dnf and not r.disqualified]
    return min(finishers, key=lambda r: r.position) if finishers else None


def stock_archetype_win_rates(races_per_track: int = 120) -> dict[str, float]:
    archetypes = list(CarArchetype)
    wins: Counter[str] = Counter()
    races = 0
    for track_index, track_key in enumerate(TRACKS):
        for race_index in range(races_per_track):
            teams = [
                _team(
                    index + 1,
                    f"arch-{track_index}-{race_index}-{index}",
                    archetype=archetype,
                )
                for index, archetype in enumerate(archetypes)
            ]
            _, results, _ = RaceEngine(
                track_key,
                teams,
                seed=f"balance-arch-{track_key}-{race_index}",
                laps=10,
            ).run()
            winner = _winner(results)
            if winner:
                team = teams[winner.team_id - 1]
                wins[team.archetype.name] += 1
            races += 1
    return {archetype.name: wins[archetype.name] * 100.0 / races for archetype in archetypes}


def driver_profile_win_rates(races_per_track: int = 120) -> dict[str, float]:
    names = list(DRIVER_PROFILES)
    wins: Counter[str] = Counter()
    races = 0
    for track_index, track_key in enumerate(TRACKS):
        for race_index in range(races_per_track):
            teams = [
                _team(
                    index + 1,
                    f"driver-{track_index}-{race_index}-{index}",
                    stats=DRIVER_PROFILES[name],
                )
                for index, name in enumerate(names)
            ]
            _, results, _ = RaceEngine(
                track_key,
                teams,
                seed=f"balance-driver-{track_key}-{race_index}",
                laps=10,
            ).run()
            winner = _winner(results)
            if winner:
                wins[names[winner.team_id - 1]] += 1
            races += 1
    return {name: wins[name] * 100.0 / races for name in names}


def developed_team_win_rate(races_per_track: int = 120) -> float:
    wins = 0
    races = 0
    for track_index, track_key in enumerate(TRACKS):
        for race_index in range(races_per_track):
            teams = []
            for index in range(10):
                identity = f"developed-{track_index}-{race_index}-{index}"
                teams.append(
                    _team(
                        index + 1,
                        identity,
                        parts=DEVELOPED_PARTS if index == 0 else [],
                        crew=DEVELOPED_CREW if index == 0 else {},
                    )
                )
            _, results, _ = RaceEngine(
                track_key,
                teams,
                seed=f"balance-developed-{track_key}-{race_index}",
                laps=10,
            ).run()
            winner = _winner(results)
            wins += int(bool(winner and winner.team_id == 1))
            races += 1
    return wins * 100.0 / races


def legal_part_slot_win_rates(races_per_track: int = 35) -> dict[str, dict[str, float]]:
    report: dict[str, dict[str, float]] = {}
    for slot in PartSlot:
        keys = [key for key, part in PARTS.items() if part.slot == slot and "illegal_risk" not in part.risk_tags]
        wins: Counter[str] = Counter()
        races = 0
        for track_index, track_key in enumerate(TRACKS):
            for race_index in range(races_per_track):
                teams = [
                    _team(
                        index + 1,
                        f"part-{slot.value}-{track_index}-{race_index}-{index}",
                        archetype=CarArchetype.COUPE_32,
                        parts=[key],
                    )
                    for index, key in enumerate(keys)
                ]
                _, results, _ = RaceEngine(
                    track_key,
                    teams,
                    seed=f"balance-part-{slot.value}-{track_key}-{race_index}",
                    laps=10,
                ).run()
                winner = _winner(results)
                if winner:
                    wins[keys[winner.team_id - 1]] += 1
                races += 1
        report[slot.value] = {key: wins[key] * 100.0 / races for key in keys}
    return report


def crew_slot_win_rates(races_per_track: int = 35) -> dict[str, dict[str, float]]:
    report: dict[str, dict[str, float]] = {}
    for slot in CrewSlot:
        keys = [key for key, member in CREW_MEMBERS.items() if member.slot == slot]
        wins: Counter[str] = Counter()
        races = 0
        for track_index, track_key in enumerate(TRACKS):
            for race_index in range(races_per_track):
                teams = [
                    _team(
                        index + 1,
                        f"crew-{slot.value}-{track_index}-{race_index}-{index}",
                        archetype=CarArchetype.COUPE_32,
                        crew={slot.value: key},
                    )
                    for index, key in enumerate(keys)
                ]
                # Two stock controls make the race size representative without
                # changing which crew member is compared against the others.
                for filler in range(2):
                    teams.append(
                        _team(
                            len(teams) + 1,
                            f"crew-control-{slot.value}-{track_index}-{race_index}-{filler}",
                            archetype=CarArchetype.COUPE_32,
                        )
                    )
                _, results, _ = RaceEngine(
                    track_key,
                    teams,
                    seed=f"balance-crew-{slot.value}-{track_key}-{race_index}",
                    laps=10,
                ).run()
                winner = _winner(results)
                if winner and winner.team_id <= len(keys):
                    wins[keys[winner.team_id - 1]] += 1
                races += 1
        report[slot.value] = {key: wins[key] * 100.0 / races for key in keys}
    return report



def sponsor_win_rates(races_per_track: int = 50) -> dict[str, float]:
    rates: dict[str, float] = {}
    for sponsor_key in SPONSORS:
        wins = 0
        races = 0
        for track_key in TRACKS:
            for race_index in range(races_per_track):
                teams = [
                    _team(
                        index + 1,
                        f"sponsor-{sponsor_key}-{track_key}-{race_index}-{index}",
                        active_sponsor_key=sponsor_key if index == 0 else None,
                    )
                    for index in range(10)
                ]
                _, results, _ = RaceEngine(
                    track_key,
                    teams,
                    seed=f"balance-sponsor-{sponsor_key}-{track_key}-{race_index}",
                    laps=10,
                ).run()
                winner = _winner(results)
                wins += int(bool(winner and winner.team_id == 1))
                races += 1
        rates[sponsor_key] = wins * 100.0 / races
    return rates

def legal_part_tradeoff_failures() -> list[str]:
    failures = []
    for key, part in PARTS.items():
        if "illegal_risk" in part.risk_tags:
            continue
        values = part.modifiers.as_dict()
        gain = any(value > 0 for stat, value in values.items() if stat != "heat") or values["heat"] < 0
        drawback = any(value < 0 for stat, value in values.items() if stat != "heat") or values["heat"] > 0
        if not gain or not drawback:
            failures.append(key)
    return failures


def structural_report() -> dict:
    stock = _team(1, "stock")
    developed = _team(1, "developed", parts=DEVELOPED_PARTS, crew=DEVELOPED_CREW)
    illegal_parts = [key for key, part in PARTS.items() if "illegal_risk" in part.risk_tags]
    illegal_team = _team(2, "illegal", parts=illegal_parts)
    return {
        "legal_part_tradeoff_failures": legal_part_tradeoff_failures(),
        "stock_tuning_efficiency": BuildService.tuning_efficiency(stock),
        "developed_tuning_efficiency": BuildService.tuning_efficiency(developed),
        "developed_strain": build_strain(developed),
        "all_illegal_strain": build_strain(illegal_team),
        "all_illegal_dsq_risk": BuildService.illegal_disqualification_risk_percent(illegal_team),
        "developed_crew_effects": asdict(crew_effects(developed)),
        "part_strain": {key: part_strain(part) for key, part in PARTS.items()},
    }


def validate_report(report: dict) -> list[str]:
    failures: list[str] = []
    archetypes = report["stock_archetypes"]
    for name, rate in archetypes.items():
        if not (BALANCE_TARGETS["stock_archetype_min"] <= rate <= BALANCE_TARGETS["stock_archetype_max"]):
            failures.append(f"stock archetype {name} outside target: {rate:.2f}%")

    driver_rates = report["driver_profiles"]
    driver_spread = max(driver_rates.values()) - min(driver_rates.values())
    if driver_spread > BALANCE_TARGETS["driver_profile_spread_max"]:
        failures.append(f"driver profile spread too high: {driver_spread:.2f}pp")

    if report["developed_team_win_rate"] > BALANCE_TARGETS["developed_team_win_max"]:
        failures.append(f"developed team dominance: {report['developed_team_win_rate']:.2f}%")

    for slot, rates in report["legal_parts"].items():
        if rates and max(rates.values()) > BALANCE_TARGETS["legal_part_slot_win_max"]:
            failures.append(f"part slot {slot} has dominant option: {max(rates.values()):.2f}%")

    for slot, rates in report["crew"].items():
        if rates and max(rates.values()) > BALANCE_TARGETS["crew_member_win_max"]:
            failures.append(f"crew slot {slot} has dominant option: {max(rates.values()):.2f}%")

    for sponsor_key, rate in report["sponsors"].items():
        if rate > BALANCE_TARGETS["sponsor_win_max"]:
            failures.append(f"sponsor {sponsor_key} dominates stock controls: {rate:.2f}%")

    failures.extend(f"legal part lacks tradeoff: {key}" for key in report["structural"]["legal_part_tradeoff_failures"])
    return failures


def run_lab(races_per_track: int = 120, slot_races_per_track: int = 35) -> dict:
    report = {
        "stock_archetypes": stock_archetype_win_rates(races_per_track),
        "driver_profiles": driver_profile_win_rates(races_per_track),
        "developed_team_win_rate": developed_team_win_rate(races_per_track),
        "legal_parts": legal_part_slot_win_rates(slot_races_per_track),
        "crew": crew_slot_win_rates(slot_races_per_track),
        "sponsors": sponsor_win_rates(max(20, races_per_track // 2)),
        "structural": structural_report(),
    }
    report["failures"] = validate_report(report)
    return report


def _print_report(report: dict) -> None:
    print("Rat Rod Racing Bot v0.4.6 Balance Lab (v0.4.3 balance baseline + sponsor guardrails)")
    print("\nStock archetype win rates")
    for name, rate in report["stock_archetypes"].items():
        print(f"  {name:16} {rate:6.2f}%")
    print("\nDriver profile win rates")
    for name, rate in report["driver_profiles"].items():
        print(f"  {name:16} {rate:6.2f}%")
    spread = max(report["driver_profiles"].values()) - min(report["driver_profiles"].values())
    print(f"  spread: {spread:.2f} percentage points")
    print(f"\nDeveloped team vs nine stock cars: {report['developed_team_win_rate']:.2f}%")

    print("\nLegal part slot leaders")
    for slot, rates in report["legal_parts"].items():
        key, rate = max(rates.items(), key=lambda item: item[1])
        print(f"  {slot:14} {key:28} {rate:6.2f}%")

    print("\nCrew slot leaders")
    for slot, rates in report["crew"].items():
        key, rate = max(rates.items(), key=lambda item: item[1])
        print(f"  {slot:14} {key:28} {rate:6.2f}%")

    print("\nSponsor solo win rates vs nine independent controls")
    for key, rate in report["sponsors"].items():
        print(f"  {key:22} {rate:6.2f}%")

    structural = report["structural"]
    print(
        "\nStacking: "
        f"developed tune {structural['developed_tuning_efficiency'] * 100:.0f}% | "
        f"strain {structural['developed_strain']}"
    )
    print(
        "Illegal stress: "
        f"all-eight strain {structural['all_illegal_strain']} | "
        f"DSQ risk {structural['all_illegal_dsq_risk']}%"
    )

    if report["failures"]:
        print("\nFAIL")
        for failure in report["failures"]:
            print(f"  - {failure}")
    else:
        print("\nPASS - competitive integrity targets satisfied")


def main() -> int:
    parser = argparse.ArgumentParser(description="Monte Carlo balance regression lab for Rat Rod Racing Bot")
    parser.add_argument("--races-per-track", type=int, default=120)
    parser.add_argument("--slot-races-per-track", type=int, default=35)
    parser.add_argument("--quick", action="store_true", help="Use a shorter deterministic smoke sample")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--no-fail", action="store_true", help="Report targets without returning a failing exit code")
    args = parser.parse_args()
    if args.quick:
        args.races_per_track = 40
        args.slot_races_per_track = 12
    report = run_lab(args.races_per_track, args.slot_races_per_track)
    if args.json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        _print_report(report)
    return 0 if args.no_fail or not report["failures"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
