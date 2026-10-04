from __future__ import annotations

from collections.abc import Iterable

from models.domain import RaceResult


def is_official_finisher(result: RaceResult | dict) -> bool:
    getter = result.get if isinstance(result, dict) else lambda key, default=None: getattr(result, key, default)
    return not bool(getter("dnf", False)) and not bool(getter("disqualified", False))


def official_finishers(results: Iterable[RaceResult]) -> list[RaceResult]:
    return sorted((result for result in results if is_official_finisher(result)), key=lambda result: result.position)


def official_winner(results: Iterable[RaceResult]) -> RaceResult | None:
    finishers = official_finishers(results)
    return finishers[0] if finishers else None


def official_podium(results: Iterable[RaceResult]) -> list[RaceResult]:
    return official_finishers(results)[:3]
