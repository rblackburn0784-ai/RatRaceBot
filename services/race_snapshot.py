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
    )


def build_replay_snapshot(
    teams: list[Team],
    *,
    laps: int,
    initial_damage_by_team_id: dict[int, int] | None = None,
    weather_key: str | None = None,
    rng_state: tuple | None = None,
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
