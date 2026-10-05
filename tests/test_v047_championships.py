import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from cogs.tournaments import PUBLIC_TOURNAMENT_COMMANDS
from models.domain import Team
from models.enums import CarArchetype
from models.stats import DriverStats
from services.championship import (
    build_season_awards,
    calendar_entries,
    championship_hub_embed,
    head_to_head,
    team_form,
    title_picture,
)
from storage.database import Database


def make_team(index: int) -> Team:
    return Team(
        id=None,
        name=f"Season Team {index}",
        driver_name=f"Driver {index}",
        pit_crew_name=f"Crew {index}",
        car_name=f"Rod {index}",
        archetype=list(CarArchetype)[(index - 1) % len(CarArchetype)],
        stats=DriverStats(4, 4, 4, 4, 4, 4),
        owner_user_id=7000 + index,
    )


def results_for(teams, *, winner_index=0, dnf_index=None, dsq_index=None, fastest_index=0):
    order = list(range(len(teams)))
    if winner_index in order:
        order.remove(winner_index)
        order.insert(0, winner_index)
    rows = []
    for position, team_index in enumerate(order, start=1):
        team = teams[team_index]
        dnf = team_index == dnf_index
        dsq = team_index == dsq_index
        rows.append(
            {
                "team_id": team.id,
                "team_name": team.name,
                "driver_name": team.driver_name,
                "position": position,
                "laps_completed": 4 if dnf else 10,
                "total_time": 600.0 + position,
                "points": 0 if dnf or dsq else max(0, 11 - position),
                "warnings": 1 if team_index == 8 else 0,
                "dnf": dnf,
                "disqualified": dsq,
                "damage": 80 if dnf else position * 2,
                "tyre_wear": position * 3,
                "starting_damage": 0,
                "overtakes": max(0, 10 - position),
                "crashes": 2 if dnf else 0,
                "illegal_moves": 1 if team_index == 8 else 0,
                "last_minute_wins": 1 if position == 1 and team_index == 2 else 0,
                "pit_stops": 1 if team_index in {1, 2} else 0,
                "near_misses": position % 2,
                "fastest_lap": 52.0 if team_index == fastest_index else 54.0 + position,
            }
        )
    return rows


def pit_event(team, *, quality="Fast", delta=1, cost=11.0):
    return {
        "event_type": "pit_stop",
        "lap": 5,
        "message": "pit",
        "media_key": "pit_stop",
        "audio_key": "pit_stop",
        "actor": {"team_id": team.id, "team_name": team.name},
        "target": None,
        "participants": [],
        "context": {"pit_quality": quality, "position_delta": delta, "time_cost": cost},
    }


