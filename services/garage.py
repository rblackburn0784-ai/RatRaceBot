from __future__ import annotations

from dataclasses import dataclass, replace

from data.defaults import CREW_MEMBERS, PARTS, TRACKS, WEATHER_CONDITIONS
from models.domain import CrewMember, Team
from models.enums import CrewSlot, PartSlot
from services.balance import crew_effect_for_member, track_part_adjustment
from services.builds import BuildService

GARAGE_VERSION = "0.4.7"
SETUP_PRESETS = ("Street", "Dirt", "Wet", "High-Speed", "Custom")


@dataclass(frozen=True, slots=True)
class GarageRatings:
    fast: int
    technical: int
    wet: int
    rough: int

    def as_dict(self) -> dict[str, int]:
        return {
            "Fast Track": self.fast,
            "Technical": self.technical,
            "Wet": self.wet,
            "Rough": self.rough,
        }


@dataclass(frozen=True, slots=True)
class PartComparison:
    slot: PartSlot
    current_key: str | None
    candidate_key: str
    before_ratings: GarageRatings
    after_ratings: GarageRatings
    before_strain: int
    after_strain: int
    before_tuning: int
    after_tuning: int
    before_illegal_risk: int
    after_illegal_risk: int


def stars(rating: int) -> str:
    rating = max(1, min(5, int(rating)))
    return "★" * rating + "☆" * (5 - rating)


def _rating(score: float, low: float = 1.5, high: float = 8.5) -> int:
    if high <= low:
        return 3
    scaled = 1 + 4 * max(0.0, min(1.0, (score - low) / (high - low)))
    return max(1, min(5, round(scaled)))


def _adjusted_stats(team: Team, track_key: str, weather_key: str = "clear"):
    track = TRACKS[track_key]
    weather = WEATHER_CONDITIONS[weather_key]
    return BuildService.clamp_car_stats(
        BuildService.effective_car_stats(team)
        + track.modifiers
        + weather.modifiers
        + track_part_adjustment(team, track, weather)
    )


def _average(values: list[float]) -> float:
    return sum(values) / max(1, len(values))


def setup_ratings(team: Team) -> GarageRatings:
    fast_scores: list[float] = []
    for track_key in ("county_line", "salt_ghost", "neon_mile"):
        s = _adjusted_stats(team, track_key)
        fast_scores.append(s.speed * 0.52 + s.acceleration * 0.30 + s.braking * 0.10 + s.reliability * 0.08 - max(0, s.heat) * 0.08)

    technical_scores: list[float] = []
    for track_key in ("switchback_66", "fairground_figure8", "riverfront_sprint"):
        s = _adjusted_stats(team, track_key)
        technical_scores.append(s.handling * 0.48 + s.braking * 0.28 + s.acceleration * 0.14 + s.reliability * 0.10)

    wet_scores: list[float] = []
    for track_key in ("neon_mile", "riverfront_sprint", "switchback_66"):
        s = _adjusted_stats(team, track_key, "rain")
        wet_scores.append(s.handling * 0.40 + s.braking * 0.28 + s.reliability * 0.20 + s.durability * 0.12)

    rough_scores: list[float] = []
    for track_key in ("junkyard_bowl", "foundry_run", "boardwalk_dash"):
        s = _adjusted_stats(team, track_key)
        rough_scores.append(s.durability * 0.42 + s.reliability * 0.30 + s.handling * 0.18 + s.pit_friendliness * 0.10)

    return GarageRatings(
        fast=_rating(_average(fast_scores)),
        technical=_rating(_average(technical_scores)),
        wet=_rating(_average(wet_scores)),
        rough=_rating(_average(rough_scores)),
    )


def setup_rating_lines(team: Team) -> list[str]:
    ratings = setup_ratings(team)
    return [f"{label}: {stars(value)}" for label, value in ratings.as_dict().items()]


def equipped_part_rows(team: Team) -> list[tuple[PartSlot, str | None]]:
    by_slot = BuildService.equipped_parts_by_slot(team)
    return [(slot, by_slot.get(slot).key if slot in by_slot else None) for slot in PartSlot]


