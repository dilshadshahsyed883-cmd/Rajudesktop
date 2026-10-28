"""The Scene Plan times, not 4-second source video lengths, govern CapCut."""
from pathlib import Path
import json
import shutil
import subprocess
import tempfile
import unittest

from z_builder.core import Catalog, bind_media, load_plan, preflight, timeline
from z_builder.capcut import build_request, export_capcut, find_node


def ffmpeg_bin():
    executable = shutil.which('ffmpeg')
    if executable:
        return executable
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except (ImportError, OSError, RuntimeError):
        return None


SIMPLE = """name=Z Builder Timed Example
aspect=16:9
fps=30
00:00.000 --> 00:02.500 | video | Clip 1.mp4 | in=1.250
00:02.500 --> 00:07.250 | image | Poster 1.png
"""


class TimedScenePlanTests(unittest.TestCase):
    def test_explicit_time_video_trim_and_still_hold(self):
        plan = load_plan(SIMPLE)
        self.assertEqual([(a, b) for a,b,_ in timeline(plan)], [(0.0, 2.5), (2.5, 7.25)])
        self.assertEqual(plan.shots[0].source_in_seconds, 1.25)
        self.assertEqual(plan.shots[0].duration, 2.5)
        self.assertEqual(plan.shots[1].duration, 4.75)
        self.assertEqual(plan.duration, 7.25)

    def test_gap_overlap_and_source_overrun_rejected(self):
        for wrong in [SIMPLE.replace('00:02.500 --> 00:07.250', '00:02.550 --> 00:07.250'),
                      SIMPLE.replace('00:02.500 --> 00:07.250', '00:02.450 --> 00:07.250'),
                      SIMPLE.replace('in=1.250', 'in=8.000')]:
            with self.assertRaises(ValueError):
                load_plan(wrong)
        with tempfile.TemporaryDirectory() as folder:
            plan = load_plan(SIMPLE.replace('in=1.250', 'in=1.800'))
            for shot in plan.shots:
                asset = Path(folder) / shot.filename
                asset.write_bytes(b'dummy')
                shot.assigned_path = str(asset)
            plan.narration_path = str(Path(folder) / 'voice.mp3')
            Path(plan.narration_path).write_bytes(b'dummy')
            self.assertTrue(any('4-second clip' in issue for issue in preflight(plan)))

    def test_keyword_selection_ambiguous_requires_manual_review(self):
        txt = '00:00 --> 00:03.250 | video | keyword: tennis\n'
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            c = Catalog(root / 'c.db')
            clip = root / 'tennis court.mp4'
            clip.write_bytes(b'fake')
            c.add(clip)
            plan = load_plan(txt)
            self.assertEqual(bind_media(plan, c.assets()), [])
            self.assertTrue(Path(plan.shots[0].assigned_path).samefile(clip))
            clip2 = root / 'tennis player.mp4'
            clip2.write_bytes(b'fake')
            c.add(clip2)
            other = load_plan(txt)
            self.assertIn('multiple media', bind_media(other, c.assets())[0])

    @unittest.skipUnless(ffmpeg_bin() and find_node(), 'FFmpeg and Node needed')
    def test_real_four_second_video_is_trimmed_and_aligned_in_capcut_draft(self):
        import base64
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            clip = root / 'Clip 1.mp4'
            image = root / 'Poster 1.png'
            voice = root / 'voice.wav'
            subprocess.run([ffmpeg_bin(), '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                            '-i', 'color=c=blue:s=320x180:r=30:d=4', '-c:v', 'mpeg4', '-an', str(clip)],
                           check=True, timeout=35)
            subprocess.run([ffmpeg_bin(), '-hide_banner', '-loglevel', 'error', '-y', '-f', 'lavfi',
                            '-i', 'anullsrc=r=44100:cl=mono', '-t', '7.25', '-c:a', 'pcm_s16le', str(voice)],
                           check=True, timeout=35)
            image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a+4sAAAAASUVORK5CYII='))
            c = Catalog(root / 'library.sqlite')
            c.add(clip)
            c.add(image)
            p = load_plan(SIMPLE)
            p.narration_path = str(voice)
            self.assertEqual(bind_media(p, c.assets()), [])
            self.assertEqual(preflight(p), [])
            request, warnings = build_request(p)
            self.assertEqual(request['payload']['images'][0]['trimStart'], 1.25)
            self.assertEqual(request['payload']['images'][0]['end'], 2.5)
            self.assertEqual(request['payload']['images'][1]['end'], 7.25)
            out = export_capcut(p, str(root / 'drafts'), launch=False)
            data = json.loads((Path(out['parts'][0]['folder']) / 'draft_content.json').read_text())
            visual = [t for t in data['tracks'] if t['type'] == 'video']
            self.assertEqual([t['name'] for t in visual], ['Images + Videos - Single Layer'])
            self.assertEqual(visual[0]['segments'][0]['source_timerange'], {'start': 1250000, 'duration': 2500000})
            self.assertEqual(visual[0]['segments'][0]['target_timerange'], {'start': 0, 'duration': 2500000})
            self.assertEqual(visual[0]['segments'][1]['target_timerange'], {'start': 2500000, 'duration': 4750000})
            self.assertEqual([t['type'] for t in data['tracks']].count('audio'), 0)
            self.assertEqual(len(visual), 1)
            mats = {m['id']: m for m in data['materials']['videos']}
            self.assertEqual([mats[s['material_id']]['type'] for s in visual[0]['segments']],
                             ['video', 'photo'])
            self.assertTrue(clip.exists(), 'Source clip is never physically cut/deleted')
            self.assertTrue(image.exists())
            self.assertEqual([], [])

if __name__ == '__main__':
    unittest.main()
