import asyncio
import json
import logging
import discord
from discord import app_commands
from discord.ext import commands

from data.defaults import TRACKS
from models.domain import Team
from services.access import deny_admin_only, is_admin
from services.ai_teams import ai_teams
from services.formatting import Embeds
from services.media import MediaRegistry
from services.predictions import PredictionView
from services.audit import audit_log
from services.preflight import race_preflight_embed
from services.race_engine import RaceEngine
from services.race_report import send_race_report
from services.race_rewards import process_race_rewards
from services.race_rules import official_podium
from services.race_presentation import classification_embed
from services.race_snapshot import build_replay_snapshot, restore_replay_snapshot, restore_replay_rivalry_heat
from services.racing_world import rivalry_heat_map
from services.scrutineering import scrutineering_embed
from services.streamer import RaceStreamer
from services.team_ids import parse_team_ids_csv
from services.views import ConfirmView, PaginatedTextView
from services.ui_safety import ReliableView

TRACK_CHOICES = [
    app_commands.Choice(name=f"{track.name} ({key})", value=key)
    for key, track in list(TRACKS.items())[:25]
]

LAP_OPTIONS = (5, 7, 10)
RACE_MODES = {
    "full_ai": "Full AI Race",
    "players_only": "Players Only",
    "players_plus_ai": "Players Plus AI",
}
PLAYER_LOBBY_SECONDS = 600
MIN_PLAYER_RACERS = 4
MAX_RACERS = 10

SINGLE_RACE_AWARDS = (
    ("overtakes", "Overtakes", "🏁"),
    ("crashes", "Crashes", "💥"),
    ("illegal_moves", "Illegal Moves", "🚨"),
    ("last_minute_wins", "Last-Minute Wins", "⏱️"),
    ("near_misses", "Near Misses", "😮"),
    ("pit_stops", "Pit Stops", "🔧"),
    ("damage", "Carryover Damage", "🩹"),
    ("damage", "Peak Damage", "🔥"),
)

PODIUM_MEDALS = (
    ("🥇", "Gold Medal"),
    ("🥈", "Silver Medal"),
    ("🥉", "Bronze Medal"),
)


def _single_race_award_line(results, stat_key: str, label: str, emoji: str) -> str:
    leaders = sorted(
        results,
        key=lambda result: (-int(getattr(result, stat_key)), -int(result.points), result.team_name),
    )
    if not leaders or int(getattr(leaders[0], stat_key)) <= 0:
        return f"{emoji} **{label}:** No award this time."

    winner = leaders[0]
    return f"{emoji} **{label}:** {winner.team_name} - {getattr(winner, stat_key)}"


def single_race_final_embed(results, events, title: str) -> discord.Embed:
    embed = classification_embed(results, events, title)
    ordered = sorted(results, key=lambda result: result.position)
    podium_results = official_podium(ordered)
    podium_lines = []
    for index, result in enumerate(podium_results, start=1):
        medal, medal_label = PODIUM_MEDALS[index - 1]
        podium_lines.append(
            f"{medal} **{medal_label}** — **{result.team_name}** ({result.driver_name}) — {result.points} pts"
        )
    if podium_lines:
        embed.add_field(name="Podium", value="\n".join(podium_lines), inline=False)

    award_lines = [
        _single_race_award_line(ordered, stat_key, label, emoji)
        for stat_key, label, emoji in SINGLE_RACE_AWARDS
    ]
    embed.add_field(name="Race Awards", value="\n".join(award_lines), inline=False)
    embed.set_footer(text="v0.4.4 race presentation — official classification")
    return embed


