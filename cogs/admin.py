import discord
from discord import app_commands
from discord.ext import commands

from services.formatting import Embeds
from services.media import MediaRegistry

class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.media = MediaRegistry()

    @app_commands.command(name="ratbot_init", description="Initialise the Rat Rod Racing database.")
    async def ratbot_init(self, interaction: discord.Interaction):
        await self.bot.db.init()
        await interaction.response.send_message("Database checked and ready. The rods are coughing smoke in the alley.", ephemeral=True)

    @app_commands.command(name="media_list", description="Show configured GIF/audio media keys.")
    async def media_list(self, interaction: discord.Interaction):
        self.media.load()
        await interaction.response.send_message(f"```{self.media.keys_text()}```", ephemeral=True)

    @app_commands.command(name="parts_catalogue", description="List available rod parts and modifiers.")
    async def parts_catalogue(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=Embeds.parts_list(), ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
