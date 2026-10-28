"""Batch cutter tests: mixed sources, safe names, durable output folders, retry isolation."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from smart_media_manager.cutter_queue import (
    VIDEO_TYPES, download_source, execute_job, job_output, new_job, safe_name
)
from smart_media_manager.cutter_queue_ui import BatchCutterTab


class CutterQueueTests(unittest.TestCase):
    def test_local_batch_jobs_protect_each_other(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            a = root / "first.mp4"
            b = root / "second.mp4"
            a.write_bytes(b"test")
            b.write_bytes(b"test")
            x = new_job(str(a), "Local", "4", str(root / "output"))
            y = new_job(str(b), "Local", "4", str(root / "output"))
            self.assertNotEqual(job_output(x), job_output(y))
            self.assertEqual(x["keyword"], "first")
            self.assertEqual(y["keyword"], "second")
            self.assertEqual(x["status"], "Queued")
            self.assertEqual(x["duration"], "4")
            self.assertTrue(job_output(x).parent.name == "output")

    def test_keyword_validation_and_retry_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "test.mp4"
            path.write_bytes(b"local")
            job = new_job(str(path), "Local", "2.5", td, 'My:Video?|')
            self.assertEqual(job["keyword"], "My Video")
            old = job_output(job)
            job["attempt"] = 1
            self.assertNotEqual(job_output(job), old)
            with self.assertRaises(ValueError):
                new_job("https://example.com/video", "YouTube", "4", td)
            with self.assertRaises(Exception):
                new_job(str(path), "Local", "0", td)

    def test_local_exec_never_downloads(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.mp4"
            path.write_bytes(b"local")
            job = new_job(str(path), "Local", "4", str(Path(td) / "out"))
            cancel = threading.Event()
            notifications = []
            with patch("smart_media_manager.cutter_queue.prepare_job") as prepare, \
                 patch("smart_media_manager.cutter_queue.process_job", return_value=[Path("part.mp4")]):
                prepare.return_value.parts = [(0, 4)]
                count, folder = execute_job(job, cancel, lambda *a: notifications.append(a), Path(td) / "cache")
            self.assertEqual(count, 1)
            self.assertEqual(folder, job_output(job))
            self.assertTrue(notifications)

    def test_cancel_prevents_work(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "local.mp4"
            path.write_bytes(b"x")
            job = new_job(str(path), "Local", "4", td)
            cancel = threading.Event()
            cancel.set()
            with self.assertRaises(RuntimeError):
                execute_job(job, cancel, lambda *a: None, Path(td) / "cache")

    def test_queued_state_restored_after_relaunch(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "source.mp4"
            path.write_bytes(b"video")
            job = new_job(str(path), "Local", "4", str(root / "output"))
            job["status"] = "Cutting"
            file = root / "cutter_queue.json"
            import json
            file.write_text(json.dumps([job]), encoding="utf-8")
            fake = object.__new__(BatchCutterTab)
            fake.queue_path = file
            loaded = BatchCutterTab._load(fake)
            self.assertEqual(loaded[0]["status"], "Queued")


if __name__ == "__main__":
    unittest.main()
