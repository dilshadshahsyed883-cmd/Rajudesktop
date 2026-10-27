"""A complete original-source snapshot is mandatory; reduced rewrites fail."""
from __future__ import annotations

import importlib.util
from pathlib import Path
import tempfile
import unittest
from zipfile import ZipFile

MODULE = Path(__file__).resolve().parents[1] / "z_builder_full" / "assemble.py"
spec = importlib.util.spec_from_file_location("assemble_z_builder_full", MODULE)
assert spec and spec.loader
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)


class ParityTests(unittest.TestCase):
    def test_does_not_accept_partial_scene_builder(self):
        with tempfile.TemporaryDirectory() as tmp:
            origin = Path(tmp) / "upstream"
            origin.mkdir()
            with self.assertRaises(mod.IncompleteSource):
                mod._filemap(origin, Path(__file__).resolve().parents[1])

    def test_preserves_complete_original_bytes_and_media_library(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            upstream = folder / "upstream"
            for path in mod.UPSTREAM_REQUIRED:
                target = upstream / path
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_text(f"upstream-original::{path}\n", encoding="utf-8")
            extra = upstream / "part01" / "templates" / "settings.html"
            extra.write_text("existing-settings-retained", encoding="utf-8")
            hidden = upstream / "part01" / ".env"
            hidden.write_text("DO-NOT-PACKAGE", encoding="utf-8")
            output = folder / "bundle.zip"
            meta = mod.build(upstream, Path(__file__).resolve().parents[1], output, "0" * 40)
            self.assertGreaterEqual(len(meta["files"]), len(mod.UPSTREAM_REQUIRED) + len(mod.CAPCUT_REQUIRED))
            with ZipFile(output) as z:
                for path in mod.UPSTREAM_REQUIRED:
                    name = "Z-Builder/scene-builder-web/" + path
                    self.assertIn(name, z.namelist())
                    self.assertEqual(z.read(name), (upstream / path).read_bytes())
                self.assertEqual(z.read("Z-Builder/scene-builder-web/part01/templates/settings.html"), b"existing-settings-retained")
                self.assertNotIn("Z-Builder/scene-builder-web/part01/.env", z.namelist())
                self.assertIn("Z-Builder/capcut/capcut-draft.js", z.namelist())


if __name__ == "__main__":
    unittest.main()
