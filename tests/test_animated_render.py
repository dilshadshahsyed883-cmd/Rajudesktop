"""Real FFmpeg frame tests: numeric zoom and brightness keyframes stay editable."""
import tempfile
import subprocess
from pathlib import Path
import unittest

from PySide6.QtGui import QImage
from scene_desktop.media import ffmpeg_path
from scene_desktop.timeline import StudioProject, save, load
from scene_desktop.keyframes import set_keyframe
from scene_desktop.studio_render import render


class AnimatedVisualTests(unittest.TestCase):
    def test_animated_keyframes_survive_split_and_change_actual_frames(self):
        exe = ffmpeg_path()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            source = root / "source.png"
            subprocess.run(
                [exe,"-y","-hide_banner","-loglevel","error","-f","lavfi",
                 "-i","testsrc2=s=320x180:r=24","-frames:v","1",str(source)],
                check=True,timeout=30
            )
            project = StudioProject(width=480,height=270,fps=24)
            clip = project.add(str(source),"image","v1",2000)
            clip.keyframes = set_keyframe(clip.keyframes,"brightness",0,-.35,2000)
            clip.keyframes = set_keyframe(clip.keyframes,"brightness",1900,.35,2000)
            clip.keyframes = set_keyframe(clip.keyframes,"zoom",0,1.,2000)
            clip.keyframes = set_keyframe(clip.keyframes,"zoom",1900,2.,2000)
            editable = root / "project.sds2"
            save(project,editable)
            self.assertEqual(load(editable).item(clip.id).keyframes,clip.keyframes)
            full = render(project,root / "animated.mp4",cache_dir=root/"cache")
            self.assertTrue(full.exists())
            images=[]
            for i,sec in enumerate(["0.20","1.60"]):
                frame=root/f"frame_{i}.png"
                subprocess.run(
                    [exe,"-y","-hide_banner","-loglevel","error","-ss",sec,
                     "-i",str(full),"-frames:v","1",str(frame)],
                    check=True,timeout=35
                )
                images.append(QImage(str(frame)))
            self.assertTrue(all(not x.isNull() for x in images))
            # Global average brightness must move meaningfully.
            def brightness(image):
                return sum(image.pixelColor(x,y).value()
                           for x in range(10,image.width(),25)
                           for y in range(10,image.height(),25))
            self.assertGreater(brightness(images[1]),brightness(images[0]))
            right = project.split(clip.id,1000)
            self.assertEqual(right.keyframes["zoom"][0]["at_ms"],0)
            self.assertAlmostEqual(right.keyframes["zoom"][0]["value"],1.+1000/1900)
            self.assertEqual(project.item(clip.id).keyframes["brightness"][-1]["at_ms"],1000)
