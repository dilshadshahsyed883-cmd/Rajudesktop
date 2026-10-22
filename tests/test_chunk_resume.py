"""CPU chunk/resume regression with real FFmpeg and audio, no owner PC access."""
from __future__ import annotations
import json
import subprocess
import tempfile
import threading
import unittest
from pathlib import Path

from scene_desktop.chunk_pipeline import ChunkStore, plan_chunks
from scene_desktop.media import ffmpeg_path
from scene_desktop.studio_render import render, resumable_exports
from scene_desktop.timeline import StudioProject


class ChunkResumeTests(unittest.TestCase):
    def test_frame_aligned_chunks_do_not_drift(self):
        p=StudioProject(width=480,height=270,fps=24)
        p.add("a.png","image","v1",7420)
        p.add("b.png","image","v2",1800,start_ms=3137)
        chunks=plan_chunks(p,0,7420,max_ms=3000)
        self.assertGreaterEqual(len(chunks),3)
        self.assertEqual(chunks[0].start_frame,0)
        self.assertEqual(chunks[-1].end_frame,179)
        self.assertEqual(sum(x.frames for x in chunks),179)
        self.assertTrue(all(x.frames>0 for x in chunks))
        self.assertTrue(all(left.end_frame==right.start_frame
                            for left,right in zip(chunks,chunks[1:])))
        self.assertTrue(any(x.start_frame==round(3137*24/1000) for x in chunks))

    def test_interrupt_resume_corrupt_chunk_and_changed_chunk(self):
        exe=ffmpeg_path()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            original=root/"source.png"
            second=root/"overlay.png"
            wav=root/"voice.wav"
            for name,color in ((original,"blue"),(second,"red")):
                subprocess.run([exe,"-hide_banner","-loglevel","error","-y",
                                "-f","lavfi","-i",f"color=c={color}:s=120x90",
                                "-frames:v","1",str(name)],check=True,timeout=30)
            subprocess.run([exe,"-hide_banner","-loglevel","error","-y",
                            "-f","lavfi","-i","sine=frequency=440:duration=7.5",
                            str(wav)],check=True,timeout=30)
            p=StudioProject(width=480,height=270,fps=24)
            p.add(str(original),"image","v1",7500)
            p.add(str(wav),"audio","voice",7500)
            cache=root/"cache"
            cancelled=threading.Event()
            def interrupt(_pct,text):
                if "Chunk 1/" in text:
                    cancelled.set()
            with self.assertRaisesRegex(RuntimeError,"cancelled"):
                render(p,root/"first.mp4",cache_dir=cache,max_chunk_ms=4000,
                       progress=interrupt,stop=cancelled)
            self.assertFalse((root/"first.mp4").exists())
            store=ChunkStore(cache)
            self.assertTrue(list(store.receipts.glob("*.json")))
            self.assertEqual(resumable_exports(p,cache),[root/"first.mp4"])
            incompatible=StudioProject(width=480,height=270,fps=24)
            incompatible.add(str(second),"image","v1",7500)
            self.assertEqual(resumable_exports(incompatible,cache),[])

            resumptions=[]
            output=render(p,root/"first.mp4",cache_dir=cache,max_chunk_ms=4000,
                          progress=lambda _pct,message:resumptions.append(message))
            self.assertTrue(output.is_file())
            self.assertTrue(any("reused" in m for m in resumptions))
            receipt=json.loads(store.job_path(output).read_text(encoding="utf-8"))
            self.assertEqual(receipt["state"],"complete")
            self.assertNotIn(root/"first.mp4",resumable_exports(p,cache))

            self.assertEqual(len(receipt["verified"]),len(receipt["planned"]))
            # Source data must not be deleted by chunk cache.
            self.assertTrue(original.is_file())
            self.assertTrue(wav.is_file())
            # A tampered cache file is never reused, even if it still exists.
            key=receipt["planned"][0]
            chunk=store.section_path(key)
            chunk.write_bytes(b"BROKEN-INCOMPLETE-MP4")
            self.assertFalse(store.valid(key,plan_chunks(p,0,7500,max_ms=4000)[0]))
            rerun=[]
            render(p,root/"repaired.mp4",cache_dir=cache,max_chunk_ms=4000,
                   progress=lambda _pct,message:rerun.append(message))
            self.assertTrue(any("rendered" in m for m in rerun))
            self.assertTrue(any("reused" in m for m in rerun))
            # Edit only the late overlay; early content-addressed chunk remains reusable.
            p.add(str(second),"image","v2",1000,start_ms=6000)
            edited=[]
            result=render(p,root/"edited.mp4",cache_dir=cache,max_chunk_ms=4000,
                          progress=lambda _pct,message:edited.append(message))
            self.assertTrue(result.is_file())
            self.assertTrue(any("reused" in m for m in edited))
            self.assertTrue(any("rendered" in m for m in edited))
            # Final video has a single uninterrupted video stream and audio track.
            info=subprocess.run([exe,"-hide_banner","-i",str(result)],
                                capture_output=True,text=True,timeout=20)
            self.assertIn("Video:",info.stderr)
            self.assertIn("Audio:",info.stderr)
            self.assertTrue(second.is_file())

    def test_cpu_preview_quality_never_changes_full_export(self):
        exe=ffmpeg_path()
        with tempfile.TemporaryDirectory() as folder:
            root=Path(folder)
            img=root/"img.png"
            subprocess.run([exe,"-hide_banner","-loglevel","error","-y",
                            "-f","lavfi","-i","color=c=green:s=120x90",
                            "-frames:v","1",str(img)],check=True,timeout=30)
            p=StudioProject(width=1280,height=720,fps=24)
            p.add(str(img),"image","v1",350)
            cache=root/"cache"
            for side in (360,540):
                preview=render(p,root/f"preview-{side}.mp4",
                               preview=True,preview_side=side,cache_dir=cache)
                self.assertGreater(preview.stat().st_size,1000)
            full=render(p,root/"1080-source.mp4",cache_dir=cache)
            info=subprocess.run([exe,"-hide_banner","-i",str(full)],
                                capture_output=True,text=True,timeout=20)
            self.assertIn("1280x720",info.stderr)
