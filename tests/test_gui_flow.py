"""Automated real GUI interaction flows on a headless Windows Qt session."""
import os
import tempfile
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

os.environ.setdefault("QT_QPA_PLATFORM","offscreen")

from PySide6.QtWidgets import QApplication
from scene_desktop.media import ffmpeg_path
from scene_desktop.timeline import load
from scene_desktop.studio_window import StudioWindow


class EditorFlowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.application=QApplication.instance() or QApplication([])

    def test_library_to_timeline_keyframes_save_and_word_captions(self):
        exe=ffmpeg_path()
        with tempfile.TemporaryDirectory() as temp:
            root=Path(temp)
            image=root/"input.png"
            subprocess.run([exe,"-y","-hide_banner","-loglevel","error",
                            "-f","lavfi","-i","color=c=green:s=320x180",
                            "-frames:v","1",str(image)],check=True,timeout=30)
            with patch("scene_desktop.studio_window.app_directory",return_value=root):
                win=StudioWindow()
                try:
                    asset=win.library.ingest(image)
                    win.library.set_status([asset["id"]],"approved")
                    win.refresh_library()
                    win.media_list.setCurrentRow(0)
                    with patch("scene_desktop.studio_window.QInputDialog.getItem",
                               return_value=("Main Video",True)):
                        win.add_selected_media()
                    self.assertEqual(len(win.project.items),1)
                    clip=win.project.items[0]
                    win.selected_id=clip.id
                    win.playhead_ms=1000
                    win.show_inspector()
                    win.zoom_spin.setValue(140)
                    win.add_keyframe()
                    self.assertEqual(clip.keyframes["zoom"][0]["at_ms"],1000)
                    self.assertEqual(clip.keyframes["zoom"][0]["value"],1.4)
                    self.assertEqual(win.project.duration_ms,4000)
                    win.playhead_ms=2000
                    win.split_item()
                    self.assertEqual(len(win.project.items),2)
                    win.undo()
                    self.assertEqual(len(win.project.items),1)
                    win.project_path=root/"edit.sds2"
                    win.save_project()
                    self.assertEqual(len(load(win.project_path).items),1)
                    win.script.setPlainText("A quiet forest scene.")
                    win.plan_scenes()
                    win.match_scenes()
                    self.assertEqual(len(win.scenes),1)
                    self.assertFalse(win.scenes[0].approved)
                    win.approve_scene_page()
                    self.assertTrue(win.scenes[0].approved)
                    win.save_project()
                    restored=load(win.project_path)
                    self.assertTrue(restored.scenes[0]["approved"])
                    self.assertTrue(restored.scenes[0]["locked"])
                    win._restore_scenes_from_project()
                    self.assertTrue(win.scenes[0].approved)
                    payload={"words":[
                        {"word":"Hello","start":0.1,"end":0.4},
                        {"word":"creator","start":0.45,"end":0.85}
                    ],"language":"en","model":"tiny"}
                    win._transcription_ready(payload)
                    self.assertTrue(any(item.kind=="text" for item in win.project.items))
                    self.assertTrue(any(item.caption_style.get("karaoke_words")
                                        for item in win.project.items))
                    self.assertTrue(image.is_file())
                finally:
                    if win.thumbnail_thread and win.thumbnail_thread.isRunning():
                        win.thumbnail_thread.wait(10000)
                    win.close()
