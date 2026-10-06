from __future__ import annotations

import json
from typing import Any

import discord

from data.defaults import PARTS, TRACKS
from models.enums import CrewSlot, PartSlot
from services.builds import BuildService
from services.progression import level_for_xp, next_unlock
from services.racing_world import ensure_world_schema, heat_bar, pending_world_events
from services.sponsors import sponsor_by_key
from services.story import reputation_tags


def _json_list(raw: Any) -> list[dict[str, Any]]:
    try:
        value = json.loads(raw or "[]")
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return value if isinstance(value, list) else []


async def build_world_snapshot(db, team) -> dict[str, Any]:
    if not team or team.id is None:
        raise ValueError("A saved team is required for the Blacktop Racing World.")

    await ensure_world_schema(db)
    team_id = int(team.id)
    progress = await db.team_progress(team_id)
    profile = await db.team_profile(team_id)
    rivalries = await db.team_rivalries(team_id, limit=3)
    sponsor_offers = await db.team_sponsor_offers(team_id, limit=12)
    pending_events = await pending_world_events(db, team_id)
    setups = await db.team_setups(team_id)
    career = await db.team_career_summary(team_id)
    seasons = await db.team_season_history(team_id, limit=8)
    current_tournament = await db.current_tournament()

    xp = int(progress["xp"]) if progress else 0
    level = level_for_xp(xp)
    title = str(progress["cosmetic_title"]) if progress else "Garage Rookie"
    installed_slots = {PARTS[key].slot for key in team.parts if key in PARTS}
    assigned_crew = {slot for slot, key in team.crew.items() if key and slot in {item.value for item in CrewSlot}}
    offered = [row for row in sponsor_offers if str(row["status"]) == "offered"]
    active_sponsor = sponsor_by_key(team.active_sponsor_key)

    tournament_state = None
    if current_tournament:
        tournament_id = int(current_tournament["id"])
        standings = await db.standings(tournament_id)
        standing = next((row for row in standings if int(row["team_id"]) == team_id), None)
        next_track = await db.next_scheduled_track(tournament_id)
        tournament_state = {
            "id": tournament_id,
            "name": str(current_tournament["name"]),
            "entered": standing is not None,
            "position": (standings.index(standing) + 1) if standing is not None else None,
            "points": int(standing["points"]) if standing is not None else 0,
            "next_track": next_track,
        }

    readiness = {
        "parts": len(installed_slots),
        "part_slots": len(PartSlot),
        "crew": len(assigned_crew),
        "crew_slots": len(CrewSlot),
        "setups": len(setups),
        "illegal_risk": BuildService.illegal_disqualification_risk_percent(team),
        "strain": BuildService.build_strain(team),
    }

    if len(installed_slots) < len(PartSlot):
        next_action = "Open the garage and finish the car build."
        next_key = "garage"
    elif len(assigned_crew) < len(CrewSlot):
        next_action = "Hire or assign the remaining pit crew positions."
        next_key = "crew"
    elif not setups:
        next_action = "Save a track setup so the garage is ready for different venues."
        next_key = "setups"
    elif pending_events:
        next_action = "A Blacktop World decision is waiting for the team."
        next_key = "world_events"
    elif offered and not active_sponsor:
        next_action = "Review the sponsor offers waiting in the paddock."
        next_key = "sponsors"
    elif tournament_state and tournament_state["entered"] and tournament_state["next_track"]:
        race_number, track_key = tournament_state["next_track"]
        track_name = TRACKS[track_key].name if track_key in TRACKS else track_key
        next_action = f"Prepare for championship round {race_number} at {track_name}."
        next_key = "championship"
    else:
        next_action = "The team is ready. Pick a race and put the setup to work."
        next_key = "race"

    return {
        "team": team,
        "xp": xp,
        "level": level,
        "title": title,
        "profile": profile,
        "reputation": reputation_tags(profile),
        "rivalries": rivalries,
        "sponsor_offers": offered,
        "active_sponsor": active_sponsor,
        "pending_events": pending_events,
        "setups": setups,
        "career": career,
        "seasons": seasons,
        "tournament": tournament_state,
        "readiness": readiness,
        "next_action": next_action,
        "next_key": next_key,
    }


