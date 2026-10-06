import json
import sqlite3
import shutil
from datetime import datetime, timezone
from pathlib import Path

import discord
from discord import app_commands
from discord.ext import commands

from cogs.racing import TRACK_CHOICES, single_race_final_embed
from cogs.teams import TeamWizardView
from cogs.tournaments import TournamentWizardView, tournament_stats_embed
from data.defaults import PARTS, TRACKS
from models.enums import PartSlot
from services.audit import audit_log
from services.access import deny_admin_only, is_admin
from services.ai_teams import ai_teams
from services.builds import BuildService
from services.championship import calendar_entries, calendar_text, team_form
from services.formatting import Embeds
from services.menu_cards import ADMIN_PANEL_BACKGROUND, render_admin_panel_card
from services.media import MediaRegistry
from services.preflight import race_preflight_embed
from services.race_engine import RaceEngine
from services.race_report import send_race_report
from services.scrutineering import scrutineering_embed
from services.story import season_history_lines
from services.streamer import RaceStreamer
from services.team_ids import parse_team_ids_csv
from services.team_sheet import render_team_sheet
from services.views import ConfirmView, PaginatedTextView
from services.ui_safety import ReliableView

ADMIN_BACKGROUND = ADMIN_PANEL_BACKGROUND

STAT_LABELS = {
    "speed": "Spd",
    "acceleration": "Acc",
    "handling": "Hnd",
    "durability": "Dur",
    "braking": "Brk",
    "heat": "Heat",
    "intimidation": "Int",
    "reliability": "Rel",
    "pit_friendliness": "Pit",
}


def parts_catalogue_lines() -> list[str]:
    lines = ["Illegal parts are marked and add +6% disqualification risk per race."]
    for slot in PartSlot:
        lines.append(f"**{slot.value.title()} Parts**")
        for key, part in PARTS.items():
            if part.slot != slot:
                continue
            mods = " ".join(
                f"{STAT_LABELS.get(stat, stat.title())}{value:+d}"
                for stat, value in part.modifiers.as_dict().items()
                if value
            )
            marker = " [ILLEGAL +6% DSQ]" if BuildService.is_illegal_part_key(key) else ""
            lines.append(f"`{key}` - {part.name}{marker}: {mods or 'No modifiers'}")
    return lines


def admin_panel_embed(include_image: bool = True) -> discord.Embed:
    embed = discord.Embed(
        title="Rat Race Admin Panel",
        description="Private command hub for running teams, races, tournaments, and bot setup.",
        color=discord.Color.dark_gold(),
    )
    if include_image:
        embed.set_image(url="attachment://admin_panel_background.png")
    return embed


def admin_panel_file() -> discord.File | None:
    rendered_panel = render_admin_panel_card()
    if rendered_panel:
        return discord.File(rendered_panel, filename="admin_panel_background.png")
    if not ADMIN_BACKGROUND.exists():
        return None
    return discord.File(ADMIN_BACKGROUND, filename="admin_panel_background.png")


class AdminActionButton(discord.ui.Button):
    def __init__(self, key: str, label: str, row: int, style: discord.ButtonStyle = discord.ButtonStyle.secondary):
        super().__init__(label=label, row=row, style=style)
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, AdminPanelView):
            await interaction.response.send_message("Admin panel expired. Use `/admin_panel` again.", ephemeral=True)
            return
        await view.handle_action(interaction, self.key)


class TournamentNameModal(discord.ui.Modal):
    def __init__(self, view: "AdminPanelView"):
        super().__init__(title="Create Tournament")
        self.view_ref = view
        self.name_input = discord.ui.TextInput(label="Tournament name", max_length=80)
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        name = str(self.name_input.value).strip()
        if not name:
            await interaction.response.send_message("The tournament needs a name.", ephemeral=True)
            return
        try:
            tournament_id = await self.view_ref.cog.bot.db.create_tournament(name)
        except Exception as exc:
            await interaction.response.send_message(f"Tournament not created: {exc}", ephemeral=True)
            return
        await interaction.response.send_message(
            f"Created tournament **{name}** as ID `{tournament_id}`. Use Tournament Add Team or Tournament Wizard next.",
            ephemeral=True,
        )
        await audit_log(self.view_ref.cog.bot, "Tournament Created", f"#{tournament_id} {name}", interaction.user)


