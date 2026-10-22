"""Short genuine FFmpeg smoke render; no user media or network required."""
from pathlib import Path
import subprocess
import tempfile
import unittest

from scene_desktop.core import Project
from scene_desktop.export import export_mp4
from scene_desktop.media import duration_ms, ffmpeg_path


class ExportTests(unittest.TestCase):
    def test_real_video_export_with_silent_visual_track(self):
        exe = ffmpeg_path()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            source = root / "input.mp4"
            subprocess.run([exe, "-hide_banner", "-loglevel", "error", "-y", "-f",
                            "lavfi", "-i", "color=c=blue:s=320x180:r=24:d=0.6",
                            "-c:v", "mpeg4", str(source)], check=True, timeout=30)
            p = Project(width=720, height=1280, fps=24)
            p.add_media(str(source), duration_ms(str(source)))
            out = export_mp4(p, root / "output.mp4")
            self.assertTrue(out.exists())
            self.assertGreater(out.stat().st_size, 1024)
            with self.assertRaises(FileExistsError):
                export_mp4(p, out)
            self.assertTrue(source.exists(), "Source original must be preserved")


if __name__ == "__main__":
    unittest.main()
