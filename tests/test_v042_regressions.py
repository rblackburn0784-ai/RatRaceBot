import asyncio
import json
import os
import tempfile
import time
import unittest
from dataclasses import asdict
from pathlib import Path
from unittest.mock import patch

from config import Settings
from data.defaults import TRACKS
from models.domain import RaceResult, Team
from models.enums import CarArchetype
from models.stats import DriverStats
from services.dynamic_gifs import DynamicRaceGifRenderer
from services.engagement import achievement_candidates, xp_for_result
from services.media import DEFAULT_REGISTRY, MediaRegistry
from services.race_activity import RaceActivityRegistry
from services.race_engine import RaceEngine
from services.race_rewards import build_track_record_candidates, process_race_rewards
from services.race_rules import official_podium, official_winner
from storage.database import Database
from cogs.tournaments import TournamentsCog


def make_team(index: int, *, parts=None) -> Team:
    return Team(
        id=index,
        name=f"Team {index}",
        driver_name=f"Driver {index}",
        pit_crew_name=f"Crew {index}",
        car_name=f"Car {index}",
        archetype=list(CarArchetype)[(index - 1) % len(CarArchetype)],
        stats=DriverStats(4, 4, 4, 4, 4, 4),
        parts=list(parts or []),
        owner_user_id=1000 + index,
        crew={},
    )


def make_result(
    team_id: int,
    position: int,
    *,
    laps=10,
    total_time=600.0,
    points=0,
    dnf=False,
    disqualified=False,
    fastest_lap=58.0,
    overtakes=0,
    crashes=0,
    illegal_moves=0,
    last_minute_wins=0,
    damage=0,
) -> RaceResult:
    return RaceResult(
        team_id=team_id,
        team_name=f"Team {team_id}",
        driver_name=f"Driver {team_id}",
        position=position,
        laps_completed=laps,
        total_time=total_time,
        points=points,
        warnings=0,
        dnf=dnf,
        disqualified=disqualified,
        damage=damage,
        tyre_wear=0,
        overtakes=overtakes,
        crashes=crashes,
        illegal_moves=illegal_moves,
        last_minute_wins=last_minute_wins,
        fastest_lap=fastest_lap,
    )


def result_dict(result: RaceResult) -> dict:
    return asdict(result)


class RaceRulesTests(unittest.TestCase):
    def test_engine_classifies_finishers_then_dnf_then_dsq_and_failed_cars_score_zero(self):
        teams = [make_team(i) for i in range(1, 11)]
        found = None
        # Find a deterministic seed containing at least one DNF/DSQ, then verify global invariants.
        for i in range(250):
            engine = RaceEngine("junkyard_bowl", teams, seed=f"v042-classification-{i}", laps=10)
            _, results, _ = engine.run()
            if any(r.dnf or r.disqualified for r in results):
                found = results
                break
        self.assertIsNotNone(found, "stress seed search should produce at least one failed car")
        results = sorted(found, key=lambda r: r.position)
        categories = [2 if r.disqualified else 1 if r.dnf else 0 for r in results]
        self.assertEqual(categories, sorted(categories))
        for r in results:
            if r.dnf or r.disqualified:
                self.assertEqual(r.points, 0)
        winner = official_winner(results)
        if winner:
            self.assertFalse(winner.dnf)
            self.assertFalse(winner.disqualified)
            self.assertEqual(winner.position, 1)

    def test_dnf_and_dsq_never_count_as_winner_podium_or_first_win(self):
        dsq = make_result(1, 1, disqualified=True, points=10, last_minute_wins=1)
        dnf = make_result(2, 2, dnf=True, points=9, last_minute_wins=1)
        finisher = make_result(3, 3, points=8)
        results = [dsq, dnf, finisher]
        self.assertEqual(official_winner(results).team_id, 3)
        self.assertEqual([r.team_id for r in official_podium(results)], [3])
        self.assertNotIn(("first_win", "First Win"), achievement_candidates(dsq, {"podiums": 0}))
        self.assertNotIn(("first_win", "First Win"), achievement_candidates(dnf, {"podiums": 0}))
        self.assertLess(xp_for_result(dsq), xp_for_result(finisher))

    def test_timing_records_exclude_failed_cars_and_split_race_lengths(self):
        finisher = make_result(1, 1, laps=10, total_time=600, fastest_lap=55.0)
        dnf = make_result(2, 2, laps=2, total_time=100, fastest_lap=20.0, dnf=True)
        dsq = make_result(3, 3, laps=0, total_time=0, fastest_lap=1.0, disqualified=True)
        candidates = build_track_record_candidates("neon_mile", [finisher, dnf, dsq], 10)
        keyed = {item["record_key"]: item for item in candidates}
        self.assertEqual(keyed["fastest_lap"]["team_id"], 1)
        self.assertEqual(keyed["fastest_race_10"]["team_id"], 1)
        self.assertNotIn("fastest_race_5", keyed)
        self.assertNotIn("fastest_race_7", keyed)


class AsyncDatabaseTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.tempdir = tempfile.TemporaryDirectory()
        self.db = Database(str(Path(self.tempdir.name) / "test.sqlite3"))
        await self.db.init()
        self.teams = []
        for i in range(1, 12):
            team = make_team(i)
            team.id = None
            team.owner_user_id = 1000 + i
            team.id = await self.db.create_team(team)
            self.teams.append(team)

    async def asyncTearDown(self):
        await self.db.close()
        self.tempdir.cleanup()

    async def create_full_tournament(self, name="Championship"):
        tid = await self.db.create_tournament(name)
        for team in self.teams[:10]:
            await self.db.add_team_to_tournament(tid, team.id)
        return tid

    def tournament_results(self, *, dnf_team=None, dsq_team=None):
        rows = []
        for pos, team in enumerate(self.teams[:10], start=1):
            dnf = team.id == dnf_team
            dsq = team.id == dsq_team
            rows.append(
                result_dict(
                    make_result(
                        team.id,
                        pos,
                        points=0 if dnf or dsq else max(0, 11 - pos),
                        dnf=dnf,
                        disqualified=dsq,
                        laps=3 if dnf else 10,
                        total_time=180 if dnf else 600 + pos,
                    )
                )
            )
        return rows

    async def test_init_is_idempotent_and_reuses_connection(self):
        original = self.db.conn
        await self.db.init()
        self.assertIs(self.db.conn, original)
        row = await self.db.fetchone("PRAGMA integrity_check")
        self.assertEqual(row[0], "ok")

    async def test_tournament_rejects_eleventh_team(self):
        tid = await self.create_full_tournament()
        with self.assertRaisesRegex(ValueError, "maximum of 10"):
            await self.db.add_team_to_tournament(tid, self.teams[10].id)
        self.assertEqual(await self.db.tournament_team_count(tid), 10)

    async def test_tournament_race_requires_exactly_ten_entered_teams(self):
        tid = await self.db.create_tournament("Too Small")
        for team in self.teams[:9]:
            await self.db.add_team_to_tournament(tid, team.id)
        with self.assertRaisesRegex(ValueError, "exactly 10"):
            await self.db.save_tournament_race(tid, "neon_mile", "seed", [], self.tournament_results()[:9])

    async def test_manual_race_does_not_advance_saved_schedule(self):
        tid = await self.create_full_tournament()
        await self.db.set_tournament_schedule(tid, ["neon_mile", "county_line", "junkyard_bowl"])
        results = self.tournament_results()
        await self.db.save_tournament_race(tid, "salt_ghost", "manual", [], results, schedule_race_number=None)
        self.assertEqual(await self.db.next_scheduled_track(tid), (1, "neon_mile"))
        await self.db.save_tournament_race(tid, "neon_mile", "scheduled", [], results, schedule_race_number=1)
        self.assertEqual(await self.db.next_scheduled_track(tid), (2, "county_line"))
        self.assertEqual(await self.db.tournament_scheduled_race_count(tid), 1)
        self.assertEqual(await self.db.tournament_race_count(tid), 2)

    async def test_tournament_standings_never_award_win_or_podium_to_failed_result(self):
        tid = await self.create_full_tournament()
        failed_id = self.teams[0].id
        results = self.tournament_results(dsq_team=failed_id)
        # Deliberately put the DSQ in position 1 to simulate corrupt/external input.
        results[0]["position"] = 1
        results[0]["points"] = 0
        await self.db.save_tournament_race(tid, "neon_mile", "seed", [], results)
        row = await self.db.fetchone(
            "SELECT wins, podiums, points, disqualifications FROM tournament_teams WHERE tournament_id=? AND team_id=?",
            (tid, failed_id),
        )
        self.assertEqual((row["wins"], row["podiums"], row["points"], row["disqualifications"]), (0, 0, 0, 1))

    async def test_finalize_and_manual_close_write_history_and_close(self):
        for suffix in ("Auto", "Manual"):
            tid = await self.create_full_tournament(f"Championship {suffix}")
            await self.db.save_tournament_race(tid, "neon_mile", "seed", [], self.tournament_results())
            if suffix == "Auto":
                await self.db.finalize_tournament(tid)
            else:
                await self.db.close_tournament(tid)
            tournament = await self.db.get_tournament(tid)
            history = await self.db.fetchone("SELECT * FROM season_history WHERE tournament_id=?", (tid,))
            self.assertEqual(tournament["status"], "closed")
            self.assertIsNotNone(history)
            with self.assertRaisesRegex(ValueError, "closed"):
                await self.db.save_tournament_race(tid, "county_line", "late", [], self.tournament_results())

    async def test_tournament_cannot_finalize_before_a_race(self):
        tid = await self.create_full_tournament()
        with self.assertRaisesRegex(ValueError, "before at least one race"):
            await self.db.finalize_tournament(tid)

    async def test_failed_front_runners_cannot_drive_sponsors_interview_headline_or_timing_records(self):
        race_id = await self.db.save_race(None, "neon_mile", "downstream", [], [])
        dsq = make_result(self.teams[0].id, 1, disqualified=True, points=0, total_time=0, fastest_lap=1.0)
        dnf = make_result(self.teams[1].id, 2, dnf=True, points=0, total_time=90, fastest_lap=20.0)
        finisher = make_result(self.teams[2].id, 3, points=8, total_time=600, fastest_lap=55.0)
        embeds = await process_race_rewards(
            self.db, "neon_mile", race_id, self.teams[:3], [dsq, dnf, finisher], [], "Clear", "Audit Race", 10
        )
        titles = [embed.title or "" for embed in embeds]
        self.assertIn(f"Post-Race Interview: {self.teams[2].name}", titles)
        self.assertNotIn(f"Post-Race Interview: {self.teams[0].name}", titles)
        dsq_offers = await self.db.team_sponsor_offers(self.teams[0].id)
        finisher_offers = await self.db.team_sponsor_offers(self.teams[2].id)
        self.assertEqual(len(dsq_offers), 0)
        self.assertEqual(len(finisher_offers), 1)
        dsq_achievements = await self.db.team_achievements(self.teams[0].id)
        self.assertFalse(any(row["achievement_key"] == "first_win" for row in dsq_achievements))
        records = await self.db.track_records("neon_mile")
        timing = {row["record_key"]: row for row in records if row["record_key"].startswith("fastest_")}
        self.assertEqual(timing["fastest_lap"]["team_id"], self.teams[2].id)
        self.assertEqual(timing["fastest_race_10"]["team_id"], self.teams[2].id)
        gazette = next(embed for embed in embeds if embed.title == "Blacktop Gazette")
        self.assertIn(self.teams[2].name, gazette.description)
        self.assertNotIn(self.teams[0].name + " Takes", gazette.description)

    async def test_final_awards_path_closes_and_saves_history_before_presentation(self):
        tid = await self.create_full_tournament("Final Path")
        await self.db.save_tournament_race(tid, "neon_mile", "seed", [], self.tournament_results())

        class FakeMessage:
            def __init__(self):
                self.pinned = False
            async def pin(self, **kwargs):
                self.pinned = True

        class FakeChannel:
            def __init__(self):
                self.messages = []
            async def send(self, *args, **kwargs):
                msg = FakeMessage()
                self.messages.append((args, kwargs, msg))
                return msg

        class FakeBot:
            pass

        bot = FakeBot()
        bot.db = self.db
        cog = TournamentsCog(bot)
        channel = FakeChannel()
        await cog._post_final_awards(channel, tid)
        tournament = await self.db.get_tournament(tid)
        history = await self.db.fetchone("SELECT * FROM season_history WHERE tournament_id=?", (tid,))
        self.assertEqual(tournament["status"], "closed")
        self.assertIsNotNone(history)
        self.assertTrue(channel.messages and channel.messages[0][2].pinned)

    async def test_post_race_processing_is_atomic_and_idempotent(self):
        team1 = self.teams[0]
        team2 = self.teams[1]
        race_id = await self.db.save_race(None, "neon_mile", "idempotent", [], [])
        results = [
            result_dict(make_result(team1.id, 1, points=10, overtakes=2)),
            result_dict(make_result(team2.id, 2, disqualified=True, points=0, illegal_moves=1)),
        ]
        kwargs = dict(
            race_id=race_id,
            results=results,
            xp_updates=[
                {"team_id": team1.id, "xp": 30, "cosmetic_title": "Racer"},
                {"team_id": team2.id, "xp": 3, "cosmetic_title": "Garage Rookie"},
            ],
            achievements=[
                {"team_id": team1.id, "team_name": team1.name, "key": "first_win", "name": "First Win"},
            ],
            sponsor_offers=[
                {"team_id": team1.id, "team_name": team1.name, "sponsor_name": "Sponsor", "benefit": "+1", "drawback": "-1"},
            ],
            fatigue_updates=[],
            track_records=[
                {"track_key": "neon_mile", "record_key": "fastest_lap", "record_name": "Fastest Lap", "record_value": 55.0,
                 "team_id": team1.id, "team_name": team1.name, "details": "55.00s", "higher_is_better": False},
            ],
        )
        first = await self.db.process_post_race_atomic(**kwargs)
        second = await self.db.process_post_race_atomic(**kwargs)
        self.assertTrue(first["processed"])
        self.assertFalse(second["processed"])
        p1 = await self.db.team_profile(team1.id)
        p2 = await self.db.team_profile(team2.id)
        self.assertEqual((p1["races"], p1["wins"], p1["podiums"]), (1, 1, 1))
        self.assertEqual((p2["races"], p2["wins"], p2["podiums"], p2["disqualifications"]), (1, 0, 0, 1))
        progress = await self.db.team_progress(team1.id)
        self.assertEqual(progress["xp"], 30)
        offers = await self.db.team_sponsor_offers(team1.id)
        self.assertEqual(len(offers), 1)
        achievements = await self.db.team_achievements(team1.id)
        self.assertEqual(len(achievements), 1)
        marker = await self.db.fetchone("SELECT COUNT(*) AS n FROM race_processing WHERE race_id=?", (race_id,))
        self.assertEqual(marker["n"], 1)


