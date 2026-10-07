from __future__ import annotations

import discord

from data.defaults import TRACKS


class _TeamSelect(discord.ui.Select):
    def __init__(self, select_view, teams, placeholder: str = "Choose a team"):
        self.select_view = select_view
        options = [
            discord.SelectOption(
                label=f"#{team.id} {team.name}"[:100],
                value=str(team.id),
                description=f"{team.driver_name} - {team.car_name}"[:100],
            )
            for team in teams[:25]
            if team.id is not None
        ]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        team = await self.select_view.cog.bot.db.get_team(int(self.values[0]))
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return
        await self.select_view.on_team(interaction, team)


class _TeamMultiSelect(discord.ui.Select):
    def __init__(self, select_view, teams):
        self.select_view = select_view
        options = [
            discord.SelectOption(
                label=f"#{team.id} {team.name}"[:100],
                value=str(team.id),
                description=f"{team.driver_name} - {team.car_name}"[:100],
            )
            for team in teams[:25]
            if team.id is not None
        ]
        super().__init__(
            placeholder="Choose race teams",
            min_values=min(2, len(options)),
            max_values=min(10, len(options)),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        await self.select_view.on_team_ids(interaction, [int(value) for value in self.values])


class _PartSelect(discord.ui.Select):
    def __init__(self, select_view, options_data: list[tuple[str, str, str]], placeholder: str):
        self.select_view = select_view
        options = [
            discord.SelectOption(label=label[:100], value=value, description=description[:100])
            for value, label, description in options_data[:25]
        ]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.select_view.on_part(interaction, self.values[0])


class _TournamentSelect(discord.ui.Select):
    def __init__(self, select_view, tournaments, placeholder: str):
        self.select_view = select_view
        options = [
            discord.SelectOption(
                label=f"#{row['id']} {row['name']}"[:100],
                value=str(row["id"]),
                description=f"Status: {row['status']}"[:100],
            )
            for row in tournaments[:25]
        ]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        tournament = await self.select_view.cog.bot.db.get_tournament(int(self.values[0]))
        if not tournament:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        await self.select_view.on_tournament(interaction, tournament)


class _TrackSelect(discord.ui.Select):
    def __init__(self, select_view, placeholder: str):
        self.select_view = select_view
        options = [
            discord.SelectOption(label=track.name, value=key, description=track.description[:100])
            for key, track in list(TRACKS.items())[:25]
        ]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.select_view.on_track(interaction, self.values[0])


def apply_admin_selector_compat() -> None:
    """Replace selectors that used discord.py's now-reserved Item.parent property."""
    import cogs.admin as admin

    admin.TeamSelect = _TeamSelect
    admin.TeamMultiSelect = _TeamMultiSelect
    admin.PartSelect = _PartSelect
    admin.TournamentSelect = _TournamentSelect
    admin.TrackSelect = _TrackSelect
