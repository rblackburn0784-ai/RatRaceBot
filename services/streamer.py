import asyncio
from collections.abc import Awaitable, Callable

import discord

from models.domain import RaceEvent
from models.enums import EventType
from services.dynamic_gifs import DynamicRaceGifRenderer
from services.media import MediaRegistry
from services.race_presentation import event_explanation, leaderboard_embed, phase_embed
from services.race_presentation_core import leaderboard_checkpoints, phase_for_lap


class RaceStreamer:
    def __init__(self, media: MediaRegistry, tick_seconds: float = 5.0):
        self.media = media
        self.tick_seconds = tick_seconds
        self.dynamic_gifs = DynamicRaceGifRenderer()

    async def stream(
        self,
        channel: discord.abc.Messageable,
        events: list[RaceEvent],
        *,
        start_index: int = 0,
        progress_callback: Callable[[int], Awaitable[None]] | None = None,
    ) -> None:
        await asyncio.to_thread(self.dynamic_gifs.cleanup_cache)
        total_laps = max((int((getattr(event, "context", {}) or {}).get("laps", event.lap)) for event in events), default=0)
        total_laps = max(total_laps, max((event.lap for event in events), default=0))
        checkpoints = leaderboard_checkpoints(total_laps) if total_laps else set()
        last_phase: str | None = None
        leaderboard_posted: set[int] = set()

        for event_index, event in enumerate(events):
            if event_index < max(0, int(start_index)):
                continue
            if event.lap > 0 and total_laps:
                phase = phase_for_lap(event.lap, total_laps)
                if phase != last_phase:
                    await channel.send(embed=phase_embed(event.lap, total_laps))
                    last_phase = phase

            content = f"**Lap {event.lap}** — {event.message}" if event.lap else f"🏁 {event.message}"
            explanation = event_explanation(event)
            if explanation and event.event_type not in {EventType.LAP, EventType.PODIUM}:
                content += f"\n*Why:* {explanation}"
            context = getattr(event, "context", {}) or {}
            if event.event_type == EventType.PIT_STOP and context.get("pit_position_text"):
                content += (
                    f"\n*Pit cycle:* {context['pit_position_text']}; "
                    f"stop cost ~{float(context.get('time_cost', 0.0)):.1f}s."
                )

            # Pillow work is CPU/file-system heavy; keep it off Discord's event loop.
            dynamic_gif = await asyncio.to_thread(self.dynamic_gifs.render, event)
            gif = dynamic_gif or self.media.gif_path(event.media_key)
            if gif:
                await channel.send(content=content, file=discord.File(str(gif)))
            else:
                await channel.send(content)

            if (
                event.event_type == EventType.LAP
                and event.lap in checkpoints
                and event.lap not in leaderboard_posted
                and total_laps
            ):
                board = leaderboard_embed(context, event.lap, total_laps)
                if board:
                    await channel.send(embed=board)
                    leaderboard_posted.add(event.lap)

            if progress_callback:
                await progress_callback(event_index)
            await asyncio.sleep(self.tick_seconds)
