"""Headless smoke checks for fourth native media tab."""
import unittest
from smart_media_manager.youtube_downloader import valid_url, timestamp, selector, ffmpeg_paths

class DownloaderTests(unittest.TestCase):
    def test_url_scope(self):
        self.assertTrue(valid_url("https://www.youtube.com/watch?v=abc"))
        self.assertTrue(valid_url("https://youtu.be/abc"))
        self.assertFalse(valid_url("https://youtube.com.evil.org/watch?v=abc"))
        self.assertFalse(valid_url("file:///etc/passwd"))

    def test_timestamps(self):
        self.assertEqual(timestamp("01:02:03"), 3723)
        self.assertEqual(timestamp("5:03"), 303)
        self.assertEqual(timestamp(""), 0)
        with self.assertRaises(ValueError):
            timestamp("bad")

    def test_modes(self):
        self.assertIn("height<=720", selector("Full Video", "720p"))
        self.assertIn("bestvideo", selector("Video Only", "Best"))
        self.assertIn("bestaudio", selector("Audio Only", "1080p"))

if __name__ == "__main__":
    unittest.main()
