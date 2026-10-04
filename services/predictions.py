import discord

from models.domain import RaceResult, Team
from services.race_rules import official_winner

PREDICTION_SECONDS = 20


class PredictionSelect(discord.ui.Select):
    def __init__(self, view: "PredictionView"):
        self.prediction_view = view
        options = [
            discord.SelectOption(
                label=team.name[:100],
                value=str(team.id),
                description=f"{team.driver_name} - {team.car_name}"[:100],
            )
            for team in view.teams[:25]
            if team.id is not None
        ]
        super().__init__(placeholder="Pick the race winner", min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        team_id = int(self.values[0])
        team_name = self.prediction_view.team_names.get(team_id, "Unknown")
        self.prediction_view.picks[interaction.user.id] = (team_id, interaction.user.display_name)
        await interaction.response.send_message(f"Prediction locked: **{team_name}** to win.", ephemeral=True)


class PredictionView(discord.ui.View):
    def __init__(self, teams: list[Team], timeout: int = PREDICTION_SECONDS):
        super().__init__(timeout=timeout)
        self.teams = teams
        self.team_names = {team.id: team.name for team in teams if team.id is not None}
        self.picks: dict[int, tuple[int, str]] = {}
        self.add_item(PredictionSelect(self))

    def embed(self, title: str) -> discord.Embed:
        embed = discord.Embed(
            title="Pre-Race Predictions",
            description=f"Pick the winner for **{title}**. Window closes in {int(self.timeout or 0)} seconds.",
            color=discord.Color.dark_blue(),
        )
        embed.add_field(name="Entries", value="No picks yet." if not self.picks else f"{len(self.picks)} prediction(s) locked.", inline=False)
        return embed

    async def on_timeout(self) -> None:
        for item in self.children:
            item.disabled = True

    def results_embed(self, results: list[RaceResult], title: str) -> discord.Embed | None:
        if not self.picks:
            return None
        winner = official_winner(results)
        correct = [
            display_name
            for team_id, display_name in self.picks.values()
            if winner is not None and team_id == winner.team_id
        ]
        embed = discord.Embed(
            title="Prediction Results",
            description=f"Winner: **{winner.team_name}**" if winner else "No official winner was classified.",
            color=discord.Color.dark_blue(),
        )
        embed.add_field(
            name="Correct Picks",
            value=", ".join(correct) if correct else "Nobody called it.",
            inline=False,
        )
        embed.set_footer(text=title)
        return embed
