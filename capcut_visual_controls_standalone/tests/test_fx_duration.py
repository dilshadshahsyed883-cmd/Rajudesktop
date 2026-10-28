from __future__ import annotations
import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from engine import Options, create_preview, load_project, project_fingerprint, save_project
from fx_duration import find_target, inspect


def segment(name, material, start, length, **extra):
    return {"id": name, "material_id": material,
            "target_timerange": {"start": start, "duration": length},
            "source_timerange": {"start": 0, "duration": length}, **extra}


def sample():
    return {
        "id": "a-1", "duration": 3_000_000,
        "canvas_config": {"width": 1920, "height": 1080},
        "materials": {"videos": [{"id": "mvid", "type": "video", "material_name": "a.mp4"}],
                      "audios": [{"id": "voice", "type": "extract_music"}],
                      "canvases": [],
                      "video_effects": [
                          {"id": "f1", "type": "filter", "name": "Warm", "effect_id": "w12", "apply_target_type": 2},
                          {"id": "e1", "type": "video_effect", "name": "VHS", "effect_id": "v10", "apply_target_type": 2}]},
        "tracks": [
            {"id": "v", "type": "video", "segments": [
                segment("v1", "mvid", 0, 8_000_000, clip={"scale": {"x": 1.0, "y": 1.0},
                                                       "transform": {"x": 0, "y": 0}}, extra_material_refs=[])]},
            {"id": "a", "type": "audio", "segments": [segment("a1", "voice", 0, 10_000_000, clip=None)]},
            {"id": "t1", "type": "filter", "segments": [segment("fs1", "f1", 1_000_000, 2_000_000)]},
            {"id": "t2", "type": "effect", "segments": [segment("es1", "e1", 500_000, 3_000_000)]},
        ],
    }


