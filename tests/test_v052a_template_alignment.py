import tempfile
import unittest
from pathlib import Path

from PIL import Image

import services.race_newspaper as newspaper
from models.domain import RaceResult


def result(index: int) -> RaceResult:
    return RaceResult(
        team_id=index,
        team_name=f"Long Team Name Number {index}",
        driver_name=f"Driver {index}",
        position=index,
        laps_completed=10,
        total_time=600.0 + index,
        points=max(0, 11 - index),
        warnings=0,
        dnf=False,
        disqualified=False,
        damage=index,
        tyre_wear=index,
    )


class GazetteOriginalTemplateAlignmentTests(unittest.TestCase):
    def test_canonical_original_template_size_is_locked(self):
        self.assertEqual(newspaper.TEMPLATE_SIZE, (1103, 1426))
        self.assertEqual(len(newspaper.TEMPLATE_STANDINGS_ROW_Y), 5)
        self.assertEqual(len(newspaper.TEMPLATE_AWARD_ROW_Y), 8)
        self.assertEqual(len(newspaper.TEMPLATE_RECORD_ROW_Y), 5)

    def test_template_loader_normalises_scaled_copy_to_canonical_size(self):
        old_path = newspaper.TEMPLATE_PATH
        try:
            with tempfile.TemporaryDirectory() as tempdir:
                path = Path(tempdir) / "newspaper_template.png"
                Image.new("RGB", (2206, 2852), "white").save(path)
                newspaper.TEMPLATE_PATH = path
                loaded = newspaper._template_image()
                self.assertIsNotNone(loaded)
                self.assertEqual(loaded.size, newspaper.TEMPLATE_SIZE)
        finally:
            newspaper.TEMPLATE_PATH = old_path

    def test_template_standings_use_baked_rank_numbers_and_top_five_only(self):
        lines = newspaper._template_standings_lines([result(i) for i in range(1, 11)])
        self.assertEqual(len(lines), 5)
        self.assertFalse(any(line.startswith(("1.", "2.", "3.", "4.", "5.")) for line in lines))
        self.assertNotIn("Driver", " ".join(lines))

    def test_original_template_row_positions_are_monotonic_and_inside_panels(self):
        self.assertEqual(tuple(sorted(newspaper.TEMPLATE_STANDINGS_ROW_Y)), newspaper.TEMPLATE_STANDINGS_ROW_Y)
        self.assertTrue(all(640 < y < 750 for y in newspaper.TEMPLATE_STANDINGS_ROW_Y))
        self.assertEqual(tuple(sorted(newspaper.TEMPLATE_AWARD_ROW_Y)), newspaper.TEMPLATE_AWARD_ROW_Y)
        self.assertTrue(all(640 < y < 840 for y in newspaper.TEMPLATE_AWARD_ROW_Y))
        self.assertEqual(tuple(sorted(newspaper.TEMPLATE_RECORD_ROW_Y)), newspaper.TEMPLATE_RECORD_ROW_Y)
        self.assertTrue(all(900 < y < 1030 for y in newspaper.TEMPLATE_RECORD_ROW_Y))


if __name__ == "__main__":
    unittest.main()
