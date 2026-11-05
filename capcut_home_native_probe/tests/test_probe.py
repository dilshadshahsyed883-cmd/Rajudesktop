"""All tests use synthetic fixtures, never launch the video editor."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import sys
import json
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from capcut_home_native_probe import probe, gui


class ProbeTests(unittest.TestCase):
    def test_chunk_boundary_and_digest(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / "bin"
            f.write_bytes(b"01234" + b"NATIVE_MARKER" + b"XYZ")
            result = probe.inspect_binary(f, {"test": b"NATIVE_MARKER"}, chunk_size=7)
            self.assertTrue(result["markers"]["test"])
            self.assertEqual(result["sha256"], hashlib.sha256(f.read_bytes()).hexdigest())

    def test_real_hash_cannot_be_overridden_from_cli(self):
        with tempfile.TemporaryDirectory() as tmp:
            for name, markers in probe.MARKERS.items():
                (Path(tmp) / name).write_bytes(b"|".join(markers.values()))
            result = probe.audit(Path(tmp))
            self.assertEqual(result["status"], "UNVERIFIED_OR_INCOMPLETE")
            self.assertTrue(all(not x["verified_exact_archive"] for x in result["modules"].values()))

    def test_symbol_requirements_and_missing_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            expected = {}
            for name, markers in probe.MARKERS.items():
                data = b"|".join(markers.values())
                (root / name).write_bytes(data)
                expected[name] = hashlib.sha256(data).hexdigest()
            result = probe.audit(root, expected)
            self.assertEqual(result["status"], "NATIVE_HOME_EXPORT_SYMBOLS_FOUND")
            self.assertFalse(result["capcut_home_checkbox_patch_implemented"])
            self.assertFalse(result["callable_abi_verified"])
            self.assertFalse(result["live_mp4_export_verified"])
            (root / "VECreator.dll").unlink()
            self.assertEqual(probe.audit(root, expected)["status"], "UNVERIFIED_OR_INCOMPLETE")

    def test_probe_never_changes_installation(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name in probe.MARKERS:
                (root / name).write_bytes(b"fixture")
            initial = {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()}
            probe.audit(root)
            self.assertEqual(initial, {p.name: (p.read_bytes(), p.stat().st_mtime_ns) for p in root.iterdir()})

    def test_self_check(self):
        self.assertEqual(probe.self_check()["self_check"], "PASS")

    def test_windowed_cli_self_check_without_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            dest = Path(tmp) / "result.json"
            with patch.object(sys, "stdout", None):
                code = gui.main(["--self-check", "--json", str(dest)])
            self.assertEqual(code, 0)
            state = json.loads(dest.read_text(encoding="utf-8"))
            self.assertEqual(state["self_check"], "PASS")
            self.assertFalse(state["native_patch_available"])

    def test_gui_reports_missing_folder_without_claiming_export(self):
        with tempfile.TemporaryDirectory() as tmp:
            result = probe.audit(Path(tmp))
            self.assertIn("missing", gui.readable_state(result).lower())
            report = gui.summary_lines(result)
            self.assertIn("Native export working: NOT VERIFIED", report)
            self.assertIn("Your CapCut files were not changed.", report)

    def test_report_cannot_be_saved_inside_capcut_install(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "9.7.0.4153"
            root.mkdir()
            self.assertFalse(gui.valid_report_target(root / "report.json", root))
            self.assertFalse(gui.valid_report_target(root / "nested" / "report.json", root))
            self.assertTrue(gui.valid_report_target(Path(tmp) / "report.json", root))


if __name__ == "__main__":
    unittest.main()
