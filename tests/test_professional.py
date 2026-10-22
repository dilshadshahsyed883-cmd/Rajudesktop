import subprocess
import tempfile
import unittest
from pathlib import Path

from scene_desktop.effects import COLOR_LOOKS, MOTIONS, TRANSITIONS, GRAINS, visual_filters, overlay_position
from scene_desktop.media import ffmpeg_path
from scene_desktop.studio_render import render
from scene_desktop.timeline import StudioProject, Item


class ProfessionalEffectsTests(unittest.TestCase):
    def test_catalog_and_validation(self):
        self.assertEqual(len(COLOR_LOOKS), 23)
        self.assertEqual(len(set(COLOR_LOOKS.values())), 23)
        self.assertIn("ken_burns", MOTIONS)
        self.assertIn("slide_up", TRANSITIONS)
        self.assertIn("analog", GRAINS)
        zoom_out = visual_filters({"zoom":.50},480,270,24,1)
        self.assertTrue(any("pad=480:270" in f for f in zoom_out))
        for name in COLOR_LOOKS:
            filters = visual_filters({"look": name, "look_intensity": 65},
                                     320, 180, 24, 1.2)
            self.assertIn("eq=", ",".join(filters))
        self.assertNotEqual(overlay_position("slide_left", .8, .2),
                            overlay_position("slide_right", .8, .2))
        with self.assertRaises(ValueError):
            visual_filters({"look": "missing"}, 320, 180, 24, 1)
        with self.assertRaises(ValueError):
            Item("a.mp4", "video", "v1", 0, 0, 2000,
                 effects={"motion": "bad"}).validate()

    def test_real_kenburns_grade_slide_and_source_audio(self):
        exe = ffmpeg_path()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            video = root / "source.mp4"
            still = root / "image.png"
            subprocess.run([
                exe, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "testsrc2=size=160x90:rate=24:duration=1.2",
                "-f", "lavfi", "-i", "sine=frequency=330:duration=1.2",
                "-c:v", "mpeg4", "-c:a", "aac", "-shortest", str(video)
            ], check=True, timeout=40)
            subprocess.run([
                exe, "-hide_banner", "-loglevel", "error", "-y",
                "-f", "lavfi", "-i", "color=c=yellow:s=120x80",
                "-frames:v", "1", str(still)
            ], check=True, timeout=30)
            project = StudioProject(width=480, height=270, fps=24)
            first = project.add(str(video), "video", "v1", 1100)
            first.effects.update({"source_audio":True, "motion":"pan_left",
                                  "look":"teal_orange", "look_intensity":75,
                                  "grain":2, "grain_style":"white"})
            second = project.add(str(still), "image", "v2", 700, start_ms=350)
            second.effects["motion"] = "ken_burns"
            second.transition_in = "slide_left"
            second.transition_ms = 350
            result = render(project, root / "full.mp4", cache_dir=root / "cache")
            self.assertTrue(result.is_file())
            preview = render(project, root / "preview.mp4", cache_dir=root / "cache",
                             preview=True, window=(200, 900))
            self.assertTrue(preview.is_file())
            # Ensure overlay track truly appears on top after slide completes.
            from PySide6.QtGui import QImage
            frame = root / "frame.png"
            subprocess.run([exe,"-hide_banner","-loglevel","error","-y",
                            "-ss","0.9","-i",str(result),"-frames:v","1",
                            str(frame)],check=True,timeout=30)
            pixel = QImage(str(frame)).pixelColor(240,135)
            self.assertGreater(pixel.red(), 140)
            self.assertGreater(pixel.green(), 140)
            info = subprocess.run([exe, "-hide_banner", "-i", str(result)],
                                  capture_output=True, text=True, timeout=20)
            self.assertIn("Audio:", info.stderr)
            self.assertIn("Video:", info.stderr)
            self.assertTrue(still.is_file())
            self.assertTrue(video.is_file())


if __name__ == "__main__":
    unittest.main()
