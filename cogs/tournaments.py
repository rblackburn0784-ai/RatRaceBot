import random
from dataclasses import dataclass, field

import discord
from discord import app_commands
from discord.ext import commands

from data.defaults import TRACKS

TRACK_CHOICES = [
    app_commands.Choice(name=f"{track.name} ({key})", value=key)
    for key, track in list(TRACKS.items())[:25]
]
from services.access import deny_admin_only, is_admin
from services.formatting import Embeds
from services.media import MediaRegistry
from services.race_engine import RaceEngine
from services.streamer import RaceStreamer
from services.team_ids import parse_team_ids_csv


TOURNAMENT_LENGTHS = {
    "long": ("Long", 10),
    "medium": ("Medium", 7),
    "short": ("Short", 5),
}


def random_tournament_tracks(track_count: int) -> list[str]:
    if len(TRACKS) < track_count:
        raise ValueError(f"At least {track_count} tracks are needed to build that tournament schedule.")
    return random.sample(list(TRACKS), track_count)


def schedule_text(track_keys: list[str], completed_count: int = 0) -> str:
    lines = []
    for index, track_key in enumerate(track_keys, start=1):
        marker = "Done" if index <= completed_count else "Next" if index == completed_count + 1 else "Queued"
        track_name = TRACKS[track_key].name if track_key in TRACKS else track_key
        lines.append(f"**{index}.** {track_name} (`{track_key}`) - {marker}")
    return "\n".join(lines)


def _leader_lines(rows, stat_key: str, label: str, limit: int = 5) -> str:
    leaders = sorted(rows, key=lambda row: (-int(row[stat_key]), str(row["name"])))[:limit]
    lines = [
        f"**{row['name']}** - {row[stat_key]} {label}"
        for row in leaders
        if int(row[stat_key]) > 0
    ]
    return "\n".join(lines) if lines else "No stats yet."


def tournament_stats_embed(tournament, rows) -> discord.Embed:
    embed = discord.Embed(title=f"Tournament Stats: {tournament['name']}")
    standings = [
        f"**{index}. {row['name']}** - {row['points']} pts | W {row['wins']} | Podiums {row['podiums']} | Races {row['races']}"
        for index, row in enumerate(rows, start=1)
    ]
    embed.add_field(name="Points Table", value="\n".join(standings[:10])[:1024], inline=False)
    embed.add_field(name="Overtakes", value=_leader_lines(rows, "overtakes", "overtakes"), inline=True)
    embed.add_field(name="Crashes", value=_leader_lines(rows, "crashes", "crashes"), inline=True)
    embed.add_field(name="Illegal Moves", value=_leader_lines(rows, "illegal_moves", "moves"), inline=True)
    embed.add_field(name="Last-Minute Wins", value=_leader_lines(rows, "last_minute_wins", "wins"), inline=True)
    embed.add_field(name="Near Misses", value=_leader_lines(rows, "near_misses", "saves"), inline=True)
    embed.add_field(name="Pit Stops", value=_leader_lines(rows, "pit_stops", "stops"), inline=True)
    return embed


@dataclass
class TournamentWizardState:
    name: str | None = None
    selected_team_ids: list[int] = field(default_factory=list)
    length_key: str = "long"
    track_keys: list[str] = field(default_factory=lambda: random_tournament_tracks(10))

    @property
    def ready(self) -> bool:
        return bool(self.name) and len(self.selected_team_ids) == 10

    @property
    def track_count(self) -> int:
        return TOURNAMENT_LENGTHS[self.length_key][1]

    @property
    def length_label(self) -> str:
        return TOURNAMENT_LENGTHS[self.length_key][0]


class TournamentNameModal(discord.ui.Modal):
    def __init__(self, wizard: "TournamentWizardView"):
        super().__init__(title="Tournament Name")
        self.wizard = wizard
        self.name_input = discord.ui.TextInput(
            label="Tournament name",
            default=wizard.state.name or "",
            max_length=80,
        )
        self.add_item(self.name_input)

    async def on_submit(self, interaction: discord.Interaction):
        name = str(self.name_input.value).strip()
        if not name:
            await interaction.response.send_message("The tournament needs a name.", ephemeral=True)
            return

        self.wizard.state.name = name
        await self.wizard.refresh(interaction)


