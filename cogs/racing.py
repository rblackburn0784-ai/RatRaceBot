import logging

import discord
from discord import app_commands
from discord.ext import commands

from data.defaults import TRACKS

TRACK_CHOICES = [
    app_commands.Choice(name=f"{track.name} ({key})", value=key)
    for key, track in list(TRACKS.items())[:25]
]
from models.domain import Team
from models.enums import CarArchetype
from models.stats import DriverStats
from services.access import deny_admin_only, is_admin
from services.formatting import Embeds
from services.media import MediaRegistry
from services.race_engine import RaceEngine
from services.streamer import RaceStreamer
from services.team_ids import parse_team_ids_csv

class RacingCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.media = MediaRegistry()

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if is_admin(interaction):
            return True
        await deny_admin_only(interaction)
        return False

    @app_commands.command(name="race_tracks", description="List available tracks.")
    async def race_tracks(self, interaction: discord.Interaction):
        await interaction.response.send_message(embed=Embeds.track_list(), ephemeral=True)

    @app_commands.command(name="race_quick", description="Run a race using comma-separated team IDs, max 10.")
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
        await interaction.response.send_message(f"🏁 Race started at **{TRACKS[track_key].name}** with seed `{seed or 'auto'}`.")
        engine = RaceEngine(track_key, teams, seed)
        events, results, used_seed = engine.run()
        race_id = await self.bot.db.save_race(None, track_key, used_seed, RaceEngine.events_to_dicts(events), RaceEngine.results_to_dicts(results))
        streamer = RaceStreamer(self.media, self.bot.settings.race_tick_seconds)
        await streamer.stream(interaction.channel, events)
        await interaction.channel.send(embed=Embeds.results(results, title=f"Race #{race_id} Results — {TRACKS[track_key].name}"))

    @app_commands.command(name="race_demo", description="Create demo teams if needed and run a full 10-car demo race.")
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
            for i, s in enumerate(samples, start=1):
                try:
                    await self.bot.db.create_team(Team(None, s[0], s[1], s[2], s[3], CarArchetype(s[4]), DriverStats(4,4,4,4,4,4), []))
                except Exception as exc:
                    logging.debug("Skipping demo team creation: %s", exc)
        teams = (await self.bot.db.list_teams())[:10]
        await interaction.response.send_message(f"🏁 Demo race started at **{TRACKS[track_key].name}**.")
        engine = RaceEngine(track_key, teams)
        events, results, used_seed = engine.run()
        race_id = await self.bot.db.save_race(None, track_key, used_seed, RaceEngine.events_to_dicts(events), RaceEngine.results_to_dicts(results))
        await RaceStreamer(self.media, self.bot.settings.race_tick_seconds).stream(interaction.channel, events)
        await interaction.channel.send(embed=Embeds.results(results, title=f"Demo Race #{race_id} Results"))

async def setup(bot: commands.Bot):
    await bot.add_cog(RacingCog(bot))
