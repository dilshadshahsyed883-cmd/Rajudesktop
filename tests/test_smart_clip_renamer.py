"""Unit and integration tests; no GUI/display or FFmpeg required."""
import tempfile
import threading
import unittest
from pathlib import Path

from smart_clip_renamer.core import (
    Cancelled, RenamerError, clean_keyword, create_plan, execute_plan,
    scan_clips, smart_order, _consecutive,
)


class SmartClipRenamerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.source = Path(self.tmp.name) / "input"
        self.source.mkdir()
        self.output = Path(self.tmp.name) / "out"

    def add(self, name, payload=b"video-stream"):
        path = self.source / name
        path.write_bytes(payload)
        return path

    def assert_separated(self, names):
        for name in names:
            self.add(name)
        clips = smart_order(scan_clips(self.source))
        self.assertEqual(len(clips), len(names))
        self.assertEqual(0, sum(_consecutive(a, b) for a, b in zip(clips, clips[1:])),
                         [c.path.name for c in clips])

    def test_separates_sequences_from_four_through_forty(self):
        for length in (4, 5, 6, 7, 8, 10, 11, 12, 20, 40):
            with self.subTest(length=length):
                for p in self.source.iterdir():
                    p.unlink()
                self.assert_separated([f"Alexander {i}.mp4" for i in range(1, length + 1)])

    def test_multiple_series_are_not_confused(self):
        self.assert_separated(
            [f"Alexander {i}.mp4" for i in range(1, 9)] +
            [f"Ronaldo {i}.mkv" for i in range(1, 7)] +
            ["intro.mov", "outro.WEBM"])

    def test_three_clips_reports_unavoidable(self):
        for i in range(1, 4):
            self.add(f"Alexander {i}.mp4")
        plan = create_plan(self.source, self.output, "Alexa")
        self.assertGreater(plan.remaining_adjacent_pairs, 0)

    def test_mixed_formats_copy_bytes_and_preserve_input(self):
        samples = [("Alexander 1.mp4", b"\x00\xffclip1"),
                   ("Alexander 2.mov", b"abcdefg"),
                   ("Ronaldo 1.mkv", b"video3"),
                   ("Ronaldo 2.webm", b"video4"),
                   ("unused.txt", b"not a video")]
        for name, data in samples:
            self.add(name, data)
        plan = create_plan(self.source, self.output, "Alexa")
        self.assertEqual(4, len(plan.items))
        actual_dir = execute_plan(plan)
        self.assertEqual(actual_dir, plan.destination)
        self.assertEqual(sorted(p.name for p in actual_dir.iterdir()),
                         sorted(item.renamed for item in plan.items))
        for item in plan.items:
            self.assertEqual(item.original.read_bytes(),
                             (actual_dir / item.renamed).read_bytes())
        for name, data in samples:
            self.assertEqual(data, (self.source / name).read_bytes())

    def test_does_not_overwrite_existing_output(self):
        self.add("test 1.mp4")
        plan = create_plan(self.source, self.output, "Alexa")
        plan.destination.mkdir(parents=True)
        existing = plan.destination / "do-not-delete.txt"
        existing.write_text("keep")
        with self.assertRaises(FileExistsError):
            execute_plan(plan)
        self.assertEqual("keep", existing.read_text())

    def test_cancel_cleans_only_own_job(self):
        self.add("Alexander 1.mp4", b"a" * 200)
        self.output.mkdir()
        existing = self.output / "keep.txt"
        existing.write_text("keep")
        plan = create_plan(self.source, self.output, "Alexa")
        stopped = threading.Event()
        stopped.set()
        with self.assertRaises(Cancelled):
            execute_plan(plan, cancel=stopped)
        self.assertFalse(plan.destination.exists())
        self.assertEqual("keep", existing.read_text())
        self.assertTrue((self.source / "Alexander 1.mp4").exists())

    def test_invalid_windows_names(self):
        for value in ("", "CON", "con.txt", "Alexa?", "Name.", "A" * 81, "../bad"):
            with self.subTest(value=value), self.assertRaises(RenamerError):
                clean_keyword(value)
        self.assertEqual("Alexa", clean_keyword(" Alexa "))

    def test_ignores_nested_and_non_video_files(self):
        self.add("clip 1.mp4")
        self.add("ignore.txt")
        (self.source / "subfolder").mkdir()
        (self.source / "subfolder" / "clip 2.mp4").write_bytes(b"x")
        self.assertEqual(1, len(scan_clips(self.source)))

    def test_distinct_job_folders(self):
        self.add("Alexa 1.mp4")
        a = create_plan(self.source, self.output, "New")
        b = create_plan(self.source, self.output, "New")
        self.assertNotEqual(a.destination, b.destination)


if __name__ == "__main__":
    unittest.main()
