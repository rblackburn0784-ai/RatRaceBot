import discord

from data.defaults import CREW_MEMBERS, PARTS
from models.enums import CrewSlot, PartSlot
from services.builds import BuildService
from services.race_rules import official_winner


PROFILE_KEYS = {
    "races": 0,
    "wins": 0,
    "podiums": 0,
    "warnings": 0,
    "dnfs": 0,
    "disqualifications": 0,
    "overtakes": 0,
    "crashes": 0,
    "illegal_moves": 0,
    "last_minute_wins": 0,
    "pit_stops": 0,
    "near_misses": 0,
    "total_damage": 0,
    "peak_damage": 0,
}


def _value(profile, key: str) -> int:
    if not profile:
        return PROFILE_KEYS[key]
    return int(profile[key])


def reputation_tags(profile) -> list[str]:
    races = _value(profile, "races")
    if races <= 0:
        return ["Unproven Rookie"]

    tags = []
    wins = _value(profile, "wins")
    podiums = _value(profile, "podiums")
    overtakes = _value(profile, "overtakes")
    crashes = _value(profile, "crashes")
    illegal_moves = _value(profile, "illegal_moves")
    warnings = _value(profile, "warnings")
    disqualifications = _value(profile, "disqualifications")
    last_minute_wins = _value(profile, "last_minute_wins")
    pit_stops = _value(profile, "pit_stops")
    near_misses = _value(profile, "near_misses")
    dnfs = _value(profile, "dnfs")

    if wins >= 3 and wins / races >= 0.3:
        tags.append("Front Runner")
    if podiums >= 4 and podiums / races >= 0.45:
        tags.append("Podium Regular")
    if last_minute_wins >= 2:
        tags.append("Clutch Finisher")
    if overtakes / races >= 4:
        tags.append("Traffic Carver")
    if pit_stops / races >= 1.4:
        tags.append("Pit Lane Hero")
    if near_misses / races >= 1.5:
        tags.append("Thread-the-Needle Driver")
    if crashes / races >= 1.0 or dnfs / races >= 0.3:
        tags.append("Crash Magnet")
    if illegal_moves + warnings + disqualifications >= max(3, races * 2):
        tags.append("Black Flag Bait")

    return tags[:3] if tags else ["Steady Cruiser"]


def reputation_embed(team, profile) -> discord.Embed:
    tags = reputation_tags(profile)
    races = _value(profile, "races")
    embed = discord.Embed(
        title=f"Driver Reputation: {team.name}",
        description=f"{team.driver_name} in {team.car_name}",
        color=discord.Color.gold(),
    )
    embed.add_field(name="Reputation", value="\n".join(f"**{tag}**" for tag in tags), inline=False)
    embed.add_field(
        name="Record",
        value=(
            f"Races: **{races}**\n"
            f"Wins: **{_value(profile, 'wins')}**\n"
            f"Podiums: **{_value(profile, 'podiums')}**"
        ),
        inline=True,
    )
    embed.add_field(
        name="Style",
        value=(
            f"Overtakes: **{_value(profile, 'overtakes')}**\n"
            f"Near Misses: **{_value(profile, 'near_misses')}**\n"
            f"Last-Minute Wins: **{_value(profile, 'last_minute_wins')}**"
        ),
        inline=True,
    )
    embed.add_field(
        name="Trouble",
        value=(
            f"Crashes: **{_value(profile, 'crashes')}**\n"
            f"Illegal Moves: **{_value(profile, 'illegal_moves')}**\n"
            f"Warnings: **{_value(profile, 'warnings')}**\n"
            f"Disqualifications: **{_value(profile, 'disqualifications')}**"
        ),
        inline=True,
    )
    embed.add_field(
        name="Wear And Tear",
        value=(
            f"Pit Stops: **{_value(profile, 'pit_stops')}**\n"
            f"DNFs: **{_value(profile, 'dnfs')}**\n"
            f"Peak Damage: **{_value(profile, 'peak_damage')}%**"
        ),
        inline=True,
    )
    if races:
        average_damage = _value(profile, "total_damage") // races
        embed.add_field(name="Average Finish Damage", value=f"**{average_damage}%**", inline=True)
    return embed


