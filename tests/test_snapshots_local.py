"""Headless snapshot regression tests; no real YouTube network calls."""
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from smart_media_manager.youtube_downloader import SNAPSHOT_VIDEO_FORMAT, snapshot_video


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

    def test_video_only_webm_supported_and_cached_without_audio(self):
        """No muxed video+audio format is required to extract frames."""
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
                    if self.opts["format"] == "best[ext=mp4]/best":
                        raise RuntimeError("Requested format is not available")
                    if download:
                        log["downloads"] += 1
                        cache = root / ".snapshot_cache"
                        (cache / "X8SR49-YI_M.webm").write_bytes(b"video-only webm")
                    return {"id": "X8SR49-YI_M"}

            def fake_ffmpeg(cmd, **kwargs):
                if cmd[0] == "ffprobe":
                    self.assertTrue(str(cmd[-1]).endswith(".webm"))
                    return SimpleNamespace(stdout="4.0", returncode=0)
                Path(cmd[-1]).write_bytes(b"jpeg frame")
                return SimpleNamespace(returncode=0)

            with patch.dict(sys.modules, {"yt_dlp": SimpleNamespace(YoutubeDL=FakeYoutubeDL)}), \
                 patch("smart_media_manager.youtube_downloader.ffmpeg_paths",
                       return_value=("ffmpeg", "ffprobe")), \
                 patch("smart_media_manager.youtube_downloader.subprocess.run",
                       side_effect=fake_ffmpeg):
                for _ in range(2):
                    count = snapshot_video(self.config(root), threading.Event(),
                                           threading.Event(), lambda *args: None)
                    self.assertEqual(count, 2)
            self.assertEqual(log["downloads"], 1)
            self.assertEqual(log["formats"], [SNAPSHOT_VIDEO_FORMAT] * 2)
            self.assertIn("bv*", SNAPSHOT_VIDEO_FORMAT)
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

            with patch.dict(sys.modules, {"yt_dlp": SimpleNamespace(YoutubeDL=NoFormats)}), \
                 patch("smart_media_manager.youtube_downloader.ffmpeg_paths",
                       return_value=("ffmpeg", "ffprobe")):
                with self.assertRaisesRegex(RuntimeError, "Choose Video from PC"):
                    snapshot_video(self.config(Path(td)), threading.Event(),
                                   threading.Event(), lambda *args: None)


if __name__ == "__main__":
    unittest.main()
