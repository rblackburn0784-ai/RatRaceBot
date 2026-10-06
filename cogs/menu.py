import discord
from discord import app_commands
from discord.ext import commands

from cogs.admin import AdminPanelView, TeamSelectView, admin_panel_embed, admin_panel_file
from cogs.racing import RaceWizardView
from cogs.tournaments import TournamentWizardView
from cogs.teams import EditTeamWizardView, GarageView, MyTeamActionsView, PitCrewWizardView, SetupManagerView, SponsorOfferActionView, TeamIdentityView, TeamWizardView, team_identity_embed
from config import BOT_VERSION
from services.access import is_admin
from services.championship import championship_hub_embed
from services.engagement import available_titles_for_level, level_for_xp, progress_embed, sponsor_offers_embed
from services.menu_cards import MAIN_MENU_BACKGROUND, render_main_menu_card
from services.scrutineering import scrutineering_embed
from services.story import garage_summary_embed, hall_of_fame_embed, rivalries_embed, season_history_lines
from services.world_state import build_world_snapshot, career_history_embed, gazette_archive_embed, season_awards_embed, world_hub_embed
from services.views import PaginatedTextView
from services.ui_safety import ReliableView


class TeamTitleSelect(discord.ui.Select):
    def __init__(self, view: "TeamTitleView", titles: list[str]):
        self.menu_view = view
        options = [discord.SelectOption(label=title, value=title) for title in titles[:25]]
        super().__init__(placeholder="Choose a team title", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        if not self.menu_view.team or self.menu_view.team.id is None:
            await interaction.response.send_message("Team not found.", ephemeral=True)
            return
        title = self.values[0]
        await self.menu_view.cog.bot.db.set_team_title(self.menu_view.team.id, title)
        await interaction.response.edit_message(content=f"Set **{self.menu_view.team.name}** title to **{title}**.", view=None)


class TeamTitleView(ReliableView):
    def __init__(self, cog: "MenuCog", owner_id: int, team, titles: list[str]):
        super().__init__(timeout=180)
        self.cog = cog
        self.owner_id = owner_id
        self.team = team
        self.add_item(TeamTitleSelect(self, titles))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This title picker belongs to another driver.", ephemeral=True)
        return False


class MenuButton(discord.ui.Button):
    def __init__(self, key: str, label: str, row: int, style: discord.ButtonStyle = discord.ButtonStyle.secondary):
        super().__init__(label=label, style=style, row=row)
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, MainMenuView):
            await interaction.response.send_message("Menu expired. Use `/menu` again.", ephemeral=True)
            return
        await view.handle_button(interaction, self.key)


class StartMenuView(ReliableView):
    def __init__(self, cog: "MenuCog", owner_id: int):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("Use `/menu` to open your own start menu.", ephemeral=True)
        return False

    @discord.ui.button(label="Create Team Wizard", style=discord.ButtonStyle.success)
    async def create_team(self, interaction: discord.Interaction, button: discord.ui.Button):
        teams_cog = self.cog.teams_cog()
        if not teams_cog:
            await interaction.response.send_message("Team tools are not loaded.", ephemeral=True)
            return
        view = TeamWizardView(teams_cog, interaction.user.id)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)


class WorldActionButton(discord.ui.Button):
    def __init__(self, key: str, label: str, row: int, style: discord.ButtonStyle = discord.ButtonStyle.secondary):
        super().__init__(label=label, row=row, style=style)
        self.key = key

    async def callback(self, interaction: discord.Interaction):
        view = self.view
        if not isinstance(view, WorldHubView):
            await interaction.response.send_message("This World Hub is no longer active. Use `/world` to reopen it.", ephemeral=True)
            return
        await view.handle_action(interaction, self.key)


