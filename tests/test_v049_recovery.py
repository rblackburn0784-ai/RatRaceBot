import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from data.defaults import PARTS
from models.domain import RaceResult, Team
from models.enums import CarArchetype
from models.stats import DriverStats
from services.race_rewards import process_race_rewards
from services.race_snapshot import build_replay_snapshot
from services.recovery import RecoveryError, RecoveryManager
from services.race_activity import RaceActivityRegistry
from storage.database import Database


def make_team(index: int) -> Team:
    return Team(
        id=None,
        name=f"RC Team {index}",
        driver_name=f"Driver {index}",
        pit_crew_name=f"Crew {index}",
        car_name=f"Rod {index}",
        archetype=list(CarArchetype)[(index - 1) % len(CarArchetype)],
        stats=DriverStats(4, 4, 4, 4, 4, 4),
        owner_user_id=12000 + index,
    )


def result(team: Team, position: int) -> RaceResult:
    return RaceResult(
        team_id=int(team.id), team_name=team.name, driver_name=team.driver_name, position=position,
        laps_completed=10, total_time=600.0 + position, points=max(0, 11 - position),
        warnings=0, dnf=False, disqualified=False, damage=5, tyre_wear=20,
        overtakes=max(0, 3 - position), crashes=0, illegal_moves=0, last_minute_wins=0,
        pit_stops=0, near_misses=0, fastest_lap=52.0 + position,
    )


class RecoveryDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.db_path = root / "rat.sqlite3"
        self.backup_dir = root / "backups"
        self.db = Database(str(self.db_path))
        await self.db.init()
        self.recovery = RecoveryManager(self.db, str(self.db_path), str(self.backup_dir))
        await self.recovery.init()
        self.teams = []
        for index in range(1, 4):
            team = make_team(index)
            team.id = await self.db.create_team(team)
            self.teams.append(team)

    async def asyncTearDown(self):
        await self.db.close()
        self.tempdir.cleanup()

    async def _save_processed_race(self, *, checkpoint=True):
        token = None
        if checkpoint:
            token = await self.recovery.create_race_checkpoint({"test": True})
        results = [result(self.teams[0], 1), result(self.teams[1], 2)]
        replay = build_replay_snapshot(self.teams[:2], laps=10, weather_key="clear")
        race_id = await self.db.save_race(
            None, "neon_mile", "rc-recovery", [], [vars_like(r) for r in results], replay_data=replay
        )
        if token:
            self.recovery.bind_race_checkpoint(token, race_id)
        await self.recovery.mark_presentation(race_id, -1, "saved")
        await process_race_rewards(self.db, "neon_mile", race_id, self.teams[:2], results, [], "Clear", "RC Race", 10)
        return race_id, results

    async def test_consistent_backup_and_restore_round_trip(self):
        backup = await self.recovery.backup_database("roundtrip")
        await self.db.execute("UPDATE teams SET name='Changed' WHERE id=?", (self.teams[0].id,))
        changed = await self.db.get_team(self.teams[0].id)
        self.assertEqual(changed.name, "Changed")
        source, safety = await self.recovery.restore_backup(backup.name)
        self.assertEqual(source, backup)
        self.assertTrue(safety.exists())
        restored = await self.db.get_team(self.teams[0].id)
        self.assertEqual(restored.name, self.teams[0].name)

    async def test_undo_last_race_restores_pre_race_database(self):
        race_id, _ = await self._save_processed_race()
        self.assertIsNotNone(await self.db.get_race(race_id))
        self.assertIsNotNone(await self.db.team_profile(self.teams[0].id))
        undone = await self.recovery.undo_last_race()
        self.assertEqual(undone["race_id"], race_id)
        self.assertIsNone(await self.db.get_race(race_id))
        self.assertIsNone(await self.db.team_profile(self.teams[0].id))

    async def test_reprocess_latest_race_is_not_double_counted(self):
        race_id, _ = await self._save_processed_race()
        before = await self.db.team_profile(self.teams[0].id)
        self.assertEqual(int(before["races"]), 1)
        await self.recovery.reprocess_latest_race(race_id)
        after = await self.db.team_profile(self.teams[0].id)
        self.assertEqual(int(after["races"]), 1)
        marker = await self.db.fetchone("SELECT COUNT(*) AS n FROM race_processing WHERE race_id=?", (race_id,))
        self.assertEqual(int(marker["n"]), 1)

    async def test_correct_result_rebuilds_latest_race_from_checkpoint(self):
        race_id, _ = await self._save_processed_race()
        await self.recovery.correct_latest_result(race_id, int(self.teams[1].id), 1, "finish")
        row = await self.db.get_race(race_id)
        saved = json.loads(row["results_json"])
        winner = min(saved, key=lambda item: int(item["position"]))
        self.assertEqual(int(winner["team_id"]), int(self.teams[1].id))
        profile_a = await self.db.team_profile(self.teams[0].id)
        profile_b = await self.db.team_profile(self.teams[1].id)
        self.assertEqual(int(profile_a["wins"]), 0)
        self.assertEqual(int(profile_b["wins"]), 1)

    async def test_old_race_rewrite_is_refused(self):
        first_id, _ = await self._save_processed_race()
        second_token = await self.recovery.create_race_checkpoint({"test": "second"})
        second_id = await self.db.save_race(None, "county_line", "second", [], [], replay_data={"version": 1, "laps": 10, "teams": [], "initial_damage_by_team_id": {}, "weather_key": "clear", "rng_state": None})
        self.recovery.bind_race_checkpoint(second_token, second_id)
        with self.assertRaises(RecoveryError):
            await self.recovery.reprocess_latest_race(first_id)

    async def test_validate_database_passes_clean_database(self):
        report = await self.recovery.validate_database()
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["integrity"], ["ok"])

    async def test_repair_team_data_fixes_invalid_json_references_and_stats(self):
        bad_parts = ["missing_part", next(iter(PARTS)), next(iter(PARTS))]
        await self.db.execute(
            "UPDATE teams SET archetype='broken', stats_json=?, parts_json=?, crew_json=?, active_sponsor_key='missing' WHERE id=?",
            (json.dumps({"nerve": 99}), json.dumps(bad_parts), json.dumps({"bad": "missing"}), self.teams[0].id),
        )
        before = await self.recovery.validate_database()
        self.assertFalse(before["ok"])
        repaired = await self.recovery.repair_team_data(self.teams[0].id)
        self.assertTrue(repaired["fixes"])
        team = await self.db.get_team(self.teams[0].id)
        team.stats.validate()
        self.assertEqual(len({PARTS[key].slot for key in team.parts}), len(team.parts))
        self.assertIsNone(team.active_sponsor_key)
        after = await self.recovery.validate_database()
        self.assertTrue(after["ok"], after)

    async def test_presentation_state_tracks_interruption_and_resume_point(self):
        race_id, _ = await self._save_processed_race()
        await self.recovery.mark_presentation(race_id, 7, "interrupted")
        state = await self.recovery.presentation_state(race_id)
        self.assertEqual(int(state["last_event_index"]), 7)
        self.assertEqual(state["status"], "interrupted")
        rows = await self.recovery.interrupted_races()
        self.assertEqual(int(rows[0]["race_id"]), race_id)

    async def test_recovery_schema_migrates_existing_database_idempotently(self):
        await self.recovery.init()
        await self.recovery.init()
        tables = {row["name"] for row in await self.db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("recovery_log", tables)
        self.assertIn("race_presentation_state", tables)


class RecoveryConcurrencyTests(unittest.IsolatedAsyncioTestCase):
    async def test_registry_snapshot_reports_and_clears_concurrent_state(self):
        registry = RaceActivityRegistry()
        first = await registry.reserve_race([1, 2], tournament_id=10)
        self.assertIsNotNone(first)
        self.assertIsNone(await registry.reserve_race([2, 3], tournament_id=11))
        snap = await registry.snapshot()
        self.assertEqual(snap["active_team_ids"], [1, 2])
        self.assertEqual(snap["active_tournament_ids"], [10])
        await registry.release(first)
        cleared = await registry.snapshot()
        self.assertEqual(cleared["active_team_ids"], [])


def vars_like(result_obj: RaceResult) -> dict:
    return {field: getattr(result_obj, field) for field in (
        "team_id", "team_name", "driver_name", "position", "laps_completed", "total_time", "points",
        "warnings", "dnf", "disqualified", "damage", "tyre_wear", "starting_damage", "overtakes",
        "crashes", "illegal_moves", "last_minute_wins", "pit_stops", "near_misses", "fastest_lap",
    )}


if __name__ == "__main__":
    unittest.main()
