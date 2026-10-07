import unittest
from types import SimpleNamespace

import discord

import cogs.admin as admin
from services.admin_selector_compat import apply_admin_selector_compat


class AdminSelectorCompatibilityTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        apply_admin_selector_compat()

    def setUp(self):
        self.cog = SimpleNamespace(bot=SimpleNamespace(db=SimpleNamespace()))
        self.teams = [
            SimpleNamespace(
                id=1,
                name="The Saints",
                driver_name="The Dude",
                car_name="White Russian",
            ),
            SimpleNamespace(
                id=2,
                name="The Sinners",
                driver_name="Walter",
                car_name="Over the Line",
            ),
        ]
        self.tournaments = [
            {"id": 1, "name": "Blacktop Cup", "status": "open"},
        ]

    def test_team_selector_no_longer_assigns_reserved_parent(self):
        async def callback(interaction, team):
            return None

        view = admin.TeamSelectView(self.cog, 123, self.teams, callback)
        item = view.children[0]
        self.assertIs(item.select_view, view)
        self.assertIsInstance(item, discord.ui.Select)

    def test_multi_team_selector_no_longer_assigns_reserved_parent(self):
        async def callback(interaction, team_ids):
            return None

        view = admin.TeamMultiSelectView(self.cog, 123, self.teams, callback)
        item = view.children[0]
        self.assertIs(item.select_view, view)
        self.assertEqual(item.max_values, 2)

    def test_part_selector_no_longer_assigns_reserved_parent(self):
        async def callback(interaction, part_key):
            return None

        view = admin.PartSelectView(
            123,
            self.teams[0],
            [("engine_key", "Engine", "Test engine")],
            callback,
            "Choose a part",
        )
        item = view.children[0]
        self.assertIs(item.select_view, view)

    def test_tournament_selector_no_longer_assigns_reserved_parent(self):
        async def callback(interaction, tournament):
            return None

        view = admin.TournamentSelectView(self.cog, 123, self.tournaments, callback, "Choose tournament")
        item = view.children[0]
        self.assertIs(item.select_view, view)
        self.assertEqual(item.options[0].value, "1")

    def test_track_selector_no_longer_assigns_reserved_parent(self):
        async def callback(interaction, track_key):
            return None

        view = admin.TrackSelectView(self.cog, 123, callback)
        item = view.children[0]
        self.assertIs(item.select_view, view)
        self.assertGreater(len(item.options), 0)


if __name__ == "__main__":
    unittest.main()
