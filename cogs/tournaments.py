import random
import logging
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
from services.audit import audit_log
from services.championship import (
    awards_from_history,
    calendar_entries,
    calendar_text,
    championship_hub_embed,
    season_awards_text,
    summary_from_history,
    team_form,
)
from services.media import MediaRegistry
from services.preflight import race_preflight_embed
from services.predictions import PredictionView
from services.race_engine import RaceEngine
from services.race_report import send_race_report
from services.race_rewards import process_race_rewards
from services.race_snapshot import build_replay_snapshot
from services.racing_world import rivalry_heat_map
from services.scrutineering import scrutineering_embed
from services.season_control import (
    build_season_director_snapshot,
    race_results_from_row,
    season_director_embed,
)
from services.story import season_history_lines
from services.streamer import RaceStreamer
from services.team_ids import parse_team_ids_csv
from services.views import ConfirmView, PaginatedTextView
from services.ui_safety import OneShotReliableView, ReliableModal, ReliableView, safe_reply


TOURNAMENT_LENGTHS = {
    "long": ("Long", 10),
    "medium": ("Medium", 7),
    "short": ("Short", 5),
}

TOURNAMENT_AWARDS = (
    ("overtakes", "Overtakes", "🏁"),
    ("crashes", "Crashes", "💥"),
    ("illegal_moves", "Illegal Moves", "🚨"),
    ("last_minute_wins", "Last-Minute Wins", "⏱️"),
    ("near_misses", "Near Misses", "😮"),
    ("pit_stops", "Pit Stops", "🔧"),
    ("carryover_damage", "Carryover Damage", "🩹"),
    ("peak_carryover_damage", "Peak Damage", "🔥"),
)

PODIUM_MEDALS = (
    ("🥇", "Gold Medal"),
    ("🥈", "Silver Medal"),
    ("🥉", "Bronze Medal"),
)

