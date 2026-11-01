import hashlib
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from zipfile import ZipFile
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from verify_capcut_960 import rebuild, inventory

class CapCutArchiveTests(unittest.TestCase):
    def setUp(self):
        self.tmp = TemporaryDirectory()
        self.base = Path(self.tmp.name)
        self.parts = self.base / "parts"
        self.parts.mkdir()
        self.out = self.base / "outputs"
        self.out.mkdir()
        self.orig = self.base / "original.zip"
        with ZipFile(self.orig, "w") as z:
            z.writestr("test/readme.txt", "Archive verification works")
        raw = self.orig.read_bytes()
        entries = []
        for i, off in enumerate(range(0, len(raw), 24)):
            chunk = raw[off:off + 24]
            name = f"piece{i:03d}"
            (self.parts / name).write_bytes(chunk)
            entries.append({"name": name, "bytes": len(chunk),
                            "sha256": hashlib.sha256(chunk).hexdigest()})
        self.manifest = {"parts": entries, "source_bytes": len(raw),
                         "source_sha256": hashlib.sha256(raw).hexdigest()}

    def tearDown(self):
        self.tmp.cleanup()

    def test_integrity_inventory(self):
        target = self.out / "joined.zip"
        self.assertEqual(rebuild(self.parts, self.manifest, target), self.manifest["source_sha256"])
        self.assertEqual(target.read_bytes(), self.orig.read_bytes())
        stats = inventory(target, self.out / "index.csv")
        self.assertEqual(stats["files"], 1)

    def test_wrong_hash_rejects_output(self):
        self.manifest["parts"][0]["sha256"] = "0" * 64
        target = self.out / "joined.zip"
        with self.assertRaises(ValueError):
            rebuild(self.parts, self.manifest, target)
        self.assertFalse(target.exists())
        self.assertFalse((self.out / "joined.zip.partial").exists())

    def test_no_overwrite(self):
        target = self.out / "joined.zip"
        target.write_text("owner-file")
        with self.assertRaises(ValueError):
            rebuild(self.parts, self.manifest, target)
        self.assertEqual(target.read_text(), "owner-file")

    def test_no_inventory_overwrite(self):
        target = self.out / "joined.zip"
        rebuild(self.parts, self.manifest, target)
        inv = self.out / "index.csv"
        inv.write_text("keep")
        with self.assertRaises(ValueError):
            inventory(target, inv)
        self.assertEqual(inv.read_text(), "keep")

if __name__ == "__main__":
    unittest.main()
