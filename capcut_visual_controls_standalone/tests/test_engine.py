from __future__ import annotations
import copy
import json
from pathlib import Path
import tempfile
import unittest
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Options, BLURS, create_preview, load_project, project_fingerprint, save_project


def draft():
    return {
        "id": "p1", "duration": 7_000_000, "canvas_config": {"width": 1920, "height": 1080},
        "materials": {"videos": [
            {"id": "vid", "type": "video", "material_name": "clip1.mp4"},
            {"id": "img", "type": "photo", "material_name": "photo1.png"}],
            "audios": [{"id": "aud", "type": "extract_music"}],
            "canvases": [{"id": "oldcanvas", "type": "canvas_color", "blur": 0, "color": ""}],
            "transitions": [{"id": "transition", "name": "Blink"}]},
        "tracks": [
            {"type": "video", "name": "Visual", "segments": [
                {"id": "svid", "material_id": "vid", "extra_material_refs": ["oldcanvas", "transition"],
                 "clip": {"scale": {"x": 1, "y": 1}, "transform": {"x": 0.4, "y": 0}, "rotation": 5},
                 "uniform_scale": {"on": True, "value": 1},
                 "target_timerange": {"start": 0, "duration": 3_000_000}},
                {"id": "sphoto", "material_id": "img", "extra_material_refs": [],
                 "clip": {"scale": {"x": 1, "y": 1}, "transform": {"x": 0.1, "y": 0}},
                 "target_timerange": {"start": 3_000_000, "duration": 4_000_000}}]},
            {"type": "audio", "segments": [{"id": "saudio", "material_id": "aud", "clip": None,
                                               "target_timerange": {"start": 0, "duration": 7_000_000}}]}]}


class VisualTests(unittest.TestCase):
    def test_ranges_and_preservation(self):
        data = draft()
        updated, rows, count = create_preview(data, Options())
        v, i = updated["tracks"][0]["segments"]
        self.assertEqual(count["videos"], 1)
        self.assertEqual(count["images"], 1)
        self.assertEqual(v["clip"]["transform"]["x"], 0)
        self.assertTrue(1.15 <= v["clip"]["scale"]["x"] <= 1.25)
        self.assertTrue(1.05 <= i["clip"]["scale"]["x"] <= 1.1)
        self.assertTrue(-220 <= v["clip"]["transform"]["y"] * 540 <= -120)
        self.assertTrue(-50 <= i["clip"]["transform"]["y"] * 540 <= 0)
        self.assertEqual(i["clip"]["transform"]["x"], .1)
        self.assertEqual(v["uniform_scale"]["value"], v["clip"]["scale"]["x"])
        self.assertEqual(updated["materials"]["transitions"], data["materials"]["transitions"])
        self.assertEqual(updated["tracks"][1], data["tracks"][1])
        self.assertEqual(v["target_timerange"], data["tracks"][0]["segments"][0]["target_timerange"])
        self.assertEqual(updated["materials"]["canvases"][0]["type"], "canvas_blur")
        self.assertEqual(updated["materials"]["canvases"][0]["blur"], .375)
        self.assertEqual(v["extra_material_refs"][-1], "transition")
        self.assertEqual(len(updated["materials"]["canvases"]), 2)

    def test_stable_and_idempotent(self):
        one, rows, _ = create_preview(draft(), Options())
        two, _, _ = create_preview(one, Options())
        self.assertEqual(one, two)
        v1, _, _ = create_preview(draft(), Options(seed=88))
        self.assertNotEqual(one["tracks"][0]["segments"][0]["clip"]["scale"], v1["tracks"][0]["segments"][0]["clip"]["scale"])

    def test_animated_static_transforms_skipped_but_canvas_applied(self):
        source = draft()
        source["tracks"][0]["segments"][0]["common_keyframes"] = [{"property_type": "KFTypeScaleX", "keyframe_list": [{"values": [1]}, {"values": [1.3]}]}]
        result, rows, counts = create_preview(source, Options())
        self.assertEqual(result["tracks"][0]["segments"][0]["clip"], source["tracks"][0]["segments"][0]["clip"])
        self.assertEqual(result["tracks"][0]["segments"][0]["common_keyframes"], source["tracks"][0]["segments"][0]["common_keyframes"])
        self.assertEqual(counts["animated_skipped"], 1)
        self.assertEqual(result["materials"]["canvases"][0]["type"], "canvas_blur")

    def test_canvas_only(self):
        result, rows, c = create_preview(draft(), Options(video_scale=False, video_position=False, image_scale=False, image_position=False))
        self.assertEqual(result["tracks"][0]["segments"][0]["clip"], draft()["tracks"][0]["segments"][0]["clip"])
        self.assertEqual(c["blurred"], 2)

    def test_both_drafts_metadata_backup_and_fingerprint(self):
        with tempfile.TemporaryDirectory() as td:
            root = Path(td)
            project = root / "Example"
            nested = project / "Timelines" / "A1"
            nested.mkdir(parents=True)
            top = project / "draft_content.json"
            active = nested / "draft_content.json"
            original = draft()
            top.write_text(json.dumps({**original, "name": "stale"}), encoding="utf8")
            active.write_text(json.dumps(original), encoding="utf8")
            (project / "Timelines" / "project.json").write_text(json.dumps({"main_timeline_id": "A1"}), encoding="utf8")
            (project / "draft_meta_info.json").write_text(json.dumps({"tm_draft_modified": 1, "important": 5}))
            (root / "root_meta_info.json").write_text(json.dumps({"all_draft_store": [
                {"draft_fold_path": str(project).replace("\\", "/"), "tm_draft_modified": 1}]}))
            loaded, paths, warnings = load_project(project)
            self.assertEqual(loaded, original)
            self.assertEqual(len(paths), 2)
            self.assertTrue(warnings)
            fingerprint = project_fingerprint(paths)
            result = save_project(project, Options(), expected=fingerprint)
            self.assertTrue(result["saved"])
            self.assertTrue((Path(result["backup"]) / "manifest.json").exists())
            self.assertEqual(json.loads(top.read_text()), json.loads(active.read_text()))
            self.assertEqual(json.loads((project / "draft_meta_info.json").read_text())["important"], 5)
            self.assertEqual(json.loads((root / "root_meta_info.json").read_text())["all_draft_store"][0]["tm_draft_modified"] > 1, True)
            second, _, _ = load_project(project)
            self.assertEqual(second["tracks"][1], original["tracks"][1])
            with self.assertRaises(RuntimeError):
                save_project(project, Options(seed=4), expected=fingerprint)
            self.assertFalse((project / ".visual_controls_test.lock").exists())

    def test_invalid_ranges_and_canvas_rejected(self):
        with self.assertRaises(ValueError): create_preview(draft(), Options(video_scale_min=140, video_scale_max=120))
        with self.assertRaises(ValueError): create_preview(draft(), Options(blur_strength=.123))
        missing = draft()
        del missing["canvas_config"]
        with self.assertRaises(ValueError): create_preview(missing, Options())


if __name__ == "__main__":
    unittest.main()

