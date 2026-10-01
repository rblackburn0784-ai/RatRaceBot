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


async def process_race_rewards(db, track_key: str, race_id: int, teams: list[Team], results: list[RaceResult], events: list[RaceEvent], weather_name: str, title: str) -> list[discord.Embed]:
    teams_by_id = {team.id: team for team in teams if team.id and team.id > 0}
    saved_results = [result for result in results if result.team_id in teams_by_id]
    embeds: list[discord.Embed] = []
    new_achievements = []
    sponsor_lines = []

    await db.decay_fatigue([result.team_id for result in saved_results])

    for result in saved_results:
        team = teams_by_id[result.team_id]
        current_progress = await db.team_progress(team.id)
        current_xp = int(current_progress["xp"]) if current_progress else 0
        gained_xp = xp_for_result(result)
        new_level = level_for_xp(current_xp + gained_xp)
        title_name = cosmetic_title_for_level(new_level)
        await db.add_team_xp(team.id, gained_xp, title_name)

        profile = await db.team_profile(team.id)
        for key, name in achievement_candidates(result, profile):
            if await db.unlock_achievement(team.id, key, name):
                new_achievements.append(f"**{team.name}** unlocked **{name}**")

        if result.position <= 3 and result.team_id > 0:
            sponsor_name, benefit, drawback = sponsor_offer(team, race_id)
            await db.create_sponsor_offer(team.id, sponsor_name, benefit, drawback)
            sponsor_lines.append(f"**{team.name}** heard from **{sponsor_name}**")

        if result.damage >= 75 or result.dnf:
            await db.set_team_fatigue(
                team.id,
                "driver_shaken" if result.damage >= 75 else "crew_exhausted",
                "Driver Shaken" if result.damage >= 75 else "Crew Exhausted",
                "A rough race left this team carrying a short-term story flag.",
                races_remaining=1,
            )

    embeds.extend(await update_track_records(db, track_key, race_id, results))
    embeds.append(hype_embed(results, events, title))
    embeds.append(newspaper_embed(results, title, TRACKS[track_key].name, weather_name))

    winner = min(results, key=lambda result: result.position)
    winner_team = teams_by_id.get(winner.team_id)
    if winner_team:
        embeds.append(interview_embed(winner_team, winner, await db.team_profile(winner.team_id)))

    if new_achievements:
        embed = discord.Embed(title="New Achievements", color=discord.Color.green())
        embed.add_field(name="Unlocked", value="\n".join(new_achievements[:10]), inline=False)
        embeds.append(embed)

    if sponsor_lines:
        embed = discord.Embed(
            title="Sponsor Offers",
            description="New offers are waiting in `/sponsor_offers`.",
            color=discord.Color.dark_gold(),
        )
        embed.add_field(name="Fresh Interest", value="\n".join(sponsor_lines[:10]), inline=False)
        embeds.append(embed)

    return embeds


async def update_track_records(db, track_key: str, race_id: int, results: list[RaceResult]) -> list[discord.Embed]:
    embeds = []
    winner = min(results, key=lambda result: result.position)
    best_time = min(results, key=lambda result: result.total_time)
    total_crashes = sum(result.crashes for result in results)
    total_overtakes = sum(result.overtakes for result in results)
    chaos = total_crashes * 3 + total_overtakes + sum(result.illegal_moves for result in results) * 2
    candidates = [
        ("winner_time", "Fastest Winner", winner.total_time, winner.team_id, winner.team_name, f"{winner.total_time:.2f}s", False),
        ("best_time", "Fastest Overall Time", best_time.total_time, best_time.team_id, best_time.team_name, f"{best_time.total_time:.2f}s", False),
        ("most_crashes", "Most Crashes In Race", total_crashes, None, None, f"{total_crashes} crashes", True),
        ("most_overtakes", "Most Overtakes In Race", total_overtakes, None, None, f"{total_overtakes} overtakes", True),
        ("chaos_score", "Most Chaotic Race", chaos, None, None, f"Chaos score {chaos}", True),
    ]
    new_lines = []
    for key, name, value, team_id, team_name, details, higher in candidates:
        if await db.update_track_record(track_key, key, name, float(value), team_id, team_name, race_id, details, higher):
            holder = f" by {team_name}" if team_name else ""
            new_lines.append(f"**{name}:** {details}{holder}")
    if new_lines:
        embed = discord.Embed(title="Track Record Board", color=discord.Color.blue())
        embed.add_field(name="New Records", value="\n".join(new_lines), inline=False)
        embeds.append(embed)
    return embeds
