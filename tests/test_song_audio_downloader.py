"""Offline regression coverage of matching filenames and original yt-dlp pipeline."""
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch, MagicMock
from song_audio_downloader.core import (
    video_id_from_url, canonical_url, planned_paths, valid_jpeg, download_video,
)
ID = "sQ74S7cZ3Kg"


class Tests(unittest.TestCase):
    def test_video_id_forms(self):
        for link in (f"https://youtu.be/{ID}", f"https://youtube.com/watch?v={ID}&t=1",
                     f"https://youtube.com/shorts/{ID}", f"https://youtube.com/live/{ID}"):
            self.assertEqual(video_id_from_url(link), ID)
            self.assertEqual(canonical_url(link), f"https://www.youtube.com/watch?v={ID}")

    def test_invalid(self):
        for url in (f"https://youtube.com.evil.org/watch?v={ID}", "file:///etc/passwd",
                    "https://youtu.be/short", f"https://youtu.be/{ID}/extra",
                    "https://www.youtube.com/playlist?list=abc"):
            with self.subTest(url=url), self.assertRaises(ValueError):
                video_id_from_url(url)

    def test_paired_names(self):
        item = {"url": f"https://youtu.be/{ID}", "output": "Downloads",
                "mode": "Audio Only", "audio_format": "MP3", "download_thumbnail": True}
        _, audio, thumbnail = planned_paths(item)
        self.assertEqual(audio.name, ID + ".mp3")
        self.assertEqual(thumbnail.name, ID + ".jpg")
        item["audio_format"] = "WAV"
        self.assertEqual(planned_paths(item)[1].name, ID + ".wav")
        item["download_thumbnail"] = False
        self.assertIsNone(planned_paths(item)[2])

    def test_jpeg_signature(self):
        with tempfile.TemporaryDirectory() as temp:
            p = Path(temp) / "x.jpg"
            self.assertFalse(valid_jpeg(p))
            p.write_bytes(b"bad" * 100)
            self.assertFalse(valid_jpeg(p))
            p.write_bytes(b"\xff\xd8\xff" + b"\0" * 200)
            self.assertTrue(valid_jpeg(p))

    def test_yt_dlp_options_and_idempotence(self):
        with tempfile.TemporaryDirectory() as temp:
            item = {"url": f"https://youtu.be/{ID}", "output": temp, "mode": "Audio Only",
                    "audio_format": "MP3", "quality": "Best", "download_thumbnail": True}
            options = []
            class MockDL:
                def __init__(self, opts): options.append(opts)
                def __enter__(self): return self
                def __exit__(self, *args): return False
                def extract_info(self, url, download):
                    Path(temp, ID + ".mp3").write_bytes(b"audio")
                    Path(temp, ID + ".jpg").write_bytes(b"\xff\xd8\xff" + b"x" * 200)
                    return {"id": ID}
            with patch("song_audio_downloader.core.ffmpeg_paths",
                       return_value=("C:/ffmpeg/bin/ffmpeg.exe", "C:/ffmpeg/bin/ffprobe.exe")), \
                 patch.dict("sys.modules", {"yt_dlp": MagicMock(YoutubeDL=MockDL)}):
                progress = []
                download_video(item, threading.Event(), progress.append)
                download_video(item, threading.Event(), progress.append)
            self.assertEqual(len(options), 1)
            self.assertEqual(options[0]["outtmpl"], str(Path(temp) / "%(id)s.%(ext)s"))
            self.assertTrue(options[0]["writethumbnail"])
            self.assertEqual(options[0]["postprocessors"][0]["key"], "FFmpegExtractAudio")
            self.assertEqual(options[0]["postprocessors"][1]["key"], "FFmpegThumbnailsConvertor")
            self.assertEqual(progress[-1], 100)


if __name__ == "__main__":
    unittest.main()
