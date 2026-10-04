import asyncio

import discord

from models.domain import RaceEvent
from services.dynamic_gifs import DynamicRaceGifRenderer
from services.media import MediaRegistry

class RaceStreamer:
    def __init__(self, media: MediaRegistry, tick_seconds: float = 5.0):
        self.media = media
        self.tick_seconds = tick_seconds
        self.dynamic_gifs = DynamicRaceGifRenderer()

    async def stream(self, channel: discord.abc.Messageable, events: list[RaceEvent]) -> None:
        await asyncio.to_thread(self.dynamic_gifs.cleanup_cache)
        for event in events:
            content = f"**Lap {event.lap}** — {event.message}" if event.lap else f"🏁 {event.message}"
            # Pillow work is CPU/file-system heavy; keep it off Discord's event loop.
            dynamic_gif = await asyncio.to_thread(self.dynamic_gifs.render, event)
            gif = dynamic_gif or self.media.gif_path(event.media_key)
            if gif:
                await channel.send(content=content, file=discord.File(str(gif)))
            else:
                await channel.send(content)
            await asyncio.sleep(self.tick_seconds)
