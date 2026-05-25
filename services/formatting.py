import discord
from data.defaults import PARTS, TRACKS
from models.domain import RaceResult, Team
from services.builds import BuildService

class Embeds:
    @staticmethod
    def team_sheet(team: Team) -> discord.Embed:
        eff = BuildService.effective_car_stats(team)
        e = discord.Embed(title=f"#{team.id} {team.name}", description=f"Driver: **{team.driver_name}**\nRod: **{team.car_name}** — {team.archetype.value}")
        e.add_field(name="Pit Crew", value=team.pit_crew_name, inline=True)
        e.add_field(name="Driver Stats", value=(
            f"Nerve {team.stats.nerve} | Handling {team.stats.handling} | Aggression {team.stats.aggression}\n"
            f"Mechanics {team.stats.mechanics} | Reflexes {team.stats.reflexes} | Showmanship {team.stats.showmanship}\n"
            f"Total: {team.stats.total}/24"
        ), inline=False)
        e.add_field(name="Effective Rod Stats", value="\n".join(f"{k.title()}: {v:+d}" for k, v in eff.as_dict().items()), inline=False)
        e.add_field(name="Parts", value=BuildService.part_summary(team), inline=False)
        return e

    @staticmethod
    def track_list() -> discord.Embed:
        e = discord.Embed(title="Rat Rod Tracks", description="Five bad places to make worse decisions.")
        for key, t in TRACKS.items():
            e.add_field(name=f"{key} — {t.name}", value=f"{t.description}\nHazards: {', '.join(t.hazard_names)}", inline=False)
        return e

    @staticmethod
    def parts_list() -> discord.Embed:
        e = discord.Embed(title="Rat Rod Parts Catalogue")
        for key, p in PARTS.items():
            mods = ", ".join(f"{k} {v:+d}" for k, v in p.modifiers.as_dict().items() if v)
            e.add_field(name=f"{key} — {p.name} [{p.slot.value}]", value=f"{p.description}\n{mods or 'No stat modifiers'}", inline=False)
        return e

    @staticmethod
    def results(results: list[RaceResult], title: str = "Race Results") -> discord.Embed:
        e = discord.Embed(title=title)
        lines = []
        for r in sorted(results, key=lambda x: x.position):
            status = "DSQ" if r.disqualified else "DNF" if r.dnf else f"+{r.points} pts"
            lines.append(f"**{r.position}. {r.team_name}** — {r.driver_name} — {status} — damage {r.damage}% tyres {r.tyre_wear}% warnings {r.warnings}")
        e.description = "\n".join(lines)
        return e
