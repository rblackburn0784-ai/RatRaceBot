import discord

from data.defaults import PARTS
from models.domain import Team, WeatherCondition
from services.builds import BuildService
from services.engagement import traits_text
from services.sponsors import sponsor_by_key


def _illegal_parts(team: Team) -> list[str]:
    return [
        part.name.removeprefix("ILLEGAL ").strip()
        for part in BuildService.equipped_parts_by_slot(team).values()
        if "illegal_risk" in part.risk_tags
    ]


def _weather_warnings(team: Team, weather: WeatherCondition | None) -> list[str]:
    if not weather:
        return []

    stats = BuildService.clamp_car_stats(BuildService.effective_car_stats(team) + weather.modifiers)
    warnings = []
    if weather.key == "rain" and stats.braking <= 1:
        warnings.append("wet braking looks sketchy")
    if weather.key in {"rain", "oil_mist", "crosswind"} and stats.handling <= 1:
        warnings.append("handling may be a handful")
    if weather.key == "heatwave" and stats.heat >= 8:
        warnings.append("engine bay is running hot")
    if weather.pit_difficulty_delta > 0 and stats.pit_friendliness <= 1:
        warnings.append("pit lane work may get messy")
    return warnings


def _team_scrutineering_lines(
    team: Team,
    weather: WeatherCondition | None = None,
    carryover_damage: int = 0,
) -> tuple[str, str]:
    illegal_parts = _illegal_parts(team)
    illegal_risk = BuildService.illegal_disqualification_risk_percent(team)
    sponsor = sponsor_by_key(team.active_sponsor_key)
    if illegal_risk and sponsor:
        illegal_risk = min(95, illegal_risk + sponsor.illegal_scrutiny_bonus)
    stats = BuildService.effective_car_stats(team)
    warnings = []

    if illegal_parts:
        warnings.append(f"{len(illegal_parts)} illegal part(s): {', '.join(illegal_parts[:2])}")
    if stats.heat >= 8:
        warnings.append("high heat build")
    if stats.reliability <= 1:
        warnings.append("low reliability")
    strain = BuildService.build_strain(team)
    if strain >= 12:
        warnings.append(f"knife-edge tune: strain {strain}")
    elif strain >= 8:
        warnings.append(f"stressed tune: strain {strain}")
    if carryover_damage:
        warnings.append(f"{carryover_damage}% repaired tournament damage")
    if sponsor:
        warnings.append(f"sponsor: {sponsor.name}")
    warnings.extend(_weather_warnings(team, weather))

    if illegal_risk >= 18:
        verdict = "Officials have this rod circled in red."
        status = "High Risk"
    elif illegal_risk:
        verdict = "Passed, but the clipboards are watching."
        status = "Suspicious"
    elif stats.heat >= 8 or stats.reliability <= 1:
        verdict = "Legal, but mechanically spicy."
        status = "Mechanical Risk"
    elif warnings:
        verdict = "Passed with a few raised eyebrows."
        status = "Watchlist"
    else:
        verdict = "Passed clean. Officials look bored."
        status = "Clear"

    detail = (
        f"Illegal risk: **{illegal_risk}%**\n"
        f"Strain: **{strain} ({BuildService.build_strain_label(team)})** | Tuning: **{BuildService.tuning_efficiency(team) * 100:.0f}%**\n"
        f"Checks: {', '.join(warnings) if warnings else 'no major issues'}\n"
        f"Traits: {', '.join(line.split(':**')[0].replace('**', '') for line in traits_text(team).splitlines())}\n"
        f"Verdict: {verdict}"
    )
    return status, detail


def scrutineering_embed(
    teams: list[Team],
    title: str = "Pre-Race Scrutineering",
    weather: WeatherCondition | None = None,
    carryover_damage: dict[int, int] | None = None,
) -> discord.Embed:
    carryover_damage = carryover_damage or {}
    description = "Officials inspect the grid before the flag drops."
    if weather:
        description += f"\nWeather: **{weather.name}** - {weather.description}"

    embed = discord.Embed(title=title, description=description, color=discord.Color.orange())
    for team in teams[:10]:
        damage = carryover_damage.get(team.id or 0, 0)
        status, detail = _team_scrutineering_lines(team, weather, damage)
        embed.add_field(
            name=f"{status}: {team.name}",
            value=detail[:1024],
            inline=False,
        )
    return embed
