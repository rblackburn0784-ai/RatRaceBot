import discord

from data.defaults import TRACKS
from models.domain import Team
from models.stats import CarStats
from services.builds import BuildService
from services.race_presentation import team_setup_summary, track_character
from services.scrutineering import scrutineering_embed


def missing_setup(team: Team) -> str:
    missing = []
    if not team.parts:
        missing.append("no parts")
    if not team.crew:
        missing.append("no pit crew")
    return ", ".join(missing) if missing else "ready"


def _resolve_track(track_name: str, track_key: str | None):
    if track_key and track_key in TRACKS:
        return TRACKS[track_key]
    return next((track for track in TRACKS.values() if track.name == track_name), None)


def race_preflight_embed(
    teams: list[Team],
    track_name: str,
    weather,
    *,
    title: str = "Race Preflight",
    seed: str | None = None,
    carryover_damage: dict[int, int] | None = None,
    track_key: str | None = None,
    laps: int | None = None,
) -> discord.Embed:
    track = _resolve_track(track_name, track_key)
    embed = scrutineering_embed(
        teams,
        title=title,
        weather=weather,
        carryover_damage=carryover_damage,
    )
    race_laps = laps or (track.laps if track else None)
    character = track_character(track) if track else "Mixed"
    lap_text = f"{race_laps} laps" if race_laps else "race distance set by track"
    embed.description = (
        f"**{track_name.upper()} — {lap_text.upper()}**\n"
        f"{weather.name} · {character}\n\n"
        "These cards describe broad strengths and compromises; exact race maths stays hidden."
    )

    if track:
        embed.add_field(
            name="Track Character",
            value=(
                f"{track.description}\n"
                f"Hazards: {', '.join(track.hazard_names)}\n"
                f"Race phases: **Start → Opening → Mid-Race → Pit Window → Closing → Final Lap**"
            )[:1024],
            inline=False,
        )

    for team in teams[:10]:
        damage = 0
        if carryover_damage and team.id is not None:
            damage = int(carryover_damage.get(team.id, 0))
        if track:
            summary = team_setup_summary(team, track, weather, damage)
        else:
            risk = BuildService.illegal_disqualification_risk_percent(team)
            setup = missing_setup(team)
            damage_text = f" | carryover {damage}%" if damage else ""
            risk_text = f" | illegal {risk}%" if risk else ""
            summary = f"{setup}{risk_text}{damage_text}"
        embed.add_field(
            name=f"#{team.id or 'AI'} {team.name} — {team.car_name}",
            value=summary,
            inline=False,
        )

    embed.set_footer(text=f"Race seed: {seed or 'auto'} · Setup guidance is qualitative, not a guarantee.")
    return embed


def effective_stat_lines(stats: CarStats) -> list[str]:
    return [f"{key.replace('_', ' ').title()}: {value:+d}" for key, value in stats.as_dict().items()]
