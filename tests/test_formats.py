"""Actual landscape + portrait Full HD FFmpeg export verification."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from scene_desktop.media import ffmpeg_path
from scene_desktop.studio_render import render
from scene_desktop.timeline import StudioProject


class FullHDTests(unittest.TestCase):
    def test_real_full_hd_landscape_and_portrait(self):
        ffmpeg = ffmpeg_path()
        with tempfile.TemporaryDirectory() as work:
            root = Path(work)
            image = root / "source.png"
            subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                            "-f", "lavfi", "-i", "color=c=blue:s=320x180",
                            "-frames:v", "1", str(image)], check=True, timeout=45)
            for dims in ((1920,1080),(1080,1920)):
                with self.subTest(dims=dims):
                    project = StudioProject(width=dims[0],height=dims[1],fps=24)
                    project.add(str(image), "image", "v1", 300)
                    output = root / f"out-{dims[0]}x{dims[1]}.mp4"
                    render(project, output, cache_dir=root / "cached")
                    self.assertGreater(output.stat().st_size, 1000)
                    info = subprocess.run([ffmpeg,"-hide_banner","-i",str(output)],
                                          capture_output=True,text=True,timeout=20)
                    self.assertIn(f"{dims[0]}x{dims[1]}",info.stderr)


if __name__ == "__main__":
    unittest.main()
