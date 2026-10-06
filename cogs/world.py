from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

from services.access import is_admin
from services.ui_safety import OneShotReliableView, safe_reply
from services.racing_world import (
    ensure_world_schema,
    heat_bar,
    pending_world_events,
    resolve_world_event,
    world_event_embed,
)


class WorldEventDecisionView(OneShotReliableView):
    def __init__(self, cog: "RacingWorldCog", owner_id: int, team_id: int, event_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.team_id = int(team_id)
        self.event_id = int(event_id)

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This story decision belongs to another driver.", ephemeral=True)
        return False

    async def choose(self, interaction: discord.Interaction, choice: str) -> None:
        await ensure_world_schema(self.cog.bot.db)
        row = await self.cog.bot.db.fetchone("SELECT * FROM world_events WHERE id=?", (self.event_id,))
        if not row:
            await safe_reply(interaction, "That world event no longer exists. Refresh the World Hub.")
            return
        if int(row["team_id"]) != self.team_id:
            await safe_reply(interaction, "That world event no longer belongs to this team.")
            return
        if str(row["status"]) != "pending":
            self._disable()
            await safe_reply(
                interaction,
                f"That decision was already resolved as **{row['choice'] or '?'}**. No second choice was applied.",
            )
            return
        if not self.begin_once():
            await safe_reply(interaction, "That decision is already being processed. No second choice was applied.")
            return

        event = await resolve_world_event(self.cog.bot.db, self.event_id, choice)
        self._disable()
        if not event:
            await safe_reply(interaction, "That world event disappeared before it could be resolved.")
            return
        await interaction.response.edit_message(embed=world_event_embed(event), view=self)

    @discord.ui.button(label="Choose A", style=discord.ButtonStyle.primary)
    async def choose_a(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.choose(interaction, "A")

    @discord.ui.button(label="Choose B", style=discord.ButtonStyle.primary)
    async def choose_b(self, interaction: discord.Interaction, button: discord.ui.Button):
        await self.choose(interaction, "B")


class RacingWorldCog(commands.Cog):
    """v0.4.8 public-facing rivalry stories and low-impact world decisions."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def _team_for_user(self, interaction: discord.Interaction, team_id: int | None):
        if team_id is not None and is_admin(interaction):
            return await self.bot.db.get_team(int(team_id))
        return await self.bot.db.get_team_by_owner(interaction.user.id)

    async def send_world_events(self, interaction: discord.Interaction, team) -> None:
        rows = await pending_world_events(self.bot.db, int(team.id))
        if not rows:
            await interaction.response.send_message(
                f"**{team.name}** has no pending world-event decisions.",
                ephemeral=True,
            )
            return
        row = dict(rows[0])
        embed = world_event_embed(row)
        embed.title = f"🌎 Blacktop World — {row['title']}"
        embed.set_footer(text=f"World Event #{row['id']} · {len(rows)} pending · choices are story decisions, not random stat punishment")
        await interaction.response.send_message(
            embed=embed,
            view=WorldEventDecisionView(self, interaction.user.id, int(team.id), int(row["id"])),
            ephemeral=True,
        )

    @app_commands.command(name="world_events", description="Show pending racing-world decisions for your team.")
    async def world_events(self, interaction: discord.Interaction, team_id: int | None = None):
        team = await self._team_for_user(interaction, team_id)
        if not team:
            await interaction.response.send_message(
                "No linked team found. Drivers can view their own events; admins may provide a team ID.",
                ephemeral=True,
            )
            return
        await self.send_world_events(interaction, team)

    @app_commands.command(name="world_event_choose", description="Resolve one of your pending racing-world decisions.")
    @app_commands.choices(
        choice=[
            app_commands.Choice(name="A", value="A"),
            app_commands.Choice(name="B", value="B"),
        ]
    )
    async def world_event_choose(
        self,
        interaction: discord.Interaction,
        event_id: int,
        choice: app_commands.Choice[str],
    ):
        await ensure_world_schema(self.bot.db)
        row = await self.bot.db.fetchone("SELECT * FROM world_events WHERE id=?", (int(event_id),))
        if not row:
            await interaction.response.send_message("World event not found.", ephemeral=True)
            return

        if not is_admin(interaction):
            team = await self.bot.db.get_team_by_owner(interaction.user.id)
            if not team or int(row["team_id"]) != int(team.id):
                await interaction.response.send_message("That world event belongs to another team.", ephemeral=True)
                return

        if str(row["status"]) != "pending":
            await interaction.response.send_message(
                f"That world event was already resolved as **{row['choice'] or '?'}**. No second choice was applied.",
                ephemeral=True,
            )
            return
        event = await resolve_world_event(self.bot.db, int(event_id), choice.value)
        if not event:
            await interaction.response.send_message("World event not found.", ephemeral=True)
            return
        await interaction.response.send_message(embed=world_event_embed(event), ephemeral=True)

    @app_commands.command(name="rivalry_story", description="Show a team's richer v0.4.8 rivalry history.")
    async def rivalry_story(self, interaction: discord.Interaction, team_id: int | None = None):
        team = await self._team_for_user(interaction, team_id)
        if not team:
            await interaction.response.send_message(
                "No linked team found. Drivers can view their own rivalries; admins may provide a team ID.",
                ephemeral=True,
            )
            return

        await ensure_world_schema(self.bot.db)
        rows = await self.bot.db.fetchall(
            """
            SELECT r.*, opponent.name AS opponent_name,
                   winner.name AS last_winner_name,
                   COALESCE(s.overtakes, 0) AS overtakes,
                   COALESCE(s.championship_battles, 0) AS championship_battles,
                   COALESCE(s.stolen_wins, 0) AS stolen_wins,
                   COALESCE(s.dnfs_caused, 0) AS dnfs_caused,
                   COALESCE(s.last_incident, '') AS last_incident
            FROM team_rivalries r
            JOIN teams opponent
              ON opponent.id = CASE WHEN r.team_a_id=? THEN r.team_b_id ELSE r.team_a_id END
            LEFT JOIN teams winner ON winner.id=r.last_winner_id
            LEFT JOIN rivalry_story_stats s
              ON s.team_a_id=r.team_a_id AND s.team_b_id=r.team_b_id
            WHERE r.team_a_id=? OR r.team_b_id=?
            ORDER BY r.heat DESC, r.updated_at DESC
            LIMIT 8
            """,
            (int(team.id), int(team.id), int(team.id)),
        )
        embed = discord.Embed(
            title=f"🔥 Rivalry Book — {team.name}",
            description="Heat is capped at 100. High heat changes race flavour; any gameplay nudge remains deliberately tiny.",
            color=discord.Color.dark_red(),
        )
        if not rows:
            embed.add_field(name="No grudges yet", value="Race close, trade overtakes and keep the bumpers honest.", inline=False)
        for row in rows:
            heat = min(100, int(row["heat"]))
            details = [
                f"Races {row['races']}",
                f"Overtakes {row['overtakes']}",
                f"Contacts {row['contacts']}",
                f"Illegal {row['illegal_incidents']}",
            ]
            if int(row["championship_battles"]):
                details.append(f"Title battles {row['championship_battles']}")
            if int(row["stolen_wins"]):
                details.append(f"Stolen wins {row['stolen_wins']}")
            if int(row["dnfs_caused"]):
                details.append(f"Caused DNFs {row['dnfs_caused']}")
            incident = str(row["last_incident"] or "no signature incident yet")
            last_winner = row["last_winner_name"] or "Unknown"
            embed.add_field(
                name=f"{row['opponent_name']} — Heat {heat}",
                value=(
                    f"{heat_bar(heat)} **{heat}**\n"
                    f"{' | '.join(details)}\n"
                    f"Last incident: **{incident}** | Last winner: **{last_winner}**"
                )[:1024],
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RacingWorldCog(bot))
