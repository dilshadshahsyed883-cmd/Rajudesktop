"""Offline regression tests for the Scene Builder Windows desktop modules."""
from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from scene_builder_desktop.desktop_catalog import DesktopCatalog
from scene_builder_desktop.director_bridge import build_rough_cut, inspect_plan
from scene_builder_desktop.director_v25 import DirectorSpecError
from scene_builder_desktop.scene_media_library import InvalidMedia


def simple_v25(filename: str = "alex.png", *, effect: str = "none", source_mode: str = "library_only") -> str:
    sections = [
        "SCENE_PLAN_VERSION=2",
        "[PROJECT]", "mode=director", "name=sample", "base_preset=standard", "validation=strict",
        "[OUTPUT]", "resolution=720p", "aspect_ratio=16:9", "fps=30", "codec=h264",
        "filename=sample.mp4",
        "[MEDIA]", f"source_mode={source_mode}", "avoid_duplicates=false", "missing_media=fail",
        "library_summary_generated=true",
        "[TIMING]", "audio=narration_upload", "narration_start=auto", "split=manual",
        "max_semantic_beat_seconds=3",
        "[CAPTIONS]", "captions_enabled=false", "caption_style=none", "caption_position=bottom",
        "[AUDIO]", "voice_volume_percent=100", "music_enabled=false",
        "[LOOK]", "lut_enabled=false", "lut_pack=none", "lut_preset=none",
        "[INTRO]", "intro_enabled=false", "intro_duration_seconds=16",
    ]
    for idx in range(1, 9):
        sections += [f"[INTRO.SHOT_{idx:02d}]", "hook_role=context", "media_type=image"]
    sections += [
        "[SCENE_001]", "narration=First scene text",
        "[SCENE_001.SHOT_01]", "media_type=image",
        f"library_filename={filename}", "library_keyword=" + Path(filename).stem,
        f"effect={effect}", "transition_out=hard_cut",
    ]
    return "\n".join(sections) + "\n"


class DesktopCatalogTests(unittest.TestCase):
    def setUp(self):
        self.root = tempfile.TemporaryDirectory()
        self.addCleanup(self.root.cleanup)
        self.work = Path(self.root.name)
        self.media = self.work / "original" / "alex.png"
        self.media.parent.mkdir()
        self.media.write_bytes(b"\x89PNG\r\n\x1a\n" + b"a" * 64)
        self.catalog = DesktopCatalog(self.work / "app-lib")

    def test_non_destructive_library_import_and_report(self):
        first = self.catalog.import_path(self.media)
        again = self.catalog.import_path(self.media)
        self.assertTrue(first["approved"])
        self.assertEqual(first["id"], again["id"])
        self.assertTrue(again["duplicate"])
        self.assertEqual(self.catalog.summary()["images"], 1)
        imported, _ = self.catalog.file(first["id"])
        self.assertNotEqual(imported, self.media)
        self.assertTrue(imported.is_file())
        self.assertIn("alex.png", self.catalog.report())
        self.catalog.clean()
        self.assertFalse(imported.exists())
        self.assertTrue(self.media.exists())

    def test_reject_forged_or_symlinked_media(self):
        forged = self.work / "bad.png"
        forged.write_bytes(b"plain-text-not-an-image")
        with self.assertRaises(InvalidMedia):
            self.catalog.import_path(forged)
        symlink = self.work / "linked.png"
        try:
            symlink.symlink_to(self.media)
        except (OSError, NotImplementedError):
            return
        with self.assertRaises(InvalidMedia):
            self.catalog.import_path(symlink)

    def test_v25_preflight_and_rough_cut_draft(self):
        self.catalog.import_path(self.media)
        report = inspect_plan(simple_v25(), self.catalog, "library_only")
        self.assertEqual(report["status"], "VALIDATED_INTENT_ONLY", report["errors"])
        self.assertTrue(report["desktop_rough_cut_ready"], report["desktop_blockers"])
        project = build_rough_cut(simple_v25(), self.catalog, "library_only")
        self.assertEqual(project.name, "sample")
        self.assertEqual(len(project.clips), 1)
        self.assertEqual(project.duration_ms, 3000)
        self.assertEqual((project.width, project.height, project.fps), (1280, 720, 30))

    def test_unavailable_asset_fails_without_silent_fallback(self):
        report = inspect_plan(simple_v25(), self.catalog, "library_only")
        self.assertFalse(report["desktop_rough_cut_ready"])
        with self.assertRaises(DirectorSpecError):
            build_rough_cut(simple_v25(), self.catalog, "library_only")

    def test_render_adapter_does_not_discard_effects(self):
        self.catalog.import_path(self.media)
        report = inspect_plan(simple_v25(effect="cinematic_grain"), self.catalog, "library_only")
        self.assertFalse(report["desktop_rough_cut_ready"])
        self.assertIn("cinematic_grain", "\n".join(report["desktop_blockers"]))

    def test_library_mode_conflict_is_blocked(self):
        self.catalog.import_path(self.media)
        report = inspect_plan(simple_v25(), self.catalog, "scene_first")
        self.assertEqual(report["status"], "BLOCKED")
        self.assertFalse(report["desktop_rough_cut_ready"])


if __name__ == "__main__":
    unittest.main()
