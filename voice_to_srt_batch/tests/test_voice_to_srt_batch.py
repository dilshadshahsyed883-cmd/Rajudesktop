import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
import queue
import threading
from unittest.mock import patch

from voice_to_srt_studio.app import Studio
from voice_to_srt_studio.engine import (
    Word, Cancelled, build_cues, collect_folder, output_path,
    render_srt, save_atomic, to_srt_time, transcribe_one, unique_valid_sources,
)


class EngineTests(unittest.TestCase):
    def test_srt_format_and_unicode(self):
        cues = build_cues([
            Word(" سلام", 0.23, 1.1), Word(" دنیا", 1.2, 2.9),
            Word(" Hello", 3.1, 3.8), Word(" world", 3.8, 4.3),
        ], 2, 3)
        text = render_srt(cues)
        self.assertIn("00:00:00,230 --> 00:00:02,900", text)
        self.assertIn("سلام دنیا", text)
        self.assertEqual(to_srt_time(3661.234), "01:01:01,234")

    def test_group_by_duration_and_pause(self):
        items = [Word(" word", 0, .8), Word(" two", .9, 1.8),
                 Word(" three", 2, 3.1), Word(" four", 5, 5.7)]
        cues = build_cues(items, 2, 3)
        self.assertEqual(len(cues), 3)
        self.assertEqual(cues[1].text, "three")
        self.assertEqual(cues[2].start, 5)

    def test_file_selection_and_atomic_output(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            (folder / "A.MP3").write_bytes(b"fake")
            (folder / "b.WAV").write_bytes(b"fake")
            (folder / "notes.txt").write_text("skip")
            selected = unique_valid_sources([folder / "A.MP3", folder / "A.MP3", folder / "notes.txt"])
            self.assertEqual(len(selected), 1)
            self.assertEqual(len(collect_folder(folder)), 2)
            dest = output_path(selected[0], None)
            save_atomic(dest, "1\n00:00:00,000 --> 00:00:01,000\nHi\n")
            self.assertTrue(dest.exists())
            self.assertEqual(dest.name, "A.srt")
            self.assertFalse(list(folder.glob(".srt-*.tmp")))

    def test_faux_whisper_transcription_and_cancel(self):
        segments = [SimpleNamespace(start=0.0, end=2.0, text="hello world",
                                    words=[SimpleNamespace(start=0.2, end=1.0, word=" Hello"),
                                           SimpleNamespace(start=1.0, end=2.0, word=" world")])]
        class FakeModel:
            def transcribe(self, path, **options):
                self.options = options
                return iter(segments), SimpleNamespace(duration=3)
        fake = FakeModel()
        events = []
        result = transcribe_one(fake, Path("voice.mp3"), "Short (2-3 sec)", "English",
                                events.append, lambda: False)
        self.assertEqual(result[0].text, "Hello world")
        self.assertEqual(events[-1], 1.0)
        self.assertTrue(fake.options["word_timestamps"])
        with self.assertRaises(Cancelled):
            transcribe_one(fake, Path("voice.mp3"), "Short (2-3 sec)", "English",
                           lambda n: None, lambda: True)


class BatchTests(unittest.TestCase):
    def test_two_files_and_existing_output_are_independent(self):
        with tempfile.TemporaryDirectory() as root:
            folder = Path(root)
            audio1, audio2 = folder / "one.mp3", folder / "two.mp3"
            audio1.write_bytes(b"dummy audio")
            audio2.write_bytes(b"dummy audio")
            # Existing output must remain unchanged by default.
            (folder / "one.srt").write_text("keep", encoding="utf-8")
            studio = Studio.__new__(Studio)  # worker has no Tk dependency
            studio.events = queue.Queue()
            studio.stop_event = threading.Event()
            mock_cues = [build_cues([Word(" Hello", 0, 1), Word(" world", 1, 2)], 2, 3)[0]]
            with patch("voice_to_srt_studio.app.make_model", return_value=object()) as load, \
                 patch("voice_to_srt_studio.app.transcribe_one", return_value=mock_cues) as transcribe:
                studio._worker([("1", audio1), ("2", audio2)], None,
                               ("small", "Short (2-3 sec)", "English", False))
                self.assertEqual(load.call_count, 1)
                self.assertEqual(transcribe.call_count, 1)
            self.assertEqual((folder / "one.srt").read_text(encoding="utf-8"), "keep")
            self.assertIn("Hello world", (folder / "two.srt").read_text(encoding="utf-8"))
            items = list(studio.events.queue)
            self.assertTrue(any(e[0] == "item" and e[1] == "1" and e[2] == "Skipped" for e in items))
            self.assertTrue(any(e[0] == "item" and e[1] == "2" and e[2] == "Done" for e in items))
            self.assertEqual(items[-1][0], "finished")

    def test_cancellation_avoids_new_files(self):
        with tempfile.TemporaryDirectory() as root:
            audio = Path(root) / "voice.mp3"
            audio.write_bytes(b"dummy audio")
            studio = Studio.__new__(Studio)
            studio.events = queue.Queue()
            studio.stop_event = threading.Event()
            studio.stop_event.set()
            studio._worker([("1", audio)], None, ("small", "Short (2-3 sec)", "English", False))
            self.assertFalse((Path(root) / "voice.srt").exists())
            self.assertTrue(any(e[0] == "item" and e[2] == "Cancelled" for e in studio.events.queue))


if __name__ == "__main__":
    unittest.main()
