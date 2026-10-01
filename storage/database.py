import asyncio
import json
from dataclasses import asdict
import sqlite3
from pathlib import Path
from typing import Any

from models.domain import Team
from models.enums import CarArchetype
from models.stats import DriverStats

MAX_TOURNAMENT_CARRYOVER_DAMAGE = 30
DAMAGE_CARRYOVER_DIVISOR = 4
DNF_CARRYOVER_PENALTY = 5

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    driver_name TEXT NOT NULL,
    pit_crew_name TEXT NOT NULL,
    car_name TEXT NOT NULL,
    archetype TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    parts_json TEXT NOT NULL DEFAULT '[]',
    owner_user_id INTEGER,
    crew_json TEXT NOT NULL DEFAULT '{}'
);

CREATE TABLE IF NOT EXISTS tournaments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'open',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS tournament_teams (
    tournament_id INTEGER NOT NULL,
    team_id INTEGER NOT NULL,
    points INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    podiums INTEGER NOT NULL DEFAULT 0,
    races INTEGER NOT NULL DEFAULT 0,
    warnings INTEGER NOT NULL DEFAULT 0,
    dnfs INTEGER NOT NULL DEFAULT 0,
    disqualifications INTEGER NOT NULL DEFAULT 0,
    overtakes INTEGER NOT NULL DEFAULT 0,
    crashes INTEGER NOT NULL DEFAULT 0,
    illegal_moves INTEGER NOT NULL DEFAULT 0,
    last_minute_wins INTEGER NOT NULL DEFAULT 0,
    pit_stops INTEGER NOT NULL DEFAULT 0,
    near_misses INTEGER NOT NULL DEFAULT 0,
    carryover_damage INTEGER NOT NULL DEFAULT 0,
    peak_carryover_damage INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (tournament_id, team_id)
);

CREATE TABLE IF NOT EXISTS races (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER,
    track_key TEXT NOT NULL,
    seed TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    events_json TEXT NOT NULL,
    results_json TEXT NOT NULL,
    replay_json TEXT
);

CREATE TABLE IF NOT EXISTS tournament_schedule (
    tournament_id INTEGER NOT NULL,
    race_number INTEGER NOT NULL,
    track_key TEXT NOT NULL,
    PRIMARY KEY (tournament_id, race_number)
);

CREATE TABLE IF NOT EXISTS team_profiles (
    team_id INTEGER PRIMARY KEY,
    races INTEGER NOT NULL DEFAULT 0,
    wins INTEGER NOT NULL DEFAULT 0,
    podiums INTEGER NOT NULL DEFAULT 0,
    warnings INTEGER NOT NULL DEFAULT 0,
    dnfs INTEGER NOT NULL DEFAULT 0,
    disqualifications INTEGER NOT NULL DEFAULT 0,
    overtakes INTEGER NOT NULL DEFAULT 0,
    crashes INTEGER NOT NULL DEFAULT 0,
    illegal_moves INTEGER NOT NULL DEFAULT 0,
    last_minute_wins INTEGER NOT NULL DEFAULT 0,
    pit_stops INTEGER NOT NULL DEFAULT 0,
    near_misses INTEGER NOT NULL DEFAULT 0,
    total_damage INTEGER NOT NULL DEFAULT 0,
    peak_damage INTEGER NOT NULL DEFAULT 0,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS team_rivalries (
    team_a_id INTEGER NOT NULL,
    team_b_id INTEGER NOT NULL,
    heat INTEGER NOT NULL DEFAULT 0,
    races INTEGER NOT NULL DEFAULT 0,
    close_finishes INTEGER NOT NULL DEFAULT 0,
    contacts INTEGER NOT NULL DEFAULT 0,
    illegal_incidents INTEGER NOT NULL DEFAULT 0,
    last_winner_id INTEGER,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_a_id, team_b_id)
);

