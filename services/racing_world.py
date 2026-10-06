from __future__ import annotations

from collections import defaultdict
import hashlib
import random
from typing import Iterable

import discord

from data.defaults import TRACKS
from models.domain import RaceEvent, RaceResult, Team
from models.enums import EventType
from services.race_rules import official_winner
from services.sponsors import sponsor_by_key


RIVALRY_HEAT_CAP = 100
RIVALRY_HOT = 50
RIVALRY_BOILING = 70

WORLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS rivalry_story_stats (
    team_a_id INTEGER NOT NULL,
    team_b_id INTEGER NOT NULL,
    overtakes INTEGER NOT NULL DEFAULT 0,
    championship_battles INTEGER NOT NULL DEFAULT 0,
    stolen_wins INTEGER NOT NULL DEFAULT 0,
    dnfs_caused INTEGER NOT NULL DEFAULT 0,
    last_incident TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_a_id, team_b_id)
);

CREATE TABLE IF NOT EXISTS racing_world_processed (
    race_id INTEGER PRIMARY KEY,
    processed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS world_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    race_id INTEGER NOT NULL UNIQUE,
    team_id INTEGER NOT NULL,
    event_key TEXT NOT NULL,
    title TEXT NOT NULL,
    prompt TEXT NOT NULL,
    option_a TEXT NOT NULL,
    option_b TEXT NOT NULL,
    outcome_a TEXT NOT NULL,
    outcome_b TEXT NOT NULL,
    choice TEXT,
    outcome TEXT,
    status TEXT NOT NULL DEFAULT 'pending',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    resolved_at TEXT
);
"""


WORLD_EVENTS = {
    "garage_break_in": {
        "title": "🔧 Garage Break-In",
        "prompt": "Someone got into the garage overnight. Nothing vital was taken, but the crew wants a response.",
        "a": "Lock the place down and keep it quiet.",
        "b": "Tell the paddock and make a show of standing your ground.",
        "outcome_a": "The crew tightens security and the matter disappears behind a locked roller door.",
        "outcome_b": "The story gets around the paddock. Nobody admits knowing anything, which means everybody knows something.",
    },
    "sponsor_dispute": {
        "title": "💼 Sponsor Dispute",
        "prompt": "A sponsor wants more visibility after the last race, while the crew thinks the garage is becoming a billboard.",
        "a": "Back the crew and keep the branding restrained.",
        "b": "Give the sponsor a bigger spotlight for the next story.",
        "outcome_a": "The crew gets its way and the garage keeps its old-school look.",
        "outcome_b": "The sponsor gets a louder mention and immediately starts acting like it owns a socket set.",
    },
    "local_newspaper_hype": {
        "title": "📰 Local Newspaper Hype",
        "prompt": "A local paper wants a feature before the next race and is fishing for a quote that will sell copies.",
        "a": "Play it respectful and talk up the racing.",
        "b": "Give them a spicy quote about the opposition.",
        "outcome_a": "The article paints the team as proper racers with grease under their fingernails.",
        "outcome_b": "The headline gets louder, and at least one rival pins the clipping to a garage wall.",
    },
    "crew_argument": {
        "title": "🗯️ Crew Argument",
        "prompt": "The crew chief and lead mechanic disagree about what mattered most in the last result.",
        "a": "Settle it in a garage meeting.",
        "b": "Let each side prove its point at the next test.",
        "outcome_a": "The argument ends with tea, swearing and a surprisingly sensible checklist.",
        "outcome_b": "Both sides leave convinced the next race will prove them right.",
    },
    "surprise_inspection": {
        "title": "📋 Surprise Inspection",
        "prompt": "Officials announce a surprise paddock inspection. The car is legal, but the team can decide how to handle the attention.",
        "a": "Open the doors and cooperate.",
        "b": "Make them check every washer twice.",
        "outcome_a": "The inspection is painless and the officials leave with clean paperwork.",
        "outcome_b": "The inspection takes forever, but the crew enjoys every sarcastic minute of it.",
    },
    "engine_supplier_breakthrough": {
        "title": "⚙️ Engine Supplier Breakthrough",
        "prompt": "The engine supplier has a new idea and wants the team involved before anybody else hears about it.",
        "a": "Help test the concept quietly.",
        "b": "Keep the current package and ask for proven data first.",
        "outcome_a": "The team becomes part of the supplier's development story without changing race stats.",
        "outcome_b": "The crew keeps the known setup and waits for somebody else to find the expensive mistakes.",
    },
    "bad_weather_forecast": {
        "title": "🌧️ Bad Weather Forecast",
        "prompt": "The forecast for the next meeting looks ugly, but nobody trusts it enough to rebuild the car around a rumour.",
        "a": "Prepare the wet-weather checklist.",
        "b": "Ignore the gossip and stay focused on the normal setup.",
        "outcome_a": "Rain tyres and waterproofs move to the front of the garage plan.",
        "outcome_b": "The crew refuses to chase clouds until somebody can actually see one.",
    },
    "track_repairs": {
        "title": "🚧 Track Repairs",
        "prompt": "The next venue is repairing a rough section and asks teams whether they want the old bump left as character.",
        "a": "Back the repair and favour a cleaner surface.",
        "b": "Tell them the bump is part of the place.",
        "outcome_a": "The team publicly backs the repair crew and a smoother racing line.",
        "outcome_b": "The team votes for character, noise and suspension travel.",
    },
}


def pair_key(first_team_id: int, second_team_id: int) -> tuple[int, int]:
    return tuple(sorted((int(first_team_id), int(second_team_id))))


def heat_bar(heat: int) -> str:
    clamped = max(0, min(RIVALRY_HEAT_CAP, int(heat)))
    filled = min(10, max(0, round(clamped / 10)))
    return "█" * filled + "░" * (10 - filled)


async def ensure_world_schema(db) -> None:
    async with db.lock:
        conn = db._require()
        conn.executescript(WORLD_SCHEMA)
        conn.commit()


async def rivalry_heat_map(db, team_ids: Iterable[int]) -> dict[tuple[int, int], int]:
    ids = sorted({int(team_id) for team_id in team_ids if int(team_id) > 0})
    if len(ids) < 2:
        return {}
    await ensure_world_schema(db)
    placeholders = ",".join("?" for _ in ids)
    rows = await db.fetchall(
        f"""
        SELECT team_a_id, team_b_id, heat
        FROM team_rivalries
        WHERE team_a_id IN ({placeholders}) AND team_b_id IN ({placeholders})
        """,
        (*ids, *ids),
    )
    return {
        pair_key(int(row["team_a_id"]), int(row["team_b_id"])): min(RIVALRY_HEAT_CAP, int(row["heat"]))
        for row in rows
    }


def _event_team_id(data: dict | None) -> int:
    if not data:
        return 0
    try:
        return int(data.get("team_id") or 0)
    except (TypeError, ValueError):
        return 0


def _event_type(event: RaceEvent) -> EventType:
    return event.event_type if isinstance(event.event_type, EventType) else EventType(str(event.event_type))


def _signal(updates: dict, first_id: int, second_id: int) -> dict:
    key = pair_key(first_id, second_id)
    if key not in updates:
        updates[key] = {
            "team_a_id": key[0],
            "team_b_id": key[1],
            "heat": 0,
            "races": 1,
            "close_finishes": 0,
            "contacts": 0,
            "illegal_incidents": 0,
            "overtakes": 0,
            "championship_battles": 0,
            "stolen_wins": 0,
            "dnfs_caused": 0,
            "winner_id": None,
            "last_incident": "",
        }
    return updates[key]


def build_rivalry_updates(
    results: list[RaceResult],
    events: list[RaceEvent],
    championship_pairs: Iterable[tuple[int, int]] = (),
) -> list[dict]:
    updates: dict[tuple[int, int], dict] = {}
    valid_ids = {int(result.team_id) for result in results if int(result.team_id) > 0}
    final_lap = max((int(event.lap) for event in events), default=0)
    final_overtakes: dict[int, int] = {}
    overtake_counts: defaultdict[tuple[int, int], int] = defaultdict(int)

    for event in events:
        event_type = _event_type(event)
        actor_id = _event_team_id(event.actor)
        target_id = _event_team_id(event.target)
        if actor_id not in valid_ids:
            continue

        if event_type == EventType.OVERTAKE and target_id in valid_ids and actor_id != target_id:
            item = _signal(updates, actor_id, target_id)
            item["overtakes"] += 1
            item["heat"] += 1
            item["last_incident"] = "repeated overtakes"
            overtake_counts[pair_key(actor_id, target_id)] += 1
            if int(event.lap) == final_lap:
                final_overtakes[actor_id] = target_id

        elif event_type == EventType.ILLEGAL_MOVE and target_id in valid_ids and actor_id != target_id:
            item = _signal(updates, actor_id, target_id)
            item["contacts"] += 1
            item["illegal_incidents"] += 1
            item["heat"] += 4
            item["last_incident"] = "illegal contact"

        elif event_type in {EventType.DAMAGE_MINOR, EventType.DAMAGE_MAJOR} and target_id in valid_ids and actor_id != target_id:
            item = _signal(updates, actor_id, target_id)
            item["contacts"] += 1
            item["heat"] += 2 if event_type == EventType.DAMAGE_MINOR else 3
            item["last_incident"] = "contact"

        elif event_type == EventType.DESTROYED:
            caused_by = 0
            try:
                caused_by = int((event.context or {}).get("caused_by_team_id") or 0)
            except (TypeError, ValueError):
                caused_by = 0
            if caused_by in valid_ids and caused_by != actor_id:
                item = _signal(updates, actor_id, caused_by)
                item["dnfs_caused"] += 1
                item["contacts"] += 1
                item["heat"] += 8
                item["last_incident"] = "DNF caused by contact"

    for key, count in overtake_counts.items():
        if count >= 2:
            updates[key]["heat"] += min(3, count - 1)
            updates[key]["last_incident"] = "repeated overtakes"

    ordered = sorted(results, key=lambda result: int(result.position))
    for first, second in zip(ordered, ordered[1:]):
        if first.dnf or first.disqualified or second.dnf or second.disqualified:
            continue
        gap = abs(float(first.total_time) - float(second.total_time))
        if gap <= 5.0:
            item = _signal(updates, int(first.team_id), int(second.team_id))
            item["close_finishes"] += 1
            item["heat"] += 2
            item["winner_id"] = int(first.team_id)
            if not item["last_incident"]:
                item["last_incident"] = "close finish"

    winner = official_winner(results)
    if winner and int(winner.last_minute_wins) > 0:
        target_id = final_overtakes.get(int(winner.team_id))
        if target_id:
            item = _signal(updates, int(winner.team_id), target_id)
            item["stolen_wins"] += 1
            item["heat"] += 6
            item["winner_id"] = int(winner.team_id)
            item["last_incident"] = "stolen win"

    for first_id, second_id in championship_pairs:
        if first_id in valid_ids and second_id in valid_ids and first_id != second_id:
            item = _signal(updates, first_id, second_id)
            item["championship_battles"] += 1
            item["heat"] += 2
            if not item["last_incident"]:
                item["last_incident"] = "championship battle"

    for result in results:
        if int(result.team_id) <= 0:
            continue
        for item in updates.values():
            if int(result.team_id) in {item["team_a_id"], item["team_b_id"]}:
                if not result.dnf and not result.disqualified and (
                    item["winner_id"] is None
                    or int(result.position) < next(
                        (
                            int(other.position)
                            for other in results
                            if int(other.team_id) in {item["team_a_id"], item["team_b_id"]}
                            and int(other.team_id) != int(result.team_id)
                        ),
                        999,
                    )
                ):
                    item["winner_id"] = int(result.team_id)

    return list(updates.values())


async def _championship_pairs(db, race_id: int) -> list[tuple[int, int]]:
    if race_id <= 0:
        return []
    race = await db.get_race(race_id)
    if not race or race["tournament_id"] is None or int(race["championship_round"] or 0) != 1:
        return []
    rows = await db.standings(int(race["tournament_id"]))
    contenders = list(rows[:4])
    pairs = []
    for index, first in enumerate(contenders):
        for second in contenders[index + 1:]:
            if abs(int(first["points"]) - int(second["points"])) <= 12:
                pairs.append((int(first["team_id"]), int(second["team_id"])))
    return pairs


async def record_race_world(
    db,
    race_id: int,
    results: list[RaceResult],
    events: list[RaceEvent],
) -> dict:
    if race_id <= 0:
        return {"processed": False, "updates": []}
    await ensure_world_schema(db)
    championship_pairs = await _championship_pairs(db, race_id)
    updates = build_rivalry_updates(results, events, championship_pairs)

    async with db.lock:
        conn = db._require()
        try:
            conn.execute("BEGIN")
            if conn.execute("SELECT 1 FROM racing_world_processed WHERE race_id=?", (race_id,)).fetchone():
                conn.rollback()
                return {"processed": False, "updates": []}

            for item in updates:
                conn.execute(
                    """
                    INSERT INTO team_rivalries(
                        team_a_id, team_b_id, heat, races, close_finishes,
                        contacts, illegal_incidents, last_winner_id
                    )
                    VALUES (?, ?, MIN(?, 100), 1, ?, ?, ?, ?)
                    ON CONFLICT(team_a_id, team_b_id) DO UPDATE SET
                        heat = MIN(100, team_rivalries.heat + excluded.heat),
                        races = team_rivalries.races + 1,
                        close_finishes = team_rivalries.close_finishes + excluded.close_finishes,
                        contacts = team_rivalries.contacts + excluded.contacts,
                        illegal_incidents = team_rivalries.illegal_incidents + excluded.illegal_incidents,
                        last_winner_id = COALESCE(excluded.last_winner_id, team_rivalries.last_winner_id),
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        item["team_a_id"], item["team_b_id"], max(1, int(item["heat"])),
                        int(item["close_finishes"]), int(item["contacts"]), int(item["illegal_incidents"]),
                        item.get("winner_id"),
                    ),
                )
                conn.execute(
                    """
                    INSERT INTO rivalry_story_stats(
                        team_a_id, team_b_id, overtakes, championship_battles,
                        stolen_wins, dnfs_caused, last_incident
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(team_a_id, team_b_id) DO UPDATE SET
                        overtakes = rivalry_story_stats.overtakes + excluded.overtakes,
                        championship_battles = rivalry_story_stats.championship_battles + excluded.championship_battles,
                        stolen_wins = rivalry_story_stats.stolen_wins + excluded.stolen_wins,
                        dnfs_caused = rivalry_story_stats.dnfs_caused + excluded.dnfs_caused,
                        last_incident = CASE
                            WHEN excluded.last_incident <> '' THEN excluded.last_incident
                            ELSE rivalry_story_stats.last_incident
                        END,
                        updated_at = CURRENT_TIMESTAMP
                    """,
                    (
                        item["team_a_id"], item["team_b_id"], int(item["overtakes"]),
                        int(item["championship_battles"]), int(item["stolen_wins"]),
                        int(item["dnfs_caused"]), str(item["last_incident"]),
                    ),
                )

            conn.execute("INSERT INTO racing_world_processed(race_id) VALUES (?)", (race_id,))
            conn.commit()
            return {"processed": True, "updates": updates}
        except Exception:
            conn.rollback()
            raise


