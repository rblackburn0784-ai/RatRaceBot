import asyncio
import logging
from pathlib import Path

import discord
from discord.ext import commands
from dotenv import load_dotenv

from config import Settings
from storage.database import Database

COGS = [
    "cogs.admin",
    "cogs.teams",
    "cogs.racing",
    "cogs.tournaments",
]

class RatRodBot(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = False
        super().__init__(command_prefix="!rr ", intents=intents)
        self.settings = settings
        self.db = Database(settings.database_path)

    async def setup_hook(self) -> None:
        await self.db.init()
        for cog in COGS:
            await self.load_extension(cog)
        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logging.info("Synced commands to guild %s", self.settings.guild_id)
        else:
            await self.tree.sync()
            logging.info("Synced global commands")

    async def close(self) -> None:
        await self.db.close()
        await super().close()

async def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    load_dotenv()
    settings = Settings.from_env()
    if not settings.discord_token:
        raise RuntimeError("DISCORD_BOT_TOKEN is missing. Copy .env.example to .env and add your bot token.")
    Path("assets/gifs").mkdir(parents=True, exist_ok=True)
    Path("assets/audio").mkdir(parents=True, exist_ok=True)
    bot = RatRodBot(settings)
    await bot.start(settings.discord_token)

if __name__ == "__main__":
    asyncio.run(main())
