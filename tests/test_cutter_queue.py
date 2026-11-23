"""Batch cutter tests: mixed sources, safe names, durable output folders, retry isolation."""
import sys
import tempfile
import threading
import queue
from decimal import Decimal
import unittest
from types import SimpleNamespace
from pathlib import Path
from unittest.mock import patch

from smart_media_manager.cutter_queue import (
    VIDEO_TYPES, cut_source, download_source, execute_job, job_output, new_job,
    safe_name, source_format
)
from smart_media_manager.cutter_queue_ui import BatchCutterTab
from video_clip_cutter.core import Job


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
            self.assertEqual(job_output(x), job_output(y))
            self.assertEqual(x["keyword"], "first")
            self.assertEqual(y["keyword"], "second")
            self.assertEqual(x["status"], "Queued")
            self.assertEqual(x["duration"], "4")
            self.assertEqual(job_output(x).name, "output")

    def test_new_queue_quality_defaults_and_validation(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source.mp4"
            source.write_bytes(b"video")
            default = new_job(str(source), "Local", "4", td)
            hd = new_job(str(source), "Local", "4", td, quality="1080p")
            self.assertEqual(default["quality"], "720p")
            self.assertEqual(hd["quality"], "1080p")
            with self.assertRaises(ValueError):
                new_job(str(source), "Local", "4", td, quality="4k")

    def test_download_source_quality_preference_and_legacy_fallback(self):
        self.assertIn("bv[height<=720]", source_format("720p"))
        self.assertIn("bv[height<=1080]", source_format("1080p"))
        self.assertEqual(source_format(), "bv[ext=mp4]/bv")
        self.assertNotIn("[height<=", source_format())
        for quality in (None, "720p", "1080p"):
            selected = source_format(quality)
            self.assertNotIn("+", selected)  # never request separate audio
            self.assertTrue(all(part.startswith("bv") for part in selected.split("/")))
            self.assertNotIn("ba", selected)  # no bestaudio format
        with self.assertRaises(ValueError):
            source_format("2160p")

    def test_download_video_only_uses_no_audio_or_merge_postprocessing(self):
        with tempfile.TemporaryDirectory() as td:
            job = new_job("https://www.youtube.com/watch?v=abc", "YouTube",
                          "3", td, quality="720p")
            seen = {}
            class FakeYDL:
                def __init__(self, opts):
                    seen.update(opts)
                def __enter__(self):
                    return self
                def __exit__(self, *args):
                    return False
                def extract_info(self, url, download):
                    self_test.assertTrue(download)
                    target = Path(seen["outtmpl"].replace("%(ext)s", "mp4"))
                    target.write_bytes(b"silent video")
                    return {"id": "abc"}
            self_test = self
            with patch.dict(sys.modules, {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYDL)}), \
                 patch("smart_media_manager.cutter_queue.ffmpeg_paths",
                       return_value=(None, None)):
                source = download_source(job, Path(td) / "cache",
                                         threading.Event(), lambda *args: None)
            self.assertTrue(source.is_file())
            self.assertNotIn("+", seen["format"])
            self.assertNotIn("merge_output_format", seen)
            self.assertNotIn("postprocessors", seen)


    def test_batch_cutter_uses_lossless_fast_copy_regardless_of_download_quality(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "sample.mp4"
            source.write_bytes(b"dummy")
            for label, expected in (("720p", 720), ("1080p", 1080)):
                job = new_job(str(source), "Local", "2", str(root), quality=label)
                job.pop("output_layout")
                with patch("smart_media_manager.cutter_queue.prepare_job") as prepare, \
                     patch("smart_media_manager.cutter_queue.process_job",
                           return_value=[Path("part.mp4")]) as process:
                    prepare.return_value = Job(
                        source=source, folder=job_output(job), name=job["keyword"],
                        step=Decimal("2"), total=Decimal("2"))
                    count, _ = cut_source(
                        job, source, threading.Event(), lambda *event: None)
                self.assertEqual(count, 1)
                self.assertNotIn("output_height", process.call_args.kwargs)
                self.assertFalse(process.call_args.kwargs["include_audio"])
                self.assertTrue(process.call_args.kwargs["fast_copy"])
            legacy = new_job(str(source), "Local", "2", str(root))
            legacy.pop("quality")
            legacy.pop("output_layout")
            with patch("smart_media_manager.cutter_queue.prepare_job") as prepare, \
                 patch("smart_media_manager.cutter_queue.process_job",
                       return_value=[Path("part.mp4")]) as process:
                prepare.return_value = Job(
                    source=source, folder=job_output(legacy), name=legacy["keyword"],
                    step=Decimal("2"), total=Decimal("2"))
                cut_source(legacy, source, threading.Event(), lambda *event: None)
            self.assertNotIn("output_height", process.call_args.kwargs)
            self.assertFalse(process.call_args.kwargs["include_audio"])
            self.assertTrue(process.call_args.kwargs["fast_copy"])

    def test_keyword_validation_and_retry_folder(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            path = root / "test.mp4"
            path.write_bytes(b"local")
            job = new_job(str(path), "Local", "2.5", td, 'My:Video?|')
            self.assertEqual(job["keyword"], "My Video")
            old = job_output(job)
            job["attempt"] = 1
            self.assertEqual(job_output(job), old)
            job.pop("output_layout")
            legacy = job_output(job)
            job["attempt"] = 2
            self.assertNotEqual(job_output(job), legacy)
            with self.assertRaises(ValueError):
                new_job("https://example.com/video", "YouTube", "4", td)
            with self.assertRaises(Exception):
                new_job(str(path), "Local", "0", td)

    def test_local_exec_never_downloads(self):
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / "sample.mp4"
            path.write_bytes(b"local")
            job = new_job(str(path), "Local", "4", str(Path(td) / "out"))
            job.pop("output_layout")
            cancel = threading.Event()
            notifications = []
            with patch("smart_media_manager.cutter_queue.prepare_job") as prepare, \
                 patch("smart_media_manager.cutter_queue.process_job", return_value=[Path("part.mp4")]):
                prepare.return_value = Job(
                    source=path, folder=job_output(job), name=job["keyword"],
                    step=Decimal("4"), total=Decimal("4"))
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


    def test_short_final_segment_discarded_only_in_manager(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source.mp4"
            source.write_bytes(b"test")
            job = new_job(str(source), "Local", "4", str(Path(td) / "out"))
            job.pop("output_layout")
            calls = []
            with patch("smart_media_manager.cutter_queue.prepare_job") as prepare, \
                 patch("smart_media_manager.cutter_queue.process_job") as process:
                prepare.return_value = Job(
                    source=source, folder=job_output(job), name=job["keyword"],
                    step=Decimal("4"), total=Decimal("10.5"))
                process.side_effect = lambda prepared, **kwargs: (
                    calls.append(prepared) or [Path("part1.mp4"), Path("part2.mp4")])
                count, _ = cut_source(job, source, threading.Event(), lambda *args: None)
            self.assertEqual(count, 2)
            self.assertEqual(calls[0].parts, [
                (Decimal("0"), Decimal("4")), (Decimal("4"), Decimal("4"))])

    def test_video_shorter_than_clip_is_skipped(self):
        with tempfile.TemporaryDirectory() as td:
            source = Path(td) / "source.mp4"
            source.write_bytes(b"test")
            job = new_job(str(source), "Local", "4", td)
            notes = []
            with patch("smart_media_manager.cutter_queue.prepare_job") as prepare, \
                 patch("smart_media_manager.cutter_queue.process_job") as process:
                prepare.return_value = Job(
                    source=source, folder=job_output(job), name=job["keyword"],
                    step=Decimal("4"), total=Decimal("2"))
                count, _ = cut_source(job, source, threading.Event(),
                                      lambda *args: notes.append(args))
            self.assertEqual(count, 0)
            process.assert_not_called()
            self.assertIn("Skipped", notes[-1][2])

    def test_download_next_while_first_is_cutting(self):
        """Only one download and one cut should overlap, in FIFO cut order."""
        first_cut_started = threading.Event()
        allow_first_cut_to_finish = threading.Event()
        second_download_started = threading.Event()
        jobs = [new_job("https://youtube.com/watch?v=aaa", "YouTube", "4", "/tmp"),
                new_job("https://youtube.com/watch?v=bbb", "YouTube", "4", "/tmp")]
        tab = object.__new__(BatchCutterTab)
        tab.cancel = threading.Event()
        tab.events = queue.Queue()
        tab.work_items = queue.Queue()
        for job in jobs:
            tab.work_items.put(job)
        order = []

        def downloading(job, cache, cancel, notify):
            if job["id"] == jobs[1]["id"]:
                second_download_started.set()
                self.assertTrue(first_cut_started.wait(2))
            return Path(f"{job['id']}.mp4")

        def cutting(job, source, cancel, notify):
            order.append(job["id"])
            if job["id"] == jobs[0]["id"]:
                first_cut_started.set()
                self.assertTrue(allow_first_cut_to_finish.wait(3))
            return 1, Path("/tmp/out")

        try:
            with patch("smart_media_manager.cutter_queue_ui.download_source", side_effect=downloading), \
                 patch("smart_media_manager.cutter_queue_ui.cut_source", side_effect=cutting):
                worker = threading.Thread(target=tab._worker, daemon=True)
                worker.start()
                self.assertTrue(second_download_started.wait(3))
                self.assertTrue(worker.is_alive())
                allow_first_cut_to_finish.set()
                worker.join(timeout=4)
                self.assertFalse(worker.is_alive())
        finally:
            allow_first_cut_to_finish.set()
        self.assertEqual(order, [jobs[0]["id"], jobs[1]["id"]])
        events = list(tab.events.queue)
        self.assertEqual(sum(x[0] == "finished" for x in events), 1)
        self.assertEqual([x[1] for x in events if x[0] == "state" and x[2] == "Completed"],
                         [jobs[0]["id"], jobs[1]["id"]])

    def test_new_items_join_active_pipeline(self):
        first_cut_started = threading.Event()
        allow_first_cut_to_finish = threading.Event()
        first = new_job("https://youtube.com/watch?v=abc", "YouTube", "3", "/tmp")
        second_url = "https://youtube.com/watch?v=def"
        tab = object.__new__(BatchCutterTab)
        tab.cancel = threading.Event()
        tab.events = queue.Queue()
        tab.work_items = queue.Queue()
        tab.work_items.put(first)
        tab.jobs = [first]
        tab.running = True
        class Field:
            def __init__(self, value):
                self.value = value
            def get(self):
                return self.value
            def set(self, value):
                self.value = value
        tab.keyword = Field("Live")
        tab.duration = Field("3")
        tab.quality = Field("720p")
        tab.output = Field("/tmp")
        tab.status = Field("")
        tab.links = SimpleNamespace(delete=lambda *args: None)
        tab._remember = lambda: None
        tab._save = lambda: None
        tab._refresh = lambda: None
        cut_ids = []

        def cutting(job, source, cancel, notify):
            cut_ids.append(job["id"])
            if job["id"] == first["id"]:
                first_cut_started.set()
                self.assertTrue(allow_first_cut_to_finish.wait(3))
            return 1, Path("/tmp/out")

        try:
            with patch("smart_media_manager.cutter_queue_ui.download_source",
                       side_effect=lambda job, *_: Path(f"{job['id']}.mp4")), \
                 patch("smart_media_manager.cutter_queue_ui.cut_source", side_effect=cutting):
                worker = threading.Thread(target=tab._worker, daemon=True)
                worker.start()
                self.assertTrue(first_cut_started.wait(2))
                second = new_job(second_url, "YouTube", "3", "/tmp")
                tab._finish_add([second], "YouTube", "/tmp")
                self.assertEqual(len(tab.jobs), 2)
                allow_first_cut_to_finish.set()
                worker.join(timeout=4)
                self.assertFalse(worker.is_alive())
        finally:
            allow_first_cut_to_finish.set()
        self.assertEqual(cut_ids, [first["id"], tab.jobs[1]["id"]])

    def test_interrupted_ready_state_restored_as_queued(self):
        with tempfile.TemporaryDirectory() as td:
            import json
            file = Path(td) / "cutter_queue.json"
            file.write_text(json.dumps([{
                "id": "abc", "source": "https://youtube.com/watch?v=abc",
                "kind": "YouTube", "keyword": "Example", "duration": "4",
                "output": td, "status": "Ready to Cut",
            }]), encoding="utf-8")
            tab = object.__new__(BatchCutterTab)
            tab.queue_path = file
            self.assertEqual(tab._load()[0]["status"], "Queued")


if __name__ == "__main__":
    unittest.main()
