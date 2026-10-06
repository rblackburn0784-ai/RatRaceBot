from __future__ import annotations

from dataclasses import asdict
from typing import Any

from models.domain import Team
from models.enums import CarArchetype
from models.stats import DriverStats

REPLAY_SNAPSHOT_VERSION = 1


def team_to_snapshot(team: Team) -> dict[str, Any]:
    return {
        "id": team.id,
        "name": team.name,
        "driver_name": team.driver_name,
        "pit_crew_name": team.pit_crew_name,
        "car_name": team.car_name,
        "archetype": team.archetype.value,
        "stats": asdict(team.stats),
        "parts": list(team.parts),
        "owner_user_id": team.owner_user_id,
        "crew": dict(team.crew),
        "active_sponsor_key": team.active_sponsor_key,
        "livery_key": team.livery_key,
        "emblem_key": team.emblem_key,
        "garage_decor_key": team.garage_decor_key,
        "intro_phrase": team.intro_phrase,
    }


def team_from_snapshot(data: dict[str, Any]) -> Team:
    return Team(
        id=int(data["id"]) if data.get("id") is not None else None,
        name=str(data["name"]),
        driver_name=str(data["driver_name"]),
        pit_crew_name=str(data["pit_crew_name"]),
        car_name=str(data["car_name"]),
        archetype=CarArchetype(str(data["archetype"])),
        stats=DriverStats(**{key: int(value) for key, value in dict(data["stats"]).items()}),
        parts=[str(key) for key in data.get("parts", [])],
        owner_user_id=int(data["owner_user_id"]) if data.get("owner_user_id") is not None else None,
        crew={str(key): str(value) for key, value in dict(data.get("crew", {})).items()},
        active_sponsor_key=str(data["active_sponsor_key"]) if data.get("active_sponsor_key") else None,
        livery_key=str(data.get("livery_key") or "bare_primer"),
        emblem_key=str(data.get("emblem_key") or "rat_skull"),
        garage_decor_key=str(data.get("garage_decor_key") or "oil_stained_bench"),
        intro_phrase=str(data.get("intro_phrase") or ""),
    )


def build_replay_snapshot(
    teams: list[Team],
    *,
    laps: int,
    initial_damage_by_team_id: dict[int, int] | None = None,
    weather_key: str | None = None,
    rng_state: tuple | None = None,
    rivalry_heat_by_pair: dict[tuple[int, int], int] | None = None,
) -> dict[str, Any]:
    return {
        "version": REPLAY_SNAPSHOT_VERSION,
        "laps": int(laps),
        "teams": [team_to_snapshot(team) for team in teams],
        "initial_damage_by_team_id": {
            str(int(team_id)): int(damage)
            for team_id, damage in (initial_damage_by_team_id or {}).items()
        },
        "weather_key": weather_key,
        "rng_state": rng_state,
        "rivalry_heat_by_pair": {
            f"{min(int(first), int(second))}:{max(int(first), int(second))}": min(100, max(0, int(heat)))
            for (first, second), heat in (rivalry_heat_by_pair or {}).items()
        },
    }


def _nested_tuple(value: Any) -> Any:
    if isinstance(value, list):
        return tuple(_nested_tuple(item) for item in value)
    return value


def restore_replay_snapshot(
    data: dict[str, Any],
) -> tuple[list[Team], int, dict[int, int], str | None, tuple | None]:
    version = int(data.get("version", 0))
    if version != REPLAY_SNAPSHOT_VERSION:
        raise ValueError(f"Unsupported replay snapshot version: {version}")

    teams = [team_from_snapshot(item) for item in data.get("teams", [])]
    laps = int(data["laps"])
    initial_damage = {
        int(team_id): int(damage)
        for team_id, damage in dict(data.get("initial_damage_by_team_id", {})).items()
    }
    weather_key = str(data["weather_key"]) if data.get("weather_key") else None
    rng_state = _nested_tuple(data.get("rng_state")) if data.get("rng_state") is not None else None
    return teams, laps, initial_damage, weather_key, rng_state



def restore_replay_rivalry_heat(data: dict[str, Any]) -> dict[tuple[int, int], int]:
    restored: dict[tuple[int, int], int] = {}
    for raw_key, raw_heat in dict(data.get("rivalry_heat_by_pair", {})).items():
        try:
            first, second = (int(value) for value in str(raw_key).split(":", 1))
            restored[(min(first, second), max(first, second))] = min(100, max(0, int(raw_heat)))
        except (TypeError, ValueError):
            continue
    return restored
