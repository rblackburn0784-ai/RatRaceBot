import asyncio
import logging
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands
from dotenv import load_dotenv

from config import Settings
from storage.database import Database
from services.race_activity import RaceActivityRegistry
from services.recovery import RecoveryManager
from services.ui_safety import safe_reply
from services.admin_selector_compat import apply_admin_selector_compat

COGS = [
    "cogs.admin",
    "cogs.teams",
    "cogs.racing",
    "cogs.tournaments",
    "cogs.world",
    "cogs.recovery",
    "cogs.menu",
]

class RatRodBot(commands.Bot):
    def __init__(self, settings: Settings):
        intents = discord.Intents.default()
        intents.message_content = False
        super().__init__(command_prefix="!rr ", intents=intents)
        self.settings = settings
        self.db = Database(settings.database_path)
        self.race_activity = RaceActivityRegistry()
        self.recovery_lock = asyncio.Lock()
        self.recovery = RecoveryManager(self.db, settings.database_path)
        self.tree.on_error = self.on_app_command_error

    async def setup_hook(self) -> None:
        await self.db.init()
        await self.recovery.init()
        for cog in COGS:
            await self.load_extension(cog)
        apply_admin_selector_compat()
        if self.settings.guild_id:
            guild = discord.Object(id=self.settings.guild_id)
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
            logging.info("Synced commands to guild %s", self.settings.guild_id)
        else:
            await self.tree.sync()
            logging.info("Synced global commands")

    async def on_app_command_error(self, interaction: discord.Interaction, error: Exception) -> None:
        if isinstance(error, app_commands.CheckFailure):
            # Cog-level permission checks often already explain the refusal. Do not
            # follow that with a second generic "command failed" message.
            if interaction.response.is_done():
                return
            await safe_reply(
                interaction,
                "You do not have permission to use that command.",
                ephemeral=True,
            )
            return

        logging.error(
            "Slash command failed: %s",
            getattr(interaction.command, "qualified_name", "unknown"),
            exc_info=(type(error), error, error.__traceback__),
        )
        await safe_reply(
            interaction,
            "That command hit an unexpected error. Reopen `/menu` or `/world`, check the current state, and try again.",
            ephemeral=True,
        )

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