async def rivalry_watch_rows(db, team_ids: Iterable[int], limit: int = 5):
    ids = sorted({int(team_id) for team_id in team_ids if int(team_id) > 0})
    if len(ids) < 2:
        return []
    await ensure_world_schema(db)
    placeholders = ",".join("?" for _ in ids)
    return await db.fetchall(
        f"""
        SELECT r.*, a.name AS team_a_name, b.name AS team_b_name,
               COALESCE(s.overtakes, 0) AS overtakes,
               COALESCE(s.championship_battles, 0) AS championship_battles,
               COALESCE(s.stolen_wins, 0) AS stolen_wins,
               COALESCE(s.dnfs_caused, 0) AS dnfs_caused,
               COALESCE(s.last_incident, '') AS last_incident
        FROM team_rivalries r
        JOIN teams a ON a.id=r.team_a_id
        JOIN teams b ON b.id=r.team_b_id
        LEFT JOIN rivalry_story_stats s
          ON s.team_a_id=r.team_a_id AND s.team_b_id=r.team_b_id
        WHERE r.team_a_id IN ({placeholders})
          AND r.team_b_id IN ({placeholders})
        ORDER BY r.heat DESC, r.updated_at DESC
        LIMIT ?
        """,
        (*ids, *ids, int(limit)),
    )


