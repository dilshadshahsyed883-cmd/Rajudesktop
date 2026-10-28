import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from transition_engine import (Plan, active_mirror, apply_plan, cut_inventory, harvest_transitions,
    immutable_snapshot, list_projects, load_project, parse_edit_file, plan_transitions, save_transitions)


def draft():
    v = [{"id":"img1","type":"photo","material_name":"0-00.png"},{"id":"vid1","type":"video","material_name":"1-41.mp4"},{"id":"img2","type":"photo","material_name":"2-00.png"}]
    seg = [{"id":"s1","material_id":"img1","target_timerange":{"start":0,"duration":4000000},"source_timerange":{"start":10000,"duration":4000000},"keyframe_refs":["keep"],"extra_material_refs":["color1"]},
           {"id":"s2","material_id":"vid1","target_timerange":{"start":4000000,"duration":3000000},"source_timerange":{"start":500000,"duration":3000000},"volume":0.6,"extra_material_refs":[]},
           {"id":"s3","material_id":"img2","target_timerange":{"start":7000000,"duration":4000000},"extra_material_refs":[]}]
    return {"duration":11000000,"fps":30,"materials":{"videos":v,"audios":[{"id":"a"}],"transitions":[]},
            "tracks":[{"id":"lower","type":"video","segments":seg},{"id":"audio","type":"audio","segments":[{"id":"v","volume":0.7}]}]}


def catalog():
    return [{"effect_id":"flash","name":"Flash Zoom","category":"Zoom","template":{"id":"t1","effect_id":"flash","name":"Flash Zoom","duration":500000,"resource_id":"r1"}},
            {"effect_id":"blink","name":"Blink","category":"Basic","template":{"id":"t2","effect_id":"blink","name":"Blink","duration":500000}}]


class EngineTests(unittest.TestCase):
    def test_mixed_media_cut_detection(self):
        cuts, errors = cut_inventory(draft())
        self.assertEqual([c["after_type"] for c in cuts], ["photo", "video"])
        self.assertEqual(errors, [])

    def test_no_rebuild_or_video_deletion(self):
        src = draft()
        p = plan_transitions(src, catalog(), "single", ["flash"], 0.6)
        out, info = apply_plan(src, catalog(), p)
        self.assertEqual(info["changed"], 2)
        self.assertEqual([s["material_id"] for s in out["tracks"][0]["segments"]], ["img1", "vid1", "img2"])
        self.assertEqual(out["tracks"][0]["segments"][1]["source_timerange"]["start"], 500000)
        self.assertEqual(out["tracks"][1], src["tracks"][1])
        self.assertEqual(out["tracks"][0]["segments"][0]["keyframe_refs"], ["keep"])
        self.assertEqual(immutable_snapshot(src), immutable_snapshot(out))

    def test_idempotent(self):
        src = draft()
        p = plan_transitions(src, catalog(), "single", ["flash"], 0.6)
        first, _ = apply_plan(src, catalog(), p)
        again, info = apply_plan(first, catalog(), p)
        self.assertEqual(info["changed"], 0)
        self.assertEqual(info["already_matching"], 2)
        self.assertEqual(first, again)

    def test_edit_file_by_filename_override(self):
        spec = {"version":1,"transitions":[{"after":"0-00.png","transition":"Flash Zoom","duration":0.6},
                                           {"after":"1-41","transition":"Blink","effect_id":"blink"}]}
        p = plan_transitions(draft(), catalog(), spec=spec)
        self.assertEqual(p.counts["will_apply"], 2)
        self.assertEqual(p.chosen[(0,0)]["durationUs"], 600000)
        self.assertEqual(p.chosen[(0,1)]["effect_id"], "blink")

    def test_validation_missing_unknown_last_clip(self):
        spec = {"transitions":[{"after":"0-00","transition":"fake"},{"after":"missing.png","transition":"Blink"},
                               {"after":"2-00.png","transition":"Blink"},{"after":"1-41","transition":"Blink"}]}
        p = plan_transitions(draft(), catalog(), spec=spec)
        self.assertEqual(p.counts["missing"], 1)
        self.assertEqual(p.counts["skipped"], 2)
        self.assertEqual(p.counts["will_apply"], 1)

    def test_ambiguous_effect_id(self):
        cat = catalog() + [{"effect_id":"other","name":"Blink","template":{"id":"t3","effect_id":"other"}}]
        spec = {"transitions":[{"after":"0-00","transition":"Blink"}]}
        self.assertEqual(plan_transitions(draft(), cat, spec=spec).counts["skipped"], 1)
        spec["transitions"][0]["effect_id"] = "other"
        self.assertEqual(plan_transitions(draft(), cat, spec=spec).counts["will_apply"], 1)

    def test_gaps_skipped(self):
        src = draft()
        src["tracks"][0]["segments"][1]["target_timerange"]["start"] = 4500000
        src["tracks"][0]["segments"][2]["target_timerange"]["start"] = 7500000
        cuts, warning = cut_inventory(src)
        self.assertEqual(len(cuts), 1)
        self.assertTrue(any("gap/overlap" in w for w in warning))

    def test_cross_track_not_assumed(self):
        src = draft()
        seg = src["tracks"][0]["segments"].pop(1)
        src["tracks"].insert(1, {"type":"video","segments":[seg]})
        cuts, _ = cut_inventory(src)
        self.assertEqual(len(cuts), 0)

    def test_replace_existing_transition_keep_other_refs(self):
        src = draft()
        src["materials"]["transitions"].append({"id":"old","effect_id":"prior","duration":100000})
        src["tracks"][0]["segments"][0]["extra_material_refs"].append("old")
        p = plan_transitions(src, catalog(), spec={"transitions":[{"after":"0-00","transition":"Blink"}]})
        out, _ = apply_plan(src, catalog(), p)
        self.assertNotIn("old", out["tracks"][0]["segments"][0]["extra_material_refs"])
        self.assertIn("color1", out["tracks"][0]["segments"][0]["extra_material_refs"])
        self.assertEqual(immutable_snapshot(src), immutable_snapshot(out))

    def test_editfile_parser(self):
        self.assertEqual(parse_edit_file('{"version":1,"transitions":[]}')["version"], 1)
        for txt in ['{"version":2,"transitions":[]}', '{"version":1}']:
            with self.assertRaises(ValueError):
                parse_edit_file(txt)


class FileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.project = self.root / "Sample"
        self.project.mkdir()
        self.main = self.project / "draft_content.json"
        self.main.write_text(json.dumps(draft()), encoding="utf-8")
        (self.project / "draft_meta_info.json").write_text('{"tm_draft_modified":1}')
        self.root_meta = self.root / "root_meta_info.json"
        self.root_meta.write_text(json.dumps({"all_draft_store":[{"draft_name":"Sample","draft_fold_path":str(self.project)}]}))

    def tearDown(self):
        self.tmp.cleanup()

    def test_scan(self):
        src = json.loads(self.main.read_text())
        src["materials"]["transitions"].append(catalog()[0]["template"])
        self.main.write_text(json.dumps(src))
        self.assertEqual(len(list_projects(self.root)),1)
        self.assertEqual(harvest_transitions(self.root)[0]["effect_id"], "flash")

    def test_mirror_backup_write_and_repeat(self):
        tdir = self.project / "Timelines" / "abc123"
        tdir.mkdir(parents=True)
        (tdir.parent / "project.json").write_text('{"main_timeline_id":"abc123"}')
        mirror = tdir / "draft_content.json"
        original = self.main.read_bytes()
        mirror.write_bytes(original)
        src, _, _, _ = load_project(self.project)
        p = plan_transitions(src, catalog(), "single", ["flash"], 0.6)
        with patch("transition_engine.capcut_running", return_value=False):
            result = save_transitions(self.project, catalog(), p)
        self.assertTrue(result["saved"])
        self.assertEqual(self.main.read_bytes(), mirror.read_bytes())
        self.assertEqual(len(json.loads(self.main.read_bytes())["tracks"][0]["segments"]), 3)
        backup = Path(result["backup_dir"])
        manifest = json.loads((backup / "manifest.json").read_text())
        self.assertTrue(any((backup / x["backup"]).read_bytes() == original for x in manifest))
        with patch("transition_engine.capcut_running", return_value=False):
            again = save_transitions(self.project, catalog(), p)
        self.assertFalse(again["saved"])

    def test_block_while_capcut_open(self):
        before = self.main.read_bytes()
        p = plan_transitions(draft(), catalog(), "single", ["flash"])
        with patch("transition_engine.capcut_running", return_value=True):
            with self.assertRaisesRegex(RuntimeError, "CapCut is running"):
                save_transitions(self.project, catalog(), p)
        self.assertEqual(before, self.main.read_bytes())

    def test_stale_preview_block(self):
        p = Plan(chosen={(9,9):{"effect_id":"flash","durationUs":500000}})
        with patch("transition_engine.capcut_running", return_value=False):
            with self.assertRaisesRegex(RuntimeError,"changed after preview"):
                save_transitions(self.project, catalog(), p)

    def test_unsafe_mirror_path_block(self):
        (self.project / "Timelines").mkdir()
        (self.project / "Timelines" / "project.json").write_text('{"main_timeline_id":"../bad"}')
        with self.assertRaises(ValueError):
            active_mirror(self.project, "draft_content.json")

    def test_rollback_on_partial_write(self):
        import transition_engine
        before = self.main.read_bytes()
        p = plan_transitions(draft(), catalog(), "single", ["flash"])
        original = transition_engine._atomic_write
        n = [0]
        def faulty(path, data):
            n[0] += 1
            if n[0] == 2: raise OSError("simulated failure")
            return original(path, data)
        with patch("transition_engine.capcut_running", return_value=False), patch("transition_engine._atomic_write", side_effect=faulty):
            with self.assertRaisesRegex(OSError,"simulated failure"):
                save_transitions(self.project, catalog(), p)
        self.assertEqual(self.main.read_bytes(), before)


if __name__ == "__main__":
    unittest.main()
