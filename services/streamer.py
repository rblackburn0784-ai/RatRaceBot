import asyncio

import discord

from models.domain import RaceEvent
from services.media import MediaRegistry

class RaceStreamer:
    def __init__(self, media: MediaRegistry, tick_seconds: float = 5.0):
        self.media = media
        self.tick_seconds = tick_seconds

    async def stream(self, channel: discord.abc.Messageable, events: list[RaceEvent]) -> None:
        for event in events:
            content = f"**Lap {event.lap}** — {event.message}" if event.lap else f"🏁 {event.message}"
            gif = self.media.gif_path(event.media_key)
            if gif:
                await channel.send(content=content, file=discord.File(str(gif)))
            else:
                await channel.send(content)
            await asyncio.sleep(self.tick_seconds)
