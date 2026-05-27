import discord
from data.defaults import PARTS, TRACKS
from models.domain import RaceResult, Team
from models.enums import PartSlot
from services.builds import BuildService

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
        e.add_field(name="Pit Crew Loadout", value=BuildService.crew_summary(team), inline=False)
        illegal_risk = BuildService.illegal_disqualification_risk_percent(team)
        if illegal_risk:
            e.add_field(
                name="Illegal Parts Warning",
                value=f"{BuildService.illegal_part_count(team)} illegal part(s): {illegal_risk}% disqualification risk per race.",
                inline=False,
            )
        return e

    @staticmethod
    def track_list() -> discord.Embed:
        e = discord.Embed(title="Rat Rod Tracks", description="Bad places to make worse decisions.")
        for key, t in TRACKS.items():
            e.add_field(name=f"{key} — {t.name}", value=f"{t.description}\nHazards: {', '.join(t.hazard_names)}", inline=False)
        return e

    @staticmethod
    def parts_list() -> discord.Embed:
        e = discord.Embed(
            title="Rat Rod Parts Catalogue",
            description="Illegal parts are marked and add +6% disqualification risk per race.",
        )
        for slot in PartSlot:
            lines = []
            for key, p in PARTS.items():
                if p.slot != slot:
                    continue
                mods = " ".join(
                    f"{STAT_LABELS.get(stat, stat.title())}{value:+d}"
                    for stat, value in p.modifiers.as_dict().items()
                    if value
                )
                marker = " [ILLEGAL +6% DSQ]" if BuildService.is_illegal_part_key(key) else ""
                lines.append(f"`{key}` - {p.name}{marker}: {mods or 'No modifiers'}")
            e.add_field(name=f"{slot.value.title()} Parts", value="\n".join(lines), inline=False)
        return e

    @staticmethod
    def results(results: list[RaceResult], title: str = "Race Results") -> discord.Embed:
        e = discord.Embed(title=title)
        lines = []
        for r in sorted(results, key=lambda x: x.position):
            status = "DSQ" if r.disqualified else "DNF" if r.dnf else f"+{r.points} pts"
            start_damage = f" | start dmg {r.starting_damage}%" if r.starting_damage else ""
            lines.append(
                f"**{r.position}. {r.team_name}** - {r.driver_name} - {status} - "
                f"OTK {r.overtakes} | Crash {r.crashes} | Illegal {r.illegal_moves} | "
                f"Pit {r.pit_stops} | damage {r.damage}%{start_damage} tyres {r.tyre_wear}% warnings {r.warnings}"
            )
        e.description = "\n".join(lines)
        return e
