import copy
import json
import pathlib
import tempfile
import unittest
from z_capcut_lab import audit, experiment, bulk_experiment, data_hash

FIXTURE_DIR = pathlib.Path(__file__).resolve().parent

class LabTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        # optionally test real local owner drafts in the development session only;
        # no personal files are bundled in the exported research kit.
        cls.draft_dir = pathlib.Path(__file__).resolve().parent / 'fixtures'
        cls.a = json.loads((cls.draft_dir / 'synthetic_single_track.json').read_text(encoding='utf-8'))
        cls.b = json.loads((cls.draft_dir / 'synthetic_two_track.json').read_text(encoding='utf-8'))

    def test_owner_samples_schema_integrity(self):
        for j in (self.a, self.b):
            r = audit(j)
            self.assertTrue(r['valid_structure'], r['errors'])
            self.assertEqual(r['segment_count'], 3)

    def test_gap_detection(self):
        self.assertEqual(audit(self.a)['visual_gaps_us'], [])
        self.assertEqual(audit(self.b)['visual_gaps_us'], [[5000000,5200000],[9200000,9400000]])

    def test_animation_clone_and_keyframe_diff(self):
        original = copy.deepcopy(self.b)
        p, summary = experiment(self.b)
        self.assertEqual(summary['copied_preset_name'], ['Pendulum 1'])
        self.assertTrue(summary['timeline_signature_unchanged'])
        self.assertTrue(summary['refs_valid_after'])
        self.assertEqual(audit(p)['media_counts'], audit(self.b)['media_counts'])
        self.assertEqual(audit(p)['effect_material_counts']['animations'], 2)
        self.assertEqual(self.b, original)
        self.assertEqual(p['tracks'][0]['segments'][1]['common_keyframes'][0]['property_type'],'KFTypeScaleX')
        self.assertEqual(p['tracks'][0]['segments'][1]['common_keyframes'][1]['property_type'],'KFTypeScaleY')
        self.assertEqual(len(p['tracks']),2)

    def test_invalid_ref_rejected(self):
        altered = copy.deepcopy(self.b)
        altered['tracks'][0]['segments'][1]['extra_material_refs'].append('NONEXISTENT')
        self.assertFalse(audit(altered)['valid_structure'])
        with self.assertRaises(ValueError): experiment(altered)

    def test_version_gated(self):
        altered = copy.deepcopy(self.b)
        altered['version'] = 0
        with self.assertRaises(ValueError): experiment(altered)

    def test_existing_keyframes_refused(self):
        altered = copy.deepcopy(self.b)
        altered['tracks'][0]['segments'][1]['common_keyframes'] = [{'property_type':'KFTypeRotation','keyframe_list':[]}]
        with self.assertRaises(ValueError): experiment(altered)

    def test_original_bytes_not_changed(self):
        pth=self.draft_dir / 'synthetic_two_track.json'
        before=data_hash(pth)
        experiment(self.b)
        self.assertEqual(data_hash(pth),before)

    def test_bulk_clone_synthetic_300_images(self):
        import uuid
        j=copy.deepcopy(self.b)
        j['duration']=1_200_000_000
        # start with one existing animated photo, add 299 synthetic photos
        base=j['tracks'][0]['segments'][1]
        j['tracks'][0]['segments'].remove(base)
        for i in range(1,300):
            identifier='new-photo-'+str(i)
            j['materials']['videos'].append({'id':identifier,'type':'photo','path':'C:/NONEXISTENT/photo.jpg'})
            j['tracks'][0]['segments'].append({'id':'new-segment-'+str(i),
                'material_id':identifier,'target_timerange':{'start':i*4_000_000,'duration':4_000_000},
                'source_timerange':{'start':0,'duration':4_000_000},
                'common_keyframes':[],'extra_material_refs':[], 'render_index':0})
        # Keep the separate video track (overlapping doesn't invalidate refs).
        self.assertTrue(audit(j)['valid_structure'])
        copied,stats=bulk_experiment(j)
        self.assertEqual(stats['animations_added'],299)
        self.assertEqual(stats['new_animation_material_slots'],299)
        self.assertEqual(stats['photo_count'],300)
        self.assertTrue(audit(copied)['valid_structure'])
        self.assertEqual(copied['duration'],j['duration'])
        self.assertFalse(stats['capcut_export_tested'])

    def test_bulk_rejects_max_images(self):
        with self.assertRaises(ValueError):
            bulk_experiment(self.b, max_images=1)

if __name__ == '__main__':
    unittest.main()