def normalized_parts(parts: list[str]) -> list[str]:
    """Keep valid parts only, one per slot, preserving the first occurrence."""
    result: list[str] = []
    seen: set[PartSlot] = set()
    for key in parts:
        part = PARTS.get(key)
        if not part or part.slot in seen:
            continue
        seen.add(part.slot)
        result.append(key)
    return result


def team_with_candidate_part(team: Team, candidate_key: str) -> Team:
    candidate = PARTS[candidate_key]
    kept = [key for key in team.parts if key in PARTS and PARTS[key].slot != candidate.slot]
    return replace(team, parts=normalized_parts([*kept, candidate_key]))


def compare_part(team: Team, candidate_key: str) -> PartComparison:
    if candidate_key not in PARTS:
        raise ValueError("Unknown part.")
    candidate = PARTS[candidate_key]
    current = next(
        (key for key in team.parts if key in PARTS and PARTS[key].slot == candidate.slot),
        None,
    )
    projected = team_with_candidate_part(team, candidate_key)
    return PartComparison(
        slot=candidate.slot,
        current_key=current,
        candidate_key=candidate_key,
        before_ratings=setup_ratings(team),
        after_ratings=setup_ratings(projected),
        before_strain=BuildService.build_strain(team),
        after_strain=BuildService.build_strain(projected),
        before_tuning=round(BuildService.tuning_efficiency(team) * 100),
        after_tuning=round(BuildService.tuning_efficiency(projected) * 100),
        before_illegal_risk=BuildService.illegal_disqualification_risk_percent(team),
        after_illegal_risk=BuildService.illegal_disqualification_risk_percent(projected),
    )


def comparison_rating_lines(comparison: PartComparison) -> list[str]:
    before = comparison.before_ratings.as_dict()
    after = comparison.after_ratings.as_dict()
    lines = []
    for label in before:
        delta = after[label] - before[label]
        change = "" if delta == 0 else f" ({delta:+d})"
        lines.append(f"{label}: {stars(before[label])} → {stars(after[label])}{change}")
    return lines


def crew_role_name(slot: CrewSlot) -> str:
    return {
        CrewSlot.CREW_CHIEF: "Strategy & coordination",
        CrewSlot.LEAD_MECHANIC: "Strain control & repairs",
        CrewSlot.TYRE_CHANGER: "Tyre life & pit tyre recovery",
        CrewSlot.FUEL_RUNNER: "Heat management & pit support",
        CrewSlot.SPOTTER: "Traffic awareness & collision avoidance",
    }[slot]


def crew_role_summary(member: CrewMember) -> str:
    effects = crew_effect_for_member(member)
    positives: list[str] = []
    negatives: list[str] = []
    labels = {
        "strategy": "strategy",
        "repair": "repairs/strain",
        "tyre_care": "tyre care",
        "heat_control": "heat control",
        "spotting": "traffic spotting",
        "attack_support": "attack support",
        "pit_bonus": "pit work",
    }
    for key, label in labels.items():
        value = getattr(effects, key)
        if value >= 0.35:
            positives.append(label)
        elif value <= -0.35:
            negatives.append(label)
    text = f"**Role:** {crew_role_name(member.slot)}"
    if positives:
        text += f"\nHelps: {', '.join(positives[:4])}."
    if negatives:
        text += f"\nTrade-off: weaker {', '.join(negatives[:3])}."
    return text


def crew_roster_lines(team: Team) -> list[str]:
    lines: list[str] = []
    for slot in CrewSlot:
        key = team.crew.get(slot.value)
        member = CREW_MEMBERS.get(key)
        if member:
            lines.append(f"**{slot.value.replace('_', ' ').title()}:** {member.name} — {crew_role_name(slot)}")
        else:
            lines.append(f"**{slot.value.replace('_', ' ').title()}:** Empty")
    return lines


