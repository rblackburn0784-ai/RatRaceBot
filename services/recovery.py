from __future__ import annotations

import json
import re
import shutil
import sqlite3
import uuid
from dataclasses import fields
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from data.defaults import CREW_MEMBERS, PARTS, TRACKS, WEATHER_CONDITIONS
from models.domain import RaceEvent, RaceResult
from models.enums import CarArchetype, EventType
from models.stats import DriverStats
from services.engagement import COSMETIC_TITLES
from services.progression import EMBLEMS, GARAGE_DECOR, LIVERIES
from services.race_engine import POINTS_BY_POSITION
from services.race_rewards import process_race_rewards
from services.race_snapshot import restore_replay_snapshot
from services.racing_world import ensure_world_schema
from services.sponsors import SPONSORS
from storage.database import SCHEMA


RECOVERY_SCHEMA = """
CREATE TABLE IF NOT EXISTS recovery_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    target_type TEXT,
    target_id INTEGER,
    details_json TEXT NOT NULL DEFAULT '{}',
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS race_presentation_state (
    race_id INTEGER PRIMARY KEY,
    last_event_index INTEGER NOT NULL DEFAULT -1,
    status TEXT NOT NULL DEFAULT 'saved',
    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
);
"""


class RecoveryError(RuntimeError):
    pass


