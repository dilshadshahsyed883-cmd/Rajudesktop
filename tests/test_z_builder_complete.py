"""Regression coverage for one-piece CapCut draft exports and true progress."""
import base64
import json
from pathlib import Path
import tempfile
import unittest

from z_builder.capcut import export_capcut, find_node, split_into_parts
from z_builder.core import load_plan, preflight


PNG = base64.b64decode(
    'iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a+4sAAAAASUVORK5CYII=')


class CompleteCapCutTests(unittest.TestCase):
    @unittest.skipUnless(find_node(), 'Node required for real native CapCut draft')
    def test_eight_minute_scene_full_project_not_blocked_by_parts_limit(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / 'Still.png'
            image.write_bytes(PNG)
            plan = load_plan('name=Long Test Video\n00:00:00.000 --> 00:08:05.000 | image | Still.png\n')
            plan.shots[0].assigned_path = str(image)
            self.assertEqual(preflight(plan), [])
            with self.assertRaisesRegex(ValueError, 'exceeds 7 minutes'):
                split_into_parts(plan)

            updates = []
            result = export_capcut(plan, str(root / 'drafts'), launch=False,
                                   mode='complete', progress_callback=lambda *args: updates.append(args))
            self.assertEqual('complete', result['mode'])
            self.assertEqual(1, result['count'])
            self.assertEqual(485.0, result['parts'][0]['duration_seconds'])
            self.assertTrue(updates)
            self.assertEqual((0, 1), updates[0][:2])
            self.assertEqual((1, 1), updates[-1][:2])
            draft = Path(result['parts'][0]['folder'])
            self.assertTrue((draft / 'Z_Builder_Project_Info.json').is_file())
            self.assertFalse((draft / 'Z_Builder_Part_Info.json').exists())
            self.assertEqual('complete', json.loads((draft / 'Z_Builder_Project_Info.json').read_text())['mode'])
            content = json.loads((draft / 'draft_content.json').read_text())
            visual = [track for track in content['tracks'] if track['type'] == 'video']
            self.assertEqual(['Images + Videos - Single Layer'], [track['name'] for track in visual])
            self.assertEqual(485_000_000, visual[0]['segments'][0]['target_timerange']['duration'])
            self.assertFalse(any(t['type'] == 'audio' for t in content['tracks']))
            self.assertTrue(image.exists())

    @unittest.skipUnless(find_node(), 'Node required')
    def test_parts_mode_unchanged_progress_and_metadata(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            image = root / 'Still.png'
            image.write_bytes(PNG)
            plan = load_plan('name=Short Test Video\n00:00.000 --> 00:04.000 | image | Still.png')
            plan.shots[0].assigned_path = str(image)
            updates = []
            result = export_capcut(plan, str(root / 'drafts'), mode='parts',
                                   progress_callback=lambda *args: updates.append(args))
            self.assertEqual('parts', result['mode'])
            self.assertEqual(1, result['count'])
            self.assertTrue((Path(result['parts'][0]['folder']) / 'Z_Builder_Part_Info.json').exists())
            self.assertEqual((1, 1), updates[-1][:2])


if __name__ == '__main__':
    unittest.main()