def crew_contributors(team: Team, purpose: str) -> list[str]:
    """Presentation-only list of assigned specialists relevant to a race moment."""
    relevant: dict[str, tuple[CrewSlot, ...]] = {
        "start": (CrewSlot.CREW_CHIEF, CrewSlot.SPOTTER),
        "overtake": (CrewSlot.SPOTTER, CrewSlot.CREW_CHIEF),
        "hazard": (CrewSlot.SPOTTER, CrewSlot.LEAD_MECHANIC),
        "pit": (CrewSlot.CREW_CHIEF, CrewSlot.LEAD_MECHANIC, CrewSlot.TYRE_CHANGER, CrewSlot.FUEL_RUNNER),
        "heat": (CrewSlot.FUEL_RUNNER, CrewSlot.LEAD_MECHANIC),
        "penalty": (CrewSlot.CREW_CHIEF,),
        "finish": (CrewSlot.CREW_CHIEF, CrewSlot.FUEL_RUNNER),
    }
    names: list[str] = []
    for slot in relevant.get(purpose, ()):
        key = team.crew.get(slot.value)
        member = CREW_MEMBERS.get(key)
        if member:
            names.append(f"{member.name} ({slot.value.replace('_', ' ').title()})")
    return names


def crew_chief_advice(team: Team) -> list[str]:
    advice: list[str] = []
    ratings = setup_ratings(team)
    strain = BuildService.build_strain(team)
    efficiency = BuildService.tuning_efficiency(team)
    illegal = BuildService.illegal_disqualification_risk_percent(team)
    parts = BuildService.equipped_parts_by_slot(team)
    crew = BuildService.equipped_crew_by_slot(team)

    if strain >= 12:
        advice.append("⚠ The car is knife-edge. Remove a high-strain part or lean on a strong Lead Mechanic before a long race.")
    elif strain >= 8:
        advice.append("• The setup is stressed. It can be quick, but expect tyre and repair pressure over longer runs.")
    else:
        advice.append("✓ Mechanical strain is under control; you have room to specialise without immediately overworking the package.")

    if efficiency < 0.50:
        advice.append("⚠ Tuning efficiency is low. Eight fitted systems are not automatically better than a focused five- or six-part setup.")
    elif efficiency >= 0.80:
        advice.append("✓ Tuning efficiency is healthy; the fitted parts are still giving most of their intended benefit.")

    rating_map = ratings.as_dict()
    best = max(rating_map, key=rating_map.get)
    worst = min(rating_map, key=rating_map.get)
    advice.append(f"• Current identity: strongest on **{best}** layouts, weakest on **{worst}** layouts.")

    if PartSlot.TYRES not in parts:
        advice.append("• Tyres are empty. That leaves a lot of venue/weather specialisation on the table.")
    if PartSlot.TRANSMISSION not in parts:
        advice.append("• No transmission setup is fitted; gearing is one of the cleanest ways to specialise for fast versus technical tracks.")
    if CrewSlot.CREW_CHIEF not in crew:
        advice.append("• The Crew Chief seat is empty. Fill it for strategy, coordination and cleaner race management.")
    if CrewSlot.LEAD_MECHANIC not in crew and strain >= 7:
        advice.append("• Hire a Lead Mechanic if you want to keep running a high-strain build—the role directly reduces effective strain and improves repairs.")
    if CrewSlot.SPOTTER not in crew:
        advice.append("• An empty Spotter seat means no specialist traffic/hazard support during close racing.")
    if CrewSlot.TYRE_CHANGER not in crew and team.stats.aggression >= 6:
        advice.append("• Your aggressive driver is hard on tyres; a Tyre Changer can offset some of that wear and improve tyre recovery in the pits.")
    if CrewSlot.FUEL_RUNNER not in crew and BuildService.effective_car_stats(team).heat >= 6:
        advice.append("• Heat is high and the Fuel Runner seat is empty. A specialist there can protect late-race consistency.")
    if illegal:
        advice.append(f"⚠ Illegal hardware currently adds **{illegal}%** pre-race DSQ risk. Keep it only if the shortcut is worth losing the whole race.")

    return advice[:8]


def saved_setup_summary(rows) -> dict[str, list[str]]:
    result: dict[str, list[str]] = {}
    for row in rows or []:
        name = str(row["setup_name"])
        raw = row["parts_json"]
        import json

        try:
            parts = normalized_parts(json.loads(raw))
        except Exception:
            parts = []
        result[name] = parts
    return result
