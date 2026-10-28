"""Native Scene Plan -> CapCut draft effects integration regressions."""
from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from z_builder.core import load_plan, timeline, Shot, Plan
from z_builder.native_scene_effects import (
    apply_effects_in_memory, needs_native_effects, prepare_effects,
    _segment_mapping,
)


def sample_plan():
    text = """name=Effects Test
combo_default=random_saved
transition_default=random_saved
combo_seed=7
transition_seed=8
transition_duration=0.4
00:00.000 --> 00:02.500 | image | first.jpg
00:02.500 --> 00:05.500 | image | second.jpg | combo=Pendulum 1 | transition_after=Pull in
00:05.500 --> 00:09.500 | video | cut.mp4
00:09.500 --> 00:11.500 | image | third.jpg | combo=none
"""
    return load_plan(text)


def sample_draft():
    photos = [
        {'id': 'mat-first', 'type': 'photo', 'material_name': 'image0001 first.jpg'},
        {'id': 'mat-second', 'type': 'photo', 'material_name': 'image0002 second.jpg'},
        {'id': 'mat-third', 'type': 'photo', 'material_name': 'image0003 third.jpg'},
        {'id': 'mat-video', 'type': 'video', 'material_name': 'video0003 cut.mp4'}
    ]
    def segment(ident, mat, start, duration):
        return {'id': ident, 'material_id': mat,
                'source_timerange': {'start': 0, 'duration': duration},
                'target_timerange': {'start': start, 'duration': duration},
                'common_keyframes': [{'property_type': 'scale', 'keyframe_list': []}],
                'extra_material_refs': [], 'volume': 1}
    return {'materials': {'videos': photos, 'material_animations': [], 'transitions': [], 'audios': []},
            'tracks': [
                {'id': 'lower', 'name': 'Images - Lower Layer', 'type': 'video',
                 'segments': [
                    segment('s1', 'mat-first', 0, 2_500_000),
                    segment('s2', 'mat-second', 2_500_000, 3_000_000),
                    segment('s4', 'mat-third', 9_500_000, 2_000_000)]},
                {'id': 'upper', 'name': 'Videos - Upper Layer', 'type': 'video',
                 'segments': [segment('s3', 'mat-video', 5_500_000, 4_000_000)]},
                {'id': 'voice', 'type': 'audio', 'segments': [{'id': 'voice1', 'volume': 1}]}],
            'duration': 11_500_000}


def anim_catalog(path):
    def entry(effect, name):
        return {'effect_id': effect, 'name': name, 'duration_us': 5_000_000,
                'category': 'Trending-3', 'path': str(path),
                'template': {'id': 'old'+effect, 'type': 'sticker_animation',
                             'animations': [{'id': effect, 'resource_id': effect, 'type': 'group',
                                              'name': name, 'category_name': 'Trending-3',
                                              'duration': 5_000_000, 'path': str(path)}]}}
    return [entry('anim-pendulum','Pendulum 1'), entry('anim-sway','Sway Out')]


def transition_catalog():
    return [{'effect_id': 'pull-id', 'name': 'Pull in', 'category': 'Trending',
             'template': {'id': 'oldtrans', 'effect_id': 'pull-id',
                          'name': 'Pull in', 'duration': 500_000}}]


