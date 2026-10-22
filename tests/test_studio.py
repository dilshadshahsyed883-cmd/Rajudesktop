import tempfile
import unittest
from pathlib import Path
import subprocess

from scene_desktop.timeline import StudioProject, EditHistory, save, load
from scene_desktop.library import MediaLibrary
from scene_desktop.planner import create_scene_plan, match_media, append_scenes
from scene_desktop.media import ffmpeg_path
from scene_desktop.studio_render import render


class StudioModelTests(unittest.TestCase):
    def test_multitrack_history_save_and_render_model(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            img = root / "one.png"
            img.write_bytes(b"fake-for-model")
            p = StudioProject()
            h = EditHistory(p)
            h.checkpoint()
            v = p.add(str(img), "image", "v1", 3200)
            p.add("", "text", "captions", 2200, text="A caption")
            self.assertEqual(p.duration_ms, 3200)
            h.checkpoint()
            p.move(v.id, "v2", 400)
            self.assertEqual(p.item(v.id).start_ms, 400)
            p = h.undo()
            self.assertEqual(p.item(v.id).start_ms, 0)
            p = h.redo()
            self.assertEqual(p.item(v.id).start_ms, 400)
            right = p.split(v.id, 1600)
            self.assertEqual(right.in_ms, 1200)
            path = root / "project.sds2"
            save(p, path)
            restored = load(path)
            self.assertEqual(len(restored.items), 3)
            self.assertEqual(restored.width, 1920)
            self.assertTrue(img.exists())
            with self.assertRaises(ValueError):
                restored.move(right.id, "music", 0)

    def test_approval_and_deterministic_scene_matching(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            exe = ffmpeg_path()
            for name in ["forest.png", "city.png"]:
                subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error",
                                "-f", "lavfi", "-i", "color=c=red:s=80x80",
                                "-frames:v", "1", str(root / name)],
                               check=True, timeout=45)
            lib = MediaLibrary(root / "library.sqlite3")
            forest = lib.ingest(root / "forest.png")
            city = lib.ingest(root / "city.png")
            self.assertEqual(lib.summary()["images"], 2)
            lib.set_status([forest["id"], city["id"]], "approved")
            lib.set_tags(forest["id"], ["trees", "forest"])
            scenes = create_scene_plan("A beautiful forest appears. Then the city lights shine.")
            self.assertEqual(len(scenes), 2)
            match_media(scenes, lib, allow_reuse=False)
            self.assertEqual(scenes[0].media_id, forest["id"])
            self.assertTrue(scenes[0].approved)
            self.assertNotEqual(scenes[0].media_id, scenes[1].media_id)
            p = StudioProject()
            self.assertEqual(append_scenes(p, scenes), 2)
            self.assertEqual(len(p.scenes), 2)
            self.assertEqual(lib.duplicates(), [])

    def test_real_multitrack_ffmpeg_export_and_cached_preview(self):
        exe = ffmpeg_path()
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            image = root / "cover.png"
            audio = root / "music.wav"
            subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error",
                            "-f", "lavfi", "-i", "color=c=blue:s=120x68",
                            "-frames:v", "1", str(image)], check=True, timeout=45)
            subprocess.run([exe, "-y", "-hide_banner", "-loglevel", "error",
                            "-f", "lavfi", "-i", "sine=frequency=440:duration=1",
                            str(audio)], check=True, timeout=45)
            p = StudioProject(width=480, height=270, fps=24)
            base = p.add(str(image), "image", "v1", 800)
            base.effects["mirror"] = True
            base.effects["zoom"] = 1.25
            base.effects["saturation"] = 0.9
            p.add(str(image), "image", "v2", 400, start_ms=300)
            p.add(str(audio), "audio", "voice", 800, start_ms=0)
            # Drawtext is part of FFmpeg packaged build acceptance.
            p.add("", "text", "captions", 800, start_ms=0, text="Scene One")
            result = render(p, root / "full.mp4", cache_dir=root / "cache")
            self.assertTrue(result.is_file())
            self.assertGreater(result.stat().st_size, 1000)
            preview = render(p, root / "preview.mp4", preview=True,
                             window=(100, 700), cache_dir=root / "cache")
            self.assertTrue(preview.is_file())
            self.assertTrue(len(list((root / "cache").glob("*.mp4"))) >= 2)
            p.validate()
            with self.assertRaises(FileExistsError):
                render(p, root / "full.mp4", cache_dir=root / "cache")


if __name__ == "__main__":
    unittest.main()