def rivalries_embed(team, rivalries) -> discord.Embed:
    embed = discord.Embed(
        title=f"Team Rivalries: {team.name}",
        description=f"{team.driver_name} and {team.car_name}",
        color=discord.Color.red(),
    )
    if not rivalries:
        embed.add_field(
            name="No Rivalries Yet",
            value="Close finishes, crashes, and illegal moves will build rivalry heat over time.",
            inline=False,
        )
        return embed

    lines = []
    for index, rivalry in enumerate(rivalries, start=1):
        last_winner = rivalry["last_winner_name"] or "Unknown"
        lines.append(
            f"**{index}. {rivalry['opponent_name']}** - Heat **{rivalry['heat']}**\n"
            f"Races {rivalry['races']} | Close finishes {rivalry['close_finishes']} | "
            f"Contacts {rivalry['contacts']} | Illegal incidents {rivalry['illegal_incidents']} | "
            f"Last winner: {last_winner}"
        )
    embed.add_field(name="Hottest Matchups", value="\n\n".join(lines)[:1024], inline=False)
    return embed


def race_story_embed(rivalries) -> discord.Embed | None:
    hot = [rivalry for rivalry in rivalries if int(rivalry["heat"]) >= 5]
    if not hot:
        return None

    embed = discord.Embed(
        title="Rivalry Watch",
        description="The race stirred up a few grudges.",
        color=discord.Color.dark_red(),
    )
    lines = [
        f"**{row['team_a_name']}** vs **{row['team_b_name']}** - Heat **{row['heat']}**"
        for row in hot[:5]
    ]
    embed.add_field(name="Heating Up", value="\n".join(lines), inline=False)
    return embed


def race_recap_embed(results, title: str, track_name: str, weather_name: str | None = None) -> discord.Embed:
    ordered = sorted(results, key=lambda result: result.position)
    winner = official_winner(ordered)
    mover = max(ordered, key=lambda result: (result.overtakes, result.points, -result.position))
    hardest_hit = max(ordered, key=lambda result: (result.damage, result.crashes, result.tyre_wear))
    trouble = max(ordered, key=lambda result: (result.illegal_moves + result.warnings * 2, result.illegal_moves))
    pit_hero = max(ordered, key=lambda result: (result.pit_stops, -result.damage))
    near_miss = max(ordered, key=lambda result: (result.near_misses, result.points))

    embed = discord.Embed(
        title=f"Race Recap: {title}",
        description=f"{track_name}{f' | Weather: {weather_name}' if weather_name else ''}",
        color=discord.Color.blurple(),
    )
    embed.add_field(
        name="Winner",
        value=f"**{winner.team_name}** - {winner.driver_name}" if winner else "No official finisher",
        inline=False,
    )
    embed.add_field(name="Biggest Mover", value=f"**{mover.team_name}** - {mover.overtakes} overtakes", inline=True)
    embed.add_field(name="Hardest Hit", value=f"**{hardest_hit.team_name}** - {hardest_hit.damage}% damage", inline=True)
    embed.add_field(name="Most Questionable", value=f"**{trouble.team_name}** - {trouble.illegal_moves} illegal, {trouble.warnings} warnings", inline=True)
    embed.add_field(name="Pit Lane Hero", value=f"**{pit_hero.team_name}** - {pit_hero.pit_stops} stops", inline=True)
    embed.add_field(name="Near Miss Nerves", value=f"**{near_miss.team_name}** - {near_miss.near_misses} near misses", inline=True)
    return embed


def garage_summary_embed(team, profile, rivalries, in_open_tournament: bool) -> discord.Embed:
    stats = BuildService.effective_car_stats(team)
    illegal_risk = BuildService.illegal_disqualification_risk_percent(team)
    installed_slots = {PARTS[key].slot for key in team.parts if key in PARTS}
    crew_slots = {CrewSlot(slot) for slot in team.crew if slot in {crew_slot.value for crew_slot in CrewSlot}}
    missing_parts = [slot.value.title() for slot in PartSlot if slot not in installed_slots]
    missing_crew = [slot.value.replace("_", " ").title() for slot in CrewSlot if slot not in crew_slots]
    tags = reputation_tags(profile)

    embed = discord.Embed(
        title=f"Garage Summary: {team.name}",
        description=f"{team.driver_name} in {team.car_name}",
        color=discord.Color.green(),
    )
    embed.add_field(
        name="Status",
        value=(
            f"Tournament lock: **{'Team profile locked' if in_open_tournament else 'Editable'}**\n"
            f"Illegal part risk: **{illegal_risk}%**\n"
            f"Mechanical strain: **{BuildService.build_strain(team)} ({BuildService.build_strain_label(team)})**\n"
            f"Tuning efficiency: **{BuildService.tuning_efficiency(team) * 100:.0f}%**\n"
            f"Reputation: **{', '.join(tags)}**"
        ),
        inline=False,
    )
    embed.add_field(
        name="Rod Stats",
        value="\n".join(f"{key.replace('_', ' ').title()}: **{value:+d}**" for key, value in stats.as_dict().items()),
        inline=True,
    )
    embed.add_field(
        name="Loadout",
        value=(
            f"Parts fitted: **{len(installed_slots)}/{len(PartSlot)}**\n"
            f"Crew assigned: **{len(crew_slots)}/{len(CrewSlot)}**\n"
            f"Races logged: **{_value(profile, 'races')}**\n"
            f"Crew effects: {BuildService.crew_effect_summary(team)}"
        ),
        inline=True,
    )
    embed.add_field(
        name="Next Garage Jobs",
        value=(
            f"Parts: {', '.join(missing_parts[:4]) if missing_parts else 'All part slots fitted'}\n"
            f"Crew: {', '.join(missing_crew[:4]) if missing_crew else 'All crew positions assigned'}"
        ),
        inline=False,
    )
    if rivalries:
        hottest = rivalries[0]
        embed.add_field(
            name="Hottest Rivalry",
            value=f"**{hottest['opponent_name']}** - Heat **{hottest['heat']}**",
            inline=False,
        )
    return embed


