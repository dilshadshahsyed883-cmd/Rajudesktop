"""Offline Song Studio tests (no network, OAuth or YouTube uploads)."""
from __future__ import annotations
import tempfile
import os
from unittest.mock import patch
import unittest
from pathlib import Path

from song_studio.core import (StudioStore, ffmpeg_filter, pairs, safe_folder,
                              sha256, source_identity)


class FolderAndIdentityTests(unittest.TestCase):
    def test_folder_validation(self):
        for name in ("", "..", " a/b ", "foo\\bar", "file:other", "xyz.", "thing?"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                safe_folder(name)
        self.assertEqual(safe_folder("Dance Songs"), "Dance Songs")

    def test_matched_pairs_and_ambiguous_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            (base / "sQ74S7cZ3Kg.mp3").write_bytes(b"audio")
            (base / "sQ74S7cZ3Kg.jpg").write_bytes(b"image")
            (base / "other.m4a").write_bytes(b"audio")
            (base / "duplicate.mp3").write_bytes(b"audio")
            (base / "duplicate.wav").write_bytes(b"audio2")
            (base / "duplicate.jpg").write_bytes(b"image")
            found = pairs(base)
            self.assertEqual(len(found), 1)
            self.assertEqual(found[0]["name"], "sQ74S7cZ3Kg")
            self.assertEqual(found[0]["audio"].suffix, ".mp3")
            self.assertEqual(found[0]["image"].suffix, ".jpg")

    def test_identity_video_id_and_content(self):
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "sQ74S7cZ3Kg.mp4"
            source.write_bytes(b"a")
            self.assertEqual(source_identity(source), "videoid:sQ74S7cZ3Kg")
            source = Path(tmp) / "song one.mp4"
            source.write_bytes(b"a")
            self.assertEqual(source_identity(source), "sha256:" + sha256(source))
            self.assertEqual(len(sha256(source)), 64)

    def test_video_filters(self):
        self.assertIn("1920:1080", ffmpeg_filter("1080p", "Fit"))
        self.assertIn("1080:1920", ffmpeg_filter("9:16", "Fit"))
        self.assertIn("overlay=", ffmpeg_filter("720p", "Blur"))
        for args in [("4K", "Fit"), ("720p", "stretch")]:
            with self.assertRaises(ValueError):
                ffmpeg_filter(*args)


class DurableStoreTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.base = Path(self.temp.name)
        self.store = StudioStore(self.base / "state", self.base / "media")

    def tearDown(self):
        self.temp.cleanup()

    def test_folder_and_profile_survive_restart(self):
        self.store.folder("Music 1")
        self.store.save_profile("My songs", "My group", "Music 1",
                                "{filename}", "New track", "10", "private")
        again = StudioStore(self.base / "state", self.base / "media")
        self.assertIn("Music 1", again.folders())
        self.assertEqual(again.profiles()[0]["group_name"], "My group")
        self.assertEqual(again.profiles()[0]["privacy"], "private")
        again.save_profile("My songs", "Default", "Music 1",
                           "{filename}", "Update", "10", "unlisted")
        self.assertEqual(len(again.profiles()), 1)
        self.assertEqual(again.profiles()[0]["description"], "Update")

    def test_channel_group_selection(self):
        token = self.store.tokens / "UCtest.json"
        token.write_text("{}")
        self.store.add_channel("UCtest", "Example Channel", token)
        self.store.set_group("UCtest", "A Group")
        self.assertEqual(self.store.channels("A Group")[0]["id"], "UCtest")
        self.assertEqual(self.store.channels("Default"), [])

    def test_durable_idempotency_and_uncertain_failures(self):
        identity = "videoid:sQ74S7cZ3Kg"
        self.assertTrue(self.store.reserve("A", identity))
        self.assertFalse(self.store.reserve("A", identity))
        self.store.needs_review("A", identity, "Network timeout")
        self.assertFalse(self.store.reserve("A", identity))
        self.assertEqual(self.store.ledger()[0]["state"], "needs_review")
        self.assertTrue(self.store.reserve("B", identity))
        self.store.receipt("B", identity, "youtube_id_123", False, "Thumbnail pending")
        again = StudioStore(self.base / "state", self.base / "media")
        self.assertFalse(again.reserve("B", identity))
        rows = {r["channel_id"]: r for r in again.ledger()}
        self.assertEqual(rows["B"]["youtube_id"], "youtube_id_123")
        self.assertEqual(rows["B"]["thumbnail_done"], 0)
        self.assertEqual(rows["A"]["state"], "needs_review")


class WindowsGuiSmoke(unittest.TestCase):
    @unittest.skipUnless(os.name == "nt", "Windows desktop UI requires a display")
    def test_all_three_modules_open(self):
        from song_studio.app import SongStudio
        with tempfile.TemporaryDirectory() as root:
            temp = Path(root)
            store = StudioStore(temp / "state", temp / "media")
            with patch("song_studio.app.StudioStore", return_value=store):
                app = SongStudio()
                try:
                    for page in ("Dashboard", "Audio Downloader", "Song Maker",
                                 "Song Uploader", "Settings", "Song Uploader"):
                        with self.subTest(page=page):
                            app.show(page)
                            app.update_idletasks()
                finally:
                    app.destroy()


if __name__ == "__main__":
    unittest.main()
