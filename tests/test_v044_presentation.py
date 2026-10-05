import unittest

from data.defaults import TRACKS, WEATHER_CONDITIONS
from models.domain import RaceResult, RaceState, Team
from models.enums import CarArchetype, EventType
from models.stats import DriverStats
from services.preflight import race_preflight_embed
from services.race_engine import RaceEngine
from services.race_presentation import classification_embed, team_setup_summary
from services.race_presentation_core import leaderboard_checkpoints, phase_for_lap


def team(team_id: int, name: str = "Test Rats") -> Team:
    return Team(
        id=team_id,
        name=name,
        driver_name=f"Driver {team_id}",
        pit_crew_name=f"Crew {team_id}",
        car_name=f"Rod {team_id}",
        archetype=CarArchetype.COUPE_32,
        stats=DriverStats(4, 4, 4, 4, 4, 4),
        parts=[],
        crew={},
    )


class PresentationTests(unittest.TestCase):
    def test_phase_progression_is_ordered_for_all_race_lengths(self):
        order = {"opening": 1, "mid": 2, "pit": 3, "closing": 4, "final": 5}
        for laps in (5, 7, 10):
            phases = [phase_for_lap(lap, laps) for lap in range(1, laps + 1)]
            values = [order[p] for p in phases]
            self.assertEqual(values, sorted(values))
            self.assertEqual(phases[-1], "final")
            self.assertIn("pit", phases)

    def test_live_leaderboard_checkpoints_are_sparse_and_include_finish(self):
        for laps in (5, 7, 10):
            points = leaderboard_checkpoints(laps)
            self.assertIn(laps, points)
            self.assertLessEqual(len(points), 4)
            self.assertTrue(all(1 <= point <= laps for point in points))

    def test_engine_lap_events_carry_leaderboard_context(self):
        teams = [team(i + 1, f"Team {i + 1}") for i in range(5)]
        events, results, _ = RaceEngine("neon_mile", teams, seed="v044-board", laps=5).run()
        lap_events = [event for event in events if event.event_type == EventType.LAP and str(event.media_key).startswith("lap_leader")]
        self.assertTrue(lap_events)
        for event in lap_events:
            self.assertEqual(event.context.get("laps"), 5)
            board = event.context.get("leaderboard")
            self.assertIsInstance(board, list)
            self.assertEqual(len(board), 5)
            self.assertIn("gap", board[0])
            self.assertIn("damage", board[0])
            self.assertIn("tyres", board[0])
            self.assertIn("strain", board[0])
        self.assertEqual(len(results), 5)

    def test_event_context_does_not_change_deterministic_results(self):
        teams_a = [team(i + 1, f"Team {i + 1}") for i in range(5)]
        teams_b = [team(i + 1, f"Team {i + 1}") for i in range(5)]
        events_a, results_a, _ = RaceEngine("switchback_66", teams_a, seed="v044-determinism", laps=7).run()
        events_b, results_b, _ = RaceEngine("switchback_66", teams_b, seed="v044-determinism", laps=7).run()
        self.assertEqual(RaceEngine.results_to_dicts(results_a), RaceEngine.results_to_dicts(results_b))
        self.assertEqual(RaceEngine.events_to_dicts(events_a), RaceEngine.events_to_dicts(events_b))

    def test_preflight_explains_setup_without_raw_formula(self):
        t = team(1)
        text = team_setup_summary(t, TRACKS["neon_mile"], WEATHER_CONDITIONS["clear"])
        self.assertIn("Straight-line:", text)
        self.assertIn("Cornering:", text)
        self.assertIn("Reliability:", text)
        self.assertIn("Strain:", text)
        self.assertIn("Tuning:", text)
        self.assertNotIn("0.58", text)

        embed = race_preflight_embed(
            [t], TRACKS["neon_mile"].name, WEATHER_CONDITIONS["clear"],
            track_key="neon_mile", laps=10, seed="abc",
        )
        self.assertIn("10 LAPS", embed.description)
        track_field = next(field for field in embed.fields if field.name == "Track Character")
        self.assertIn("Start → Opening", track_field.value)

    def test_final_classification_has_fastest_lap_and_failure_reason(self):
        results = [
            RaceResult(1, "Winner", "One", 1, 5, 300.0, 10, 0, False, False, 10, 20, fastest_lap=58.2),
            RaceResult(2, "Broken", "Two", 2, 3, 190.0, 0, 0, True, False, 100, 60, fastest_lap=59.0),
            RaceResult(3, "Black Flag", "Three", 3, 1, 65.0, 0, 3, False, True, 5, 10, fastest_lap=60.0),
        ]
        teams = [team(1, "Winner"), team(2, "Broken"), team(3, "Black Flag")]
        events, _, _ = RaceEngine("neon_mile", teams, seed="v044-event-source", laps=5).run()
        # Use explicit failure events so this test is not dependent on random attrition.
        from models.domain import RaceEvent
        events.extend([
            RaceEvent(EventType.DESTROYED, 3, "Engine expired in the rough stuff.", actor={"team_id": 2}),
            RaceEvent(EventType.DISQUALIFIED, 1, "Three warnings brought the black flag.", actor={"team_id": 3}),
        ])
        embed = classification_embed(results, events, "Test Race")
        fields = {field.name: field.value for field in embed.fields}
        self.assertIn("⚡ Fastest Lap", fields)
        self.assertIn("Winner", fields["⚡ Fastest Lap"])
        self.assertIn("Broken", fields["DNF / DSQ Report"])
        self.assertIn("Black Flag", fields["DNF / DSQ Report"])

    def test_pit_event_records_position_and_service_context(self):
        t = team(1)
        opponent = team(2, "Opponent")
        engine = RaceEngine("neon_mile", [t, opponent], seed="v044-pit", laps=5)
        engine.states = [RaceState(t, position=1, damage=70, tyre_wear=70), RaceState(opponent, position=2)]
        engine._assign_colours()
        engine._maybe_pit(engine.states[0], 2)
        pit_events = [event for event in engine.events if event.event_type == EventType.PIT_STOP]
        self.assertEqual(len(pit_events), 1)
        context = pit_events[0].context
        self.assertEqual(context["position_before"], 1)
        self.assertIn("time_cost", context)
        self.assertIn("damage_before", context)
        self.assertIn("tyres_before", context)


if __name__ == "__main__":
    unittest.main()
