"""Synthetic safety tests: no CapCut session required."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from capcut_native_render_queue import core


def box(tag, content):
    return (len(content) + 8).to_bytes(4, "big") + tag + content


class NativeQueueTests(unittest.TestCase):
    def test_ref_cannot_be_guessed(self):
        with self.assertRaises(core.NativeUnavailable):
            core.native_projects('{"projects":[{"name":"Project","id":"random"}]}')
        native = core.native_projects(json.dumps({"data": {"projects": [
            {"name": "Project", "ref": "local://draft-123"}]}}))
        self.assertEqual(native[0]["ref"], "local://draft-123")

    def test_duplicate_names_do_not_bind(self):
        disk = [
            {"key": "a", "title": "Same", "folder": "a", "updated": 1, "ref": None, "status": "Unbound"},
            {"key": "b", "title": "Same", "folder": "b", "updated": 2, "ref": None, "status": "Unbound"},
        ]
        rows = core.bind_projects(disk, [{"ref":"local://one", "title":"Same"}])
        self.assertEqual(rows[0]["status"], "Needs native match")
        self.assertEqual(rows[1]["status"], "Needs native match")
        self.assertEqual(rows[2]["status"], "Queued")

    def test_local_draft_read_only(self):
        with tempfile.TemporaryDirectory() as d:
            project = Path(d) / "DraftA"
            project.mkdir()
            f = project / "draft_content.json"
            f.write_text("{}", encoding="utf-8")
            rows = core.scan_drafts([Path(d)])
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["title"], "DraftA")
            self.assertIsNone(rows[0]["ref"])
            self.assertEqual(f.read_text(), "{}")

    def test_unique_filename(self):
        self.assertEqual(core.safe_filename("A:B", "local://one").split("--")[0], "A_B")
        self.assertNotEqual(core.safe_filename("A:B", "local://one"),
                            core.safe_filename("A:B", "local://two"))

    def test_atomic_state(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "queue.json"
            core.atomic_write(p, {"items": {"draft": {"status": "Rendering"}}})
            self.assertEqual(json.loads(p.read_text())["items"]["draft"]["status"], "Rendering")

    def test_complete_mp4(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "clip.mp4"
            self.assertFalse(core.complete_mp4(p))
            p.write_bytes(box(b"ftyp", b"isom"*10) + box(b"mdat", bytes(5000)) + box(b"moov", bytes(16)))
            self.assertTrue(core.complete_mp4(p))
            with p.open("ab") as f: f.write(b"partial")
            self.assertFalse(core.complete_mp4(p))

    def test_native_app_fingerprint_guard(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / core.VERSION
            folder.mkdir()
            (folder / "CapCut.exe").write_bytes(b"fake")
            with self.assertRaises(core.NativeUnavailable):
                core.NativeIPC(folder / "CapCut.exe").validate()

    def test_bundled_bun_only_no_mouse_no_ffmpeg(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / core.VERSION
            folder.mkdir()
            adapter = core.NativeIPC(folder / "CapCut.exe")
            with patch.object(adapter, "validate", return_value=True), patch("subprocess.run") as run:
                run.return_value.returncode = 0
                run.return_value.stdout = "[]"
                adapter.command(["draft","project","list"])
            argv = run.call_args.args[0]
            self.assertTrue(str(argv[0]).endswith("bun.exe"))
            self.assertTrue(str(argv[1]).endswith("lyraCliIpcClient.mjs"))
            self.assertIn("--socket-timeout-seconds", argv)
            self.assertFalse(run.call_args.kwargs["shell"])
            self.assertNotIn("ffmpeg", " ".join(argv).lower())

    def test_export_ref_and_overwrite_guard(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / core.VERSION
            folder.mkdir()
            adapter = core.NativeIPC(folder/"CapCut.exe")
            target = Path(d)/"finished.mp4"
            target.write_bytes(b"existing")
            with self.assertRaises(core.NativeUnavailable):
                adapter.render("local://test",target)
            with self.assertRaises(core.NativeUnavailable):
                adapter.render("not-a-ref", Path(d)/"new.mp4")


if __name__ == "__main__":
    unittest.main()