def _rivalry_history_line(row) -> str:
    parts = []
    races = int(row["races"])
    contacts = int(row["contacts"])
    illegal = int(row["illegal_incidents"])
    overtakes = int(row["overtakes"])
    stolen = int(row["stolen_wins"])
    championship = int(row["championship_battles"])
    dnfs = int(row["dnfs_caused"])
    if races:
        parts.append(f"{races} race{'s' if races != 1 else ''}")
    if overtakes:
        parts.append(f"{overtakes} overtake{'s' if overtakes != 1 else ''}")
    if contacts:
        parts.append(f"{contacts} contact{'s' if contacts != 1 else ''}")
    if illegal:
        parts.append(f"{illegal} illegal incident{'s' if illegal != 1 else ''}")
    if championship:
        parts.append(f"{championship} title battle{'s' if championship != 1 else ''}")
    if stolen:
        parts.append(f"{stolen} stolen win{'s' if stolen != 1 else ''}")
    if dnfs:
        parts.append(f"{dnfs} caused DNF{'s' if dnfs != 1 else ''}")
    return ". ".join(parts[:3]) + ("." if parts else "The grudge is only getting started.")


async def rivalry_watch_embed(db, team_ids: Iterable[int], limit: int = 5) -> discord.Embed | None:
    rows = await rivalry_watch_rows(db, team_ids, limit=limit)
    hot = [row for row in rows if int(row["heat"]) >= 12]
    if not hot:
        return None
    top_heat = int(hot[0]["heat"])
    embed = discord.Embed(
        title="🔥 RIVALRY INTENSIFIES" if top_heat >= RIVALRY_HOT else "Rivalry Watch",
        description="Old grudges are now part of the race story.",
        color=discord.Color.dark_red(),
    )
    lines = []
    for row in hot:
        heat = min(RIVALRY_HEAT_CAP, int(row["heat"]))
        lines.append(
            f"**{row['team_a_name']} vs {row['team_b_name']}**\n"
            f"Heat: {heat_bar(heat)} **{heat}**\n"
            f"{_rivalry_history_line(row)}"
        )
    embed.add_field(name="Blacktop Feuds", value="\n\n".join(lines)[:1024], inline=False)
    return embed


