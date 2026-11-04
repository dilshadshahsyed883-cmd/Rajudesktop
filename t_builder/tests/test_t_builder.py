import base64
import json
import os
from pathlib import Path
import random
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from t_builder.timeline import keyword,rebalance,plan_timeline,FeasibilityError,validate_timeline
from t_builder.catalog import Catalog
from t_builder.generation import generate,write_native,verify_native


def assets(n=100):
    return [{'path':f'/media/{k} {i}.{ext}','kind':kind,'exists':True,'duration':4}
            for kind,ext in [('image','jpg'),('video','mp4')] for k in ['Alexa','Emma'] for i in range(n)]

class TimelineTests(unittest.TestCase):
    def test_keyword_sequences(self):
        for value in ['Alexa 1.jpg','Alexa_2.png','Alexa-12.mp4']:
            self.assertEqual(keyword(value),'Alexa')
        self.assertEqual(keyword('New York Family_33.jpg'),'New York Family')
        self.assertEqual(keyword('Formula1.jpg'),'Formula1')
    def test_strength_rebalance_exact(self):
        w={}
        rng=random.Random(4)
        for k in 'ABCDE':
            w[k]=20;w=rebalance(w);self.assertEqual(sum(w.values()),100)
        for i in range(1000):
            k=rng.choice(list(w));v=rng.randrange(101);w=rebalance(w,k,v)
            self.assertEqual(w[k],v);self.assertEqual(sum(w.values()),100)
        w.pop('A');w=rebalance(w);self.assertEqual(sum(w.values()),100)
        self.assertEqual(rebalance({'A':5}),{'A':100});self.assertEqual(rebalance({}),{})
        self.assertEqual(rebalance({'a':50,'b':30,'c':20},'a',60),{'a':60,'b':24,'c':16})
    def test_unchecked_and_bad_totals_blocked(self):
        for w in ({},{'Alexa':99},{'Alexa':101},{'Alexa':-10,'Emma':110}):
            with self.assertRaises(FeasibilityError):plan_timeline(assets(),60,w)
    def test_images_fill_exact_endpoint_and_random(self):
        t=plan_timeline(assets(),60.123456,{'Alexa':50,'Emma':50},seed=4)
        self.assertEqual(t.duration,60_123_456);self.assertEqual(t.images[-1].end,t.duration)
        validate_timeline(t)
        self.assertGreater(len(set(c.duration for c in t.images)),3)
        nums=[int(Path(c.path).stem.split()[-1]) for c in t.images]
        self.assertNotEqual(nums,sorted(nums));self.assertEqual(len(nums),len(set(c.path for c in t.images)))
    def test_strength_distribution(self):
        t=plan_timeline(assets(1000),3600,{'Alexa':70,'Emma':30},seed=4)
        ratio=sum(c.keyword=='Alexa' for c in t.images)/len(t.images)
        self.assertAlmostEqual(ratio,.7,delta=.05)
    def test_video_coverage_alternation_no_reuse_and_gaps(self):
        for seed in range(20):
            t=plan_timeline(assets(),120,{'Alexa':50,'Emma':50},{'Alexa':70,'Emma':30},20,seed)
            validate_timeline(t);self.assertEqual(sum(c.duration for c in t.videos),24_000_000)
            self.assertEqual(len({c.path for c in t.videos}),len(t.videos))
            for a,b in zip(t.videos,t.videos[1:]):
                self.assertNotEqual(a.keyword,b.keyword);self.assertGreater(b.start,a.end)
                self.assertTrue(any(im.start>=a.end and im.end<=b.start for im in t.images))
    def test_video_duration_limits_and_source_trims(self):
        a=assets()
        for x in a:
            if x['kind']=='video':x['duration']=2.7
        t=plan_timeline(a,60,{'Alexa':100},{'Alexa':50,'Emma':50},21.6666666667,1)
        self.assertTrue(all(c.duration+c.trim<=2_700_000 for c in t.videos))
    def test_independent_image_video_keyword_selection(self):
        t=plan_timeline(assets(),60,{'Alexa':100},{'Emma':100},5,1)
        self.assertEqual({c.keyword for c in t.images},{'Alexa'})
        self.assertEqual({c.keyword for c in t.videos},{'Emma'})
    def test_one_video_keyword_warns(self):
        with self.assertRaisesRegex(FeasibilityError,'two video keywords'):
            plan_timeline(assets(),120,{'Alexa':100},{'Alexa':100},20)
    def test_infeasible_coverage_and_short_clips(self):
        for coverage in [100,.1]:
            with self.assertRaises(FeasibilityError):plan_timeline(assets(),60,{'Alexa':100},{'Alexa':50,'Emma':50},coverage)
        a=assets()
        for x in a:x['duration']=2
        with self.assertRaises(FeasibilityError):plan_timeline(a,60,{'Alexa':100},{'Alexa':50,'Emma':50},20)
    def test_zero_and_disabled_video_selection(self):
        for weights,cov in [(None,20),({},0)]:
            self.assertFalse(plan_timeline(assets(),60,{'Alexa':100},weights,cov).videos)
    def test_used_files_excluded(self):
        a=[{'path':'/media/used/Alexa 1.jpg','kind':'image'}]
        with self.assertRaises(FeasibilityError):plan_timeline(a,60,{'Alexa':100})
    def test_sparse_image_reuse(self):
        a=[{'path':'/media/Alexa 1.jpg','kind':'image'}]
        t=plan_timeline(a,60,{'Alexa':100});validate_timeline(t)

class FilesTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name);self.media=self.root/'media';self.media.mkdir();self.drafts=self.root/'drafts';self.drafts.mkdir()
        self.catalog=Catalog(self.root/'app'/'lib.sqlite');self.catalog.add_root(self.media)
        self.image=self.media/'Alexa 1.png'
        self.image.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a+4sAAAAASUVORK5CYII='))
        self.catalog.add(self.image)
        self.audio=self.root/'voice.wav';self.audio.write_bytes(b'audio fixture')
    def timeline(self):return plan_timeline(self.catalog.assets(),10,{'Alexa':100},seed=3)
    def test_recursive_import_summary_and_tags(self):
        nested=self.media/'nested';nested.mkdir();(nested/'Emma_2.jpg').write_bytes(b'x')
        n,errors=self.catalog.add_folder(self.media);self.assertEqual(n,2);self.assertFalse(errors)
        a=self.catalog.assets()[0];self.catalog.update_tags(a['id'],'family');self.assertIn('family',self.catalog.summary())
        self.assertIn('keyword=Emma',self.catalog.summary())
    def test_moves_selected_only_and_updates_catalog(self):
        other=self.media/'unused.jpg';other.write_bytes(b'x');self.catalog.add(other)
        t=self.timeline();self.catalog.move_selected(t)
        self.assertFalse(self.image.exists());self.assertTrue(other.exists())
        self.assertTrue(all(Path(c.path).parent.name=='used' for c in t.images))
        a=next(a for a in self.catalog.assets() if a['filename']==self.image.name)
        self.assertTrue(a['used']);self.assertEqual(a['export_count'],1);self.assertIn('USED',self.catalog.summary())
    def test_move_collision_never_overwrites(self):
        (self.media/'used').mkdir();dest=self.media/'used'/self.image.name;dest.write_bytes(b'existing')
        with self.assertRaises(FileExistsError):self.catalog.move_selected(self.timeline())
        self.assertTrue(self.image.exists());self.assertEqual(dest.read_bytes(),b'existing')
    def test_failure_leaves_moves_and_honest_report(self):
        with patch('t_builder.generation.write_native',side_effect=ValueError('writer failure')):
            with self.assertRaisesRegex(RuntimeError,'Generation incomplete'):
                generate(self.catalog,(self.timeline(),str(self.audio),self.drafts,'Failed'),False)
        self.assertFalse(self.image.exists());self.assertTrue((self.media/'used'/self.image.name).exists())
        report=json.loads((self.catalog.db_path.parent/'last_generation.json').read_text())
        self.assertEqual(report['status'],'incomplete');self.assertTrue(report['moved_files_still_in_used'])
    def test_cleanup_requires_confirmation_and_protects_references(self):
        self.catalog.move_selected(self.timeline());used=self.media/'used'/self.image.name
        unrelated=self.media/'used'/'unrelated.jpg';unrelated.write_bytes(b'x')
        candidates,protected=self.catalog.cleanup_candidates(self.media,[self.drafts]);self.assertEqual(candidates,[str(used)])
        with self.assertRaisesRegex(ValueError,'confirmation'):self.catalog.cleanup(self.media,candidates,[self.drafts])
        p=self.drafts/'Existing';p.mkdir();(p/'draft_content.json').write_text(json.dumps({'materials':{'videos':[{'path':str(used)}]}}))
        candidates,protected=self.catalog.cleanup_candidates(self.media,[self.drafts]);self.assertEqual(protected,[str(used)]);self.assertFalse(candidates)
        with self.assertRaises(ValueError):self.catalog.cleanup(self.media,[str(used)],[self.drafts],True)
        self.assertTrue(used.exists());self.assertTrue(unrelated.exists())
    def test_cleanup_boundary_malformed_and_deleted_projects(self):
        self.catalog.move_selected(self.timeline());used=self.media/'used'/self.image.name
        p=self.drafts/'draft_content.json';p.write_text('encrypted')
        with self.assertRaisesRegex(ValueError,'blocked'):self.catalog.cleanup_candidates(self.media,[self.drafts])
        p.unlink()
        with patch('send2trash.send2trash',side_effect=lambda p:Path(p).unlink()) as recycle:
            self.assertEqual(self.catalog.cleanup(self.media,[str(used)],[self.drafts],True),1)
            recycle.assert_called_once()
        with self.assertRaises(ValueError):self.catalog.cleanup_candidates(self.root,[self.drafts])
    def test_native_editable_draft_moved_path_and_audio(self):
        t=self.timeline();self.catalog.move_selected(t)
        result=write_native(t,str(self.audio),self.drafts,'Native Test',False)
        raw=verify_native(Path(result['folder']),t,str(self.audio))
        self.assertEqual([tr['type'] for tr in raw['tracks']],['video','audio'])
        self.assertTrue(all('/used/' in m['path'] for m in raw['materials']['videos']))
        candidates,protected=self.catalog.cleanup_candidates(self.media,[self.drafts]);self.assertFalse(candidates);self.assertTrue(protected)

class QtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app=QApplication.instance() or QApplication([])
    def test_strength_checkbox_and_sliders(self):
        from t_builder.ui import Strengths
        w=Strengths();w.rebuild({'Alexa':50,'Emma':30,'Family':20})
        for k in w.rows:w.rows[k][0].setChecked(True)
        w.rows['Alexa'][1].setValue(70);self.assertEqual(w.weights['Alexa'],70);self.assertEqual(sum(w.weights.values()),100)
        w.rows['Emma'][0].setChecked(False);self.assertNotIn('Emma',w.weights)
        self.assertEqual(w.rows['Emma'][1].value(),0);self.assertEqual(sum(w.weights.values()),100)
        for k in w.rows:w.rows[k][0].setChecked(False)
        self.assertEqual(w.weights,{})
        w.close()
    def test_independent_ui_and_canonical_controls(self):
        from t_builder.ui import Window
        with tempfile.TemporaryDirectory() as d,patch('t_builder.capcut_controls_tab.list_projects',return_value=[]):
            w=Window(d);w.capcut_controls_tab.timer.stop()
            self.assertEqual([w.tabs.tabText(i) for i in range(w.tabs.count())],['Media Library','Timeline Builder','CapCut Controls'])
            self.assertEqual(w.steps.count(),3);self.assertFalse(w.video_enabled.isChecked());self.assertFalse(w.cleanup_check.isChecked())
            ctl=w.capcut_controls_tab
            self.assertEqual([ctl.sections.tabText(i) for i in range(ctl.sections.count())],['Transitions','Scale'])
            self.assertEqual(ctl.settings.applicationName(),'T Builder Capcut Controls')
            self.assertEqual(ctl.transitions_tab.settings.applicationName(),'T Builder Capcut Transitions')
            self.assertTrue(w.catalog.db_path.is_relative_to(d));w.close()
    def test_canonical_controls_copied_without_feature_changes(self):
        root=Path(__file__).resolve().parents[2]
        for file in ('scale_tab.py','transitions_tab.py','capcut_controls_tab.py'):
            self.assertEqual((root/'z_builder'/file).read_text().replace('Z Builder','T Builder'),(root/'t_builder'/file).read_text())

if __name__=='__main__':unittest.main()
