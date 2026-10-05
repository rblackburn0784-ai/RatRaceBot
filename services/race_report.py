from __future__ import annotations

import discord

from data.defaults import TRACKS
from models.domain import RaceEvent, RaceResult, Team
from services.formatting import Embeds
from services.predictions import PredictionView
from services.race_newspaper import render_race_newspaper
from services.race_presentation import classification_embed
from services.race_rewards import process_race_rewards
from services.story import race_recap_embed, race_story_embed


async def send_race_report(
    *,
    channel: discord.abc.Messageable,
    db,
    track_key: str,
    race_id: int,
    teams: list[Team],
    results: list[RaceResult],
    events: list[RaceEvent],
    weather_name: str,
    title: str,
    race_laps: int,
    predictions: PredictionView | None = None,
    rivalry_watch=None,
    final_embed: discord.Embed | None = None,
    award_rewards: bool = True,
) -> None:
    result_embed = Embeds.results(results, title=title)
    final_embed = final_embed or classification_embed(results, events, title)
    recap_embed = race_recap_embed(results, title, TRACKS[track_key].name, weather_name)
    prediction_results = predictions.results_embed(results, title) if predictions else None
    reward_embeds = (
        await process_race_rewards(db, track_key, race_id, teams, results, events, weather_name, title, race_laps)
        if award_rewards
        else []
    )
    if rivalry_watch is None and award_rewards:
        rivalry_watch = await db.race_rivalry_watch([
            {
                "team_id": result.team_id, "position": result.position, "total_time": result.total_time,
                "crashes": result.crashes, "illegal_moves": result.illegal_moves,
                "disqualified": result.disqualified, "dnf": result.dnf,
            }
            for result in results
        ])
    story_embed = race_story_embed(rivalry_watch or [])

    newspaper = render_race_newspaper(
        results=results,
        events=events,
        title=title,
        track_name=TRACKS[track_key].name,
        weather_name=weather_name,
        prediction_embed=prediction_results,
        rivalry_embed=story_embed,
        reward_embeds=reward_embeds,
    )
    # v0.4.4: the official classification is always posted, even when the
    # newspaper renderer succeeds. Track-record notifications are also explicit
    # rather than being hidden inside the Gazette image.
    await channel.send(embed=final_embed)
    for embed in reward_embeds:
        if embed.title == "Track Record Board":
            await channel.send(embed=embed)

    if newspaper:
        await channel.send(
            content="Blacktop Gazette race report:",
            file=discord.File(newspaper, filename=f"blacktop_gazette_race_{race_id}.png"),
        )
        return

    await channel.send(embed=result_embed)
    await channel.send(embed=recap_embed)
    if prediction_results:
        await channel.send(embed=prediction_results)
    if story_embed:
        await channel.send(embed=story_embed)
    for embed in reward_embeds:
        if embed.title != "Track Record Board":
            await channel.send(embed=embed)
