"""Headless tests for PC video snapshots; no network access or yt-dlp required."""
import tempfile
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from smart_media_manager.youtube_downloader import snapshot_video


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


if __name__ == "__main__":
    unittest.main()