class RecoveryManager:
    """Administrative recovery helpers for the v0.5 release-candidate line."""

    def __init__(self, db, database_path: str, backup_dir: str = "backups"):
        self.db = db
        self.database_path = Path(database_path)
        self.backup_dir = Path(backup_dir)
        self.checkpoint_dir = self.backup_dir / "checkpoints"

    async def init(self) -> None:
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        self.checkpoint_dir.mkdir(parents=True, exist_ok=True)
        async with self.db.lock:
            conn = self.db._require()
            conn.executescript(RECOVERY_SCHEMA)
            conn.commit()

    @staticmethod
    def _stamp() -> str:
        return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")

    @staticmethod
    def _slug(value: str) -> str:
        clean = re.sub(r"[^a-zA-Z0-9_-]+", "_", value).strip("_")
        return clean[:80] or "backup"

    async def _backup_to(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        async with self.db.lock:
            source = self.db._require()
            destination = sqlite3.connect(path)
            try:
                source.backup(destination)
                destination.commit()
            finally:
                destination.close()
        return path

    async def backup_database(self, label: str = "manual") -> Path:
        suffix = self.database_path.suffix or ".sqlite3"
        path = self.backup_dir / f"{self.database_path.stem}_{self._slug(label)}_{self._stamp()}{suffix}"
        await self._backup_to(path)
        await self.log("backup_database", "backup", None, {"path": str(path), "label": label})
        return path

    async def create_race_checkpoint(self, context: dict[str, Any]) -> str:
        token = uuid.uuid4().hex[:12]
        suffix = self.database_path.suffix or ".sqlite3"
        db_path = self.checkpoint_dir / f"pre_race_{self._stamp()}_{token}{suffix}"
        meta_path = db_path.with_suffix(db_path.suffix + ".json")
        await self._backup_to(db_path)
        meta = {
            "version": 1,
            "token": token,
            "kind": "pre_race",
            "database": str(db_path),
            "race_id": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "context": context,
        }
        meta_path.write_text(json.dumps(meta, indent=2, sort_keys=True), encoding="utf-8")
        return token

    def _checkpoint_meta_paths(self) -> list[Path]:
        if not self.checkpoint_dir.exists():
            return []
        return sorted(self.checkpoint_dir.glob("*.json"), reverse=True)

    def _load_checkpoint_meta(self, path: Path) -> dict[str, Any] | None:
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else None
        except (OSError, json.JSONDecodeError, TypeError):
            return None

    def _checkpoint_by_token(self, token: str) -> tuple[Path, dict[str, Any]] | None:
        for meta_path in self._checkpoint_meta_paths():
            data = self._load_checkpoint_meta(meta_path)
            if data and data.get("token") == token:
                return meta_path, data
        return None

    def checkpoint_for_race(self, race_id: int) -> dict[str, Any] | None:
        for meta_path in self._checkpoint_meta_paths():
            data = self._load_checkpoint_meta(meta_path)
            if data and int(data.get("race_id") or 0) == int(race_id):
                data["_meta_path"] = str(meta_path)
                return data
        return None

    def bind_race_checkpoint(self, token: str, race_id: int) -> None:
        found = self._checkpoint_by_token(token)
        if not found:
            raise RecoveryError("Automatic pre-race checkpoint metadata could not be found.")
        meta_path, data = found
        data["race_id"] = int(race_id)
        data["bound_at"] = datetime.now(timezone.utc).isoformat()
        meta_path.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")

    def list_backups(self) -> list[Path]:
        suffixes = {".sqlite", ".sqlite3", ".db"}
        if not self.backup_dir.exists():
            return []
        return sorted(
            [
                path for path in self.backup_dir.iterdir()
                if path.is_file() and path.suffix.lower() in suffixes
            ],
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )

    def resolve_backup(self, name: str) -> Path:
        candidate = Path(name)
        if candidate.is_absolute() or ".." in candidate.parts:
            raise RecoveryError("Backup name must refer to a file inside the backups directory.")
        path = self.backup_dir / candidate.name
        if not path.exists() or not path.is_file():
            raise RecoveryError(f"Backup not found: {candidate.name}")
        return path

    @staticmethod
    def _validate_sqlite_file(path: Path) -> tuple[bool, str]:
        try:
            conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
            try:
                row = conn.execute("PRAGMA integrity_check").fetchone()
                result = str(row[0]) if row else "no result"
                return result.lower() == "ok", result
            finally:
                conn.close()
        except sqlite3.DatabaseError as exc:
            return False, str(exc)

    async def _restore_path(self, source: Path) -> None:
        ok, result = self._validate_sqlite_file(source)
        if not ok:
            raise RecoveryError(f"Backup failed SQLite integrity check: {result}")
        async with self.db.lock:
            if self.db.conn is not None:
                self.db.conn.close()
                self.db.conn = None
            self.database_path.parent.mkdir(parents=True, exist_ok=True)
            for suffix in ("-wal", "-shm"):
                sidecar = Path(str(self.database_path) + suffix)
                try:
                    sidecar.unlink()
                except FileNotFoundError:
                    pass
            shutil.copy2(source, self.database_path)
            self.db.conn = sqlite3.connect(self.database_path)
            self.db.conn.row_factory = sqlite3.Row
            self.db.conn.executescript(SCHEMA)
            self.db._migrate()
            self.db.conn.executescript(RECOVERY_SCHEMA)
            self.db.conn.commit()

    async def restore_backup(self, name: str) -> tuple[Path, Path]:
        source = self.resolve_backup(name)
        safety = await self.backup_database("pre_restore_safety")
        await self._restore_path(source)
        await self.log("restore_backup", "backup", None, {"source": str(source), "safety": str(safety)})
        return source, safety

    async def validate_database(self) -> dict[str, Any]:
        await self.init()
        # World tables were deliberately lazy in v0.4.8. Health validation now
        # materialises them first so a missing world subsystem cannot be hidden.
        await ensure_world_schema(self.db)

        issues: list[str] = []
        warnings: list[str] = []
        async with self.db.lock:
            conn = self.db._require()
            integrity_rows = conn.execute("PRAGMA integrity_check").fetchall()
            integrity = [str(row[0]) for row in integrity_rows]
            if integrity != ["ok"]:
                issues.extend(f"SQLite integrity: {item}" for item in integrity)

            foreign = conn.execute("PRAGMA foreign_key_check").fetchall()
            if foreign:
                issues.append(f"Foreign-key check returned {len(foreign)} row(s).")

            required_tables = {
                "teams", "tournaments", "tournament_teams", "races", "tournament_schedule",
                "team_profiles", "team_rivalries", "season_history", "team_season_history",
                "team_progress", "team_achievements", "sponsor_offers", "team_identity",
                "team_fatigue", "track_records", "team_setups", "race_processing",
                "recovery_log", "race_presentation_state", "rivalry_story_stats",
                "racing_world_processed", "world_events",
            }
            present = {
                str(row["name"])
                for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
            }
            missing = sorted(required_tables - present)
            if missing:
                issues.append("Missing tables: " + ", ".join(missing))

            for row in conn.execute("SELECT id, archetype, stats_json, parts_json, crew_json FROM teams").fetchall():
                team_id = int(row["id"])
                try:
                    CarArchetype(str(row["archetype"]))
                except ValueError:
                    issues.append(f"Team #{team_id}: invalid archetype.")
                try:
                    stats = DriverStats(**json.loads(row["stats_json"]))
                    stats.validate()
                except Exception as exc:
                    issues.append(f"Team #{team_id}: invalid driver stats ({exc}).")
                try:
                    parts = json.loads(row["parts_json"])
                    if not isinstance(parts, list) or any(key not in PARTS for key in parts):
                        issues.append(f"Team #{team_id}: invalid parts data.")
                except Exception:
                    issues.append(f"Team #{team_id}: malformed parts JSON.")
                try:
                    crew = json.loads(row["crew_json"])
                    if (
                        not isinstance(crew, dict)
                        or any(
                            key not in CREW_MEMBERS
                            or CREW_MEMBERS[key].slot.value != str(slot)
                            for slot, key in crew.items()
                        )
                    ):
                        issues.append(f"Team #{team_id}: invalid crew data.")
                except Exception:
                    issues.append(f"Team #{team_id}: malformed crew JSON.")

            for row in conn.execute("SELECT id, tournament_id, track_key, events_json, results_json, replay_json FROM races").fetchall():
                race_id = int(row["id"])
                if str(row["track_key"]) not in TRACKS:
                    issues.append(f"Race #{race_id}: unknown track key {row['track_key']!r}.")
                for column in ("events_json", "results_json"):
                    try:
                        value = json.loads(row[column])
                        if not isinstance(value, list):
                            raise ValueError("not a list")
                    except Exception:
                        issues.append(f"Race #{race_id}: malformed {column}.")
                if row["replay_json"]:
                    try:
                        value = json.loads(row["replay_json"])
                        if not isinstance(value, dict):
                            raise ValueError("not an object")
                    except Exception:
                        issues.append(f"Race #{race_id}: malformed replay_json.")

            for row in conn.execute("SELECT tournament_id, race_number, track_key FROM tournament_schedule").fetchall():
                if str(row["track_key"]) not in TRACKS:
                    issues.append(
                        f"Tournament #{int(row['tournament_id'])} round {int(row['race_number'])}: "
                        f"unknown track key {row['track_key']!r}."
                    )

            orphan_checks = {
                "tournament teams": "SELECT COUNT(*) AS c FROM tournament_teams x LEFT JOIN teams t ON t.id=x.team_id LEFT JOIN tournaments tr ON tr.id=x.tournament_id WHERE t.id IS NULL OR tr.id IS NULL",
                "tournament schedule rows": "SELECT COUNT(*) AS c FROM tournament_schedule x LEFT JOIN tournaments tr ON tr.id=x.tournament_id WHERE tr.id IS NULL",
                "tournament races": "SELECT COUNT(*) AS c FROM races r LEFT JOIN tournaments tr ON tr.id=r.tournament_id WHERE r.tournament_id IS NOT NULL AND tr.id IS NULL",
                "team profiles": "SELECT COUNT(*) AS c FROM team_profiles x LEFT JOIN teams t ON t.id=x.team_id WHERE t.id IS NULL",
                "team progress": "SELECT COUNT(*) AS c FROM team_progress x LEFT JOIN teams t ON t.id=x.team_id WHERE t.id IS NULL",
                "team achievements": "SELECT COUNT(*) AS c FROM team_achievements x LEFT JOIN teams t ON t.id=x.team_id WHERE t.id IS NULL",
                "sponsor offers": "SELECT COUNT(*) AS c FROM sponsor_offers x LEFT JOIN teams t ON t.id=x.team_id WHERE t.id IS NULL",
                "team identity rows": "SELECT COUNT(*) AS c FROM team_identity x LEFT JOIN teams t ON t.id=x.team_id WHERE t.id IS NULL",
                "team fatigue rows": "SELECT COUNT(*) AS c FROM team_fatigue x LEFT JOIN teams t ON t.id=x.team_id WHERE t.id IS NULL",
                "team setups": "SELECT COUNT(*) AS c FROM team_setups x LEFT JOIN teams t ON t.id=x.team_id WHERE t.id IS NULL",
                "team season history": "SELECT COUNT(*) AS c FROM team_season_history x LEFT JOIN teams t ON t.id=x.team_id LEFT JOIN tournaments tr ON tr.id=x.tournament_id WHERE t.id IS NULL OR tr.id IS NULL",
                "season history": "SELECT COUNT(*) AS c FROM season_history x LEFT JOIN tournaments tr ON tr.id=x.tournament_id WHERE tr.id IS NULL",
                "track record team references": "SELECT COUNT(*) AS c FROM track_records x LEFT JOIN teams t ON t.id=x.team_id WHERE x.team_id IS NOT NULL AND t.id IS NULL",
                "track record race references": "SELECT COUNT(*) AS c FROM track_records x LEFT JOIN races r ON r.id=x.race_id WHERE x.race_id IS NOT NULL AND r.id IS NULL",
                "team rivalries": "SELECT COUNT(*) AS c FROM team_rivalries x LEFT JOIN teams a ON a.id=x.team_a_id LEFT JOIN teams b ON b.id=x.team_b_id WHERE a.id IS NULL OR b.id IS NULL",
                "rivalry story stats": "SELECT COUNT(*) AS c FROM rivalry_story_stats x LEFT JOIN teams a ON a.id=x.team_a_id LEFT JOIN teams b ON b.id=x.team_b_id WHERE a.id IS NULL OR b.id IS NULL",
                "world events": "SELECT COUNT(*) AS c FROM world_events x LEFT JOIN teams t ON t.id=x.team_id LEFT JOIN races r ON r.id=x.race_id WHERE t.id IS NULL OR r.id IS NULL",
                "race processing rows": "SELECT COUNT(*) AS c FROM race_processing x LEFT JOIN races r ON r.id=x.race_id WHERE r.id IS NULL",
                "world processing rows": "SELECT COUNT(*) AS c FROM racing_world_processed x LEFT JOIN races r ON r.id=x.race_id WHERE r.id IS NULL",
                "race presentation rows": "SELECT COUNT(*) AS c FROM race_presentation_state x LEFT JOIN races r ON r.id=x.race_id WHERE r.id IS NULL",
            }
            for label, sql in orphan_checks.items():
                count = int(conn.execute(sql).fetchone()["c"])
                if count:
                    issues.append(f"Orphaned {label}: {count} row(s).")

            open_tournaments = conn.execute(
                "SELECT id, name FROM tournaments WHERE status='open' ORDER BY id"
            ).fetchall()
            if len(open_tournaments) > 1:
                issues.append(
                    "Multiple active championships detected: "
                    + ", ".join(f"#{int(row['id'])} {row['name']}" for row in open_tournaments)
                )

            latest = conn.execute("SELECT MAX(id) AS id FROM races").fetchone()
            latest_id = int(latest["id"] or 0)
            if latest_id and not self.checkpoint_for_race(latest_id):
                warnings.append(
                    f"Latest race #{latest_id} has no v0.4.9+ pre-race checkpoint; "
                    "destructive recovery is unavailable for it."
                )

        return {
            "ok": not issues,
            "integrity": integrity,
            "issues": issues,
            "warnings": warnings,
            "tables_checked": len(required_tables),
        }

    async def log(self, action: str, target_type: str | None, target_id: int | None, details: dict[str, Any] | None = None) -> None:
        await self.init()
        await self.db.execute(
            "INSERT INTO recovery_log(action, target_type, target_id, details_json) VALUES (?, ?, ?, ?)",
            (action, target_type, target_id, json.dumps(details or {}, sort_keys=True)),
        )

    async def mark_presentation(self, race_id: int, last_event_index: int, status: str) -> None:
        await self.init()
        await self.db.execute(
            """
            INSERT INTO race_presentation_state(race_id, last_event_index, status, updated_at)
            VALUES (?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(race_id) DO UPDATE SET
                last_event_index=excluded.last_event_index,
                status=excluded.status,
                updated_at=CURRENT_TIMESTAMP
            """,
            (int(race_id), int(last_event_index), str(status)),
        )

    async def presentation_state(self, race_id: int):
        await self.init()
        return await self.db.fetchone("SELECT * FROM race_presentation_state WHERE race_id=?", (int(race_id),))

    async def interrupted_races(self):
        await self.init()
        return await self.db.fetchall(
            """
            SELECT p.*, r.track_key, r.tournament_id
            FROM race_presentation_state p
            JOIN races r ON r.id=p.race_id
            WHERE p.status IN ('saved', 'streaming', 'interrupted')
            ORDER BY p.race_id DESC
            """
        )

    async def latest_race(self):
        return await self.db.fetchone("SELECT * FROM races ORDER BY id DESC LIMIT 1")

    async def _assert_latest_recoverable(self, race_id: int) -> tuple[Any, dict[str, Any]]:
        latest = await self.latest_race()
        if not latest:
            raise RecoveryError("There are no saved races.")
        if int(latest["id"]) != int(race_id):
            raise RecoveryError(
                f"Race #{race_id} is not the latest saved race. v0.4.9 refuses to rewrite older races because later progression would become inconsistent."
            )
        checkpoint = self.checkpoint_for_race(race_id)
        if not checkpoint:
            raise RecoveryError(
                f"Race #{race_id} does not have a v0.4.9 automatic pre-race checkpoint. It cannot be safely rewritten."
            )
        return latest, checkpoint

    async def undo_last_race(self) -> dict[str, Any]:
        latest = await self.latest_race()
        if not latest:
            raise RecoveryError("There are no races to undo.")
        race_id = int(latest["id"])
        _row, checkpoint = await self._assert_latest_recoverable(race_id)
        checkpoint_path = Path(str(checkpoint["database"]))
        if not checkpoint_path.exists():
            raise RecoveryError("The pre-race checkpoint file is missing.")
        safety = await self.backup_database(f"pre_undo_race_{race_id}")
        await self._restore_path(checkpoint_path)
        await self.log("undo_last_race", "race", race_id, {"safety": str(safety), "checkpoint": str(checkpoint_path)})
        return {"race_id": race_id, "safety": safety, "checkpoint": checkpoint_path}

    @staticmethod
    def event_from_dict(data: dict[str, Any]) -> RaceEvent:
        return RaceEvent(
            event_type=EventType(str(data["event_type"])),
            lap=int(data.get("lap", 0)),
            message=str(data.get("message", "")),
            media_key=data.get("media_key"),
            audio_key=data.get("audio_key"),
            actor=data.get("actor"),
            target=data.get("target"),
            participants=list(data.get("participants") or []),
            context=dict(data.get("context") or {}),
        )

    @staticmethod
    def result_from_dict(data: dict[str, Any]) -> RaceResult:
        allowed = {field.name for field in fields(RaceResult)}
        clean = {key: value for key, value in data.items() if key in allowed}
        return RaceResult(**clean)

    async def _reinsert_payload(
        self,
        payload: dict[str, Any],
        results_data: list[dict[str, Any]],
    ) -> int:
        events_data = json.loads(payload["events_json"])
        replay_data = json.loads(payload["replay_json"]) if payload.get("replay_json") else None
        tournament_id = payload.get("tournament_id")
        if tournament_id is None:
            race_id = await self.db.save_race(
                None,
                str(payload["track_key"]),
                str(payload["seed"]),
                events_data,
                results_data,
                replay_data=replay_data,
            )
        else:
            race_id = await self.db.save_tournament_race(
                int(tournament_id),
                str(payload["track_key"]),
                str(payload["seed"]),
                events_data,
                results_data,
                replay_data=replay_data,
                schedule_race_number=int(payload["schedule_race_number"]) if payload.get("schedule_race_number") is not None else None,
            )
        return int(race_id)

    async def _post_process_payload(
        self,
        race_id: int,
        payload: dict[str, Any],
        results_data: list[dict[str, Any]],
    ) -> None:
        replay = json.loads(payload["replay_json"]) if payload.get("replay_json") else None
        if not replay:
            raise RecoveryError("The race lacks a replay snapshot, so teams/weather cannot be reconstructed safely.")
        teams, laps, _damage, weather_key, _rng = restore_replay_snapshot(replay)
        events = [self.event_from_dict(item) for item in json.loads(payload["events_json"])]
        results = [self.result_from_dict(item) for item in results_data]
        weather = WEATHER_CONDITIONS.get(weather_key) if weather_key else None
        weather_name = weather.name if weather else str(weather_key or "Unknown")
        await process_race_rewards(
            self.db,
            str(payload["track_key"]),
            int(race_id),
            teams,
            results,
            events,
            weather_name,
            f"Recovered Race #{race_id}",
            int(laps),
        )
        await self.mark_presentation(race_id, -1, "saved")

        tournament_id = payload.get("tournament_id")
        if tournament_id is not None and int(payload.get("championship_round") or 0) == 1:
            schedule = await self.db.tournament_schedule(int(tournament_id))
            if schedule:
                completed = await self.db.tournament_scheduled_race_count(int(tournament_id))
                if completed >= len(schedule):
                    await self.db.finalize_tournament(int(tournament_id))

    async def reprocess_latest_race(
        self,
        race_id: int,
        transform_results: Callable[[list[dict[str, Any]], dict[str, Any] | None], list[dict[str, Any]]] | None = None,
        action: str = "reprocess_race",
    ) -> dict[str, Any]:
        latest, checkpoint = await self._assert_latest_recoverable(race_id)
        payload = dict(latest)
        original_results = json.loads(payload["results_json"])
        replay = json.loads(payload["replay_json"]) if payload.get("replay_json") else None
        results_data = transform_results(original_results, replay) if transform_results else original_results

        checkpoint_path = Path(str(checkpoint["database"]))
        if not checkpoint_path.exists():
            raise RecoveryError("The automatic pre-race checkpoint file is missing.")

        safety = await self.backup_database(f"pre_{action}_{race_id}")
        try:
            await self._restore_path(checkpoint_path)
            new_id = await self._reinsert_payload(payload, results_data)
            if new_id != int(race_id):
                raise RecoveryError(
                    f"Recovered race was assigned ID #{new_id} instead of #{race_id}; safety rollback required."
                )
            await self._post_process_payload(new_id, payload, results_data)
            self.bind_race_checkpoint(str(checkpoint["token"]), new_id)
            await self.log(action, "race", race_id, {"safety": str(safety)})
            return {"race_id": new_id, "safety": safety, "results": results_data}
        except Exception:
            await self._restore_path(safety)
            raise

    async def correct_latest_result(
        self,
        race_id: int,
        team_id: int,
        new_position: int,
        status: str = "keep",
    ) -> dict[str, Any]:
        status = status.lower().strip()
        if status not in {"keep", "finish", "dnf", "dsq"}:
            raise RecoveryError("Status must be keep, finish, dnf, or dsq.")

        def transform(rows: list[dict[str, Any]], replay: dict[str, Any] | None) -> list[dict[str, Any]]:
            if not rows:
                raise RecoveryError("Race has no result rows.")
            if new_position < 1 or new_position > len(rows):
                raise RecoveryError(f"New position must be between 1 and {len(rows)}.")
            target = next((row for row in rows if int(row.get("team_id", 0)) == int(team_id)), None)
            if not target:
                raise RecoveryError(f"Team #{team_id} is not in race #{race_id}.")
            occupant = next((row for row in rows if int(row.get("position", 0)) == int(new_position)), None)
            old_position = int(target["position"])
            if occupant and occupant is not target:
                occupant["position"] = old_position
            target["position"] = int(new_position)

            if status != "keep":
                target["dnf"] = status == "dnf"
                target["disqualified"] = status == "dsq"
                if status == "finish":
                    target["dnf"] = False
                    target["disqualified"] = False
                    if replay:
                        target["laps_completed"] = int(replay.get("laps", target.get("laps_completed", 0)))

            ordered = sorted(
                rows,
                key=lambda row: (
                    2 if row.get("disqualified") else 1 if row.get("dnf") else 0,
                    int(row.get("position", 999)),
                ),
            )
            for index, row in enumerate(ordered, start=1):
                row["position"] = index
                official = not row.get("dnf") and not row.get("disqualified")
                row["points"] = int(POINTS_BY_POSITION.get(index, 0)) if official else 0
                if not official:
                    row["last_minute_wins"] = 0
            return ordered

        result = await self.reprocess_latest_race(
            race_id,
            transform_results=transform,
            action="correct_result",
        )
        result.update({"team_id": int(team_id), "new_position": int(new_position), "status": status})
        return result

    async def restore_tournament(self, tournament_id: int) -> dict[str, Any]:
        row = await self.db.get_tournament(int(tournament_id))
        if not row:
            raise RecoveryError("Tournament not found.")
        if str(row["status"]) == "open":
            return {"tournament_id": tournament_id, "name": row["name"], "already_open": True}

        open_rows = await self.db.fetchall("SELECT id, name FROM tournaments WHERE status='open' AND id<>? ORDER BY id", (int(tournament_id),))
        if open_rows:
            raise RecoveryError(
                "Another tournament is already open. Close it before restoring this tournament."
            )
        safety = await self.backup_database(f"pre_restore_tournament_{tournament_id}")
        async with self.db.lock:
            conn = self.db._require()
            try:
                conn.execute("BEGIN")
                conn.execute("UPDATE tournaments SET status='open' WHERE id=?", (int(tournament_id),))
                conn.execute("DELETE FROM season_history WHERE tournament_id=?", (int(tournament_id),))
                conn.execute("DELETE FROM team_season_history WHERE tournament_id=?", (int(tournament_id),))
                conn.commit()
            except Exception:
                conn.rollback()
                raise
        await self.log("restore_tournament", "tournament", int(tournament_id), {"safety": str(safety)})
        return {"tournament_id": int(tournament_id), "name": row["name"], "safety": safety, "already_open": False}

    @staticmethod
    def _repair_stats(raw: Any) -> tuple[dict[str, int], bool]:
        keys = ("nerve", "handling", "aggression", "mechanics", "reflexes", "showmanship")
        changed = False
        try:
            source = dict(raw)
        except Exception:
            source = {}
            changed = True
        stats = {}
        for key in keys:
            try:
                value = int(source.get(key, 4))
            except (TypeError, ValueError):
                value = 4
                changed = True
            clamped = max(1, min(8, value))
            changed = changed or clamped != value
            stats[key] = clamped
        while sum(stats.values()) > 24:
            key = max(stats, key=lambda name: stats[name])
            if stats[key] <= 1:
                break
            stats[key] -= 1
            changed = True
        return stats, changed

    async def repair_team_data(self, team_id: int) -> dict[str, Any]:
        await self.init()
        safety = await self.backup_database(f"pre_repair_team_{team_id}")
        fixes: list[str] = []
        async with self.db.lock:
            conn = self.db._require()
            row = conn.execute("SELECT * FROM teams WHERE id=?", (int(team_id),)).fetchone()
            if not row:
                raise RecoveryError("Team not found.")
            try:
                archetype = CarArchetype(str(row["archetype"])).value
            except ValueError:
                archetype = CarArchetype.COUPE_32.value
                fixes.append("reset invalid archetype")

            try:
                raw_stats = json.loads(row["stats_json"])
            except Exception:
                raw_stats = {}
            stats, changed = self._repair_stats(raw_stats)
            if changed:
                fixes.append("repaired driver stats")

            try:
                raw_parts = json.loads(row["parts_json"])
                if not isinstance(raw_parts, list):
                    raw_parts = []
            except Exception:
                raw_parts = []
            seen_slots = set()
            parts: list[str] = []
            for key in raw_parts:
                if key not in PARTS:
                    continue
                slot = PARTS[key].slot.value
                if slot in seen_slots:
                    continue
                seen_slots.add(slot)
                parts.append(key)
            if parts != raw_parts:
                fixes.append("removed unknown/duplicate-slot parts")

            try:
                raw_crew = json.loads(row["crew_json"])
                if not isinstance(raw_crew, dict):
                    raw_crew = {}
            except Exception:
                raw_crew = {}
            crew: dict[str, str] = {}
            for slot, key in raw_crew.items():
                member = CREW_MEMBERS.get(str(key))
                if member and member.slot.value == str(slot):
                    crew[str(slot)] = str(key)
            if crew != raw_crew:
                fixes.append("removed invalid crew assignments")

            sponsor_key = row["active_sponsor_key"]
            if sponsor_key and sponsor_key not in SPONSORS:
                sponsor_key = None
                fixes.append("cleared invalid active sponsor")

            conn.execute(
                """
                UPDATE teams
                SET archetype=?, stats_json=?, parts_json=?, crew_json=?, active_sponsor_key=?
                WHERE id=?
                """,
                (archetype, json.dumps(stats), json.dumps(parts), json.dumps(crew), sponsor_key, int(team_id)),
            )

            identity = conn.execute("SELECT * FROM team_identity WHERE team_id=?", (int(team_id),)).fetchone()
            if identity:
                valid_liveries = {item.key for item in LIVERIES}
                valid_emblems = {item.key for item in EMBLEMS}
                valid_decor = {item.key for item in GARAGE_DECOR}
                livery = identity["livery_key"] if identity["livery_key"] in valid_liveries else "bare_primer"
                emblem = identity["emblem_key"] if identity["emblem_key"] in valid_emblems else "rat_skull"
                decor = identity["garage_decor_key"] if identity["garage_decor_key"] in valid_decor else "oil_stained_bench"
                if (livery, emblem, decor) != (identity["livery_key"], identity["emblem_key"], identity["garage_decor_key"]):
                    fixes.append("repaired invalid identity cosmetics")
                    conn.execute(
                        "UPDATE team_identity SET livery_key=?, emblem_key=?, garage_decor_key=?, updated_at=CURRENT_TIMESTAMP WHERE team_id=?",
                        (livery, emblem, decor, int(team_id)),
                    )

            setup_rows = conn.execute("SELECT setup_name, parts_json FROM team_setups WHERE team_id=?", (int(team_id),)).fetchall()
            for setup in setup_rows:
                try:
                    raw = json.loads(setup["parts_json"])
                    if not isinstance(raw, list):
                        raw = []
                except Exception:
                    raw = []
                valid: list[str] = []
                slots = set()
                for key in raw:
                    if key not in PARTS:
                        continue
                    slot = PARTS[key].slot.value
                    if slot in slots:
                        continue
                    slots.add(slot)
                    valid.append(key)
                if valid != raw:
                    conn.execute(
                        "UPDATE team_setups SET parts_json=?, updated_at=CURRENT_TIMESTAMP WHERE team_id=? AND setup_name=?",
                        (json.dumps(valid), int(team_id), setup["setup_name"]),
                    )
                    fixes.append(f"repaired setup {setup['setup_name']}")

            progress = conn.execute("SELECT cosmetic_title FROM team_progress WHERE team_id=?", (int(team_id),)).fetchone()
            if progress and not str(progress["cosmetic_title"]).strip():
                conn.execute(
                    "UPDATE team_progress SET cosmetic_title=?, updated_at=CURRENT_TIMESTAMP WHERE team_id=?",
                    (COSMETIC_TITLES[1], int(team_id)),
                )
                fixes.append("restored empty cosmetic title")
            conn.commit()

        await self.log("repair_team_data", "team", int(team_id), {"fixes": fixes, "safety": str(safety)})
        return {"team_id": int(team_id), "fixes": fixes, "safety": safety}
