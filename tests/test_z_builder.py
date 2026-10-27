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
            self.assertTrue((Path(result['parts'][0]['folder']) / 'draft_content.json').exists())
            self.assertTrue((Path(result['parts'][0]['folder']) / 'Z_Builder_Timeline.csv').exists())
            self.assertEqual([], [])
            data = json.loads((Path(result['parts'][0]['folder']) / 'draft_content.json').read_text())
            self.assertEqual(len(data['tracks'][0]['segments']), 1)


    def test_used_media_requires_verified_export_and_manual_cleanup(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            used = root / 'Used Video.mp4'
            unused = root / 'Keep Image.jpg'
            used.write_bytes(b'video')
            unused.write_bytes(b'image')
            catalog = Catalog(root / 'catalog.sqlite')
            used_id = catalog.add(used)
            unused_id = catalog.add(unused)
            self.assertEqual([], [a for a in catalog.assets() if a['export_count']])
            self.assertEqual(([], [f'{unused_id}: not marked as exported (not eligible)']),
                             catalog.recycle_exported_media([unused_id], recycle=lambda _: self.fail('deleted unused')))
            self.assertEqual(1, catalog.record_successful_export([str(used), str(used), str(root / 'missing.jpg')]))
            self.assertEqual(2, catalog.record_successful_export([str(used), str(unused)]))
            indexed = {a['id']: a for a in catalog.assets()}
            self.assertEqual(2, indexed[used_id]['export_count'])
            self.assertEqual(1, indexed[unused_id]['export_count'])
            recycled = root / 'recycled'
            recycled.mkdir()
            moved, failures = catalog.recycle_exported_media([used_id, used_id],
                recycle=lambda path: Path(path).rename(recycled / Path(path).name))
            # Windows may resolve a short 8.3 profile path into its long equivalent.
            self.assertEqual(1, len(moved))
            self.assertEqual(used.name, Path(moved[0]).name)
            self.assertFalse(failures)
            self.assertFalse(used.exists())
            self.assertTrue((recycled / used.name).exists())
            self.assertTrue(unused.exists())
            self.assertEqual([unused_id], [a['id'] for a in catalog.assets()])
            # Re-importing a recovered original must not inherit old usage history.
            (recycled / used.name).rename(used)
            catalog.add(used)
            self.assertEqual(0, next(a['export_count'] for a in catalog.assets() if a['id'] == used_id))

    def test_failed_recycle_keeps_original_and_catalog_history(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            source = root / 'clip.mp4'
            source.write_bytes(b'data')
            catalog = Catalog(root / 'catalog.sqlite')
            asset_id = catalog.add(source)
            catalog.record_successful_export([source])
            def broken_recycle(_):
                raise PermissionError('file locked by Windows')
            moved, failures = catalog.recycle_exported_media([asset_id], recycle=broken_recycle)
            self.assertFalse(moved)
            self.assertIn('file locked', failures[0])
            self.assertTrue(source.is_file())
            self.assertEqual(1, catalog.assets()[0]['export_count'])


    def test_clean_entire_library_records_only_preserves_all_original_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            img, clip = root / 'original.jpg', root / 'clip.mp4'
            img.write_bytes(b'image')
            clip.write_bytes(b'video')
            db = Catalog(root / 'lib.sqlite')
            db.add(img)
            db.add(clip)
            db.record_successful_export([img])
            self.assertEqual(2, db.clear_library_records())
            self.assertEqual([], db.assets())
            self.assertTrue(img.exists())
            self.assertTrue(clip.exists())
            self.assertEqual(0, db.clear_library_records())
            new_id = db.add(img)
            self.assertEqual(0, next(a['export_count'] for a in db.assets()
                                      if a['id'] == new_id))

    def test_clean_entire_library_recycles_used_and_unused_with_safe_failures(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            ok_file, locked, missing = (root / 'good.jpg', root / 'locked.mp4',
                                        root / 'missing.jpg')
            ok_file.write_bytes(b'ok')
            locked.write_bytes(b'locked')
            missing.write_bytes(b'not here soon')
            db = Catalog(root / 'lib.sqlite')
            db.add(ok_file)
            db.add(locked)
            db.add(missing)
            missing.unlink()
            trash = root / 'trash'
            trash.mkdir()
            def recycle(path):
                source = Path(path)
                if source.name == 'locked.mp4':
                    raise PermissionError('simulated locked file')
                source.rename(trash / source.name)
            moved, forgotten, failures = db.recycle_entire_library(recycle=recycle)
            self.assertEqual([ok_file.name], [Path(x).name for x in moved])
            self.assertEqual([missing.name], [Path(x).name for x in forgotten])
            self.assertEqual(1, len(failures))
            self.assertIn('simulated locked file', failures[0])
            self.assertTrue((trash / 'good.jpg').is_file())
            self.assertTrue(locked.is_file())
            self.assertFalse(missing.exists())
            self.assertEqual(['locked.mp4'], [a['filename'] for a in db.assets()])



if __name__ == '__main__':
    unittest.main()
