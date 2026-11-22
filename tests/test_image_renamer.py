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

    def test_case_insensitive_collision_uses_next_available_number(self):
        out = self.root / "out"
        out.mkdir()
        (out / "aLeXa 1.webp").write_bytes(b"safe")
        plan = make_plan(scan_folder(self.src), "Alexa", 1, out)
        self.assertEqual([x.target.stem for x in plan], ["Alexa 2", "Alexa 3", "Alexa 4"])
        self.assertEqual(execute(plan), 3)
        self.assertEqual((out / "aLeXa 1.webp").read_bytes(), b"safe")

    def test_gap_fill_across_extensions_and_preserve_existing(self):
        out = self.root / "out"
        out.mkdir()
        for name in ("Naomi Osaka 1.jpg", "Naomi Osaka 2.jpg",
                     "Naomi Osaka 4.jpg", "Naomi Osaka 7.png"):
            (out / name).write_bytes(name.encode())
        extra = self.src / "IMG_3.jpg"
        extra.write_bytes(b"new")
        files = [self.src / "IMG_10.jpg", self.src / "IMG_2.png",
                 self.src / "IMG_1.webp", extra]
        plan = make_plan(files, "Naomi Osaka", 1, out)
        self.assertEqual([p.target.name for p in plan], [
            "Naomi Osaka 3.jpg", "Naomi Osaka 5.png",
            "Naomi Osaka 6.webp", "Naomi Osaka 8.jpg"])
        self.assertEqual(execute(plan), 4)
        self.assertEqual((out / "Naomi Osaka 7.png").read_bytes(),
                         b"Naomi Osaka 7.png")

    def test_numbers_reserved_across_extensions_and_start_number(self):
        out = self.root / "out"
        out.mkdir()
        (out / "naomi osaka 10.PNG").write_bytes(b"previous")
        (out / "Naomi Osaka 12.jpg").write_bytes(b"previous")
        (out / "Different Name 11.webp").write_bytes(b"unrelated")
        plan = make_plan(scan_folder(self.src), "Naomi Osaka", 10, out)
        self.assertEqual([p.target.stem for p in plan],
                         ["Naomi Osaka 11", "Naomi Osaka 13", "Naomi Osaka 14"])
        self.assertEqual((out / "naomi osaka 10.PNG").read_bytes(), b"previous")

    def test_contiguous_numbers_continue_after_last(self):
        out = self.root / "out"
        out.mkdir()
        for i in range(1, 61):
            (out / f"Naomi Osaka {i}.jpg").write_bytes(b"old")
        plan = make_plan(scan_folder(self.src), "Naomi Osaka", 1, out)
        self.assertEqual([p.target.stem for p in plan],
                         ["Naomi Osaka 61", "Naomi Osaka 62", "Naomi Osaka 63"])

    def test_preview_then_occupied_number_never_overwritten(self):
        out = self.root / "out"
        out.mkdir()
        (out / "Naomi Osaka 1.jpg").write_bytes(b"old")
        plan = make_plan(scan_folder(self.src), "Naomi Osaka", 1, out)
        self.assertEqual(plan[0].target.stem, "Naomi Osaka 2")
        colliding = out / "naomi osaka 2.png"
        colliding.write_bytes(b"arrived-after-preview")
        with self.assertRaises(FileExistsError):
            execute(plan)
        self.assertEqual(colliding.read_bytes(), b"arrived-after-preview")
        self.assertFalse(plan[0].target.exists())

    def test_inplace_preserves_existing_names_and_undo_only_changes(self):
        source_old = self.src / "Naomi Osaka 1.jpg"
        source_other = self.src / "Naomi Osaka 3.png"
        source_old.write_bytes(b"one")
        source_other.write_bytes(b"three")
        original = self.src / "IMG_1.webp"
        plan = make_plan([source_old, original, source_other],
                         "Naomi Osaka", 1, in_place=True)
        self.assertEqual([p.target.name for p in plan],
                         ["Naomi Osaka 1.jpg", "Naomi Osaka 2.webp",
                          "Naomi Osaka 3.png"])
        self.assertEqual(execute(plan, True), 1)
        history = self.root / "smart-history.json"
        save_history(history, plan)
        import json
        entries = json.loads(history.read_text(encoding="utf-8"))["entries"]
        self.assertEqual(len(entries), 1)
        self.assertEqual(undo_last(history), 1)
        self.assertTrue(original.exists())
        self.assertEqual(source_old.read_bytes(), b"one")
        self.assertEqual(source_other.read_bytes(), b"three")

    def test_inplace_noop_does_not_overwrite_prior_undo_history(self):
        already = self.src / "Naomi Osaka 5.jpg"
        already.write_bytes(b"keep")
        history = self.root / "old-history.json"
        history.write_text("previous history")
        plan = make_plan([already], "Naomi Osaka", 10, in_place=True)
        self.assertEqual(plan[0].source, plan[0].target)
        self.assertEqual(execute(plan, True), 0)
        save_history(history, plan)
        self.assertEqual(history.read_text(), "previous history")
        self.assertEqual(already.read_bytes(), b"keep")

    def test_separate_inplace_folders_get_separate_number_spaces(self):
        folder2 = self.root / "other"
        folder2.mkdir()
        (self.src / "Naomi Osaka 1.jpg").write_bytes(b"existing")
        img_a = self.src / "one.jpg"
        img_b = folder2 / "two.jpg"
        img_a.write_bytes(b"A")
        img_b.write_bytes(b"B")
        plan = make_plan([img_a, img_b], "Naomi Osaka", 1, in_place=True)
        self.assertEqual([p.target.name for p in plan],
                         ["Naomi Osaka 2.jpg", "Naomi Osaka 1.jpg"])

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

    def test_correctly_numbered_originals_never_swap(self):
        one = self.src / "Alexa 1.jpg"
        two = self.src / "Alexa 2.jpg"
        one.write_bytes(b"one")
        two.write_bytes(b"two")
        plan = make_plan([two, one], "Alexa", 1, in_place=True)
        self.assertEqual([p.target for p in plan], [two, one])
        self.assertEqual(execute(plan, True), 0)
        self.assertEqual(one.read_bytes(), b"one")
        self.assertEqual(two.read_bytes(), b"two")

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
