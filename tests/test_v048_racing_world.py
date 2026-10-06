import tempfile
import unittest
from pathlib import Path

from models.domain import RaceEvent, RaceResult, Team
from models.enums import CarArchetype, EventType
from models.stats import DriverStats
from services.racing_world import (
    build_rivalry_updates,
    ensure_world_schema,
    heat_bar,
    record_race_world,
    resolve_world_event,
)
from storage.database import Database


def make_team(index: int) -> Team:
    return Team(
        id=None,
        name=f"Story Team {index}",
        driver_name=f"Story Driver {index}",
        pit_crew_name=f"Story Crew {index}",
        car_name=f"Story Rod {index}",
        archetype=list(CarArchetype)[(index - 1) % len(CarArchetype)],
        stats=DriverStats(4, 4, 4, 4, 4, 4),
        owner_user_id=9800 + index,
    )


def result(team_id: int, name: str, position: int, total_time: float, *, last_minute_wins: int = 0) -> RaceResult:
    return RaceResult(
        team_id=team_id,
        team_name=name,
        driver_name=f"Driver {team_id}",
        position=position,
        laps_completed=10,
        total_time=total_time,
        points=max(0, 11 - position),
        warnings=0,
        dnf=False,
        disqualified=False,
        damage=12,
        tyre_wear=30,
        overtakes=3 if position == 1 else 1,
        crashes=0,
        illegal_moves=0,
        last_minute_wins=last_minute_wins,
        pit_stops=0,
        near_misses=0,
        fastest_lap=52.0 + position,
    )


def car(team_id: int, name: str) -> dict:
    return {
        "team_id": team_id,
        "team_name": name,
        "driver_name": f"Driver {team_id}",
        "car_name": f"Rod {team_id}",
        "car_key": "coupe_32",
        "colour": "black" if team_id == 1 else "red",
    }


def rivalry_events() -> list[RaceEvent]:
    first = car(1, "Rust Kings")
    second = car(2, "Atomic Rats")
    return [
        RaceEvent(EventType.OVERTAKE, 3, "pass one", actor=first, target=second),
        RaceEvent(EventType.ILLEGAL_MOVE, 5, "door rub", actor=second, target=first),
        RaceEvent(EventType.OVERTAKE, 8, "pass two", actor=first, target=second),
        RaceEvent(EventType.OVERTAKE, 10, "final pass", actor=first, target=second),
        RaceEvent(EventType.LAST_MINUTE_WIN, 10, "stolen at the line", actor=first),
    ]


class RacingWorldCoreTests(unittest.TestCase):
    def test_heat_bar_matches_0_to_100_scale(self):
        self.assertEqual(heat_bar(0), "░░░░░░░░░░")
        self.assertEqual(heat_bar(72), "███████░░░")
        self.assertEqual(heat_bar(100), "██████████")

    def test_interaction_based_rivalry_tracks_requested_story_signals(self):
        results = [
            result(1, "Rust Kings", 1, 600.0, last_minute_wins=1),
            result(2, "Atomic Rats", 2, 602.0),
        ]
        updates = build_rivalry_updates(results, rivalry_events(), championship_pairs=[(1, 2)])
        self.assertEqual(len(updates), 1)
        update = updates[0]
        self.assertEqual((update["team_a_id"], update["team_b_id"]), (1, 2))
        self.assertEqual(update["overtakes"], 3)
        self.assertEqual(update["contacts"], 1)
        self.assertEqual(update["illegal_incidents"], 1)
        self.assertEqual(update["championship_battles"], 1)
        self.assertEqual(update["stolen_wins"], 1)
        self.assertEqual(update["close_finishes"], 1)
        self.assertEqual(update["heat"], 19)
        self.assertEqual(update["last_incident"], "championship battle")

    def test_explicitly_attributed_dnf_builds_large_rivalry_signal(self):
        first = car(1, "Rust Kings")
        second = car(2, "Atomic Rats")
        results = [
            result(1, "Rust Kings", 1, 600.0),
            RaceResult(
                team_id=2,
                team_name="Atomic Rats",
                driver_name="Driver 2",
                position=2,
                laps_completed=6,
                total_time=9999.0,
                points=0,
                warnings=0,
                dnf=True,
                disqualified=False,
                damage=100,
                tyre_wear=55,
            ),
        ]
        events = [
            RaceEvent(
                EventType.DESTROYED,
                6,
                "contact retirement",
                actor=second,
                context={"caused_by_team_id": 1},
            )
        ]
        update = build_rivalry_updates(results, events)[0]
        self.assertEqual(update["dnfs_caused"], 1)
        self.assertEqual(update["contacts"], 1)
        self.assertEqual(update["heat"], 8)
        self.assertEqual(update["last_incident"], "DNF caused by contact")


class RacingWorldDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tempdir.name) / "world.sqlite3"))
        await self.db.init()
        self.team_a = make_team(1)
        self.team_b = make_team(2)
        self.team_a.id = await self.db.create_team(self.team_a)
        self.team_b.id = await self.db.create_team(self.team_b)

    async def asyncTearDown(self):
        await self.db.close()
        self.tempdir.cleanup()

    async def test_world_processing_is_idempotent_and_caps_heat(self):
        results = [
            result(self.team_a.id, self.team_a.name, 1, 600.0, last_minute_wins=1),
            result(self.team_b.id, self.team_b.name, 2, 602.0),
        ]
        events = rivalry_events()
        for event in events:
            if event.actor and int(event.actor["team_id"]) == 1:
                event.actor["team_id"] = self.team_a.id
            if event.actor and int(event.actor["team_id"]) == 2:
                event.actor["team_id"] = self.team_b.id
            if event.target and int(event.target["team_id"]) == 1:
                event.target["team_id"] = self.team_a.id
            if event.target and int(event.target["team_id"]) == 2:
                event.target["team_id"] = self.team_b.id

        first = await record_race_world(self.db, 77, results, events)
        second = await record_race_world(self.db, 77, results, events)
        self.assertTrue(first["processed"])
        self.assertFalse(second["processed"])

        a, b = sorted((self.team_a.id, self.team_b.id))
        row = await self.db.fetchone(
            "SELECT heat, races FROM team_rivalries WHERE team_a_id=? AND team_b_id=?",
            (a, b),
        )
        self.assertIsNotNone(row)
        self.assertLessEqual(int(row["heat"]), 100)
        self.assertEqual(int(row["races"]), 1)

    async def test_world_event_choice_is_a_story_decision_not_a_stat_change(self):
        await ensure_world_schema(self.db)
        await self.db.execute(
            """
            INSERT INTO world_events(
                race_id, team_id, event_key, title, prompt,
                option_a, option_b, outcome_a, outcome_b
            ) VALUES (501, ?, 'crew_argument', 'Crew Argument', 'Choose.',
                      'Talk it out', 'Let them test', 'Calm garage', 'Lively garage')
            """,
            (self.team_a.id,),
        )
        row = await self.db.fetchone("SELECT id FROM world_events WHERE race_id=501")
        resolved = await resolve_world_event(self.db, int(row["id"]), "B")
        self.assertEqual(resolved["status"], "resolved")
        self.assertEqual(resolved["choice"], "B")
        self.assertEqual(resolved["outcome"], "Lively garage")
        team = await self.db.get_team(self.team_a.id)
        self.assertEqual(team.name, self.team_a.name)


if __name__ == "__main__":
    unittest.main()