class RangeModal(discord.ui.Modal):
    def __init__(self, view: "AdminPanelView"):
        super().__init__(title="Personalize Saved AI")
        self.view_ref = view
        self.start_id = discord.ui.TextInput(label="Start team ID", default="2", max_length=8)
        self.end_id = discord.ui.TextInput(label="End team ID", default="11", max_length=8)
        self.add_item(self.start_id)
        self.add_item(self.end_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            start_id = int(str(self.start_id.value).strip())
            end_id = int(str(self.end_id.value).strip())
        except ValueError:
            await interaction.response.send_message("Use numeric team IDs.", ephemeral=True)
            return
        await self.view_ref.personalize_ai_range(interaction, start_id, end_id)


class RaceReplayModal(discord.ui.Modal):
    def __init__(self, view: "AdminPanelView"):
        super().__init__(title="Replay Race")
        self.view_ref = view
        self.race_id = discord.ui.TextInput(label="Race ID", max_length=8)
        self.add_item(self.race_id)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            race_id = int(str(self.race_id.value).strip())
        except ValueError:
            await interaction.response.send_message("Use a numeric race ID.", ephemeral=True)
            return
        await self.view_ref.replay_race_id(interaction, race_id)


class TeamSelect(discord.ui.Select):
    def __init__(self, parent: "TeamSelectView", teams, placeholder: str = "Choose a team"):
        self.parent = parent
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
        team = await self.parent.cog.bot.db.get_team(int(self.values[0]))
        if not team:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return
        await self.parent.on_team(interaction, team)


class TeamSelectView(ReliableView):
    def __init__(self, cog: "AdminCog", owner_id: int, teams, on_team, placeholder: str = "Choose a team"):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.on_team = on_team
        self.add_item(TeamSelect(self, teams, placeholder))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id and is_admin(interaction):
            return True
        await interaction.response.send_message("This selector belongs to another admin.", ephemeral=True)
        return False


class TeamMultiSelect(discord.ui.Select):
    def __init__(self, parent: "TeamMultiSelectView", teams):
        self.parent = parent
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
        await self.parent.on_team_ids(interaction, [int(value) for value in self.values])


class TeamMultiSelectView(ReliableView):
    def __init__(self, cog: "AdminCog", owner_id: int, teams, on_team_ids):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.on_team_ids = on_team_ids
        self.add_item(TeamMultiSelect(self, teams))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id and is_admin(interaction):
            return True
        await interaction.response.send_message("This selector belongs to another admin.", ephemeral=True)
        return False


class PartSelect(discord.ui.Select):
    def __init__(self, parent: "PartSelectView", options_data: list[tuple[str, str, str]], placeholder: str):
        self.parent = parent
        options = [
            discord.SelectOption(label=label[:100], value=value, description=description[:100])
            for value, label, description in options_data[:25]
        ]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.parent.on_part(interaction, self.values[0])


class PartSelectView(ReliableView):
    def __init__(self, owner_id: int, team, options_data: list[tuple[str, str, str]], on_part, placeholder: str):
        super().__init__(timeout=180)
        self.owner_id = owner_id
        self.team = team
        self.on_part = on_part
        self.add_item(PartSelect(self, options_data, placeholder))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id and is_admin(interaction):
            return True
        await interaction.response.send_message("This selector belongs to another admin.", ephemeral=True)
        return False


class TournamentSelect(discord.ui.Select):
    def __init__(self, parent: "TournamentSelectView", tournaments, placeholder: str):
        self.parent = parent
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
        tournament = await self.parent.cog.bot.db.get_tournament(int(self.values[0]))
        if not tournament:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        await self.parent.on_tournament(interaction, tournament)


class TournamentSelectView(ReliableView):
    def __init__(self, cog: "AdminCog", owner_id: int, tournaments, on_tournament, placeholder: str):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.on_tournament = on_tournament
        self.add_item(TournamentSelect(self, tournaments, placeholder))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id and is_admin(interaction):
            return True
        await interaction.response.send_message("This selector belongs to another admin.", ephemeral=True)
        return False


class TrackSelect(discord.ui.Select):
    def __init__(self, parent: "TrackSelectView", placeholder: str):
        self.parent = parent
        options = [
            discord.SelectOption(label=track.name, value=key, description=track.description[:100])
            for key, track in list(TRACKS.items())[:25]
        ]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.parent.on_track(interaction, self.values[0])


class TrackSelectView(ReliableView):
    def __init__(self, cog: "AdminCog", owner_id: int, on_track, placeholder: str = "Choose a track"):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.on_track = on_track
        self.add_item(TrackSelect(self, placeholder))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id and is_admin(interaction):
            return True
        await interaction.response.send_message("This selector belongs to another admin.", ephemeral=True)
        return False


class AdminPanelView(ReliableView):
    def __init__(self, cog: "AdminCog", owner_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        buttons = [
            ("ratbot_init", "Ratbot Init", 0, discord.ButtonStyle.danger),
            ("media_list", "Media List", 0, discord.ButtonStyle.secondary),
            ("parts_catalogue", "Parts Catalogue", 0, discord.ButtonStyle.secondary),
            ("ai_personalize_saved", "Personalize AI", 0, discord.ButtonStyle.secondary),
            ("team_list", "Team List", 0, discord.ButtonStyle.primary),
            ("team_create", "Team Create", 1, discord.ButtonStyle.success),
            ("team_sheet", "Team Sheet", 1, discord.ButtonStyle.secondary),
            ("team_delete", "Team Delete", 1, discord.ButtonStyle.danger),
            ("team_add_part", "Team Add Part", 1, discord.ButtonStyle.secondary),
            ("team_remove_part", "Team Remove Part", 1, discord.ButtonStyle.secondary),
            ("tournament_wizard", "Tournament Wizard", 2, discord.ButtonStyle.success),
            ("tournament_create", "Tournament Create", 2, discord.ButtonStyle.primary),
            ("tournament_add_team", "Tournament Add Team", 2, discord.ButtonStyle.secondary),
            ("tournament_standings", "Standings", 2, discord.ButtonStyle.secondary),
            ("tournament_stats", "Tournament Stats", 2, discord.ButtonStyle.secondary),
            ("season_history", "Season History", 3, discord.ButtonStyle.secondary),
            ("tournament_start_race", "Start Race", 3, discord.ButtonStyle.danger),
            ("tournament_next_race", "Next Race", 3, discord.ButtonStyle.danger),
            ("tournament_schedule", "Schedule", 3, discord.ButtonStyle.secondary),
            ("tournament_close", "Close Tournament", 3, discord.ButtonStyle.danger),
            ("race_quick", "Race Quick", 4, discord.ButtonStyle.danger),
            ("race_demo", "Race Demo", 4, discord.ButtonStyle.danger),
            ("race_replay", "Race Replay", 4, discord.ButtonStyle.danger),
            ("backup_database", "Backup DB", 4, discord.ButtonStyle.primary),
            ("admin_health", "Health", 4, discord.ButtonStyle.success),
        ]
        for key, label, row, style in buttons:
            self.add_item(AdminActionButton(key, label, row, style))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id and is_admin(interaction):
            return True
        await interaction.response.send_message("This admin panel belongs to another admin.", ephemeral=True)
        return False

    async def handle_action(self, interaction: discord.Interaction, key: str) -> None:
        handler = getattr(self, f"_handle_{key}", None)
        if handler:
            await handler(interaction)
            return
        await interaction.response.send_message("That admin action is not wired yet.", ephemeral=True)

    def _teams_cog(self):
        return self.cog.bot.get_cog("TeamsCog")

    def _tournaments_cog(self):
        return self.cog.bot.get_cog("TournamentsCog")

    def _racing_cog(self):
        return self.cog.bot.get_cog("RacingCog")

    async def _current_tournament(self):
        return await self.cog.bot.db.current_tournament()

    async def _send_shortcut(self, interaction: discord.Interaction, title: str, commands_text: str) -> None:
        embed = discord.Embed(title=title, description=commands_text, color=discord.Color.dark_gold())
        await interaction.response.send_message(embed=embed, ephemeral=True)

    async def _choose_team(self, interaction: discord.Interaction, title: str, on_team, placeholder: str = "Choose a team") -> None:
        teams = await self.cog.bot.db.list_teams()
        if not teams:
            await interaction.response.send_message("No teams found.", ephemeral=True)
            return
        await interaction.response.send_message(
            title,
            view=TeamSelectView(self.cog, interaction.user.id, teams, on_team, placeholder),
            ephemeral=True,
        )

    async def _choose_tournament(
        self,
        interaction: discord.Interaction,
        title: str,
        on_tournament,
        *,
        include_closed: bool = True,
        placeholder: str = "Choose a tournament",
    ) -> None:
        tournaments = await self.cog.bot.db.list_tournaments(include_closed=include_closed)
        if not tournaments:
            await interaction.response.send_message("No tournaments found.", ephemeral=True)
            return
        await interaction.response.send_message(
            title,
            view=TournamentSelectView(self.cog, interaction.user.id, tournaments, on_tournament, placeholder),
            ephemeral=True,
        )

    async def _handle_ratbot_init(self, interaction: discord.Interaction) -> None:
        await self.cog.bot.db.init()
        await interaction.response.send_message("Database checked and ready.", ephemeral=True)

    async def _handle_media_list(self, interaction: discord.Interaction) -> None:
        self.cog.media.load()
        await interaction.response.send_message(f"```{self.cog.media.keys_text()}```", ephemeral=True)

    async def _handle_parts_catalogue(self, interaction: discord.Interaction) -> None:
        view = PaginatedTextView(interaction.user.id, "Parts Catalogue", parts_catalogue_lines(), per_page=12)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def _handle_ai_personalize_saved(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RangeModal(self))

    async def personalize_ai_range(self, interaction: discord.Interaction, start_id: int, end_id: int) -> None:
        await interaction.response.defer(ephemeral=True)
        if start_id > end_id:
            start_id, end_id = end_id, start_id

        count = min(25, end_id - start_id + 1)
        generated = ai_teams(count, f"saved-ai-upgrade-{start_id}-{end_id}")
        updated = []
        for team_id, ai_team in zip(range(start_id, start_id + count), generated):
            existing = await self.cog.bot.db.get_team(team_id)
            if not existing:
                continue
            existing.pit_crew_name = ai_team.pit_crew_name
            existing.archetype = ai_team.archetype
            existing.stats = ai_team.stats
            existing.parts = ai_team.parts
            existing.crew = ai_team.crew
            await self.cog.bot.db.update_team_profile(existing)
            await self.cog.bot.db.update_team_parts(team_id, existing.parts)
            await self.cog.bot.db.update_team_crew(team_id, existing.crew)
            updated.append(f"`#{team_id}` **{existing.name}** - {existing.pit_crew_name}")

        if not updated:
            await interaction.followup.send("No teams found in that ID range.", ephemeral=True)
            return
        await audit_log(self.cog.bot, "AI Teams Personalized", f"Range {start_id}-{end_id}", interaction.user)
        await interaction.followup.send("Personalized saved AI/demo teams:\n" + "\n".join(updated[:20]), ephemeral=True)

    async def _handle_team_list(self, interaction: discord.Interaction) -> None:
        teams = await self.cog.bot.db.list_teams()
        if not teams:
            await interaction.response.send_message("No teams yet.", ephemeral=True)
            return
        lines = [f"`{team.id}` **{team.name}** - {team.driver_name} - {team.car_name}" for team in teams]
        view = PaginatedTextView(interaction.user.id, "Team List", lines, per_page=12)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def _handle_team_create(self, interaction: discord.Interaction) -> None:
        teams_cog = self._teams_cog()
        if not teams_cog:
            await interaction.response.send_message("Team tools are not loaded.", ephemeral=True)
            return
        view = TeamWizardView(teams_cog, interaction.user.id)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def _handle_team_sheet(self, interaction: discord.Interaction) -> None:
        async def send_sheet(select_interaction: discord.Interaction, team):
            sheet = render_team_sheet(team)
            if not sheet:
                await select_interaction.response.send_message(embed=Embeds.team_sheet(team), ephemeral=True)
                return
            file = discord.File(sheet, filename="team_sheet.png")
            embed = discord.Embed(title=f"#{team.id} {team.name} Team Card")
            embed.set_image(url="attachment://team_sheet.png")
            await select_interaction.response.send_message(embed=embed, file=file, ephemeral=True)

        await self._choose_team(interaction, "Choose a team sheet to view.", send_sheet)

    async def _handle_team_delete(self, interaction: discord.Interaction) -> None:
        async def ask_delete(select_interaction: discord.Interaction, team):
            if team.id is not None and await self.cog.bot.db.team_in_open_tournament(team.id):
                await select_interaction.response.send_message(
                    "That team is in an open tournament. Close the tournament before deleting it.",
                    ephemeral=True,
                )
                return

            async def delete_team(confirm_interaction: discord.Interaction):
                await self.cog.bot.db.delete_team(int(team.id))
                await audit_log(self.cog.bot, "Team Deleted", f"#{team.id} {team.name}", confirm_interaction.user)
                await confirm_interaction.response.edit_message(
                    content=f"Deleted team **{team.name}** (`{team.id}`).",
                    embed=None,
                    view=None,
                )

            embed = discord.Embed(
                title="Confirm Team Delete",
                description=f"Delete **#{team.id} {team.name}**? This cannot be undone.",
                color=discord.Color.red(),
            )
            await select_interaction.response.send_message(
                embed=embed,
                view=ConfirmView(select_interaction.user.id, "Delete Team", delete_team),
                ephemeral=True,
            )

        await self._choose_team(interaction, "Choose a team to delete.", ask_delete)

    async def _handle_team_add_part(self, interaction: discord.Interaction) -> None:
        async def choose_part(select_interaction: discord.Interaction, team):
            occupied_slots = {PARTS[key].slot for key in team.parts if key in PARTS}
            options_data = [
                (key, f"{part.name} [{part.slot.value}]", part.description)
                for key, part in PARTS.items()
                if key not in team.parts and part.slot not in occupied_slots
            ]
            if not options_data:
                await select_interaction.response.send_message("That team has no open part slots.", ephemeral=True)
                return

            async def add_part(part_interaction: discord.Interaction, part_key: str):
                part = PARTS[part_key]
                team.parts.append(part_key)
                await self.cog.bot.db.update_team_parts(int(team.id), team.parts)
                await audit_log(
                    self.cog.bot,
                    "Part Added",
                    f"#{team.id} {team.name}: {part.name}",
                    part_interaction.user,
                )
                await part_interaction.response.send_message(f"Fitted **{part.name}** to **{team.name}**.", ephemeral=True)

            await select_interaction.response.send_message(
                f"Choose a part for **{team.name}**.",
                view=PartSelectView(select_interaction.user.id, team, options_data, add_part, "Choose a part to fit"),
                ephemeral=True,
            )

        await self._choose_team(interaction, "Choose a team to fit a part.", choose_part)

    async def _handle_team_remove_part(self, interaction: discord.Interaction) -> None:
        async def choose_part(select_interaction: discord.Interaction, team):
            options_data = [
                (key, PARTS[key].name, PARTS[key].description)
                for key in team.parts
                if key in PARTS
            ]
            if not options_data:
                await select_interaction.response.send_message("That team has no fitted parts.", ephemeral=True)
                return

            async def remove_part(part_interaction: discord.Interaction, part_key: str):
                part = PARTS[part_key]
                team.parts.remove(part_key)
                await self.cog.bot.db.update_team_parts(int(team.id), team.parts)
                await audit_log(
                    self.cog.bot,
                    "Part Removed",
                    f"#{team.id} {team.name}: {part.name}",
                    part_interaction.user,
                )
                await part_interaction.response.send_message(f"Removed **{part.name}** from **{team.name}**.", ephemeral=True)

            await select_interaction.response.send_message(
                f"Choose a part to remove from **{team.name}**.",
                view=PartSelectView(select_interaction.user.id, team, options_data, remove_part, "Choose a part to remove"),
                ephemeral=True,
            )

        await self._choose_team(interaction, "Choose a team to remove a part.", choose_part)

    async def _handle_tournament_wizard(self, interaction: discord.Interaction) -> None:
        tournaments_cog = self._tournaments_cog()
        if not tournaments_cog:
            await interaction.response.send_message("Tournament tools are not loaded.", ephemeral=True)
            return
        teams = await self.cog.bot.db.list_teams()
        if len(teams) < 10:
            await interaction.response.send_message("Create at least 10 race teams before starting a tournament wizard.", ephemeral=True)
            return
        try:
            view = TournamentWizardView(tournaments_cog, interaction.user.id, teams)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def _handle_tournament_create(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TournamentNameModal(self))

    async def _handle_tournament_add_team(self, interaction: discord.Interaction) -> None:
        async def choose_team(tournament_interaction: discord.Interaction, tournament):
            teams = await self.cog.bot.db.list_teams()
            if not teams:
                await tournament_interaction.response.send_message("No teams found.", ephemeral=True)
                return

            async def add_team(team_interaction: discord.Interaction, team):
                await self.cog.bot.db.add_team_to_tournament(int(tournament["id"]), int(team.id))
                await audit_log(
                    self.cog.bot,
                    "Tournament Team Added",
                    f"Tournament #{tournament['id']} {tournament['name']}: #{team.id} {team.name}",
                    team_interaction.user,
                )
                await team_interaction.response.send_message(
                    f"Added **{team.name}** to tournament `{tournament['id']}`.",
                    ephemeral=True,
                )

            await tournament_interaction.response.send_message(
                f"Choose a team to add to **{tournament['name']}**.",
                view=TeamSelectView(self.cog, tournament_interaction.user.id, teams, add_team, "Choose a team to add"),
                ephemeral=True,
            )

        await self._choose_tournament(
            interaction,
            "Choose a tournament to add a team to.",
            choose_team,
            include_closed=False,
        )

    async def _handle_tournament_standings(self, interaction: discord.Interaction) -> None:
        async def show_standings(select_interaction: discord.Interaction, tournament):
            rows = await self.cog.bot.db.standings(int(tournament["id"]))
            if not rows:
                await select_interaction.response.send_message("No standings yet.", ephemeral=True)
                return
            races = await self.cog.bot.db.tournament_races(int(tournament["id"]), championship_only=True)
            lines = []
            for index, row in enumerate(rows, start=1):
                form = " · ".join(team_form(races, int(row["team_id"]), 5)) or "—"
                lines.append(
                    f"**{index}. {row['name']}** - {row['points']} pts | W {row['wins']} | Podiums {row['podiums']} | "
                    f"FL {row['fastest_laps']} | DNF {row['dnfs']} | DSQ {row['disqualifications']}\n"
                    f"Form: `{form}` | Car Dmg {row['carryover_damage']}%"
                )
            view = PaginatedTextView(select_interaction.user.id, f"Standings: {tournament['name']}", lines, per_page=10)
            await select_interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

        await self._choose_tournament(interaction, "Choose a tournament for standings.", show_standings)

    async def _handle_tournament_stats(self, interaction: discord.Interaction) -> None:
        async def show_stats(select_interaction: discord.Interaction, tournament):
            rows = await self.cog.bot.db.standings(int(tournament["id"]))
            if not rows:
                await select_interaction.response.send_message("No tournament stats yet.", ephemeral=True)
                return
            await select_interaction.response.send_message(embed=tournament_stats_embed(tournament, rows), ephemeral=True)

        await self._choose_tournament(interaction, "Choose a tournament for stats.", show_stats)

    async def _handle_season_history(self, interaction: discord.Interaction) -> None:
        rows = await self.cog.bot.db.season_history()
        view = PaginatedTextView(interaction.user.id, "Season History", season_history_lines(rows), per_page=8)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def _handle_tournament_start_race(self, interaction: discord.Interaction) -> None:
        async def choose_track(select_interaction: discord.Interaction, tournament):
            async def start_with_track(track_interaction: discord.Interaction, track_key: str):
                team_ids = await self.cog.bot.db.tournament_team_ids(int(tournament["id"]))
                await self._confirm_tournament_race(track_interaction, int(tournament["id"]), track_key, team_ids, None)

            await select_interaction.response.send_message(
                f"Choose a track for **{tournament['name']}**.",
                view=TrackSelectView(self.cog, select_interaction.user.id, start_with_track),
                ephemeral=True,
            )

        await self._choose_tournament(
            interaction,
            "Choose a tournament to start a race.",
            choose_track,
            include_closed=False,
        )

    async def _handle_tournament_next_race(self, interaction: discord.Interaction) -> None:
        tournament = await self._current_tournament()
        if not tournament:
            await interaction.response.send_message("No current tournament found.", ephemeral=True)
            return
        tournaments_cog = self._tournaments_cog()
        if not tournaments_cog:
            await interaction.response.send_message("Tournament tools are not loaded.", ephemeral=True)
            return
        await tournaments_cog.tournament_next_race.callback(tournaments_cog, interaction, int(tournament["id"]), None)

    async def _handle_tournament_schedule(self, interaction: discord.Interaction) -> None:
        async def show_schedule(select_interaction: discord.Interaction, tournament):
            rows = await self.cog.bot.db.tournament_schedule(int(tournament["id"]))
            if not rows:
                await select_interaction.response.send_message("This tournament does not have a saved schedule.", ephemeral=True)
                return
            races = await self.cog.bot.db.tournament_races(int(tournament["id"]))
            await select_interaction.response.send_message(calendar_text(calendar_entries(rows, races)), ephemeral=True)

        await self._choose_tournament(interaction, "Choose a tournament schedule.", show_schedule)

    async def _handle_tournament_close(self, interaction: discord.Interaction) -> None:
        async def ask_close(select_interaction: discord.Interaction, tournament):
            async def close_tournament(confirm_interaction: discord.Interaction):
                try:
                    await self.cog.bot.db.close_tournament(int(tournament["id"]))
                except ValueError as exc:
                    await confirm_interaction.response.edit_message(content=str(exc), embed=None, view=None)
                    return
                await audit_log(
                    self.cog.bot,
                    "Tournament Closed",
                    f"#{tournament['id']} {tournament['name']}",
                    confirm_interaction.user,
                )
                await confirm_interaction.response.edit_message(
                    content=f"Finalised, saved and closed tournament **{tournament['name']}** (`{tournament['id']}`).",
                    embed=None,
                    view=None,
                )

            schedule = await self.cog.bot.db.tournament_schedule(int(tournament["id"]))
            completed = await self.cog.bot.db.tournament_scheduled_race_count(int(tournament["id"]))
            close_note = ""
            if schedule and completed < len(schedule):
                close_note = (
                    f"\n\n⚠️ Only **{completed}/{len(schedule)} rounds** are complete. "
                    "Closing now records a **Shortened Season** in Season History."
                )
            embed = discord.Embed(
                title="Confirm Tournament Close",
                description=f"Close **#{tournament['id']} {tournament['name']}**?{close_note}",
                color=discord.Color.red(),
            )
            await select_interaction.response.send_message(
                embed=embed,
                view=ConfirmView(select_interaction.user.id, "Close Tournament", close_tournament),
                ephemeral=True,
            )

        await self._choose_tournament(
            interaction,
            "Choose a tournament to close.",
            ask_close,
            include_closed=False,
        )

    async def _handle_race_quick(self, interaction: discord.Interaction) -> None:
        async def choose_teams(track_interaction: discord.Interaction, track_key: str):
            teams = await self.cog.bot.db.list_teams()
            if len(teams) < 2:
                await track_interaction.response.send_message("I need at least 2 teams.", ephemeral=True)
                return

            async def confirm_with_teams(team_interaction: discord.Interaction, team_ids: list[int]):
                teams_by_id = {team.id: team for team in await self.cog.bot.db.list_teams()}
                selected = [teams_by_id[team_id] for team_id in team_ids if team_id in teams_by_id]
                await self._confirm_single_race(team_interaction, track_key, selected, None, "Admin Quick Race")

            await track_interaction.response.send_message(
                "Choose 2-10 teams for the quick race.",
                view=TeamMultiSelectView(self.cog, track_interaction.user.id, teams, confirm_with_teams),
                ephemeral=True,
            )

        await interaction.response.send_message(
            "Choose a track for Race Quick.",
            view=TrackSelectView(self.cog, interaction.user.id, choose_teams),
            ephemeral=True,
        )

    async def _handle_race_demo(self, interaction: discord.Interaction) -> None:
        async def confirm_demo(track_interaction: discord.Interaction, track_key: str):
            existing = await self.cog.bot.db.list_teams()
            preview_teams = existing[:10] if len(existing) >= 10 else [*existing, *ai_teams(10 - len(existing), f"demo-preview-{len(existing)}")]
            await self._confirm_demo_race(track_interaction, track_key, preview_teams)

        await interaction.response.send_message(
            "Choose a demo race track.",
            view=TrackSelectView(self.cog, interaction.user.id, confirm_demo),
            ephemeral=True,
        )

    async def _handle_race_replay(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(RaceReplayModal(self))

    async def replay_race_id(self, interaction: discord.Interaction, race_id: int) -> None:
        race = await self.cog.bot.db.get_race(race_id)
        if not race:
            await interaction.response.send_message("Race not found.", ephemeral=True)
            return
        results = json.loads(race["results_json"])
        teams = []
        for result in results[:10]:
            team_id = int(result.get("team_id", 0))
            if team_id <= 0:
                continue
            team = await self.cog.bot.db.get_team(team_id)
            if team:
                teams.append(team)
        await self._confirm_single_race(
            interaction,
            str(race["track_key"]),
            teams,
            str(race["seed"]),
            f"Replay Race #{race_id}",
        )

    async def _handle_backup_database(self, interaction: discord.Interaction) -> None:
        await self.cog.backup_database(interaction)

    async def _handle_admin_health(self, interaction: discord.Interaction) -> None:
        recovery_cog = self.cog.bot.get_cog("RecoveryCog")
        if not recovery_cog:
            await interaction.response.send_message("Recovery/health tools are not loaded.", ephemeral=True)
            return
        await recovery_cog.admin_health.callback(recovery_cog, interaction)

    async def _confirm_single_race(
        self,
        interaction: discord.Interaction,
        track_key: str,
        teams,
        seed: str | None,
        title: str,
    ) -> None:
        if len(teams) < 2:
            await interaction.response.send_message("I need at least 2 teams.", ephemeral=True)
            return
        engine = RaceEngine(track_key, teams, seed)
        seed = engine.seed
        embed = race_preflight_embed(teams, TRACKS[track_key].name, engine.weather, title="Confirm Race Quick", seed=seed, track_key=track_key, laps=TRACKS[track_key].laps)

        async def run(confirm_interaction: discord.Interaction):
            racing_cog = self._racing_cog()
            if not racing_cog:
                await confirm_interaction.response.edit_message(content="Race tools are not loaded.", embed=None, view=None)
                return
            await confirm_interaction.response.edit_message(content="Race confirmed. Posting to channel now.", embed=None, view=None)
            await audit_log(self.cog.bot, "Race Started", f"{title} at {TRACKS[track_key].name} seed {seed}", confirm_interaction.user)
            await racing_cog.run_single_race(confirm_interaction.channel, track_key, TRACKS[track_key].laps, teams, title=title, seed=seed)

        await interaction.response.send_message(
            embed=embed,
            view=ConfirmView(interaction.user.id, "Start Race", run),
            ephemeral=True,
        )

    async def _confirm_demo_race(self, interaction: discord.Interaction, track_key: str, preview_teams) -> None:
        engine = RaceEngine(track_key, preview_teams)
        seed = engine.seed
        embed = race_preflight_embed(preview_teams, TRACKS[track_key].name, engine.weather, title="Confirm Demo Race", seed=seed, track_key=track_key, laps=TRACKS[track_key].laps)

        async def run(confirm_interaction: discord.Interaction):
            await confirm_interaction.response.edit_message(content="Demo race confirmed. Posting to channel now.", embed=None, view=None)
            await audit_log(self.cog.bot, "Demo Race Started", f"{TRACKS[track_key].name} seed {seed}", confirm_interaction.user)
            racing_cog = self._racing_cog()
            if not racing_cog:
                await confirm_interaction.followup.send("Race tools are not loaded.", ephemeral=True)
                return
            await racing_cog.run_demo_race(confirm_interaction.channel, track_key, seed)

        await interaction.response.send_message(
            embed=embed,
            view=ConfirmView(interaction.user.id, "Start Demo Race", run),
            ephemeral=True,
        )

    async def _confirm_tournament_race(
        self,
        interaction: discord.Interaction,
        tournament_id: int,
        track_key: str,
        team_ids: list[int],
        seed: str | None,
    ) -> None:
        try:
            await self.cog.bot.db.require_full_tournament_grid(tournament_id)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        teams = []
        tournament_ids = set(await self.cog.bot.db.tournament_team_ids(tournament_id))
        if len(team_ids) != 10 or set(team_ids) != tournament_ids:
            await interaction.response.send_message("Tournament races must use all 10 entered teams exactly once.", ephemeral=True)
            return
        for team_id in team_ids:
            team = await self.cog.bot.db.get_team(team_id)
            if team:
                teams.append(team)
        if len(teams) != 10:
            await interaction.response.send_message("Tournament grid is incomplete; all 10 entered teams must exist.", ephemeral=True)
            return
        carryover_damage = await self.cog.bot.db.tournament_carryover_damage(tournament_id)
        schedule = await self.cog.bot.db.tournament_schedule(tournament_id)
        title_prefix = "Exhibition Race" if schedule else "Tournament Race"
        engine = RaceEngine(track_key, teams, seed, initial_damage_by_team_id=carryover_damage)
        seed = engine.seed
        embed = race_preflight_embed(
            teams,
            TRACKS[track_key].name,
            engine.weather,
            title=f"Confirm {title_prefix}",
            seed=seed,
            carryover_damage=carryover_damage,
            track_key=track_key,
            laps=engine.laps,
        )

        async def run(confirm_interaction: discord.Interaction):
            tournaments_cog = self._tournaments_cog()
            if not tournaments_cog:
                await confirm_interaction.response.edit_message(content="Tournament tools are not loaded.", embed=None, view=None)
                return
            await confirm_interaction.response.edit_message(content="Tournament race confirmed. Posting to channel now.", embed=None, view=None)
            await audit_log(self.cog.bot, "Tournament Race Started", f"Tournament #{tournament_id} at {TRACKS[track_key].name} seed {seed}", confirm_interaction.user)
            await tournaments_cog._run_tournament_race(
                confirm_interaction,
                tournament_id,
                track_key,
                team_ids,
                seed,
                title_prefix=title_prefix,
            )

        await interaction.response.send_message(
            embed=embed,
            view=ConfirmView(interaction.user.id, "Start Tournament Race", run),
            ephemeral=True,
        )

    async def _handle_current_tournament(self, interaction: discord.Interaction) -> None:
        tournament = await self.cog.bot.db.current_tournament()
        if not tournament:
            await interaction.response.send_message("No open tournament found.", ephemeral=True)
            return

        rows = await self.cog.bot.db.standings(int(tournament["id"]))
        race_count = await self.cog.bot.db.tournament_race_count(int(tournament["id"]))
        championship_count = await self.cog.bot.db.tournament_championship_race_count(int(tournament["id"]))
        next_track = await self.cog.bot.db.next_scheduled_track(int(tournament["id"]))
        embed = discord.Embed(
            title=f"Admin Panel: {tournament['name']}",
            description=f"Championship races: **{championship_count}** | All saved tournament races: **{race_count}**",
            color=discord.Color.dark_gold(),
        )
        if next_track:
            race_number, track_key = next_track
            embed.add_field(name="Next Race", value=f"Race {race_number}: `{track_key}`", inline=False)
        standings = [
            f"**{index}. {row['name']}** - {row['points']} pts"
            for index, row in enumerate(rows[:10], start=1)
        ]
        embed.add_field(name="Standings", value="\n".join(standings) if standings else "No standings yet.", inline=False)
        await interaction.response.send_message(embed=embed, ephemeral=True)


class AdminCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.media = MediaRegistry()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_admin(interaction):
            return True
        await deny_admin_only(interaction)
        return False

    @app_commands.command(name="ratbot_init", description="Initialise the Rat Rod Racing database.")
    async def ratbot_init(self, interaction: discord.Interaction):
        await self.bot.db.init()
        await interaction.response.send_message("Database checked and ready. The rods are coughing smoke in the alley.", ephemeral=True)

    @app_commands.command(name="media_list", description="Show configured GIF/audio media keys.")
    async def media_list(self, interaction: discord.Interaction):
        self.media.load()
        lines = self.media.keys_text().splitlines()
        view = PaginatedTextView(interaction.user.id, "Media Keys", lines, per_page=15)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(name="parts_catalogue", description="List available rod parts and modifiers.")
    async def parts_catalogue(self, interaction: discord.Interaction):
        view = PaginatedTextView(interaction.user.id, "Parts Catalogue", parts_catalogue_lines(), per_page=12)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(name="backup_database", description="Admin: create a consistent timestamped SQLite backup.")
    async def backup_database(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        try:
            backup_path = await self.bot.recovery.backup_database("manual")
        except (OSError, sqlite3.DatabaseError) as exc:
            await interaction.followup.send(f"Backup failed: {exc}", ephemeral=True)
            return
        await audit_log(self.bot, "Database Backup Created", str(backup_path), interaction.user)
        await interaction.followup.send(f"Database backup created: {backup_path}", ephemeral=True)

    @app_commands.command(name="admin_panel", description="Open a quick admin control panel.")
    async def admin_panel(self, interaction: discord.Interaction):
        file = admin_panel_file()
        embed = admin_panel_embed(include_image=file is not None)
        if file:
            await interaction.response.send_message(
                embed=embed,
                file=file,
                view=AdminPanelView(self, interaction.user.id),
                ephemeral=True,
            )
            return

        if not file:
            embed.description = "Private command hub for running teams, races, tournaments, and bot setup."
        await interaction.response.send_message(
            embed=embed,
            view=AdminPanelView(self, interaction.user.id),
            ephemeral=True,
        )

    @app_commands.command(name="ai_personalize_saved", description="Admin: upgrade saved AI/demo teams with personalities, parts, and crew.")
    async def ai_personalize_saved(self, interaction: discord.Interaction, start_id: int = 2, end_id: int = 11):
        await interaction.response.defer(ephemeral=True)
        if start_id > end_id:
            start_id, end_id = end_id, start_id

        count = min(25, end_id - start_id + 1)
        generated = ai_teams(count, f"saved-ai-upgrade-{start_id}-{end_id}")
        updated = []
        for team_id, ai_team in zip(range(start_id, start_id + count), generated):
            existing = await self.bot.db.get_team(team_id)
            if not existing:
                continue
            existing.pit_crew_name = ai_team.pit_crew_name
            existing.archetype = ai_team.archetype
            existing.stats = ai_team.stats
            existing.parts = ai_team.parts
            existing.crew = ai_team.crew
            await self.bot.db.update_team_profile(existing)
            await self.bot.db.update_team_parts(team_id, existing.parts)
            await self.bot.db.update_team_crew(team_id, existing.crew)
            updated.append(f"`#{team_id}` **{existing.name}** - {existing.pit_crew_name}")

        if not updated:
            await interaction.followup.send("No teams found in that ID range.", ephemeral=True)
            return

        await audit_log(self.bot, "AI Teams Personalized", f"Range {start_id}-{end_id}", interaction.user)
        await interaction.followup.send(
            "Personalized saved AI/demo teams:\n" + "\n".join(updated[:20]),
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(AdminCog(bot))
