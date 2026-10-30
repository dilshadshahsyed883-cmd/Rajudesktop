"""Offline coverage: no real OAuth, YouTube uploads, or VPS changes."""
from __future__ import annotations
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from short_studio.core import RenderOptions, Store, file_hash, motion_filter, safe_folder
from short_studio import uploader


class ShortStudioTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.store = Store(Path(self.tmp.name))

    def test_persistent_folders_and_sequence(self):
        self.store.create_folder("Aina Asif")
        first = self.store.reserve_names("Aina Asif", 2)
        more = Store(Path(self.tmp.name)).reserve_names("Aina Asif", 1)
        self.assertRegex(first[0].name, r"Aina Asif 001_[a-f0-9]{6}\.mp4")
        self.assertRegex(first[1].name, r"Aina Asif 002_[a-f0-9]{6}\.mp4")
        self.assertRegex(more[0].name, r"Aina Asif 003_[a-f0-9]{6}\.mp4")
        self.assertNotEqual(first[0].stem[-6:], more[0].stem[-6:])
        self.assertEqual(self.store.folders(), ["Aina Asif", "Default"])

    def test_folder_guards(self):
        for name in ("../escape", "bad/name", "", ".hidden"):
            with self.assertRaises(ValueError):
                safe_folder(name)
        with self.assertRaises(ValueError):
            self.store.delete_empty_folder("Default")
        self.store.create_folder("Unused")
        (self.store.folder_path("Unused") / "existing.mp4").write_bytes(b"test")
        with self.assertRaises(OSError):
            self.store.delete_empty_folder("Unused")
        self.assertIn("Unused", self.store.folders())

    def test_settings_validation_and_motion(self):
        self.assertIsNone(RenderOptions().validate())
        with self.assertRaises(ValueError):
            RenderOptions(count=1000).validate()
        with self.assertRaises(ValueError):
            RenderOptions(video_seconds=0).validate()
        for m in ("none", "zoom_in", "zoom_out", "pan_lr", "pan_rl"):
            self.assertIn("fps=30", motion_filter(m, 30, 30))

    def test_group_profile_and_duplicate_upload_queue(self):
        self.store.create_folder("Shorts")
        folder = self.store.folder_path("Shorts")
        (folder / "Shorts 001_aabbcc.mp4").write_bytes(b"mock-a")
        (folder / "Shorts 002_aabbcc.mp4").write_bytes(b"mock-b")
        with self.store.db() as c:
            c.execute("INSERT INTO channels(id,label,token_file) VALUES('ch1','Channel One','unused')")
            c.execute("INSERT INTO channels(id,label,token_file) VALUES('ch2','Channel Two','unused')")
        group = uploader.create_group(self.store, "Gaming", ["ch1", "ch2"])
        p = uploader.create_profile(self.store, "Gaming Group", group, "Shorts",
                                    "{filename}", "Manual description", privacy="public",
                                    schedule_pkt="18:00")
        self.assertEqual(uploader.enqueue_profile(self.store, p), 4)
        self.assertEqual(uploader.enqueue_profile(self.store, p), 0)
        self.assertEqual(len(uploader.upload_rows(self.store)), 4)
        # Content hash, not filename or profile, enforces per-channel once-only.
        (folder / "Shorts 003_aabbcc.mp4").write_bytes(b"mock-a")
        self.assertEqual(uploader.enqueue_profile(self.store, p), 0)
        slot = uploader.find_publish_slot(self.store, uploader.profiles(self.store)[0], "ch1",
                                          datetime(2026, 10, 30, 17, 0, tzinfo=timezone.utc))
        self.assertGreater(slot, datetime(2026, 10, 30, 17, 0, tzinfo=timezone.utc))

    def test_upload_resume_becomes_uncertain_without_network(self):
        self.store.create_folder("Videos")
        target = self.store.folder_path("Videos") / "Videos 001_aabbcc.mp4"
        target.write_bytes(b"video")
        with self.store.db() as c:
            c.execute("INSERT INTO channels(id,label,token_file) VALUES('ch1','One','missing')")
        group = uploader.create_group(self.store, "One", ["ch1"])
        profile = uploader.create_profile(self.store, "Profile", group, "Videos", "", "")
        uploader.enqueue_profile(self.store, profile)
        with self.store.db() as c:
            c.execute("UPDATE uploads SET state='uploading'")
        self.assertEqual(uploader.upload_pending(self.store), 0)
        self.assertEqual(uploader.upload_rows(self.store)[0]["state"], "uncertain")
        self.assertTrue(target.is_file())


if __name__ == "__main__":
    unittest.main()
