"""Use a real .cube LUT through the Windows-packaged FFmpeg filtergraph."""
import subprocess
import tempfile
import unittest
from pathlib import Path

from scene_desktop.media import ffmpeg_path
from scene_desktop.timeline import StudioProject
from scene_desktop.studio_render import render


class CubeLUTTests(unittest.TestCase):
    def test_user_supplied_cube_lut_and_cache_invalidation(self):
        exe = ffmpeg_path()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / "subject.png"
            subprocess.run([exe,"-hide_banner","-loglevel","error","-y",
                            "-f","lavfi","-i","color=c=red:s=100x70",
                            "-frames:v","1",str(image)],check=True,timeout=30)
            lut = root / "grade.cube"
            lut.write_text(
                'TITLE "identity"\nLUT_3D_SIZE 2\n'
                '0 0 0\n1 0 0\n0 1 0\n1 1 0\n'
                '0 0 1\n1 0 1\n0 1 1\n1 1 1\n',
                encoding="utf-8"
            )
            p = StudioProject(width=480,height=270,fps=24)
            item = p.add(str(image),"image","v1",300)
            item.effects["lut_file"] = str(lut)
            first = render(p,root/"first.mp4",cache_dir=root/"cache")
            self.assertTrue(first.is_file())
            earlier = len(list((root/"cache").glob("*.mp4")))
            self.assertGreater(earlier,0)
            lut.write_text(lut.read_text(encoding="utf-8").replace("1 0 0","0.8 0.0 0.0"),encoding="utf-8")
            second = render(p,root/"second.mp4",cache_dir=root/"cache")
            self.assertTrue(second.is_file())
            self.assertGreater(len(list((root/"cache").glob("*.mp4"))), earlier)
            self.assertTrue(image.exists())
            self.assertTrue(lut.exists())


if __name__ == "__main__":
    unittest.main()
