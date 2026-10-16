import json
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

from cogs.tournaments import SeasonDirectorView
from models.domain import Team
from models.enums import CarArchetype
from models.stats import DriverStats
from services.recovery import RecoveryManager
from services.season_control import build_season_director_snapshot, season_director_embed
from storage.database import Database


def make_team(index: int) -> Team:
    return Team(
        id=None,
        name=f"Director Team {index}",
        driver_name=f"Driver {index}",
        pit_crew_name=f"Crew {index}",
        car_name=f"Rod {index}",
        archetype=list(CarArchetype)[(index - 1) % len(CarArchetype)],
        stats=DriverStats(4, 4, 4, 4, 4, 4),
        owner_user_id=31000 + index,
    )


def results_for(teams, winner_index=0):
    order = list(range(len(teams)))
    order.remove(winner_index)
    order.insert(0, winner_index)
    rows = []
    for position, team_index in enumerate(order, start=1):
        team = teams[team_index]
        rows.append(
            {
                "team_id": int(team.id),
                "team_name": team.name,
                "driver_name": team.driver_name,
                "position": position,
                "laps_completed": 10,
                "total_time": 600.0 + position,
                "points": max(0, 11 - position),
                "warnings": 0,
                "dnf": False,
                "disqualified": False,
                "damage": position,
                "tyre_wear": position * 2,
                "starting_damage": 0,
                "overtakes": max(0, 10 - position),
                "crashes": 0,
                "illegal_moves": 0,
                "last_minute_wins": 0,
                "pit_stops": 1,
                "near_misses": position % 2,
                "fastest_lap": 50.0 + position,
            }
        )
    return rows


class SeasonDirectorDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.db_path = root / "season-director.sqlite3"
        self.db = Database(str(self.db_path))
        await self.db.init()
        self.recovery = RecoveryManager(self.db, str(self.db_path), str(root / "backups"))
        await self.recovery.init()
        self.teams = []
        for index in range(1, 11):
            team = make_team(index)
            team.id = await self.db.create_team(team)
            self.teams.append(team)
        self.tid = await self.db.create_tournament_with_grid(
            "Director Season",
            [int(team.id) for team in self.teams],
            ["neon_mile", "county_line", "junkyard_bowl"],
        )

    async def asyncTearDown(self):
        await self.db.close()
        self.tempdir.cleanup()

    async def test_pause_keeps_season_active_and_teams_locked(self):
        await self.db.pause_tournament(self.tid)
        row = await self.db.current_tournament()
        self.assertEqual(int(row["id"]), self.tid)
        self.assertEqual(row["status"], "paused")
        self.assertTrue(await self.db.team_in_open_tournament(int(self.teams[0].id)))
        with self.assertRaisesRegex(ValueError, "Only one championship"):
            await self.db.create_tournament("Should Not Exist")
        with self.assertRaisesRegex(ValueError, "closed"):
            await self.db.save_tournament_race(
                self.tid,
                "neon_mile",
                "paused",
                [],
                results_for(self.teams),
                schedule_race_number=1,
            )

    async def test_resume_restores_racing_state(self):
        await self.db.pause_tournament(self.tid)
        await self.db.resume_tournament(self.tid)
        row = await self.db.get_tournament(self.tid)
        self.assertEqual(row["status"], "open")
        race_id = await self.db.save_tournament_race(
            self.tid,
            "neon_mile",
            "resumed",
            [],
            results_for(self.teams),
            schedule_race_number=1,
        )
        self.assertGreater(race_id, 0)

    async def test_existing_scheduled_race_backfills_operation_state_on_init(self):
        race_id = await self.db.save_tournament_race(
            self.tid,
            "neon_mile",
            "legacy-round",
            [],
            results_for(self.teams),
            schedule_race_number=1,
        )
        await self.db.execute(
            "INSERT OR IGNORE INTO race_processing(race_id) VALUES (?)",
            (race_id,),
        )
        await self.db.execute(
            "DELETE FROM season_race_state WHERE tournament_id=? AND round_number=1",
            (self.tid,),
        )
        self.assertIsNone(await self.db.latest_season_race_state(self.tid))
        await self.db.init()
        state = await self.db.latest_season_race_state(self.tid)
        self.assertEqual(state["phase"], "legacy_imported")
        self.assertEqual(int(state["race_id"]), race_id)
        self.assertEqual(int(state["race_simulated"]), 1)
        self.assertEqual(int(state["standings_updated"]), 1)
        self.assertEqual(int(state["rewards_processed"]), 1)
        self.assertEqual(int(state["gazette_generated"]), 0)

    async def test_round_operation_state_tracks_each_stage(self):
        await self.db.mark_season_race_state(
            self.tid, 1, "neon_mile", phase="simulated", race_simulated=True
        )
        await self.db.mark_season_race_state(
            self.tid, 1, "neon_mile", race_id=99, phase="standings_updated",
            standings_updated=True
        )
        await self.db.mark_season_race_state(
            self.tid, 1, "neon_mile", phase="rewards_processed", rewards_processed=True
        )
        await self.db.mark_season_race_state(
            self.tid, 1, "neon_mile", phase="complete", gazette_generated=True
        )
        state = await self.db.latest_season_race_state(self.tid)
        self.assertEqual(state["phase"], "complete")
        self.assertEqual(int(state["race_id"]), 99)
        self.assertEqual(int(state["race_simulated"]), 1)
        self.assertEqual(int(state["standings_updated"]), 1)
        self.assertEqual(int(state["rewards_processed"]), 1)
        self.assertEqual(int(state["gazette_generated"]), 1)

    async def test_director_snapshot_reports_round_leader_contenders_and_form(self):
        race_id = await self.db.save_tournament_race(
            self.tid,
            "neon_mile",
            "round-one",
            [],
            results_for(self.teams, winner_index=0),
            schedule_race_number=1,
        )
        await self.db.mark_season_race_state(
            self.tid, 1, "neon_mile", race_id=race_id, phase="complete",
            race_simulated=True, standings_updated=True, rewards_processed=True,
            gazette_generated=True,
        )
        snapshot = await build_season_director_snapshot(self.db, self.tid)
        self.assertEqual(snapshot["completed_rounds"], 1)
        self.assertEqual(snapshot["total_rounds"], 3)
        self.assertEqual(snapshot["next_entry"]["race_number"], 2)
        self.assertEqual(snapshot["next_entry"]["track_key"], "county_line")
        self.assertEqual(snapshot["leader"]["name"], self.teams[0].name)
        self.assertGreaterEqual(len(snapshot["contenders"]), 1)
        self.assertTrue(snapshot["recent_form"])
        self.assertEqual(snapshot["operation"]["phase"], "complete")
        self.assertEqual(snapshot["history_status"], "pending")
        embed = season_director_embed(snapshot)
        names = {field.name for field in embed.fields}
        self.assertIn("🏁 Next Race", names)
        self.assertIn("🥇 Championship Leader", names)
        self.assertIn("📐 Mathematical Title Picture", names)
        self.assertIn("📊 Recent Form", names)
        self.assertIn("🧰 Operation State", names)

    async def test_end_paused_season_writes_history(self):
        await self.db.save_tournament_race(
            self.tid,
            "neon_mile",
            "round-one",
            [],
            results_for(self.teams),
            schedule_race_number=1,
        )
        await self.db.pause_tournament(self.tid)
        outcome = await self.db.close_tournament(self.tid)
        self.assertEqual(outcome, "closed")
        tournament = await self.db.get_tournament(self.tid)
        self.assertEqual(tournament["status"], "closed")
        self.assertIsNotNone(await self.db.season_history_entry(self.tid))

    async def test_reopen_closed_season_removes_frozen_history_and_keeps_audit_log(self):
        await self.db.save_tournament_race(
            self.tid,
            "neon_mile",
            "round-one",
            [],
            results_for(self.teams),
            schedule_race_number=1,
        )
        await self.db.close_tournament(self.tid)
        self.assertIsNotNone(await self.db.season_history_entry(self.tid))
        result = await self.recovery.restore_tournament(self.tid)
        self.assertFalse(result["already_open"])
        tournament = await self.db.get_tournament(self.tid)
        self.assertEqual(tournament["status"], "open")
        self.assertIsNone(await self.db.season_history_entry(self.tid))
        log = await self.db.season_control_log(self.tid)
        self.assertTrue(any(row["action"] == "reopen" for row in log))


class SeasonDirectorUiTests(unittest.TestCase):
    def test_open_director_exposes_expected_controls(self):
        snapshot = {
            "tournament": {"id": 1, "name": "Season", "status": "open"},
            "races": [],
            "next_entry": {"race_number": 1, "track_key": "neon_mile", "track_name": "Neon Mile"},
        }
        cog = SimpleNamespace(bot=SimpleNamespace())
        view = SeasonDirectorView(cog, 123, snapshot)
        labels = {item.label for item in view.children}
        self.assertEqual(
            labels,
            {
                "▶ Start Next Race", "🛠 Correct Result", "↻ Refresh",
                "⏸ Pause Season", "▶ Resume Season", "🛑 Cancel Empty",
                "🏁 End Season", "♻ Reopen Season", "🏆 Championship Hub",
            },
        )
        by_label = {item.label: item for item in view.children}
        self.assertFalse(by_label["▶ Start Next Race"].disabled)
        self.assertFalse(by_label["⏸ Pause Season"].disabled)
        self.assertTrue(by_label["▶ Resume Season"].disabled)
        self.assertFalse(by_label["🛑 Cancel Empty"].disabled)
        self.assertTrue(by_label["🏁 End Season"].disabled)


if __name__ == "__main__":
    unittest.main()
