"""Shared-folder publication, real media and queue lifecycle regressions."""
import json
import os
import queue
import shutil
import subprocess
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from smart_media_manager.clip_output import publish_clip, validate_output, default_output_folder, available_clip_name
from smart_media_manager.cutter_queue import cut_source, job_output, new_job, safe_name
from smart_media_manager.cutter_queue_ui import BatchCutterTab
from smart_media_manager.app import Preferences
from video_clip_cutter.core import Cancelled


class SharedOutputTests(unittest.TestCase):
    def test_saved_folder_survives_restart(self):
        with tempfile.TemporaryDirectory() as td:
            file = Path(td) / "settings.json"
            folder = str(Path(td) / "User selected clips")
            Preferences(file).set("cutter_output", folder)
            self.assertEqual(Preferences(file).get("cutter_output", str(default_output_folder())), folder)

    def test_redirected_windows_desktop_default(self):
        registry = Mock()
        registry.OpenKey.return_value.__enter__ = Mock(return_value="key")
        registry.OpenKey.return_value.__exit__ = Mock(return_value=False)
        registry.QueryValueEx.return_value = ("/redirected/Desktop", 2)
        with patch.dict("sys.modules", {"winreg": registry}), \
             patch("smart_media_manager.clip_output.os", SimpleNamespace(name="nt", path=os.path)):
            self.assertEqual(default_output_folder(), Path("/redirected/Desktop/Alexa Media/clips"))

    def test_names_and_concurrent_publication_preserve_existing_files(self):
        with tempfile.TemporaryDirectory() as td:
            folder = validate_output(Path(td) / "clips")
            old = folder / "ALEX 3.MP4"
            old.write_bytes(b"historic")
            clip = Path(td) / "Alex 3.mp4"
            clip.write_bytes(b"finished-video")
            with patch("smart_media_manager.clip_output.video_duration", return_value=Decimal(4)):
                with ThreadPoolExecutor(max_workers=6) as executor:
                    results = list(executor.map(
                        lambda _: publish_clip(clip, folder, Decimal(4)), range(12)))
            self.assertEqual(len(set(results)), 12)
            self.assertEqual({p.name for p in results}, {f"Alex {n}.mp4" for n in range(4, 16)})
            self.assertEqual(old.read_bytes(), b"historic")
            self.assertTrue(all(p.read_bytes() == b"finished-video" for p in results))
            self.assertEqual(len(list(folder.iterdir())), 13)
            self.assertFalse(list(Path(td).glob(".smart-media-publish-*")))

    def test_exact_filename_first_and_only_trailing_number_changes(self):
        cases = [
            ("Alex_007.mp4", {"Alex_077.mp4"}, "Alex_007.mp4"),
            ("Alex_007.mp4", {"Alex_007.mp4", "Alex_077.mp4"}, "Alex_078.mp4"),
            ("Alex 7.MP4", {"ALEX 7.mp4", "Alex 77.mp4"}, "Alex 78.MP4"),
            ("Alex-007.mp4", {"Alex-007.mp4", "Alex-999.mp4"}, "Alex-1000.mp4"),
            ("Alex_007.mp4", {"Alex_007.mp4", "Alex 999.mp4", "Alex_888.txt"}, "Alex_008.mp4"),
            ("Alex.mp4", {"Alex.mp4", "Alex 9.mp4"}, "Alex 10.mp4"),
            ("Alex.mp4", {"Alex 9.mp4"}, "Alex.mp4"),
            ("Alex007.mp4", {"alex007.MP4", "Alex077.mp4"}, "Alex078.mp4"),
            ("Café_007.mp4", {"Cafe\u0301_007.mp4", "CAFÉ_077.MP4"}, "Café_078.mp4"),
        ]
        for original, existing, expected in cases:
            with self.subTest(original=original, existing=existing):
                self.assertEqual(available_clip_name(original, existing), expected)

    @unittest.skipIf(os.name == "nt", "Exercises the POSIX exclusive-link race path")
    def test_external_writer_race_rescans_maximum_and_keeps_existing_data(self):
        with tempfile.TemporaryDirectory() as td:
            folder = validate_output(Path(td) / "clips")
            clip = Path(td) / "Alex_007.mp4"
            clip.write_bytes(b"finished-video")
            link = os.link
            calls = []
            def racing_link(source, target):
                calls.append(target.name)
                if len(calls) == 1:
                    target.write_bytes(b"other-writer")
                    (folder / "Alex_077.mp4").write_bytes(b"other-maximum")
                    raise FileExistsError(target)
                link(source, target)
            with patch("smart_media_manager.clip_output.video_duration", return_value=Decimal(4)), \
                 patch("smart_media_manager.clip_output.os.link", side_effect=racing_link):
                result = publish_clip(clip, folder, Decimal(4))
            self.assertEqual(calls, ["Alex_007.mp4", "Alex_078.mp4"])
            self.assertEqual(result.read_bytes(), b"finished-video")
            self.assertEqual((folder / "Alex_007.mp4").read_bytes(), b"other-writer")

    def test_partial_copy_never_appears_in_library(self):
        with tempfile.TemporaryDirectory() as td:
            folder = validate_output(Path(td) / "clips")
            clip = Path(td) / "clip.mp4"
            clip.write_bytes(b"finished-video")
            def broken_copy(source, target):
                Path(target).write_bytes(b"partial")
                self.assertEqual(list(folder.iterdir()), [])
                raise OSError("Disk full")
            with patch("smart_media_manager.clip_output.video_duration", return_value=Decimal(4)), \
                 patch("smart_media_manager.clip_output.shutil.copyfile", side_effect=broken_copy):
                with self.assertRaises(OSError):
                    publish_clip(clip, folder, Decimal(4))
            self.assertEqual(list(folder.iterdir()), [])
            self.assertFalse(list(Path(td).glob(".smart-media-publish-*")))

    def test_windows_names_unicode_and_output_snapshot(self):
        for raw in ('CON', 'nul.txt', 'COM¹', 'LPT³', 'A:/B?*', ' . ', '🎾' * 200):
            name = safe_name(raw)
            self.assertTrue(name)
            self.assertNotRegex(name, r'[<>:"/\\|?*]')
            self.assertFalse(name.endswith((' ', '.')))
            self.assertLessEqual(len(name.encode('utf-8')), 180)
            self.assertLessEqual(len(name.encode('utf-16-le')), 170)
        job = new_job("https://youtu.be/abc", "YouTube", "4", "first", "Alex")
        self.assertEqual(job_output(job), Path("first").resolve())
        with tempfile.TemporaryDirectory() as td:
            prefs = Preferences(Path(td) / "settings.json")
            prefs.set("cutter_output", str(Path(td) / "chosen"))
            self.assertEqual(Preferences(prefs.location).get("cutter_output"), str(Path(td) / "chosen"))
        self.assertEqual(job_output(job), Path("first").resolve())

    @unittest.skipUnless(shutil.which("ffmpeg") and shutil.which("ffprobe"), "FFmpeg required")
    def test_real_media_shared_jobs_retry_cancel_and_source_preservation(self):
        with tempfile.TemporaryDirectory() as td, patch.dict(os.environ, {"LOCALAPPDATA": td}):
            root = Path(td)
            source = root / "source.mp4"
            subprocess.run(["ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                            "testsrc2=size=160x90:rate=25", "-f", "lavfi", "-i",
                            "sine=frequency=400", "-t", "6", "-c:v", "libx264",
                            "-g", "50", "-sc_threshold", "0", "-c:a", "aac", str(source)], check=True)
            original = source.read_bytes()
            folder = root / "clips"
            first = new_job(str(source), "Local", "2", str(folder), "Alex")
            count, result = cut_source(first, source, threading.Event(), lambda *args: None)
            self.assertEqual(count, 3)
            self.assertEqual(result, folder.resolve())
            before = {p.name: p.read_bytes() for p in folder.iterdir()}
            cancel = threading.Event()
            second = new_job(str(source), "Local", "2", str(folder), "alex")
            def notify(stage, percent, detail):
                if detail.startswith("Clip "):
                    cancel.set()
            with self.assertRaises(Cancelled):
                cut_source(second, source, cancel, notify)
            self.assertGreater(len(list(folder.iterdir())), len(before))
            second["attempt"] = 1
            cut_source(second, source, threading.Event(), lambda *args: None)
            for name, data in before.items():
                self.assertEqual((folder / name).read_bytes(), data)
            for clip in folder.iterdir():
                self.assertEqual(clip.suffix, ".mp4")
                data = json.loads(subprocess.check_output(["ffprobe", "-v", "error",
                    "-show_entries", "stream=codec_type", "-of", "json", str(clip)]))
                self.assertEqual([s["codec_type"] for s in data["streams"]], ["video"])
            self.assertEqual(source.read_bytes(), original)
            self.assertEqual(list((root / "SmartMediaManager" / "cutter_staging").iterdir()), [])



