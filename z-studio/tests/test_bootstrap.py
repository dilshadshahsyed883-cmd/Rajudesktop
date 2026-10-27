"""Offline tests: never download software or modify the host PATH."""
import importlib.util
import io
from pathlib import Path
from unittest import TestCase, mock
from zipfile import ZipFile
import tempfile

PATH = Path(__file__).resolve().parents[1] / "launcher" / "bootstrap_node.py"
spec = importlib.util.spec_from_file_location("zstudio_bootstrap", PATH)
bootstrap = importlib.util.module_from_spec(spec)
spec.loader.exec_module(bootstrap)


class BootstrapTests(TestCase):
    def test_official_sha_lookup(self):
        filename = "node-v24.21.0-win-x64.zip"
        digest = "a" * 64
        text = (digest + "  " + filename + "\n").encode()
        self.assertEqual(bootstrap.sha_from_official_file(text, filename), digest)
        with self.assertRaises(ValueError):
            bootstrap.sha_from_official_file(text, "different.zip")

    def test_lts_select(self):
        data = b'''[
          {"version":"v24.22.1","lts":"Krypton","files":["win-x64-zip"]},
          {"version":"v24.21.0","lts":"Krypton","files":["win-x64-zip"]}
        ]'''
        with mock.patch.object(bootstrap, "get_bytes", return_value=data):
            self.assertEqual(bootstrap.node_release("x64"), "v24.22.1")

    def test_metadata_fallback(self):
        with mock.patch.object(bootstrap, "get_bytes", side_effect=OSError("offline")):
            self.assertEqual(bootstrap.node_release("x64"), "v24.21.0")

    def test_architectures(self):
        with mock.patch.object(bootstrap.platform, "machine", return_value="AMD64"):
            self.assertEqual(bootstrap.win_arch(), "x64")
        with mock.patch.object(bootstrap.platform, "machine", return_value="ARM64"):
            self.assertEqual(bootstrap.win_arch(), "arm64")

    def test_archive_traversal_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.zip"
            with ZipFile(p, "w") as z:
                z.writestr("node-v24-win-x64/../../evil.txt", "bad")
            with self.assertRaises(ValueError):
                bootstrap.validated_extract(p, Path(tmp), "node-v24-win-x64")

    def test_archive_valid(self):
        with tempfile.TemporaryDirectory() as tmp:
            p = Path(tmp) / "test.zip"
            with ZipFile(p, "w") as z:
                z.writestr("node-v24-win-x64/node.exe", "fake")
            bootstrap.validated_extract(p, Path(tmp), "node-v24-win-x64")
            self.assertTrue((Path(tmp) / "node-v24-win-x64/node.exe").is_file())


if __name__ == '__main__':
    import unittest
    unittest.main()
