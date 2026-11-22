"""Headless snapshot regression tests; no real YouTube network calls."""
import json
import queue
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from smart_media_manager.youtube_downloader import YoutubeTab, new_snapshot_job, snapshot_video


class LocalSnapshotsTests(unittest.TestCase):
    def config(self, video, folder):
        return {"url": "", "local_video": str(video), "output": str(folder),
                "start": "", "end": "", "interval": "2",
                "format": "JPG", "quality": "90", "resolution": "Original"}

    def test_pc_video_snapshots_without_youtube(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            video = root / "My video.mp4"
            video.write_bytes(b"fake test video")
            folder = root / "snapshots"
            events = []

            def ffmpeg(cmd, **kwargs):
                if "ffprobe" in str(cmd[0]):
                    return SimpleNamespace(stdout="4.0", returncode=0)
                Path(cmd[-1]).write_bytes(b"frame data")
                return SimpleNamespace(stdout="", returncode=0)

            with patch("smart_media_manager.youtube_downloader.ffmpeg_paths",
                       return_value=("ffmpeg", "ffprobe")), \
                 patch("smart_media_manager.youtube_downloader.subprocess.run",
                       side_effect=ffmpeg):
                count = snapshot_video(self.config(video, folder), threading.Event(),
                                       threading.Event(), lambda *a: events.append(a))
            self.assertEqual(count, 2)
            results = list((folder / "My video snapshots").glob("snapshot_*.jpg"))
            self.assertEqual(len(results), 2)
            self.assertTrue(all(p.read_bytes() == b"frame data" for p in results))
            self.assertGreater(len(events), 2)

    def test_missing_local_video_fails_without_network(self):
        with tempfile.TemporaryDirectory() as td:
            config = self.config(Path(td) / "missing.mp4", Path(td) / "output")
            with patch("smart_media_manager.youtube_downloader.ffmpeg_paths",
                       return_value=("ffmpeg", "ffprobe")):
                with self.assertRaises(ValueError):
                    snapshot_video(config, threading.Event(), threading.Event(), lambda *x: None)


class YouTubeSnapshotTests(unittest.TestCase):
    def config(self, folder):
        return {"url": "https://www.youtube.com/watch?v=X8SR49-YI_M", "local_video": "",
                "output": str(folder), "start": "", "end": "",
                "interval": "2", "format": "JPG", "quality": "90",
                "resolution": "Original"}

    def test_reuses_cutter_download_format_and_source_cache(self):
        """Snapshot source is downloaded through the production cutter engine."""
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            log = {"formats": [], "downloads": 0}

            class FakeYoutubeDL:
                def __init__(self, opts):
                    self.opts = opts
                    log["formats"].append(opts["format"])

                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    return False

                def extract_info(self, url, download):
                    self_test.assertTrue(download)
                    log["downloads"] += 1
                    # Mimic a video-only WebM source saved by the cutter template.
                    target = Path(self.opts["outtmpl"].replace("%(ext)s", "webm"))
                    target.write_bytes(b"video-only webm")
                    return {"id": "X8SR49-YI_M"}

            self_test = self

            def fake_ffmpeg(cmd, **kwargs):
                if cmd[0] == "ffprobe":
                    self.assertTrue(str(cmd[-1]).endswith(".webm"))
                    self.assertIn(".snapshot_cache", str(cmd[-1]))
                    return SimpleNamespace(stdout="4.0", returncode=0)
                Path(cmd[-1]).write_bytes(b"jpeg frame")
                return SimpleNamespace(returncode=0)

            with (
                patch.dict(sys.modules, {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYoutubeDL)}),
                patch("smart_media_manager.youtube_downloader.ffmpeg_paths",
                      return_value=("ffmpeg", "ffprobe")),
                patch("smart_media_manager.youtube_downloader.subprocess.run",
                      side_effect=fake_ffmpeg),
            ):
                for _ in range(2):
                    count = snapshot_video(self.config(root), threading.Event(),
                                           threading.Event(), lambda *args: None)
                    self.assertEqual(count, 2)
            self.assertEqual(log["downloads"], 1)
            self.assertEqual(len(log["formats"]), 1)
            self.assertIn("bv*[ext=mp4]+ba[ext=m4a]", log["formats"][0])
            self.assertIn("/bv*", log["formats"][0])
            self.assertEqual(len(list(root.glob("snapshot_*.jpg"))), 2)

    def test_no_accessible_video_format_reports_actionable_message(self):
        with tempfile.TemporaryDirectory() as td:
            class NoFormats:
                def __init__(self, opts):
                    pass

                def __enter__(self):
                    return self

                def __exit__(self, *_):
                    return False

                def extract_info(self, url, download):
                    raise RuntimeError("Requested format is not available")

            with (
                patch.dict(sys.modules, {"yt_dlp": SimpleNamespace(YoutubeDL=NoFormats)}),
                patch("smart_media_manager.youtube_downloader.ffmpeg_paths",
                      return_value=("ffmpeg", "ffprobe")),
            ):
                with self.assertRaisesRegex(RuntimeError, "Choose Video from PC"):
                    snapshot_video(self.config(Path(td)), threading.Event(),
                                   threading.Event(), lambda *args: None)

    def test_cancel_before_download_does_not_start_network(self):
        with tempfile.TemporaryDirectory() as td:
            cancel = threading.Event()
            cancel.set()
            with (
                patch("smart_media_manager.youtube_downloader.ffmpeg_paths",
                      return_value=("ffmpeg", "ffprobe")),
                patch("smart_media_manager.cutter_queue.download_source") as downloader,
            ):
                count = snapshot_video(self.config(Path(td)), cancel,
                                       threading.Event(), lambda *args: None)
                self.assertEqual(count, 0)
                downloader.assert_not_called()



class SnapshotQueueTests(unittest.TestCase):
    def config(self, root, source, name="Naomi Osaka"):
        return {
            "local_video": str(source), "url": "", "name": name,
            "output": str(root / "out"), "interval": "2",
            "format": "JPG", "quality": "90", "resolution": "Original",
            "start": "", "end": "",
        }

    def test_named_jobs_keep_own_settings_and_separate_folders(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "original.mp4"
            source.write_bytes(b"source")
            first = new_snapshot_job(self.config(root, source))
            other_cfg = self.config(root, source)
            other_cfg["interval"] = "3"
            second = new_snapshot_job(other_cfg)
            self.assertNotEqual(first["id"], second["id"])
            self.assertEqual(first["name"], "Naomi Osaka")
            self.assertEqual(first["interval"], "2")
            self.assertEqual(second["interval"], "3")

            def fake_ffmpeg(cmd, **kwargs):
                if "ffprobe" in cmd[0]:
                    return SimpleNamespace(stdout="4.0", returncode=0)
                Path(cmd[-1]).write_bytes(b"jpg")
                return SimpleNamespace(returncode=0)

            with patch("smart_media_manager.youtube_downloader.ffmpeg_paths",
                       return_value=("ffmpeg", "ffprobe")), \\
                 patch("smart_media_manager.youtube_downloader.subprocess.run",
                       side_effect=fake_ffmpeg):
                self.assertEqual(snapshot_video(first, threading.Event(),
                                                 threading.Event(), lambda *a: None), 2)
                self.assertEqual(snapshot_video(second, threading.Event(),
                                                 threading.Event(), lambda *a: None), 2)
            folders = list((root / "out").glob("Naomi Osaka [*"))
            self.assertEqual(len(folders), 2)
            images = sorted((root / "out").rglob("*.jpg"))
            self.assertEqual(len(images), 4)
            self.assertTrue(all(p.name.startswith("Naomi Osaka ") for p in images))
            self.assertEqual(len({p.parent for p in images}), 2)
            self.assertTrue(source.exists())

    def test_invalid_options_or_bad_source_rejected_before_queue(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "sample.mp4"
            source.write_bytes(b"video")
            bad = self.config(root, source)
            bad["interval"] = "0"
            with self.assertRaises(ValueError):
                new_snapshot_job(bad)
            bad = self.config(root, source)
            bad["end"] = "00:00:01"
            bad["start"] = "00:00:02"
            with self.assertRaises(ValueError):
                new_snapshot_job(bad)
            bad = self.config(root, source)
            bad["resolution"] = "16k"
            with self.assertRaises(ValueError):
                new_snapshot_job(bad)
            bad = self.config(root, root / "missing.mp4")
            with self.assertRaises(ValueError):
                new_snapshot_job(bad)

    def test_restart_recovers_active_job_and_preserves_completed(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            source = root / "sample.mp4"
            source.write_bytes(b"video")
            active = new_snapshot_job(self.config(root, source))
            complete = new_snapshot_job(self.config(root, source))
            active["status"] = "Extracting"
            complete["status"] = "Completed"
            file = root / "snapshot_queue.json"
            file.write_text(json.dumps([active, complete]), encoding="utf-8")
            ui = object.__new__(YoutubeTab)
            ui.snapshot_queue_file = file
            restored = ui._read_snapshot_queue()
            self.assertEqual([j["status"] for j in restored], ["Queued", "Completed"])

    def test_worker_sequential_and_live_additions(self):
        root = Path("/tmp")
        first = {
            "id": "a1", "name": "First", "status": "Queued", "output": str(root),
        }
        second = {
            "id": "b2", "name": "Second", "status": "Queued", "output": str(root),
        }
        ui = object.__new__(YoutubeTab)
        ui.snap_work_items = queue.Queue()
        ui.snap_work_items.put(first)
        ui.snap_cancel = threading.Event()
        ui.snap_pause = threading.Event()
        ui.snap_stop_queue = threading.Event()
        ui.events = queue.Queue()
        first_started = threading.Event()
        release_first = threading.Event()
        seen = []

        def fake_snapshot(config, cancel, pause, notify):
            seen.append(config["id"])
            if config["id"] == "a1":
                first_started.set()
                self.assertTrue(release_first.wait(3))
            notify("frame", 1, 1)
            return 1

        try:
            with patch("smart_media_manager.youtube_downloader.snapshot_video",
                       side_effect=fake_snapshot):
                worker = threading.Thread(target=ui._snapshot_worker, daemon=True)
                worker.start()
                self.assertTrue(first_started.wait(2))
                ui.snap_work_items.put(second)
                release_first.set()
                worker.join(4)
                self.assertFalse(worker.is_alive())
        finally:
            release_first.set()
        self.assertEqual(seen, ["a1", "b2"])
        events = list(ui.events.queue)
        self.assertEqual([e[1] for e in events if e[0] == "snap_done"],
                         ["a1", "b2"])
        self.assertEqual(events[-1][0], "snap_finished")

    def test_stop_queue_keeps_next_jobs_unprocessed(self):
        ui = object.__new__(YoutubeTab)
        ui.snap_work_items = queue.Queue()
        ui.snap_work_items.put({"id": "a"})
        ui.snap_work_items.put({"id": "b"})
        ui.snap_cancel = threading.Event()
        ui.snap_pause = threading.Event()
        ui.snap_stop_queue = threading.Event()
        ui.events = queue.Queue()

        def fake_snapshot(job, cancel, pause, notify):
            ui.snap_stop_queue.set()
            ui.snap_cancel.set()
            return 0

        with patch("smart_media_manager.youtube_downloader.snapshot_video",
                   side_effect=fake_snapshot) as run:
            ui._snapshot_worker()
        self.assertEqual(run.call_count, 1)
        self.assertEqual(list(ui.events.queue)[-1], ("snap_finished", 0, True))

    def test_add_while_active_freezes_name_and_snapshot_settings(self):
        class FakeVar:
            def __init__(self, value):
                self.value = value
            def get(self):
                return self.value
            def set(self, value):
                self.value = value

        class FakeLinks:
            def __init__(self, value):
                self.value = value
            def get(self, *_):
                return self.value
            def delete(self, *_):
                self.value = ""

        with tempfile.TemporaryDirectory() as td:
            ui = object.__new__(YoutubeTab)
            ui.snapshot_local = FakeVar("")
            ui.snapshot_links = FakeLinks(
                "https://www.youtube.com/watch?v=aaaa\n"
                "https://www.youtube.com/watch?v=bbbb")
            ui.snapshot_name = FakeVar("Naomi Osaka")
            ui.snapshot_output = FakeVar(td)
            ui.interval = FakeVar("5")
            ui.snap_format = FakeVar("JPG")
            ui.snap_quality = FakeVar("90")
            ui.resolution = FakeVar("Original")
            ui.start_time = FakeVar("")
            ui.end_time = FakeVar("")
            ui.snap_status = FakeVar("")
            ui.snapshot_jobs = []
            ui.snap_running = True
            ui.snap_stop_queue = threading.Event()
            ui.snap_work_items = queue.Queue()
            ui.prefs = SimpleNamespace(set=lambda *args: None)
            ui._save_snapshot_queue = lambda: None
            ui._refresh_snapshot_queue = lambda: None
            ui._queue_snapshots()
            self.assertEqual(len(ui.snapshot_jobs), 2)
            self.assertEqual([job["name"] for job in ui.snapshot_jobs],
                             ["Naomi Osaka 1", "Naomi Osaka 2"])
            self.assertEqual([job["interval"] for job in ui.snapshot_jobs], ["5", "5"])
            self.assertEqual(ui.snap_work_items.qsize(), 2)
            ui.interval.set("10")
            ui.snapshot_links.value = "https://www.youtube.com/watch?v=cccc"
            ui._queue_snapshots()
            self.assertEqual([job["interval"] for job in ui.snapshot_jobs],
                             ["5", "5", "10"])
            self.assertEqual(ui.snap_work_items.qsize(), 3)



if __name__ == "__main__":
    unittest.main()
