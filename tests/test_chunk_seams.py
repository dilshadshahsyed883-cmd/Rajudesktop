"""Render-boundary regression: continuity in visual transitions/audio & exact CFR."""
from __future__ import annotations
import re
import struct
import subprocess
import tempfile
import unittest
from pathlib import Path

from PySide6.QtGui import QImage

from scene_desktop.media import ffmpeg_path
from scene_desktop.studio_render import render
from scene_desktop.timeline import StudioProject


class ChunkSeamTests(unittest.TestCase):
    def test_dissolve_survives_forced_chunk_edge_and_audio_is_continuous(self):
        ff=ffmpeg_path()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            original=root/"blue.png"
            overlay=root/"white.png"
            audio=root/"voice.wav"
            for image,color in ((original,"blue"),(overlay,"white")):
                subprocess.run([ff,"-hide_banner","-loglevel","error","-y",
                                "-f","lavfi","-i",f"color=c={color}:s=120x90",
                                "-frames:v","1",str(image)],check=True,timeout=30)
            subprocess.run([ff,"-hide_banner","-loglevel","error","-y",
                            "-f","lavfi","-i","sine=frequency=200:duration=8",
                            str(audio)],check=True,timeout=30)
            p=StudioProject(width=480,height=270,fps=24)
            p.add(str(original),"image","v1",8000)
            incoming=p.add(str(overlay),"image","v2",2400,start_ms=4600)
            incoming.transition_in="dissolve"
            incoming.transition_ms=1800
            p.add(str(audio),"audio","voice",8000)
            # Global 5-second split happens during the incoming dissolve.
            output=render(p,root/"joined.mp4",cache_dir=root/"cache",
                          max_chunk_ms=5000)
            self.assertTrue(output.is_file())
            samples=[]
            for index,when in enumerate(("4.88","4.96","5.04","5.12")):
                frame=root/f"sample{index}.png"
                subprocess.run([ff,"-hide_banner","-loglevel","error","-y",
                                "-ss",when,"-i",str(output),"-frames:v","1",
                                str(frame)],check=True,timeout=30)
                picture=QImage(str(frame))
                self.assertFalse(picture.isNull())
                samples.append(picture.pixelColor(240,135).red())
            # RGB red increases smoothly as white replaces blue.
            self.assertTrue(all(a<=b+8 for a,b in zip(samples,samples[1:])),
                            f"Cross-chunk dissolve jumped: {samples}")
            self.assertLess(max(samples)-min(samples),90)
            # 8s at 24fps must be exactly 192 frames, not 191/193 from ms drift.
            info=subprocess.run([ff,"-hide_banner","-loglevel","info",
                                 "-i",str(output),"-map","0:v:0","-vf","showinfo",
                                 "-f","null","-"],
                                capture_output=True,text=True,timeout=60)
            nvalues=[int(n) for n in re.findall(r"Parsed_showinfo_[^\n]*?n:\s*(\d+)",info.stderr)]
            self.assertEqual(len(nvalues),192,info.stderr[-1000:])
            self.assertEqual(nvalues[-1],191)
            # Mixed soundtrack is single-pass, not chunk-muxed, and remains
            # audible on both sides of the 5-second scene/chunk boundary.
            pcm=subprocess.run([ff,"-hide_banner","-loglevel","error",
                                "-i",str(output),"-vn","-ac","1",
                                "-ar","48000","-f","s16le","-"],
                               capture_output=True,check=True,timeout=45).stdout
            for at in (4.95,5.05):
                offset=int(at*48000)*2
                block=pcm[offset:offset+4800]
                values=struct.unpack("<"+str(len(block)//2)+"h",block)
                self.assertGreater(sum(abs(v) for v in values)/len(values),30)
            self.assertTrue(original.exists())
            self.assertTrue(overlay.exists())
            self.assertTrue(audio.exists())

    def test_absolute_motion_parameter_does_not_reset_between_chunks(self):
        from scene_desktop.effects import visual_filters
        early=",".join(visual_filters({"motion":"pan_right"},480,270,24,1.,
                                      section_elapsed=0,clip_total_ms=8000))
        late=",".join(visual_filters({"motion":"pan_right"},480,270,24,1.,
                                     section_elapsed=5.,clip_total_ms=8000))
        self.assertIn("(n+0)/192",early)
        self.assertIn("(n+120)/192",late)
        zoom=",".join(visual_filters({"motion":"ken_burns"},480,270,24,1.,
                                     section_elapsed=5.,clip_total_ms=8000))
        self.assertIn("(on+120)",zoom)
