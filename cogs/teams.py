import discord
from discord import app_commands
from discord.ext import commands

from data.defaults import PARTS
from models.domain import Team
from models.enums import CarArchetype
from models.stats import DriverStats
from services.formatting import Embeds


STAT_CHOICES = [app_commands.Choice(name=str(i), value=i) for i in range(1, 9)]


class TeamsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ----------------------------
    # AUTOCOMPLETE HELPERS
    # ----------------------------

    async def team_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[int]]:
        """Autocomplete teams as: #1 Team Name — Driver — Car."""
        teams = await self.bot.db.list_teams()
        current_lower = str(current).lower()

        choices: list[app_commands.Choice[int]] = []
        for team in teams:
            label = f"#{team.id} {team.name} — {team.driver_name} — {team.car_name}"
            searchable = f"{team.id} {team.name} {team.driver_name} {team.car_name}".lower()
            if not current_lower or current_lower in searchable:
                choices.append(app_commands.Choice(name=label[:100], value=int(team.id)))

        return choices[:25]

    async def add_part_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete parts, hiding parts blocked by an already-filled slot when team_id is known."""
        current_lower = str(current).lower()
        team_id = getattr(interaction.namespace, "team_id", None)
        team = None

        if isinstance(team_id, int):
            team = await self.bot.db.get_team(team_id)

        choices: list[app_commands.Choice[str]] = []
        for key, part in PARTS.items():
            if team:
                # Hide already fitted parts.
                if key in team.parts:
                    continue
                # Hide parts from slots already occupied by another fitted part.
                occupied_slots = {
                    PARTS[p].slot
                    for p in team.parts
                    if p in PARTS
                }
                if part.slot in occupied_slots:
                    continue

            label = f"{part.name} [{part.slot.value}] — {key}"
            searchable = f"{key} {part.name} {part.slot.value} {part.description}".lower()
            if not current_lower or current_lower in searchable:
                choices.append(app_commands.Choice(name=label[:100], value=key))

        return choices[:25]

    async def remove_part_autocomplete(
        self,
        interaction: discord.Interaction,
        current: str,
    ) -> list[app_commands.Choice[str]]:
        """Autocomplete only the parts currently fitted to the selected team."""
        current_lower = str(current).lower()
        team_id = getattr(interaction.namespace, "team_id", None)

        if not isinstance(team_id, int):
            return []

        team = await self.bot.db.get_team(team_id)
        if not team:
            return []

        choices: list[app_commands.Choice[str]] = []
        for key in team.parts:
            part = PARTS.get(key)
            if not part:
                continue
            label = f"{part.name} [{part.slot.value}] — {key}"
            searchable = f"{key} {part.name} {part.slot.value} {part.description}".lower()
            if not current_lower or current_lower in searchable:
                choices.append(app_commands.Choice(name=label[:100], value=key))

        return choices[:25]

    # ----------------------------
    # TEAM COMMANDS
    # ----------------------------

    @app_commands.command(name="team_create", description="Create a rat rod racing team.")
    @app_commands.describe(
        name="Team name",
        driver="Driver name",
        pit_crew="Pit crew name",
        car_name="Rod name",
        car_type="Car archetype",
        nerve="1-8",
        handling="1-8",
        aggression="1-8",
        mechanics="1-8",
        reflexes="1-8",
        showmanship="1-8",
    )
    @app_commands.choices(
        nerve=STAT_CHOICES,
        handling=STAT_CHOICES,
        aggression=STAT_CHOICES,
        mechanics=STAT_CHOICES,
        reflexes=STAT_CHOICES,
        showmanship=STAT_CHOICES,
    )
    async def team_create(
        self,
        interaction: discord.Interaction,
        name: str,
        driver: str,
        pit_crew: str,
        car_name: str,
        car_type: CarArchetype,
        nerve: int,
        handling: int,
        aggression: int,
        mechanics: int,
        reflexes: int,
        showmanship: int,
    ):
        try:
            stats = DriverStats(nerve, handling, aggression, mechanics, reflexes, showmanship)
            stats.validate()
            team = Team(None, name, driver, pit_crew, car_name, car_type, stats, [])
            team_id = await self.bot.db.create_team(team)
            team.id = team_id
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return

        await interaction.response.send_message(
            f"✅ Created team **{name}** as ID `{team_id}`.",
            embed=Embeds.team_sheet(team),
        )

    @app_commands.command(name="team_list", description="List all racing teams.")
    async def team_list(self, interaction: discord.Interaction):
        teams = await self.bot.db.list_teams()
        if not teams:
            await interaction.response.send_message("No teams yet. Use `/team_create`.", ephemeral=True)
            return

        text = "\n".join(f"`{t.id}` **{t.name}** — {t.driver_name} — {t.car_name}" for t in teams)
        await interaction.response.send_message(text[:1900])

    @app_commands.command(name="team_sheet", description="Show a full team sheet.")
    @app_commands.autocomplete(team_id=team_autocomplete)
    async def team_sheet(self, interaction: discord.Interaction, team_id: int):
        team = await self.bot.db.get_team(team_id)
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return

        await interaction.response.send_message(embed=Embeds.team_sheet(team))

    @app_commands.command(name="team_add_part", description="Fit a custom part to a team rod.")
    @app_commands.autocomplete(team_id=team_autocomplete, part_key=add_part_autocomplete)
    async def team_add_part(self, interaction: discord.Interaction, team_id: int, part_key: str):
        team = await self.bot.db.get_team(team_id)
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return

        if part_key not in PARTS:
            await interaction.response.send_message("Unknown part. Use `/parts_catalogue`.", ephemeral=True)
            return

        new_part = PARTS[part_key]
        existing_same_slot = [p for p in team.parts if PARTS.get(p) and PARTS[p].slot == new_part.slot]
        if existing_same_slot:
            await interaction.response.send_message(
                f"That rod already has a `{new_part.slot.value}` part fitted. Remove it first.",
                ephemeral=True,
            )
            return

        team.parts.append(part_key)
        await self.bot.db.update_team_parts(team_id, team.parts)
        await interaction.response.send_message(
            f"✅ Fitted **{new_part.name}** to **{team.name}**.",
            embed=Embeds.team_sheet(team),
        )

    @app_commands.command(name="team_remove_part", description="Remove a custom part from a team rod.")
    @app_commands.autocomplete(team_id=team_autocomplete, part_key=remove_part_autocomplete)
    async def team_remove_part(self, interaction: discord.Interaction, team_id: int, part_key: str):
        team = await self.bot.db.get_team(team_id)
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return

        if part_key not in team.parts:
            await interaction.response.send_message("That team does not have that part fitted.", ephemeral=True)
            return

        team.parts.remove(part_key)
        await self.bot.db.update_team_parts(team_id, team.parts)
        await interaction.response.send_message(
            f"Removed `{part_key}` from **{team.name}**.",
            embed=Embeds.team_sheet(team),
        )


async def setup(bot: commands.Bot):
    await bot.add_cog(TeamsCog(bot))