class ChampionshipCoreTests(unittest.TestCase):
    def test_title_picture_can_report_p2_clinch(self):
        rows = [
            {"team_id": 1, "name": "Leader", "points": 22},
            {"team_id": 2, "name": "Chaser", "points": 20},
            {"team_id": 3, "name": "Third", "points": 9},
        ]
        picture = title_picture(rows, 1)
        self.assertIn("P2 or better", picture["text"])
        self.assertFalse(picture["clinched"])

    def test_title_picture_detects_mathematical_clinch(self):
        rows = [
            {"team_id": 1, "name": "Leader", "points": 42},
            {"team_id": 2, "name": "Chaser", "points": 20},
        ]
        picture = title_picture(rows, 2)
        self.assertTrue(picture["clinched"])
        self.assertIn("clinched", picture["text"])

    def test_form_head_to_head_and_calendar_are_round_based(self):
        races = [
            {
                "id": 1,
                "schedule_race_number": 1,
                "championship_round": 1,
                "results_json": json.dumps([
                    {"team_id": 1, "team_name": "A", "position": 1, "dnf": False, "disqualified": False, "fastest_lap": 50.0},
                    {"team_id": 2, "team_name": "B", "position": 2, "dnf": False, "disqualified": False, "fastest_lap": 51.0},
                ]),
                "events_json": "[]",
            },
            {
                "id": 2,
                "schedule_race_number": None,
                "championship_round": 0,
                "results_json": json.dumps([
                    {"team_id": 1, "team_name": "A", "position": 2, "dnf": False, "disqualified": False},
                    {"team_id": 2, "team_name": "B", "position": 1, "dnf": False, "disqualified": False},
                ]),
                "events_json": "[]",
            },
        ]
        schedule = [{"race_number": 1, "track_key": "neon_mile"}, {"race_number": 2, "track_key": "county_line"}]
        self.assertEqual(team_form(races, 1), ["W"])
        self.assertEqual(head_to_head(races, 1, 2), {"first": 1, "second": 0, "ties": 0, "meetings": 1})
        entries = calendar_entries(schedule, races)
        self.assertEqual(entries[0]["status"], "completed")
        self.assertEqual(entries[0]["winner"], "A")
        self.assertEqual(entries[1]["status"], "next")

    def test_all_planned_season_awards_exist(self):
        standings = []
        for i in range(1, 11):
            standings.append(
                {
                    "team_id": i,
                    "name": f"Team {i}",
                    "points": 100 - i,
                    "wins": 2 if i == 1 else 0,
                    "podiums": 3 if i <= 3 else 0,
                    "fastest_laps": 2 if i == 2 else 0,
                    "warnings": i % 2,
                    "dnfs": 1 if i == 10 else 0,
                    "disqualifications": 1 if i == 9 else 0,
                    "overtakes": i * 2,
                    "crashes": 2 if i == 10 else 0,
                    "illegal_moves": 1 if i == 9 else 0,
                    "pit_stops": 1,
                    "peak_carryover_damage": i,
                }
            )
        awards = build_season_awards(standings, [])
        keys = {award["key"] for award in awards}
        self.assertEqual(
            keys,
            {
                "champion", "runner_up", "most_wins", "most_podiums", "fastest_driver",
                "overtake_king", "cleanest_team", "dirtiest_team", "most_reliable",
                "best_pit_crew", "giant_killer", "hard_luck",
            },
        )

    def test_championship_hub_renders_core_sections(self):
        tournament = {"id": 1, "name": "Blacktop Cup", "status": "open"}
        standings = [
            {"team_id": 1, "name": "A", "points": 10, "wins": 1, "podiums": 1, "fastest_laps": 1},
            {"team_id": 2, "name": "B", "points": 9, "wins": 0, "podiums": 1, "fastest_laps": 0},
        ]
        schedule = [{"race_number": 1, "track_key": "neon_mile"}, {"race_number": 2, "track_key": "county_line"}]
        races = [{
            "id": 1,
            "schedule_race_number": 1,
            "championship_round": 1,
            "results_json": json.dumps([
                {"team_id": 1, "team_name": "A", "position": 1, "dnf": False, "disqualified": False, "fastest_lap": 50.0},
                {"team_id": 2, "team_name": "B", "position": 2, "dnf": False, "disqualified": False, "fastest_lap": 51.0},
            ]),
            "events_json": "[]",
        }]
        embed = championship_hub_embed(tournament, standings, schedule, races, [])
        names = {field.name for field in embed.fields}
        self.assertIn("Championship Standings", names)
        self.assertIn("Title Picture", names)
        self.assertIn("Head-to-Head — Top Two", names)
        self.assertIn("Calendar", names)

    def test_public_tournament_surface_is_read_only(self):
        self.assertIn("championship", PUBLIC_TOURNAMENT_COMMANDS)
        self.assertIn("tournament_standings", PUBLIC_TOURNAMENT_COMMANDS)
        self.assertNotIn("tournament_next_race", PUBLIC_TOURNAMENT_COMMANDS)
        self.assertNotIn("tournament_close", PUBLIC_TOURNAMENT_COMMANDS)


class ChampionshipDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tempdir.name) / "season.sqlite3"))
        await self.db.init()
        self.teams = []
        for i in range(1, 11):
            team = make_team(i)
            team.id = await self.db.create_team(team)
            self.teams.append(team)

    async def asyncTearDown(self):
        await self.db.close()
        self.tempdir.cleanup()

    async def create_championship(self, name="Blacktop Season", tracks=None):
        tid = await self.db.create_tournament(name)
        for team in self.teams:
            await self.db.add_team_to_tournament(tid, team.id)
        if tracks is not None:
            await self.db.set_tournament_schedule(tid, tracks)
        return tid

    async def test_fresh_schema_has_championship_fields(self):
        tt = {row["name"] for row in await self.db.fetchall("PRAGMA table_info(tournament_teams)")}
        races = {row["name"] for row in await self.db.fetchall("PRAGMA table_info(races)")}
        history = {row["name"] for row in await self.db.fetchall("PRAGMA table_info(season_history)")}
        self.assertIn("fastest_laps", tt)
        self.assertIn("championship_round", races)
        self.assertIn("awards_json", history)
        self.assertIn("summary_json", history)

    async def test_manual_race_inside_saved_calendar_is_exhibition(self):
        tid = await self.create_championship(tracks=["neon_mile", "county_line"])
        results = results_for(self.teams, fastest_index=0)
        race_id = await self.db.save_tournament_race(tid, "salt_ghost", "exhibition", [], results)
        race = await self.db.fetchone("SELECT * FROM races WHERE id=?", (race_id,))
        self.assertEqual(race["championship_round"], 0)
        self.assertEqual(await self.db.tournament_championship_race_count(tid), 0)
        self.assertEqual(await self.db.next_scheduled_track(tid), (1, "neon_mile"))
        standings = await self.db.standings(tid)
        self.assertTrue(all(int(row["points"]) == 0 for row in standings))
        self.assertTrue(all(int(row["races"]) == 0 for row in standings))
        self.assertTrue(all(int(row["fastest_laps"]) == 0 for row in standings))

    async def test_exhibition_alone_cannot_create_a_zero_point_champion(self):
        tid = await self.create_championship(name="Exhibition Only", tracks=["neon_mile", "county_line"])
        await self.db.save_tournament_race(tid, "salt_ghost", "exhibition-only", [], results_for(self.teams))
        with self.assertRaisesRegex(ValueError, "scoring round"):
            await self.db.finalize_tournament(tid)

    async def test_scheduleless_manual_tournament_race_still_scores(self):
        tid = await self.create_championship(name="Old School Manual", tracks=None)
        results = results_for(self.teams, fastest_index=0)
        race_id = await self.db.save_tournament_race(tid, "neon_mile", "manual", [], results)
        race = await self.db.fetchone("SELECT championship_round FROM races WHERE id=?", (race_id,))
        self.assertEqual(race["championship_round"], 1)
        standings = await self.db.standings(tid)
        self.assertEqual(int(standings[0]["points"]), 10)
        self.assertEqual(sum(int(row["fastest_laps"]) for row in standings), 1)

    async def test_fastest_lap_counter_excludes_failed_cars(self):
        tid = await self.create_championship(tracks=["neon_mile"])
        failed = 0
        results = results_for(self.teams, dnf_index=failed, fastest_index=failed)
        # Give a healthy car the next-best actual lap.
        for result in results:
            if result["team_id"] == self.teams[1].id:
                result["fastest_lap"] = 53.0
        await self.db.save_tournament_race(tid, "neon_mile", "round-1", [], results, schedule_race_number=1)
        rows = await self.db.standings(tid)
        by_id = {int(row["team_id"]): row for row in rows}
        self.assertEqual(int(by_id[self.teams[failed].id]["fastest_laps"]), 0)
        self.assertEqual(int(by_id[self.teams[1].id]["fastest_laps"]), 1)

    async def test_completed_season_persists_awards_and_summary(self):
        tid = await self.create_championship(tracks=["neon_mile", "county_line"])
        await self.db.save_tournament_race(
            tid,
            "neon_mile",
            "r1",
            [pit_event(self.teams[1], quality="Fast", delta=2, cost=10.5)],
            results_for(self.teams, winner_index=0, fastest_index=1),
            schedule_race_number=1,
        )
        await self.db.save_tournament_race(
            tid,
            "county_line",
            "r2",
            [pit_event(self.teams[1], quality="Fast", delta=1, cost=10.0)],
            results_for(self.teams, winner_index=1, fastest_index=1),
            schedule_race_number=2,
        )
        await self.db.finalize_tournament(tid)
        history = await self.db.season_history_entry(tid)
        awards = json.loads(history["awards_json"])
        summary = json.loads(history["summary_json"])
        self.assertEqual(summary["season_status"], "complete")
        self.assertEqual(summary["completed_scheduled_races"], 2)
        self.assertEqual(summary["scheduled_races"], 2)
        self.assertEqual({award["key"] for award in awards}, {
            "champion", "runner_up", "most_wins", "most_podiums", "fastest_driver",
            "overtake_king", "cleanest_team", "dirtiest_team", "most_reliable",
            "best_pit_crew", "giant_killer", "hard_luck",
        })
        pit_award = next(award for award in awards if award["key"] == "best_pit_crew")
        self.assertEqual(pit_award["team_id"], self.teams[1].id)

    async def test_manual_early_close_is_marked_shortened(self):
        tid = await self.create_championship(name="Short Season", tracks=["neon_mile", "county_line", "junkyard_bowl"])
        await self.db.save_tournament_race(
            tid,
            "neon_mile",
            "r1",
            [],
            results_for(self.teams),
            schedule_race_number=1,
        )
        await self.db.close_tournament(tid)
        history = await self.db.season_history_entry(tid)
        summary = json.loads(history["summary_json"])
        self.assertEqual(summary["season_status"], "shortened")
        self.assertEqual(summary["completed_scheduled_races"], 1)
        self.assertEqual(summary["scheduled_races"], 3)

    async def test_finalization_is_idempotent_and_does_not_rewrite_history(self):
        tid = await self.create_championship(name="Idempotent Season", tracks=["neon_mile"])
        await self.db.save_tournament_race(
            tid, "neon_mile", "r1", [], results_for(self.teams), schedule_race_number=1
        )
        await self.db.finalize_tournament(tid)
        first = await self.db.season_history_entry(tid)
        first_completed = first["completed_at"]
        first_awards = first["awards_json"]
        await self.db.finalize_tournament(tid)
        second = await self.db.season_history_entry(tid)
        self.assertEqual(second["completed_at"], first_completed)
        self.assertEqual(second["awards_json"], first_awards)


