"""Frozen EXE acceptance with real synthetic media, isolated settings and drafts."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import wave
from unittest.mock import patch


def run(report):
    checks={};error=''
    try:
        from PySide6.QtCore import QSettings, QStandardPaths
        from PySide6.QtWidgets import QApplication
        from .ui import Window
        from .catalog import Catalog
        from .generation import prepare,generate,verify_native
        from .generation import find_node
        from capcut_visual_controls_standalone.engine import save_project
        import imageio_ffmpeg
        QStandardPaths.setTestModeEnabled(True)
        app=QApplication.instance() or QApplication([])
        app.setOrganizationName('Rajudesktop');app.setApplicationName('T Builder Smoke')
        with tempfile.TemporaryDirectory(prefix='t-builder-smoke-') as td:
            root=Path(td);media=root/'media';media.mkdir();drafts=root/'drafts';drafts.mkdir()
            QSettings.setDefaultFormat(QSettings.Format.IniFormat)
            QSettings.setPath(QSettings.Format.IniFormat,QSettings.Scope.UserScope,str(root/'settings'))
            ffmpeg=imageio_ffmpeg.get_ffmpeg_exe()
            flags=subprocess.CREATE_NO_WINDOW if os.name=='nt' else 0
            def ff(args):
                subprocess.run([ffmpeg,'-hide_banner','-loglevel','error','-y',*args],check=True,capture_output=True,creationflags=flags,timeout=60)
            for key,color in [('Alexa','blue'),('Emma','red')]:
                for i in range(4):
                    ff(['-f','lavfi','-i',f'color=c={color}:s=64x64','-frames:v','1',str(media/f'{key} {i}.png')])
                for i in range(2):
                    ff(['-f','lavfi','-i',f'color=c={color}:s=64x64:r=30','-t','4','-c:v','libx264','-pix_fmt','yuv420p',str(media/f'{key} {i}.mp4')])
            voice=root/'voice.wav'
            with wave.open(str(voice),'wb') as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(16000);wav.writeframes(b'\0\0'*(16000*30))
            with patch('t_builder.capcut_controls_tab.list_projects',return_value=[]):win=Window(root/'app')
            win.capcut_controls_tab.timer.stop();win.refresh_timer.stop()
            checks['three_main_tabs']=win.tabs.count()==3
            checks['three_timeline_subtabs']=win.steps.count()==3
            checks['canonical_controls']=win.capcut_controls_tab.sections.count()==2
            import sys
            checks['bundled_node']=bool(find_node()) and (not getattr(sys,'frozen',False) or Path(find_node()).resolve().is_relative_to(Path(sys._MEIPASS).resolve()))
            checks['bundled_ffmpeg']=Path(ffmpeg).is_file()
            catalog=win.catalog;count,errors=catalog.add_folder(media)
            checks['recursive_import']=count==12 and not errors
            win.refresh_library();win.media_table.selectRow(0);win.select_library()
            checks['image_preview']=not win.image.pixmap().isNull()
            video_row=next(i for i,a in enumerate(win.visible_assets) if a['kind']=='video')
            win.media_table.selectRow(video_row);win.select_library()
            checks['video_preview_source']=win.player.source().isLocalFile();win.player.stop();win.player.setSource(__import__('PySide6.QtCore',fromlist=['QUrl']).QUrl())
            checks['summary']='keyword=Alexa' in catalog.summary()
            prepared=prepare(catalog,str(media),str(voice),{'Alexa':60,'Emma':40},{'Alexa':50,'Emma':50},20,'T Builder Smoke',str(drafts),seed=4)
            out=generate(catalog,prepared,False)
            t=prepared[0];project=Path(out['folder']);raw=verify_native(project,t,str(voice))
            checks['native_editable_three_tracks']=[tr['type'] for tr in raw['tracks']]==['video','video','audio']
            checks['coverage_exact']=sum(c.duration for c in t.videos)==6_000_000
            checks['moved_paths']=all(Path(c.path).parent.name=='used' for c in t.images+t.videos)
            checks['cleanup_off_preserves_used']=all(Path(c.path).exists() for c in t.images+t.videos)
            eligible,protected=catalog.cleanup_candidates(media,[drafts]);checks['reference_protection']=not eligible and bool(protected)
            ctl=win.capcut_controls_tab;ctl.projects_root=drafts;ctl.refresh()
            checks['scale_preview']=ctl.scale_tab.preview()
            saved=save_project(project,ctl.scale_tab.options(),ctl.scale_tab.expected)
            checks['scale_backup']=saved['saved'] and Path(saved['backup']).is_dir()
            after=json.loads((project/'draft_content.json').read_text())
            checks['scale_timing_preserved']=after['duration']==raw['duration']
            win.show();win.tabs.setCurrentIndex(1);win.steps.setCurrentIndex(2);app.processEvents()
            Path(report).parent.mkdir(parents=True,exist_ok=True)
            win.grab().save(str(Path(report).with_suffix('.png')));win.close()
    except Exception:
        import traceback
        error=traceback.format_exc()
    Path(report).parent.mkdir(parents=True,exist_ok=True)
    Path(report).write_text(json.dumps({'passed':bool(checks) and all(checks.values()) and not error,'checks':checks,'error':error},indent=2),encoding='utf-8')
    return 0 if checks and all(checks.values()) and not error else 1
