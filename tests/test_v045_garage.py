import json
import tempfile
import unittest
from pathlib import Path

from data.defaults import CREW_MEMBERS, PARTS
from models.domain import Team
from models.enums import CarArchetype, CrewSlot, PartSlot
from models.stats import DriverStats
from services.garage import (
    SETUP_PRESETS,
    compare_part,
    crew_chief_advice,
    crew_contributors,
    crew_role_summary,
    normalized_parts,
    setup_ratings,
    stars,
    team_with_candidate_part,
)
from storage.database import Database


def make_team(team_id=1, *, parts=None, crew=None, aggression=4):
    return Team(
        id=team_id,
        name="Garage Rats",
        driver_name="Grease",
        pit_crew_name="Night Shift",
        car_name="The Rustbucket",
        archetype=CarArchetype.COUPE_32,
        stats=DriverStats(4, 4, aggression, 4, 4, 4),
        parts=list(parts or []),
        owner_user_id=999,
        crew=dict(crew or {}),
    )


class GarageGameplayTests(unittest.TestCase):
    def test_five_named_presets_are_fixed(self):
        self.assertEqual(SETUP_PRESETS, ("Street", "Dirt", "Wet", "High-Speed", "Custom"))

    def test_normalized_parts_keeps_one_part_per_slot(self):
        engine_keys = [key for key, part in PARTS.items() if part.slot == PartSlot.ENGINE]
        tyre_key = next(key for key, part in PARTS.items() if part.slot == PartSlot.TYRES)
        result = normalized_parts([engine_keys[0], engine_keys[1], tyre_key, "missing_part"])
        self.assertEqual(len(result), 2)
        self.assertEqual(PARTS[result[0]].slot, PartSlot.ENGINE)
        self.assertEqual(PARTS[result[1]].slot, PartSlot.TYRES)

    def test_candidate_replaces_same_slot_without_mutating_team(self):
        engine_keys = [key for key, part in PARTS.items() if part.slot == PartSlot.ENGINE and "illegal_risk" not in part.risk_tags]
        team = make_team(parts=[engine_keys[0]])
        projected = team_with_candidate_part(team, engine_keys[1])
        self.assertEqual(team.parts, [engine_keys[0]])
        self.assertIn(engine_keys[1], projected.parts)
        self.assertNotIn(engine_keys[0], projected.parts)

    def test_part_comparison_exposes_tradeoffs_and_does_not_modify_team(self):
        tyre_keys = [key for key, part in PARTS.items() if part.slot == PartSlot.TYRES and "illegal_risk" not in part.risk_tags]
        team = make_team(parts=[tyre_keys[0]])
        before = list(team.parts)
        comparison = compare_part(team, tyre_keys[1])
        self.assertEqual(comparison.slot, PartSlot.TYRES)
        self.assertEqual(team.parts, before)
        self.assertGreaterEqual(comparison.after_tuning, 0)
        self.assertGreaterEqual(comparison.after_strain, 0)
        self.assertEqual(set(comparison.after_ratings.as_dict()), {"Fast Track", "Technical", "Wet", "Rough"})

    def test_setup_ratings_are_player_facing_one_to_five_stars(self):
        ratings = setup_ratings(make_team()).as_dict()
        for value in ratings.values():
            self.assertGreaterEqual(value, 1)
            self.assertLessEqual(value, 5)
            self.assertEqual(len(stars(value)), 5)

    def test_crew_roles_are_role_specific_and_visible(self):
        for slot in CrewSlot:
            member = next(member for member in CREW_MEMBERS.values() if member.slot == slot)
            text = crew_role_summary(member)
            self.assertIn("Role:", text)
            self.assertTrue("Helps:" in text or "Trade-off:" in text)

    def test_crew_contributors_match_race_moment(self):
        crew = {}
        for slot in CrewSlot:
            member = next(member for member in CREW_MEMBERS.values() if member.slot == slot)
            crew[slot.value] = member.key
        team = make_team(crew=crew)
        pit = " ".join(crew_contributors(team, "pit"))
        overtake = " ".join(crew_contributors(team, "overtake"))
        self.assertIn("Lead Mechanic", pit)
        self.assertIn("Tyre Changer", pit)
        self.assertIn("Spotter", overtake)

    def test_crew_chief_advice_reacts_to_missing_specialists(self):
        advice = " ".join(crew_chief_advice(make_team(aggression=7)))
        self.assertIn("Spotter", advice)
        self.assertIn("Tyre Changer", advice)


class GarageSetupDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tempdir.name) / "garage.sqlite3"))
        await self.db.init()
        team = make_team(team_id=None)
        team.id = await self.db.create_team(team)
        self.team = team

    async def asyncTearDown(self):
        await self.db.close()
        self.tempdir.cleanup()

    async def test_setup_table_migrates_and_round_trips_parts(self):
        parts = normalized_parts(list(PARTS)[:10])
        await self.db.save_team_setup(self.team.id, "Street", parts)
        row = await self.db.team_setup(self.team.id, "Street")
        self.assertIsNotNone(row)
        self.assertEqual(json.loads(row["parts_json"]), parts)
        rows = await self.db.team_setups(self.team.id)
        self.assertEqual(len(rows), 1)

    async def test_saving_same_preset_overwrites_instead_of_creating_extra_slot(self):
        engine = next(key for key, part in PARTS.items() if part.slot == PartSlot.ENGINE)
        tyres = next(key for key, part in PARTS.items() if part.slot == PartSlot.TYRES)
        await self.db.save_team_setup(self.team.id, "Wet", [engine])
        await self.db.save_team_setup(self.team.id, "Wet", [tyres])
        rows = await self.db.team_setups(self.team.id)
        self.assertEqual(len(rows), 1)
        self.assertEqual(json.loads(rows[0]["parts_json"]), [tyres])

    async def test_team_delete_cleans_saved_setups(self):
        await self.db.save_team_setup(self.team.id, "Custom", [])
        await self.db.delete_team(self.team.id)
        rows = await self.db.team_setups(self.team.id)
        self.assertEqual(rows, [])


if __name__ == "__main__":
    unittest.main()
