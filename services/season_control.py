from __future__ import annotations

import json
from typing import Any, Mapping, Sequence

import discord

from data.defaults import TRACKS
from services.championship import calendar_entries, team_form, title_picture


def _get(row: Mapping[str, Any] | Any, key: str, default: Any = None) -> Any:
    if isinstance(row, Mapping):
        return row.get(key, default)
    try:
        return row[key]
    except (KeyError, IndexError, TypeError):
        return getattr(row, key, default)


def phase_icon(value: Any) -> str:
    return "✅" if bool(int(value or 0)) else "⬜"


async def build_season_director_snapshot(db, tournament_id: int) -> dict[str, Any]:
    tournament = await db.get_tournament(int(tournament_id))
    if not tournament:
        raise ValueError("Tournament not found.")

    standings = await db.standings(int(tournament_id))
    schedule = await db.tournament_schedule(int(tournament_id))
    races = await db.tournament_races(int(tournament_id))
    entries = calendar_entries(schedule, races)
    completed = sum(1 for entry in entries if entry["status"] == "completed")
    total = len(entries)
    next_entry = next((entry for entry in entries if entry["status"] == "next"), None)

    if total:
        picture = title_picture(standings, max(0, total - completed))
    else:
        picture = {"text": "Manual championship · no saved calendar.", "contenders": []}

    contenders = list(picture.get("contenders") or [])
    contender_ids = {int(item.get("team_id") or 0) for item in contenders}
    form_rows = []
    for row in standings:
        team_id = int(_get(row, "team_id", 0))
        if contender_ids and team_id not in contender_ids:
            continue
        form = " · ".join(team_form(races, team_id, 5)) or "—"
        form_rows.append(
            {
                "team_id": team_id,
                "name": str(_get(row, "name", "Team")),
                "points": int(_get(row, "points", 0)),
                "form": form,
            }
        )

    operation = await db.latest_season_race_state(int(tournament_id))
    history = await db.season_history_entry(int(tournament_id))
    history_status = "complete" if history else "pending"

    return {
        "tournament": tournament,
        "standings": standings,
        "schedule": schedule,
        "races": races,
        "entries": entries,
        "completed_rounds": completed,
        "total_rounds": total,
        "current_round": completed,
        "next_entry": next_entry,
        "leader": standings[0] if standings else None,
        "title_picture": picture,
        "contenders": contenders,
        "recent_form": form_rows,
        "operation": operation,
        "history_status": history_status,
    }


def season_director_embed(snapshot: dict[str, Any]) -> discord.Embed:
    tournament = snapshot["tournament"]
    status = str(_get(tournament, "status", "open")).lower()
    status_label = {
        "open": "🟢 OPEN",
        "paused": "⏸️ PAUSED",
        "closed": "🏁 CLOSED",
        "cancelled": "🛑 CANCELLED",
    }.get(status, status.upper())
    completed = int(snapshot["completed_rounds"])
    total = int(snapshot["total_rounds"])
    next_entry = snapshot["next_entry"]
    leader = snapshot["leader"]
    operation = snapshot["operation"]

    embed = discord.Embed(
        title=f"🎛️ SEASON DIRECTOR — {_get(tournament, 'name', 'Championship')}",
        description=(
            f"Status: **{status_label}**\n"
            + (
                f"Rounds: **{completed}/{total} complete**"
                if total
                else "Manual championship · no saved calendar"
            )
        ),
        color=discord.Color.gold() if status == "open" else discord.Color.orange(),
    )

    if next_entry:
        embed.add_field(
            name="🏁 Next Race",
            value=(
                f"**Round {next_entry['race_number']}** · **{next_entry['track_name']}**\n"
                f"Track key: `{next_entry['track_key']}`"
            ),
            inline=True,
        )
    else:
        embed.add_field(
            name="🏁 Next Race",
            value="No scheduled round remaining.",
            inline=True,
        )

    if leader:
        embed.add_field(
            name="🥇 Championship Leader",
            value=f"**{_get(leader, 'name', 'Leader')}** · **{_get(leader, 'points', 0)} pts**",
            inline=True,
        )
    else:
        embed.add_field(name="🥇 Championship Leader", value="No standings yet.", inline=True)

    contender_names = [str(item.get("name", "Team")) for item in snapshot["contenders"]]
    embed.add_field(
        name="📐 Mathematical Title Picture",
        value=(
            snapshot["title_picture"]["text"][:1024]
            if snapshot["title_picture"].get("text")
            else "No title calculation available."
        ),
        inline=False,
    )
    embed.add_field(
        name=f"🏎️ Still Eligible ({len(contender_names)})",
        value=", ".join(contender_names[:10]) if contender_names else "No eligible teams calculated yet.",
        inline=False,
    )

    form_lines = [
        f"**{item['name']}** · {item['points']} pts · `{item['form']}`"
        for item in snapshot["recent_form"][:8]
    ]
    embed.add_field(
        name="📊 Recent Form",
        value="\n".join(form_lines)[:1024] if form_lines else "No championship form yet.",
        inline=False,
    )

    if operation:
        phase = str(_get(operation, "phase", "pending")).replace("_", " ").title()
        ops = (
            f"{phase_icon(_get(operation, 'race_simulated', 0))} Race simulated\n"
            f"{phase_icon(_get(operation, 'standings_updated', 0))} Standings updated\n"
            f"{phase_icon(_get(operation, 'rewards_processed', 0))} Rewards processed\n"
            f"{phase_icon(_get(operation, 'gazette_generated', 0))} Gazette generated\n"
            f"{'✅' if snapshot['history_status'] == 'complete' else '⬜'} Season history {snapshot['history_status']}"
        )
        round_number = _get(operation, "round_number", "?")
        race_id = _get(operation, "race_id", None)
        detail = f"Latest: **Round {round_number}** · phase **{phase}**"
        if race_id:
            detail += f" · Race #{race_id}"
        error_text = str(_get(operation, "error_text", "") or "").strip()
        if error_text:
            detail += f"\n⚠️ {error_text[:220]}"
        embed.add_field(name="🧰 Operation State", value=f"{detail}\n{ops}", inline=False)
    else:
        embed.add_field(
            name="🧰 Operation State",
            value=(
                "⬜ Race simulated\n⬜ Standings updated\n⬜ Rewards processed\n"
                "⬜ Gazette generated\n"
                f"{'✅' if snapshot['history_status'] == 'complete' else '⬜'} Season history {snapshot['history_status']}"
            ),
            inline=False,
        )

    embed.set_footer(
        text="Season Director controls championship administration; destructive actions require confirmation."
    )
    return embed


def race_results_from_row(row) -> list[dict[str, Any]]:
    try:
        value = json.loads(row["results_json"] or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []
