import json
import tempfile
import unittest
from pathlib import Path

from cogs.menu import MainMenuView, WorldHubView
from data.defaults import CREW_MEMBERS, PARTS
from models.domain import Team
from models.enums import CarArchetype, CrewSlot, PartSlot
from models.stats import DriverStats
from services.recovery import RecoveryManager
from services.ui_safety import OneShotReliableView
from services.world_state import build_world_snapshot, career_history_embed, world_hub_embed
from storage.database import Database


def make_team(index: int) -> Team:
    return Team(
        id=None,
        name=f"World Team {index}",
        driver_name=f"Driver {index}",
        pit_crew_name=f"Crew {index}",
        car_name=f"Rod {index}",
        archetype=list(CarArchetype)[(index - 1) % len(CarArchetype)],
        stats=DriverStats(4, 4, 4, 4, 4, 4),
        owner_user_id=15000 + index,
    )


def full_parts() -> list[str]:
    chosen = []
    for slot in PartSlot:
        chosen.append(next(key for key, part in PARTS.items() if part.slot == slot and "illegal_risk" not in part.risk_tags))
    return chosen


def full_crew() -> dict[str, str]:
    chosen = {}
    for slot in CrewSlot:
        chosen[slot.value] = next(key for key, member in CREW_MEMBERS.items() if member.slot == slot)
    return chosen


def results_for(teams: list[Team], winner_index: int = 0) -> list[dict]:
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
                "fastest_lap": 52.0 + position,
            }
        )
    return rows


class PersistentWorldDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.db_path = root / "world.sqlite3"
        self.db = Database(str(self.db_path))
        await self.db.init()
        self.recovery = RecoveryManager(self.db, str(self.db_path), str(root / "backups"))
        await self.recovery.init()
        self.teams = []
        for index in range(1, 11):
            team = make_team(index)
            team.id = await self.db.create_team(team)
            self.teams.append(team)

    async def asyncTearDown(self):
        await self.db.close()
        self.tempdir.cleanup()

    async def create_finished_season(self, name="Blacktop Season One", winner_index=0):
        tournament_id = await self.db.create_tournament(name)
        for team in self.teams:
            await self.db.add_team_to_tournament(tournament_id, int(team.id))
        await self.db.set_tournament_schedule(tournament_id, ["neon_mile"])
        await self.db.save_tournament_race(
            tournament_id,
            "neon_mile",
            f"{name}-seed",
            [],
            results_for(self.teams, winner_index=winner_index),
            schedule_race_number=1,
        )
        await self.db.finalize_tournament(tournament_id)
        return tournament_id

    async def test_completed_season_creates_permanent_history_for_every_team(self):
        tournament_id = await self.create_finished_season()
        rows = await self.db.fetchall(
            "SELECT * FROM team_season_history WHERE tournament_id=? ORDER BY final_position",
            (tournament_id,),
        )
        self.assertEqual(len(rows), 10)
        self.assertEqual(int(rows[0]["team_id"]), int(self.teams[0].id))
        self.assertEqual(int(rows[0]["final_position"]), 1)
        career = await self.db.team_career_summary(int(self.teams[0].id))
        self.assertEqual(career["seasons"], 1)
        self.assertEqual(career["titles"], 1)
        self.assertEqual(career["season_podiums"], 1)

    async def test_next_season_keeps_previous_history_and_same_team_can_enter(self):
        first = await self.create_finished_season("Season One", winner_index=0)
        second = await self.db.create_tournament("Season Two")
        for team in self.teams:
            await self.db.add_team_to_tournament(second, int(team.id))
        history = await self.db.team_season_history(int(self.teams[0].id))
        self.assertEqual(len(history), 1)
        self.assertEqual(int(history[0]["tournament_id"]), first)
        self.assertTrue(await self.db.team_in_open_tournament(int(self.teams[0].id)))

    async def test_migration_backfills_pre_v05_completed_season_history(self):
        tournament_id = await self.create_finished_season("Legacy Season")
        await self.db.execute("DELETE FROM team_season_history WHERE tournament_id=?", (tournament_id,))
        self.assertEqual(await self.db.team_season_history(int(self.teams[0].id)), [])
        await self.db.init()
        history = await self.db.team_season_history(int(self.teams[0].id))
        self.assertEqual(len(history), 1)
        self.assertEqual(history[0]["season_name"], "Legacy Season")

    async def test_restore_tournament_removes_per_team_history_snapshot(self):
        tournament_id = await self.create_finished_season("Restorable Season")
        self.assertEqual(len(await self.db.team_season_history(int(self.teams[0].id))), 1)
        restored = await self.recovery.restore_tournament(tournament_id)
        self.assertFalse(restored["already_open"])
        self.assertEqual(await self.db.team_season_history(int(self.teams[0].id)), [])
        self.assertIsNone(await self.db.season_history_entry(tournament_id))
        tournament = await self.db.get_tournament(tournament_id)
        self.assertEqual(tournament["status"], "open")

    async def test_world_snapshot_guides_incomplete_team_to_garage(self):
        snapshot = await build_world_snapshot(self.db, self.teams[0])
        self.assertEqual(snapshot["next_key"], "garage")
        self.assertIn("garage", snapshot["next_action"].lower())

    async def test_world_snapshot_guides_complete_team_to_race_without_forcing_power(self):
        team = self.teams[0]
        team.parts = full_parts()
        team.crew = full_crew()
        await self.db.update_team_parts(int(team.id), team.parts)
        await self.db.update_team_crew(int(team.id), team.crew)
        await self.db.save_team_setup(int(team.id), "Street", team.parts)
        reloaded = await self.db.get_team(int(team.id))
        snapshot = await build_world_snapshot(self.db, reloaded)
        self.assertEqual(snapshot["next_key"], "race")
        self.assertEqual(snapshot["readiness"]["parts"], len(PartSlot))
        self.assertEqual(snapshot["readiness"]["crew"], len(CrewSlot))
        self.assertGreaterEqual(snapshot["readiness"]["setups"], 1)
        embed = world_hub_embed(snapshot)
        self.assertIn("Progression expands choices", embed.footer.text)

    async def test_career_history_embed_uses_frozen_season_snapshots(self):
        await self.create_finished_season("Archive Season")
        career = await self.db.team_career_summary(int(self.teams[0].id))
        seasons = await self.db.team_season_history(int(self.teams[0].id))
        embed = career_history_embed(self.teams[0], career, seasons)
        self.assertIn("Permanent Team History", embed.title)
        values = "\n".join(field.value for field in embed.fields)
        self.assertIn("Archive Season", values)


class WorldUiSafetyTests(unittest.IsolatedAsyncioTestCase):
    async def test_world_and_main_menu_respect_discord_component_row_limits(self):
        class DummyCog:
            pass

        world = WorldHubView(DummyCog(), 123, 1, "garage")
        main = MainMenuView(DummyCog(), 123, show_admin=True)

        for view in (world, main):
            self.assertLessEqual(len(view.children), 25)
            counts = {}
            for item in view.children:
                counts[item.row] = counts.get(item.row, 0) + 1
            self.assertTrue(all(count <= 5 for count in counts.values()), counts)

    async def test_one_shot_view_refuses_second_execution(self):
        view = OneShotReliableView(timeout=30)
        self.assertTrue(view.begin_once())
        self.assertFalse(view.begin_once())

    async def test_all_project_views_and_modals_use_shared_error_boundaries(self):
        root = Path(__file__).resolve().parents[1]
        checked = [
            root / "cogs" / name
            for name in ("admin.py", "menu.py", "racing.py", "teams.py", "tournaments.py", "world.py")
        ] + [root / "services" / "views.py"]
        offenders = []
        for path in checked:
            text = path.read_text(encoding="utf-8")
            if "(discord.ui.View):" in text or "(discord.ui.Modal" in text:
                offenders.append(path.name)
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()
