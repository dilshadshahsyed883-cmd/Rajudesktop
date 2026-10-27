import json
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from z_builder.core import Catalog, bind_media, load_plan, preflight, save_project, open_project
from z_builder.capcut import build_request, export_capcut, find_node


def sample_plan(filename='Alexandra Eala 1.jpg', mode='library_only'):
    return '''SCENE_PLAN_VERSION=2
[PROJECT]
name=Z Builder Unit Test
[MEDIA]
source_mode=''' + mode + '''
[OUTPUT]
resolution=1080p
aspect_ratio=16:9
fps=30
[SCENE_001.SHOT_01]
media_type=image
library_filename=''' + filename + '''
pexels_primary_keyword=tennis court match
animation=pan_left
animation_duration=2
narration=Welcome.
'''


class ZBuilderCoreTests(unittest.TestCase):
    def test_exact_filename_mapping_and_duplicate_detection(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            media = root / 'Alexandra Eala 1.jpg'
            media.write_bytes(b'image dummy')
            catalog = Catalog(root / 'catalog.sqlite')
            catalog.add(media)
            plan = load_plan(sample_plan())
            self.assertFalse(bind_media(plan, catalog.assets()))
            self.assertFalse(preflight(plan))
            self.assertTrue(Path(plan.shots[0].assigned_path).samefile(media))
            other = root / 'sub' / media.name
            other.parent.mkdir()
            other.write_bytes(b'other dummy')
            catalog.add(other)
            plan = load_plan(sample_plan())
            self.assertIn('ambiguous', bind_media(plan, catalog.assets())[0])
            self.assertTrue(preflight(plan))

    def test_library_only_no_pexels_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            plan = load_plan(sample_plan('missing.jpg', 'library_only'))
            problem = bind_media(plan, [])
            self.assertIn('local media missing', problem[0])
            file = Path(tmp) / 'project.zbproj'
            save_project(plan, file)
            self.assertEqual(open_project(file).source_mode, 'library_only')
            self.assertIn('Pexels', bind_media(load_plan(sample_plan('none', 'scene_first')), [])[0])

    def test_invalid_or_unsupported_plan_rejected(self):
        with self.assertRaises(ValueError):
            load_plan(sample_plan().replace('SCENE_PLAN_VERSION=2', 'SCENE_PLAN_VERSION=1'))
        with self.assertRaises(ValueError):
            load_plan(sample_plan().replace('fps=30', 'fps=27'))
        with self.assertRaises(ValueError):
            load_plan(sample_plan() + '\n[SCENE_001.SHOT_01]\nduration_seconds=1\n')

    def test_motion_and_caption_export_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            f = Path(tmp) / 'Alexandra Eala 1.jpg'
            f.write_bytes(b'image dummy')
            c = Catalog(Path(tmp) / 'data.db')
            c.add(f)
            p = load_plan(sample_plan())
            bind_media(p, c.assets())
            payload, warnings = build_request(p)
            self.assertEqual(payload['payload']['images'][0]['kfs']['px'][0]['v'], 0.06)
            self.assertEqual(payload['payload']['captions'][0]['text'], 'Welcome.')

    @unittest.skipUnless(find_node(), 'Node runtime unavailable')
    def test_z_studio_capcut_draft_is_verified(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # Valid tiny PNG avoids a CapCut input probe rejecting unknown image bytes.
            import base64
            f = root / 'Alexandra Eala 1.png'
            f.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a+4sAAAAASUVORK5CYII='))
            c = Catalog(root / 'lib.sqlite')
            c.add(f)
            p = load_plan(sample_plan(f.name))
            bind_media(p, c.assets())
            result = export_capcut(p, str(root / 'drafts'), launch=False)
            self.assertTrue((Path(result['folder']) / 'draft_content.json').exists())
            self.assertTrue((Path(result['folder']) / 'Z_Builder_Timeline.csv').exists())
            self.assertEqual(result['verify_issues'], [])
            data = json.loads((Path(result['folder']) / 'draft_content.json').read_text())
            self.assertEqual(len(data['tracks'][0]['segments']), 1)


if __name__ == '__main__':
    unittest.main()
