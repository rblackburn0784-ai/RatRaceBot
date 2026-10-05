from __future__ import annotations

import discord

from data.defaults import PARTS, TRACKS
from models.domain import RaceEvent, RaceResult, Team, Track, WeatherCondition
from models.enums import EventType
from services.balance import TRACK_SPECIALISATIONS, effective_strain, track_part_adjustment
from services.builds import BuildService
from services.race_rules import is_official_finisher
from services.race_presentation_core import PHASE_LABELS, leaderboard_checkpoints, phase_for_lap, phase_label

def _stars(value: float, low: float = 1.5, high: float = 8.5) -> str:
    if high <= low:
        rating = 3
    else:
        rating = round(1 + 4 * max(0.0, min(1.0, (value - low) / (high - low))))
    rating = max(1, min(5, rating))
    return "★" * rating + "☆" * (5 - rating)


def track_character(track: Track) -> str:
    tags: list[str] = []
    if track.straight_bias >= 5:
        tags.append("Fast")
    elif track.straight_bias <= 2:
        tags.append("Short-gear")
    else:
        tags.append("Mixed")
    if track.corner_difficulty >= 5:
        tags.append("Technical")
    elif track.corner_difficulty <= 2:
        tags.append("Flowing")
    if track.surface_roughness >= 4:
        tags.append("Rough")
    elif track.surface_roughness <= 1:
        tags.append("Smooth")
    if track.pit_difficulty >= 4:
        tags.append("Tough pits")
    if track.hazard_rate >= 17:
        tags.append("Hazard-heavy")
    return " · ".join(tags[:4])


def _part_specialisation_notes(team: Team, track: Track, weather: WeatherCondition) -> list[str]:
    notes: list[str] = []
    for part in BuildService.equipped_parts_by_slot(team).values():
        mapping = TRACK_SPECIALISATIONS.get(part.key, {})
        if track.key in mapping:
            mod = mapping[track.key]
            sign = sum(mod.as_dict().values())
            notes.append(f"{'✓' if sign >= 0 else '⚠'} {part.name} is {'well suited' if sign >= 0 else 'a compromise'} here")
        if weather.key in mapping:
            notes.append(f"✓ {part.name} matches {weather.name.lower()} conditions")
    return notes


def setup_notes(team: Team, track: Track, weather: WeatherCondition) -> list[str]:
    adjusted = BuildService.clamp_car_stats(
        BuildService.effective_car_stats(team) + track.modifiers + weather.modifiers + track_part_adjustment(team, track, weather)
    )
    notes = _part_specialisation_notes(team, track, weather)
    if adjusted.heat >= 7:
        notes.append("⚠ High heat could hurt late-race consistency")
    elif adjusted.heat <= 1:
        notes.append("✓ Heat management should stay comfortable")
    if adjusted.reliability >= 6:
        notes.append("✓ Strong reliability suits a long run")
    if adjusted.handling >= 6 and track.corner_difficulty >= 4:
        notes.append("✓ Cornering setup suits this technical layout")
    if adjusted.speed >= 6 and track.straight_bias >= 4:
        notes.append("✓ Straight-line setup should pay off here")
    strain = BuildService.build_strain(team)
    if strain >= 12:
        notes.append("⚠ Knife-edge strain makes the car harder on tyres and repairs")
    elif strain <= 3:
        notes.append("✓ Low strain gives the package a reliability cushion")
    illegal = BuildService.illegal_disqualification_risk_percent(team)
    if illegal:
        notes.append(f"⚠ Illegal hardware carries {illegal}% pre-race DSQ risk")
    if not notes:
        notes.append("• Neutral setup: no major venue advantage or warning")
    # Keep the pre-race card compact.
    deduped: list[str] = []
    for note in notes:
        if note not in deduped:
            deduped.append(note)
    return deduped[:4]


def team_setup_summary(team: Team, track: Track, weather: WeatherCondition, carryover_damage: int = 0) -> str:
    adjusted = BuildService.clamp_car_stats(
        BuildService.effective_car_stats(team) + track.modifiers + weather.modifiers + track_part_adjustment(team, track, weather)
    )
    straight = adjusted.speed * 0.58 + adjusted.acceleration * 0.42
    corner = adjusted.handling * 0.62 + adjusted.braking * 0.38
    reliability = adjusted.reliability * 0.58 + adjusted.durability * 0.42
    pit = adjusted.pit_friendliness * 0.55 + team.stats.mechanics * 0.45
    lines = [
        f"Straight-line: {_stars(straight)}  Cornering: {_stars(corner)}",
        f"Reliability: {_stars(reliability)}  Pit work: {_stars(pit)}",
        f"Strain: **{BuildService.build_strain_label(team)}** · Tuning: **{BuildService.tuning_efficiency(team) * 100:.0f}%**",
    ]
    if carryover_damage:
        lines.append(f"Carryover damage: **{carryover_damage}%**")
    lines.extend(setup_notes(team, track, weather))
    return "\n".join(lines)[:1024]



