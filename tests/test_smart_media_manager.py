"""Unified app's settings and backend regression tests (no display required)."""
import tempfile
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from image_renamer.core import execute, make_plan, save_history, undo_last
from smart_clip_renamer.core import create_plan, execute_plan
from smart_media_manager.app import Preferences
from video_clip_cutter.core import prepare_job


class ManagerTests(unittest.TestCase):
    def test_settings_persist(self):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / "prefs.json"
            Preferences(file).set("images_output", "D:/Photos")
            self.assertEqual(Preferences(file).get("images_output"), "D:/Photos")

    def test_image_copy_and_undo(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            folder = root / "photos"
            folder.mkdir()
            a, b = folder / "Original 1.png", folder / "Original 2.jpg"
            a.write_bytes(b"png")
            b.write_bytes(b"jpg")
            out = root / "named"
            plan = make_plan([a, b], "Alexa", 1, out, in_place=False)
            self.assertEqual(execute(plan, False), 2)
            self.assertEqual((out / "Alexa 1.png").read_bytes(), b"png")
            self.assertTrue(a.is_file())
            moved = make_plan([a, b], "Rename", 3, in_place=True)
            self.assertEqual(execute(moved, True), 2)
            history = root / "last.json"
            save_history(history, moved)
            self.assertEqual(undo_last(history), 2)
            self.assertTrue(a.exists())
            self.assertTrue(b.exists())

    def test_smart_clip_copies_and_separates(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "clips"
            src.mkdir()
            for name in ("Alex 1.mp4", "Alex 2.mp4", "Other 1.mov", "Other 2.mov"):
                (src / name).write_bytes(name.encode("utf-8"))
            plan = create_plan(src, root / "output", "Alexa")
            self.assertEqual(len(plan.items), 4)
            self.assertEqual(plan.remaining_adjacent_pairs, 0)
            output = execute_plan(plan)
            self.assertEqual(len(list(output.iterdir())), 4)
            self.assertEqual(len(list(src.iterdir())), 4)
            self.assertTrue(all(x.renamed.startswith("Alexa ") for x in plan.items))

    def test_cutter_numbered_segments(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            src = root / "source.mp4"
            src.write_bytes(b"planning-only")
            with patch("video_clip_cutter.core.video_duration", return_value=Decimal("9")):
                plan = prepare_job(src, root / "out", "Alexa", "4")
            self.assertEqual(len(plan.parts), 3)
            self.assertEqual([p.name for p in plan.targets],
                             ["Alexa 1.mp4", "Alexa 2.mp4", "Alexa 3.mp4"])


if __name__ == "__main__":
    unittest.main()