CREATE TABLE IF NOT EXISTS season_history (
    tournament_id INTEGER PRIMARY KEY,
    tournament_name TEXT NOT NULL,
    champion_team_id INTEGER,
    champion_name TEXT,
    runner_up_team_id INTEGER,
    runner_up_name TEXT,
    third_team_id INTEGER,
    third_name TEXT,
    standings_json TEXT NOT NULL,
    completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS team_progress (
    team_id INTEGER PRIMARY KEY,
    xp INTEGER NOT NULL DEFAULT 0,
    cosmetic_title TEXT NOT NULL DEFAULT 'Garage Rookie',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS team_achievements (
    team_id INTEGER NOT NULL,
    achievement_key TEXT NOT NULL,
    achievement_name TEXT NOT NULL,
    unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (team_id, achievement_key)
);

CREATE TABLE IF NOT EXISTS sponsor_offers (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    team_id INTEGER NOT NULL,
    sponsor_name TEXT NOT NULL,
    benefit_text TEXT NOT NULL,
    drawback_text TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'offered',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS team_fatigue (
    team_id INTEGER PRIMARY KEY,
    fatigue_key TEXT NOT NULL,
    fatigue_name TEXT NOT NULL,
    description TEXT NOT NULL,
    races_remaining INTEGER NOT NULL DEFAULT 1,
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS track_records (
    track_key TEXT NOT NULL,
    record_key TEXT NOT NULL,
    record_name TEXT NOT NULL,
    record_value REAL NOT NULL,
    team_id INTEGER,
    team_name TEXT,
    race_id INTEGER,
    details TEXT NOT NULL DEFAULT '',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (track_key, record_key)
);
"""

class Database:
    def __init__(self, path: str):
        self.path = path
        self.conn: sqlite3.Connection | None = None
        self.lock = asyncio.Lock()

    async def init(self) -> None:
        Path(self.path).parent.mkdir(parents=True, exist_ok=True) if Path(self.path).parent != Path('.') else None
        self.conn = sqlite3.connect(self.path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(SCHEMA)
        self._migrate()
        self.conn.commit()

    def _migrate(self) -> None:
        conn = self._require()
        team_columns = {row["name"] for row in conn.execute("PRAGMA table_info(teams)").fetchall()}
        if "owner_user_id" not in team_columns:
            conn.execute("ALTER TABLE teams ADD COLUMN owner_user_id INTEGER")
        if "crew_json" not in team_columns:
            conn.execute("ALTER TABLE teams ADD COLUMN crew_json TEXT NOT NULL DEFAULT '{}'")
        conn.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_teams_owner_user_id ON teams(owner_user_id) WHERE owner_user_id IS NOT NULL"
        )

        race_columns = {row["name"] for row in conn.execute("PRAGMA table_info(races)").fetchall()}
        if "replay_json" not in race_columns:
            conn.execute("ALTER TABLE races ADD COLUMN replay_json TEXT")

        columns = {row["name"] for row in conn.execute("PRAGMA table_info(tournament_teams)").fetchall()}
        stat_columns = {
            "overtakes": "INTEGER NOT NULL DEFAULT 0",
            "crashes": "INTEGER NOT NULL DEFAULT 0",
            "illegal_moves": "INTEGER NOT NULL DEFAULT 0",
            "last_minute_wins": "INTEGER NOT NULL DEFAULT 0",
            "pit_stops": "INTEGER NOT NULL DEFAULT 0",
            "near_misses": "INTEGER NOT NULL DEFAULT 0",
            "carryover_damage": "INTEGER NOT NULL DEFAULT 0",
            "peak_carryover_damage": "INTEGER NOT NULL DEFAULT 0",
        }
        for column, definition in stat_columns.items():
            if column not in columns:
                conn.execute(f"ALTER TABLE tournament_teams ADD COLUMN {column} {definition}")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS team_profiles (
                team_id INTEGER PRIMARY KEY,
                races INTEGER NOT NULL DEFAULT 0,
                wins INTEGER NOT NULL DEFAULT 0,
                podiums INTEGER NOT NULL DEFAULT 0,
                warnings INTEGER NOT NULL DEFAULT 0,
                dnfs INTEGER NOT NULL DEFAULT 0,
                disqualifications INTEGER NOT NULL DEFAULT 0,
                overtakes INTEGER NOT NULL DEFAULT 0,
                crashes INTEGER NOT NULL DEFAULT 0,
                illegal_moves INTEGER NOT NULL DEFAULT 0,
                last_minute_wins INTEGER NOT NULL DEFAULT 0,
                pit_stops INTEGER NOT NULL DEFAULT 0,
                near_misses INTEGER NOT NULL DEFAULT 0,
                total_damage INTEGER NOT NULL DEFAULT 0,
                peak_damage INTEGER NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS team_rivalries (
                team_a_id INTEGER NOT NULL,
                team_b_id INTEGER NOT NULL,
                heat INTEGER NOT NULL DEFAULT 0,
                races INTEGER NOT NULL DEFAULT 0,
                close_finishes INTEGER NOT NULL DEFAULT 0,
                contacts INTEGER NOT NULL DEFAULT 0,
                illegal_incidents INTEGER NOT NULL DEFAULT 0,
                last_winner_id INTEGER,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (team_a_id, team_b_id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS season_history (
                tournament_id INTEGER PRIMARY KEY,
                tournament_name TEXT NOT NULL,
                champion_team_id INTEGER,
                champion_name TEXT,
                runner_up_team_id INTEGER,
                runner_up_name TEXT,
                third_team_id INTEGER,
                third_name TEXT,
                standings_json TEXT NOT NULL,
                completed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS team_progress (
                team_id INTEGER PRIMARY KEY,
                xp INTEGER NOT NULL DEFAULT 0,
                cosmetic_title TEXT NOT NULL DEFAULT 'Garage Rookie',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS team_achievements (
                team_id INTEGER NOT NULL,
                achievement_key TEXT NOT NULL,
                achievement_name TEXT NOT NULL,
                unlocked_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (team_id, achievement_key)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS sponsor_offers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                team_id INTEGER NOT NULL,
                sponsor_name TEXT NOT NULL,
                benefit_text TEXT NOT NULL,
                drawback_text TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'offered',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        sponsor_columns = {row["name"] for row in conn.execute("PRAGMA table_info(sponsor_offers)").fetchall()}
        if "status" not in sponsor_columns:
            conn.execute("ALTER TABLE sponsor_offers ADD COLUMN status TEXT NOT NULL DEFAULT 'offered'")
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS team_fatigue (
                team_id INTEGER PRIMARY KEY,
                fatigue_key TEXT NOT NULL,
                fatigue_name TEXT NOT NULL,
                description TEXT NOT NULL,
                races_remaining INTEGER NOT NULL DEFAULT 1,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS track_records (
                track_key TEXT NOT NULL,
                record_key TEXT NOT NULL,
                record_name TEXT NOT NULL,
                record_value REAL NOT NULL,
                team_id INTEGER,
                team_name TEXT,
                race_id INTEGER,
                details TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (track_key, record_key)
            )
            """
        )

    async def close(self) -> None:
        if self.conn:
            self.conn.close()
            self.conn = None

    def _require(self) -> sqlite3.Connection:
        if not self.conn:
            raise RuntimeError("Database not initialised")
        return self.conn

    async def execute(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Cursor:
        async with self.lock:
            cur = self._require().execute(sql, params)
            self._require().commit()
            return cur

    async def fetchall(self, sql: str, params: tuple[Any, ...] = ()) -> list[sqlite3.Row]:
        async with self.lock:
            return self._require().execute(sql, params).fetchall()

    async def fetchone(self, sql: str, params: tuple[Any, ...] = ()) -> sqlite3.Row | None:
        async with self.lock:
            return self._require().execute(sql, params).fetchone()

    async def create_team(self, team: Team) -> int:
        stats_json = json.dumps(asdict(team.stats))
        parts_json = json.dumps(team.parts)
        crew_json = json.dumps(team.crew)
        cur = await self.execute(
            """INSERT INTO teams(name, driver_name, pit_crew_name, car_name, archetype, stats_json, parts_json, owner_user_id, crew_json)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                team.name,
                team.driver_name,
                team.pit_crew_name,
                team.car_name,
                team.archetype.value,
                stats_json,
                parts_json,
                team.owner_user_id,
                crew_json,
            ),
        )
        return int(cur.lastrowid)

    @staticmethod
    def row_to_team(row: sqlite3.Row) -> Team:
        stats = DriverStats(**json.loads(row["stats_json"]))
        return Team(
            id=row["id"],
            name=row["name"],
            driver_name=row["driver_name"],
            pit_crew_name=row["pit_crew_name"],
            car_name=row["car_name"],
            archetype=CarArchetype(row["archetype"]),
            stats=stats,
            parts=json.loads(row["parts_json"]),
            owner_user_id=row["owner_user_id"] if "owner_user_id" in row.keys() else None,
            crew=json.loads(row["crew_json"]) if "crew_json" in row.keys() else {},
        )

    async def get_team(self, team_id: int) -> Team | None:
        row = await self.fetchone("SELECT * FROM teams WHERE id=?", (team_id,))
        return self.row_to_team(row) if row else None

    async def list_teams(self) -> list[Team]:
        rows = await self.fetchall("SELECT * FROM teams ORDER BY id")
        return [self.row_to_team(r) for r in rows]

    async def get_team_by_owner(self, owner_user_id: int) -> Team | None:
        row = await self.fetchone("SELECT * FROM teams WHERE owner_user_id=?", (owner_user_id,))
        return self.row_to_team(row) if row else None

    async def update_team_profile(self, team: Team) -> None:
        if team.id is None:
            raise ValueError("Team is missing an ID.")
        await self.execute(
            """
            UPDATE teams
            SET name=?, driver_name=?, pit_crew_name=?, car_name=?, archetype=?, stats_json=?
            WHERE id=?
            """,
            (
                team.name,
                team.driver_name,
                team.pit_crew_name,
                team.car_name,
                team.archetype.value,
                json.dumps(asdict(team.stats)),
                team.id,
            ),
        )

    async def team_in_open_tournament(self, team_id: int) -> bool:
        row = await self.fetchone(
            """
            SELECT 1
            FROM tournament_teams tt
            JOIN tournaments t ON t.id = tt.tournament_id
            WHERE tt.team_id=? AND t.status='open'
            LIMIT 1
            """,
            (team_id,),
        )
        return bool(row)

    async def delete_team(self, team_id: int) -> None:
        async with self.lock:
            conn = self._require()
            try:
                conn.execute("BEGIN")
                open_row = conn.execute(
                    """
                    SELECT 1
                    FROM tournament_teams tt
                    JOIN tournaments t ON t.id = tt.tournament_id
                    WHERE tt.team_id=? AND t.status='open'
                    LIMIT 1
                    """,
                    (team_id,),
                ).fetchone()
                if open_row:
                    raise ValueError("That team is in an open tournament. Close the tournament before deleting it.")

                conn.execute(
                    """
                    DELETE FROM tournament_teams
                    WHERE team_id=?
                      AND tournament_id IN (SELECT id FROM tournaments WHERE status!='open')
                    """,
                    (team_id,),
                )
                conn.execute("DELETE FROM team_profiles WHERE team_id=?", (team_id,))
                conn.execute("DELETE FROM team_progress WHERE team_id=?", (team_id,))
                conn.execute("DELETE FROM team_achievements WHERE team_id=?", (team_id,))
                conn.execute("DELETE FROM sponsor_offers WHERE team_id=?", (team_id,))
                conn.execute("DELETE FROM team_fatigue WHERE team_id=?", (team_id,))
                conn.execute(
                    "DELETE FROM team_rivalries WHERE team_a_id=? OR team_b_id=?",
                    (team_id, team_id),
                )
                # Preserve historical track records by name, but remove the dead live-team reference.
                conn.execute("UPDATE track_records SET team_id=NULL WHERE team_id=?", (team_id,))
                conn.execute("DELETE FROM teams WHERE id=?", (team_id,))
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    async def update_team_parts(self, team_id: int, parts: list[str]) -> None:
        await self.execute("UPDATE teams SET parts_json=? WHERE id=?", (json.dumps(parts), team_id))

    async def update_team_crew(self, team_id: int, crew: dict[str, str]) -> None:
        await self.execute("UPDATE teams SET crew_json=? WHERE id=?", (json.dumps(crew), team_id))

    async def create_tournament(self, name: str) -> int:
        cur = await self.execute("INSERT INTO tournaments(name) VALUES (?)", (name,))
        return int(cur.lastrowid)

    @staticmethod
    def _require_open_tournament_conn(conn: sqlite3.Connection, tournament_id: int) -> sqlite3.Row:
        row = conn.execute("SELECT * FROM tournaments WHERE id=?", (tournament_id,)).fetchone()
        if not row:
            raise ValueError("Tournament not found.")
        if row["status"] != "open":
            raise ValueError("That tournament is closed and can no longer be changed or raced.")
        return row

    async def add_team_to_tournament(self, tournament_id: int, team_id: int) -> None:
        async with self.lock:
            conn = self._require()
            try:
                conn.execute("BEGIN")
                self._require_open_tournament_conn(conn, tournament_id)
                if not conn.execute("SELECT 1 FROM teams WHERE id=?", (team_id,)).fetchone():
                    raise ValueError("Team not found.")
                conn.execute(
                    "INSERT OR IGNORE INTO tournament_teams(tournament_id, team_id) VALUES (?, ?)",
                    (tournament_id, team_id),
                )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    async def set_tournament_schedule(self, tournament_id: int, track_keys: list[str]) -> None:
        async with self.lock:
            conn = self._require()
            try:
                conn.execute("BEGIN")
                self._require_open_tournament_conn(conn, tournament_id)
                conn.execute("DELETE FROM tournament_schedule WHERE tournament_id=?", (tournament_id,))
                for race_number, track_key in enumerate(track_keys, start=1):
                    conn.execute(
                        "INSERT INTO tournament_schedule(tournament_id, race_number, track_key) VALUES (?, ?, ?)",
                        (tournament_id, race_number, track_key),
                    )
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    async def tournament_schedule(self, tournament_id: int) -> list[sqlite3.Row]:
        return await self.fetchall(
            "SELECT race_number, track_key FROM tournament_schedule WHERE tournament_id=? ORDER BY race_number",
            (tournament_id,),
        )

    async def tournament_race_count(self, tournament_id: int) -> int:
        row = await self.fetchone("SELECT COUNT(*) AS race_count FROM races WHERE tournament_id=?", (tournament_id,))
        return int(row["race_count"]) if row else 0

    async def next_scheduled_track(self, tournament_id: int) -> tuple[int, str] | None:
        next_race_number = await self.tournament_race_count(tournament_id) + 1
        row = await self.fetchone(
            """
            SELECT race_number, track_key
            FROM tournament_schedule
            WHERE tournament_id=? AND race_number=?
            """,
            (tournament_id, next_race_number),
        )
        if not row:
            return None
        return int(row["race_number"]), str(row["track_key"])

    async def get_tournament(self, tournament_id: int):
        return await self.fetchone("SELECT * FROM tournaments WHERE id=?", (tournament_id,))

    async def current_tournament(self):
        return await self.fetchone(
            "SELECT * FROM tournaments WHERE status='open' ORDER BY id DESC LIMIT 1"
        )

    async def list_tournaments(self, include_closed: bool = True, limit: int = 25):
        if include_closed:
            return await self.fetchall(
                "SELECT * FROM tournaments ORDER BY id DESC LIMIT ?",
                (limit,),
            )
        return await self.fetchall(
            "SELECT * FROM tournaments WHERE status='open' ORDER BY id DESC LIMIT ?",
            (limit,),
        )

    async def close_tournament(self, tournament_id: int) -> None:
        await self.execute("UPDATE tournaments SET status='closed' WHERE id=?", (tournament_id,))

    async def tournament_team_ids(self, tournament_id: int) -> list[int]:
        rows = await self.fetchall("SELECT team_id FROM tournament_teams WHERE tournament_id=? ORDER BY team_id", (tournament_id,))
        return [int(r["team_id"]) for r in rows]

    async def tournament_carryover_damage(self, tournament_id: int) -> dict[int, int]:
        rows = await self.fetchall(
            "SELECT team_id, carryover_damage FROM tournament_teams WHERE tournament_id=?",
            (tournament_id,),
        )
        return {int(row["team_id"]): int(row["carryover_damage"]) for row in rows}

    async def standings(self, tournament_id: int) -> list[sqlite3.Row]:
        return await self.fetchall(
            """
            SELECT tt.*, t.name, t.driver_name, t.car_name
            FROM tournament_teams tt
            JOIN teams t ON t.id = tt.team_id
            WHERE tt.tournament_id=?
            ORDER BY tt.points DESC, tt.wins DESC, tt.podiums DESC, tt.races ASC, t.name ASC
            """,
            (tournament_id,),
        )

    @staticmethod
    def calculate_carryover_damage(result: dict) -> int:
        final_damage = max(0, min(100, int(result.get("damage", 0))))
        carryover = final_damage // DAMAGE_CARRYOVER_DIVISOR
        if result.get("dnf"):
            carryover += DNF_CARRYOVER_PENALTY
        return min(MAX_TOURNAMENT_CARRYOVER_DAMAGE, carryover)

    def _apply_race_results_conn(self, conn: sqlite3.Connection, tournament_id: int, results: list[dict]) -> None:
        for r in results:
            carryover_damage = self.calculate_carryover_damage(r)
            cur = conn.execute(
                """
                UPDATE tournament_teams
                SET points = points + ?,
                    wins = wins + ?,
                    podiums = podiums + ?,
                    races = races + 1,
                    warnings = warnings + ?,
                    dnfs = dnfs + ?,
                    disqualifications = disqualifications + ?,
                    overtakes = overtakes + ?,
                    crashes = crashes + ?,
                    illegal_moves = illegal_moves + ?,
                    last_minute_wins = last_minute_wins + ?,
                    pit_stops = pit_stops + ?,
                    near_misses = near_misses + ?,
                    carryover_damage = ?,
                    peak_carryover_damage = MAX(peak_carryover_damage, ?)
                WHERE tournament_id=? AND team_id=?
                """,
                (
                    r["points"], 1 if r["position"] == 1 else 0, 1 if r["position"] <= 3 else 0,
                    r["warnings"], 1 if r["dnf"] else 0, 1 if r["disqualified"] else 0,
                    r.get("overtakes", 0), r.get("crashes", 0), r.get("illegal_moves", 0),
                    r.get("last_minute_wins", 0), r.get("pit_stops", 0), r.get("near_misses", 0),
                    carryover_damage, carryover_damage,
                    tournament_id, r["team_id"],
                ),
            )
            if cur.rowcount != 1:
                raise ValueError(f"Team {r['team_id']} is not entered in tournament {tournament_id}.")

    async def apply_race_results(self, tournament_id: int, results: list[dict]) -> None:
        async with self.lock:
            conn = self._require()
            try:
                conn.execute("BEGIN")
                self._require_open_tournament_conn(conn, tournament_id)
                self._apply_race_results_conn(conn, tournament_id, results)
                conn.commit()
            except Exception:
                conn.rollback()
                raise

    async def save_race(
        self,
        tournament_id: int | None,
        track_key: str,
        seed: str,
        events: list[dict],
        results: list[dict],
        replay_data: dict | None = None,
    ) -> int:
        cur = await self.execute(
            """
            INSERT INTO races(tournament_id, track_key, seed, events_json, results_json, replay_json)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                tournament_id,
                track_key,
                seed,
                json.dumps(events),
                json.dumps(results),
                json.dumps(replay_data) if replay_data is not None else None,
            ),
        )
        return int(cur.lastrowid)

    async def save_tournament_race(
        self,
        tournament_id: int,
        track_key: str,
        seed: str,
        events: list[dict],
        results: list[dict],
        replay_data: dict | None = None,
    ) -> int:
        """Atomically update tournament standings and persist the race."""
        async with self.lock:
            conn = self._require()
            try:
                conn.execute("BEGIN")
                self._require_open_tournament_conn(conn, tournament_id)
                self._apply_race_results_conn(conn, tournament_id, results)
                cur = conn.execute(
                    """
                    INSERT INTO races(tournament_id, track_key, seed, events_json, results_json, replay_json)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        tournament_id,
                        track_key,
                        seed,
                        json.dumps(events),
                        json.dumps(results),
                        json.dumps(replay_data) if replay_data is not None else None,
                    ),
                )
                race_id = int(cur.lastrowid)
                conn.commit()
                return race_id
            except Exception:
                conn.rollback()
                raise

    async def record_race_story(self, results: list[dict]) -> None:
        saved_results = [r for r in results if int(r.get("team_id", 0)) > 0]
        for result in saved_results:
            await self._record_team_profile(result)
        await self._record_rivalries(saved_results)

    async def _record_team_profile(self, result: dict) -> None:
        await self.execute(
            """
            INSERT INTO team_profiles(
                team_id, races, wins, podiums, warnings, dnfs, disqualifications,
                overtakes, crashes, illegal_moves, last_minute_wins, pit_stops,
                near_misses, total_damage, peak_damage
            )
            VALUES (?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                races = races + 1,
                wins = wins + excluded.wins,
                podiums = podiums + excluded.podiums,
                warnings = warnings + excluded.warnings,
                dnfs = dnfs + excluded.dnfs,
                disqualifications = disqualifications + excluded.disqualifications,
                overtakes = overtakes + excluded.overtakes,
                crashes = crashes + excluded.crashes,
                illegal_moves = illegal_moves + excluded.illegal_moves,
                last_minute_wins = last_minute_wins + excluded.last_minute_wins,
                pit_stops = pit_stops + excluded.pit_stops,
                near_misses = near_misses + excluded.near_misses,
                total_damage = total_damage + excluded.total_damage,
                peak_damage = MAX(peak_damage, excluded.peak_damage),
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                int(result["team_id"]),
                1 if int(result["position"]) == 1 else 0,
                1 if int(result["position"]) <= 3 else 0,
                int(result.get("warnings", 0)),
                1 if result.get("dnf") else 0,
                1 if result.get("disqualified") else 0,
                int(result.get("overtakes", 0)),
                int(result.get("crashes", 0)),
                int(result.get("illegal_moves", 0)),
                int(result.get("last_minute_wins", 0)),
                int(result.get("pit_stops", 0)),
                int(result.get("near_misses", 0)),
                int(result.get("damage", 0)),
                int(result.get("damage", 0)),
            ),
        )

    async def _record_rivalries(self, results: list[dict]) -> None:
        ordered = sorted(results, key=lambda result: int(result["position"]))
        for first, second in zip(ordered, ordered[1:]):
            time_gap = abs(float(first.get("total_time", 0)) - float(second.get("total_time", 0)))
            close_finish = time_gap <= 5
            contacts = int(first.get("crashes", 0)) + int(second.get("crashes", 0))
            illegal_incidents = (
                int(first.get("illegal_moves", 0))
                + int(second.get("illegal_moves", 0))
                + (1 if first.get("disqualified") else 0)
                + (1 if second.get("disqualified") else 0)
            )
            if not close_finish and contacts == 0 and illegal_incidents == 0:
                continue

            heat = (2 if close_finish else 0) + contacts + illegal_incidents * 2
            await self.record_rivalry_pair(
                int(first["team_id"]),
                int(second["team_id"]),
                heat=max(1, heat),
                close_finish=close_finish,
                contacts=contacts,
                illegal_incidents=illegal_incidents,
                winner_id=int(first["team_id"]),
            )

    async def record_rivalry_pair(
        self,
        first_team_id: int,
        second_team_id: int,
        heat: int,
        close_finish: bool,
        contacts: int,
        illegal_incidents: int,
        winner_id: int,
    ) -> None:
        team_a_id, team_b_id = sorted((first_team_id, second_team_id))
        await self.execute(
            """
            INSERT INTO team_rivalries(
                team_a_id, team_b_id, heat, races, close_finishes,
                contacts, illegal_incidents, last_winner_id
            )
            VALUES (?, ?, ?, 1, ?, ?, ?, ?)
            ON CONFLICT(team_a_id, team_b_id) DO UPDATE SET
                heat = heat + excluded.heat,
                races = races + 1,
                close_finishes = close_finishes + excluded.close_finishes,
                contacts = contacts + excluded.contacts,
                illegal_incidents = illegal_incidents + excluded.illegal_incidents,
                last_winner_id = excluded.last_winner_id,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                team_a_id,
                team_b_id,
                heat,
                1 if close_finish else 0,
                contacts,
                illegal_incidents,
                winner_id,
            ),
        )

    async def team_profile(self, team_id: int) -> sqlite3.Row | None:
        return await self.fetchone("SELECT * FROM team_profiles WHERE team_id=?", (team_id,))

    async def team_rivalries(self, team_id: int, limit: int = 5) -> list[sqlite3.Row]:
        return await self.fetchall(
            """
            SELECT
                r.*,
                opponent.id AS opponent_id,
                opponent.name AS opponent_name,
                opponent.driver_name AS opponent_driver_name,
                opponent.car_name AS opponent_car_name,
                winner.name AS last_winner_name
            FROM team_rivalries r
            JOIN teams opponent
              ON opponent.id = CASE WHEN r.team_a_id=? THEN r.team_b_id ELSE r.team_a_id END
            LEFT JOIN teams winner ON winner.id = r.last_winner_id
            WHERE r.team_a_id=? OR r.team_b_id=?
            ORDER BY r.heat DESC, r.races DESC, r.updated_at DESC
            LIMIT ?
            """,
            (team_id, team_id, team_id, limit),
        )

    async def race_rivalry_watch(self, results: list[dict], limit: int = 5) -> list[sqlite3.Row]:
        team_ids = sorted({int(result.get("team_id", 0)) for result in results if int(result.get("team_id", 0)) > 0})
        if len(team_ids) < 2:
            return []

        placeholders = ",".join("?" for _ in team_ids)
        return await self.fetchall(
            f"""
            SELECT
                r.*,
                team_a.name AS team_a_name,
                team_b.name AS team_b_name
            FROM team_rivalries r
            JOIN teams team_a ON team_a.id = r.team_a_id
            JOIN teams team_b ON team_b.id = r.team_b_id
            WHERE r.team_a_id IN ({placeholders})
              AND r.team_b_id IN ({placeholders})
              AND r.heat >= 5
            ORDER BY r.heat DESC, r.updated_at DESC
            LIMIT ?
            """,
            (*team_ids, *team_ids, limit),
        )

    async def record_season_history(self, tournament_id: int) -> None:
        tournament = await self.get_tournament(tournament_id)
        rows = await self.standings(tournament_id)
        if not tournament or not rows:
            return

        standings = [
            {
                "team_id": int(row["team_id"]),
                "name": row["name"],
                "driver_name": row["driver_name"],
                "points": int(row["points"]),
                "wins": int(row["wins"]),
                "podiums": int(row["podiums"]),
            }
            for row in rows
        ]
        top = standings[:3]
        await self.execute(
            """
            INSERT INTO season_history(
                tournament_id, tournament_name, champion_team_id, champion_name,
                runner_up_team_id, runner_up_name, third_team_id, third_name,
                standings_json, completed_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(tournament_id) DO UPDATE SET
                tournament_name = excluded.tournament_name,
                champion_team_id = excluded.champion_team_id,
                champion_name = excluded.champion_name,
                runner_up_team_id = excluded.runner_up_team_id,
                runner_up_name = excluded.runner_up_name,
                third_team_id = excluded.third_team_id,
                third_name = excluded.third_name,
                standings_json = excluded.standings_json,
                completed_at = CURRENT_TIMESTAMP
            """,
            (
                tournament_id,
                tournament["name"],
                top[0]["team_id"] if len(top) > 0 else None,
                top[0]["name"] if len(top) > 0 else None,
                top[1]["team_id"] if len(top) > 1 else None,
                top[1]["name"] if len(top) > 1 else None,
                top[2]["team_id"] if len(top) > 2 else None,
                top[2]["name"] if len(top) > 2 else None,
                json.dumps(standings),
            ),
        )

    async def season_history(self, limit: int = 10) -> list[sqlite3.Row]:
        return await self.fetchall(
            "SELECT * FROM season_history ORDER BY completed_at DESC LIMIT ?",
            (limit,),
        )

    async def hall_of_fame_champions(self, limit: int = 5) -> list[sqlite3.Row]:
        return await self.fetchall(
            """
            SELECT
                champion_team_id AS team_id,
                champion_name AS team_name,
                COUNT(*) AS titles,
                MAX(completed_at) AS last_title_at
            FROM season_history
            WHERE champion_team_id IS NOT NULL
            GROUP BY champion_team_id, champion_name
            ORDER BY titles DESC, last_title_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    async def hall_of_fame_podiums(self, limit: int = 5) -> list[sqlite3.Row]:
        return await self.fetchall(
            """
            SELECT team_id, team_name, COUNT(*) AS podiums
            FROM (
                SELECT champion_team_id AS team_id, champion_name AS team_name
                FROM season_history
                WHERE champion_team_id IS NOT NULL
                UNION ALL
                SELECT runner_up_team_id AS team_id, runner_up_name AS team_name
                FROM season_history
                WHERE runner_up_team_id IS NOT NULL
                UNION ALL
                SELECT third_team_id AS team_id, third_name AS team_name
                FROM season_history
                WHERE third_team_id IS NOT NULL
            )
            GROUP BY team_id, team_name
            ORDER BY podiums DESC, team_name ASC
            LIMIT ?
            """,
            (limit,),
        )

    async def hall_of_fame_stat_leaders(self, stat_key: str, limit: int = 3) -> list[sqlite3.Row]:
        allowed_stats = {
            "wins",
            "podiums",
            "overtakes",
            "crashes",
            "illegal_moves",
            "last_minute_wins",
            "pit_stops",
            "near_misses",
            "peak_damage",
        }
        if stat_key not in allowed_stats:
            raise ValueError("Unsupported Hall of Fame stat.")

        return await self.fetchall(
            f"""
            SELECT t.id AS team_id, t.name AS team_name, t.driver_name, p.{stat_key} AS stat_value, p.races
            FROM team_profiles p
            JOIN teams t ON t.id = p.team_id
            WHERE p.races > 0 AND p.{stat_key} > 0
            ORDER BY p.{stat_key} DESC, p.races ASC, t.name ASC
            LIMIT ?
            """,
            (limit,),
        )

    async def hall_of_fame_rivalries(self, limit: int = 5) -> list[sqlite3.Row]:
        return await self.fetchall(
            """
            SELECT
                r.*,
                team_a.name AS team_a_name,
                team_b.name AS team_b_name,
                winner.name AS last_winner_name
            FROM team_rivalries r
            JOIN teams team_a ON team_a.id = r.team_a_id
            JOIN teams team_b ON team_b.id = r.team_b_id
            LEFT JOIN teams winner ON winner.id = r.last_winner_id
            ORDER BY r.heat DESC, r.races DESC, r.updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )

    async def add_team_xp(self, team_id: int, xp: int, cosmetic_title: str) -> sqlite3.Row | None:
        await self.execute(
            """
            INSERT INTO team_progress(team_id, xp, cosmetic_title)
            VALUES (?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                xp = xp + excluded.xp,
                cosmetic_title = excluded.cosmetic_title,
                updated_at = CURRENT_TIMESTAMP
            """,
            (team_id, xp, cosmetic_title),
        )
        return await self.team_progress(team_id)

    async def set_team_title(self, team_id: int, cosmetic_title: str) -> None:
        await self.execute(
            """
            INSERT INTO team_progress(team_id, xp, cosmetic_title)
            VALUES (?, 0, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                cosmetic_title = excluded.cosmetic_title,
                updated_at = CURRENT_TIMESTAMP
            """,
            (team_id, cosmetic_title),
        )

    async def team_progress(self, team_id: int) -> sqlite3.Row | None:
        return await self.fetchone("SELECT * FROM team_progress WHERE team_id=?", (team_id,))

    async def unlock_achievement(self, team_id: int, achievement_key: str, achievement_name: str) -> bool:
        cur = await self.execute(
            """
            INSERT OR IGNORE INTO team_achievements(team_id, achievement_key, achievement_name)
            VALUES (?, ?, ?)
            """,
            (team_id, achievement_key, achievement_name),
        )
        return cur.rowcount > 0

    async def team_achievements(self, team_id: int) -> list[sqlite3.Row]:
        return await self.fetchall(
            "SELECT * FROM team_achievements WHERE team_id=? ORDER BY unlocked_at DESC",
            (team_id,),
        )

    async def create_sponsor_offer(self, team_id: int, sponsor_name: str, benefit_text: str, drawback_text: str) -> int:
        cur = await self.execute(
            """
            INSERT INTO sponsor_offers(team_id, sponsor_name, benefit_text, drawback_text)
            VALUES (?, ?, ?, ?)
            """,
            (team_id, sponsor_name, benefit_text, drawback_text),
        )
        return int(cur.lastrowid)

    async def team_sponsor_offers(self, team_id: int, limit: int = 5) -> list[sqlite3.Row]:
        return await self.fetchall(
            """
            SELECT * FROM sponsor_offers
            WHERE team_id=?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (team_id, limit),
        )

    async def sponsor_offer(self, offer_id: int) -> sqlite3.Row | None:
        return await self.fetchone("SELECT * FROM sponsor_offers WHERE id=?", (offer_id,))

    async def update_sponsor_offer_status(self, offer_id: int, status: str) -> None:
        if status not in {"offered", "accepted", "rejected"}:
            raise ValueError("Unsupported sponsor offer status.")
        await self.execute("UPDATE sponsor_offers SET status=? WHERE id=?", (status, offer_id))

    async def get_race(self, race_id: int) -> sqlite3.Row | None:
        return await self.fetchone("SELECT * FROM races WHERE id=?", (race_id,))

    async def recent_races(self, limit: int = 5) -> list[sqlite3.Row]:
        return await self.fetchall(
            "SELECT * FROM races ORDER BY id DESC LIMIT ?",
            (limit,),
        )

    async def set_team_fatigue(self, team_id: int, fatigue_key: str, fatigue_name: str, description: str, races_remaining: int = 1) -> None:
        await self.execute(
            """
            INSERT INTO team_fatigue(team_id, fatigue_key, fatigue_name, description, races_remaining)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(team_id) DO UPDATE SET
                fatigue_key = excluded.fatigue_key,
                fatigue_name = excluded.fatigue_name,
                description = excluded.description,
                races_remaining = excluded.races_remaining,
                updated_at = CURRENT_TIMESTAMP
            """,
            (team_id, fatigue_key, fatigue_name, description, races_remaining),
        )

    async def team_fatigue(self, team_id: int) -> sqlite3.Row | None:
        return await self.fetchone("SELECT * FROM team_fatigue WHERE team_id=?", (team_id,))

    async def decay_fatigue(self, team_ids: list[int]) -> None:
        for team_id in team_ids:
            await self.execute(
                """
                UPDATE team_fatigue
                SET races_remaining = races_remaining - 1,
                    updated_at = CURRENT_TIMESTAMP
                WHERE team_id=?
                """,
                (team_id,),
            )
        await self.execute("DELETE FROM team_fatigue WHERE races_remaining <= 0")

    async def update_track_record(
        self,
        track_key: str,
        record_key: str,
        record_name: str,
        record_value: float,
        team_id: int | None,
        team_name: str | None,
        race_id: int,
        details: str,
        higher_is_better: bool = True,
    ) -> bool:
        current = await self.fetchone(
            "SELECT record_value FROM track_records WHERE track_key=? AND record_key=?",
            (track_key, record_key),
        )
        should_update = (
            current is None
            or (higher_is_better and record_value > float(current["record_value"]))
            or (not higher_is_better and record_value < float(current["record_value"]))
        )
        if not should_update:
            return False
        await self.execute(
            """
            INSERT INTO track_records(track_key, record_key, record_name, record_value, team_id, team_name, race_id, details)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(track_key, record_key) DO UPDATE SET
                record_name = excluded.record_name,
                record_value = excluded.record_value,
                team_id = excluded.team_id,
                team_name = excluded.team_name,
                race_id = excluded.race_id,
                details = excluded.details,
                updated_at = CURRENT_TIMESTAMP
            """,
            (track_key, record_key, record_name, record_value, team_id, team_name, race_id, details),
        )
        return True

    async def track_records(self, track_key: str | None = None) -> list[sqlite3.Row]:
        if track_key:
            return await self.fetchall(
                "SELECT * FROM track_records WHERE track_key=? ORDER BY record_key",
                (track_key,),
            )
        return await self.fetchall(
            "SELECT * FROM track_records ORDER BY track_key, record_key"
        )