def leaderboard_embed(context: dict, lap: int, laps: int) -> discord.Embed | None:
    board = context.get("leaderboard") if context else None
    if not isinstance(board, list) or not board:
        return None
    embed = discord.Embed(
        title=f"Live Leaderboard — Lap {lap}/{laps}",
        description=f"**{phase_label(lap, laps)}** · gaps are estimates from simulated elapsed race time.",
        color=discord.Color.blurple(),
    )
    lines = []
    for row in board[:10]:
        lines.append(
            f"**P{row['position']} {row['team_name']}** — {row['gap']} · "
            f"DMG {row['damage']}% · TYR {row['tyres']}% · {row['strain']}"
        )
    embed.add_field(name="Running Order", value="\n".join(lines)[:1024], inline=False)
    return embed


def phase_embed(lap: int, laps: int) -> discord.Embed:
    phase = phase_for_lap(lap, laps)
    descriptions = {
        "opening": "Reflexes and acceleration matter most while the field is tightly packed.",
        "mid": "Setup balance, traffic management and tyre condition start separating the field.",
        "pit": "Mechanics, crew specialists and pit-friendliness can recover—or lose—serious time.",
        "closing": "Reliability, damage, tyres and driver Nerve become increasingly important.",
        "final": "One lap left. Nerve, remaining grip and late-race momentum decide the finish.",
    }
    return discord.Embed(
        title=PHASE_LABELS.get(phase, "Race Phase"),
        description=descriptions.get(phase, "The race is underway."),
        color=discord.Color.dark_gold(),
    )


def event_explanation(event: RaceEvent) -> str | None:
    context = getattr(event, "context", None) or {}
    why = context.get("why")
    if why:
        return str(why)
    return None


def classification_embed(results: list[RaceResult], events: list[RaceEvent], title: str) -> discord.Embed:
    ordered = sorted(results, key=lambda result: result.position)
    reasons: dict[int, str] = {}
    for event in events:
        if event.event_type not in {EventType.DESTROYED, EventType.DISQUALIFIED} or not event.actor:
            continue
        team_id = int(event.actor.get("team_id", 0))
        if team_id:
            reasons[team_id] = event.message

    embed = discord.Embed(
        title=f"Final Classification — {title}",
        description="Official finishers score. DNFs and DSQs are classified behind finishers and score zero.",
        color=discord.Color.gold(),
    )
    winner_time = next((r.total_time for r in ordered if is_official_finisher(r)), None)
    lines: list[str] = []
    for result in ordered:
        if result.disqualified:
            status = "DSQ — 0 pts"
        elif result.dnf:
            status = f"DNF L{result.laps_completed} — 0 pts"
        else:
            gap = "WINNER" if result.position == 1 else f"+{max(0.0, result.total_time - (winner_time or result.total_time)):.1f}s"
            status = f"{gap} · {result.points} pts"
        lines.append(f"**P{result.position} {result.team_name}** — {status}")
    embed.add_field(name="Classification", value="\n".join(lines)[:1024], inline=False)

    failures = []
    for result in ordered:
        if result.dnf or result.disqualified:
            reason = reasons.get(result.team_id, "Race-ending incident recorded.")
            failures.append(f"**{result.team_name}:** {reason}")
    if failures:
        embed.add_field(name="DNF / DSQ Report", value="\n".join(failures)[:1024], inline=False)

    finishers = [result for result in ordered if is_official_finisher(result) and result.fastest_lap is not None]
    if finishers:
        fastest = min(finishers, key=lambda result: float(result.fastest_lap or 10**9))
        embed.add_field(
            name="⚡ Fastest Lap",
            value=f"**{fastest.team_name}** — {float(fastest.fastest_lap):.2f}s",
            inline=True,
        )
    embed.add_field(
        name="Race Condition",
        value=(
            f"Finishers: **{sum(1 for r in ordered if is_official_finisher(r))}** · "
            f"DNF: **{sum(1 for r in ordered if r.dnf and not r.disqualified)}** · "
            f"DSQ: **{sum(1 for r in ordered if r.disqualified)}**"
        ),
        inline=True,
    )
    return embed
