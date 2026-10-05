import random
from dataclasses import dataclass

import discord

from data.defaults import WEATHER_CONDITIONS
from models.domain import RaceEvent, RaceResult, Team
from models.enums import EventType
from services.race_rules import is_official_finisher, official_winner
from models.stats import CarStats
from services.story import reputation_tags
from services.progression import level_for_xp, unlock_lines, next_unlock
from services.sponsors import sponsor_by_key, sponsors_for_level


@dataclass(frozen=True)
class DriverTrait:
    key: str
    name: str
    description: str
    modifiers: CarStats


DRIVER_TRAITS = (
    DriverTrait("late_braker", "Late Braker", "Finds time under braking, occasionally scares the pit wall.", CarStats(braking=1, heat=1)),
    DriverTrait("smooth_operator", "Smooth Operator", "Kind to tyres and tidy through traffic.", CarStats(handling=1, reliability=1, intimidation=-1)),
    DriverTrait("hothead", "Hothead", "Aggressive in a scrap and never knowingly calm.", CarStats(intimidation=2, reliability=-1, heat=1)),
    DriverTrait("rain_specialist", "Rain Specialist", "Looks happier when everyone else is sliding, but gives away a little dry-road pace.", CarStats(speed=-1, handling=1, braking=1)),
    DriverTrait("clutch_nerves", "Clutch Nerves", "Finds an extra breath when the finish is close, but brakes a shade conservatively early on.", CarStats(acceleration=1, braking=-1, reliability=1)),
    DriverTrait("tyre_shredder", "Tyre Shredder", "Launches hard and asks questions later.", CarStats(acceleration=2, durability=-1)),
    DriverTrait("pit_whisperer", "Pit Whisperer", "Turns messy stops into survivable ones.", CarStats(pit_friendliness=2, speed=-1)),
    DriverTrait("showboat", "Showboat", "The crowd loves it. The stopwatch sometimes does.", CarStats(intimidation=1, heat=1, reliability=-1)),
)

COSMETIC_TITLES = {
    1: "Garage Rookie",
    2: "Backroad Regular",
    3: "Pit Lane Name",
    4: "Blacktop Threat",
    5: "Main Event Material",
    7: "Crowd Favorite",
    10: "Legend In Primer",
}



def team_traits(team: Team) -> list[DriverTrait]:
    seed = f"{team.id}:{team.name}:{team.driver_name}:{team.car_name}"
    rng = random.Random(seed)
    traits = list(DRIVER_TRAITS)
    rng.shuffle(traits)
    return traits[:2]


def trait_modifiers(team: Team) -> CarStats:
    total = CarStats()
    for trait in team_traits(team):
        total = total + trait.modifiers
    return total


def traits_text(team: Team) -> str:
    return "\n".join(f"**{trait.name}:** {trait.description}" for trait in team_traits(team))


def cosmetic_title_for_level(level: int) -> str:
    title = "Garage Rookie"
    for required_level, candidate in sorted(COSMETIC_TITLES.items()):
        if level >= required_level:
            title = candidate
    return title


def available_titles_for_level(level: int) -> list[str]:
    return [
        title
        for required_level, title in sorted(COSMETIC_TITLES.items())
        if level >= required_level
    ]


