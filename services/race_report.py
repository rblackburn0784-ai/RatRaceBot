from __future__ import annotations

import discord

from data.defaults import TRACKS
from models.domain import RaceEvent, RaceResult, Team
from services.formatting import Embeds
from services.predictions import PredictionView
from services.race_newspaper import render_race_newspaper
from services.race_presentation import classification_embed
from services.race_rewards import process_race_rewards
from services.racing_world import build_gazette_story, rivalry_watch_embed
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
    reward_embeds_override: list[discord.Embed] | None = None,
    persisted_report: bool | None = None,
) -> None:
    result_embed = Embeds.results(results, title=title)
    final_embed = final_embed or classification_embed(results, events, title)
    recap_embed = race_recap_embed(results, title, TRACKS[track_key].name, weather_name)
    prediction_results = predictions.results_embed(results, title) if predictions else None
    if reward_embeds_override is not None:
        reward_embeds = reward_embeds_override
    else:
        reward_embeds = (
            await process_race_rewards(db, track_key, race_id, teams, results, events, weather_name, title, race_laps)
            if award_rewards
            else []
        )

    team_ids = [int(result.team_id) for result in results if int(result.team_id) > 0]
    persisted = award_rewards if persisted_report is None else bool(persisted_report)
    if persisted:
        story_embed = await rivalry_watch_embed(db, team_ids)
    else:
        story_embed = race_story_embed(rivalry_watch or [])

    gazette_story = await build_gazette_story(
        db,
        race_id=race_id,
        track_key=track_key,
        results=results,
        events=events,
        teams=teams,
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
        gazette_story=gazette_story,
    )

    # Official classification, new records and world decisions are explicit even
    # when the image Gazette renders successfully.
    await channel.send(embed=final_embed)
    explicit_titles = {"Track Record Board", "Blacktop World Event"}
    for embed in reward_embeds:
        if embed.title in explicit_titles or (embed.title and any(token in embed.title for token in ("Garage Break-In", "Sponsor Dispute", "Newspaper Hype", "Crew Argument", "Surprise Inspection", "Engine Supplier", "Weather Forecast", "Track Repairs"))):
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
        if embed.title not in explicit_titles and not (embed.title and any(token in embed.title for token in ("Garage Break-In", "Sponsor Dispute", "Newspaper Hype", "Crew Argument", "Surprise Inspection", "Engine Supplier", "Weather Forecast", "Track Repairs"))):
            await channel.send(embed=embed)
