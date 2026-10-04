import unittest

from data.defaults import PARTS
from models.domain import RaceState, Team
from models.enums import CarArchetype
from models.stats import DriverStats
from services.balance import build_strain, track_part_adjustment
from services.builds import BuildService
from services.race_engine import RaceEngine
from tools.balance_lab import (
    BALANCE_TARGETS,
    DEVELOPED_CREW,
    DEVELOPED_PARTS,
    crew_slot_win_rates,
    developed_team_win_rate,
    driver_profile_win_rates,
    legal_part_slot_win_rates,
    legal_part_tradeoff_failures,
    stock_archetype_win_rates,
)


def make_team(*, parts=None, crew=None, stats=None) -> Team:
    return Team(
        id=1,
        name="Balance Test",
        driver_name="Driver",
        pit_crew_name="Crew",
        car_name="Rod",
        archetype=CarArchetype.SEDAN,
        stats=stats or DriverStats(4, 4, 4, 4, 4, 4),
        parts=list(parts or []),
        owner_user_id=None,
        crew=dict(crew or {}),
    )


class BalanceTargetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # Deterministic quick samples. The full Balance Lab uses larger defaults
        # and is run before release packaging.
        cls.archetypes = stock_archetype_win_rates(40)
        cls.drivers = driver_profile_win_rates(40)
        cls.developed = developed_team_win_rate(40)
        cls.parts = legal_part_slot_win_rates(12)
        cls.crew = crew_slot_win_rates(12)

    def test_stock_archetypes_remain_inside_competitive_band(self):
        for name, rate in self.archetypes.items():
            self.assertGreaterEqual(rate, BALANCE_TARGETS["stock_archetype_min"], (name, rate))
            self.assertLessEqual(rate, BALANCE_TARGETS["stock_archetype_max"], (name, rate))

    def test_driver_allocations_do_not_create_a_super_driver(self):
        spread = max(self.drivers.values()) - min(self.drivers.values())
        self.assertLessEqual(spread, BALANCE_TARGETS["driver_profile_spread_max"])

    def test_fully_developed_team_is_not_a_near_guaranteed_winner(self):
        self.assertLessEqual(self.developed, BALANCE_TARGETS["developed_team_win_max"])

    def test_no_legal_part_dominates_its_slot(self):
        for slot, rates in self.parts.items():
            self.assertLessEqual(max(rates.values()), BALANCE_TARGETS["legal_part_slot_win_max"], slot)

    def test_no_crew_member_dominates_its_role(self):
        for slot, rates in self.crew.items():
            self.assertLessEqual(max(rates.values()), BALANCE_TARGETS["crew_member_win_max"], slot)


class BalanceStructureTests(unittest.TestCase):
    def test_every_legal_part_has_gain_and_drawback(self):
        self.assertEqual(legal_part_tradeoff_failures(), [])

    def test_crew_no_longer_stacks_permanent_car_stats(self):
        stock = make_team()
        staffed = make_team(crew=DEVELOPED_CREW)
        self.assertEqual(BuildService.effective_car_stats(stock), BuildService.effective_car_stats(staffed))
        self.assertNotEqual(BuildService.crew_effect_summary(staffed), "No specialist crew effects")

    def test_tuning_efficiency_diminishes_large_stacks(self):
        one_part = make_team(parts=[DEVELOPED_PARTS[0]])
        full = make_team(parts=DEVELOPED_PARTS)
        self.assertGreater(BuildService.tuning_efficiency(one_part), BuildService.tuning_efficiency(full))
        self.assertGreater(build_strain(full), build_strain(one_part))
        self.assertLess(BuildService.tuning_efficiency(full), 0.5)

    def test_illegal_risk_stays_six_percent_per_fitted_part(self):
        illegal = [key for key, part in PARTS.items() if "illegal_risk" in part.risk_tags]
        one = make_team(parts=[illegal[0]])
        many = make_team(parts=illegal)
        self.assertEqual(BuildService.illegal_disqualification_risk_percent(one), 6)
        self.assertEqual(BuildService.illegal_disqualification_risk_percent(many), 48)
        self.assertGreater(build_strain(many), sum(build_strain(make_team(parts=[key])) for key in illegal))

    def test_track_specialisation_changes_the_same_part_by_venue(self):
        team = make_team(parts=["salt_flat_skins"])
        salt_engine = RaceEngine("salt_ghost", [team, make_team()], seed="special-salt", weather_key="clear")
        city_engine = RaceEngine("neon_mile", [team, make_team()], seed="special-city", weather_key="clear")
        salt = track_part_adjustment(team, salt_engine.track, salt_engine.weather)
        city = track_part_adjustment(team, city_engine.track, city_engine.weather)
        self.assertNotEqual(salt, city)
        self.assertGreater(salt.speed, city.speed)

    def test_lap_time_uses_a_smooth_floor_not_a_hard_cliff(self):
        team = make_team()
        opponent = Team(
            id=2,
            name="Opponent",
            driver_name="Other",
            pit_crew_name="Other Crew",
            car_name="Other Rod",
            archetype=CarArchetype.COUPE_32,
            stats=DriverStats(4, 4, 4, 4, 4, 4),
        )
        engine = RaceEngine("salt_ghost", [team, opponent], seed="smooth-floor", weather_key="clear")
        state = RaceState(team=team, position=1)
        rng_state = engine.rng.getstate()
        fast = engine._lap_time(state, 80.0)
        engine.rng.setstate(rng_state)
        faster = engine._lap_time(state, 100.0)
        self.assertGreater(fast, faster)
        self.assertGreater(faster, 42.0)


if __name__ == "__main__":
    unittest.main()
