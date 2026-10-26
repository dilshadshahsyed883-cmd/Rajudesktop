"""Independent Image Renamer offline regression tests."""
import tempfile
import unittest
from pathlib import Path
from image_renamer.core import (execute, make_plan, scan_folder, undo_last, save_history, valid_keyword)

class RenameTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.src = self.root / "images"
        self.src.mkdir()
        for name in ("IMG_10.jpg", "IMG_2.png", "IMG_1.webp"):
            (self.src / name).write_bytes(name.encode())

    def test_natural_order_and_extensions(self):
        files = scan_folder(self.src)
        self.assertEqual([f.name for f in files], ["IMG_1.webp", "IMG_2.png", "IMG_10.jpg"])
        plan = make_plan(files, "Alexa", 1, self.root / "output")
        self.assertEqual([x.target.name for x in plan], ["Alexa 1.webp", "Alexa 2.png", "Alexa 3.jpg"])

    def test_copy_is_non_destructive(self):
        plan = make_plan(scan_folder(self.src), "Alexa", 4, self.root / "output")
        self.assertEqual(execute(plan), 3)
        for item in plan:
            self.assertEqual(item.source.read_bytes(), item.target.read_bytes())
        self.assertEqual(len(scan_folder(self.src)), 3)

    def test_case_insensitive_collision(self):
        out = self.root / "out"
        out.mkdir()
        (out / "aLeXa 1.webp").write_bytes(b"safe")
        with self.assertRaises(FileExistsError):
            make_plan(scan_folder(self.src), "Alexa", 1, out)
        self.assertEqual((out / "aLeXa 1.webp").read_bytes(), b"safe")

    def test_bad_names_and_number(self):
        for value in ("", " ", "a:b", "A\\B", "CON", "a?b"):
            with self.assertRaises(ValueError):
                valid_keyword(value)
        with self.assertRaises(ValueError):
            make_plan(scan_folder(self.src), "Alexa", 0, self.root / "out")

    def test_duplicate_source(self):
        f = scan_folder(self.src)[0]
        with self.assertRaises(ValueError):
            make_plan([f, f], "Alexa", 1, self.root / "out")

    def test_source_changed(self):
        plan = make_plan(scan_folder(self.src), "Alexa", 1, self.root / "out")
        plan[0].source.write_bytes(b"changed")
        with self.assertRaises(RuntimeError):
            execute(plan)

    def test_inplace_undo(self):
        before = {p.name: p.read_bytes() for p in scan_folder(self.src)}
        plan = make_plan(scan_folder(self.src), "Alexa", 1, in_place=True)
        self.assertEqual(execute(plan, True), 3)
        history = self.root / "history.json"
        save_history(history, plan)
        self.assertEqual(undo_last(history), 3)
        self.assertEqual(before, {p.name: p.read_bytes() for p in scan_folder(self.src)})
        self.assertFalse(history.exists())

    def test_undo_guard(self):
        plan = make_plan(scan_folder(self.src), "Alexa", 1, in_place=True)
        execute(plan, True)
        history = self.root / "history.json"
        save_history(history, plan)
        plan[0].target.write_bytes(b"user changed this")
        with self.assertRaises(RuntimeError):
            undo_last(history)
        self.assertTrue(history.exists())

    def test_swapping_names(self):
        one = self.src / "Alexa 1.jpg"
        two = self.src / "Alexa 2.jpg"
        one.write_bytes(b"one")
        two.write_bytes(b"two")
        plan = make_plan([two, one], "Alexa", 1, in_place=True)
        execute(plan, True)
        self.assertEqual(one.read_bytes(), b"two")
        self.assertEqual(two.read_bytes(), b"one")

    def test_copy_rollback(self):
        plan = make_plan(scan_folder(self.src), "Alexa", 1, self.root / "out")
        def fail(n, total):
            if n == 2:
                raise RuntimeError("failure")
        with self.assertRaises(RuntimeError):
            execute(plan, progress=fail)
        self.assertFalse(any(x.target.exists() for x in plan))

    def test_inplace_rollback(self):
        before = {p.name: p.read_bytes() for p in scan_folder(self.src)}
        plan = make_plan(scan_folder(self.src), "Alexa", 1, in_place=True)
        def fail(n, total):
            if n == 2:
                raise RuntimeError("failure")
        with self.assertRaises(RuntimeError):
            execute(plan, True, progress=fail)
        self.assertEqual(before, {p.name: p.read_bytes() for p in scan_folder(self.src)})

if __name__ == "__main__":
    unittest.main()
