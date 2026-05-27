import asyncio
import logging

import discord
from discord import app_commands
from discord.ext import commands

from data.defaults import TRACKS
from models.domain import Team
from models.enums import CarArchetype
from models.stats import DriverStats
from services.access import deny_admin_only, is_admin
from services.ai_teams import ai_teams
from services.formatting import Embeds
from services.media import MediaRegistry
from services.race_engine import RaceEngine
from services.streamer import RaceStreamer
from services.team_ids import parse_team_ids_csv

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


class RaceWizardView(discord.ui.View):
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
        for item in self.children:
            item.disabled = True

        if self.mode == "full_ai":
            await interaction.response.edit_message(embed=self.embed(), view=self)
            teams = [self.owner_team, *ai_teams(9, f"{interaction.id}-{self.owner_team.id}-{self.track_key}")]
            await self.cog.run_single_race(
                interaction.channel,
                self.track_key,
                self.laps,
                teams,
                title=f"{self.owner_team.name} vs AI",
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


class PlayerRaceLobbyView(discord.ui.View):
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

        self.teams_by_user_id[interaction.user.id] = team
        await interaction.response.edit_message(embed=self.embed(), view=self)

    async def finish_after_delay(self) -> None:
        await asyncio.sleep(PLAYER_LOBBY_SECONDS)
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
            )


class RacingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.media = MediaRegistry()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        command_name = interaction.command.name if interaction.command else ""
        if is_admin(interaction) or command_name in {"race_wizard", "race_tracks"}:
            return True
        await deny_admin_only(interaction)
        return False

    async def run_single_race(self, channel: discord.abc.Messageable, track_key: str, laps: int, teams: list[Team], title: str) -> None:
        await channel.send(f"Race started: **{TRACKS[track_key].name}**, {laps} laps, {len(teams)} teams.")
        engine = RaceEngine(track_key, teams, laps=laps)
        events, results, used_seed = engine.run()
        race_id = await self.bot.db.save_race(None, track_key, used_seed, RaceEngine.events_to_dicts(events), RaceEngine.results_to_dicts(results))
        await RaceStreamer(self.media, self.bot.settings.race_tick_seconds).stream(channel, events)
        await channel.send(embed=Embeds.results(results, title=f"{title} Race #{race_id} Results - {TRACKS[track_key].name}"))

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
        await interaction.response.send_message(f"Race started at **{TRACKS[track_key].name}** with seed `{seed or 'auto'}`.")
        engine = RaceEngine(track_key, teams, seed)
        events, results, used_seed = engine.run()
        race_id = await self.bot.db.save_race(None, track_key, used_seed, RaceEngine.events_to_dicts(events), RaceEngine.results_to_dicts(results))
        await RaceStreamer(self.media, self.bot.settings.race_tick_seconds).stream(interaction.channel, events)
        await interaction.channel.send(embed=Embeds.results(results, title=f"Race #{race_id} Results - {TRACKS[track_key].name}"))

    @app_commands.command(name="race_demo", description="Admin: create demo teams if needed and run a full 10-car demo race.")
    @app_commands.choices(track_key=TRACK_CHOICES)
    async def race_demo(self, interaction: discord.Interaction, track_key: str = "neon_mile"):
        if track_key not in TRACKS:
            await interaction.response.send_message("Unknown track. Use `/race_tracks`.", ephemeral=True)
            return
        existing = await self.bot.db.list_teams()
        if len(existing) < 10:
            samples = [
                ("The Rust Saints", "Johnny Carburettor", "The Alley Cats", "Saintly Rattle", CarArchetype.COUPE_32),
                ("Blacktop Banshees", "Mabel Moon", "Grease Choir", "Moon Howler", CarArchetype.ROADSTER_29),
                ("County Line Devils", "Buck Harlan", "Barnstorm Crew", "Red Prayer", CarArchetype.GASSER),
                ("Junkyard Apostles", "Sal Vex", "Scrap Chapel", "Tin Sermon", CarArchetype.TRUCK_50),
                ("Neon Greasers", "Ricky Switchblade", "Diner Rats", "Pink Trouble", CarArchetype.LEADSLED),
                ("Salt Ghosts", "Eddie Vale", "Whiteout Wrenches", "Ghost Needle", CarArchetype.LAKSTER),
                ("Chrome Undertakers", "Lana Graves", "Last Rites Pit", "Hearse Fire", CarArchetype.SEDAN),
                ("Switchback Sinners", "Tommy Blacktop", "Cliffside Crew", "Dead Man's Bend", CarArchetype.COUPE_32),
                ("The Primer Kings", "Hank Rattle", "Primer Pit Boys", "Grey Ghost", CarArchetype.TRUCK_50),
                ("Rockabilly Reapers", "Rosie Riot", "The Combbacks", "Lipstick Lightning", CarArchetype.ROADSTER_29),
            ]
            for sample in samples:
                try:
                    await self.bot.db.create_team(Team(None, sample[0], sample[1], sample[2], sample[3], CarArchetype(sample[4]), DriverStats(4, 4, 4, 4, 4, 4), []))
                except Exception as exc:
                    logging.debug("Skipping demo team creation: %s", exc)
        teams = (await self.bot.db.list_teams())[:10]
        await interaction.response.send_message(f"Demo race started at **{TRACKS[track_key].name}**.")
        engine = RaceEngine(track_key, teams)
        events, results, used_seed = engine.run()
        race_id = await self.bot.db.save_race(None, track_key, used_seed, RaceEngine.events_to_dicts(events), RaceEngine.results_to_dicts(results))
        await RaceStreamer(self.media, self.bot.settings.race_tick_seconds).stream(interaction.channel, events)
        await interaction.channel.send(embed=Embeds.results(results, title=f"Demo Race #{race_id} Results"))


async def setup(bot: commands.Bot):
    await bot.add_cog(RacingCog(bot))
