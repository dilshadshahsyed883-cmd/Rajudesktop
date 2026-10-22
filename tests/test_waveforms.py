import subprocess
import tempfile
from pathlib import Path
import unittest

from scene_desktop.media import ffmpeg_path
from scene_desktop.waveforms import generate_waveform


class WaveformTests(unittest.TestCase):
    def test_read_only_voice_waveform_and_cache(self):
        exe=ffmpeg_path()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            voice=root/"voice.wav"
            subprocess.run([exe,"-hide_banner","-loglevel","error","-y",
                            "-f","lavfi","-i","sine=frequency=440:duration=1.3",
                            str(voice)],check=True,timeout=25)
            before=voice.stat().st_size
            output=generate_waveform(voice,root/"cache")
            self.assertTrue(output.is_file())
            self.assertGreater(output.stat().st_size,64)
            self.assertEqual(generate_waveform(voice,root/"cache"),output)
            self.assertEqual(voice.stat().st_size,before)