PUBLIC_TOURNAMENT_COMMANDS = {
    "championship",
    "tournament_standings",
    "tournament_stats",
    "tournament_schedule",
    "season_history",
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


def _award_line(rows, stat_key: str, label: str, emoji: str) -> str:
    leaders = sorted(
        rows,
        key=lambda row: (-int(row[stat_key]), -int(row["points"]), str(row["name"])),
    )
    if not leaders or int(leaders[0][stat_key]) <= 0:
        return f"{emoji} **{label}:** No award this time."

    winner = leaders[0]
    return f"{emoji} **{label}:** {winner['name']} - {winner[stat_key]}"


def tournament_stats_embed(tournament, rows) -> discord.Embed:
    embed = discord.Embed(title=f"Tournament Stats: {tournament['name']}")
    standings = [
        f"**{index}. {row['name']}** - {row['points']} pts | W {row['wins']} | Podiums {row['podiums']} | "
        f"FL {row['fastest_laps']} | DNF {row['dnfs']} | DSQ {row['disqualifications']}"
        for index, row in enumerate(rows, start=1)
    ]
    embed.add_field(name="Points Table", value="\n".join(standings[:10])[:1024], inline=False)
    embed.add_field(name="Overtakes", value=_leader_lines(rows, "overtakes", "overtakes"), inline=True)
    embed.add_field(name="Crashes", value=_leader_lines(rows, "crashes", "crashes"), inline=True)
    embed.add_field(name="Illegal Moves", value=_leader_lines(rows, "illegal_moves", "moves"), inline=True)
    embed.add_field(name="Last-Minute Wins", value=_leader_lines(rows, "last_minute_wins", "wins"), inline=True)
    embed.add_field(name="Near Misses", value=_leader_lines(rows, "near_misses", "saves"), inline=True)
    embed.add_field(name="Pit Stops", value=_leader_lines(rows, "pit_stops", "stops"), inline=True)
    embed.add_field(name="Carryover Damage", value=_leader_lines(rows, "carryover_damage", "damage"), inline=True)
    embed.add_field(name="Peak Damage", value=_leader_lines(rows, "peak_carryover_damage", "peak"), inline=True)
    return embed


def tournament_final_embed(tournament, rows, history=None) -> discord.Embed:
    embed = discord.Embed(
        title=f"Final Results: {tournament['name']}",
        description="The tournament is complete. Here is the final podium and chaos board.",
    )
    podium_lines = []
    for index, row in enumerate(rows[:3], start=1):
        medal, medal_label = PODIUM_MEDALS[index - 1]
        podium_lines.append(
            f"{medal} **{medal_label}** - **{row['name']}** ({row['driver_name']}) - {row['points']} pts"
        )
    embed.add_field(
        name="Top 3 Racers",
        value="\n".join(podium_lines) if podium_lines else "No racers finished.",
        inline=False,
    )

    placement_lines = [
        f"**{index}.** {row['name']} - {row['points']} pts"
        for index, row in enumerate(rows[3:10], start=4)
    ]
    embed.add_field(
        name="4th-10th Place",
        value="\n".join(placement_lines) if placement_lines else "No other racers placed.",
        inline=False,
    )

    season_awards = awards_from_history(history) if history else []
    if season_awards:
        embed.add_field(name="Season Awards", value=season_awards_text(season_awards)[:1024], inline=False)
    chaos_lines = [_award_line(rows, stat_key, label, emoji) for stat_key, label, emoji in TOURNAMENT_AWARDS]
    embed.add_field(name="Chaos Board", value="\n".join(chaos_lines), inline=False)
    if history:
        summary = summary_from_history(history)
        if summary:
            status = str(summary.get("season_status", "complete")).title()
            embed.add_field(
                name="Season Summary",
                value=(
                    f"Status: **{status}** | Championship races: **{summary.get('championship_races', 0)}**\n"
                    f"Overtakes: **{summary.get('total_overtakes', 0)}** | Crashes: **{summary.get('total_crashes', 0)}** | "
                    f"DNFs: **{summary.get('total_dnfs', 0)}** | DSQs: **{summary.get('total_disqualifications', 0)}**"
                ),
                inline=False,
            )
    embed.set_footer(text="Final tournament report")
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


class TournamentNameModal(ReliableModal):
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


class TournamentWizardView(OneShotReliableView):
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
        if not self.begin_once():
            await safe_reply(interaction, "Tournament creation is already being processed. No duplicate season was created.")
            return

        try:
            tournament_id = await self.cog.bot.db.create_tournament_with_grid(
                self.state.name or "",
                self.state.selected_team_ids,
                self.state.track_keys,
            )
        except Exception as exc:
            self._action_started = False
            await safe_reply(interaction, f"Tournament not created: {exc}")
            return

        self._disable()
        await interaction.response.edit_message(
            content=f"Created {self.state.length_label.lower()} tournament **{self.state.name}** as ID `{tournament_id}`.",
            embed=self.embed(),
            view=self,
        )


class CorrectResultTeamSelect(discord.ui.Select):
    def __init__(self, correction_view: "SeasonCorrectResultView"):
        self.correction_view = correction_view
        options = [
            discord.SelectOption(
                label=f"P{row.get('position', '?')} · {str(row.get('team_name', 'Team'))}"[:100],
                value=str(row.get("team_id")),
                description=str(row.get("driver_name", ""))[:100] or None,
                default=correction_view.team_id == int(row.get("team_id", 0)),
            )
            for row in correction_view.results[:25]
            if int(row.get("team_id", 0)) > 0
        ]
        super().__init__(placeholder="Choose team to correct", options=options, row=0)

    async def callback(self, interaction: discord.Interaction):
        self.correction_view.team_id = int(self.values[0])
        current = next(
            (row for row in self.correction_view.results if int(row.get("team_id", 0)) == self.correction_view.team_id),
            None,
        )
        if current:
            self.correction_view.new_position = int(current.get("position", 1))
        self.correction_view.rebuild()
        await interaction.response.edit_message(embed=self.correction_view.embed(), view=self.correction_view)


class CorrectResultPositionSelect(discord.ui.Select):
    def __init__(self, correction_view: "SeasonCorrectResultView"):
        self.correction_view = correction_view
        options = [
            discord.SelectOption(
                label=f"P{position}",
                value=str(position),
                default=correction_view.new_position == position,
            )
            for position in range(1, len(correction_view.results) + 1)
        ]
        super().__init__(placeholder="Corrected finishing position", options=options, row=1)

    async def callback(self, interaction: discord.Interaction):
        self.correction_view.new_position = int(self.values[0])
        self.correction_view.rebuild()
        await interaction.response.edit_message(embed=self.correction_view.embed(), view=self.correction_view)


class CorrectResultStatusSelect(discord.ui.Select):
    def __init__(self, correction_view: "SeasonCorrectResultView"):
        self.correction_view = correction_view
        labels = (
            ("keep", "Keep current status"),
            ("finish", "Official finisher"),
            ("dnf", "DNF"),
            ("dsq", "Disqualified"),
        )
        options = [
            discord.SelectOption(label=label, value=value, default=correction_view.status == value)
            for value, label in labels
        ]
        super().__init__(placeholder="Corrected race status", options=options, row=2)

    async def callback(self, interaction: discord.Interaction):
        self.correction_view.status = self.values[0]
        self.correction_view.rebuild()
        await interaction.response.edit_message(embed=self.correction_view.embed(), view=self.correction_view)


class SeasonCorrectResultView(ReliableView):
    def __init__(self, cog: "TournamentsCog", owner_id: int, tournament_id: int, race_row):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.tournament_id = int(tournament_id)
        self.race_row = race_row
        self.results = sorted(
            race_results_from_row(race_row),
            key=lambda row: int(row.get("position", 999)),
        )
        self.team_id: int | None = None
        self.new_position = 1
        self.status = "keep"
        self.rebuild()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This result-correction panel belongs to another admin.", ephemeral=True)
        return False

    def rebuild(self) -> None:
        self.clear_items()
        self.add_item(CorrectResultTeamSelect(self))
        self.add_item(CorrectResultPositionSelect(self))
        self.add_item(CorrectResultStatusSelect(self))
        apply_button = discord.ui.Button(
            label="Review Correction",
            style=discord.ButtonStyle.danger,
            row=3,
            disabled=self.team_id is None,
        )
        apply_button.callback = self.review
        self.add_item(apply_button)
        cancel = discord.ui.Button(label="Cancel", style=discord.ButtonStyle.secondary, row=3)
        cancel.callback = self.cancel
        self.add_item(cancel)

    def embed(self) -> discord.Embed:
        race_id = int(self.race_row["id"])
        selected = next(
            (row for row in self.results if int(row.get("team_id", 0)) == int(self.team_id or 0)),
            None,
        )
        current = (
            f"P{selected.get('position')} · {selected.get('team_name')}"
            if selected else "Choose a team"
        )
        embed = discord.Embed(
            title=f"Correct Championship Result — Race #{race_id}",
            description=(
                "Correction rebuilds the latest persisted race from its pre-race checkpoint, "
                "then reapplies standings and progression exactly once."
            ),
            color=discord.Color.red(),
        )
        embed.add_field(name="Selected", value=current, inline=False)
        embed.add_field(name="New Position", value=f"P{self.new_position}", inline=True)
        embed.add_field(name="Status", value=self.status.upper(), inline=True)
        embed.set_footer(text="Only the latest recoverable persisted race can be corrected safely.")
        return embed

    async def review(self, interaction: discord.Interaction) -> None:
        if self.team_id is None:
            await interaction.response.send_message("Choose a team first.", ephemeral=True)
            return
        race_id = int(self.race_row["id"])

        async def apply(confirm_interaction: discord.Interaction):
            snapshot = await self.cog.bot.race_activity.snapshot()
            if snapshot["active_team_ids"] or snapshot["lobby_team_ids"]:
                await confirm_interaction.response.edit_message(
                    content="Correction is blocked while a race or lobby is active.",
                    embed=None,
                    view=None,
                )
                return
            try:
                result = await self.cog.bot.recovery.correct_latest_result(
                    race_id,
                    int(self.team_id),
                    int(self.new_position),
                    self.status,
                )
            except Exception as exc:
                await confirm_interaction.response.edit_message(
                    content=f"Result was not corrected: {exc}",
                    embed=None,
                    view=None,
                )
                return
            round_number = self.race_row["schedule_race_number"]
            if round_number is not None:
                await self.cog.bot.db.mark_season_race_state(
                    self.tournament_id,
                    int(round_number),
                    str(self.race_row["track_key"]),
                    race_id=race_id,
                    phase="corrected",
                    race_simulated=True,
                    standings_updated=True,
                    rewards_processed=True,
                    gazette_generated=False,
                    error_text="Official result corrected; Gazette image reflects the pre-correction result until regenerated.",
                )
            await audit_log(
                self.cog.bot,
                "Season Result Corrected",
                f"Tournament #{self.tournament_id} race #{race_id}: team #{self.team_id} -> P{self.new_position} {self.status}",
                confirm_interaction.user,
            )
            await confirm_interaction.response.edit_message(
                content=(
                    f"Race #{race_id} corrected safely. Standings/progression were rebuilt. "
                    "Season Director now flags the Gazette as needing regeneration."
                ),
                embed=None,
                view=None,
            )

        confirm = ConfirmView(
            interaction.user.id,
            "Correct Championship Result",
            apply,
        )
        await interaction.response.send_message(
            content=(
                f"Confirm correction of Race #{race_id}: team #{self.team_id} → "
                f"P{self.new_position}, status **{self.status.upper()}**?"
            ),
            view=confirm,
            ephemeral=True,
        )

    async def cancel(self, interaction: discord.Interaction) -> None:
        self._disable()
        await interaction.response.edit_message(content="Result correction cancelled.", embed=None, view=self)


class SeasonDirectorView(ReliableView):
    def __init__(self, cog: "TournamentsCog", owner_id: int, snapshot: dict):
        super().__init__(timeout=900)
        self.cog = cog
        self.owner_id = owner_id
        self.snapshot = snapshot
        self.tournament_id = int(snapshot["tournament"]["id"])
        self.rebuild()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This Season Director belongs to another admin.", ephemeral=True)
        return False

    def rebuild(self) -> None:
        self.clear_items()
        status = str(self.snapshot["tournament"]["status"])
        next_entry = self.snapshot["next_entry"]
        scoring_races = sum(
            1 for race in self.snapshot["races"] if int(race["championship_round"]) == 1
        )

        controls = [
            ("start_next", "▶ Start Next Race", discord.ButtonStyle.success, 0, status != "open" or next_entry is None),
            ("correct", "🛠 Correct Result", discord.ButtonStyle.secondary, 0, not self.snapshot["races"]),
            ("refresh", "↻ Refresh", discord.ButtonStyle.primary, 0, False),
            ("pause", "⏸ Pause Season", discord.ButtonStyle.secondary, 1, status != "open"),
            ("resume", "▶ Resume Season", discord.ButtonStyle.success, 1, status != "paused"),
            ("cancel_empty", "🛑 Cancel Empty", discord.ButtonStyle.danger, 1, status not in {"open", "paused"} or scoring_races > 0),
            ("end", "🏁 End Season", discord.ButtonStyle.danger, 2, status not in {"open", "paused"} or scoring_races == 0),
            ("reopen", "♻ Reopen Season", discord.ButtonStyle.danger, 2, status not in {"closed", "cancelled"}),
            ("championship", "🏆 Championship Hub", discord.ButtonStyle.secondary, 2, False),
        ]
        for key, label, style, row, disabled in controls:
            button = discord.ui.Button(label=label, style=style, row=row, disabled=disabled)
            button.callback = self._callback(key)
            self.add_item(button)

    def _callback(self, key: str):
        async def callback(interaction: discord.Interaction):
            handler = getattr(self, f"handle_{key}")
            await handler(interaction)
        return callback

    async def refresh_snapshot(self) -> None:
        self.snapshot = await build_season_director_snapshot(self.cog.bot.db, self.tournament_id)
        self.rebuild()

    async def handle_refresh(self, interaction: discord.Interaction) -> None:
        await self.refresh_snapshot()
        await interaction.response.edit_message(embed=season_director_embed(self.snapshot), view=self)

    async def handle_start_next(self, interaction: discord.Interaction) -> None:
        await self.refresh_snapshot()
        if str(self.snapshot["tournament"]["status"]) != "open":
            await interaction.response.send_message("Resume the season before starting another round.", ephemeral=True)
            return
        next_entry = self.snapshot["next_entry"]
        if not next_entry:
            await interaction.response.send_message("No scheduled round remains.", ephemeral=True)
            return
        team_ids = await self.cog.bot.db.tournament_team_ids(self.tournament_id)
        await self.cog.send_tournament_preflight(
            interaction,
            self.tournament_id,
            str(next_entry["track_key"]),
            team_ids,
            title_prefix=f"Scheduled Race {int(next_entry['race_number'])}",
            post_final_awards=int(next_entry["race_number"]) == int(self.snapshot["total_rounds"]),
            schedule_race_number=int(next_entry["race_number"]),
        )

    async def handle_correct(self, interaction: discord.Interaction) -> None:
        races = await self.cog.bot.db.tournament_races(self.tournament_id, championship_only=True)
        if not races:
            await interaction.response.send_message("No championship result exists to correct.", ephemeral=True)
            return
        race_row = races[-1]
        latest = await self.cog.bot.recovery.latest_race()
        if not latest or int(latest["id"]) != int(race_row["id"]):
            await interaction.response.send_message(
                "The latest championship race is not the latest persisted race, so conservative recovery will not rewrite it. "
                "Correct the latest race first or use recovery tools after reviewing the intervening race.",
                ephemeral=True,
            )
            return
        view = SeasonCorrectResultView(self.cog, interaction.user.id, self.tournament_id, race_row)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    async def handle_pause(self, interaction: discord.Interaction) -> None:
        activity = await self.cog.bot.race_activity.snapshot()
        if self.tournament_id in set(activity["active_tournament_ids"]):
            await interaction.response.send_message("The season cannot be paused while its race is active.", ephemeral=True)
            return
        try:
            await self.cog.bot.db.pause_tournament(self.tournament_id)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await audit_log(self.cog.bot, "Season Paused", f"Tournament #{self.tournament_id}", interaction.user)
        await self.refresh_snapshot()
        await interaction.response.edit_message(embed=season_director_embed(self.snapshot), view=self)

    async def handle_resume(self, interaction: discord.Interaction) -> None:
        try:
            await self.cog.bot.db.resume_tournament(self.tournament_id)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await audit_log(self.cog.bot, "Season Resumed", f"Tournament #{self.tournament_id}", interaction.user)
        await self.refresh_snapshot()
        await interaction.response.edit_message(embed=season_director_embed(self.snapshot), view=self)

    async def handle_cancel_empty(self, interaction: discord.Interaction) -> None:
        async def cancel(confirm_interaction: discord.Interaction):
            try:
                outcome = await self.cog.bot.db.close_tournament(self.tournament_id)
            except ValueError as exc:
                await confirm_interaction.response.edit_message(content=str(exc), embed=None, view=None)
                return
            await audit_log(self.cog.bot, "Season Cancelled", f"Tournament #{self.tournament_id}", confirm_interaction.user)
            await confirm_interaction.response.edit_message(
                content=f"Season #{self.tournament_id} {outcome}. No scoring history was created.",
                embed=None,
                view=None,
            )

        await interaction.response.send_message(
            content="Cancel this empty season? This removes it from the active racing world but preserves its administrative record.",
            view=ConfirmView(interaction.user.id, "Cancel Empty Season", cancel),
            ephemeral=True,
        )

    async def handle_end(self, interaction: discord.Interaction) -> None:
        activity = await self.cog.bot.race_activity.snapshot()
        if self.tournament_id in set(activity["active_tournament_ids"]):
            await interaction.response.send_message("The season cannot end while its race is active.", ephemeral=True)
            return

        async def end(confirm_interaction: discord.Interaction):
            try:
                outcome = await self.cog.bot.db.close_tournament(self.tournament_id)
            except ValueError as exc:
                await confirm_interaction.response.edit_message(content=str(exc), embed=None, view=None)
                return
            await audit_log(self.cog.bot, "Season Ended", f"Tournament #{self.tournament_id}", confirm_interaction.user)
            await confirm_interaction.response.edit_message(
                content=f"Season #{self.tournament_id} {outcome}. Final standings and permanent history are now frozen.",
                embed=None,
                view=None,
            )

        completed = int(self.snapshot["completed_rounds"])
        total = int(self.snapshot["total_rounds"])
        warning = (
            f" This is a shortened season ({completed}/{total} scheduled rounds complete)."
            if total and completed < total else ""
        )
        await interaction.response.send_message(
            content=f"End this championship and freeze Season History?{warning}",
            view=ConfirmView(interaction.user.id, "End Season", end),
            ephemeral=True,
        )

    async def handle_reopen(self, interaction: discord.Interaction) -> None:
        async def reopen(confirm_interaction: discord.Interaction):
            activity = await self.cog.bot.race_activity.snapshot()
            if activity["active_team_ids"] or activity["lobby_team_ids"]:
                await confirm_interaction.response.edit_message(
                    content="Reopen is blocked while any race or lobby is active.",
                    embed=None,
                    view=None,
                )
                return
            try:
                result = await self.cog.bot.recovery.restore_tournament(self.tournament_id)
            except Exception as exc:
                await confirm_interaction.response.edit_message(
                    content=f"Season was not reopened: {exc}",
                    embed=None,
                    view=None,
                )
                return
            await audit_log(self.cog.bot, "Season Reopened", f"Tournament #{self.tournament_id}", confirm_interaction.user)
            await confirm_interaction.response.edit_message(
                content=(
                    f"**{result['name']}** reopened safely. Its frozen Season History snapshot was removed "
                    "until the season is ended again."
                ),
                embed=None,
                view=None,
            )

        await interaction.response.send_message(
            content=(
                "Reopen this finished season? A safety backup will be created and its frozen Season History "
                "will be removed until the championship is closed again."
            ),
            view=ConfirmView(interaction.user.id, "Reopen Season", reopen),
            ephemeral=True,
        )

    async def handle_championship(self, interaction: discord.Interaction) -> None:
        standings = await self.cog.bot.db.standings(self.tournament_id)
        schedule = await self.cog.bot.db.tournament_schedule(self.tournament_id)
        races = await self.cog.bot.db.tournament_races(self.tournament_id)
        rivalries = await self.cog.bot.db.tournament_rivalries(self.tournament_id, limit=5)
        tournament = await self.cog.bot.db.get_tournament(self.tournament_id)
        await interaction.response.send_message(
            embed=championship_hub_embed(tournament, standings, schedule, races, rivalries),
            ephemeral=True,
        )


class TournamentsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.media = MediaRegistry()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        command_name = getattr(getattr(interaction, "command", None), "name", "")
        if command_name in PUBLIC_TOURNAMENT_COMMANDS:
            return True
        if is_admin(interaction):
            return True
        await deny_admin_only(interaction)
        return False

    async def _send_private(self, interaction: discord.Interaction, message: str) -> None:
        if interaction.response.is_done():
            await interaction.followup.send(message, ephemeral=True)
        else:
            await interaction.response.send_message(message, ephemeral=True)

    async def send_season_director(
        self,
        interaction: discord.Interaction,
        tournament_id: int | None = None,
    ) -> None:
        tournament = (
            await self.bot.db.get_tournament(int(tournament_id))
            if tournament_id is not None
            else await self.bot.db.current_tournament()
        )
        if not tournament and tournament_id is None:
            recent = await self.bot.db.list_tournaments(include_closed=True, limit=1)
            tournament = recent[0] if recent else None
        if not tournament:
            await self._send_private(interaction, "No championship exists yet.")
            return
        snapshot = await build_season_director_snapshot(self.bot.db, int(tournament["id"]))
        view = SeasonDirectorView(self, interaction.user.id, snapshot)
        if interaction.response.is_done():
            await interaction.followup.send(embed=season_director_embed(snapshot), view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=season_director_embed(snapshot), view=view, ephemeral=True)

    async def send_tournament_preflight(
        self,
        interaction: discord.Interaction,
        tournament_id: int,
        track_key: str,
        team_ids: list[int],
        seed: str | None = None,
        *,
        title_prefix: str = "Tournament Race",
        post_final_awards: bool = False,
        schedule_race_number: int | None = None,
    ) -> None:
        tournament = await self.bot.db.get_tournament(tournament_id)
        if not tournament:
            await self._send_private(interaction, "Tournament not found.")
            return
        if tournament["status"] != "open":
            await self._send_private(interaction, "That championship is not open for racing. Resume it in Season Director if it is paused.")
            return
        try:
            await self.bot.db.require_full_tournament_grid(tournament_id)
        except ValueError as exc:
            await self._send_private(interaction, str(exc))
            return
        teams = []
        tournament_ids = set(await self.bot.db.tournament_team_ids(tournament_id))
        requested_ids = [int(team_id) for team_id in team_ids]
        if len(requested_ids) != 10 or set(requested_ids) != tournament_ids:
            await self._send_private(interaction, "Tournament races must use all 10 entered teams exactly once.")
            return
        for team_id in requested_ids:
            team = await self.bot.db.get_team(team_id)
            if team:
                teams.append(team)
        if len(teams) != 10:
            await self._send_private(interaction, "Tournament grid is incomplete; all 10 entered teams must exist.")
            return
        carryover_damage = await self.bot.db.tournament_carryover_damage(tournament_id)
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
            await audit_log(self.bot, "Tournament Race Started", f"Tournament #{tournament_id} at {TRACKS[track_key].name} seed {seed}", confirm_interaction.user)
            await confirm_interaction.response.edit_message(content="Tournament race confirmed. Posting to channel now.", embed=None, view=None)
            await self._run_tournament_race(
                confirm_interaction,
                tournament_id,
                track_key,
                team_ids,
                seed,
                title_prefix=title_prefix,
                post_final_awards=post_final_awards,
                schedule_race_number=schedule_race_number,
            )

        view = ConfirmView(interaction.user.id, "Start Tournament Race", run)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    async def _run_tournament_race(
        self,
        interaction: discord.Interaction,
        tournament_id: int,
        track_key: str,
        team_ids: list[int],
        seed: str | None = None,
        title_prefix: str = "Tournament Race",
        post_final_awards: bool = False,
        schedule_race_number: int | None = None,
    ) -> None:
        tournament = await self.bot.db.get_tournament(tournament_id)
        if not tournament or tournament["status"] != "open":
            await self._send_private(interaction, "That tournament is closed or no longer exists.")
            return
        try:
            await self.bot.db.require_full_tournament_grid(tournament_id)
        except ValueError as exc:
            await self._send_private(interaction, str(exc))
            return

        tournament_ids = set(await self.bot.db.tournament_team_ids(tournament_id))
        requested_ids = [int(team_id) for team_id in team_ids]
        if len(requested_ids) != 10 or set(requested_ids) != tournament_ids:
            await self._send_private(interaction, "Tournament races must use all 10 entered teams exactly once.")
            return
        teams = []
        for team_id in requested_ids:
            team = await self.bot.db.get_team(team_id)
            if team:
                teams.append(team)
        if len(teams) != 10:
            await self._send_private(interaction, "Tournament grid is incomplete; all 10 entered teams must exist.")
            return

        reservation = await self.bot.race_activity.reserve_race(requested_ids, tournament_id=tournament_id)
        if reservation is None:
            await self._send_private(interaction, "Tournament race cannot start because the tournament or one of its teams is already active elsewhere.")
            return

        try:
            carryover_damage = await self.bot.db.tournament_carryover_damage(tournament_id)
            active_rivalry_heat = await rivalry_heat_map(self.bot.db, requested_ids)
            damaged_teams = [team for team in teams if carryover_damage.get(team.id or 0, 0) > 0]
            damage_note = f" {len(damaged_teams)} team(s) are carrying repaired damage." if damaged_teams else ""
            engine = RaceEngine(
                track_key,
                teams,
                seed,
                initial_damage_by_team_id=carryover_damage,
                rivalry_heat_by_pair=active_rivalry_heat,
            )
            await self._send_private(interaction, "Tournament race is starting in the channel.")
            await interaction.channel.send(
                f"Tournament race started: **{TRACKS[track_key].name}** with {len(teams)} teams. "
                f"Weather: **{engine.weather.name}**.{damage_note}"
            )
            await interaction.channel.send(
                embed=scrutineering_embed(
                    teams,
                    title=f"Pre-Race Scrutineering: {TRACKS[track_key].name}",
                    weather=engine.weather,
                    carryover_damage=carryover_damage,
                )
            )
            predictions = PredictionView(teams)
            prediction_message = await interaction.channel.send(embed=predictions.embed(TRACKS[track_key].name), view=predictions)
            await predictions.wait()
            await prediction_message.edit(embed=predictions.embed(TRACKS[track_key].name), view=predictions)

            tournament = await self.bot.db.get_tournament(tournament_id)
            if not tournament or tournament["status"] != "open":
                await interaction.channel.send("Tournament closed before the green flag. This race was cancelled.")
                return

            events, results, used_seed = engine.run()
            result_dicts = RaceEngine.results_to_dicts(results)
            if schedule_race_number is not None:
                await self.bot.db.mark_season_race_state(
                    tournament_id,
                    int(schedule_race_number),
                    track_key,
                    phase="simulated",
                    race_simulated=True,
                    error_text="",
                )
            reward_embeds: list[discord.Embed] = []
            async with self.bot.recovery_lock:
                checkpoint_token = await self.bot.recovery.create_race_checkpoint(
                    {
                        "track_key": track_key,
                        "laps": engine.laps,
                        "team_ids": requested_ids,
                        "tournament_id": tournament_id,
                        "schedule_race_number": schedule_race_number,
                        "seed": used_seed,
                    }
                )
                replay_data = build_replay_snapshot(
                    teams,
                    laps=engine.laps,
                    initial_damage_by_team_id=carryover_damage,
                    weather_key=engine.weather.key,
                    rng_state=engine.initial_rng_state,
                    rivalry_heat_by_pair=active_rivalry_heat,
                )
                try:
                    race_id = await self.bot.db.save_tournament_race(
                        tournament_id,
                        track_key,
                        used_seed,
                        RaceEngine.events_to_dicts(events),
                        result_dicts,
                        replay_data=replay_data,
                        schedule_race_number=schedule_race_number,
                    )
                except ValueError as exc:
                    await interaction.channel.send(f"Tournament race was not saved: {exc}")
                    return
                self.bot.recovery.bind_race_checkpoint(checkpoint_token, race_id)
                await self.bot.recovery.mark_presentation(race_id, -1, "saved")
                if schedule_race_number is not None:
                    await self.bot.db.mark_season_race_state(
                        tournament_id,
                        int(schedule_race_number),
                        track_key,
                        race_id=race_id,
                        phase="standings_updated",
                        race_simulated=True,
                        standings_updated=True,
                        error_text="",
                    )
                result_title = f"{title_prefix} #{race_id} Results"
                try:
                    reward_embeds = await process_race_rewards(
                        self.bot.db,
                        track_key,
                        race_id,
                        teams,
                        results,
                        events,
                        engine.weather.name,
                        result_title,
                        engine.laps,
                    )
                    if schedule_race_number is not None:
                        await self.bot.db.mark_season_race_state(
                            tournament_id,
                            int(schedule_race_number),
                            track_key,
                            race_id=race_id,
                            phase="rewards_processed",
                            race_simulated=True,
                            standings_updated=True,
                            rewards_processed=True,
                            error_text="",
                        )
                except Exception:
                    logging.exception("Tournament post-race processing failed for race %s; restoring checkpoint", race_id)
                    await self.bot.recovery.undo_last_race()
                    raise

            if schedule_race_number is None and await self.bot.db.tournament_schedule(tournament_id):
                await interaction.channel.send(
                    "🏁 **Exhibition result:** this race is saved for history, but it does not change championship points, "
                    "fastest-lap totals, carryover damage, or the scheduled round count."
                )

            stream_error = None
            try:
                await self.bot.recovery.mark_presentation(race_id, -1, "streaming")

                async def progress_callback(index: int) -> None:
                    await self.bot.recovery.mark_presentation(race_id, index, "streaming")

                await RaceStreamer(self.media, self.bot.settings.race_tick_seconds).stream(
                    interaction.channel,
                    events,
                    progress_callback=progress_callback,
                )
                await self.bot.recovery.mark_presentation(race_id, len(events) - 1, "complete")
            except (discord.HTTPException, OSError) as exc:
                stream_error = exc
                state = await self.bot.recovery.presentation_state(race_id)
                last_index = int(state["last_event_index"]) if state else -1
                await self.bot.recovery.mark_presentation(race_id, last_index, "interrupted")
                logging.exception("Tournament race streaming failed for race %s", race_id)

            report_error = None
            try:
                report_state = await send_race_report(
                    channel=interaction.channel,
                    db=self.bot.db,
                    track_key=track_key,
                    race_id=race_id,
                    teams=teams,
                    results=results,
                    events=events,
                    weather_name=engine.weather.name,
                    title=result_title,
                    race_laps=engine.laps,
                    predictions=predictions,
                    rivalry_watch=None,
                    award_rewards=False,
                    reward_embeds_override=reward_embeds,
                    persisted_report=True,
                    championship_race=schedule_race_number is not None,
                )
                if schedule_race_number is not None:
                    gazette_ok = bool(report_state.get("gazette_generated"))
                    await self.bot.db.mark_season_race_state(
                        tournament_id,
                        int(schedule_race_number),
                        track_key,
                        race_id=race_id,
                        phase="complete" if gazette_ok else "report_fallback",
                        race_simulated=True,
                        standings_updated=True,
                        rewards_processed=True,
                        gazette_generated=gazette_ok,
                        error_text="" if gazette_ok else "Gazette image unavailable; fallback Discord report posted.",
                    )
            except (discord.HTTPException, OSError) as exc:
                report_error = exc
                logging.exception("Tournament race report delivery failed for race %s", race_id)
                if schedule_race_number is not None:
                    await self.bot.db.mark_season_race_state(
                        tournament_id,
                        int(schedule_race_number),
                        track_key,
                        race_id=race_id,
                        phase="report_error",
                        race_simulated=True,
                        standings_updated=True,
                        rewards_processed=True,
                        gazette_generated=False,
                        error_text=f"Race report delivery failed: {exc}",
                    )

            # The final scheduled result closes the championship even if Discord cannot
            # deliver the live report. The database is the source of truth.
            if post_final_awards:
                try:
                    await self._post_final_awards(interaction.channel, tournament_id)
                except (discord.HTTPException, OSError):
                    logging.exception("Final tournament awards could not be delivered for tournament %s", tournament_id)

            if stream_error or report_error:
                try:
                    await interaction.channel.send("Some race presentation messages could not be posted, but the saved result and progression were completed safely.")
                except discord.HTTPException:
                    pass
        finally:
            await self.bot.race_activity.release(reservation)

    async def _post_final_awards(self, channel, tournament_id: int) -> None:
        try:
            rows = await self.bot.db.finalize_tournament(tournament_id)
        except ValueError:
            return
        tournament = await self.bot.db.get_tournament(tournament_id)
        if not tournament or not rows:
            return

        history = await self.bot.db.season_history_entry(tournament_id)
        message = await channel.send(embed=tournament_final_embed(tournament, rows, history))
        try:
            await message.pin(reason="Final tournament results")
        except (discord.Forbidden, discord.HTTPException):
            await channel.send("Final results posted, but I could not pin them. Check my channel permissions.")

    @app_commands.command(name="season_director", description="Admin: run the current championship from one control centre.")
    async def season_director(self, interaction: discord.Interaction, tournament_id: int | None = None):
        await self.send_season_director(interaction, tournament_id)

    @app_commands.command(name="tournament_create", description="Create a rat rod tournament.")
    async def tournament_create(self, interaction: discord.Interaction, name: str):
        try:
            tid = await self.bot.db.create_tournament(name)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        await audit_log(self.bot, "Tournament Created", f"#{tid} {name}", interaction.user)
        await interaction.response.send_message(
            f"✅ Tournament **{name}** created as ID `{tid}`. Add 10 teams with `/tournament_add_team`, or use `/tournament_wizard` for the guided setup.",
            ephemeral=True,
        )

    @app_commands.command(name="tournament_wizard", description="Create a tournament with 10 teams and a short, medium, or long track schedule.")
    async def tournament_wizard(self, interaction: discord.Interaction):
        await interaction.response.defer(ephemeral=True)
        current = await self.bot.db.current_tournament()
        if current:
            await interaction.followup.send(
                f"Only one championship can be active at a time. Close **{current['name']}** (#{current['id']}) before creating the next season.",
                ephemeral=True,
            )
            return
        teams = await self.bot.db.list_teams()
        if len(teams) < 10:
            await interaction.followup.send("Create at least 10 race teams before starting a tournament wizard.", ephemeral=True)
            return

        try:
            view = TournamentWizardView(self, interaction.user.id, teams)
        except ValueError as exc:
            await interaction.followup.send(str(exc), ephemeral=True)
            return

        await interaction.followup.send(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(name="tournament_add_team", description="Add a team to a tournament.")
    async def tournament_add_team(self, interaction: discord.Interaction, tournament_id: int, team_id: int):
        t = await self.bot.db.get_tournament(tournament_id)
        team = await self.bot.db.get_team(team_id)
        if not t or not team:
            await interaction.response.send_message("Tournament or team not found.", ephemeral=True)
            return
        if t["status"] != "open":
            await interaction.response.send_message("That tournament is closed and cannot accept teams.", ephemeral=True)
            return
        try:
            await self.bot.db.add_team_to_tournament(tournament_id, team_id)
        except ValueError as exc:
            await interaction.response.send_message(str(exc), ephemeral=True)
            return
        await audit_log(self.bot, "Tournament Team Added", f"Tournament #{tournament_id}: #{team_id} {team.name}", interaction.user)
        await interaction.response.send_message(f"✅ Added **{team.name}** to tournament `{tournament_id}`.", ephemeral=True)

    @app_commands.command(name="tournament_standings", description="Show tournament standings.")
    async def tournament_standings(self, interaction: discord.Interaction, tournament_id: int):
        rows = await self.bot.db.standings(tournament_id)
        if not rows:
            await interaction.response.send_message("No standings yet.", ephemeral=True)
            return
        races = await self.bot.db.tournament_races(tournament_id, championship_only=True)
        lines = []
        for i, r in enumerate(rows, start=1):
            form = " · ".join(team_form(races, int(r["team_id"]), 5)) or "—"
            lines.append(
                f"**{i}. {r['name']}** - {r['points']} pts | W {r['wins']} | Podiums {r['podiums']} | FL {r['fastest_laps']} | "
                f"DNF {r['dnfs']} | DSQ {r['disqualifications']}\n"
                f"Form: `{form}` | Car Dmg {r['carryover_damage']}% | Overtakes {r['overtakes']}"
            )
        view = PaginatedTextView(interaction.user.id, "Tournament Standings", lines, per_page=10)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

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

        await interaction.response.send_message(embed=tournament_stats_embed(tournament, rows), ephemeral=True)

    @app_commands.command(name="season_history", description="Show saved tournament champions and podiums.")
    async def season_history(self, interaction: discord.Interaction):
        rows = await self.bot.db.season_history()
        view = PaginatedTextView(interaction.user.id, "Season History", season_history_lines(rows), per_page=8)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(name="championship", description="Open the current Blacktop Championship Hub.")
    async def championship(self, interaction: discord.Interaction, tournament_id: int | None = None):
        tournament = await self.bot.db.get_tournament(tournament_id) if tournament_id else await self.bot.db.current_tournament()
        if not tournament and tournament_id is None:
            recent = await self.bot.db.list_tournaments(include_closed=True, limit=1)
            tournament = recent[0] if recent else None
        if not tournament:
            await interaction.response.send_message("No championship found.", ephemeral=True)
            return
        tid = int(tournament["id"])
        standings = await self.bot.db.standings(tid)
        schedule = await self.bot.db.tournament_schedule(tid)
        races = await self.bot.db.tournament_races(tid)
        rivalries = await self.bot.db.tournament_rivalries(tid, limit=5)
        await interaction.response.send_message(
            embed=championship_hub_embed(tournament, standings, schedule, races, rivalries),
            ephemeral=True,
        )

    @app_commands.command(name="tournament_start_race", description="Run a tournament race using all 10 entered teams.")
    @app_commands.choices(track_key=TRACK_CHOICES)
    async def tournament_start_race(self, interaction: discord.Interaction, tournament_id: int, track_key: str, team_ids_csv: str | None = None, seed: str | None = None):
        if track_key not in TRACKS:
            await interaction.response.send_message("Unknown track. Use `/race_tracks`.", ephemeral=True)
            return
        tournament = await self.bot.db.get_tournament(tournament_id)
        if not tournament:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        if tournament["status"] != "open":
            await interaction.response.send_message("That championship is not open for racing. Resume it in Season Director if it is paused.", ephemeral=True)
            return
        if team_ids_csv:
            ids = parse_team_ids_csv(team_ids_csv)
        else:
            ids = await self.bot.db.tournament_team_ids(tournament_id)
        schedule = await self.bot.db.tournament_schedule(tournament_id)
        title_prefix = "Exhibition Race" if schedule else "Tournament Race"
        await self.send_tournament_preflight(interaction, tournament_id, track_key, ids, seed, title_prefix=title_prefix)

    @app_commands.command(name="tournament_next_race", description="Run the next race from a tournament's saved track schedule.")
    async def tournament_next_race(self, interaction: discord.Interaction, tournament_id: int, seed: str | None = None):
        tournament = await self.bot.db.get_tournament(tournament_id)
        if not tournament:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        if tournament["status"] != "open":
            await interaction.response.send_message("That championship is not open for racing. Resume it in Season Director if it is paused.", ephemeral=True)
            return

        next_track = await self.bot.db.next_scheduled_track(tournament_id)
        if not next_track:
            await interaction.response.send_message("No scheduled race is left for that tournament.", ephemeral=True)
            return

        race_number, track_key = next_track
        team_ids = await self.bot.db.tournament_team_ids(tournament_id)
        schedule_rows = await self.bot.db.tournament_schedule(tournament_id)
        await self.send_tournament_preflight(
            interaction,
            tournament_id,
            track_key,
            team_ids,
            seed,
            title_prefix=f"Scheduled Race {race_number}",
            post_final_awards=race_number == len(schedule_rows),
            schedule_race_number=race_number,
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

        races = await self.bot.db.tournament_races(tournament_id)
        await interaction.response.send_message(calendar_text(calendar_entries(rows, races)), ephemeral=True)

    @app_commands.command(name="tournament_close", description="Finalise standings, save Season History, and close a tournament.")
    async def tournament_close(self, interaction: discord.Interaction, tournament_id: int):
        tournament = await self.bot.db.get_tournament(tournament_id)
        if not tournament:
            await interaction.response.send_message("Tournament not found.", ephemeral=True)
            return
        if tournament["status"] not in {"open", "paused"}:
            await interaction.response.send_message("That tournament is already closed or cancelled.", ephemeral=True)
            return

        async def close(confirm_interaction: discord.Interaction):
            try:
                outcome = await self.bot.db.close_tournament(tournament_id)
            except ValueError as exc:
                await confirm_interaction.response.edit_message(content=str(exc), embed=None, view=None)
                return
            if outcome == "cancelled":
                await audit_log(self.bot, "Tournament Cancelled", f"#{tournament_id} {tournament['name']} (no scoring races)", confirm_interaction.user)
                await confirm_interaction.response.edit_message(
                    content=f"Tournament `{tournament_id}` had no scoring races, so it was cancelled without creating Season History.",
                    embed=None,
                    view=None,
                )
                return
            await audit_log(self.bot, "Tournament Closed", f"#{tournament_id} {tournament['name']}", confirm_interaction.user)
            await confirm_interaction.response.edit_message(
                content=f"Tournament `{tournament_id}` finalised, saved to Season History, and closed.",
                embed=None,
                view=None,
            )

        schedule = await self.bot.db.tournament_schedule(tournament_id)
        completed = await self.bot.db.tournament_scheduled_race_count(tournament_id)
        scoring_races = await self.bot.db.tournament_championship_race_count(tournament_id)
        close_note = ""
        if scoring_races == 0:
            close_note = (
                "\n\n⚠️ This championship has **no scoring races**. Closing it will cancel the empty/partial season "
                "without creating Season History."
            )
        elif schedule and completed < len(schedule):
            close_note = (
                f"\n\n⚠️ This championship is only **{completed}/{len(schedule)} rounds** complete. "
                "Closing it now will permanently record a **Shortened Season** using the current standings."
            )
        embed = discord.Embed(
            title="Confirm Tournament Close",
            description=f"Close **#{tournament_id} {tournament['name']}**?{close_note}",
            color=discord.Color.red(),
        )
        await interaction.response.send_message(
            embed=embed,
            view=ConfirmView(interaction.user.id, "Close Tournament", close),
            ephemeral=True,
        )

async def setup(bot: commands.Bot):
    await bot.add_cog(TournamentsCog(bot))
