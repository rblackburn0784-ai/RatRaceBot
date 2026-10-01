from __future__ import annotations

import discord

from data.defaults import TRACKS
from models.domain import RaceEvent, RaceResult, Team
from services.formatting import Embeds
from services.predictions import PredictionView
from services.race_newspaper import render_race_newspaper
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
    predictions: PredictionView | None = None,
    rivalry_watch=None,
    final_embed: discord.Embed | None = None,
    award_rewards: bool = True,
) -> None:
    result_embed = Embeds.results(results, title=title)
    recap_embed = race_recap_embed(results, title, TRACKS[track_key].name, weather_name)
    prediction_results = predictions.results_embed(results, title) if predictions else None
    story_embed = race_story_embed(rivalry_watch or [])
    reward_embeds = (
        await process_race_rewards(db, track_key, race_id, teams, results, events, weather_name, title)
        if award_rewards
        else []
    )

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
    if newspaper:
        await channel.send(
            content="Blacktop Gazette race report:",
            file=discord.File(newspaper, filename=f"blacktop_gazette_race_{race_id}.png"),
        )
        return

    await channel.send(embed=result_embed)
    await channel.send(embed=recap_embed)
    if final_embed:
        await channel.send(embed=final_embed)
    if prediction_results:
        await channel.send(embed=prediction_results)
    if story_embed:
        await channel.send(embed=story_embed)
    for embed in reward_embeds:
        await channel.send(embed=embed)