class WorldHubView(ReliableView):
    def __init__(self, cog: "MenuCog", owner_id: int, team_id: int, next_key: str):
        super().__init__(timeout=900)
        self.cog = cog
        self.owner_id = owner_id
        self.team_id = int(team_id)
        self.next_key = next_key
        buttons = [
            ("garage", "Garage", 0, discord.ButtonStyle.primary),
            ("crew", "Hire Crew", 0, discord.ButtonStyle.primary),
            ("race", "Race", 0, discord.ButtonStyle.danger),
            ("progress", "XP / Reputation", 0, discord.ButtonStyle.secondary),
            ("championship", "Championship", 0, discord.ButtonStyle.success),
            ("sponsors", "Sponsors", 1, discord.ButtonStyle.secondary),
            ("rivalries", "Rivalries", 1, discord.ButtonStyle.secondary),
            ("world_events", "World Stories", 1, discord.ButtonStyle.secondary),
            ("gazette", "Gazette", 1, discord.ButtonStyle.secondary),
            ("history", "Team History", 1, discord.ButtonStyle.secondary),
            ("setups", "Track Setups", 2, discord.ButtonStyle.primary),
            ("awards", "Season Awards", 2, discord.ButtonStyle.secondary),
            ("recommended", "▶ Recommended Next", 2, discord.ButtonStyle.success),
            ("refresh", "Refresh World", 2, discord.ButtonStyle.primary),
            ("main_menu", "Main Menu", 2, discord.ButtonStyle.secondary),
            ("next_season", "Next Season", 3, discord.ButtonStyle.success),
        ]
        for key, label, row, style in buttons:
            self.add_item(WorldActionButton(key, label, row, style))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This Blacktop World belongs to another driver. Use `/world` for your own.", ephemeral=True)
        return False

    async def team(self):
        return await self.cog.bot.db.get_team(self.team_id)

    async def handle_action(self, interaction: discord.Interaction, key: str) -> None:
        if key == "recommended":
            key = self.next_key
        handler = getattr(self, f"_handle_{key}", None)
        if not handler:
            await interaction.response.send_message("That World Hub action is unavailable. Refresh the hub and try again.", ephemeral=True)
            return
        await handler(interaction)

    async def _require_team(self, interaction: discord.Interaction):
        team = await self.team()
        if team:
            return team
        await interaction.response.send_message("That team no longer exists. Reopen `/menu` and choose a current team.", ephemeral=True)
        return None

    async def _handle_garage(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        teams_cog = self.cog.teams_cog()
        if not team or not teams_cog:
            if team and not teams_cog:
                await interaction.response.send_message("Garage tools are not loaded.", ephemeral=True)
            return
        progress = await self.cog.bot.db.team_progress(team.id)
        level = level_for_xp(int(progress["xp"]) if progress else 0)
        setups = await self.cog.bot.db.team_setups(team.id)
        view = GarageView(teams_cog, interaction.user.id, team, setups, level)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def _handle_crew(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        teams_cog = self.cog.teams_cog()
        if not team or not teams_cog:
            if team and not teams_cog:
                await interaction.response.send_message("Pit crew tools are not loaded.", ephemeral=True)
            return
        progress = await self.cog.bot.db.team_progress(team.id)
        level = level_for_xp(int(progress["xp"]) if progress else 0)
        view = PitCrewWizardView(teams_cog, interaction.user.id, team, level)
        file = view.crew_file()
        if file:
            await interaction.response.send_message(embed=view.embed(True), file=file, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=view.embed(False), view=view, ephemeral=True)

    async def _handle_race(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        racing_cog = self.cog.racing_cog()
        if not team or not racing_cog:
            if team and not racing_cog:
                await interaction.response.send_message("Race tools are not loaded.", ephemeral=True)
            return
        if await self.cog.bot.race_activity.is_team_busy(int(team.id)):
            await interaction.response.send_message("That team is already in an active race or race lobby.", ephemeral=True)
            return
        view = RaceWizardView(racing_cog, interaction.user.id, team)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def _handle_progress(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        if not team:
            return
        await interaction.response.send_message(
            embed=progress_embed(
                team,
                await self.cog.bot.db.team_progress(team.id),
                await self.cog.bot.db.team_achievements(team.id),
                await self.cog.bot.db.team_sponsor_offers(team.id),
                await self.cog.bot.db.team_fatigue(team.id),
            ),
            ephemeral=True,
        )

    async def _handle_championship(self, interaction: discord.Interaction) -> None:
        tournament = await self.cog.bot.db.current_tournament()
        if not tournament:
            recent = await self.cog.bot.db.list_tournaments(include_closed=True, limit=1)
            tournament = recent[0] if recent else None
        if not tournament:
            await interaction.response.send_message("No championship exists yet. An admin can create the next season from the Tournament Wizard.", ephemeral=True)
            return
        tid = int(tournament["id"])
        await interaction.response.send_message(
            embed=championship_hub_embed(
                tournament,
                await self.cog.bot.db.standings(tid),
                await self.cog.bot.db.tournament_schedule(tid),
                await self.cog.bot.db.tournament_races(tid),
                await self.cog.bot.db.tournament_rivalries(tid, limit=5),
            ),
            ephemeral=True,
        )

    async def _handle_sponsors(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        teams_cog = self.cog.teams_cog()
        if not team:
            return
        offers = await self.cog.bot.db.team_sponsor_offers(team.id, limit=8)
        view = SponsorOfferActionView(teams_cog, interaction.user.id, team, offers) if teams_cog else None
        await interaction.response.send_message(embed=sponsor_offers_embed(team, offers), view=view, ephemeral=True)

    async def _handle_rivalries(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        if not team:
            return
        await interaction.response.send_message(
            embed=rivalries_embed(team, await self.cog.bot.db.team_rivalries(team.id)),
            ephemeral=True,
        )

    async def _handle_world_events(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        world_cog = self.cog.bot.get_cog("RacingWorldCog")
        if not team or not world_cog:
            if team and not world_cog:
                await interaction.response.send_message("Blacktop World story tools are not loaded.", ephemeral=True)
            return
        await world_cog.send_world_events(interaction, team)

    async def _handle_gazette(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        if team:
            await interaction.response.send_message(embed=await gazette_archive_embed(self.cog.bot.db, team), ephemeral=True)

    async def _handle_history(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        if not team:
            return
        await interaction.response.send_message(
            embed=career_history_embed(
                team,
                await self.cog.bot.db.team_career_summary(team.id),
                await self.cog.bot.db.team_season_history(team.id),
            ),
            ephemeral=True,
        )

    async def _handle_setups(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        teams_cog = self.cog.teams_cog()
        if not team or not teams_cog:
            if team and not teams_cog:
                await interaction.response.send_message("Track setup tools are not loaded.", ephemeral=True)
            return
        progress = await self.cog.bot.db.team_progress(team.id)
        level = level_for_xp(int(progress["xp"]) if progress else 0)
        setups = await self.cog.bot.db.team_setups(team.id)
        view = SetupManagerView(teams_cog, interaction.user.id, team, setups, "load", level)
        await interaction.response.send_message(
            embed=discord.Embed(
                title=f"Track Setups — {team.name}",
                description=(
                    "Save the current hardware into an unlocked preset or load an existing setup before a race. "
                    "Setups change choices, not the underlying progression balance."
                ),
                color=discord.Color.dark_teal(),
            ),
            view=view,
            ephemeral=True,
        )

    async def _handle_awards(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        if team:
            await interaction.response.send_message(
                embed=season_awards_embed(team, await self.cog.bot.db.team_season_history(team.id)),
                ephemeral=True,
            )

    async def _handle_refresh(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        if not team:
            return
        snapshot = await build_world_snapshot(self.cog.bot.db, team)
        self.next_key = str(snapshot["next_key"])
        await interaction.response.edit_message(embed=world_hub_embed(snapshot), view=self)

    async def _handle_next_season(self, interaction: discord.Interaction) -> None:
        team = await self._require_team(interaction)
        if not team:
            return
        current = await self.cog.bot.db.current_tournament()
        if current:
            await interaction.response.send_message(
                f"**{current['name']}** is still the active season. Finish or close it before starting the next one.",
                ephemeral=True,
            )
            return
        history = await self.cog.bot.db.team_season_history(int(team.id), limit=1)
        archive_note = (
            f"Your last season, **{history[0]['season_name']}**, is permanently archived."
            if history else
            "This team has not completed a championship season yet."
        )
        if not is_admin(interaction):
            await interaction.response.send_message(
                archive_note + " An admin starts the next championship; you can keep running exhibition races while you wait.",
                ephemeral=True,
            )
            return
        tournaments_cog = self.cog.tournaments_cog()
        if not tournaments_cog:
            await interaction.response.send_message("Tournament tools are not loaded.", ephemeral=True)
            return
        teams = await self.cog.bot.db.list_teams()
        if len(teams) < 10:
            await interaction.response.send_message(
                archive_note + f" The next championship needs 10 saved teams; only {len(teams)} exist.",
                ephemeral=True,
            )
            return
        view = TournamentWizardView(tournaments_cog, interaction.user.id, teams)
        await interaction.response.send_message(
            content=archive_note + " Build the next season below.",
            embed=view.embed(),
            view=view,
            ephemeral=True,
        )

    async def _handle_main_menu(self, interaction: discord.Interaction) -> None:
        view = MainMenuView(self.cog, interaction.user.id, show_admin=is_admin(interaction))
        await interaction.response.send_message(
            embed=discord.Embed(title="Rat Rod Racing Bot", description="Main menu"),
            view=view,
            ephemeral=True,
        )


class MainMenuView(ReliableView):
    def __init__(self, cog: "MenuCog", owner_id: int, show_admin: bool):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        buttons = [
            ("world_hub", "🌎 Blacktop World", 0, discord.ButtonStyle.success),
            ("team_wizard", "Create Team Wizard", 0, discord.ButtonStyle.success),
            ("team_edit_wizard", "Team Edit Wizard", 0, discord.ButtonStyle.primary),
            ("pit_crew_wizard", "Pit Crew Wizard", 0, discord.ButtonStyle.primary),
            ("my_team", "My Team", 0, discord.ButtonStyle.secondary),
            ("race_wizard", "Race Wizard", 1, discord.ButtonStyle.danger),
            ("scrutineering", "Scrutineering", 1, discord.ButtonStyle.secondary),
            ("sponsor_offers", "Sponsor Offers", 1, discord.ButtonStyle.secondary),
            ("team_progress", "Team Progress", 1, discord.ButtonStyle.secondary),
            ("team_title", "Team Title", 2, discord.ButtonStyle.secondary),
            ("team_rivalries", "Team Rivalries", 2, discord.ButtonStyle.secondary),
            ("championship", "Championship", 2, discord.ButtonStyle.primary),
            ("hall_of_fame", "Hall Of Fame", 2, discord.ButtonStyle.secondary),
            ("season_history", "Season History", 2, discord.ButtonStyle.secondary),
            ("team_identity", "Team Identity", 3, discord.ButtonStyle.secondary),
            ("status", "Status", 3, discord.ButtonStyle.primary),
        ]
        for key, label, row, style in buttons:
            self.add_item(MenuButton(key, label, row, style))
        if show_admin:
            self.add_item(MenuButton("admin_panel", "Admin Panel", 3, discord.ButtonStyle.danger))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This menu belongs to another driver. Use `/menu` to open your own.", ephemeral=True)
        return False

    async def handle_button(self, interaction: discord.Interaction, key: str) -> None:
        handler = getattr(self, f"_handle_{key}", None)
        if not handler:
            await interaction.response.send_message("That menu option is not ready yet.", ephemeral=True)
            return
        await handler(interaction)

    async def _with_team(self, interaction: discord.Interaction, callback) -> None:
        if not is_admin(interaction):
            team = await self.cog.bot.db.get_team_by_owner(interaction.user.id)
            if not team:
                await interaction.response.send_message("You do not have a team yet. Use Create Team Wizard.", ephemeral=True)
                return
            await callback(interaction, team)
            return

        teams = await self.cog.bot.db.list_teams()
        if not teams:
            await interaction.response.send_message("No teams found.", ephemeral=True)
            return
        admin_cog = self.cog.admin_cog()
        if not admin_cog:
            await interaction.response.send_message("Admin tools are not loaded.", ephemeral=True)
            return
        await interaction.response.send_message(
            "Choose a team for this menu action.",
            view=TeamSelectView(admin_cog, interaction.user.id, teams, callback, "Choose a team"),
            ephemeral=True,
        )

    async def _handle_world_hub(self, interaction: discord.Interaction) -> None:
        async def open_world(select_interaction: discord.Interaction, team):
            await self.cog.send_world_hub_for_team(select_interaction, team)

        await self._with_team(interaction, open_world)

    async def _handle_team_wizard(self, interaction: discord.Interaction) -> None:
        teams_cog = self.cog.teams_cog()
        if not teams_cog:
            await interaction.response.send_message("Team tools are not loaded.", ephemeral=True)
            return
        if not is_admin(interaction) and await self.cog.bot.db.get_team_by_owner(interaction.user.id):
            await interaction.response.send_message(
                "You already have a team. Use Team Edit Wizard or the garage tools to change it.",
                ephemeral=True,
            )
            return
        view = TeamWizardView(teams_cog, interaction.user.id)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def _handle_team_edit_wizard(self, interaction: discord.Interaction) -> None:
        teams_cog = self.cog.teams_cog()
        if not teams_cog:
            await interaction.response.send_message("Team tools are not loaded.", ephemeral=True)
            return

        async def open_edit(select_interaction: discord.Interaction, team):
            if team.id is not None and await self.cog.bot.db.team_in_open_tournament(team.id):
                await select_interaction.response.send_message(
                    "That team is in an open tournament, so team details are locked.",
                    ephemeral=True,
                )
                return
            view = EditTeamWizardView(teams_cog, select_interaction.user.id, team)
            await select_interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

        await self._with_team(interaction, open_edit)

    async def _handle_pit_crew_wizard(self, interaction: discord.Interaction) -> None:
        teams_cog = self.cog.teams_cog()
        if not teams_cog:
            await interaction.response.send_message("Team tools are not loaded.", ephemeral=True)
            return

        async def open_pit(select_interaction: discord.Interaction, team):
            progress = await self.cog.bot.db.team_progress(team.id)
            level = level_for_xp(int(progress["xp"]) if progress else 0)
            view = PitCrewWizardView(teams_cog, select_interaction.user.id, team, level)
            file = view.crew_file()
            if file:
                await select_interaction.response.send_message(embed=view.embed(True), file=file, view=view, ephemeral=True)
            else:
                await select_interaction.response.send_message(embed=view.embed(False), view=view, ephemeral=True)

        await self._with_team(interaction, open_pit)

    async def _handle_my_team(self, interaction: discord.Interaction) -> None:
        teams_cog = self.cog.teams_cog()
        if not teams_cog:
            await interaction.response.send_message("Team tools are not loaded.", ephemeral=True)
            return

        async def show_team(select_interaction: discord.Interaction, team):
            profile = await self.cog.bot.db.team_profile(team.id)
            rivalries = await self.cog.bot.db.team_rivalries(team.id, limit=1)
            in_open_tournament = await self.cog.bot.db.team_in_open_tournament(team.id)
            await select_interaction.response.send_message(
                embed=garage_summary_embed(team, profile, rivalries, in_open_tournament),
                view=MyTeamActionsView(teams_cog, select_interaction.user.id, team),
                ephemeral=True,
            )

        await self._with_team(interaction, show_team)

    async def _handle_race_wizard(self, interaction: discord.Interaction) -> None:
        racing_cog = self.cog.racing_cog()
        if not racing_cog:
            await interaction.response.send_message("Race tools are not loaded.", ephemeral=True)
            return
        team = await self.cog.bot.db.get_team_by_owner(interaction.user.id)
        if not team and is_admin(interaction):
            teams = await self.cog.bot.db.list_teams()
            team = teams[0] if teams else None
        if not team:
            await interaction.response.send_message("You need your own team first. Use Create Team Wizard.", ephemeral=True)
            return
        view = RaceWizardView(racing_cog, interaction.user.id, team)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def _handle_scrutineering(self, interaction: discord.Interaction) -> None:
        async def show_scrutineering(select_interaction: discord.Interaction, team):
            await select_interaction.response.send_message(
                embed=scrutineering_embed([team], title=f"Scrutineering Report: {team.name}"),
                ephemeral=True,
            )

        await self._with_team(interaction, show_scrutineering)

    async def _handle_sponsor_offers(self, interaction: discord.Interaction) -> None:
        async def show_sponsors(select_interaction: discord.Interaction, team):
            offers = await self.cog.bot.db.team_sponsor_offers(team.id, limit=8)
            teams_cog = self.cog.teams_cog()
            view = SponsorOfferActionView(teams_cog, select_interaction.user.id, team, offers) if teams_cog else None
            await select_interaction.response.send_message(embed=sponsor_offers_embed(team, offers), view=view, ephemeral=True)

        await self._with_team(interaction, show_sponsors)

    async def _handle_team_progress(self, interaction: discord.Interaction) -> None:
        async def show_progress(select_interaction: discord.Interaction, team):
            await select_interaction.response.send_message(
                embed=progress_embed(
                    team,
                    await self.cog.bot.db.team_progress(team.id),
                    await self.cog.bot.db.team_achievements(team.id),
                    await self.cog.bot.db.team_sponsor_offers(team.id),
                    await self.cog.bot.db.team_fatigue(team.id),
                ),
                ephemeral=True,
            )

        await self._with_team(interaction, show_progress)

    async def _handle_team_title(self, interaction: discord.Interaction) -> None:
        async def choose_title(select_interaction: discord.Interaction, team):
            progress = await self.cog.bot.db.team_progress(team.id)
            xp = int(progress["xp"]) if progress else 0
            titles = available_titles_for_level(level_for_xp(xp))
            await select_interaction.response.send_message(
                f"Choose a title for **{team.name}**.",
                view=TeamTitleView(self.cog, select_interaction.user.id, team, titles),
                ephemeral=True,
            )

        await self._with_team(interaction, choose_title)

    async def _handle_team_identity(self, interaction: discord.Interaction) -> None:
        teams_cog = self.cog.teams_cog()
        if not teams_cog:
            await interaction.response.send_message("Team tools are not loaded.", ephemeral=True)
            return

        async def show_identity(select_interaction: discord.Interaction, team):
            progress = await self.cog.bot.db.team_progress(team.id)
            level = level_for_xp(int(progress["xp"]) if progress else 0)
            identity = await self.cog.bot.db.team_identity(team.id)
            await select_interaction.response.send_message(
                embed=team_identity_embed(team, identity, level),
                view=TeamIdentityView(teams_cog, select_interaction.user.id, team, identity, level),
                ephemeral=True,
            )

        await self._with_team(interaction, show_identity)

    async def _handle_team_rivalries(self, interaction: discord.Interaction) -> None:
        async def show_rivalries(select_interaction: discord.Interaction, team):
            rivalries = await self.cog.bot.db.team_rivalries(team.id)
            await select_interaction.response.send_message(embed=rivalries_embed(team, rivalries), ephemeral=True)

        await self._with_team(interaction, show_rivalries)

    async def _handle_championship(self, interaction: discord.Interaction) -> None:
        tournament = await self.cog.bot.db.current_tournament()
        if not tournament:
            recent = await self.cog.bot.db.list_tournaments(include_closed=True, limit=1)
            tournament = recent[0] if recent else None
        if not tournament:
            await interaction.response.send_message("No championship found.", ephemeral=True)
            return
        tid = int(tournament["id"])
        await interaction.response.send_message(
            embed=championship_hub_embed(
                tournament,
                await self.cog.bot.db.standings(tid),
                await self.cog.bot.db.tournament_schedule(tid),
                await self.cog.bot.db.tournament_races(tid),
                await self.cog.bot.db.tournament_rivalries(tid, limit=5),
            ),
            ephemeral=True,
        )

    async def _handle_hall_of_fame(self, interaction: discord.Interaction) -> None:
        stat_keys = (
            "wins",
            "overtakes",
            "last_minute_wins",
            "pit_stops",
            "near_misses",
            "crashes",
            "illegal_moves",
            "peak_damage",
        )
        stat_leaders = {
            key: await self.cog.bot.db.hall_of_fame_stat_leaders(key, limit=1)
            for key in stat_keys
        }
        await interaction.response.send_message(
            embed=hall_of_fame_embed(
                champions=await self.cog.bot.db.hall_of_fame_champions(),
                podiums=await self.cog.bot.db.hall_of_fame_podiums(),
                stat_leaders=stat_leaders,
                rivalries=await self.cog.bot.db.hall_of_fame_rivalries(),
                recent_seasons=await self.cog.bot.db.season_history(limit=5),
            ),
            ephemeral=True,
        )

    async def _handle_season_history(self, interaction: discord.Interaction) -> None:
        rows = await self.cog.bot.db.season_history()
        view = PaginatedTextView(interaction.user.id, "Season History", season_history_lines(rows), per_page=8)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def _handle_admin_panel(self, interaction: discord.Interaction) -> None:
        if not is_admin(interaction):
            await interaction.response.send_message("Only admins can use that button.", ephemeral=True)
            return
        admin_cog = self.cog.admin_cog()
        if not admin_cog:
            await interaction.response.send_message("Admin tools are not loaded.", ephemeral=True)
            return
        file = admin_panel_file()
        embed = admin_panel_embed(include_image=file is not None)
        if file:
            await interaction.response.send_message(
                embed=embed,
                file=file,
                view=AdminPanelView(admin_cog, interaction.user.id),
                ephemeral=True,
            )
        else:
            embed.description = "Private command hub for running teams, races, tournaments, and bot setup."
            await interaction.response.send_message(
                embed=embed,
                view=AdminPanelView(admin_cog, interaction.user.id),
                ephemeral=True,
            )

    async def _handle_status(self, interaction: discord.Interaction) -> None:
        await self.cog.send_status(interaction)


class MenuCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    def teams_cog(self):
        return self.bot.get_cog("TeamsCog")

    def racing_cog(self):
        return self.bot.get_cog("RacingCog")

    def admin_cog(self):
        return self.bot.get_cog("AdminCog")

    def tournaments_cog(self):
        return self.bot.get_cog("TournamentsCog")

    async def owned_or_admin_team(self, interaction: discord.Interaction, teams_cog=None):
        teams_cog = teams_cog or self.teams_cog()
        if teams_cog:
            return await teams_cog._owned_or_admin_team(interaction)

        team = await self.bot.db.get_team_by_owner(interaction.user.id)
        if team:
            return team
        await interaction.response.send_message("You do not have a team yet. Use Create Team Wizard.", ephemeral=True)
        return None

    async def send_world_hub_for_team(self, interaction: discord.Interaction, team) -> None:
        snapshot = await build_world_snapshot(self.bot.db, team)
        await interaction.response.send_message(
            embed=world_hub_embed(snapshot),
            view=WorldHubView(self, interaction.user.id, int(team.id), str(snapshot["next_key"])),
            ephemeral=True,
        )

    @app_commands.command(name="world", description="Open your persistent Blacktop Racing World hub.")
    async def world(self, interaction: discord.Interaction):
        view = MainMenuView(self, interaction.user.id, show_admin=is_admin(interaction))
        await view._handle_world_hub(interaction)

    @app_commands.command(name="menu", description="Open the Rat Rod Racing Bot main menu.")
    async def menu(self, interaction: discord.Interaction):
        show_admin = is_admin(interaction)
        if not show_admin and not await self.bot.db.get_team_by_owner(interaction.user.id):
            view = StartMenuView(self, interaction.user.id)
            embed = discord.Embed(
                title="Start Here",
                description="Create your racing team first, then the full menu opens up.",
            )
            rendered_menu = render_main_menu_card(False)
            if rendered_menu:
                embed.set_image(url="attachment://main_menu_background.png")
                file = discord.File(rendered_menu, filename="main_menu_background.png")
                await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=True)
            elif MAIN_MENU_BACKGROUND.exists():
                embed.set_image(url="attachment://main_menu_background.png")
                file = discord.File(MAIN_MENU_BACKGROUND, filename="main_menu_background.png")
                await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=True)
            else:
                await interaction.response.send_message(embed=embed, view=view, ephemeral=True)
            return

        view = MainMenuView(self, interaction.user.id, show_admin=show_admin)
        embed = discord.Embed(title="Rat Rod Racing Bot")
        rendered_menu = render_main_menu_card(show_admin)

        if rendered_menu:
            embed.set_image(url="attachment://main_menu_background.png")
            file = discord.File(rendered_menu, filename="main_menu_background.png")
            await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=True)
        elif MAIN_MENU_BACKGROUND.exists():
            embed.set_image(url="attachment://main_menu_background.png")
            file = discord.File(MAIN_MENU_BACKGROUND, filename="main_menu_background.png")
            await interaction.response.send_message(embed=embed, file=file, view=view, ephemeral=True)
        else:
            embed.description = "Pick a button below to open a tool."
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="status", description="Show your Rat Rod dashboard and current race-night status.")
    async def status(self, interaction: discord.Interaction):
        await self.send_status(interaction)

    async def send_status(self, interaction: discord.Interaction):
        embed = discord.Embed(title="Rat Rod Status", color=discord.Color.dark_gold())
        tournament = await self.bot.db.current_tournament()
        if tournament:
            race_count = await self.bot.db.tournament_race_count(int(tournament["id"]))
            next_track = await self.bot.db.next_scheduled_track(int(tournament["id"]))
            next_text = f"Race {next_track[0]}: `{next_track[1]}`" if next_track else "No scheduled race left"
            embed.add_field(
                name="Current Tournament",
                value=f"**{tournament['name']}**\nRaces run: {race_count}\nNext: {next_text}",
                inline=False,
            )
        else:
            embed.add_field(name="Current Tournament", value="No open tournament.", inline=False)

        team = await self.bot.db.get_team_by_owner(interaction.user.id)
        if team:
            missing = []
            if not team.parts:
                missing.append("parts")
            if not team.crew:
                missing.append("pit crew")
            offers = await self.bot.db.team_sponsor_offers(team.id, limit=3)
            offered = [offer for offer in offers if offer["status"] == "offered"]
            from services.sponsors import sponsor_by_key
            active_sponsor = sponsor_by_key(team.active_sponsor_key)
            embed.add_field(
                name="Your Team",
                value=(
                    f"**#{team.id} {team.name}** - {team.driver_name}\n"
                    f"Setup: {'missing ' + ', '.join(missing) if missing else 'ready'}\n"
                    f"Sponsor: {active_sponsor.name if active_sponsor else 'Independent'}\n"
                    f"Sponsor offers: {len(offered)} waiting"
                ),
                inline=False,
            )
        else:
            embed.add_field(name="Your Team", value="No team yet. Use `/menu` to start.", inline=False)

        recent_races = await self.bot.db.recent_races(limit=3)
        if recent_races:
            embed.add_field(
                name="Recent Races",
                value="\n".join(f"Race #{row['id']} - `{row['track_key']}` - seed `{row['seed']}`" for row in recent_races),
                inline=False,
            )
        if is_admin(interaction):
            teams = await self.bot.db.list_teams()
            open_tournaments = await self.bot.db.list_tournaments(include_closed=False)
            embed.add_field(
                name="Admin Warnings",
                value=f"Teams: {len(teams)}\nOpen tournaments: {len(open_tournaments)}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed, ephemeral=True)

    @app_commands.command(name="version", description="Show the bot version and recent feature notes.")
    async def version(self, interaction: discord.Interaction):
        embed = discord.Embed(
            title="Rat Rod Racing Bot",
            description=f"Version {BOT_VERSION} — Blacktop Racing World",
            color=discord.Color.dark_gold(),
        )
        embed.add_field(
            name="v0.5",
            value=(
                "Persistent `/world` hub connects the full team → garage → setup → race → championship loop\n"
                "Completed seasons now become permanent per-team career history and awards\n"
                "Existing completed seasons are backfilled automatically during upgrade\n"
                "World-story decisions have safe A/B buttons with duplicate-click protection\n"
                "Shared UI error handling prevents silent failed interactions across the bot\n"
                "Progression still expands choices and identity rather than granting automatic victory\n"
                "Full regression tests and the full Balance Lab remain release gates"
            ),
            inline=False,
        )
        await interaction.response.send_message(embed=embed, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(MenuCog(bot))
