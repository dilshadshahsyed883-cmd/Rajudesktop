"""Safe native-output receipt tests (the original CapCut renderer is not run)."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from capcut_home_native_queue.native_output_validation import (
    begin_export, verify_completed, NativeOutputError,
)


class OutputValidationTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.target = self.root / "render.mp4"
        self.source = self.root / "my-draft"
        self.source.mkdir()
        self.ticket = begin_export("job-1", "draft-1", str(self.source), str(self.target),
                                   now_ns=lambda: 0)

    @staticmethod
    def _ffprobe_response(video=True, duration="3.5"):
        class Result:
            returncode = 0
            stdout = json.dumps({"format": {"duration": duration}, "streams": [
                {"codec_type": "video", "width": 1280, "height": 720}] if video else
                [{"codec_type": "audio"}]})
        return Result()

    def write_file(self, path=None):
        (path or self.target).write_bytes(b"synthetic-test-media-" * 100)

    def verify(self, **kwargs):
        with patch("capcut_home_native_queue.native_output_validation.subprocess.run",
                   return_value=self._ffprobe_response()) as run:
            receipt = verify_completed(self.ticket, str(self.target),
                                       stability_seconds=0, **kwargs)
        return receipt, run

    def test_complete_receipt_bound_to_ticket(self):
        self.write_file()
        result, runner = self.verify()
        self.assertEqual(result.key, "job-1")
        self.assertEqual(result.duration_seconds, 3.5)
        self.assertEqual((result.width, result.height), (1280, 720))
        self.assertEqual(len(result.sha256), 64)
        self.assertEqual(result.size_bytes, self.target.stat().st_size)
        self.assertIn("-show_entries", runner.call_args.args[0])

    def test_missing_and_wrong_file_rejected(self):
        with self.assertRaises(NativeOutputError):
            self.verify()
        self.write_file()
        another = self.root / "foreign.mp4"
        another.write_bytes(self.target.read_bytes())
        with self.assertRaisesRegex(NativeOutputError, "differs"):
            verify_completed(self.ticket, str(another), stability_seconds=0)

    def test_existing_target_cannot_be_admitted(self):
        self.write_file()
        with self.assertRaisesRegex(NativeOutputError, "exists"):
            begin_export("job", "draft", str(self.source), str(self.target))

    def test_relative_target_rejected(self):
        with self.assertRaisesRegex(NativeOutputError, "Relative"):
            begin_export("job", "draft", str(self.source), "render.mp4")

    def test_wrong_extension_rejected(self):
        with self.assertRaisesRegex(NativeOutputError, "MP4"):
            begin_export("job", "draft", str(self.source), str(self.root / "a.avi"))

    def test_stale_mp4_rejected(self):
        self.write_file()
        ticket = begin_export("job", "draft", str(self.source), str(self.root / "other.mp4"),
                              now_ns=lambda: 9_000_000_000_000_000_000)
        other = self.root / "other.mp4"
        self.write_file(other)
        os.utime(other, ns=(1_000_000_000, 1_000_000_000))
        with self.assertRaisesRegex(NativeOutputError, "predates"):
            verify_completed(ticket, str(other), stability_seconds=0)

    def test_no_video_stream_rejected(self):
        self.write_file()
        with patch("capcut_home_native_queue.native_output_validation.subprocess.run",
                   return_value=self._ffprobe_response(video=False)):
            with self.assertRaisesRegex(NativeOutputError, "no video stream"):
                verify_completed(self.ticket, str(self.target), stability_seconds=0)

    def test_zero_duration_rejected(self):
        self.write_file()
        with patch("capcut_home_native_queue.native_output_validation.subprocess.run",
                   return_value=self._ffprobe_response(duration="0")):
            with self.assertRaisesRegex(NativeOutputError, "duration"):
                verify_completed(self.ticket, str(self.target), stability_seconds=0)

    def test_ffprobe_missing_fails_closed(self):
        self.write_file()
        with patch("capcut_home_native_queue.native_output_validation.subprocess.run",
                   side_effect=FileNotFoundError):
            with self.assertRaisesRegex(NativeOutputError, "unavailable"):
                verify_completed(self.ticket, str(self.target), stability_seconds=0)

    def test_changed_during_validation_rejected(self):
        self.write_file()
        with patch("capcut_home_native_queue.native_output_validation.subprocess.run",
                   return_value=self._ffprobe_response()):
            def mutate(_):
                with self.target.open("ab") as file:
                    file.write(b"modified during probe")
            with self.assertRaisesRegex(NativeOutputError, "changed"):
                verify_completed(self.ticket, str(self.target),
                                 stability_seconds=0.01, sleep=mutate)

    def test_no_symlink_outputs(self):
        link = self.root / "symlink.mp4"
        self.write_file()
        try:
            link.symlink_to(self.target)
        except (OSError, NotImplementedError):
            self.skipTest("Symlink creation unavailable on this Windows runner")
        with self.assertRaisesRegex(NativeOutputError, "Symlink"):
            begin_export("job", "draft", str(self.source), str(link))


if __name__ == "__main__":
    unittest.main()
