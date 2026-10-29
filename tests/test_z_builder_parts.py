"""End-to-end long scene plans, fixed visual tracks and optional CapCut narration."""
import base64
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from z_builder.core import load_plan, preflight
from z_builder.capcut import split_into_parts, export_capcut, find_node, build_request

PNG = base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a+4sAAAAASUVORK5CYII=')


def stamp(seconds):
    ms = round(seconds * 1000)
    return f'{ms // 3600000:02d}:{(ms // 60000) % 60:02d}:{(ms // 1000) % 60:02d}.{ms % 1000:03d}'


def make_plan(count=345):
    lines = ['name=Eala Example', 'resolution=1080p', 'fps=30']
    for i in range(count):
        a, b = 2.5 * i, 2.5 * (i + 1)
        kind, file = ('video', f'FourSeconds_{i}.mp4') if i % 4 == 0 else ('image', 'Still.png')
        lines.append(f'{stamp(a)} --> {stamp(b)} | {kind} | {file}')
    return load_plan('\n'.join(lines))


class PartTests(unittest.TestCase):
    def test_split_345_shots_preserves_all_absolute_times(self):
        original = make_plan()
        parts = split_into_parts(original)
        self.assertEqual(len(parts), 3)
        self.assertEqual(parts[0].start_seconds, 0)
        self.assertEqual(parts[-1].end_seconds, 862.5)
        self.assertTrue(all(x.end_seconds - x.start_seconds <= 420 for x in parts))
        self.assertTrue(all(x.end_seconds - x.start_seconds >= 300 for x in parts[:-1]))
        self.assertEqual(sum(len(x.plan.shots) for x in parts), 345)
        self.assertEqual(sum(x.end_seconds - x.start_seconds for x in parts), 862.5)
        for a, b in zip(parts, parts[1:]):
            self.assertEqual(a.end_seconds, b.start_seconds)
            self.assertAlmostEqual(b.plan.shots[0].start_seconds, 0)
            self.assertNotEqual(a.plan.shots[-1].section, b.plan.shots[0].section)

    def test_single_overlong_scene_blocks_without_cutting(self):
        p = load_plan('00:00 --> 08:00 | image | Still.png')
        with self.assertRaisesRegex(ValueError, 'exceeds 7 minutes'):
            split_into_parts(p)

    def test_no_voice_required_for_simple_plan_and_request_is_voice_free(self):
        p = load_plan('00:00 --> 00:02.500 | image | Still.png')
        with tempfile.TemporaryDirectory() as d:
            img = Path(d) / 'Still.png'
            img.write_bytes(PNG)
            p.shots[0].assigned_path = str(img)
            self.assertEqual(preflight(p), [])
            req, _ = build_request(p)
            self.assertIsNone(req['payload']['voice'])
            self.assertFalse(req['payload']['separateLayers'])
            self.assertTrue(req['payload']['singleVisualTrack'])
            with self.assertRaisesRegex(ValueError, 'no voice file'):
                build_request(p, include_voice=True)

    @unittest.skipUnless(find_node(), 'Node required')
    def test_real_three_part_capcut_drafts_fixed_layers_audio_off_and_on(self):
        with tempfile.TemporaryDirectory() as d:
            folder = Path(d)
            img = folder / 'Still.png'
            vid = folder / 'FourSeconds.mp4'
            voice = folder / 'voice.mp3'
            img.write_bytes(PNG)
            # The draft writer works on paths, while FFmpeg correctness is
            # independently covered by test_z_builder_timing's genuine MP4.
            vid.write_bytes(b'video source placeholder for this writer-only test')
            voice.write_bytes(b'voice source placeholder for this writer-only test')
            plan = make_plan()
            plan.narration_path = str(voice)
            for shot in plan.shots:
                if shot.media_type == 'video':
                    unique = folder / shot.filename
                    unique.write_bytes(vid.read_bytes())
                    shot.assigned_path = str(unique)
                else:
                    shot.assigned_path = str(img)
            self.assertEqual(preflight(plan), [])
            def mock_probe(path):
                return {'duration': 900.0 if path == str(voice) else 4.0,
                        'w': 1280, 'h': 720, 'hasAudio': True}
            with patch('z_builder.capcut.probe', side_effect=mock_probe):
                out = export_capcut(plan, str(folder / 'drafts'), launch=False)
            self.assertEqual(out['count'], 3)
            previous = 0.0
            for part in out['parts']:
                self.assertEqual(part['original_start_seconds'], previous)
                previous = part['original_end_seconds']
                self.assertTrue(part['duration_seconds'] <= 420)
                data = json.loads((Path(part['folder']) / 'draft_content.json').read_text())
                visual = [t for t in data['tracks'] if t['type'] == 'video']
                self.assertEqual([t['name'] for t in visual], ['Images + Videos - Single Layer'])
                self.assertFalse(any(t['type'] == 'audio' for t in data['tracks']))
                self.assertEqual(visual[0]['segments'][0]['track_render_index'], 0)
                self.assertTrue((Path(part['folder']) / 'Z_Builder_Part_Info.json').is_file())
                for track in visual:
                    for seg in track['segments']:
                        end = seg['target_timerange']['start'] + seg['target_timerange']['duration']
                        self.assertLessEqual(end / 1_000_000, part['duration_seconds'] + 0.001)
            self.assertEqual(previous, 862.5)
            with patch('z_builder.capcut.probe', side_effect=mock_probe):
                voiced = export_capcut(plan, str(folder / 'voice-drafts'), launch=False, include_voice=True)
            self.assertEqual(voiced['count'], 3)
            for part in voiced['parts']:
                data = json.loads((Path(part['folder']) / 'draft_content.json').read_text())
                tracks = [t for t in data['tracks'] if t['type'] == 'audio']
                self.assertEqual(len(tracks), 1)
                self.assertEqual(tracks[0]['segments'][0]['source_timerange']['start'],
                                 round(part['original_start_seconds'] * 1_000_000))
                self.assertEqual(tracks[0]['segments'][0]['target_timerange']['start'], 0)
                self.assertEqual(tracks[0]['segments'][0]['target_timerange']['duration'],
                                 round(part['duration_seconds'] * 1_000_000))


if __name__ == '__main__':
    unittest.main()
