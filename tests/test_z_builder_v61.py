"""V6.1 selected-project isolation, reference scale and full-duration Combo tests."""
import copy
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtWidgets import QApplication, QPushButton
from z_builder.capcut_controls_tab import CapcutControlsTab
from autocapcut_animations_only.animation_engine import harvest_animations, make_plan, apply_animation, save as save_animations
from autocapcut_transitions_only.transition_engine import harvest_transitions
from capcut_visual_controls_standalone.engine import create_preview, load_project, save_project
from z_builder.core import Catalog, load_plan, bind_media, preflight, media_usage_issues


def fixture(tag, cache):
    return {'id':tag,'duration':6000000,'canvas_config':{'width':1920,'height':1080},
      'materials':{'videos':[{'id':'p','type':'photo','material_name':'photo.jpg'},
                             {'id':'v','type':'video','material_name':'movie.mp4'}],
        'canvases':[], 'transitions':[{'id':'t','effect_id':tag+'-transition','name':tag+' Fade'}],
        'material_animations':[{'id':'a','type':'sticker_animation','animations':[
          {'id':tag+'-animation','resource_id':tag+'-animation','type':'group',
           'category_name':'Trending','name':tag+' Combo','duration':3000000,'path':str(cache)}]}]},
      'tracks':[{'type':'video','segments':[
        {'id':'s1','material_id':'p','extra_material_refs':['t','a'],
         'target_timerange':{'start':0,'duration':2500000},'source_timerange':{'start':0,'duration':2500000},
         'clip':{'scale':{'x':1,'y':1},'transform':{'x':.2,'y':0}}},
        {'id':'s2','material_id':'v','extra_material_refs':[],
         'target_timerange':{'start':2500000,'duration':3500000},'source_timerange':{'start':0,'duration':3500000},
         'clip':{'scale':{'x':1,'y':1},'transform':{'x':0,'y':0}}}]}]}


