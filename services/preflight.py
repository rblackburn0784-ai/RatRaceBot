import discord

from models.domain import Team
from models.stats import CarStats
from services.builds import BuildService
from services.scrutineering import scrutineering_embed


def missing_setup(team: Team) -> str:
    missing = []
    if not team.parts:
        missing.append("no parts")
    if not team.crew:
        missing.append("no pit crew")
    return ", ".join(missing) if missing else "ready"


def race_preflight_embed(
    teams: list[Team],
    track_name: str,
    weather,
    *,
    title: str = "Race Preflight",
    seed: str | None = None,
    carryover_damage: dict[int, int] | None = None,
) -> discord.Embed:
    embed = scrutineering_embed(
        teams,
        title=title,
        weather=weather,
        carryover_damage=carryover_damage,
    )
    embed.description = (
        f"Track: **{track_name}**\n"
        f"Weather: **{weather.name}**\n"
        f"Seed: `{seed or 'auto'}`\n"
        "Confirm to post the race publicly."
    )

    lines = []
    for team in teams[:10]:
        risk = BuildService.illegal_disqualification_risk_percent(team)
        setup = missing_setup(team)
        damage = 0
        if carryover_damage and team.id is not None:
            damage = int(carryover_damage.get(team.id, 0))
        damage_text = f" | carryover {damage}%" if damage else ""
        risk_text = f" | illegal {risk}%" if risk else ""
        lines.append(f"#{team.id} **{team.name}** - {setup}{risk_text}{damage_text}")
    embed.add_field(name=f"Teams ({len(teams)})", value="\n".join(lines)[:1024], inline=False)
    return embed


def effective_stat_lines(stats: CarStats) -> list[str]:
    return [f"{key.replace('_', ' ').title()}: {value:+d}" for key, value in stats.as_dict().items()]
