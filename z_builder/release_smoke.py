"""Isolated frozen executable smoke test; never reads or writes user projects."""
import json
import base64
from pathlib import Path
import tempfile
from PySide6.QtCore import QStandardPaths
from PySide6.QtWidgets import QApplication


def run(report):
    from .core import Catalog, bind_media, load_plan
    from .capcut import export_capcut, find_node
    from .ui import Window
    from capcut_visual_controls_standalone.engine import save_project
    QStandardPaths.setTestModeEnabled(True)
    app=QApplication.instance() or QApplication([])
    checks={}
    with tempfile.TemporaryDirectory(prefix='zbuilder-v63-smoke-') as td:
        root=Path(td)
        # Block accidental enumeration of real project folders during startup.
        from unittest.mock import patch
        with patch('z_builder.capcut_controls_tab.list_projects',return_value=[]):
            win=Window()
        win.capcut_controls_tab.timer.stop()
        win.resize(1280,800)
        win.show();app.processEvents()
        checks['four_main_tabs']=win.tabs.count()==4
        checks['two_controls_tabs']=[win.capcut_controls_tab.sections.tabText(i) for i in range(win.capcut_controls_tab.sections.count())]==['Transitions','Scale']
        checks['bundled_node']=bool(find_node())
        media=root/'image.png'
        media.write_bytes(base64.b64decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+a+4sAAAAASUVORK5CYII='))
        video=root/'clip.mp4'
        video.write_bytes(b'writer smoke placeholder')
        c=Catalog(root/'lib.sqlite');c.add(media);c.add(video)
        p=load_plan('name=V63 Smoke\n00:00 --> 00:04 | image | image.png\n00:04 --> 00:06.500 | video | clip.mp4')
        assert not bind_media(p,c.assets())
        out=export_capcut(p,str(root/'drafts'),False,False,mode='complete')
        project=Path(out['parts'][0]['folder'])
        raw=json.loads((project/'draft_content.json').read_text())
        checks['native_complete_export']=[t['name'] for t in raw['tracks'] if t['type']=='video']==['Images - Lower Layer','Videos - Upper Layer']
        ctl=win.capcut_controls_tab
        ctl.projects_root=project.parent;ctl.refresh()
        checks['shared_project']=ctl.selected_project()==project
        checks['animation_ui_absent']=not hasattr(ctl,'animations_tab') and not hasattr(win,'animations_tab')
        checks['scale_preview']=ctl.scale_tab.preview()
        result=save_project(project,ctl.scale_tab.options(),ctl.scale_tab.expected)
        checks['guarded_scale_save']=result['saved'] and Path(result['backup']).is_dir()
        after=json.loads((project/'draft_content.json').read_text())
        checks['timing_preserved']=after['duration']==raw['duration']
        win.tabs.setCurrentIndex(3);ctl.sections.setCurrentIndex(1);app.processEvents()
        win.grab().save(str(Path(report).with_suffix('.png')))
        win.close()
    Path(report).write_text(json.dumps({'passed':all(checks.values()),'checks':checks},indent=2))
    return 0 if all(checks.values()) else 1