def world_hub_embed(snapshot: dict[str, Any]) -> discord.Embed:
    team = snapshot["team"]
    readiness = snapshot["readiness"]
    career = snapshot["career"]
    tournament = snapshot["tournament"]
    active_sponsor = snapshot["active_sponsor"]
    embed = discord.Embed(
        title=f"🌎 BLACKTOP RACING WORLD — {team.name}",
        description=(
            f"**{snapshot['title']} · Level {snapshot['level']}**\n"
            f"{team.driver_name} · {team.car_name} · {team.archetype.value}\n"
            f"Reputation: **{', '.join(snapshot['reputation'])}**"
        ),
        color=discord.Color.dark_gold(),
    )
    embed.add_field(
        name="Garage",
        value=(
            f"Parts **{readiness['parts']}/{readiness['part_slots']}** · Crew **{readiness['crew']}/{readiness['crew_slots']}**\n"
            f"Saved setups **{readiness['setups']}** · Illegal risk **{readiness['illegal_risk']}%** · Strain **{readiness['strain']}**"
        ),
        inline=True,
    )
    embed.add_field(
        name="Progression",
        value=(
            f"XP **{snapshot['xp']}** · Level **{snapshot['level']}**\n"
            f"Next unlock: {next_unlock(snapshot['level'])}"
        )[:1024],
        inline=True,
    )
    embed.add_field(
        name="Paddock",
        value=(
            f"Sponsor: **{active_sponsor.name if active_sponsor else 'Independent'}**\n"
            f"Offers **{len(snapshot['sponsor_offers'])}** · World decisions **{len(snapshot['pending_events'])}**"
        ),
        inline=True,
    )

    if snapshot["rivalries"]:
        hottest = snapshot["rivalries"][0]
        embed.add_field(
            name="🔥 Hottest Rivalry",
            value=f"**{hottest['opponent_name']}** · {heat_bar(int(hottest['heat']))} **{int(hottest['heat'])}/100**",
            inline=False,
        )
    else:
        embed.add_field(name="🔥 Hottest Rivalry", value="No serious grudge has formed yet.", inline=False)

    if tournament:
        if tournament["entered"]:
            next_text = "Season complete / no scheduled round left"
            if tournament["next_track"]:
                race_number, track_key = tournament["next_track"]
                track_name = TRACKS[track_key].name if track_key in TRACKS else track_key
                next_text = f"R{race_number}: {track_name}"
            championship_text = f"**{tournament['name']}** · P{tournament['position']} · {tournament['points']} pts\nNext: {next_text}"
        else:
            championship_text = f"**{tournament['name']}** is active; this team is not entered."
    else:
        championship_text = "No championship is currently open."
    embed.add_field(name="🏆 Championship", value=championship_text, inline=False)

    embed.add_field(
        name="Permanent Career",
        value=(
            f"Seasons **{career['seasons']}** · Titles **{career['titles']}** · Season podiums **{career['season_podiums']}**\n"
            f"Championship wins **{career['championship_wins']}** · Championship podiums **{career['championship_podiums']}** · "
            f"Fastest laps **{career['fastest_laps']}**"
        ),
        inline=False,
    )
    embed.add_field(name="➡️ What Next?", value=snapshot["next_action"], inline=False)
    embed.set_footer(text="Progression expands choices and identity; it never grants automatic victory.")
    return embed


def career_history_embed(team, career: dict[str, int], seasons) -> discord.Embed:
    embed = discord.Embed(
        title=f"📚 Permanent Team History — {team.name}",
        description=f"{team.driver_name} · {team.car_name}",
        color=discord.Color.purple(),
    )
    embed.add_field(
        name="Career",
        value=(
            f"Seasons **{career['seasons']}** · Championships **{career['titles']}** · Season podiums **{career['season_podiums']}**\n"
            f"Championship points **{career['championship_points']}** · Wins **{career['championship_wins']}** · "
            f"Podiums **{career['championship_podiums']}** · Fastest laps **{career['fastest_laps']}**"
        ),
        inline=False,
    )
    if not seasons:
        embed.add_field(name="Season Archive", value="No completed championship seasons yet.", inline=False)
        return embed
    lines = []
    for row in seasons[:8]:
        awards = _json_list(row["awards_json"])
        award_text = ", ".join(str(item.get("name", "Award")) for item in awards[:3]) or "No individual award"
        lines.append(
            f"**{row['season_name']}** — P{row['final_position']} · {row['points']} pts · "
            f"W {row['wins']} · Pod {row['podiums']} · FL {row['fastest_laps']}\n{award_text}"
        )
    embed.add_field(name="Season Archive", value="\n\n".join(lines)[:1024], inline=False)
    return embed


async def gazette_archive_embed(db, team, limit: int = 6) -> discord.Embed:
    embed = discord.Embed(
        title=f"📰 Blacktop Gazette Archive — {team.name}",
        description="Recent saved races involving this team.",
        color=discord.Color.dark_gold(),
    )
    rows = await db.recent_races(limit=40)
    stories = []
    for row in rows:
        results = _json_list(row["results_json"])
        mine = next((item for item in results if int(item.get("team_id") or 0) == int(team.id)), None)
        if not mine:
            continue
        official = not mine.get("dnf") and not mine.get("disqualified")
        track = TRACKS.get(str(row["track_key"]))
        track_name = track.name if track else str(row["track_key"])
        if mine.get("disqualified"):
            result_text = "DSQ"
        elif mine.get("dnf"):
            result_text = "DNF"
        else:
            result_text = f"P{mine.get('position', '?')}"
        headline = "WINNER" if official and int(mine.get("position") or 999) == 1 else result_text
        stories.append(
            f"**Race #{row['id']} · {track_name} — {headline}**\n"
            f"{mine.get('overtakes', 0)} overtakes · {mine.get('damage', 0)}% damage · {mine.get('points', 0)} pts"
        )
        if len(stories) >= limit:
            break
    embed.add_field(name="Recent Editions", value="\n\n".join(stories)[:1024] if stories else "No Gazette editions for this team yet.", inline=False)
    return embed


def season_awards_embed(team, seasons) -> discord.Embed:
    embed = discord.Embed(
        title=f"🏅 Season Awards — {team.name}",
        description="Permanent awards earned across completed championships.",
        color=discord.Color.gold(),
    )
    award_lines = []
    for row in seasons:
        for award in _json_list(row["awards_json"]):
            award_lines.append(
                f"**{row['season_name']} · {award.get('name', 'Award')}**\n{award.get('detail', '')}"
            )
    embed.add_field(name="Trophy Cabinet", value="\n\n".join(award_lines)[:1024] if award_lines else "No season awards yet.", inline=False)
    return embed