class ActivityAndHardeningTests(unittest.IsolatedAsyncioTestCase):
    async def test_activity_registry_blocks_lobby_and_race_overlap(self):
        registry = RaceActivityRegistry()
        self.assertTrue(await registry.reserve_lobby_team(1))
        self.assertFalse(await registry.reserve_lobby_team(1))
        self.assertIsNone(await registry.reserve_race([1, 2]))
        reservation = await registry.promote_lobby_to_race([1])
        self.assertIsNotNone(reservation)
        self.assertTrue(await registry.is_team_busy(1))
        self.assertIsNone(await registry.reserve_race([1]))
        await registry.release(reservation)
        self.assertFalse(await registry.is_team_busy(1))
        tour = await registry.reserve_race([1, 2], tournament_id=99)
        self.assertIsNotNone(tour)
        self.assertIsNone(await registry.reserve_race([3, 4], tournament_id=99))
        await registry.release(tour)

    async def test_media_registry_survives_malformed_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "media_registry.json"
            path.write_text("{bad json", encoding="utf-8")
            registry = MediaRegistry(str(path))
            self.assertEqual(registry.data["gifs"]["start"], DEFAULT_REGISTRY["gifs"]["start"])

    async def test_dynamic_gif_cache_cleanup_removes_stale_and_excess_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "cache"
            output.mkdir()
            now = time.time()
            for i in range(5):
                p = output / f"{i}.gif"
                p.write_bytes(b"GIF89a")
                os.utime(p, (now - i * 10, now - i * 10))
            stale = output / "stale.gif"
            stale.write_bytes(b"GIF89a")
            os.utime(stale, (now - 10000, now - 10000))
            renderer = DynamicRaceGifRenderer(track_dir=Path(tmp), car_dir=Path(tmp), output_dir=output)
            deleted = renderer.cleanup_cache(max_files=2, max_age_seconds=100)
            self.assertGreaterEqual(deleted, 4)
            self.assertLessEqual(len(list(output.glob("*.gif"))), 2)

    async def test_config_tick_seconds_is_hardened(self):
        with patch.dict(os.environ, {"RACE_TICK_SECONDS": "not-a-number"}, clear=False):
            self.assertEqual(Settings.from_env().race_tick_seconds, 5.0)
        with patch.dict(os.environ, {"RACE_TICK_SECONDS": "999"}, clear=False):
            self.assertEqual(Settings.from_env().race_tick_seconds, 30.0)
        with patch.dict(os.environ, {"RACE_TICK_SECONDS": "-5"}, clear=False):
            self.assertEqual(Settings.from_env().race_tick_seconds, 0.0)


if __name__ == "__main__":
    unittest.main()
