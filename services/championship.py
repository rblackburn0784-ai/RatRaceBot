from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable, Mapping, Sequence

import discord

from data.defaults import POINTS_BY_POSITION, TRACKS


@dataclass(frozen=True, slots=True)
class SeasonAward:
    key: str
    name: str
    emoji: str
    team_id: int | None
    team_name: str
    detail: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "name": self.name,
            "emoji": self.emoji,
            "team_id": self.team_id,
            "team_name": self.team_name,
            "detail": self.detail,
        }


def _get(row: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def _loads(value: Any, default: Any) -> Any:
    if value in (None, ""):
        return default
    if isinstance(value, (list, dict)):
        return value
    try:
        return json.loads(value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return default


def _race_results(race: Mapping[str, Any] | Any) -> list[dict[str, Any]]:
    return list(_loads(_get(race, "results_json", []), []))


def _race_events(race: Mapping[str, Any] | Any) -> list[dict[str, Any]]:
    return list(_loads(_get(race, "events_json", []), []))


def is_championship_race(race: Mapping[str, Any] | Any) -> bool:
    value = _get(race, "championship_round", None)
    if value is not None:
        return bool(int(value))
    # Legacy rows pre-date the explicit marker and already affected standings.
    return True


def official_result(result: Mapping[str, Any]) -> bool:
    return not bool(result.get("dnf")) and not bool(result.get("disqualified"))


def result_token(result: Mapping[str, Any] | None) -> str:
    if not result:
        return "—"
    if result.get("disqualified"):
        return "DSQ"
    if result.get("dnf"):
        return "DNF"
    position = int(result.get("position", 0) or 0)
    if position == 1:
        return "W"
    return f"P{position}" if position > 0 else "—"


def championship_races(races: Iterable[Mapping[str, Any] | Any]) -> list[Any]:
    return [race for race in races if is_championship_race(race)]


def team_form(races: Iterable[Mapping[str, Any] | Any], team_id: int, limit: int = 5) -> list[str]:
    tokens: list[str] = []
    for race in championship_races(races):
        result = next((r for r in _race_results(race) if int(r.get("team_id", 0)) == int(team_id)), None)
        if result is not None:
            tokens.append(result_token(result))
    return tokens[-limit:]


def head_to_head(races: Iterable[Mapping[str, Any] | Any], first_team_id: int, second_team_id: int) -> dict[str, int]:
    first = second = ties = meetings = 0
    for race in championship_races(races):
        results = _race_results(race)
        a = next((r for r in results if int(r.get("team_id", 0)) == int(first_team_id)), None)
        b = next((r for r in results if int(r.get("team_id", 0)) == int(second_team_id)), None)
        if not a or not b:
            continue
        meetings += 1
        ap = int(a.get("position", 999))
        bp = int(b.get("position", 999))
        if ap < bp:
            first += 1
        elif bp < ap:
            second += 1
        else:
            ties += 1
    return {"first": first, "second": second, "ties": ties, "meetings": meetings}


def calendar_entries(
    schedule_rows: Sequence[Mapping[str, Any] | Any],
    races: Sequence[Mapping[str, Any] | Any],
) -> list[dict[str, Any]]:
    by_round = {
        int(_get(race, "schedule_race_number", 0)): race
        for race in races
        if _get(race, "schedule_race_number", None) is not None
    }
    completed = len(by_round)
    entries: list[dict[str, Any]] = []
    for schedule in schedule_rows:
        number = int(_get(schedule, "race_number", 0))
        track_key = str(_get(schedule, "track_key", ""))
        race = by_round.get(number)
        status = "completed" if race else "next" if number == completed + 1 else "queued"
        winner = None
        fastest = None
        if race:
            results = _race_results(race)
            winner_result = next((r for r in sorted(results, key=lambda item: int(item.get("position", 999))) if official_result(r)), None)
            if winner_result:
                winner = winner_result.get("team_name")
            timed = [r for r in results if official_result(r) and r.get("fastest_lap") is not None]
            if timed:
                fastest_result = min(timed, key=lambda item: float(item.get("fastest_lap") or 10**9))
                fastest = {
                    "team_name": fastest_result.get("team_name"),
                    "time": float(fastest_result.get("fastest_lap")),
                }
        entries.append(
            {
                "race_number": number,
                "track_key": track_key,
                "track_name": TRACKS[track_key].name if track_key in TRACKS else track_key,
                "status": status,
                "race_id": int(_get(race, "id", 0)) if race else None,
                "winner": winner,
                "fastest": fastest,
            }
        )
    return entries


def title_picture(standings: Sequence[Mapping[str, Any] | Any], remaining_rounds: int) -> dict[str, Any]:
    if not standings:
        return {"text": "No championship standings yet.", "contenders": []}
    ordered = list(standings)
    leader = ordered[0]
    leader_points = int(_get(leader, "points", 0))
    max_per_round = max(POINTS_BY_POSITION.values(), default=10)
    remaining_rounds = max(0, int(remaining_rounds))
    max_remaining = remaining_rounds * max_per_round
    contenders = [
        {
            "team_id": int(_get(row, "team_id", 0)),
            "name": str(_get(row, "name", "Team")),
            "points": int(_get(row, "points", 0)),
        }
        for row in ordered
        if int(_get(row, "points", 0)) + max_remaining >= leader_points
    ]

    if remaining_rounds == 0:
        return {
            "text": f"🏆 **{_get(leader, 'name', 'Leader')}** is champion on **{leader_points} pts**.",
            "contenders": contenders[:1],
            "clinched": True,
        }

    second_points = int(_get(ordered[1], "points", 0)) if len(ordered) > 1 else -10**6
    gap = leader_points - second_points
    if gap > max_remaining:
        return {
            "text": f"🏆 **{_get(leader, 'name', 'Leader')}** has mathematically clinched the title with {remaining_rounds} round(s) left.",
            "contenders": contenders[:1],
            "clinched": True,
        }

    clinch_position = None
    # Guarantee after the next round even if the nearest rival wins every remaining round.
    threshold = max_remaining - gap
    for position in sorted(POINTS_BY_POSITION):
        if POINTS_BY_POSITION[position] > threshold:
            clinch_position = position
        else:
            break

    lines = [
        f"**{_get(leader, 'name', 'Leader')}** leads by **{gap} pts** with **{remaining_rounds}** round(s) remaining.",
        f"Maximum remaining score: **{max_remaining} pts**.",
    ]
    if clinch_position is not None:
        label = "a win" if clinch_position == 1 else f"P{clinch_position} or better"
        lines.append(f"🏁 The leader can clinch next round with **{label}**, regardless of the nearest rival's result.")
    if len(contenders) > 1:
        lines.append("Still mathematically alive: " + ", ".join(item["name"] for item in contenders[:6]) + ("…" if len(contenders) > 6 else ""))
    else:
        lines.append("Only the championship leader remains mathematically alive.")
    return {"text": "\n".join(lines), "contenders": contenders, "clinched": False, "gap": gap}


def _best(rows: Sequence[Mapping[str, Any] | Any], key, reverse: bool = True):
    return sorted(rows, key=key, reverse=reverse)[0] if rows else None


def _award(key: str, name: str, emoji: str, row: Any | None, detail: str) -> SeasonAward:
    return SeasonAward(
        key=key,
        name=name,
        emoji=emoji,
        team_id=int(_get(row, "team_id", 0)) if row is not None and _get(row, "team_id", None) is not None else None,
        team_name=str(_get(row, "name", "No award")) if row is not None else "No award",
        detail=detail,
    )


def _pit_scores(races: Sequence[Mapping[str, Any] | Any]) -> dict[int, dict[str, float]]:
    scores: dict[int, dict[str, float]] = defaultdict(lambda: {"score": 0.0, "stops": 0.0, "time": 0.0, "gains": 0.0})
    for race in championship_races(races):
        for event in _race_events(race):
            event_type = str(event.get("event_type", ""))
            if event_type not in {"pit_stop", "EventType.PIT_STOP"}:
                continue
            actor = event.get("actor") or {}
            team_id = int(actor.get("team_id", 0) or 0)
            if team_id <= 0:
                continue
            context = event.get("context") or {}
            quality = str(context.get("pit_quality", "Solid"))
            quality_score = {"Fast": 3.0, "Solid": 1.0, "Botched": -2.0}.get(quality, 0.0)
            delta = float(context.get("position_delta", 0) or 0)
            time_cost = float(context.get("time_cost", 0) or 0)
            scores[team_id]["score"] += quality_score + max(-2.0, min(2.0, delta * 0.75))
            scores[team_id]["stops"] += 1
            scores[team_id]["time"] += time_cost
            scores[team_id]["gains"] += max(0.0, delta)
    return scores


def build_season_awards(
    standings: Sequence[Mapping[str, Any] | Any],
    races: Sequence[Mapping[str, Any] | Any],
) -> list[dict[str, Any]]:
    rows = list(standings)
    if not rows:
        return []

    awards: list[SeasonAward] = []
    champion = rows[0]
    runner_up = rows[1] if len(rows) > 1 else None
    awards.append(_award("champion", "Champion", "🏆", champion, f"{_get(champion, 'points', 0)} championship points"))
    if runner_up is not None:
        awards.append(_award("runner_up", "Runner-Up", "🥈", runner_up, f"{_get(runner_up, 'points', 0)} championship points"))

    most_wins = _best(rows, lambda r: (int(_get(r, "wins", 0)), int(_get(r, "points", 0)), -int(_get(r, "dnfs", 0))))
    most_podiums = _best(rows, lambda r: (int(_get(r, "podiums", 0)), int(_get(r, "points", 0)), int(_get(r, "wins", 0))))
    fastest = _best(rows, lambda r: (int(_get(r, "fastest_laps", 0)), int(_get(r, "points", 0)), int(_get(r, "wins", 0))))
    overtake = _best(rows, lambda r: (int(_get(r, "overtakes", 0)), int(_get(r, "points", 0))))

    awards.extend(
        [
            _award("most_wins", "Most Wins", "🥇", most_wins, f"{_get(most_wins, 'wins', 0)} wins"),
            _award("most_podiums", "Most Podiums", "🎖️", most_podiums, f"{_get(most_podiums, 'podiums', 0)} podiums"),
            _award("fastest_driver", "Fastest Driver", "⚡", fastest, f"{_get(fastest, 'fastest_laps', 0)} race fastest laps"),
            _award("overtake_king", "Overtake King", "🏁", overtake, f"{_get(overtake, 'overtakes', 0)} overtakes"),
        ]
    )

    def trouble(row: Any) -> int:
        return int(_get(row, "warnings", 0)) + 2 * int(_get(row, "illegal_moves", 0)) + 5 * int(_get(row, "disqualifications", 0))

    cleanest = sorted(rows, key=lambda r: (trouble(r), int(_get(r, "crashes", 0)), -int(_get(r, "points", 0)), str(_get(r, "name", ""))))[0]
    dirtiest = _best(rows, lambda r: (trouble(r), int(_get(r, "illegal_moves", 0)), int(_get(r, "warnings", 0)), -int(_get(r, "points", 0))))
    reliable = sorted(
        rows,
        key=lambda r: (
            int(_get(r, "dnfs", 0)) + int(_get(r, "disqualifications", 0)),
            int(_get(r, "peak_carryover_damage", 0)),
            -int(_get(r, "points", 0)),
        ),
    )[0]
    awards.extend(
        [
            _award("cleanest_team", "Cleanest Team", "🧼", cleanest, f"discipline score {trouble(cleanest)}"),
            _award("dirtiest_team", "Dirtiest Team", "🚨", dirtiest, f"discipline score {trouble(dirtiest)}"),
            _award(
                "most_reliable",
                "Most Reliable",
                "🔩",
                reliable,
                f"{int(_get(reliable, 'dnfs', 0))} DNF / {int(_get(reliable, 'disqualifications', 0))} DSQ",
            ),
        ]
    )

    pit_scores = _pit_scores(races)
    pit_row = None
    pit_detail = "No championship pit stops recorded"
    if pit_scores:
        by_id = {int(_get(row, "team_id", 0)): row for row in rows}
        best_id, score = max(
            pit_scores.items(),
            key=lambda item: (item[1]["score"], item[1]["gains"], -item[1]["time"] / max(1.0, item[1]["stops"])),
        )
        pit_row = by_id.get(best_id)
        pit_detail = f"pit score {score['score']:.1f} across {int(score['stops'])} stop(s)"
    awards.append(_award("best_pit_crew", "Best Pit Crew", "🔧", pit_row, pit_detail))

    outside_top_three = rows[3:] if len(rows) > 3 else rows
    giant = _best(outside_top_three, lambda r: (int(_get(r, "wins", 0)) * 4 + int(_get(r, "podiums", 0)) * 2, int(_get(r, "points", 0)), int(_get(r, "overtakes", 0))))
    awards.append(
        _award(
            "giant_killer",
            "Giant Killer",
            "🪓",
            giant,
            f"{_get(giant, 'wins', 0)} wins / {_get(giant, 'podiums', 0)} podiums from outside the final top three" if giant else "No award",
        )
    )

    hard_luck = _best(
        rows,
        lambda r: (
            int(_get(r, "dnfs", 0)) * 5 + int(_get(r, "crashes", 0)) + int(_get(r, "peak_carryover_damage", 0)) / 10.0,
            int(_get(r, "dnfs", 0)),
            int(_get(r, "peak_carryover_damage", 0)),
        ),
    )
    awards.append(
        _award(
            "hard_luck",
            "Hard Luck Award",
            "🍀",
            hard_luck,
            f"{_get(hard_luck, 'dnfs', 0)} DNF, {_get(hard_luck, 'crashes', 0)} crashes, peak carryover {_get(hard_luck, 'peak_carryover_damage', 0)}%",
        )
    )
    return [award.as_dict() for award in awards]


def build_season_summary(
    standings: Sequence[Mapping[str, Any] | Any],
    races: Sequence[Mapping[str, Any] | Any],
    scheduled_races: int,
) -> dict[str, Any]:
    official = championship_races(races)
    completed_scheduled = sum(1 for race in races if _get(race, "schedule_race_number", None) is not None)
    total_overtakes = sum(int(_get(row, "overtakes", 0)) for row in standings)
    total_crashes = sum(int(_get(row, "crashes", 0)) for row in standings)
    total_dnfs = sum(int(_get(row, "dnfs", 0)) for row in standings)
    total_dsqs = sum(int(_get(row, "disqualifications", 0)) for row in standings)
    return {
        "championship_races": len(official),
        "scheduled_races": int(scheduled_races),
        "completed_scheduled_races": completed_scheduled,
        "season_status": "complete" if scheduled_races and completed_scheduled >= scheduled_races else "shortened" if scheduled_races else "manual",
        "total_overtakes": total_overtakes,
        "total_crashes": total_crashes,
        "total_dnfs": total_dnfs,
        "total_disqualifications": total_dsqs,
    }


def awards_from_history(row: Mapping[str, Any] | Any) -> list[dict[str, Any]]:
    return list(_loads(_get(row, "awards_json", "[]"), []))


def summary_from_history(row: Mapping[str, Any] | Any) -> dict[str, Any]:
    return dict(_loads(_get(row, "summary_json", "{}"), {}))


def calendar_text(entries: Sequence[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for entry in entries:
        status = entry["status"]
        marker = "✅" if status == "completed" else "➡️" if status == "next" else "⬜"
        suffix = ""
        if entry.get("winner"):
            suffix = f" — Winner: **{entry['winner']}**"
        lines.append(f"{marker} **R{entry['race_number']}** {entry['track_name']}{suffix}")
    return "\n".join(lines) if lines else "No saved calendar."


def championship_hub_embed(
    tournament: Mapping[str, Any] | Any,
    standings: Sequence[Mapping[str, Any] | Any],
    schedule_rows: Sequence[Mapping[str, Any] | Any],
    races: Sequence[Mapping[str, Any] | Any],
    rivalries: Sequence[Mapping[str, Any] | Any] = (),
) -> discord.Embed:
    entries = calendar_entries(schedule_rows, races)
    completed = sum(1 for entry in entries if entry["status"] == "completed")
    total = len(entries)
    status = str(_get(tournament, "status", "open"))
    next_entry = next((entry for entry in entries if entry["status"] == "next"), None)
    if total:
        subtitle = f"Round **{completed}/{total}**"
        if next_entry:
            subtitle += f" · Next: **{next_entry['track_name']}**"
        elif status == "closed":
            subtitle += " · Season complete"
    else:
        subtitle = "Manual championship · No saved calendar"

    embed = discord.Embed(
        title=f"🏆 BLACKTOP CHAMPIONSHIP — {_get(tournament, 'name', 'Championship')}",
        description=subtitle,
        color=discord.Color.gold(),
    )

    standing_lines = []
    for index, row in enumerate(standings[:10], start=1):
        form = " · ".join(team_form(races, int(_get(row, "team_id", 0)), 3)) or "—"
        standing_lines.append(
            f"**{index}. {_get(row, 'name', 'Team')}** — {_get(row, 'points', 0)} pts | "
            f"W {_get(row, 'wins', 0)} | P {_get(row, 'podiums', 0)} | FL {_get(row, 'fastest_laps', 0)} | `{form}`"
        )
    embed.add_field(name="Championship Standings", value="\n".join(standing_lines)[:1024] if standing_lines else "No results yet.", inline=False)

    if total:
        picture = title_picture(standings, max(0, total - completed))
        embed.add_field(name="Title Picture", value=picture["text"][:1024], inline=False)

    if len(standings) >= 2:
        first = standings[0]
        second = standings[1]
        h2h = head_to_head(races, int(_get(first, "team_id", 0)), int(_get(second, "team_id", 0)))
        embed.add_field(
            name="Head-to-Head — Top Two",
            value=(
                f"**{_get(first, 'name', 'P1')}** {h2h['first']}–{h2h['second']} **{_get(second, 'name', 'P2')}** "
                f"across {h2h['meetings']} championship round(s)."
            ),
            inline=False,
        )

    if rivalries:
        lines = [
            f"🔥 **{_get(row, 'team_a_name', 'Team A')}** vs **{_get(row, 'team_b_name', 'Team B')}** — Heat {_get(row, 'heat', 0)}"
            for row in rivalries[:3]
        ]
        embed.add_field(name="Rivalry Watch", value="\n".join(lines), inline=False)

    if entries:
        focus = [entry for entry in entries if entry["status"] in {"completed", "next"}][-4:]
        queued = [entry for entry in entries if entry["status"] == "queued"][:2]
        embed.add_field(name="Calendar", value=calendar_text((focus + queued)[-6:])[:1024], inline=False)

    embed.set_footer(text="Scheduled rounds decide the championship; ad-hoc races are exhibitions once a calendar exists.")
    return embed


def season_awards_text(awards: Sequence[Mapping[str, Any]]) -> str:
    if not awards:
        return "No season awards recorded."
    return "\n".join(
        f"{award.get('emoji', '🏅')} **{award.get('name', 'Award')}:** {award.get('team_name', 'No award')} — {award.get('detail', '')}"
        for award in awards
    )
