"""All tests use synthetic fixtures, never launch the video editor."""
import hashlib
from pathlib import Path
import tempfile
import unittest
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from capcut_home_native_probe import probe


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


if __name__ == "__main__":
    unittest.main()
