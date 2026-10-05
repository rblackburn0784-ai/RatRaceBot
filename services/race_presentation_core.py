from __future__ import annotations

import math
from collections.abc import Iterable

from models.domain import RaceState
from services.builds import BuildService

PHASE_LABELS = {
    "start": "🏁 Start",
    "opening": "🚦 Opening Laps",
    "mid": "⚙️ Mid-Race",
    "pit": "🔧 Pit Window",
    "closing": "🔥 Closing Laps",
    "final": "🏆 Final Lap",
}


def phase_for_lap(lap: int, laps: int) -> str:
    if lap <= 0:
        return "start"
    if lap >= laps:
        return "final"
    opening_end = max(1, round(laps * 0.25))
    mid_end = max(opening_end + 1, round(laps * 0.45))
    pit_end = max(mid_end + 1, round(laps * 0.65))
    if lap <= opening_end:
        return "opening"
    if lap <= mid_end:
        return "mid"
    if lap <= pit_end:
        return "pit"
    return "closing"


def phase_label(lap: int, laps: int) -> str:
    return PHASE_LABELS[phase_for_lap(lap, laps)]


def leaderboard_checkpoints(laps: int) -> set[int]:
    points = {2, max(2, math.ceil(laps / 2)), max(2, laps - 2), laps}
    return {min(laps, max(1, point)) for point in points}


def leaderboard_snapshot(states: Iterable[RaceState], laps: int) -> list[dict]:
    ordered = list(states)
    running = [state for state in ordered if not state.dnf and not state.disqualified]
    leader_time = running[0].total_time if running else 0.0
    leader_lap = running[0].lap if running else 0
    rows: list[dict] = []
    for state in ordered:
        if state.disqualified:
            gap = "DSQ"
        elif state.dnf:
            gap = f"DNF L{state.lap}/{laps}"
        elif state.position == 1:
            gap = "LEADER"
        elif state.lap < leader_lap:
            gap = f"-{leader_lap - state.lap} lap"
        else:
            gap = f"+{max(0.0, state.total_time - leader_time):.1f}s"
        rows.append({
            "position": state.position,
            "team_name": state.team.name,
            "gap": gap,
            "damage": min(100, int(state.damage)),
            "tyres": min(100, int(state.tyre_wear)),
            "strain": BuildService.build_strain_label(state.team),
            "lap": state.lap,
        })
    return rows
