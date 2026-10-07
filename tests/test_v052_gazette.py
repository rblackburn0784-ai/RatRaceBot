import unittest

from PIL import Image, ImageDraw, ImageFont

from models.domain import RaceResult
from services.race_newspaper import (
    PANEL_LIMITS,
    _bounded_wrapped_lines,
    _compact_story,
    _gazette_recap_lines,
    _panel_lines,
    _race_label,
    _standings_heading,
    _standings_lines,
)


def result(index: int, *, team_name: str | None = None, driver_name: str | None = None) -> RaceResult:
    return RaceResult(
        team_id=index,
        team_name=team_name or f"Team {index}",
        driver_name=driver_name or f"Driver {index}",
        position=index,
        laps_completed=10,
        total_time=600.0 + index,
        points=max(0, 11 - index),
        warnings=1 if index == 2 else 0,
        dnf=False,
        disqualified=False,
        damage=index * 3,
        tyre_wear=index * 4,
        overtakes=max(0, 6 - index),
        crashes=1 if index == 3 else 0,
        illegal_moves=1 if index == 2 else 0,
        pit_stops=index % 3,
        near_misses=index,
        fastest_lap=55.0 + index,
    )


class GazettePolishTests(unittest.TestCase):
    def setUp(self):
        self.results = [
            result(
                index,
                team_name=f"Extremely Long Blacktop Racing Team Name Number {index}",
                driver_name=f"Unnecessarily Long Driver Name Number {index}",
            )
            for index in range(1, 11)
        ]

    def test_recap_is_fixed_five_lines_and_contains_no_race_metadata(self):
        lines = _gazette_recap_lines(
            self.results,
            "Admin Quick Race Race #88 Results - Boardwalk Dash",
            "Boardwalk Dash",
            "Heatwave",
            {
                "race_winner": "Extremely Long Blacktop Racing Team Name Number 1 — Unnecessarily Long Driver Name Number 1",
                "championship_situation": "Exhibition race — no championship table attached.",
                "upcoming_race": "Next: an extremely verbose event that must not enter recap.",
            },
        )
        self.assertEqual(len(lines), PANEL_LIMITS["recap"])
        joined = " ".join(lines)
        self.assertNotIn("Boardwalk Dash", joined)
        self.assertNotIn("Heatwave", joined)
        self.assertNotIn("Exhibition race", joined)
        self.assertNotIn("Admin Quick Race", joined)
        self.assertTrue(all(len(line) <= 58 for line in lines))

    def test_race_order_is_top_five_and_omits_driver_names(self):
        lines = _standings_lines(self.results)
        self.assertEqual(len(lines), 5)
        self.assertTrue(lines[0].startswith("1. "))
        self.assertTrue(lines[-1].startswith("5. "))
        joined = " ".join(lines)
        self.assertNotIn("Driver", joined)
        self.assertNotIn("6.", joined)

    def test_non_championship_uses_race_order_heading(self):
        self.assertEqual(_standings_heading(False), "RACE ORDER")
        self.assertEqual(_standings_heading(True), "FINAL STANDINGS")

    def test_story_fields_are_capped_before_rendering(self):
        story = _compact_story({
            "headline": "H" * 200,
            "championship_situation": "S" * 200,
            "rivalry_story": "R" * 200,
            "sponsor_story": "P" * 200,
            "pit_lane_quote": "Q" * 300,
        })
        self.assertLessEqual(len(story["headline"]), 62)
        self.assertLessEqual(len(story["championship_situation"]), 94)
        self.assertLessEqual(len(story["rivalry_story"]), 96)
        self.assertLessEqual(len(story["sponsor_story"]), 92)
        self.assertLessEqual(len(story["pit_lane_quote"]), 150)

    def test_panel_lines_enforce_logical_line_and_character_limits(self):
        lines = _panel_lines(
            ["A" * 100, "B" * 100, "C" * 100, "D" * 100],
            max_lines=3,
            max_chars=20,
        )
        self.assertEqual(len(lines), 3)
        self.assertTrue(all(len(line) <= 20 for line in lines))

    def test_rendered_wrap_never_exceeds_panel_budget(self):
        image = Image.new("RGB", (500, 300), "white")
        draw = ImageDraw.Draw(image)
        font = ImageFont.load_default()
        rendered = _bounded_wrapped_lines(
            draw,
            ["one two three four five six seven eight nine ten"] * 6,
            font,
            90,
            4,
        )
        self.assertEqual(len(rendered), 4)

    def test_race_label_removes_duplicate_race_word_and_results_metadata(self):
        label = _race_label("Admin Quick Race Race #8 Results - Boardwalk Dash")
        self.assertEqual(label, "Quick Race #8")


if __name__ == "__main__":
    unittest.main()