class TournamentTeamSelect(discord.ui.Select):
    def __init__(self, wizard: "TournamentWizardView"):
        self.wizard = wizard
        options = [
            discord.SelectOption(
                label=f"#{team.id} {team.name}"[:100],
                value=str(team.id),
                description=f"{team.driver_name} - {team.car_name}"[:100],
                default=team.id in wizard.state.selected_team_ids,
            )
            for team in wizard.teams[:25]
            if team.id is not None
        ]
        super().__init__(
            placeholder="Choose exactly 10 race teams",
            min_values=1,
            max_values=min(10, len(options)),
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.wizard.state.selected_team_ids = [int(value) for value in self.values]
        selected = set(self.wizard.state.selected_team_ids)
        for option in self.options:
            option.default = int(option.value) in selected
        await self.wizard.refresh(interaction)


class TournamentLengthSelect(discord.ui.Select):
    def __init__(self, wizard: "TournamentWizardView"):
        self.wizard = wizard
        options = [
            discord.SelectOption(
                label=f"{label} - {track_count} races",
                value=key,
                default=wizard.state.length_key == key,
            )
            for key, (label, track_count) in TOURNAMENT_LENGTHS.items()
        ]
        super().__init__(
            placeholder="Choose tournament length",
            min_values=1,
            max_values=1,
            options=options,
        )

    async def callback(self, interaction: discord.Interaction):
        self.wizard.state.length_key = self.values[0]
        self.wizard.state.track_keys = random_tournament_tracks(self.wizard.state.track_count)
        for option in self.options:
            option.default = option.value == self.values[0]
        await self.wizard.refresh(interaction)


class TournamentWizardView(discord.ui.View):
    def __init__(self, cog: "TournamentsCog", owner_id: int, teams):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.teams = teams
        self.teams_by_id = {team.id: team for team in teams if team.id is not None}
        self.state = TournamentWizardState()
        self.add_item(TournamentLengthSelect(self))
        self.add_item(TournamentTeamSelect(self))
        self.update_controls()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This tournament wizard belongs to someone else.", ephemeral=True)
        return False

    def update_controls(self) -> None:
        self.create_tournament.disabled = not self.state.ready

    def embed(self) -> discord.Embed:
        selected_teams = [
            self.teams_by_id[team_id]
            for team_id in self.state.selected_team_ids
            if team_id in self.teams_by_id
        ]
        team_lines = [
            f"`{team.id}` **{team.name}** - {team.driver_name}"
            for team in selected_teams
        ]
        if not team_lines:
            team_lines = ["No teams selected."]

        embed = discord.Embed(title="Create Tournament")
        embed.add_field(name="Name", value=self.state.name or "Not set", inline=False)
        embed.add_field(name="Length", value=f"{self.state.length_label} - {self.state.track_count} races", inline=False)
        embed.add_field(
            name=f"Race Teams ({len(selected_teams)}/10)",
            value="\n".join(team_lines)[:1024],
            inline=False,
        )
        embed.add_field(name="Track Order", value=schedule_text(self.state.track_keys)[:1024], inline=False)
        if len(self.teams) > 25:
            embed.set_footer(text="Showing the first 25 teams in the selector.")
        return embed

    async def refresh(self, interaction: discord.Interaction) -> None:
        self.update_controls()
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Name Tournament", style=discord.ButtonStyle.primary)
    async def name_tournament(self, interaction: discord.Interaction, button: discord.ui.Button):
        await interaction.response.send_modal(TournamentNameModal(self))

    @discord.ui.button(label="Shuffle Tracks", style=discord.ButtonStyle.secondary)
    async def shuffle_tracks(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.state.track_keys = random_tournament_tracks(self.state.track_count)
        await self.refresh(interaction)

    @discord.ui.button(label="Create Tournament", style=discord.ButtonStyle.success)
    async def create_tournament(self, interaction: discord.Interaction, button: discord.ui.Button):
        if not self.state.ready:
            await interaction.response.send_message("Name the tournament and choose exactly 10 teams first.", ephemeral=True)
            return

        try:
            tournament_id = await self.cog.bot.db.create_tournament(self.state.name or "")
            for team_id in self.state.selected_team_ids:
                await self.cog.bot.db.add_team_to_tournament(tournament_id, team_id)
            await self.cog.bot.db.set_tournament_schedule(tournament_id, self.state.track_keys)
        except Exception as exc:
            await interaction.response.send_message(f"Tournament not created: {exc}", ephemeral=True)
            return

        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(
            content=f"Created {self.state.length_label.lower()} tournament **{self.state.name}** as ID `{tournament_id}`.",
            embed=self.embed(),
            view=self,
        )


class TournamentsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.media = MediaRegistry()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_admin(interaction):
            return True
        await deny_admin_only(interaction)
        return False

    async def _run_tournament_race(
        self,
        interaction: discord.Interaction,
        tournament_id: int,
        track_key: str,
        team_ids: list[int],
        seed: str | None = None,
        title_prefix: str = "Tournament Race",
    ) -> None:
        teams = []
        tournament_ids = set(await self.bot.db.tournament_team_ids(tournament_id))
        for team_id in team_ids[:10]:
            if team_id not in tournament_ids:
                continue
            team = await self.bot.db.get_team(team_id)
            if team:
                teams.append(team)
        if len(teams) < 2:
            await interaction.response.send_message("I need at least 2 valid tournament teams, ideally 10.", ephemeral=True)
            return

        await interaction.response.send_message(f"Tournament race started: **{TRACKS[track_key].name}** with {len(teams)} teams.")
        engine = RaceEngine(track_key, teams, seed)
        events, results, used_seed = engine.run()
        result_dicts = RaceEngine.results_to_dicts(results)
        await self.bot.db.apply_race_results(tournament_id, result_dicts)
        race_id = await self.bot.db.save_race(tournament_id, track_key, used_seed, RaceEngine.events_to_dicts(events), result_dicts)
        await RaceStreamer(self.media, self.bot.settings.race_tick_seconds).stream(interaction.channel, events)
        await interaction.channel.send(embed=Embeds.results(results, title=f"{title_prefix} #{race_id} Results"))

    @app_commands.command(name="tournament_create", description="Create a rat rod tournament.")
    async def tournament_create(self, interaction: discord.Interaction, name: str):
        try:
            tid = await self.bot.db.create_tournament(name)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ Tournament **{name}** created as ID `{tid}`. Add 10 teams with `/tournament_add_team`, or use `/tournament_wizard` for the guided setup.")

    @app_commands.command(name="tournament_wizard", description="Create a tournament with 10 teams and a short, medium, or long track schedule.")
    async def tournament_wizard(self, interaction: discord.Interaction):
        teams = await self.bot.db.list_teams()
        if len(teams) < 10:
            await interaction.response.send_message("Create at least 10 race teams before starting a tournament wizard.", ephemeral=True)
            return

        try:
            view = TournamentWizardView(self, interaction.user.id, teams)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return

        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(name="tournament_add_team", description="Add a team to a tournament.")
    async def tournament_add_team(self, interaction: discord.Interaction, tournament_id: int, team_id: int):
        t = await self.bot.db.get_tournament(tournament_id)
        team = await self.bot.db.get_team(team_id)
        if not t or not team:
            await interaction.response.send_message("Tournament or team not found.", ephemeral=True)
            return
        await self.bot.db.add_team_to_tournament(tournament_id, team_id)
        await interaction.response.send_message(f"✅ Added **{team.name}** to tournament `{tournament_id}`.")

    @app_commands.command(name="tournament_standings", description="Show tournament standings.")
    async def tournament_standings(self, interaction: discord.Interaction, tournament_id: int):
        rows = await self.bot.db.standings(tournament_id)
        if not rows:
            await interaction.response.send_message("No standings yet.", ephemeral=True)
            return
        lines = []
        for i, r in enumerate(rows, start=1):
            lines.append(
                f"**{i}. {r['name']}** - {r['points']} pts | W {r['wins']} | Podiums {r['podiums']} | "
                f"Races {r['races']} | Overtakes {r['overtakes']} | Crashes {r['crashes']} | Illegal {r['illegal_moves']}"
            )
        await interaction.response.send_message("\n".join(lines[:30]))

    @app_commands.command(name="tournament_stats", description="Show the current tournament's fun stats.")
    async def tournament_stats(self, interaction: discord.Interaction, tournament_id: int | None = None):
        tournament = await self.bot.db.get_tournament(tournament_id) if tournament_id else await self.bot.db.current_tournament()
        if not tournament:
            await interaction.response.send_message("No current tournament found.", ephemeral=True)
            return

        rows = await self.bot.db.standings(int(tournament["id"]))
        if not rows:
            await interaction.response.send_message("No tournament stats yet.", ephemeral=True)
            return

        await interaction.response.send_message(embed=tournament_stats_embed(tournament, rows))

    @app_commands.command(name="tournament_start_race", description="Run a tournament race. Use selected CSV IDs or next 10 in standings list.")
    @app_commands.choices(track_key=TRACK_CHOICES)
    async def tournament_start_race(self, interaction: discord.Interaction, tournament_id: int, track_key: str, team_ids_csv: str | None = None, seed: str | None = None):
        if track_key not in TRACKS:
            await interaction.response.send_message("Unknown track. Use `/race_tracks`.", ephemeral=True)
            return
        tournament = await self.bot.db.get_tournament(tournament_id)
        if not tournament:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        if team_ids_csv:
            ids = parse_team_ids_csv(team_ids_csv)
        else:
            ids = (await self.bot.db.tournament_team_ids(tournament_id))[:10]
        await self._run_tournament_race(interaction, tournament_id, track_key, ids, seed)

    @app_commands.command(name="tournament_next_race", description="Run the next race from a tournament's saved track schedule.")
    async def tournament_next_race(self, interaction: discord.Interaction, tournament_id: int, seed: str | None = None):
        tournament = await self.bot.db.get_tournament(tournament_id)
        if not tournament:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return

        next_track = await self.bot.db.next_scheduled_track(tournament_id)
        if not next_track:
            await interaction.response.send_message("No scheduled race is left for that tournament.", ephemeral=True)
            return

        race_number, track_key = next_track
        team_ids = await self.bot.db.tournament_team_ids(tournament_id)
        await self._run_tournament_race(
            interaction,
            tournament_id,
            track_key,
            team_ids,
            seed,
            title_prefix=f"Scheduled Race {race_number}",
        )

    @app_commands.command(name="tournament_schedule", description="Show the saved track order for a tournament.")
    async def tournament_schedule(self, interaction: discord.Interaction, tournament_id: int):
        tournament = await self.bot.db.get_tournament(tournament_id)
        if not tournament:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return

        rows = await self.bot.db.tournament_schedule(tournament_id)
        if not rows:
            await interaction.response.send_message("This tournament does not have a saved schedule.", ephemeral=True)
            return

        track_keys = [str(row["track_key"]) for row in rows]
        completed_count = await self.bot.db.tournament_race_count(tournament_id)
        await interaction.response.send_message(schedule_text(track_keys, completed_count))

    @app_commands.command(name="tournament_close", description="Close a tournament.")
    async def tournament_close(self, interaction: discord.Interaction, tournament_id: int):
        await self.bot.db.close_tournament(tournament_id)
        await interaction.response.send_message(f"Tournament `{tournament_id}` closed.")

async def setup(bot: commands.Bot):
    await bot.add_cog(TournamentsCog(bot))
