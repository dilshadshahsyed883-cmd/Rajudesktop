"""Safe synthetic tests; no CapCut install, mouse action, or user draft required."""
import hashlib
import json
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from capcut_auto_export_evidence import core
from capcut_auto_export_evidence.windows import Driver, Card


def atom(name, data):
    return struct.pack(">I4s", 8 + len(data), name) + data


class EvidenceTests(unittest.TestCase):
    def test_version_and_archive_are_pinned(self):
        self.assertEqual(core.SUPPORTED_VERSION, "9.6.0.4097")
        self.assertEqual(len(core.LYRA_DLL_SHA256), 64)
        self.assertEqual(len(core.ARCHIVE_SHA256), 64)

    def test_project_name_and_dialog_identity(self):
        self.assertEqual(core.project_name(" 1028 "), "1028")
        self.assertTrue(core.export_dialog_match("Export-1028", "1028"))
        self.assertTrue(core.export_dialog_match("Export–1028", "1028"))
        self.assertFalse(core.export_dialog_match("Export-1029", "1028"))
        self.assertFalse(core.export_dialog_match("Export-1028-extra", "1028"))
        for value in ("", ".", "..", "bad/name", "bad:name", "x"*181):
            with self.assertRaises(core.Halt):
                core.project_name(value)

    def test_no_output_overwrite(self):
        with tempfile.TemporaryDirectory() as d:
            target = core.expected_video(d, "scene")
            self.assertEqual(target.name, "scene.mp4")
            target.write_text("existing")
            with self.assertRaises(core.Halt):
                core.expected_video(d, "scene")
            self.assertEqual(target.read_text(), "existing")

    def test_file_observer_valid_atom_structure(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "ok.mp4"
            p.write_bytes(atom(b"ftyp", b"isom" + bytes(100)) +
                          atom(b"mdat", bytes(5000)) + atom(b"moov", bytes(18)))
            watcher = core.Observer(p)
            self.assertFalse(watcher.poll()[0])
            self.assertFalse(watcher.poll()[0])
            self.assertFalse(watcher.poll()[0])
            self.assertTrue(watcher.poll()[0])
            with p.open("ab") as out:
                out.write(b"invalid")
            self.assertFalse(core._box_tags(p))

    def test_missing_video_and_partial_moov_rejected(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.mp4"
            self.assertFalse(core.Observer(p).poll()[0])
            p.write_bytes(atom(b"ftyp", bytes(100)) + atom(b"mdat", bytes(5000)))
            self.assertFalse(core._box_tags(p))

    def test_corrupted_and_unresolved_job_journal_blocks(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "job.json"
            self.assertFalse(core.unresolved(f))
            f.write_text("not valid json")
            self.assertTrue(core.unresolved(f))
            core.atomic_json(f, {"phase": "export_requested"})
            self.assertTrue(core.unresolved(f))
            core.atomic_json(f, {"phase": "verified"})
            self.assertFalse(core.unresolved(f))
            core.atomic_json(f, {"phase": "acknowledged"})
            self.assertFalse(core.unresolved(f))

    def test_ffprobe_validation_metadata_and_checksum(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "out.mp4"
            p.write_bytes(b"synthetic" * 600)
            obj = {"format": {"duration": "23.2"},
                   "streams": [
                       {"codec_type":"video", "codec_name":"h264", "width":1080, "height":1920},
                       {"codec_type":"audio", "codec_name":"aac"}]}
            class Proc:
                returncode=0
                stdout=json.dumps(obj)
                stderr=""
            with patch("capcut_auto_export_evidence.core.subprocess.run", return_value=Proc()), \
                 patch("capcut_auto_export_evidence.core.shutil.which", return_value="/fake/ffprobe"):
                result = core.validate_media(p, "ffprobe")
            self.assertEqual(result["width"],1080)
            self.assertEqual(result["audio_streams"],1)
            self.assertEqual(result["sha256"], hashlib.sha256(p.read_bytes()).hexdigest())

    def test_reject_bad_ffprobe_output(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "bad.mp4"
            p.write_bytes(b"file")
            class Proc:
                returncode=0
                stdout=json.dumps({"format":{"duration":"0"},"streams":[]})
                stderr=""
            with patch("capcut_auto_export_evidence.core.subprocess.run", return_value=Proc()), \
                 patch("capcut_auto_export_evidence.core.shutil.which", return_value="/fake/ffprobe"):
                with self.assertRaises(core.Halt):
                    core.validate_media(p,"ffprobe")

    def test_dll_hash_difference_fails_closed(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d) / core.SUPPORTED_VERSION
            folder.mkdir()
            exe = folder / "CapCut.exe"
            exe.write_bytes(b"dummy")
            (folder / "lyra_cli_client.dll").write_bytes(b"wrong")
            with self.assertRaises(core.Halt):
                core.installed_evidence(exe)

    def test_selfcheck_never_certifies_unattended(self):
        info = core.self_check()
        self.assertFalse(info["windows_export_tested"])
        self.assertFalse(info["unattended_batch_certified"])


if __name__ == "__main__":
    unittest.main()
