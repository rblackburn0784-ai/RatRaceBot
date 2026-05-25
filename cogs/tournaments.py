import discord
from discord import app_commands
from discord.ext import commands

from data.defaults import TRACKS

TRACK_CHOICES = [
    app_commands.Choice(name=f"{track.name} ({key})", value=key)
    for key, track in TRACKS.items()
]
from services.formatting import Embeds
from services.media import MediaRegistry
from services.race_engine import RaceEngine
from services.streamer import RaceStreamer

class TournamentsCog(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.media = MediaRegistry()

    @app_commands.command(name="tournament_create", description="Create a rat rod tournament.")
    async def tournament_create(self, interaction: discord.Interaction, name: str):
        try:
            tid = await self.bot.db.create_tournament(name)
        except Exception as e:
            await interaction.response.send_message(f"❌ {e}", ephemeral=True)
            return
        await interaction.response.send_message(f"✅ Tournament **{name}** created as ID `{tid}`. Add 20–30 teams with `/tournament_add_team`.")

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
            lines.append(f"**{i}. {r['name']}** — {r['points']} pts | W {r['wins']} | Podiums {r['podiums']} | Races {r['races']} | DSQ {r['disqualifications']} | DNF {r['dnfs']}")
        await interaction.response.send_message("\n".join(lines[:30]))

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
            ids = [int(x.strip()) for x in team_ids_csv.split(",") if x.strip().isdigit()]
        else:
            ids = (await self.bot.db.tournament_team_ids(tournament_id))[:10]
        if len(ids) > 10:
            ids = ids[:10]
        teams = []
        tournament_ids = set(await self.bot.db.tournament_team_ids(tournament_id))
        for team_id in ids:
            if team_id not in tournament_ids:
                continue
            team = await self.bot.db.get_team(team_id)
            if team:
                teams.append(team)
        if len(teams) < 2:
            await interaction.response.send_message("I need at least 2 valid tournament teams, ideally 10.", ephemeral=True)
            return
        await interaction.response.send_message(f"🏆 Tournament race started: **{TRACKS[track_key].name}** with {len(teams)} teams.")
        engine = RaceEngine(track_key, teams, seed)
        events, results, used_seed = engine.run()
        result_dicts = RaceEngine.results_to_dicts(results)
        await self.bot.db.apply_race_results(tournament_id, result_dicts)
        race_id = await self.bot.db.save_race(tournament_id, track_key, used_seed, RaceEngine.events_to_dicts(events), result_dicts)
        await RaceStreamer(self.media, self.bot.settings.race_tick_seconds).stream(interaction.channel, events)
        await interaction.channel.send(embed=Embeds.results(results, title=f"Tournament Race #{race_id} Results"))

    @app_commands.command(name="tournament_close", description="Close a tournament.")
    async def tournament_close(self, interaction: discord.Interaction, tournament_id: int):
        await self.bot.db.close_tournament(tournament_id)
        await interaction.response.send_message(f"Tournament `{tournament_id}` closed.")

async def setup(bot: commands.Bot):
    await bot.add_cog(TournamentsCog(bot))