class V61Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)
        self.cache=self.root/'cache';self.cache.mkdir()
        for tag in ['A','B']:
            project=self.root/tag;project.mkdir()
            (project/'draft_content.json').write_text(json.dumps(fixture(tag,self.cache)))
        self.widget=CapcutControlsTab();self.addCleanup(self.widget.close)
        self.widget.timer.stop()
        self.widget.projects_root=self.root;self.widget.refresh()
        self.select('A')

    def select(self,name):
        w=self.widget
        w.project_combo.setCurrentIndex(w.project_combo.findData(str(self.root/name)))
        w.load_selected(force=True)

    def test_shared_selector_and_project_isolation(self):
        w=self.widget
        self.assertIs(w.transitions_tab.project_combo,w.project_combo)
        self.assertIs(w.animations_tab.project_combo,w.project_combo)
        self.assertEqual(w.sections.count(),3)
        self.assertEqual([x['effect_id'] for x in w.transitions_tab.catalog],['A-transition'])
        self.assertEqual([x['effect_id'] for x in w.animations_tab.catalog],['A-animation'])
        w.transitions_tab.selected_ids={'A-transition'}
        self.select('B')
        self.assertEqual([x['effect_id'] for x in w.transitions_tab.catalog],['B-transition'])
        self.assertEqual([x['effect_id'] for x in w.animations_tab.catalog],['B-animation'])
        self.assertEqual(w.transitions_tab.selected_ids,set())
        self.assertEqual(w.animations_tab.preview_rows,[])
        for i in [0,1,2,0]:w.sections.setCurrentIndex(i)
        self.assertEqual(w.project_combo.currentText(),'B')
        for panel in [w.transitions_tab,w.animations_tab]:
            self.assertFalse(any(b.text() in ['Refresh','Change folder'] for b in panel.findChildren(QPushButton)))

    def test_external_change_invalidates_then_refreshes_all_panels(self):
        w=self.widget;w.scale_tab.preview()
        f=self.root/'A/draft_content.json';raw=json.loads(f.read_text())
        raw['materials']['transitions']=[];raw['materials']['material_animations']=[]
        f.write_text(json.dumps(raw))
        with self.assertRaisesRegex(ValueError,'Project changed'):w.require_current()
        self.assertIsNone(w.scale_tab.expected)
        self.assertEqual(w.transitions_tab.catalog,[])
        self.assertEqual(w.animations_tab.catalog,[])
        w.refresh()
        self.assertEqual(w.project_combo.currentText(),'A')
        w.require_current()

    def test_unreferenced_transition_hidden(self):
        f=self.root/'A/draft_content.json';raw=json.loads(f.read_text())
        raw['materials']['transitions'].append({'id':'orphan','effect_id':'bad','name':'Other'})
        f.write_text(json.dumps(raw))
        self.assertEqual([e['effect_id'] for e in harvest_transitions(self.root,project=self.root/'A')],['A-transition'])

    def test_animation_fits_short_and_long_images(self):
        entries=harvest_animations(self.root,project=self.root/'A')
        for seconds in [2.5,4,6,10]:
            raw=fixture('A',self.cache);raw['tracks'][0]['segments'][0]['target_timerange']['duration']=int(seconds*1e6)
            rows,_=make_plan(raw,entries,[(0,0)],'A-animation',fit_to_clip=True)
            updated,_=apply_animation(raw,entries,'A-animation',rows)
            mat=updated['materials']['material_animations'][-1]
            self.assertEqual(mat['animations'][0]['duration'],int(seconds*1e6))
            self.assertEqual(updated['tracks'][0]['segments'][0]['target_timerange'],raw['tracks'][0]['segments'][0]['target_timerange'])
            self.assertEqual(updated['tracks'][0]['segments'][1],raw['tracks'][0]['segments'][1])
            project=self.root/('duration_'+str(seconds));project.mkdir()
            (project/'draft_content.json').write_text(json.dumps(raw))
            result=save_animations(project,entries,'A-animation',rows)
            self.assertTrue(result['saved'])
            saved=json.loads((project/'draft_content.json').read_text())
            self.assertEqual(saved['materials']['material_animations'][-1]['animations'][0]['duration'],int(seconds*1e6))

    def test_scale_reference_defaults_determinism_and_project_save(self):
        panel=self.widget.scale_tab;opts=panel.options()
        self.assertEqual((opts.video_scale_min,opts.video_scale_max,opts.video_y_min,opts.video_y_max),(150,170,-250,-190))
        self.assertEqual((opts.blur_strength,opts.seed,opts.extend_filters,opts.extend_effects),(.75,28,False,False))
        raw=fixture('A',self.cache);first,_,_=create_preview(raw,opts);second,_,_=create_preview(raw,opts)
        # UUID canvas IDs may differ; native transforms must be repeatable.
        for a,b in zip(first['tracks'][0]['segments'],second['tracks'][0]['segments']):self.assertEqual(a['clip'],b['clip'])
        photo,video=first['tracks'][0]['segments']
        self.assertTrue(1.5<=video['clip']['scale']['x']<=1.7)
        self.assertTrue(-250<=video['clip']['transform']['y']*540<=-190)
        self.assertEqual(photo['clip']['transform']['x'],.2)
        self.assertEqual(first['materials']['material_animations'],raw['materials']['material_animations'])
        before=(self.root/'B/draft_content.json').read_bytes()
        self.assertTrue(panel.preview());expected=panel.expected
        result=save_project(self.root/'A',opts,expected)
        self.assertTrue(result['saved']);self.assertTrue(Path(result['backup']).is_dir())
        self.assertEqual((self.root/'B/draft_content.json').read_bytes(),before)
        self.assertEqual(load_project(self.root/'A')[0]['tracks'][0]['segments'][1]['target_timerange'],raw['tracks'][0]['segments'][1]['target_timerange'])

    def test_failed_multifile_scale_save_restores_originals(self):
        import capcut_visual_controls_standalone.engine as engine
        project=self.root/'A'
        mirror=project/'Timelines'/'active';mirror.mkdir(parents=True)
        top=project/'draft_content.json'
        active=mirror/'draft_content.json';active.write_bytes(top.read_bytes())
        (project/'Timelines'/'project.json').write_text(json.dumps({'main_timeline_id':'active'}))
        originals={p:p.read_bytes() for p in [top,active]}
        actual_atomic=engine._atomic
        calls=[]
        def fail_once(path,data):
            calls.append(path)
            if len(calls)==2:raise OSError('simulated second-file write failure')
            actual_atomic(path,data)
        with patch.object(engine,'_atomic',side_effect=fail_once):
            with self.assertRaisesRegex(OSError,'simulated'):
                save_project(project,self.widget.scale_tab.options())
        self.assertEqual({p:p.read_bytes() for p in originals},originals)
        self.assertFalse((project/'.visual_controls_test.lock').exists())
        self.assertTrue(list((project/'.visual_controls_backups').glob('*/manifest.json')))

    def test_input_has_media_summary_without_capcut_summary(self):
        from z_builder.ui import Window
        win=Window();self.addCleanup(win.close)
        labels=[b.text() for b in win.tabs.widget(0).findChildren(QPushButton)]
        self.assertIn('Download Media Summary',labels)
        self.assertFalse(any('CapCut' in x and 'Summary' in x for x in labels))

    def test_media_usage_and_sequence_rules(self):
        root=self.root
        for name in ['tennis old.jpg','tennis fresh.jpg','movie.mp4']:(root/name).write_bytes(b'x')
        c=Catalog(root/'catalog.db')
        c.add(root/'tennis old.jpg');c.add(root/'tennis fresh.jpg');c.add(root/'movie.mp4')
        c.record_successful_export([str(root/'tennis old.jpg'),str(root/'movie.mp4')])
        p=load_plan('00:00 --> 00:03 | image | keyword: tennis')
        self.assertEqual(bind_media(p,c.assets()),[])
        self.assertEqual(Path(p.shots[0].assigned_path).name,'tennis fresh.jpg')
        p=load_plan('00:00 --> 00:03 | video | movie.mp4')
        self.assertTrue(bind_media(p,c.assets()))
        p.shots[0].assigned_path=str(root/'movie.mp4')
        self.assertTrue(media_usage_issues(p,c.assets()))
        p=load_plan('00:00 --> 00:02 | video | movie.mp4\n00:02 --> 00:04 | video | other.mp4')
        self.assertTrue(any('consecutive videos' in x for x in preflight(p)))
