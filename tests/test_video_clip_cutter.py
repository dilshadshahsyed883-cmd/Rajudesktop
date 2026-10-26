from __future__ import annotations

import shutil
import subprocess
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path

from video_clip_cutter.core import (Cancelled, CutterError, parse_duration, prepare_job,
                                    process_job, read_settings, segments, validate_name, write_settings)


class ValidationTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(validate_name("  Nature  "), "Nature")
        for name in ("", "  ", "bad/name", "bad:name", "CON", "COM1.txt", "ending.", "test\x00"):
            with self.subTest(name=name), self.assertRaises(CutterError):
                validate_name(name)

    def test_duration(self):
        self.assertEqual(parse_duration("4"), Decimal("4"))
        self.assertEqual(parse_duration("2.5"), Decimal("2.5"))
        for value in ("0", "-5", "nan", "inf", "not a number", "3601"):
            with self.subTest(value=value), self.assertRaises(CutterError):
                parse_duration(value)

    def test_segments(self):
        self.assertEqual(segments(Decimal("17"), Decimal("4")), [
            (Decimal("0"), Decimal("4")), (Decimal("4"), Decimal("4")),
            (Decimal("8"), Decimal("4")), (Decimal("12"), Decimal("4")),
            (Decimal("16"), Decimal("1"))])
        self.assertEqual(len(segments(Decimal("0.5"), Decimal("4"))), 1)

    def test_settings(self):
        with tempfile.TemporaryDirectory() as root:
            path = Path(root) / "profile" / "settings.json"
            self.assertEqual(read_settings(path), {})
            write_settings({"duration": "7.5", "output_folder": root}, path)
            self.assertEqual(read_settings(path)["duration"], "7.5")
            path.write_text("invalid", encoding="utf-8")
            self.assertEqual(read_settings(path), {})


@unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg needed for integration")
class FfmpegTests(unittest.TestCase):
    def test_real_splitting_and_existing_file_protection(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            source = folder / "source.mp4"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=160x90:rate=10", "-t", "9", "-c:v", "mpeg4", "-y", str(source)],
                           check=True, timeout=30)
            output = folder / "out"
            job = prepare_job(source, output, "Nature", "4")
            self.assertEqual(len(job.parts), 3)
            updates = []
            written = process_job(job, progress=lambda i, n, p: updates.append(i))
            self.assertEqual([p.name for p in written], ["Nature 1.mp4", "Nature 2.mp4", "Nature 3.mp4"])
            self.assertEqual(updates, [1, 2, 3])
            self.assertTrue(all(p.stat().st_size > 0 for p in written))
            with self.assertRaises(CutterError):
                prepare_job(source, output, "Nature", "4")

    def test_cancel_preserves_source(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            source = folder / "source.mp4"
            subprocess.run(["ffmpeg", "-loglevel", "error", "-f", "lavfi", "-i",
                            "color=c=red:s=96x64:r=5", "-t", "3", "-y", str(source)], check=True, timeout=30)
            job = prepare_job(source, folder / "out", "Test", "1")
            event = threading.Event()
            event.set()
            with self.assertRaises(Cancelled):
                process_job(job, cancel=event)
            self.assertTrue(source.exists())
            self.assertFalse(any(job.folder.glob("*.mp4")))


if __name__ == "__main__":
    unittest.main()
