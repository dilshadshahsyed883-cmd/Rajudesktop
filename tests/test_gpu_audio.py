import tempfile
import subprocess
import unittest
from pathlib import Path

from scene_desktop.gpu_audio import audio_window,has_timeline_audio,GPUAudioMixThread,audio_active_between
from scene_desktop.timeline import StudioProject
from scene_desktop.media import ffmpeg_path


class LiveAudioMixTests(unittest.TestCase):
    def test_audio_window_and_actual_file(self):
        exe=ffmpeg_path()
        with tempfile.TemporaryDirectory() as root:
            path=Path(root)
            wav=path/"voice.wav"
            subprocess.run([exe,"-y","-hide_banner","-loglevel","error",
                            "-f","lavfi","-i","sine=frequency=500:duration=1",
                            str(wav)],check=True,timeout=30)
            p=StudioProject(width=480,height=270)
            p.add(str(wav),"audio","voice",1000)
            self.assertTrue(has_timeline_audio(p))
            self.assertEqual(audio_window(p,800),(800,1000))
            worker=GPUAudioMixThread(p,100,path/"gpu-audio.m4a",7)
            worker.run()
            self.assertTrue(worker.filename.is_file())
            self.assertGreater(worker.filename.stat().st_size,1000)
            self.assertEqual(worker.generation,7)
            self.assertTrue(wav.is_file())
            future=StudioProject()
            future.add(str(wav),"audio","voice",1000,start_ms=25000)
            self.assertFalse(audio_active_between(future,0,20000))
            self.assertTrue(audio_active_between(future,20000,26000))
