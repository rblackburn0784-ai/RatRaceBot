import discord

from data.defaults import TRACKS
from models.domain import RaceEvent, RaceResult, Team
from services.engagement import (
    achievement_candidates,
    cosmetic_title_for_level,
    hype_embed,
    interview_embed,
    level_for_xp,
    newspaper_embed,
    sponsor_offer,
    xp_for_result,
)
from services.race_rules import is_official_finisher, official_podium, official_winner
from services.racing_world import maybe_create_world_event, record_race_world, world_event_embed
from services.sponsors import sponsor_by_key


async def process_race_rewards(
    db,
    track_key: str,
    race_id: int,
    teams: list[Team],
    results: list[RaceResult],
    events: list[RaceEvent],
    weather_name: str,
    title: str,
    race_laps: int,
) -> list[discord.Embed]:
    teams_by_id = {team.id: team for team in teams if team.id and team.id > 0}
    saved_results = [result for result in results if result.team_id in teams_by_id]
    xp_updates: list[dict] = []
    achievements: list[dict] = []
    sponsor_updates: list[dict] = []
    fatigue_updates: list[dict] = []
    level_ups: list[dict] = []
    levels_by_team: dict[int, int] = {}

    official_podium_ids = {result.team_id for result in official_podium(saved_results)}

    for result in saved_results:
        team = teams_by_id[result.team_id]
        current_progress = await db.team_progress(team.id)
        current_xp = int(current_progress["xp"]) if current_progress else 0
        base_xp = xp_for_result(result)
        active_sponsor = sponsor_by_key(team.active_sponsor_key)
        gained_xp = max(1, int(round(base_xp * (active_sponsor.xp_multiplier if active_sponsor else 1.0))))
        old_level = level_for_xp(current_xp)
        new_level = level_for_xp(current_xp + gained_xp)
        levels_by_team[team.id] = new_level
        if new_level > old_level:
            level_ups.append({"team_id": team.id, "team_name": team.name, "old_level": old_level, "new_level": new_level})
        xp_updates.append(
            {
                "team_id": team.id,
                "xp": gained_xp,
                "cosmetic_title": cosmetic_title_for_level(new_level),
            }
        )

        profile = await db.team_profile(team.id)
        projected_podiums = int(profile["podiums"]) if profile else 0
        if result.team_id in official_podium_ids:
            projected_podiums += 1
        projected_profile = {"podiums": projected_podiums}
        for key, name in achievement_candidates(result, projected_profile):
            achievements.append({"team_id": team.id, "team_name": team.name, "key": key, "name": name})

        if result.team_id in official_podium_ids:
            sponsor_key, sponsor_name, benefit, drawback = sponsor_offer(team, race_id, new_level)
            sponsor_updates.append(
                {
                    "team_id": team.id,
                    "team_name": team.name,
                    "sponsor_key": sponsor_key,
                    "sponsor_name": sponsor_name,
                    "benefit": benefit,
                    "drawback": drawback,
                }
            )

        if result.damage >= 75 or result.dnf:
            fatigue_updates.append(
                {
                    "team_id": team.id,
                    "key": "driver_shaken" if result.damage >= 75 else "crew_exhausted",
                    "name": "Driver Shaken" if result.damage >= 75 else "Crew Exhausted",
                    "description": "A rough race left this team carrying a short-term story flag.",
                    "races_remaining": 1,
                }
            )

    record_candidates = build_track_record_candidates(track_key, results, race_laps)
    processing = await db.process_post_race_atomic(
        race_id=race_id,
        results=[_result_dict(result) for result in saved_results],
        xp_updates=xp_updates,
        achievements=achievements,
        sponsor_offers=sponsor_updates,
        fatigue_updates=fatigue_updates,
        track_records=record_candidates,
    )

    await record_race_world(db, race_id, saved_results, events)
    world_event = await maybe_create_world_event(
        db,
        race_id=race_id,
        track_key=track_key,
        teams=teams,
    )

    embeds: list[discord.Embed] = []
    if world_event and world_event.get("status") == "pending":
        embeds.append(world_event_embed(world_event))
    new_records = processing.get("new_records", [])
    if new_records:
        embed = discord.Embed(title="Track Record Board", color=discord.Color.blue())
        lines = []
        for record in new_records:
            holder = f" by {record.get('team_name')}" if record.get("team_name") else ""
            lines.append(f"**{record['record_name']}:** {record['details']}{holder}")
        embed.add_field(name="New Records", value="\n".join(lines), inline=False)
        embeds.append(embed)

    embeds.append(hype_embed(results, events, title))
    gazette = newspaper_embed(results, title, TRACKS[track_key].name, weather_name)
    winner = official_winner(results)
    if winner and levels_by_team.get(winner.team_id, 1) >= 5:
        gazette.add_field(
            name="Established Name",
            value=f"**{winner.team_name}** has enough paddock reputation to earn featured Blacktop Gazette coverage.",
            inline=False,
        )
    embeds.append(gazette)

    winner_team = teams_by_id.get(winner.team_id) if winner else None
    if winner and winner_team:
        embeds.append(interview_embed(winner_team, winner, await db.team_profile(winner.team_id)))

    if processing.get("processed") and level_ups:
        embed = discord.Embed(title="Team Level Up", color=discord.Color.gold())
        embed.add_field(
            name="Progression Unlocks",
            value="\n".join(
                f"**{item['team_name']}** reached **Level {item['new_level']}** — new identity/setup/sponsor options may be available."
                for item in level_ups[:10]
            ),
            inline=False,
        )
        embeds.append(embed)

    new_achievements = processing.get("new_achievements", [])
    if new_achievements:
        embed = discord.Embed(title="New Achievements", color=discord.Color.green())
        embed.add_field(
            name="Unlocked",
            value="\n".join(
                f"**{item.get('team_name', 'Team')}** unlocked **{item['name']}**"
                for item in new_achievements[:10]
            ),
            inline=False,
        )
        embeds.append(embed)

    if processing.get("processed") and sponsor_updates:
        embed = discord.Embed(
            title="Sponsor Offers",
            description="New offers are waiting in `/sponsor_offers`.",
            color=discord.Color.dark_gold(),
        )
        embed.add_field(
            name="Fresh Interest",
            value="\n".join(
                f"**{offer['team_name']}** heard from **{offer['sponsor_name']}**"
                for offer in sponsor_updates[:10]
            ),
            inline=False,
        )
        embeds.append(embed)

    return embeds