def rivalry_story_text(rows) -> str:
    if not rows:
        return "No feud dominated the paddock this time."
    row = rows[0]
    heat = min(RIVALRY_HEAT_CAP, int(row["heat"]))
    incident = str(row["last_incident"] or "another hard race")
    return f"{row['team_a_name']} vs {row['team_b_name']} sits at {heat} heat after {incident}."


async def build_gazette_story(
    db,
    *,
    race_id: int,
    track_key: str,
    results: list[RaceResult],
    events: list[RaceEvent],
    teams: list[Team],
) -> dict[str, str]:
    winner = official_winner(results)
    if not winner:
        return {}
    ordered = sorted(results, key=lambda result: int(result.position))
    mover = max(ordered, key=lambda result: (int(result.overtakes), int(result.points), -int(result.position)))
    trouble = max(ordered, key=lambda result: (int(result.illegal_moves) + int(result.warnings) * 2 + (4 if result.disqualified else 0), int(result.crashes)))
    crash_total = sum(int(result.crashes) for result in results)
    illegal_total = sum(int(result.illegal_moves) for result in results)
    team_ids = [int(result.team_id) for result in results if int(result.team_id) > 0]
    rivalry_rows = await rivalry_watch_rows(db, team_ids, limit=1)

    championship = "Exhibition race — no championship table attached."
    upcoming = "Next race: paddock schedule not yet posted."
    race = await db.get_race(race_id) if race_id > 0 else None
    if race and race["tournament_id"] is not None:
        tournament_id = int(race["tournament_id"])
        standings = await db.standings(tournament_id)
        if standings:
            leader = standings[0]
            if len(standings) > 1:
                gap = int(leader["points"]) - int(standings[1]["points"])
                championship = f"{leader['name']} lead the championship on {leader['points']} pts, {gap} ahead."
            else:
                championship = f"{leader['name']} lead the championship on {leader['points']} pts."
        try:
            next_round = await db.next_scheduled_track(tournament_id)
        except (AttributeError, ValueError):
            next_round = None
        if next_round:
            round_no, next_key = next_round
            next_name = TRACKS[next_key].name if next_key in TRACKS else str(next_key)
            upcoming = f"Up next: Round {round_no} at {next_name}."
        else:
            upcoming = "Championship calendar complete — the season verdict is in."

    stolen = int(winner.last_minute_wins) > 0
    if stolen:
        headline = f"{winner.team_name.upper()} STEAL IT AT {TRACKS[track_key].name.upper()}"
    elif crash_total + illegal_total >= 8:
        headline = f"{winner.team_name.upper()} SURVIVE BLACKTOP CHAOS"
    elif rivalry_rows and int(rivalry_rows[0]["heat"]) >= RIVALRY_BOILING:
        headline = f"{winner.team_name.upper()} WIN AS FEUD BOILS OVER"
    else:
        headline = f"{winner.team_name.upper()} TAKE {TRACKS[track_key].name.upper()}"

    if trouble.disqualified:
        scandal = f"{trouble.team_name} leave under a black flag after a race full of questions."
    elif int(trouble.illegal_moves) > 0:
        scandal = f"{trouble.team_name} collect {trouble.illegal_moves} illegal move(s) and {trouble.warnings} warning(s)."
    elif crash_total:
        hardest = max(ordered, key=lambda result: (int(result.damage), int(result.crashes)))
        scandal = f"{hardest.team_name} finish with {hardest.damage}% damage after the roughest ride."
    else:
        scandal = "Officials report a surprisingly clean night on the blacktop."

    pit_hero = max(ordered, key=lambda result: (int(result.pit_stops), -int(result.damage)))
    quote_seed = int(hashlib.sha256(f"{race_id}:{winner.team_id}:quote".encode()).hexdigest()[:8], 16)
    quote_rng = random.Random(quote_seed)
    quote = quote_rng.choice((
        f'"We kept our heads when everybody else started leaning on doors." — {winner.driver_name}',
        f'"The car was talking all night. We just listened before it started shouting." — {winner.driver_name}',
        f'"Nobody wins one of these alone. Ask the crew how much metal is still underneath it." — {winner.driver_name}',
        f'"We saw the gap and decided apologies could wait until after the flag." — {winner.driver_name}',
    ))
    if int(pit_hero.pit_stops) > 0:
        quote += f" Pit-lane note: {pit_hero.team_name} made {pit_hero.pit_stops} stop(s)."

    teams_by_id = {int(team.id): team for team in teams if team.id}
    winner_team = teams_by_id.get(int(winner.team_id))
    sponsor_story = "Sponsor row stays quiet after this one."
    if winner_team and winner_team.active_sponsor_key:
        sponsor = sponsor_by_key(winner_team.active_sponsor_key)
        if sponsor:
            sponsor_story = f"{sponsor.name} gets the winner's spotlight with {winner.team_name}."

    return {
        "headline": headline,
        "race_winner": f"{winner.team_name} — {winner.driver_name}",
        "championship_situation": championship,
        "biggest_move": f"{mover.team_name}: {mover.overtakes} overtakes on the way to P{mover.position}.",
        "scandal": scandal,
        "rivalry_story": rivalry_story_text(rivalry_rows),
        "pit_lane_quote": quote,
        "sponsor_story": sponsor_story,
        "upcoming_race": upcoming,
    }


