"""GPU-preview decode and bounded cache tests; no GPU machine required."""
import tempfile
import time
from pathlib import Path
from unittest import TestCase

from PySide6.QtGui import QImage
from scene_desktop.live_preview import (
    BoundedFrameProvider,_safe_video_frame,_safe_still_frame,OpenGLTimelineCanvas
)
from scene_desktop.timeline import StudioProject
from scene_desktop.media import ffmpeg_path
import subprocess


class FrameDecodeTests(TestCase):
    def test_video_frame_seek_and_image_scaling(self):
        ffmpeg=ffmpeg_path()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            still=root/"still.png"
            clip=root/"moving.mp4"
            subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-y",
                            "-f","lavfi","-i","color=c=red:s=360x240",
                            "-frames:v","1",str(still)],check=True,timeout=30)
            subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-y",
                            "-f","lavfi","-i","testsrc2=s=320x180:r=24:d=2",
                            "-c:v","mpeg4","-q:v","5",str(clip)],check=True,timeout=35)
            qimage=_safe_still_frame(still,0,180)
            self.assertFalse(qimage.isNull())
            self.assertLessEqual(max(qimage.width(),qimage.height()),180)
            frame=_safe_video_frame(clip,1000,360)
            self.assertFalse(frame.isNull())
            self.assertEqual((frame.width(),frame.height()),(320,180))
            self.assertLessEqual(max(frame.width(),frame.height()),360)

    def test_bounded_lru_cache_async(self):
        ffmpeg=ffmpeg_path()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            still=root/"a.png"
            subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-y",
                            "-f","lavfi","-i","color=c=green:s=80x60",
                            "-frames:v","1",str(still)],check=True,timeout=30)
            p=StudioProject()
            item=p.add(str(still),"image","v1",2000)
            updates=[]
            provider=BoundedFrameProvider(lambda:updates.append("ready"),max_bytes=8*1024**2)
            try:
                key,image=provider.get(item,0)
                self.assertIsNone(image)
                for retry in range(80):
                    time.sleep(.02)
                    provider.poll()
                    if key in provider.frames:
                        break
                self.assertIn(key,provider.frames)
                self.assertTrue(updates)
                self.assertLessEqual(provider.size_bytes,8*1024**2)
                key,result=provider.get(item,500)
                self.assertFalse(result.isNull())
                provider.reset()
                self.assertEqual(provider.size_bytes,0)
            finally:
                provider.close()

    def test_opengl_widget_constructs_without_context(self):
        # Offscreen Windows runner may not supply a usable OpenGL context:
        # widget creation must not imply hardware acceleration.
        from PySide6.QtWidgets import QApplication
        app=QApplication.instance() or QApplication([])
        canvas=OpenGLTimelineCanvas()
        try:
            self.assertFalse(canvas.is_hardware())
            self.assertFalse(canvas.playing)
            canvas.seek(0)
            self.assertEqual(canvas.position_ms,0)
        finally:
            canvas.shutdown()
            canvas.deleteLater()