class RaceTrackSelect(discord.ui.Select):
    def __init__(self, wizard: "RaceWizardView"):
        self.wizard = wizard
        options = [
            discord.SelectOption(
                label=track.name,
                value=key,
                description=track.description[:100],
                default=wizard.track_key == key,
            )
            for key, track in list(TRACKS.items())[:25]
        ]
        super().__init__(placeholder="Choose a track", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.wizard.track_key = self.values[0]
        await self.wizard.refresh(interaction)


class RaceLapsSelect(discord.ui.Select):
    def __init__(self, wizard: "RaceWizardView"):
        self.wizard = wizard
        options = [
            discord.SelectOption(label=f"{laps} laps", value=str(laps), default=wizard.laps == laps)
            for laps in LAP_OPTIONS
        ]
        super().__init__(placeholder="Choose race length", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.wizard.laps = int(self.values[0])
        await self.wizard.refresh(interaction)


class RaceModeSelect(discord.ui.Select):
    def __init__(self, wizard: "RaceWizardView"):
        self.wizard = wizard
        options = [
            discord.SelectOption(
                label=label,
                value=value,
                description={
                    "full_ai": "Your team races 9 AI teams.",
                    "players_only": "Players join for 10 minutes, then race if 4+ joined.",
                    "players_plus_ai": "Players join for 10 minutes, then AI fills empty slots.",
                }[value],
                default=wizard.mode == value,
            )
            for value, label in RACE_MODES.items()
        ]
        super().__init__(placeholder="Choose race mode", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        self.wizard.mode = self.values[0]
        await self.wizard.refresh(interaction)


class RaceWizardView(ReliableView):
    def __init__(self, cog: "RacingCog", owner_id: int, owner_team: Team):
        super().__init__(timeout=600)
        self.cog = cog
        self.owner_id = owner_id
        self.owner_team = owner_team
        self.track_key = next(iter(TRACKS))
        self.laps = 5
        self.mode = "full_ai"
        self.add_item(RaceTrackSelect(self))
        self.add_item(RaceLapsSelect(self))
        self.add_item(RaceModeSelect(self))

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id == self.owner_id:
            return True
        await interaction.response.send_message("This race wizard belongs to someone else.", ephemeral=True)
        return False

    def embed(self) -> discord.Embed:
        embed = discord.Embed(title="Single Race Wizard")
        embed.add_field(name="Track", value=TRACKS[self.track_key].name, inline=False)
        embed.add_field(name="Laps", value=f"{self.laps}", inline=True)
        embed.add_field(name="Mode", value=RACE_MODES[self.mode], inline=True)
        embed.add_field(name="Your Team", value=f"#{self.owner_team.id} {self.owner_team.name}", inline=False)
        return embed

    async def refresh(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(embed=self.embed(), view=self)

    @discord.ui.button(label="Start", style=discord.ButtonStyle.success)
    async def start(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.mode != "full_ai":
            team_id = self.owner_team.id or 0
            reserved = await self.cog.bot.race_activity.reserve_lobby_team(team_id)
            if not reserved:
                await interaction.response.send_message(
                    "Your team is already in an active race or another race lobby.",
                    ephemeral=True,
                )
                return

        for item in self.children:
            item.disabled = True

        if self.mode == "full_ai":
            await interaction.response.edit_message(embed=self.embed(), view=self)
            teams = [self.owner_team, *ai_teams(9, f"{interaction.id}-{self.owner_team.id}-{self.track_key}")]
            await self.cog.send_single_race_preflight(
                interaction,
                self.track_key,
                teams,
                f"{self.owner_team.name} vs AI",
                laps=self.laps,
            )
            return

        await interaction.response.edit_message(embed=self.embed(), view=self)
        lobby = PlayerRaceLobbyView(
            self.cog,
            host_user_id=interaction.user.id,
            track_key=self.track_key,
            laps=self.laps,
            mode=self.mode,
            initial_team=self.owner_team,
        )
        message = await interaction.channel.send(embed=lobby.embed(), view=lobby)
        lobby.message = message
        asyncio.create_task(lobby.finish_after_delay())


class PlayerRaceLobbyView(ReliableView):
    def __init__(self, cog: "RacingCog", host_user_id: int, track_key: str, laps: int, mode: str, initial_team: Team):
        super().__init__(timeout=PLAYER_LOBBY_SECONDS + 30)
        self.cog = cog
        self.host_user_id = host_user_id
        self.track_key = track_key
        self.laps = laps
        self.mode = mode
        self.teams_by_user_id = {host_user_id: initial_team}
        self.message: discord.Message | None = None
        self.finished = False

    def embed(self) -> discord.Embed:
        status = "Race lobby closed." if self.finished else "Click the tick button to join. Lobby closes in 10 minutes."
        embed = discord.Embed(
            title=f"Race Lobby: {TRACKS[self.track_key].name}",
            description=(
                f"Mode: **{RACE_MODES[self.mode]}**\n"
                f"Laps: **{self.laps}**\n"
                f"{status}"
            ),
        )
        joined = [
            f"**{team.name}** - {team.driver_name}"
            for team in self.teams_by_user_id.values()
        ]
        embed.add_field(name=f"Racers ({len(joined)}/{MAX_RACERS})", value="\n".join(joined), inline=False)
        if self.mode == "players_only":
            embed.set_footer(text="Players Only needs at least 4 joined teams to start.")
        else:
            embed.set_footer(text="Players Plus AI needs at least 4 joined teams; AI fills the remaining slots.")
        return embed

    @discord.ui.button(label="Join Race", emoji="✅", style=discord.ButtonStyle.success)
    async def join_race(self, interaction: discord.Interaction, button: discord.ui.Button):
        if self.finished:
            await interaction.response.send_message("That race lobby has already closed.", ephemeral=True)
            return
        if interaction.user.id in self.teams_by_user_id:
            await interaction.response.send_message("You are already in this race.", ephemeral=True)
            return
        if len(self.teams_by_user_id) >= MAX_RACERS:
            await interaction.response.send_message("This race is full.", ephemeral=True)
            return

        team = await self.cog.bot.db.get_team_by_owner(interaction.user.id)
        if not team:
            await interaction.response.send_message("You need your own team first. Use `/team_wizard`.", ephemeral=True)
            return
        if not await self.cog.bot.race_activity.reserve_lobby_team(team.id or 0):
            await interaction.response.send_message(
                "That team is already in an active race or another race lobby.",
                ephemeral=True,
            )
            return

        self.teams_by_user_id[interaction.user.id] = team
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def finish_after_delay(self) -> None:
        checkpoints = [
            (PLAYER_LOBBY_SECONDS - 300, "5 minutes left to join the race."),
            (PLAYER_LOBBY_SECONDS - 60, "1 minute left. Grid is nearly locked."),
        ]
        elapsed = 0
        for delay, message in checkpoints:
            wait_for = max(0, delay - elapsed)
            if wait_for:
                await asyncio.sleep(wait_for)
            elapsed = delay
            if self.finished:
                return
            if self.message:
                await self.message.channel.send(message)

        final_wait = max(0, PLAYER_LOBBY_SECONDS - elapsed)
        if final_wait:
            await asyncio.sleep(final_wait)
        await self.finish_lobby()

    async def finish_lobby(self) -> None:
        if self.finished:
            return
        self.finished = True
        for item in self.children:
            item.disabled = True
        if self.message:
            await self.message.edit(embed=self.embed(), view=self)

        player_teams = list(self.teams_by_user_id.values())
        if len(player_teams) < MIN_PLAYER_RACERS:
            await self.cog.bot.race_activity.release_lobby_teams([team.id for team in player_teams])
            if self.message:
                await self.message.channel.send(
                    f"Race cancelled: only {len(player_teams)} joined. At least {MIN_PLAYER_RACERS} player teams are needed."
                )
            return

        teams = player_teams[:MAX_RACERS]
        if self.mode == "players_plus_ai" and len(teams) < MAX_RACERS:
            teams.extend(ai_teams(MAX_RACERS - len(teams), f"{self.message.id if self.message else self.track_key}-fill"))

        if self.message:
            await self.cog.run_single_race(
                self.message.channel,
                self.track_key,
                self.laps,
                teams,
                title=RACE_MODES[self.mode],
                lobby_reserved=True,
            )


class RacingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.media = MediaRegistry()
        self.race_cooldowns: dict[int, float] = {}

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        command_name = interaction.command.name if interaction.command else ""
        if is_admin(interaction) or command_name in {"race_wizard", "race_tracks", "track_cards"}:
            return True
        await deny_admin_only(interaction)
        return False

    async def run_single_race(
        self,
        channel: discord.abc.Messageable,
        track_key: str,
        laps: int,
        teams: list[Team],
        title: str,
        seed: str | None = None,
        *,
        initial_damage_by_team_id: dict[int, int] | None = None,
        persist: bool = True,
        replay_source_id: int | None = None,
        weather_key: str | None = None,
        rng_state: tuple | None = None,
        rivalry_heat_by_pair: dict[tuple[int, int], int] | None = None,
        lobby_reserved: bool = False,
    ) -> None:
        team_ids = [team.id for team in teams if team.id is not None]
        reservation = (
            await self.bot.race_activity.promote_lobby_to_race(team_ids)
            if lobby_reserved
            else await self.bot.race_activity.reserve_race(team_ids)
        )
        if reservation is None:
            if lobby_reserved:
                await self.bot.race_activity.release_lobby_teams(team_ids)
            await channel.send("Race cancelled: one or more teams are already active in another race or lobby.")
            return

        try:
            initial_damage_by_team_id = initial_damage_by_team_id or {}
            active_rivalry_heat = (
                rivalry_heat_by_pair
                if rivalry_heat_by_pair is not None
                else await rivalry_heat_map(self.bot.db, [int(team_id) for team_id in team_ids if team_id])
            )
            engine = RaceEngine(
                track_key,
                teams,
                seed=seed,
                laps=laps,
                initial_damage_by_team_id=initial_damage_by_team_id,
                weather_key=weather_key,
                rng_state=rng_state,
                rivalry_heat_by_pair=active_rivalry_heat,
            )
            await channel.send(
                embed=scrutineering_embed(
                    teams,
                    title=f"Pre-Race Scrutineering: {TRACKS[track_key].name}",
                    weather=engine.weather,
                    carryover_damage=initial_damage_by_team_id,
                )
            )
            predictions = PredictionView(teams)
            prediction_message = await channel.send(embed=predictions.embed(title), view=predictions)
            await predictions.wait()
            await prediction_message.edit(embed=predictions.embed(title), view=predictions)
            await channel.send(
                f"Race started: **{TRACKS[track_key].name}**, {laps} laps, {len(teams)} teams. "
                f"Weather: **{engine.weather.name}**."
            )
            events, results, used_seed = engine.run()
            result_dicts = RaceEngine.results_to_dicts(results)
            reward_embeds: list[discord.Embed] = []

            if persist:
                async with self.bot.recovery_lock:
                    checkpoint_token = await self.bot.recovery.create_race_checkpoint(
                        {
                            "track_key": track_key,
                            "laps": laps,
                            "team_ids": [int(team_id) for team_id in team_ids if team_id],
                            "tournament_id": None,
                            "seed": used_seed,
                        }
                    )
                    replay_data = build_replay_snapshot(
                        teams,
                        laps=laps,
                        initial_damage_by_team_id=initial_damage_by_team_id,
                        weather_key=engine.weather.key,
                        rng_state=engine.initial_rng_state,
                        rivalry_heat_by_pair=active_rivalry_heat,
                    )
                    race_id = await self.bot.db.save_race(
                        None,
                        track_key,
                        used_seed,
                        RaceEngine.events_to_dicts(events),
                        result_dicts,
                        replay_data=replay_data,
                    )
                    self.bot.recovery.bind_race_checkpoint(checkpoint_token, race_id)
                    await self.bot.recovery.mark_presentation(race_id, -1, "saved")
                    result_title = f"{title} Race #{race_id} Results - {TRACKS[track_key].name}"
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
                            laps,
                        )
                    except Exception:
                        logging.exception("Post-race processing failed for race %s; restoring pre-race checkpoint", race_id)
                        await self.bot.recovery.undo_last_race()
                        raise
            else:
                race_id = replay_source_id or 0
                result_title = f"{title} Results - {TRACKS[track_key].name}"

            stream_error = None
            try:
                progress_callback = None
                if persist:
                    await self.bot.recovery.mark_presentation(race_id, -1, "streaming")

                    async def progress_callback(index: int) -> None:
                        await self.bot.recovery.mark_presentation(race_id, index, "streaming")

                await RaceStreamer(self.media, self.bot.settings.race_tick_seconds).stream(
                    channel,
                    events,
                    progress_callback=progress_callback,
                )
                if persist:
                    await self.bot.recovery.mark_presentation(race_id, len(events) - 1, "complete")
            except (discord.HTTPException, OSError) as exc:
                stream_error = exc
                if persist:
                    state = await self.bot.recovery.presentation_state(race_id)
                    last_index = int(state["last_event_index"]) if state else -1
                    await self.bot.recovery.mark_presentation(race_id, last_index, "interrupted")
                logging.exception("Race event streaming failed for race %s", race_id)

            await send_race_report(
                channel=channel,
                db=self.bot.db,
                track_key=track_key,
                race_id=race_id,
                teams=teams,
                results=results,
                events=events,
                weather_name=engine.weather.name,
                title=result_title,
                race_laps=laps,
                predictions=predictions,
                rivalry_watch=None if persist else [],
                final_embed=single_race_final_embed(results, events, result_title),
                award_rewards=False,
                reward_embeds_override=reward_embeds,
                persisted_report=persist,
            )
            if stream_error:
                try:
                    await channel.send("Some live race updates could not be posted, but the saved result and progression were completed safely.")
                except discord.HTTPException:
                    pass
        finally:
            await self.bot.race_activity.release(reservation)

    async def run_demo_race(self, channel: discord.abc.Messageable, track_key: str, seed: str | None = None) -> None:
        existing = await self.bot.db.list_teams()
        if len(existing) < 10:
            for team in ai_teams(10 - len(existing), f"demo-fill-{len(existing)}"):
                try:
                    team.id = None
                    await self.bot.db.create_team(team)
                except Exception:
                    continue
        teams = (await self.bot.db.list_teams())[:10]
        await self.run_single_race(channel, track_key, TRACKS[track_key].laps, teams, title="Demo Race", seed=seed)

    def _cooldown_remaining(self, user_id: int, seconds: int = 30) -> int:
        now = asyncio.get_running_loop().time()
        last = self.race_cooldowns.get(user_id, 0)
        remaining = int(seconds - (now - last))
        return max(0, remaining)

    def _mark_cooldown(self, user_id: int) -> None:
        self.race_cooldowns[user_id] = asyncio.get_running_loop().time()

    async def send_single_race_preflight(
        self,
        interaction: discord.Interaction,
        track_key: str,
        teams: list[Team],
        title: str,
        *,
        seed: str | None = None,
        laps: int | None = None,
        initial_damage_by_team_id: dict[int, int] | None = None,
        persist: bool = True,
        replay_source_id: int | None = None,
        weather_key: str | None = None,
        rng_state: tuple | None = None,
        rivalry_heat_by_pair: dict[tuple[int, int], int] | None = None,
    ) -> None:
        remaining = self._cooldown_remaining(interaction.user.id)
        if remaining:
            message = f"Race controls are cooling down. Try again in {remaining} seconds."
            if interaction.response.is_done():
                await interaction.followup.send(message, ephemeral=True)
            else:
                await interaction.response.send_message(message, ephemeral=True)
            return

        initial_damage_by_team_id = initial_damage_by_team_id or {}
        engine = RaceEngine(
            track_key,
            teams,
            seed=seed,
            laps=laps or TRACKS[track_key].laps,
            initial_damage_by_team_id=initial_damage_by_team_id,
            weather_key=weather_key,
            rng_state=rng_state,
            rivalry_heat_by_pair=rivalry_heat_by_pair,
        )
        seed = engine.seed
        embed = race_preflight_embed(
            teams,
            TRACKS[track_key].name,
            engine.weather,
            title="Race Preflight",
            seed=seed,
            carryover_damage=initial_damage_by_team_id,
            track_key=track_key,
            laps=laps or TRACKS[track_key].laps,
        )

        async def run(confirm_interaction: discord.Interaction):
            self._mark_cooldown(confirm_interaction.user.id)
            await audit_log(self.bot, "Race Started", f"{title} at {TRACKS[track_key].name} seed {seed}", confirm_interaction.user)
            await confirm_interaction.response.edit_message(content="Race confirmed. Posting to channel now.", embed=None, view=None)
            await self.run_single_race(
                confirm_interaction.channel,
                track_key,
                laps or TRACKS[track_key].laps,
                teams,
                title=title,
                seed=seed,
                initial_damage_by_team_id=initial_damage_by_team_id,
                persist=persist,
                replay_source_id=replay_source_id,
                weather_key=engine.weather.key if weather_key is not None else None,
                rng_state=engine.initial_rng_state if rng_state is not None else None,
                rivalry_heat_by_pair=rivalry_heat_by_pair,
            )

        view = ConfirmView(interaction.user.id, "Start Race", run)
        if interaction.response.is_done():
            await interaction.followup.send(embed=embed, view=view, ephemeral=True)
        else:
            await interaction.response.send_message(embed=embed, view=view, ephemeral=True)

    @app_commands.command(name="race_tracks", description="List available tracks.")
    async def race_tracks(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=Embeds.track_list(), ephemeral=True)

    @app_commands.command(name="race_wizard", description="Start a single race wizard.")
    async def race_wizard(self, interaction: discord.Interaction):
        team = await self.bot.db.get_team_by_owner(interaction.user.id)
        if not team and is_admin(interaction):
            teams = await self.bot.db.list_teams()
            team = teams[0] if teams else None
        if not team:
            await interaction.response.send_message("You need your own team first. Use `/team_wizard`.", ephemeral=True)
            return
        view = RaceWizardView(self, interaction.user.id, team)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)

    @app_commands.command(name="race_quick", description="Admin: run a race using comma-separated team IDs, max 10.")
    @app_commands.choices(track_key=TRACK_CHOICES)
    async def race_quick(self, interaction: discord.Interaction, track_key: str, team_ids_csv: str, seed: str | None = None):
        if track_key not in TRACKS:
            await interaction.response.send_message("Unknown track. Use `/race_tracks`.", ephemeral=True)
            return
        ids = parse_team_ids_csv(team_ids_csv)
        teams = []
        for team_id in ids:
            team = await self.bot.db.get_team(team_id)
            if team:
                teams.append(team)
        if len(teams) < 2:
            await interaction.response.send_message("I need at least 2 valid teams.", ephemeral=True)
            return
        await self.send_single_race_preflight(interaction, track_key, teams, "Quick Race", seed=seed)

    @app_commands.command(name="race_demo", description="Admin: create demo teams if needed and run a full 10-car demo race.")
    @app_commands.choices(track_key=TRACK_CHOICES)
    async def race_demo(self, interaction: discord.Interaction, track_key: str = "neon_mile"):
        if track_key not in TRACKS:
            await interaction.response.send_message("Unknown track. Use `/race_tracks`.", ephemeral=True)
            return
        existing = await self.bot.db.list_teams()
        teams = existing[:10] if len(existing) >= 10 else [*existing, *ai_teams(10 - len(existing), f"demo-preview-{len(existing)}")]
        engine = RaceEngine(track_key, teams)
        seed = engine.seed
        embed = race_preflight_embed(teams, TRACKS[track_key].name, engine.weather, title="Demo Race Preflight", seed=seed, track_key=track_key, laps=TRACKS[track_key].laps)

        async def run(confirm_interaction: discord.Interaction):
            self._mark_cooldown(confirm_interaction.user.id)
            await audit_log(self.bot, "Demo Race Started", f"{TRACKS[track_key].name} seed {seed}", confirm_interaction.user)
            await confirm_interaction.response.edit_message(content="Demo race confirmed. Posting to channel now.", embed=None, view=None)
            await self.run_demo_race(confirm_interaction.channel, track_key, seed)

        await interaction.response.send_message(
            embed=embed,
            view=ConfirmView(interaction.user.id, "Start Demo Race", run),
            ephemeral=True,
        )

    @app_commands.command(name="race_replay", description="Admin: replay a saved race without changing stats or records.")
    async def race_replay(self, interaction: discord.Interaction, race_id: int):
        race = await self.bot.db.get_race(race_id)
        if not race:
            await interaction.response.send_message("Race not found.", ephemeral=True)
            return

        teams: list[Team] = []
        laps = TRACKS[str(race["track_key"])].laps
        initial_damage: dict[int, int] = {}
        weather_key: str | None = None
        rng_state: tuple | None = None
        replay_rivalry_heat: dict[tuple[int, int], int] = {}
        exact_snapshot = bool("replay_json" in race.keys() and race["replay_json"])

        if exact_snapshot:
            try:
                snapshot = json.loads(race["replay_json"])
                teams, laps, initial_damage, weather_key, rng_state = restore_replay_snapshot(snapshot)
                replay_rivalry_heat = restore_replay_rivalry_heat(snapshot)
            except (TypeError, ValueError, KeyError, json.JSONDecodeError) as exc:
                await interaction.response.send_message(f"Saved replay snapshot is invalid: {exc}", ephemeral=True)
                return
        else:
            # Legacy v0.4 races only stored team IDs and seed, so current team builds must be used.
            results = json.loads(race["results_json"])
            for result in results[:10]:
                team_id = int(result.get("team_id", 0))
                if team_id <= 0:
                    continue
                team = await self.bot.db.get_team(team_id)
                if team:
                    teams.append(team)

        if len(teams) < 2:
            await interaction.response.send_message("That race does not have enough saved teams to replay.", ephemeral=True)
            return

        replay_label = f"Replay Race #{race_id}" if exact_snapshot else f"Legacy Replay Race #{race_id}"
        await self.send_single_race_preflight(
            interaction,
            str(race["track_key"]),
            teams,
            replay_label,
            seed=str(race["seed"]),
            laps=laps,
            initial_damage_by_team_id=initial_damage,
            persist=False,
            replay_source_id=race_id,
            weather_key=weather_key,
            rng_state=rng_state,
            rivalry_heat_by_pair=replay_rivalry_heat if exact_snapshot else {},
        )

    @app_commands.command(name="track_cards", description="Show track cards with difficulty and hazards.")
    async def track_cards(self, interaction: discord.Interaction):
        lines = []
        for key, track in TRACKS.items():
            lines.append(
                f"**{track.name}** (`{key}`)\n"
                f"Corners {track.corner_difficulty} | Straights {track.straight_bias} | Roughness {track.surface_roughness} | Pit {track.pit_difficulty} | Hazard {track.hazard_rate}\n"
                f"Hazards: {', '.join(track.hazard_names)}"
            )
        view = PaginatedTextView(interaction.user.id, "Track Cards", lines, per_page=3)
        await interaction.response.send_message(embed=view.embed(), view=view, ephemeral=True)


async def setup(bot: commands.Bot):
    await bot.add_cog(RacingCog(bot))