class FxDurationTests(unittest.TestCase):
    def test_audio_is_authoritative_and_both_fx_extend(self):
        data = sample()
        untouched = copy.deepcopy(data)
        result, visuals, c = create_preview(data, Options(canvas_blur=False,
                video_scale=False, video_position=False, image_scale=False, image_position=False))
        self.assertEqual(c['timeline_target'], '10.000s (audio timeline endpoint)')
        self.assertEqual(c['filters_found'], 1)
        self.assertEqual(c['effects_found'], 1)
        self.assertEqual(c['fx_extended'], 2)
        self.assertEqual(c['fx_skipped'], 0)
        for t in result['tracks'][2:]:
            seg = t['segments'][0]
            self.assertEqual(seg['target_timerange'], {'start': 0, 'duration': 10_000_000})
            self.assertEqual(seg['source_timerange'], {'start': 0, 'duration': 10_000_000})
        self.assertEqual(result['tracks'][:2], data['tracks'][:2])
        self.assertEqual(result['materials']['video_effects'], data['materials']['video_effects'])
        self.assertEqual(result['duration'], 3_000_000, 'stale draft duration not rewritten')
        self.assertEqual(data, untouched, 'Preview must not mutate the source object')
        twice, _, stats = create_preview(result, Options(canvas_blur=False,
                   video_scale=False, video_position=False, image_scale=False, image_position=False))
        self.assertEqual(result, twice)
        self.assertEqual(stats['fx_extended'], 0)

    def test_toggle_independent_and_detect_disabled(self):
        d = sample()
        rows, t = inspect(d, apply_filters=False, apply_effects=True)
        self.assertEqual([r['status'] for r in rows], ['Disabled by checkbox', 'Will extend'])
        self.assertEqual(d['tracks'][2]['segments'][0]['target_timerange']['duration'], 2_000_000)
        self.assertEqual(d['tracks'][3]['segments'][0]['target_timerange']['duration'], 10_000_000)
        d = sample()
        out, _ = inspect(d, apply_filters=True, apply_effects=False)
        self.assertEqual([r['status'] for r in out], ['Will extend', 'Disabled by checkbox'])

    def test_no_audio_falls_back_to_visual(self):
        data = sample()
        data['tracks'][1]['segments'] = []
        self.assertEqual(find_target(data).end_us, 8_000_000)
        self.assertIn('visual', find_target(data).source)
        out, t = inspect(data)
        self.assertEqual(data['tracks'][3]['segments'][0]['target_timerange']['duration'], 8_000_000)

    def test_multi_segments_not_overlapped(self):
        data = sample()
        other = segment('fs2', 'f1', 3_000_000, 2_000_000)
        data['tracks'][2]['segments'].append(other)
        old = copy.deepcopy(data['tracks'][2])
        rows, t = inspect(data)
        self.assertIn('Multiple segments', rows[0]['status'])
        self.assertIn('Multiple segments', rows[1]['status'])
        self.assertEqual(old, data['tracks'][2])
        self.assertEqual(data['tracks'][3]['segments'][0]['target_timerange']['duration'], 10_000_000)

    def test_clip_scoped_and_keyframed_are_read_only(self):
        data = sample()
        data['materials']['video_effects'].append({'id': 'e2', 'type': 'video_effect', 'name': 'Segment Glow', 'apply_target_type': 0})
        data['tracks'][0]['segments'][0]['extra_material_refs'] = ['e2']
        data['tracks'][3]['segments'][0]['common_keyframes'] = [{'property_type': 'x'}]
        data['tracks'][2]['segments'][0]['material_id'] = 'e2'
        old_filter = copy.deepcopy(data['tracks'][2]); old_effect = copy.deepcopy(data['tracks'][3])
        rows, _ = inspect(data)
        self.assertIn('Track/material type conflict', rows[0]['status'])
        self.assertIn('Animated FX', rows[1]['status'])
        self.assertIn('Detected only', rows[2]['status'])
        self.assertEqual(data['tracks'][2], old_filter)
        self.assertEqual(data['tracks'][3], old_effect)

    def test_invalid_timeranges_missing_materials_fails_closed(self):
        data = sample()
        data['tracks'][2]['segments'][0]['target_timerange']['duration'] = -100
        data['tracks'][3]['segments'][0]['source_timerange']['start'] = 4
        original = copy.deepcopy(data)
        rows, _ = inspect(data)
        self.assertIn('Invalid timerange', rows[0]['status'])
        self.assertIn('source timerange', rows[1]['status'])
        self.assertEqual(data, original)
        data['materials']['video_effects'] = {'bad': 'structure'}
        with self.assertRaises(ValueError): inspect(data)

    def test_missing_audio_and_visual_endpoint_no_modifications(self):
        data = sample()
        data['tracks'][0]['segments'] = []
        data['tracks'][1]['segments'] = []
        rows, target = inspect(data)
        self.assertEqual(target.end_us, 0)
        self.assertEqual(rows[0]['status'], 'Missing audio and visual timeline endpoint')

    def test_duplicate_effect_id_skipped(self):
        data = sample()
        data['materials']['video_effects'].append(copy.deepcopy(data['materials']['video_effects'][0]))
        rows, _ = inspect(data)
        self.assertIn('Duplicate material', rows[0]['status'])

    def test_nested_writes_metadata_backups_and_fingerprint(self):
        data = sample()
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            p = root / 'FX Project'
            main = p / 'draft_content.json'
            nested = p / 'Timelines' / 'MAIN'
            nested.mkdir(parents=True)
            active = nested / 'draft_content.json'
            main.write_text(json.dumps({**data, 'name': 'stale'}), encoding='utf8')
            active.write_text(json.dumps(data), encoding='utf8')
            (p / 'Timelines' / 'project.json').write_text(json.dumps({'main_timeline_id':'MAIN'}), encoding='utf8')
            before, paths, warns = load_project(p)
            fingerprints = project_fingerprint(paths)
            opts = Options(canvas_blur=False, video_scale=False, video_position=False,
                           image_scale=False, image_position=False)
            result = save_project(p, opts, expected=fingerprints)
            self.assertTrue(result['saved'])
            self.assertEqual(result['counts']['fx_extended'], 2)
            self.assertEqual(json.loads(main.read_text()), json.loads(active.read_text()))
            self.assertEqual(json.loads(main.read_text())['tracks'][2]['segments'][0]['target_timerange']['duration'], 10_000_000)
            backups = Path(result['backup'])
            self.assertTrue((backups / 'manifest.json').is_file())
            self.assertEqual(len(json.loads((backups / 'manifest.json').read_text())), 2)
            with self.assertRaises(RuntimeError):
                save_project(p, opts, expected=fingerprints)
            self.assertFalse((p / '.visual_controls_test.lock').exists())


if __name__ == '__main__': unittest.main()