class ChampionshipMigrationTests(unittest.IsolatedAsyncioTestCase):
    async def test_v046_style_database_migrates_and_backfills_fastest_laps(self):
        with tempfile.TemporaryDirectory() as tempdir:
            path = Path(tempdir) / "legacy.sqlite3"
            conn = sqlite3.connect(path)
            conn.executescript(
                """
                CREATE TABLE tournament_teams (
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
                CREATE TABLE races (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tournament_id INTEGER,
                    track_key TEXT NOT NULL,
                    seed TEXT NOT NULL,
                    started_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    events_json TEXT NOT NULL,
                    results_json TEXT NOT NULL,
                    replay_json TEXT,
                    schedule_race_number INTEGER
                );
                CREATE TABLE tournament_schedule (
                    tournament_id INTEGER NOT NULL,
                    race_number INTEGER NOT NULL,
                    track_key TEXT NOT NULL,
                    PRIMARY KEY (tournament_id, race_number)
                );
                CREATE TABLE season_history (
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
                """
            )
            conn.execute("INSERT INTO tournament_teams(tournament_id, team_id) VALUES (1, 1)")
            conn.execute("INSERT INTO tournament_schedule(tournament_id, race_number, track_key) VALUES (1, 1, 'neon_mile')")
            legacy_results = json.dumps([
                {"team_id": 1, "team_name": "Legacy", "position": 1, "dnf": False, "disqualified": False, "fastest_lap": 51.2}
            ])
            conn.execute(
                "INSERT INTO races(tournament_id, track_key, seed, events_json, results_json, schedule_race_number) VALUES (1, 'neon_mile', 'old', '[]', ?, 1)",
                (legacy_results,),
            )
            conn.commit()
            conn.close()

            db = Database(str(path))
            await db.init()
            race_cols = {row["name"] for row in await db.fetchall("PRAGMA table_info(races)")}
            team_cols = {row["name"] for row in await db.fetchall("PRAGMA table_info(tournament_teams)")}
            history_cols = {row["name"] for row in await db.fetchall("PRAGMA table_info(season_history)")}
            self.assertIn("championship_round", race_cols)
            self.assertIn("fastest_laps", team_cols)
            self.assertIn("awards_json", history_cols)
            self.assertIn("summary_json", history_cols)
            race = await db.fetchone("SELECT championship_round FROM races WHERE id=1")
            standing = await db.fetchone("SELECT fastest_laps FROM tournament_teams WHERE tournament_id=1 AND team_id=1")
            self.assertEqual(int(race["championship_round"]), 1)
            self.assertEqual(int(standing["fastest_laps"]), 1)
            await db.close()


if __name__ == "__main__":
    unittest.main()
