import unittest

import discord

from cogs.teams import DRIVER_STAT_LABELS, DriverStatSelect, DriverStatsView, TeamWizardState
from models.stats import DriverStats


class DummyWizard:
    def __init__(self, stats=None):
        self.owner_id = 123
        self.state = TeamWizardState(stats=stats)
        self.updated = False

    def update_controls(self):
        self.updated = True

    def embed(self):
        return discord.Embed(title="Team Wizard")


class FakeResponse:
    def __init__(self):
        self.edits = []

    async def edit_message(self, **kwargs):
        self.edits.append(kwargs)


class FakeInteraction:
    def __init__(self):
        self.user = type("User", (), {"id": 123})()
        self.response = FakeResponse()


class DriverStatsDropdownTests(unittest.IsolatedAsyncioTestCase):
    async def test_new_builder_starts_balanced_and_uses_three_dropdowns_per_page(self):
        view = DriverStatsView(DummyWizard())
        self.assertEqual(view.total, 24)
        self.assertEqual(view.remaining, 0)
        selects = [item for item in view.children if isinstance(item, DriverStatSelect)]
        self.assertEqual(len(selects), 3)
        self.assertEqual([item.attr for item in selects], [attr for _label, attr in DRIVER_STAT_LABELS[:3]])
        self.assertTrue(all(int(option.value) <= 4 for option in selects[0].options))

    async def test_lowering_one_stat_opens_budget_for_other_dropdowns(self):
        view = DriverStatsView(DummyWizard())
        view.values["nerve"] = 2
        view.rebuild_items()
        handling = next(
            item for item in view.children
            if isinstance(item, DriverStatSelect) and item.attr == "handling"
        )
        offered = [int(option.value) for option in handling.options]
        self.assertEqual(max(offered), 6)
        self.assertEqual(view.total, 22)
        self.assertEqual(view.remaining, 2)

    async def test_second_page_contains_remaining_three_stats(self):
        view = DriverStatsView(DummyWizard())
        view.page = 1
        view.rebuild_items()
        selects = [item for item in view.children if isinstance(item, DriverStatSelect)]
        self.assertEqual([item.attr for item in selects], [attr for _label, attr in DRIVER_STAT_LABELS[3:]])
        rows = {}
        for item in view.children:
            rows[item.row] = rows.get(item.row, 0) + 1
        self.assertTrue(all(count <= 5 for count in rows.values()))
        self.assertLessEqual(max(rows), 3)

    async def test_save_commits_valid_dropdown_values_back_to_team_wizard(self):
        wizard = DummyWizard()
        view = DriverStatsView(wizard)
        view.values.update(
            nerve=6,
            handling=5,
            aggression=2,
            mechanics=3,
            reflexes=5,
            showmanship=3,
        )
        interaction = FakeInteraction()
        await view.save_stats(interaction)
        self.assertEqual(
            wizard.state.stats,
            DriverStats(6, 5, 2, 3, 5, 3),
        )
        self.assertEqual(wizard.state.stats.total, 24)
        self.assertTrue(wizard.updated)
        self.assertTrue(interaction.response.edits)

    async def test_existing_driver_stats_are_preserved_when_editor_opens(self):
        stats = DriverStats(8, 4, 2, 3, 5, 2)
        view = DriverStatsView(DummyWizard(stats))
        self.assertEqual(view.total, 24)
        self.assertEqual(
            [view.values[attr] for _label, attr in DRIVER_STAT_LABELS],
            [8, 4, 2, 3, 5, 2],
        )


if __name__ == "__main__":
    unittest.main()
