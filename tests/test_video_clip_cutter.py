from __future__ import annotations

import io
import shutil
import subprocess
import tempfile
import threading
import unittest
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from video_clip_cutter.core import (Job, Cancelled, CutterError, parse_duration, prepare_job,
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

    def test_optional_output_quality_scales_without_upscaling(self):
        # Headless test: inspect the FFmpeg command without real encoding.
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            source = folder / "source.mp4"
            source.write_bytes(b"source")
            commands = []

            class FakeProcess:
                returncode = 0
                def __init__(self):
                    self.stderr = io.StringIO("")
                def poll(self):
                    return 0

            def mock_popen(args, **kwargs):
                commands.append(args)
                Path(args[-1]).write_bytes(b"encoded")
                return FakeProcess()

            with patch("video_clip_cutter.core.find_executable", return_value="ffmpeg"), \
                 patch("video_clip_cutter.core.subprocess.Popen", side_effect=mock_popen):
                for quality in (720, 1080, None):
                    job = Job(source, folder / str(quality), "Frame",
                              Decimal("1"), Decimal("1"))
                    job.folder.mkdir()
                    self.assertEqual(len(process_job(job, output_height=quality)), 1)
                silent = Job(source, folder / "silent", "Frame",
                             Decimal("1"), Decimal("1"))
                silent.folder.mkdir()
                self.assertEqual(len(process_job(silent, output_height=720,
                                                 include_audio=False)), 1)
            self.assertIn("-vf", commands[0])
            self.assertIn("min(iw,1280)", commands[0][commands[0].index("-vf") + 1])
            self.assertIn("min(ih,720)", commands[0][commands[0].index("-vf") + 1])
            self.assertIn("min(iw,1920)", commands[1][commands[1].index("-vf") + 1])
            self.assertIn("min(ih,1080)", commands[1][commands[1].index("-vf") + 1])
            self.assertNotIn("-vf", commands[2])
            # Standalone cutter keeps audio unless caller requests silent output.
            self.assertIn("0:a?", commands[0])
            self.assertIn("-c:a", commands[0])
            self.assertIn("-an", commands[3])
            self.assertNotIn("0:a?", commands[3])
            self.assertNotIn("-c:a", commands[3])
            self.assertNotIn("-b:a", commands[3])
            with self.assertRaises(ValueError):
                process_job(Job(source, folder, "Bad", Decimal("1"), Decimal("1")),
                            output_height=2160)

    def test_fast_copy_command_and_no_overwrite(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            source = folder / "source.mp4"
            source.write_bytes(b"source")
            output = folder / "out"
            output.mkdir()
            job = Job(source, output, "Clip", Decimal("4"), Decimal("8"))
            seen = []
            updates = []

            class FakeProcess:
                returncode = 0
                def __init__(self):
                    self.stderr = io.StringIO("")
                def poll(self):
                    return 0

            def mock_popen(command, **kwargs):
                seen.append(command)
                stage = Path(command[-1]).parent
                (stage / "clip-000001.mp4").write_bytes(b"first")
                (stage / "clip-000002.mp4").write_bytes(b"second")
                return FakeProcess()

            with patch("video_clip_cutter.core.subprocess.Popen", side_effect=mock_popen), \
                 patch("video_clip_cutter.core.video_duration", return_value=Decimal("4")):
                clips = process_job(job, ffmpeg="ffmpeg", include_audio=False,
                                    fast_copy=True, progress=lambda i, n, p: updates.append(i))
            self.assertEqual([p.name for p in clips], ["Clip 1.mp4", "Clip 2.mp4"])
            self.assertEqual(updates, [1, 2])
            self.assertIn("copy", seen[0])
            self.assertIn("segment", seen[0])
            self.assertIn("-an", seen[0])
            self.assertNotIn("libx264", seen[0])
            self.assertFalse(any(output.glob(".fast-copy-*")))
            self.assertTrue(source.exists())

            # Another writer's completed output is never overwritten.
            with patch("video_clip_cutter.core.subprocess.Popen", side_effect=mock_popen), \
                 patch("video_clip_cutter.core.video_duration", return_value=Decimal("4")):
                with self.assertRaises(CutterError):
                    process_job(job, ffmpeg="ffmpeg", include_audio=False, fast_copy=True)
            self.assertEqual((output / "Clip 1.mp4").read_bytes(), b"first")

    def test_fast_copy_discards_all_underlength_clips_and_renumbers(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            source = base / "source.mp4"
            source.write_bytes(b"source")
            folder = base / "out"
            folder.mkdir()
            job = Job(source, folder, "Only Full", Decimal("4"), Decimal("16"))

            class FakeProcess:
                returncode = 0
                stderr = io.StringIO("")
                def poll(self):
                    return 0

            def launch(command, **kwargs):
                stage = Path(command[-1]).parent
                for number in range(1, 5):
                    (stage / f"clip-{number:06d}.mp4").write_bytes(bytes([number]))
                return FakeProcess()

            lengths = {
                "clip-000001.mp4": Decimal("4.5"),
                "clip-000002.mp4": Decimal("2.0"),
                "clip-000003.mp4": Decimal("4.0"),
                "clip-000004.mp4": Decimal("3.99"),
            }
            with patch("video_clip_cutter.core.subprocess.Popen", side_effect=launch), \
                 patch("video_clip_cutter.core.video_duration",
                       side_effect=lambda p: lengths[p.name]):
                clips = process_job(job, ffmpeg="ffmpeg", include_audio=False, fast_copy=True)

            self.assertEqual([p.name for p in clips],
                             ["Only Full 1.mp4", "Only Full 2.mp4"])
            self.assertEqual([p.read_bytes() for p in clips], [b"\x01", b"\x03"])
            self.assertFalse(any(folder.glob(".fast-copy-*")))
            self.assertTrue(source.exists())

    def test_fast_copy_zero_valid_segments_is_not_a_failure(self):
        with tempfile.TemporaryDirectory() as root:
            base = Path(root)
            source = base / "source.mp4"
            source.write_bytes(b"source")
            out = base / "out"
            out.mkdir()
            job = Job(source, out, "No Shorts", Decimal("4"), Decimal("8"))

            class FakeProcess:
                returncode = 0
                stderr = io.StringIO("")
                def poll(self):
                    return 0

            def launch(command, **kwargs):
                (Path(command[-1]).parent / "clip-000001.mp4").write_bytes(b"short")
                return FakeProcess()

            with patch("video_clip_cutter.core.subprocess.Popen", side_effect=launch), \
                 patch("video_clip_cutter.core.video_duration", return_value=Decimal("2")):
                clips = process_job(job, ffmpeg="ffmpeg", include_audio=False, fast_copy=True)
            self.assertEqual(clips, [])
            self.assertFalse(any(out.glob("*.mp4")))
            self.assertFalse(any(out.glob(".fast-copy-*")))

    def test_fast_copy_rejects_scaling_or_audio(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            job = Job(folder / "input.mp4", folder, "Clip", Decimal("4"), Decimal("8"))
            with self.assertRaises(ValueError):
                process_job(job, ffmpeg="ffmpeg", include_audio=False, fast_copy=True,
                            output_height=720)
            with self.assertRaises(ValueError):
                process_job(job, ffmpeg="ffmpeg", include_audio=True, fast_copy=True)

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

    def test_fast_copy_keyframe_segments_preserve_codec_and_skip_short_tail(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            source = folder / "original.mp4"
            subprocess.run([
                "ffmpeg", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=10",
                "-t", "17", "-c:v", "libx264",
                "-g", "50", "-keyint_min", "50", "-sc_threshold", "0",
                "-y", str(source)
            ], check=True, timeout=30)
            output = folder / "out"
            output.mkdir()
            job = Job(source, output, "Fast", Decimal("4"), Decimal("16"))
            clips = process_job(job, fast_copy=True, include_audio=False)
            # GOP/keyframes are every five seconds: three 5-second clips,
            # with the final ~1-second remainder intentionally discarded.
            self.assertEqual([p.name for p in clips],
                             ["Fast 1.mp4", "Fast 2.mp4", "Fast 3.mp4"])
            for clip in clips:
                stream_info = subprocess.check_output([
                    "ffprobe", "-v", "error", "-show_entries",
                    "stream=codec_type,codec_name", "-of",
                    "default=noprint_wrappers=1", str(clip)
                ], text=True)
                self.assertIn("codec_name=h264", stream_info)
                self.assertIn("codec_type=video", stream_info)
                self.assertNotIn("codec_type=audio", stream_info)
            self.assertTrue(source.exists())
            self.assertFalse(any(output.glob(".fast-copy-*")))

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
