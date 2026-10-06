import asyncio
import re
import tempfile
import unittest
from pathlib import Path

import discord
from discord import app_commands

from cogs.recovery import EXPECTED_SLASH_COMMANDS
from main import RatRodBot
from models.domain import RaceEvent, Team
from models.enums import CarArchetype, EventType
from models.stats import DriverStats
from services.media import MediaRegistry
from services.recovery import RecoveryManager
from services.streamer import RaceStreamer
from services.ui_safety import ReliableView
from services.world_state import career_history_embed
from storage.database import Database


def make_team(index: int) -> Team:
    return Team(
        id=None,
        name=f"Reliability Team {index}",
        driver_name=f"Driver {index}",
        pit_crew_name=f"Crew {index}",
        car_name=f"Rod {index}",
        archetype=list(CarArchetype)[(index - 1) % len(CarArchetype)],
        stats=DriverStats(4, 4, 4, 4, 4, 4),
        owner_user_id=21000 + index,
    )


class SeasonReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        root = Path(self.tempdir.name)
        self.db = Database(str(root / "reliability.sqlite3"))
        await self.db.init()
        self.recovery = RecoveryManager(self.db, str(root / "reliability.sqlite3"), str(root / "backups"))
        await self.recovery.init()
        self.teams = []
        for index in range(1, 11):
            team = make_team(index)
            team.id = await self.db.create_team(team)
            self.teams.append(team)

    async def asyncTearDown(self):
        await self.db.close()
        self.tempdir.cleanup()

    async def test_atomic_tournament_creation_writes_grid_and_schedule_together(self):
        team_ids = [int(team.id) for team in self.teams]
        tournament_id = await self.db.create_tournament_with_grid(
            "Atomic Season",
            team_ids,
            ["neon_mile", "county_line", "junkyard_bowl"],
        )
        self.assertEqual(await self.db.tournament_team_count(tournament_id), 10)
        schedule = await self.db.tournament_schedule(tournament_id)
        self.assertEqual([row["track_key"] for row in schedule], ["neon_mile", "county_line", "junkyard_bowl"])

    async def test_atomic_tournament_creation_rolls_back_everything_on_bad_team(self):
        team_ids = [int(team.id) for team in self.teams[:9]] + [999999]
        with self.assertRaisesRegex(ValueError, "no longer exist"):
            await self.db.create_tournament_with_grid("Broken Season", team_ids, ["neon_mile"])
        self.assertEqual(await self.db.list_tournaments(), [])
        self.assertEqual(await self.db.fetchall("SELECT * FROM tournament_teams"), [])
        self.assertEqual(await self.db.fetchall("SELECT * FROM tournament_schedule"), [])

    async def test_single_active_season_is_enforced_even_for_concurrent_create_attempts(self):
        first = self.db.create_tournament("Season A")
        second = self.db.create_tournament("Season B")
        results = await asyncio.gather(first, second, return_exceptions=True)
        successful = [value for value in results if isinstance(value, int)]
        refused = [value for value in results if isinstance(value, Exception)]
        self.assertEqual(len(successful), 1)
        self.assertEqual(len(refused), 1)
        self.assertIn("Only one championship", str(refused[0]))
        open_rows = await self.db.list_tournaments(include_closed=False)
        self.assertEqual(len(open_rows), 1)

    async def test_database_validation_checks_all_persistent_subsystems(self):
        report = await self.recovery.validate_database()
        self.assertTrue(report["ok"], report)
        self.assertEqual(report["tables_checked"], 22)

        await self.db.execute(
            "INSERT INTO sponsor_offers(team_id, sponsor_name, benefit_text, drawback_text) VALUES (?, ?, ?, ?)",
            (999999, "Ghost Sponsor", "none", "none"),
        )
        broken = await self.recovery.validate_database()
        self.assertFalse(broken["ok"])
        self.assertTrue(any("Orphaned sponsor offers" in item for item in broken["issues"]))

    async def test_database_validation_detects_legacy_multiple_open_seasons(self):
        await self.db.execute("INSERT INTO tournaments(name, status) VALUES ('Legacy A', 'open')")
        await self.db.execute("INSERT INTO tournaments(name, status) VALUES ('Legacy B', 'open')")
        report = await self.recovery.validate_database()
        self.assertFalse(report["ok"])
        self.assertTrue(any("Multiple active championships" in item for item in report["issues"]))


    async def test_empty_legacy_season_can_be_cancelled_to_repair_duplicate_open_state(self):
        first = await self.db.execute("INSERT INTO tournaments(name, status) VALUES ('Legacy A', 'open')")
        second = await self.db.execute("INSERT INTO tournaments(name, status) VALUES ('Legacy B', 'open')")
        outcome = await self.db.close_tournament(int(first.lastrowid))
        self.assertEqual(outcome, "cancelled")
        first_row = await self.db.get_tournament(int(first.lastrowid))
        second_row = await self.db.get_tournament(int(second.lastrowid))
        self.assertEqual(first_row["status"], "cancelled")
        self.assertEqual(second_row["status"], "open")
        self.assertIsNone(await self.db.season_history_entry(int(first.lastrowid)))
        report = await self.recovery.validate_database()
        self.assertTrue(report["ok"], report)


class CommandHealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_expected_command_manifest_matches_all_decorated_commands(self):
        root = Path(__file__).resolve().parents[1]
        found = set()
        for path in (root / "cogs").glob("*.py"):
            text = path.read_text(encoding="utf-8")
            found.update(re.findall(r'@app_commands\.command\(\s*name\s*=\s*["\']([^"\']+)["\']', text))
        self.assertEqual(found, EXPECTED_SLASH_COMMANDS)
        self.assertEqual(len(found), 59)

    async def test_check_failure_does_not_send_second_message_after_permission_denial(self):
        class Response:
            def is_done(self):
                return True

        class Followup:
            def __init__(self):
                self.messages = []
            async def send(self, *args, **kwargs):
                self.messages.append((args, kwargs))

        class Interaction:
            def __init__(self):
                self.response = Response()
                self.followup = Followup()

        interaction = Interaction()
        await RatRodBot.on_app_command_error(object(), interaction, app_commands.CheckFailure("denied"))
        self.assertEqual(interaction.followup.messages, [])


class MediaAndUiReliabilityTests(unittest.IsolatedAsyncioTestCase):
    async def test_race_streamer_attaches_configured_audio(self):
        with tempfile.TemporaryDirectory() as tempdir:
            audio = Path(tempdir) / "lap_leader.mp3"
            audio.write_bytes(b"fake-mp3")
            media = MediaRegistry(path=str(Path(tempdir) / "media.json"))
            media.data = {"gifs": {}, "audio": {"lap_leader": str(audio)}}
            self.assertEqual(media.audio_path("lap"), audio)

            class FakeChannel:
                def __init__(self):
                    self.calls = []
                async def send(self, content=None, **kwargs):
                    self.calls.append((content, kwargs))

            event = RaceEvent(EventType.LAP, 1, "Lap update", audio_key="lap", context={"laps": 1})
            streamer = RaceStreamer(media, tick_seconds=0)
            streamer.dynamic_gifs.render = lambda _event: None
            channel = FakeChannel()
            await streamer.stream(channel, [event])

            attachment_calls = [kwargs for _content, kwargs in channel.calls if kwargs.get("files")]
            self.assertTrue(attachment_calls)
            files = attachment_calls[-1]["files"]
            self.assertEqual(len(files), 1)
            self.assertEqual(files[0].filename, "lap_leader.mp3")
            for file in files:
                file.close()

    async def test_bound_view_disables_controls_on_timeout(self):
        class DummyView(ReliableView):
            @discord.ui.button(label="Click")
            async def click(self, interaction, button):
                pass

        class FakeMessage:
            def __init__(self):
                self.edits = []
            async def edit(self, **kwargs):
                self.edits.append(kwargs)

        view = DummyView(timeout=10)
        message = FakeMessage()
        view.bind_message(message)
        await view.on_timeout()
        self.assertTrue(all(item.disabled for item in view.children))
        self.assertEqual(message.edits[-1]["view"], view)

    async def test_permanent_history_pages_beyond_eight_seasons(self):
        team = make_team(1)
        team.id = 1
        career = {
            "seasons": 10,
            "titles": 2,
            "season_podiums": 5,
            "championship_points": 400,
            "championship_wins": 12,
            "championship_podiums": 30,
            "fastest_laps": 8,
        }
        seasons = [
            {
                "season_name": f"Season {index}",
                "final_position": index,
                "points": 100 - index,
                "wins": 1,
                "podiums": 2,
                "fastest_laps": 1,
                "awards_json": "[]",
            }
            for index in range(1, 11)
        ]
        first = career_history_embed(team, career, seasons, page=0, per_page=4)
        last = career_history_embed(team, career, seasons, page=2, per_page=4)
        self.assertIn("Page 1/3", first.footer.text)
        self.assertIn("Page 3/3", last.footer.text)
        self.assertIn("Season 9", last.fields[-1].value)
        self.assertIn("Season 10", last.fields[-1].value)


if __name__ == "__main__":
    unittest.main()