def xp_for_result(result: RaceResult | dict) -> int:
    getter = result.get if isinstance(result, dict) else lambda key, default=0: getattr(result, key, default)
    action_xp = int(getter("overtakes", 0)) + int(getter("near_misses", 0))
    if getter("disqualified", False):
        return max(3, 3 + action_xp // 2)
    if getter("dnf", False):
        return max(5, 5 + action_xp)
    position = int(getter("position"))
    xp = 10 + max(0, 11 - position) * 2 + action_xp
    xp += int(getter("last_minute_wins", 0)) * 8
    xp += 8 if position == 1 else 0
    return max(3, xp)


def achievement_candidates(result: RaceResult | dict, profile) -> list[tuple[str, str]]:
    getter = result.get if isinstance(result, dict) else lambda key, default=0: getattr(result, key, default)
    achievements = []
    official_finisher = is_official_finisher(result)
    if official_finisher and int(getter("position")) == 1:
        achievements.append(("first_win", "First Win"))
    if official_finisher and int(getter("damage", 0)) >= 90:
        achievements.append(("barely_alive", "Finished On A Prayer"))
    if int(getter("overtakes", 0)) >= 6:
        achievements.append(("overtake_machine", "Overtake Machine"))
    if int(getter("illegal_moves", 0)) > 0 and not getter("disqualified", False):
        achievements.append(("illegal_and_lucky", "Illegal And Lucky"))
    if official_finisher and int(getter("last_minute_wins", 0)) > 0:
        achievements.append(("last_lap_thief", "Last-Lap Thief"))
    if profile and int(profile["podiums"]) >= 3:
        achievements.append(("three_podiums", "Three Podiums"))
    return achievements


def hype_score(results: list[RaceResult], events: list[RaceEvent]) -> tuple[int, str]:
    score = 0
    score += sum(result.overtakes for result in results)
    score += sum(result.crashes for result in results) * 2
    score += sum(result.illegal_moves for result in results) * 2
    score += sum(result.near_misses for result in results)
    score += sum(result.last_minute_wins for result in results) * 8
    score += sum(4 for event in events if event.event_type in {EventType.DESTROYED, EventType.DISQUALIFIED})
    if score >= 45:
        label = "Total Mayhem"
    elif score >= 30:
        label = "Instant Classic"
    elif score >= 16:
        label = "Proper Scrap"
    else:
        label = "Quiet Night"
    return score, label


def hype_embed(results: list[RaceResult], events: list[RaceEvent], title: str) -> discord.Embed:
    score, label = hype_score(results, events)
    embed = discord.Embed(
        title=f"Crowd Hype: {label}",
        description=f"{title} scored **{score}** hype.",
        color=discord.Color.orange(),
    )
    embed.add_field(
        name="Why The Crowd Reacted",
        value=(
            f"Overtakes: **{sum(result.overtakes for result in results)}**\n"
            f"Crashes: **{sum(result.crashes for result in results)}**\n"
            f"Illegal moves: **{sum(result.illegal_moves for result in results)}**\n"
            f"Near misses: **{sum(result.near_misses for result in results)}**"
        ),
        inline=False,
    )
    return embed


def newspaper_embed(results: list[RaceResult], title: str, track_name: str, weather_name: str) -> discord.Embed:
    ordered = sorted(results, key=lambda result: result.position)
    winner = official_winner(ordered)
    mover = max(ordered, key=lambda result: (result.overtakes, result.points))
    trouble = max(ordered, key=lambda result: (result.illegal_moves + result.warnings, result.crashes))
    headline = f"{winner.team_name} Takes {track_name}" if winner else f"No Classified Winner At {track_name}"
    embed = discord.Embed(
        title="Blacktop Gazette",
        description=f"**{headline}**\n{title} ran under {weather_name}.",
        color=discord.Color.dark_grey(),
    )
    lead_story = (
        f"{winner.driver_name} brought **{winner.team_name}** home first."
        if winner
        else "Attrition took the whole field: no official winner or podium was awarded."
    )
    embed.add_field(name="Lead Story", value=lead_story, inline=False)
    embed.add_field(name="Big Move", value=f"**{mover.team_name}** made {mover.overtakes} overtakes.", inline=True)
    embed.add_field(name="Scandal Note", value=f"**{trouble.team_name}** drew {trouble.warnings} warnings and {trouble.illegal_moves} illegal moves.", inline=True)
    return embed


def interview_embed(team: Team, result: RaceResult, profile) -> discord.Embed:
    traits = team_traits(team)
    tags = reputation_tags(profile)
    quote_bank = [
        "The car had more left. I just ran out of road to prove it.",
        "Tell the officials I said thanks for noticing the paintwork.",
        "That was not luck. That was preparation with worse lighting.",
        "We heard the crowd on the last lap and found another gear.",
        "The crew earned that one. I mostly held on and looked busy.",
    ]
    rng = random.Random(f"{team.id}:{result.position}:{result.total_time}")
    embed = discord.Embed(
        title=f"Post-Race Interview: {team.name}",
        description=f'"{rng.choice(quote_bank)}"',
        color=discord.Color.teal(),
    )
    embed.add_field(name="Driver", value=team.driver_name, inline=True)
    embed.add_field(name="Finish", value=f"P{result.position}", inline=True)
    embed.add_field(name="Trait Flavor", value=", ".join(trait.name for trait in traits), inline=False)
    embed.add_field(name="Reputation", value=", ".join(tags), inline=False)
    return embed


def sponsor_offer(team: Team, race_id: int, level: int = 1) -> tuple[str, str, str, str]:
    eligible = sponsors_for_level(level)
    if not eligible:
        eligible = sponsors_for_level(1)
    rng = random.Random(f"sponsor:{team.id}:{race_id}:{team.name}:{level}")
    sponsor = rng.choice(eligible)
    return sponsor.key, sponsor.name, sponsor.benefit_text, sponsor.drawback_text


def weather_name(weather_key: str | None) -> str:
    if weather_key and weather_key in WEATHER_CONDITIONS:
        return WEATHER_CONDITIONS[weather_key].name
    return "Unknown Weather"


def progress_embed(team: Team, progress, achievements, sponsors, fatigue) -> discord.Embed:
    xp = int(progress["xp"]) if progress else 0
    level = level_for_xp(xp)
    title = progress["cosmetic_title"] if progress else cosmetic_title_for_level(level)
    active = sponsor_by_key(getattr(team, "active_sponsor_key", None))
    embed = discord.Embed(
        title=f"Team Progress: {team.name}",
        description=f"Cosmetic title: **{title}**",
        color=discord.Color.green(),
    )
    embed.add_field(name="Level", value=f"**{level}**", inline=True)
    embed.add_field(name="XP", value=f"**{xp}**", inline=True)
    next_level_xp = level * 100 if level < 10 else xp
    embed.add_field(
        name="Next Unlock",
        value=(f"{max(0, next_level_xp - xp)} XP to go\n{next_unlock(level)}" if level < 10 else next_unlock(level)),
        inline=False,
    )
    embed.add_field(name="Unlocked Team Options", value="\n".join(f"• {line}" for line in unlock_lines(level)), inline=False)
    embed.add_field(name="Driver Traits", value=traits_text(team), inline=False)
    if active:
        embed.add_field(
            name="Active Sponsor Contract",
            value=f"**{active.name}**\nBenefit: {active.benefit_text}\nTrade-off: {active.drawback_text}",
            inline=False,
        )
    else:
        embed.add_field(name="Active Sponsor Contract", value="Independent — no sponsor trade-off active.", inline=False)
    if achievements:
        embed.add_field(
            name="Achievements",
            value="\n".join(f"**{row['achievement_name']}**" for row in achievements[:8]),
            inline=False,
        )
    else:
        embed.add_field(name="Achievements", value="No badges yet.", inline=False)
    offered = [row for row in sponsors if row["status"] == "offered"] if sponsors else []
    if offered:
        offer = offered[0]
        embed.add_field(
            name="Latest Sponsor Offer",
            value=f"**{offer['sponsor_name']}**\n{offer['benefit_text']}\nDrawback: {offer['drawback_text']}",
            inline=False,
        )
    if fatigue:
        embed.add_field(
            name="Fatigue",
            value=f"**{fatigue['fatigue_name']}** - {fatigue['description']} ({fatigue['races_remaining']} race left)",
            inline=False,
        )
    return embed


def sponsor_offers_embed(team: Team, offers) -> discord.Embed:
    active = sponsor_by_key(getattr(team, "active_sponsor_key", None))
    embed = discord.Embed(
        title=f"Sponsor Paddock: {team.name}",
        description="One active sponsor at a time. Every contract has a race benefit and a real trade-off.",
        color=discord.Color.dark_gold(),
    )
    if active:
        embed.add_field(
            name="Active Contract",
            value=f"**{active.name}**\nBenefit: {active.benefit_text}\nTrade-off: {active.drawback_text}",
            inline=False,
        )
    else:
        embed.add_field(name="Active Contract", value="Independent — no sponsor currently affects the car.", inline=False)
    if not offers:
        embed.add_field(name="No Offers Yet", value="Podiums and strong race moments can attract sponsors.", inline=False)
        return embed
    lines = [
        f"**{row['sponsor_name']}** [{row['status'].title()}] - {row['benefit_text']}\nTrade-off: {row['drawback_text']}"
        for row in offers
    ]
    embed.add_field(name="Recent Offers", value="\n\n".join(lines)[:1024], inline=False)
    return embed


def track_records_embed(records, track_name: str | None = None) -> discord.Embed:
    embed = discord.Embed(
        title=f"Track Records{f': {track_name}' if track_name else ''}",
        description="Fast laps, chaos marks, and race-night legends.",
        color=discord.Color.blue(),
    )
    if not records:
        embed.add_field(name="No Records Yet", value="Run races to start filling the board.", inline=False)
        return embed
    lines = []
    for row in records[:20]:
        holder = f" - {row['team_name']}" if row["team_name"] else ""
        lines.append(f"**{row['track_key']} / {row['record_name']}**: {row['details']}{holder}")
    embed.add_field(name="Records", value="\n".join(lines)[:1024], inline=False)
    return embed