class ScenePlanEffectTests(unittest.TestCase):
    def test_parser_accepts_native_effects_without_changing_keyframe_motion(self):
        plan = sample_plan()
        self.assertEqual(plan.sections['CAPCUT_EFFECTS']['combo_default'], 'random_saved')
        self.assertEqual(plan.sections['CAPCUT_EFFECTS']['transition_duration'], '0.4')
        self.assertEqual(plan.shots[1].native_combo, 'Pendulum 1')
        self.assertEqual(plan.shots[1].native_transition_after, 'Pull in')
        self.assertEqual(plan.shots[3].native_combo, 'none')
        self.assertEqual(plan.shots[0].animation, 'none')
        self.assertTrue(needs_native_effects(plan))
        self.assertFalse(needs_native_effects(load_plan(
            '00:00 --> 00:02 | image | photo.jpg')))

    def test_effects_mapping_preserves_all_video_and_layers(self):
        plan = sample_plan()
        # Remove an explicit transition across image/video tracks: it is not safe.
        plan.shots[1].native_transition_after = ''
        part = SimpleNamespace(plan=plan)
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            a, t = anim_catalog(root), transition_catalog()
            with (mock.patch('z_builder.native_scene_effects.harvest_animations', return_value=a),
                  mock.patch('z_builder.native_scene_effects.harvest_transitions', return_value=t)):
                resolved = prepare_effects(plan, [part], root, root)
            self.assertEqual(len(resolved['animations']), 2)
            self.assertEqual(len(resolved['transitions']), 1)
            self.assertEqual(resolved['animations'][plan.shots[1].section], 'anim-pendulum')
            self.assertNotIn(plan.shots[3].section, resolved['animations'])
            raw = sample_draft()
            original = copy.deepcopy(raw)
            out, stats = apply_effects_in_memory(raw, part, resolved)
            self.assertEqual(stats['animations'], 2)
            self.assertEqual(stats['transitions'], 1)
            self.assertEqual(len(out['materials']['material_animations']), 2)
            self.assertEqual(len(out['materials']['transitions']), 1)
            self.assertEqual(out['tracks'][1], original['tracks'][1])
            self.assertEqual(out['tracks'][2], original['tracks'][2])
            self.assertEqual(out['materials']['videos'], original['materials']['videos'])
            for prev, after in zip(original['tracks'][0]['segments'], out['tracks'][0]['segments']):
                for field in ('id', 'material_id', 'target_timerange', 'source_timerange',
                              'common_keyframes', 'volume'):
                    self.assertEqual(prev[field], after[field])
            self.assertEqual(out['materials']['material_animations'][0]['animations'][0]['duration'], 2_500_000)

    def test_explicit_cross_layer_transition_blocks_before_draft_write(self):
        plan = sample_plan()
        part = SimpleNamespace(plan=plan)
        with tempfile.TemporaryDirectory() as root:
            root = Path(root)
            with (mock.patch('z_builder.native_scene_effects.harvest_animations',
                             return_value=anim_catalog(root)),
                  mock.patch('z_builder.native_scene_effects.harvest_transitions',
                             return_value=transition_catalog())):
                with self.assertRaisesRegex(ValueError, 'cross-layer or cross-part'):
                    prepare_effects(plan, [part], root, root)

    def test_explicit_combo_on_video_blocks(self):
        plan = sample_plan()
        plan.shots[2].native_combo = 'Pendulum 1'
        plan.shots[1].native_transition_after = 'none'
        part = SimpleNamespace(plan=plan)
        with tempfile.TemporaryDirectory() as root:
            with (mock.patch('z_builder.native_scene_effects.harvest_animations',
                             return_value=anim_catalog(root)),
                  mock.patch('z_builder.native_scene_effects.harvest_transitions',
                             return_value=transition_catalog())):
                with self.assertRaisesRegex(ValueError, 'images only'):
                    prepare_effects(plan, [part], root, root)

    def test_missing_preset_blocks_without_random_substitution(self):
        plan = sample_plan()
        plan.shots[1].native_combo = 'Imaginary Effect'
        plan.shots[1].native_transition_after = 'none'
        with tempfile.TemporaryDirectory() as root:
            with (mock.patch('z_builder.native_scene_effects.harvest_animations',
                             return_value=anim_catalog(root)),
                  mock.patch('z_builder.native_scene_effects.harvest_transitions',
                             return_value=transition_catalog())):
                with self.assertRaisesRegex(ValueError, 'not in saved CapCut projects'):
                    prepare_effects(plan, [SimpleNamespace(plan=plan)], root, root)

    def test_duplicate_image_name_is_never_fuzzy_matched(self):
        plan = sample_plan()
        plan.shots[0].filename = 'same.jpg'
        plan.shots[1].filename = 'same.jpg'
        mapping = _segment_mapping(sample_draft(), SimpleNamespace(plan=plan))
        self.assertNotEqual(mapping[plan.shots[0].section], mapping[plan.shots[1].section])

    def test_old_project_deserialization_defaults_preserved(self):
        from z_builder.core import Plan
        old = sample_plan().to_dict()
        for shot in old['shots']:
            shot.pop('native_combo')
            shot.pop('native_transition_after')
        restored = Plan.from_dict(old)
        self.assertEqual(restored.shots[0].native_combo, '')
        self.assertEqual(restored.shots[0].native_transition_after, '')


if __name__ == '__main__':
    unittest.main()
