import json
import subprocess
import tempfile
import unittest
from pathlib import Path

from scene_desktop.media import ffmpeg_path
from scene_desktop.timeline import StudioProject
from scene_desktop.studio_render import render
from scene_desktop.word_captions import (_parse_words,grouped_words,
                                         import_word_json,ass_for_section)


class KaraokeCaptionsTests(unittest.TestCase):
    def test_whisper_word_import_and_validation(self):
        payload={"segments":[{"words":[
            {"word":"Hello","start":0.10,"end":0.40},
            {"word":"beautiful","start":0.40,"end":0.80},
            {"word":"world!","start":0.80,"end":1.25}
        ]}]}
        words=_parse_words(payload)
        self.assertEqual(len(grouped_words(words)),1)
        with tempfile.TemporaryDirectory() as folder:
            filename=Path(folder)/"whisper.json"
            filename.write_text(json.dumps(payload),encoding="utf-8")
            project=StudioProject()
            self.assertEqual(import_word_json(project,filename),1)
            item=project.items[0]
            self.assertEqual(len(item.caption_style["karaoke_words"]),3)
            self.assertIn("Hello beautiful world!",item.text)
            styled=ass_for_section([item],200,900,480,270)
            self.assertIn(r"{\k",styled)
            self.assertIn("Dialogue: 0",styled)
            self.assertIn("SecondaryColour",styled)
        with self.assertRaises(ValueError):
            _parse_words({"segments":[{"text":"no word timings"}]})
        with self.assertRaises(ValueError):
            _parse_words([{"word":"oops","start":0.5,"end":0.2}])

    def test_karaoke_is_rendered_by_ffmpeg_in_video(self):
        ffmpeg=ffmpeg_path()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            image=root/"image.png"
            subprocess.run([ffmpeg,"-hide_banner","-loglevel","error","-y",
                            "-f","lavfi","-i","color=c=blue:s=160x90",
                            "-frames:v","1",str(image)],check=True,timeout=30)
            transcript=root/"words.json"
            transcript.write_text(json.dumps({"words":[
                {"word":"Hello","start":0.1,"end":0.45},
                {"word":"world","start":0.45,"end":1.0}
            ]}),encoding="utf-8")
            project=StudioProject(width=480,height=270,fps=24)
            project.add(str(image),"image","v1",1200)
            self.assertEqual(import_word_json(project,transcript),1)
            result=render(project,root/"karaoke.mp4",cache_dir=root/"cache")
            self.assertGreater(result.stat().st_size,1000)
            preview=render(project,root/"preview.mp4",cache_dir=root/"cache",
                           preview=True,window=(250,850))
            self.assertTrue(preview.is_file())
            self.assertTrue(image.exists())