def _result_dict(result: RaceResult) -> dict:
    return {
        "team_id": result.team_id,
        "team_name": result.team_name,
        "driver_name": result.driver_name,
        "position": result.position,
        "laps_completed": result.laps_completed,
        "total_time": result.total_time,
        "points": result.points,
        "warnings": result.warnings,
        "dnf": result.dnf,
        "disqualified": result.disqualified,
        "damage": result.damage,
        "tyre_wear": result.tyre_wear,
        "starting_damage": result.starting_damage,
        "overtakes": result.overtakes,
        "crashes": result.crashes,
        "illegal_moves": result.illegal_moves,
        "last_minute_wins": result.last_minute_wins,
        "pit_stops": result.pit_stops,
        "near_misses": result.near_misses,
        "fastest_lap": result.fastest_lap,
    }


def build_track_record_candidates(track_key: str, results: list[RaceResult], race_laps: int) -> list[dict]:
    finishers = [result for result in results if is_official_finisher(result)]
    total_crashes = sum(result.crashes for result in results)
    total_overtakes = sum(result.overtakes for result in results)
    chaos = total_crashes * 3 + total_overtakes + sum(result.illegal_moves for result in results) * 2
    candidates: list[dict] = []

    timed_finishers = [result for result in finishers if result.fastest_lap is not None]
    if timed_finishers:
        fastest_lap = min(timed_finishers, key=lambda result: float(result.fastest_lap or 10**9))
        candidates.append(
            {
                "track_key": track_key,
                "record_key": "fastest_lap",
                "record_name": "Fastest Lap",
                "record_value": float(fastest_lap.fastest_lap),
                "team_id": fastest_lap.team_id,
                "team_name": fastest_lap.team_name,
                "details": f"{float(fastest_lap.fastest_lap):.2f}s",
                "higher_is_better": False,
            }
        )

    if finishers and race_laps in {5, 7, 10}:
        fastest_race = min(finishers, key=lambda result: result.total_time)
        candidates.append(
            {
                "track_key": track_key,
                "record_key": f"fastest_race_{race_laps}",
                "record_name": f"Fastest {race_laps}-Lap Race",
                "record_value": float(fastest_race.total_time),
                "team_id": fastest_race.team_id,
                "team_name": fastest_race.team_name,
                "details": f"{fastest_race.total_time:.2f}s",
                "higher_is_better": False,
            }
        )

    candidates.extend(
        [
            {
                "track_key": track_key,
                "record_key": "most_crashes",
                "record_name": "Most Crashes In Race",
                "record_value": float(total_crashes),
                "team_id": None,
                "team_name": None,
                "details": f"{total_crashes} crashes",
                "higher_is_better": True,
            },
            {
                "track_key": track_key,
                "record_key": "most_overtakes",
                "record_name": "Most Overtakes In Race",
                "record_value": float(total_overtakes),
                "team_id": None,
                "team_name": None,
                "details": f"{total_overtakes} overtakes",
                "higher_is_better": True,
            },
            {
                "track_key": track_key,
                "record_key": "chaos_score",
                "record_name": "Most Chaotic Race",
                "record_value": float(chaos),
                "team_id": None,
                "team_name": None,
                "details": f"Chaos score {chaos}",
                "higher_is_better": True,
            },
        ]
    )
    return candidates
