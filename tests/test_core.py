import json
from pathlib import Path
import tempfile
import unittest

from scene_desktop.core import Clip, Project, classify, load_project, save_project


class ProjectTests(unittest.TestCase):
    def test_supported_types(self):
        self.assertEqual(classify("test.MP4"), "video")
        self.assertEqual(classify("photo.PNG"), "image")
        with self.assertRaises(ValueError):
            classify("evil.exe")

    def test_edit_split_reorder_and_roundtrip(self):
        with tempfile.TemporaryDirectory() as work:
            p = Path(work)
            a = p / "a.mp4"
            b = p / "b.png"
            a.touch()
            b.touch()
            project = Project("My edit")
            clip_a = project.add_media(str(a), 10000)
            clip_b = project.add_media(str(b), 4000)
            project.reorder([clip_b.id, clip_a.id])
            self.assertEqual(project.locate(5000), (1, 1000))
            left, right = project.split(1, 6000)
            self.assertEqual((left.duration_ms, right.duration_ms), (6000, 4000))
            self.assertEqual(project.duration_ms, 14000)
            clip_b.trim(500, 2500)
            self.assertEqual(project.duration_ms, 12000)
            path = p / "project.sdsproj"
            save_project(project, path)
            restored = load_project(path)
            self.assertEqual(restored.duration_ms, 12000)
            self.assertEqual([c.id for c in restored.clips], [c.id for c in project.clips])
            self.assertEqual(json.loads(path.read_text())["version"], 1)

    def test_invalid_actions_preserve_model(self):
        with tempfile.TemporaryDirectory() as work:
            p = Path(work) / "a.png"
            p.touch()
            project = Project()
            clip = project.add_media(str(p), 4000)
            with self.assertRaises(ValueError):
                clip.trim(900, 500)
            self.assertEqual(clip.duration_ms, 4000)
            with self.assertRaises(ValueError):
                project.reorder([clip.id, clip.id])
            with self.assertRaises(ValueError):
                project.split(0, 50)
            self.assertEqual(len(project.clips), 1)

    def test_reject_unknown_project_version(self):
        with self.assertRaises(ValueError):
            Project.from_dict({"version": 2, "clips": []})


if __name__ == "__main__":
    unittest.main()
