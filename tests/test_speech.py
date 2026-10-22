import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
import sys

from scene_desktop.speech import transcribe_local


class SpeechEngineTests(unittest.TestCase):
    def test_local_transcription_with_fake_cpu_engine_no_network(self):
        kwargs={}
        class WhisperStub:
            def __init__(self,*args,**options):
                kwargs.update(options)
            def transcribe(self,audio,**options):
                self.options=options
                word=SimpleNamespace(word="Hello",start=0.1,end=0.42)
                return iter([SimpleNamespace(words=[word])]),SimpleNamespace(language="en")
        with tempfile.TemporaryDirectory() as root:
            sound=Path(root)/"voice.wav"
            sound.write_bytes(b"fixture")
            fake=SimpleNamespace(WhisperModel=WhisperStub)
            with patch.dict(sys.modules,{"faster_whisper":fake}):
                result=transcribe_local(sound,"tiny",Path(root)/"models",False)
            self.assertEqual(result["words"][0]["word"],"Hello")
            self.assertEqual(result["language"],"en")
            self.assertEqual(kwargs["device"],"cpu")
            self.assertTrue(kwargs["local_files_only"])
        with self.assertRaises(ValueError):
            transcribe_local("missing.wav","large-v3",Path.cwd())

    def test_download_is_explicit(self):
        with tempfile.TemporaryDirectory() as root:
            sound=Path(root)/"voice.wav"
            sound.write_bytes(b"fixture")
            class Model:
                def __init__(self,*args,**kwargs):
                    self.opts=kwargs
                    self.local_only=kwargs["local_files_only"]
                def transcribe(self,*args,**kwargs):
                    return iter([SimpleNamespace(words=[SimpleNamespace(
                        word="Testing",start=.1,end=.3)])]),SimpleNamespace(language="en")
            with patch.dict(sys.modules,{"faster_whisper":SimpleNamespace(WhisperModel=Model)}):
                result=transcribe_local(sound,"base",Path(root)/"models",True)
            self.assertEqual(result["model"],"base")
