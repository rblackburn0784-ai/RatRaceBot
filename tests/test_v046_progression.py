import tempfile
import unittest
from pathlib import Path

from data.defaults import CREW_MEMBERS
from models.domain import RaceResult, Team
from models.enums import CarArchetype
from models.stats import DriverStats
from services.progression import (
    EMBLEMS,
    GARAGE_DECOR,
    LIVERIES,
    crew_required_level,
    crew_unlocked,
    level_for_xp,
    setup_slot_count,
    unlocked_options,
    unlocked_setup_names,
)
from services.race_engine import RaceEngine
from services.race_rewards import process_race_rewards
from services.engagement import xp_for_result
from services.race_snapshot import build_replay_snapshot, restore_replay_snapshot
from services.sponsors import SPONSORS, sponsor_by_key, sponsors_for_level
from storage.database import Database
from tools.balance_lab import BALANCE_TARGETS, sponsor_win_rates


def make_team(team_id=1, *, sponsor=None) -> Team:
    return Team(
        id=team_id,
        name="Progress Rats",
        driver_name="Grease",
        pit_crew_name="Night Shift",
        car_name="The Rustbucket",
        archetype=CarArchetype.SEDAN,
        stats=DriverStats(4, 4, 4, 4, 4, 4),
        owner_user_id=4242,
        active_sponsor_key=sponsor,
    )


class ProgressionStructureTests(unittest.TestCase):
    def test_level_boundaries_and_cap(self):
        self.assertEqual(level_for_xp(0), 1)
        self.assertEqual(level_for_xp(99), 1)
        self.assertEqual(level_for_xp(100), 2)
        self.assertEqual(level_for_xp(400), 5)
        self.assertEqual(level_for_xp(999999), 10)

    def test_garage_preset_capacity_unlocks_horizontally(self):
        self.assertEqual(setup_slot_count(1), 3)
        self.assertEqual(setup_slot_count(3), 4)
        self.assertEqual(setup_slot_count(5), 5)
        self.assertEqual(unlocked_setup_names(1), ("Street", "Dirt", "Wet"))
        self.assertEqual(unlocked_setup_names(3), ("Street", "Dirt", "Wet", "High-Speed"))
        self.assertEqual(unlocked_setup_names(5), ("Street", "Dirt", "Wet", "High-Speed", "Custom"))

    def test_identity_unlocks_are_level_gated(self):
        self.assertEqual([o.key for o in unlocked_options(LIVERIES, 1)], ["bare_primer"])
        self.assertGreater(len(unlocked_options(LIVERIES, 5)), 1)
        self.assertGreater(len(unlocked_options(EMBLEMS, 5)), 1)
        self.assertGreater(len(unlocked_options(GARAGE_DECOR, 5)), 1)
        self.assertTrue(any(o.required_level == 10 for o in LIVERIES))

    def test_specialist_crew_shortlist_opens_at_level_four(self):
        specialist = next(key for key in CREW_MEMBERS if crew_required_level(key) == 4)
        self.assertFalse(crew_unlocked(specialist, 3))
        self.assertTrue(crew_unlocked(specialist, 4))
        regular = next(key for key in CREW_MEMBERS if crew_required_level(key) == 1)
        self.assertTrue(crew_unlocked(regular, 1))

    def test_sponsor_pool_expands_with_level(self):
        self.assertEqual([s.key for s in sponsors_for_level(1)], ["county_line_diner"])
        self.assertEqual(len(sponsors_for_level(3)), 3)
        self.assertEqual(len(sponsors_for_level(5)), len(SPONSORS))

    def test_every_sponsor_has_a_real_benefit_and_drawback_mechanism(self):
        for sponsor in SPONSORS.values():
            benefits = (
                sponsor.opening_pace_bonus > 0,
                sponsor.pit_repair_bonus > 0,
                sponsor.momentum_chance_bonus > 0,
                sponsor.hazard_save_bonus > 0,
                sponsor.xp_multiplier > 1.0,
            )
            drawbacks = (
                sponsor.heat_pressure > 0,
                sponsor.illegal_scrutiny_bonus > 0,
                sponsor.pit_time_variance > 0,
                sponsor.tyre_wear_pressure > 0,
                sponsor.pace_penalty > 0,
            )
            self.assertTrue(any(benefits), sponsor.key)
            self.assertTrue(any(drawbacks), sponsor.key)
            self.assertTrue(sponsor.benefit_text)
            self.assertTrue(sponsor.drawback_text)

    def test_replay_snapshot_preserves_identity_and_sponsor(self):
        team = make_team(sponsor="moonshine_fuel")
        team.livery_key = "flame_job"
        team.emblem_key = "lucky_13"
        team.garage_decor_key = "neon_clock"
        team.intro_phrase = "Bad ideas, loud pipes, one more lap."
        snapshot = build_replay_snapshot([team], laps=7, weather_key="clear")
        restored, laps, _, weather, _ = restore_replay_snapshot(snapshot)
        self.assertEqual(laps, 7)
        self.assertEqual(weather, "clear")
        self.assertEqual(restored[0].active_sponsor_key, "moonshine_fuel")
        self.assertEqual(restored[0].livery_key, "flame_job")
        self.assertEqual(restored[0].emblem_key, "lucky_13")
        self.assertEqual(restored[0].garage_decor_key, "neon_clock")
        self.assertEqual(restored[0].intro_phrase, team.intro_phrase)

    def test_sponsor_effects_do_not_break_result_integrity(self):
        teams = [make_team(1, sponsor="moonshine_fuel")]
        for idx in range(2, 11):
            other = make_team(idx)
            other.owner_user_id = None
            other.name = f"Control {idx}"
            teams.append(other)
        _, results, _ = RaceEngine("neon_mile", teams, seed="v046-sponsor-integrity", laps=10, weather_key="clear").run()
        self.assertEqual(sorted(r.position for r in results), list(range(1, 11)))
        self.assertEqual(len({r.team_id for r in results}), 10)

    def test_sponsor_balance_guardrail(self):
        rates = sponsor_win_rates(8)
        for key, rate in rates.items():
            self.assertLessEqual(rate, BALANCE_TARGETS["sponsor_win_max"], (key, rate))


class ProgressionDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tempdir.name) / "progression.sqlite3"))
        await self.db.init()
        team = make_team(team_id=None)
        team.id = await self.db.create_team(team)
        self.team = team

    async def asyncTearDown(self):
        await self.db.close()
        self.tempdir.cleanup()

    async def test_fresh_schema_contains_progression_sponsor_identity_fields(self):
        team_cols = {row["name"] for row in await self.db.fetchall("PRAGMA table_info(teams)")}
        offer_cols = {row["name"] for row in await self.db.fetchall("PRAGMA table_info(sponsor_offers)")}
        tables = {row["name"] for row in await self.db.fetchall("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("active_sponsor_key", team_cols)
        self.assertIn("sponsor_key", offer_cols)
        self.assertIn("team_identity", tables)

    async def test_sponsor_acceptance_is_level_gated_and_only_one_can_be_active(self):
        moonshine = sponsor_by_key("moonshine_fuel")
        county = sponsor_by_key("county_line_diner")
        moon_offer = await self.db.create_sponsor_offer(self.team.id, moonshine.name, moonshine.benefit_text, moonshine.drawback_text, moonshine.key)
        with self.assertRaisesRegex(ValueError, "Level 5"):
            await self.db.accept_sponsor_offer(self.team.id, moon_offer)

        await self.db.add_team_xp(self.team.id, 400, "Garage Rookie")
        await self.db.accept_sponsor_offer(self.team.id, moon_offer)
        loaded = await self.db.get_team(self.team.id)
        self.assertEqual(loaded.active_sponsor_key, "moonshine_fuel")

        county_offer = await self.db.create_sponsor_offer(self.team.id, county.name, county.benefit_text, county.drawback_text, county.key)
        with self.assertRaisesRegex(ValueError, "current sponsor"):
            await self.db.accept_sponsor_offer(self.team.id, county_offer)
        await self.db.end_sponsor_contract(self.team.id)
        await self.db.accept_sponsor_offer(self.team.id, county_offer)
        loaded = await self.db.get_team(self.team.id)
        self.assertEqual(loaded.active_sponsor_key, "county_line_diner")

    async def test_county_line_contract_applies_its_xp_tradeoff_reward(self):
        await self.db.execute("UPDATE teams SET active_sponsor_key=? WHERE id=?", ("county_line_diner", self.team.id))
        self.team = await self.db.get_team(self.team.id)
        result = RaceResult(
            self.team.id, self.team.name, self.team.driver_name, 1, 5, 300.0, 10, 0,
            False, False, 0, 0, fastest_lap=59.0,
        )
        base = xp_for_result(result)
        await process_race_rewards(
            self.db, "neon_mile", 987654, [self.team], [result], [], "Clear", "Sponsor XP Test", 5
        )
        progress = await self.db.team_progress(self.team.id)
        self.assertEqual(progress["xp"], round(base * sponsor_by_key("county_line_diner").xp_multiplier))

    async def test_identity_roundtrip_and_delete_cleanup(self):
        await self.db.update_team_identity(
            self.team.id,
            livery_key="flame_job",
            emblem_key="lucky_13",
            garage_decor_key="neon_clock",
            intro_phrase="Shake, rattle and roll.",
        )
        loaded = await self.db.get_team(self.team.id)
        self.assertEqual(loaded.livery_key, "flame_job")
        self.assertEqual(loaded.emblem_key, "lucky_13")
        self.assertEqual(loaded.garage_decor_key, "neon_clock")
        self.assertEqual(loaded.intro_phrase, "Shake, rattle and roll.")
        await self.db.delete_team(self.team.id)
        self.assertIsNone(await self.db.team_identity(self.team.id))

    async def test_atomic_race_xp_does_not_overwrite_selected_cosmetic_title(self):
        await self.db.set_team_title(self.team.id, "Backroad Regular")
        result = {
            "team_id": self.team.id,
            "team_name": self.team.name,
            "position": 1,
            "dnf": False,
            "disqualified": False,
            "points": 10,
        }
        await self.db.process_post_race_atomic(
            race_id=123456,
            results=[result],
            xp_updates=[{"team_id": self.team.id, "xp": 30, "cosmetic_title": "Pit Lane Name"}],
            achievements=[], sponsor_offers=[], fatigue_updates=[], track_records=[],
        )
        progress = await self.db.team_progress(self.team.id)
        self.assertEqual(progress["cosmetic_title"], "Backroad Regular")
        self.assertEqual(progress["xp"], 30)


if __name__ == "__main__":
    unittest.main()