def season_history_embed(rows) -> discord.Embed:
    embed = discord.Embed(
        title="Season History",
        description="Past tournament podiums and champions.",
        color=discord.Color.purple(),
    )
    if not rows:
        embed.add_field(name="No Seasons Yet", value="Completed tournament podiums will appear here.", inline=False)
        return embed

    embed.add_field(name="Hall Of Fame", value="\n\n".join(season_history_lines(rows))[:1024], inline=False)
    return embed


def season_history_lines(rows) -> list[str]:
    if not rows:
        return ["No completed seasons yet."]
    lines = []
    for row in rows:
        podium = [
            f"1st {row['champion_name'] or '-'}",
            f"2nd {row['runner_up_name'] or '-'}",
            f"3rd {row['third_name'] or '-'}",
        ]
        lines.append(f"**{row['tournament_name']}** - {', '.join(podium)}")
    return lines


def _leaderboard_lines(rows, value_label: str) -> str:
    if not rows:
        return "No records yet."
    return "\n".join(
        f"**{index}. {row['team_name']}** - {row[value_label]}"
        for index, row in enumerate(rows, start=1)
    )


def _stat_leader_lines(rows, label: str) -> str:
    if not rows:
        return f"**{label}:** No record yet."
    leader = rows[0]
    return f"**{label}:** {leader['team_name']} - {leader['stat_value']}"


def hall_of_fame_embed(champions, podiums, stat_leaders: dict[str, list], rivalries, recent_seasons) -> discord.Embed:
    embed = discord.Embed(
        title="Hall Of Fame",
        description="The loudest names in Rat Race history.",
        color=discord.Color.gold(),
    )
    embed.add_field(name="Tournament Champions", value=_leaderboard_lines(champions, "titles"), inline=True)
    embed.add_field(name="Podium Royalty", value=_leaderboard_lines(podiums, "podiums"), inline=True)

    record_lines = [
        _stat_leader_lines(stat_leaders.get("wins", []), "Most Wins"),
        _stat_leader_lines(stat_leaders.get("overtakes", []), "Most Overtakes"),
        _stat_leader_lines(stat_leaders.get("last_minute_wins", []), "Last-Minute Wins"),
        _stat_leader_lines(stat_leaders.get("pit_stops", []), "Pit Stops"),
        _stat_leader_lines(stat_leaders.get("near_misses", []), "Near Misses"),
        _stat_leader_lines(stat_leaders.get("crashes", []), "Crashes"),
        _stat_leader_lines(stat_leaders.get("illegal_moves", []), "Illegal Moves"),
        _stat_leader_lines(stat_leaders.get("peak_damage", []), "Peak Damage"),
    ]
    embed.add_field(name="Record Holders", value="\n".join(record_lines)[:1024], inline=False)

    if rivalries:
        rivalry_lines = [
            f"**{row['team_a_name']}** vs **{row['team_b_name']}** - Heat {row['heat']}"
            for row in rivalries[:5]
        ]
        embed.add_field(name="Fiercest Rivalries", value="\n".join(rivalry_lines), inline=False)
    else:
        embed.add_field(name="Fiercest Rivalries", value="No rivalries recorded yet.", inline=False)

    if recent_seasons:
        recent_lines = [
            f"**{row['tournament_name']}** - Champion: {row['champion_name'] or '-'}"
            for row in recent_seasons[:5]
        ]
        embed.add_field(name="Recent Seasons", value="\n".join(recent_lines), inline=False)
    return embed
