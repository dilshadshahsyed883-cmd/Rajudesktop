"""Real frozen-app startup and controls test on disposable JSON-only projects."""
import json
from pathlib import Path
import sys
import tempfile
import traceback
from PySide6.QtCore import QElapsedTimer, QTimer, QStandardPaths
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication
from .app import Window
from .fixtures import create_project
from .engines import visual


def wait_idle(window):
    elapsed=QElapsedTimer();elapsed.start()
    while elapsed.elapsed()<30000:
        QApplication.processEvents();QTest.qWait(10)
        if window.worker is None and not window.pending_scan:
            QApplication.processEvents()
            if window.worker is None:return
    raise TimeoutError(window.message.text())


def run(report):
    report=Path(report).resolve();report.parent.mkdir(parents=True,exist_ok=True)
    QStandardPaths.setTestModeEnabled(True)
    app=QApplication.instance() or QApplication([])
    checks={};window=None
    try:
        with tempfile.TemporaryDirectory(prefix='capcut-controls-studio-smoke-') as td:
            root=Path(td)
            project,original,media=create_project(root,'Studio Demo')
            other,_,_=create_project(root,'Other Project')
            peer_before=(other/'draft_content.json').read_bytes()
            media_before={p:p.read_bytes() for p in media}
            window=Window(root=root,autostart=False)
            window.resize(1020,840);window.show()
            window.refresh();wait_idle(window)
            window.project_combo.setCurrentIndex(window.project_combo.findData(str(project)))
            wait_idle(window)
            checks['startup_three_tabs']=window.sections.count()==3
            checks['project_detection']=window.project_combo.count()==2 and window.snapshot.project==project
            checks['no_z_builder_dependency']=not any(k=='z_builder' or k.startswith('z_builder.') for k in sys.modules)
            t=window.transitions_tab
            t.mode.setCurrentIndex(t.mode.findData('single'))
            t.selected_ids={'Studio Demo-fade'};t.duration.setValue(.7)
            t.validate();wait_idle(window)
            checks['transition_preview']=bool(t.plan and t.plan.chosen)
            t.apply();wait_idle(window)
            checks['transition_save_backup']=bool(list((project/'.transition_only_backups').glob('*/manifest.json')))
            a=window.animations_tab
            a.mode.setCurrentIndex(a.mode.findData('single'))
            a.selected_effect_ids={'Studio Demo-combo'};a.select_all_images()
            a.validate();wait_idle(window)
            checks['image_duration_fit']=bool(a.preview_rows) and all(r.get('applied_duration_us')==r['duration_us'] for r in a.preview_rows if r.get('status')=='Will Apply')
            a.apply();wait_idle(window)
            checks['animation_save_backup']=bool(list((project/'.animations_only_backups').glob('*/manifest.json')))
            s=window.scale_tab
            s.preview();wait_idle(window)
            checks['scale_preview']=s.expected is not None
            s.apply();wait_idle(window)
            checks['scale_save_backup']=bool(list((project/'.visual_controls_backups').glob('*/manifest.json')))
            actual=visual.load_project(project)[0]
            checks['one_mixed_visual_track_preserved']=len([t for t in actual['tracks'] if t['type']=='video'])==1
            checks['audio_preserved']=actual['tracks'][1]==original['tracks'][1]
            checks['clip_timing_preserved']=[x['target_timerange'] for x in actual['tracks'][0]['segments']]==[x['target_timerange'] for x in original['tracks'][0]['segments']]
            checks['original_media_preserved']={p:p.read_bytes() for p in media}==media_before
            checks['other_project_untouched']=(other/'draft_content.json').read_bytes()==peer_before
            checks['effects_filters_untouched']=actual['materials']['effects']==original['materials']['effects'] and actual['materials']['video_effects']==original['materials']['video_effects']
            for index,name in enumerate(['Transitions','Animations','Scale']):
                window.sections.setCurrentIndex(index);wait_idle(window)
                app.processEvents()
                window.grab().save(str(report.with_name('Studio-'+name+'.png')))
            window.close();window=None
        result={'passed':all(checks.values()),'frozen':bool(getattr(sys,'frozen',False)),'checks':checks}
    except Exception as exc:
        result={'passed':False,'checks':checks,'error':str(exc),'traceback':traceback.format_exc()}
        if window:
            if window.worker:window.worker.wait(30000)
            app.processEvents();window.close()
    report.write_text(json.dumps(result,indent=2),encoding='utf8')
    return 0 if result['passed'] else 1