async def maybe_create_world_event(
    db,
    *,
    race_id: int,
    track_key: str,
    teams: list[Team],
) -> dict | None:
    if race_id <= 0 or not teams:
        return None
    await ensure_world_schema(db)
    existing = await db.fetchone("SELECT * FROM world_events WHERE race_id=?", (race_id,))
    if existing:
        return dict(existing)

    digest = hashlib.sha256(f"world:{race_id}:{track_key}".encode()).digest()
    roll = int.from_bytes(digest[:2], "big") / 65535
    if roll > 0.24:
        return None

    candidates = [team for team in teams if team.id and int(team.id) > 0]
    if not candidates:
        return None
    team = candidates[int.from_bytes(digest[2:4], "big") % len(candidates)]
    keys = list(WORLD_EVENTS)
    key = keys[int.from_bytes(digest[4:6], "big") % len(keys)]
    definition = WORLD_EVENTS[key]
    await db.execute(
        """
        INSERT OR IGNORE INTO world_events(
            race_id, team_id, event_key, title, prompt,
            option_a, option_b, outcome_a, outcome_b
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            race_id, int(team.id), key, definition["title"], definition["prompt"],
            definition["a"], definition["b"], definition["outcome_a"], definition["outcome_b"],
        ),
    )
    row = await db.fetchone("SELECT * FROM world_events WHERE race_id=?", (race_id,))
    return dict(row) if row else None


def world_event_embed(event: dict) -> discord.Embed:
    status = str(event.get("status") or "pending")
    embed = discord.Embed(
        title=str(event["title"]),
        description=str(event["prompt"]),
        color=discord.Color.orange(),
    )
    if status == "pending":
        embed.add_field(name="A", value=str(event["option_a"]), inline=False)
        embed.add_field(name="B", value=str(event["option_b"]), inline=False)
        embed.set_footer(text=f"World Event #{event['id']} — choose with /world_event_choose")
    else:
        embed.add_field(name=f"Choice {event.get('choice', '?')}", value=str(event.get("outcome") or "Resolved."), inline=False)
    return embed


async def pending_world_events(db, team_id: int | None = None):
    await ensure_world_schema(db)
    if team_id is None:
        return await db.fetchall(
            "SELECT * FROM world_events WHERE status='pending' ORDER BY id DESC LIMIT 10"
        )
    return await db.fetchall(
        "SELECT * FROM world_events WHERE status='pending' AND team_id=? ORDER BY id DESC LIMIT 10",
        (int(team_id),),
    )


async def resolve_world_event(db, event_id: int, choice: str) -> dict | None:
    await ensure_world_schema(db)
    row = await db.fetchone("SELECT * FROM world_events WHERE id=?", (int(event_id),))
    if not row:
        return None
    event = dict(row)
    if event["status"] != "pending":
        return event
    choice = str(choice).upper()
    if choice not in {"A", "B"}:
        raise ValueError("Choice must be A or B.")
    outcome = event["outcome_a"] if choice == "A" else event["outcome_b"]
    await db.execute(
        """
        UPDATE world_events
        SET choice=?, outcome=?, status='resolved', resolved_at=CURRENT_TIMESTAMP
        WHERE id=? AND status='pending'
        """,
        (choice, outcome, int(event_id)),
    )
    updated = await db.fetchone("SELECT * FROM world_events WHERE id=?", (int(event_id),))
    return dict(updated) if updated else None