class QueueLifecycleTests(unittest.TestCase):
    def tab(self):
        tab = object.__new__(BatchCutterTab)
        tab.jobs = []
        tab.running = False
        tab.cancel = threading.Event()
        tab.events = queue.Queue()
        tab.output = Mock()
        tab.status = Mock()
        tab.progress_bar = Mock()
        tab.links = Mock()
        tab.pc_button = Mock()
        tab.yt_button = Mock()
        tab._remember = Mock()
        tab._refresh = Mock()
        tab._save = Mock()
        tab.start_queue = Mock()
        return tab

    def test_persist_before_autostart_and_duplicate_filtering(self):
        tab = self.tab()
        order = []
        tab._save.side_effect = lambda: order.append("save")
        tab.start_queue.side_effect = lambda: order.append("start")
        job = new_job("https://youtu.be/abc", "YouTube", "4", "/tmp", "Alex")
        tab._finish_add([job], "YouTube", "/tmp")
        self.assertEqual(order, ["save", "start"])
        tab._finish_add([new_job("https://youtube.com/watch?v=abc", "YouTube", "4", "/tmp")], "YouTube", "/tmp")
        self.assertEqual(len(tab.jobs), 1)

    def test_failed_save_keeps_input_and_never_starts(self):
        tab = self.tab()
        tab._save.side_effect = OSError("Disk full")
        job = new_job("https://youtu.be/abc", "YouTube", "4", "/tmp")
        with patch("smart_media_manager.cutter_queue_ui.messagebox.showerror"):
            tab._finish_add([job], "YouTube", "/tmp")
        self.assertEqual(tab.jobs, [])
        tab.start_queue.assert_not_called()
        tab.links.delete.assert_not_called()

    def test_idle_shutdown_race_restarts_waiting_jobs(self):
        tab = self.tab()
        tab.running = True
        tab._set_running = lambda running: setattr(tab, "running", running)
        tab.after = Mock()
        tab.events.put(("finished", 1, 1, False))
        tab.jobs = [new_job("https://youtu.be/new", "YouTube", "4", "/tmp")]
        tab._poll()
        tab.start_queue.assert_called_once()

    def test_validation_is_off_ui_thread_and_retains_invalid_input(self):
        tab = self.tab()
        tab.adding = False
        tab.keyword = Mock(get=lambda: "Alex")
        tab.duration = Mock(get=lambda: "4")
        tab.quality = Mock(get=lambda: "720p")
        tab.output = Mock(get=lambda: "/tmp")
        started, release = threading.Event(), threading.Event()
        def slow_validation(folder):
            started.set()
            release.wait(3)
            raise OSError("Not writable")
        try:
            with patch("smart_media_manager.cutter_queue_ui.validate_output", side_effect=slow_validation):
                tab._add(["https://youtu.be/abc"], "YouTube")
                self.assertTrue(started.wait(1))
                self.assertTrue(tab.adding)
                self.assertTrue(tab.events.empty())
                tab.links.delete.assert_not_called()
                release.set()
                event = tab.events.get(timeout=3)
                self.assertEqual(event[0], "add_error")
        finally:
            release.set()


if __name__ == "__main__":
    unittest.main()
