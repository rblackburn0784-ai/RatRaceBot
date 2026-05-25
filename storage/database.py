import asyncio
import json
from dataclasses import asdict
import sqlite3
from pathlib import Path
from typing import Any

from models.domain import Team
from models.enums import CarArchetype
from models.stats import DriverStats

SCHEMA = """
CREATE TABLE IF NOT EXISTS teams (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL UNIQUE,
    driver_name TEXT NOT NULL,
    pit_crew_name TEXT NOT NULL,
    car_name TEXT NOT NULL,
    archetype TEXT NOT NULL,
    stats_json TEXT NOT NULL,
    parts_json TEXT NOT NULL DEFAULT '[]'
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
    PRIMARY KEY (tournament_id, team_id)
);

CREATE TABLE IF NOT EXISTS races (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    tournament_id INTEGER,
    track_key TEXT NOT NULL,
    seed TEXT NOT NULL,
    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    events_json TEXT NOT NULL,
    results_json TEXT NOT NULL
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
        self.conn.commit()

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
        cur = await self.execute(
            """INSERT INTO teams(name, driver_name, pit_crew_name, car_name, archetype, stats_json, parts_json)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (team.name, team.driver_name, team.pit_crew_name, team.car_name, team.archetype.value, stats_json, parts_json),
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
        )

    async def get_team(self, team_id: int) -> Team | None:
        row = await self.fetchone("SELECT * FROM teams WHERE id=?", (team_id,))
        return self.row_to_team(row) if row else None

    async def list_teams(self) -> list[Team]:
        rows = await self.fetchall("SELECT * FROM teams ORDER BY id")
        return [self.row_to_team(r) for r in rows]

    async def update_team_parts(self, team_id: int, parts: list[str]) -> None:
        await self.execute("UPDATE teams SET parts_json=? WHERE id=?", (json.dumps(parts), team_id))

    async def create_tournament(self, name: str) -> int:
        cur = await self.execute("INSERT INTO tournaments(name) VALUES (?)", (name,))
        return int(cur.lastrowid)

    async def add_team_to_tournament(self, tournament_id: int, team_id: int) -> None:
        await self.execute(
            "INSERT OR IGNORE INTO tournament_teams(tournament_id, team_id) VALUES (?, ?)",
            (tournament_id, team_id),
        )

    async def get_tournament(self, tournament_id: int):
        return await self.fetchone("SELECT * FROM tournaments WHERE id=?", (tournament_id,))

    async def close_tournament(self, tournament_id: int) -> None:
        await self.execute("UPDATE tournaments SET status='closed' WHERE id=?", (tournament_id,))

    async def tournament_team_ids(self, tournament_id: int) -> list[int]:
        rows = await self.fetchall("SELECT team_id FROM tournament_teams WHERE tournament_id=? ORDER BY team_id", (tournament_id,))
        return [int(r["team_id"]) for r in rows]

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

    async def apply_race_results(self, tournament_id: int, results: list[dict]) -> None:
        for r in results:
            await self.execute(
                """
                UPDATE tournament_teams
                SET points = points + ?,
                    wins = wins + ?,
                    podiums = podiums + ?,
                    races = races + 1,
                    warnings = warnings + ?,
                    dnfs = dnfs + ?,
                    disqualifications = disqualifications + ?
                WHERE tournament_id=? AND team_id=?
                """,
                (
                    r["points"], 1 if r["position"] == 1 else 0, 1 if r["position"] <= 3 else 0,
                    r["warnings"], 1 if r["dnf"] else 0, 1 if r["disqualified"] else 0,
                    tournament_id, r["team_id"],
                ),
            )

    async def save_race(self, tournament_id: int | None, track_key: str, seed: str, events: list[dict], results: list[dict]) -> int:
        cur = await self.execute(
            "INSERT INTO races(tournament_id, track_key, seed, events_json, results_json) VALUES (?, ?, ?, ?, ?)",
            (tournament_id, track_key, seed, json.dumps(events), json.dumps(results)),
        )
        return int(cur.lastrowid)
