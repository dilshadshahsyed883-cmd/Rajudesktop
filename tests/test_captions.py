import tempfile
import unittest
from pathlib import Path

from scene_desktop.captions import parse_srt, from_ms, to_ms, import_srt, export_srt
from scene_desktop.timeline import StudioProject


class CaptionTests(unittest.TestCase):
    def test_timing_roundtrip_import_export(self):
        source = "1\n00:00:01,250 --> 00:00:03,750\nA test caption.\n\n2\n00:00:04,000 --> 00:00:05,500\nSecond line\n"
        lines = parse_srt(source)
        self.assertEqual(len(lines), 2)
        self.assertEqual(lines[0], (1250, 3750, "A test caption."))
        self.assertEqual(to_ms(from_ms(9123456)), 9123456)
        with tempfile.TemporaryDirectory() as folder:
            file = Path(folder) / "test.srt"
            file.write_text(source, encoding="utf-8")
            project = StudioProject()
            self.assertEqual(import_srt(project, file), 2)
            result = export_srt(project, Path(folder) / "out.srt")
            self.assertEqual(parse_srt(result.read_text(encoding="utf-8")), lines)
            self.assertEqual(project.duration_ms, 5500)

    def test_bad_time_and_tiny_caption(self):
        with self.assertRaises(ValueError):
            to_ms("99:78:00,000")
        self.assertEqual(parse_srt("00:00:00,000 --> 00:00:00,050\nToo short"), [])


if __name__ == "__main__":
    unittest.main()
