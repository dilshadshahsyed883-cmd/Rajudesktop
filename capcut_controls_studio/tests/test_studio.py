import ast
import copy
import json
import os
from pathlib import Path
import tempfile
import time
import unittest
from unittest.mock import patch
os.environ.setdefault('QT_QPA_PLATFORM','offscreen')
from PySide6.QtCore import QElapsedTimer,QTimer,QCoreApplication,QEvent
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication,QPushButton
from capcut_controls_studio import backend
from capcut_controls_studio.app import Window
from capcut_controls_studio.fixtures import create_project
from capcut_controls_studio.engines import animations,transitions,visual


def wait_idle(window, timeout=30000):
    elapsed=QElapsedTimer();elapsed.start()
    while elapsed.elapsed()<timeout:
        QApplication.processEvents()
        QTest.qWait(10)
        if window.worker is None and not window.pending_scan:
            QApplication.processEvents()
            if window.worker is None:return
    raise AssertionError('Background operation timed out: '+window.message.text())


class NativeTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.project,self.raw,self.media=create_project(self.root,'A')
        self.other,_,_=create_project(self.root,'B')
        self.snapshot=backend.load_snapshot(self.project)

    def test_only_selected_project_resources_and_snapshot_cache(self):
        self.assertEqual([e['effect_id'] for e in self.snapshot.transitions],['A-fade'])
        self.assertEqual([e['effect_id'] for e in self.snapshot.animations],['A-combo'])
        projects,again,_=backend.scan(self.root,self.project,self.snapshot)
        self.assertIs(again,self.snapshot)
        b=backend.load_snapshot(self.other)
        self.assertEqual([e['effect_id'] for e in b.transitions],['B-fade'])

    def test_native_transition_apply_preserves_audio_media_timing_and_layers(self):
        before_other=(self.other/'draft_content.json').read_bytes()
        media_before={p:p.read_bytes() for p in self.media}
        plan=backend.preview_transitions(self.snapshot,'single',['A-fade'],.7,None)
        result=backend.apply_transitions(self.snapshot,plan)
        self.assertTrue(result['saved'])
        self.assertTrue((Path(result['backup_dir'])/'manifest.json').exists())
        after=visual.load_project(self.project)[0]
        self.assertEqual(transitions.immutable_snapshot(self.raw),transitions.immutable_snapshot(after))
        self.assertEqual(after['tracks'][1],self.raw['tracks'][1])
        self.assertEqual((self.other/'draft_content.json').read_bytes(),before_other)
        self.assertEqual({p:p.read_bytes() for p in self.media},media_before)
        self.assertEqual(json.loads((self.project/'draft_content.json').read_text()),json.loads((self.project/'Timelines/active/draft_content.json').read_text()))

    def test_animations_fit_2_5_4_6_10_seconds_and_preserve_video(self):
        for duration in [2.5,4,6,10]:
            raw=copy.deepcopy(self.raw)
            raw['tracks'][0]['segments'][0]['target_timerange']['duration']=int(duration*1e6)
            rows,_=animations.make_plan(raw,self.snapshot.animations,[(0,0)],'A-combo',fit_to_clip=True)
            after,_=animations.apply_animation(raw,self.snapshot.animations,'A-combo',rows)
            self.assertEqual(after['materials']['material_animations'][-1]['animations'][0]['duration'],int(duration*1e6))
            self.assertEqual(after['tracks'][0]['segments'][1],raw['tracks'][0]['segments'][1])
        result=backend.preview_animations(self.snapshot,[(0,0),(0,2)],'single',{'A-combo'},28)
        saved=backend.apply_animations(self.snapshot,result)
        self.assertTrue(saved['saved'])
        self.assertEqual(visual.load_project(self.project)[0]['tracks'][1],self.raw['tracks'][1])

    def test_scale_defaults_repeatable_seed_keyframes_and_exclusions(self):
        opts=visual.Options(video_scale_min=150,video_scale_max=170,video_y_min=-250,video_y_max=-190,blur_strength=.75)
        one,_,_=backend.preview_scale(self.snapshot,opts)
        two,_,_=backend.preview_scale(self.snapshot,opts)
        for a,b in zip(one['tracks'][0]['segments'],two['tracks'][0]['segments']):self.assertEqual(a['clip'],b['clip'])
        video=one['tracks'][0]['segments'][1]
        self.assertTrue(1.5<=video['clip']['scale']['x']<=1.7)
        self.assertTrue(-250<=video['clip']['transform']['y']*540<=-190)
        self.assertEqual(one['materials']['effects'],self.raw['materials']['effects'])
        self.assertEqual(one['materials']['video_effects'],self.raw['materials']['video_effects'])
        self.assertEqual(one['materials']['material_animations'],self.raw['materials']['material_animations'])
        raw=copy.deepcopy(self.raw);raw['tracks'][0]['segments'][1]['common_keyframes']=[{'property_type':'KFTypeScaleX','keyframe_list':[{'values':[1]},{'values':[1.2]}]}]
        keyed,_,counts=visual.create_preview(raw,opts)
        self.assertEqual(keyed['tracks'][0]['segments'][1]['clip'],raw['tracks'][0]['segments'][1]['clip'])
        self.assertEqual(counts['animated_skipped'],1)
        self.assertFalse(hasattr(opts,'extend_filters'))

    def test_stale_preview_and_invalid_choices_never_write(self):
        before=(self.project/'draft_content.json').read_bytes()
        with self.assertRaises(ValueError):backend.preview_transitions(self.snapshot,'single',['wrong'],.5,None)
        raw=copy.deepcopy(self.raw);raw['duration']+=1
        (self.project/'draft_content.json').write_text(json.dumps(raw))
        changed=(self.project/'draft_content.json').read_bytes()
        with self.assertRaisesRegex(ValueError,'Project changed'):backend.apply_scale(self.snapshot,visual.Options())
        self.assertEqual((self.project/'draft_content.json').read_bytes(),changed)
        self.assertFalse((self.project/'.capcut_controls_studio.lock').exists())

    def test_multi_file_rollback_and_automatic_backup(self):
        originals={p:p.read_bytes() for p in [self.project/'draft_content.json',self.project/'Timelines/active/draft_content.json']}
        atomic=visual._atomic;calls=[]
        def fail_once(path,data):
            calls.append(path)
            if len(calls)==2:raise OSError('simulated atomic write failure')
            atomic(path,data)
        with patch.object(visual,'_atomic',side_effect=fail_once):
            with self.assertRaises(OSError):backend.apply_scale(self.snapshot,visual.Options())
        self.assertEqual({p:p.read_bytes() for p in originals},originals)
        self.assertTrue(list((self.project/'.visual_controls_backups').glob('*/manifest.json')))
        self.assertFalse((self.project/'.capcut_controls_studio.lock').exists())

    def test_one_write_lane_blocks_other_operation(self):
        with backend.operation_lock(self.project):
            with self.assertRaises(FileExistsError):backend.apply_scale(self.snapshot,visual.Options())
        self.assertFalse((self.project/'.capcut_controls_studio.lock').exists())

    def test_capcut_open_blocks_writes(self):
        before=(self.project/'draft_content.json').read_bytes()
        with patch.object(visual,'capcut_running',return_value=True):
            with self.assertRaises(RuntimeError):backend.apply_scale(self.snapshot,visual.Options())
        self.assertEqual((self.project/'draft_content.json').read_bytes(),before)

    def test_engine_extraction_hashes_match_v61(self):
        import hashlib
        base=Path(__file__).parents[1]
        record=json.loads((base/'EXTRACTION.json').read_text())
        for row in record['files']:
            if row['adaptation']=='unchanged engine':
                self.assertEqual(hashlib.sha256((base/row['extracted']).read_bytes()).hexdigest(),row['source_sha256'])

    def test_scale_transform_results_match_original_v21_engine(self):
        from capcut_visual_controls_standalone import engine as reference
        values=dict(video_scale_min=150,video_scale_max=170,video_y_min=-250,video_y_max=-190,blur_strength=.75,seed=28)
        standalone,_,_=visual.create_preview(self.raw,visual.Options(**values))
        original,_,_=reference.create_preview(self.raw,reference.Options(**values,extend_filters=False,extend_effects=False))
        for actual,expected in zip(standalone['tracks'][0]['segments'],original['tracks'][0]['segments']):
            self.assertEqual(actual['clip'],expected['clip'])
            self.assertEqual(actual['target_timerange'],expected['target_timerange'])
        self.assertEqual(standalone['materials']['material_animations'],original['materials']['material_animations'])

    def test_no_z_builder_or_effect_filter_module_dependencies(self):
        base=Path(__file__).parents[1]
        for p in base.rglob('*.py'):
            if 'tests' in p.parts:continue
            tree=ast.parse(p.read_text())
            imports=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
            self.assertFalse(any(x.startswith(('z_builder','autocapcut_','capcut_visual_controls_standalone')) or 'fx_duration' in x for x in imports),p)


class WindowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):cls.app=QApplication.instance() or QApplication([])

    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.addCleanup(self.temp.cleanup)
        self.root=Path(self.temp.name)
        self.a,_,_=create_project(self.root,'A');self.b,_,_=create_project(self.root,'B')
        self.w=Window(root=self.root,autostart=False)
        self.addCleanup(self.cleanup)
        self.w.refresh();wait_idle(self.w)
        self.select(self.a)

    def cleanup(self):
        wait_idle(self.w);self.w.close();self.w.deleteLater()
        QCoreApplication.sendPostedEvents(None,QEvent.Type.DeferredDelete)

    def select(self,project):
        self.w.project_combo.setCurrentIndex(self.w.project_combo.findData(str(project)))
        wait_idle(self.w)

    def test_shared_controls_sync_no_extra_refresh_or_filters(self):
        w=self.w
        self.assertEqual([w.sections.tabText(i) for i in range(w.sections.count())],['Transitions','Animations','Scale'])
        self.assertIs(w.transitions_tab.project_combo,w.project_combo)
        self.assertIs(w.animations_tab.project_combo,w.project_combo)
        self.assertEqual(sum(b.text().endswith('Refresh') for b in w.findChildren(QPushButton)),1)
        w.transitions_tab.selected_ids={'A-fade'}
        self.select(self.b)
        self.assertEqual(w.transitions_tab.selected_ids,set())
        self.assertEqual([e['effect_id'] for e in w.animations_tab.catalog],['B-combo'])
        snap=w.snapshot
        for i in [1,2,0]:w.sections.setCurrentIndex(i);wait_idle(w)
        self.assertIs(w.snapshot,snap)
        self.assertEqual(w.scale_tab.options().video_scale_min,150)

    def test_background_work_keeps_event_loop_responsive(self):
        ticks=[];timer=QTimer();timer.setInterval(10);timer.timeout.connect(lambda:ticks.append(1));timer.start()
        self.w.run_job('Slow fixture',lambda:time.sleep(.18),lambda _:None)
        wait_idle(self.w);timer.stop()
        self.assertGreaterEqual(len(ticks),5)

    def test_background_failure_shows_inline_error_and_recovers(self):
        def fail():raise ValueError('fixture failure')
        self.w.run_job('Failing fixture',fail,lambda _:None)
        wait_idle(self.w)
        self.assertIn('fixture failure',self.w.message.text())
        self.assertTrue(self.w.project_combo.isEnabled())

    def test_scale_preview_and_apply_in_background_with_backup(self):
        panel=self.w.scale_tab;panel.preview();wait_idle(self.w)
        self.assertIsNotNone(panel.expected)
        panel.apply();wait_idle(self.w)
        self.assertIsNotNone(self.w.snapshot)
        self.assertTrue(list((self.a/'.visual_controls_backups').glob('*/manifest.json')))
        self.assertIsNone(panel.expected)

    def test_transition_and_animation_panels_execute_real_native_operations(self):
        w=self.w;t=w.transitions_tab
        t.mode.setCurrentIndex(t.mode.findData('single'));t.selected_ids={'A-fade'};t.duration.setValue(.7)
        t.validate();wait_idle(w);self.assertTrue(t.plan.chosen)
        t.apply();wait_idle(w)
        a=w.animations_tab;a.mode.setCurrentIndex(a.mode.findData('single'));a.selected_effect_ids={'A-combo'};a.select_all_images()
        a.validate();wait_idle(w);self.assertTrue(a.preview_rows)
        a.apply();wait_idle(w)
        self.assertTrue(list((self.a/'.transition_only_backups').glob('*/manifest.json')))
        self.assertTrue(list((self.a/'.animations_only_backups').glob('*/manifest.json')))

    def test_repeated_worker_lifecycle_and_clean_close(self):
        completed=[]
        for i in range(20):
            self.w.run_job('Worker lifecycle',lambda value=i:value,completed.append)
            wait_idle(self.w)
        self.assertEqual(completed,list(range(20)))

    def test_external_changes_reload_and_clear_previews(self):
        w=self.w;w.scale_tab.preview();wait_idle(w)
        self.assertIsNotNone(w.scale_tab.expected)
        paths=[self.a/'draft_content.json',self.a/'Timelines/active/draft_content.json']
        for f in paths:
            raw=json.loads(f.read_text());raw['materials']['transitions']=[];f.write_text(json.dumps(raw))
        w.check_external();wait_idle(w)
        self.assertEqual(w.transitions_tab.catalog,[])
        self.assertIsNone(w.scale_tab.expected)

if __name__=='__main__':unittest.main()
