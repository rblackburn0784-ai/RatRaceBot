from __future__ import annotations

import asyncio
from dataclasses import dataclass


@dataclass(slots=True)
class Reservation:
    team_ids: set[int]
    tournament_id: int | None = None


class RaceActivityRegistry:
    """Process-local protection against overlapping races and race lobbies."""

    def __init__(self) -> None:
        self._lock = asyncio.Lock()
        self._active_team_ids: set[int] = set()
        self._lobby_team_ids: set[int] = set()
        self._active_tournament_ids: set[int] = set()

    @staticmethod
    def _real_team_ids(team_ids) -> set[int]:
        return {int(team_id) for team_id in team_ids if team_id is not None and int(team_id) > 0}

    async def reserve_lobby_team(self, team_id: int) -> bool:
        if team_id <= 0:
            return True
        async with self._lock:
            if team_id in self._active_team_ids or team_id in self._lobby_team_ids:
                return False
            self._lobby_team_ids.add(team_id)
            return True

    async def release_lobby_teams(self, team_ids) -> None:
        ids = self._real_team_ids(team_ids)
        async with self._lock:
            self._lobby_team_ids.difference_update(ids)

    async def promote_lobby_to_race(self, team_ids) -> Reservation | None:
        ids = self._real_team_ids(team_ids)
        async with self._lock:
            conflict = ids & self._active_team_ids
            if conflict:
                return None
            self._lobby_team_ids.difference_update(ids)
            self._active_team_ids.update(ids)
            return Reservation(ids)

    async def reserve_race(self, team_ids, tournament_id: int | None = None) -> Reservation | None:
        ids = self._real_team_ids(team_ids)
        async with self._lock:
            if ids & (self._active_team_ids | self._lobby_team_ids):
                return None
            if tournament_id is not None and tournament_id in self._active_tournament_ids:
                return None
            self._active_team_ids.update(ids)
            if tournament_id is not None:
                self._active_tournament_ids.add(tournament_id)
            return Reservation(ids, tournament_id)

    async def release(self, reservation: Reservation | None) -> None:
        if reservation is None:
            return
        async with self._lock:
            self._active_team_ids.difference_update(reservation.team_ids)
            if reservation.tournament_id is not None:
                self._active_tournament_ids.discard(reservation.tournament_id)

    async def is_team_busy(self, team_id: int) -> bool:
        if team_id <= 0:
            return False
        async with self._lock:
            return team_id in self._active_team_ids or team_id in self._lobby_team_ids
