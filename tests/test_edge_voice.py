"""Offline contract tests for the independent Edge Voice Studio engine."""
import asyncio
from pathlib import Path
import subprocess
import tempfile
import unittest

from edge_voice_studio.core import (
    english_voice, safe_title, settings_hash, split_script, srt_time, write_srt)
from edge_voice_studio.engine import RenderStopped, ffmpeg_path, render_job
from edge_voice_studio.store import Store


class ChunkTests(unittest.TestCase):
    def test_empty_and_too_small(self):
        with self.assertRaises(ValueError):
            split_script("    ")
        with self.assertRaises(ValueError):
            split_script("hello", 10)

    def test_sentence_boundaries_and_size(self):
        script = ("A short sentence. Another short sentence! " * 30) + "\n\nEnd."
        chunks = split_script(script, limit=85)
        self.assertGreater(len(chunks), 2)
        self.assertTrue(all(0 < len(c) <= 85 for c in chunks))
        self.assertIn("End.", chunks[-1])
        self.assertEqual(" ".join(chunks), " ".join(script.split()))

    def test_long_token_and_signature(self):
        chunks = split_script("x" * 150, 50)
        self.assertEqual([len(x) for x in chunks], [50, 50, 50])
        a = settings_hash("hello", "en-US-AndrewNeural", 0, 0, 0)
        b = settings_hash("hello", "en-US-AndrewNeural", 5, 0, 0)
        self.assertNotEqual(a, b)

    def test_voice_and_title(self):
        self.assertTrue(english_voice("en-GB-RyanNeural"))
        self.assertFalse(english_voice("fr-FR-DeniseNeural"))
        self.assertFalse(english_voice("en-US-AndrewNeural;rm"))
        self.assertEqual(safe_title("../../hello:*?"), "hello")

    def test_srt_offsets(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "voice.srt"
            count = write_srt(
                [([{"text": "Hello", "offset": 0, "duration": 5000000}], 900),
                 ([{"text": "world", "offset": 0, "duration": 5000000}], 900)],
                output)
            self.assertEqual(count, 1)
            data = output.read_text()
            self.assertIn("00:00:00,000 --> 00:00:01,400", data)
            self.assertIn("Hello world", data)
            self.assertEqual(srt_time(61001), "00:01:01,001")

    def test_srt_prefers_three_to_four_second_cues(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "Project.srt"
            words = [
                {"text": f"word{i}", "offset": i * 5_000_000,
                 "duration": 3_500_000}
                for i in range(20)
            ]
            count = write_srt([(words, 10_000)], output)
            self.assertEqual(count, 3)
            blocks = output.read_text(encoding="utf-8").strip().split("\n\n")
            self.assertEqual(len(blocks), 3)
            self.assertIn("00:00:00,000 --> 00:00:03,850", blocks[0])
            self.assertIn("00:00:04,000 --> 00:00:07,850", blocks[1])
            self.assertIn("00:00:08,000 --> 00:00:09,850", blocks[2])

    def test_srt_without_timing_fails_instead_of_generating_guess(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "Project.srt"
            with self.assertRaisesRegex(ValueError, "word timings"):
                write_srt([([], 2500)], output)
            self.assertFalse(output.exists())


class StorageTests(unittest.TestCase):
    def test_queue_restart_favorites_and_presets(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "database.sqlite"
            store = Store(path)
            job = store.add_job("one", "hello everyone", "en-US-AndrewNeural")
            store.update(job, status="processing", completed=1)
            self.assertTrue(store.toggle_favorite("en-US-AndrewNeural"))
            self.assertFalse(store.toggle_favorite("en-US-AndrewNeural"))
            self.assertTrue(store.toggle_favorite("en-GB-RyanNeural"))
            store.save_preset("Narrator", {"voice": "en-GB-RyanNeural", "rate": -5})
            store2 = Store(path)
            self.assertEqual(store2.get(job)["status"], "queued")
            self.assertEqual(store2.next_queued()["id"], job)
            self.assertIn("en-GB-RyanNeural", store2.favorites())
            self.assertEqual(store2.get_setting("presets")["Narrator"]["rate"], -5)
            with self.assertRaises(ValueError):
                store2.add_job("x", "", "en-US-AndrewNeural")
            with self.assertRaises(ValueError):
                store2.add_job("x", "valid", "de-DE-ConradNeural")


class RenderTests(unittest.TestCase):
    def test_real_ffmpeg_chunk_recovery_without_voice_network(self):
        binary = ffmpeg_path()
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            store = Store(root / "db.sqlite")
            script = ("This is a long sentence for repeatable audio tests. " * 160)
            job = store.add_job("Long Test", script, "en-US-AndrewNeural", subtitles=True)
            generated = []
            pause = [False]

            async def fake_synth(text, voice, rate, pitch, volume, path, stopped):
                generated.append(path.name)
                proc = subprocess.run(
                    [binary, "-hide_banner", "-loglevel", "error", "-y",
                     "-f", "lavfi", "-i", "sine=frequency=350:duration=0.13",
                     "-c:a", "libmp3lame", "-q:a", "5", str(path)],
                    capture_output=True, text=True, timeout=30)
                if proc.returncode:
                    raise RuntimeError(proc.stderr)
                return [{"text": "voice", "offset": 0, "duration": 900_000}]

            def on_progress(done, total):
                if done == 1:
                    pause[0] = True

            with self.assertRaises(RenderStopped):
                asyncio.run(render_job(
                    store, job, root / "output", root / "cache",
                    stopped=lambda: pause[0], progress=on_progress, synthesis=fake_synth))
            self.assertEqual(store.get(job)["status"], "paused")
            self.assertEqual(store.get(job)["completed"], 1)
            pause[0] = False
            store.set_status(job, "queued")
            result = asyncio.run(render_job(
                store, job, root / "output", root / "cache", synthesis=fake_synth))
            self.assertTrue(result.is_file())
            self.assertGreater(result.stat().st_size, 100)
            srt = result.with_suffix(".srt")
            self.assertTrue(srt.is_file())
            self.assertGreater(srt.stat().st_size, 20)
            self.assertEqual(result.stem, srt.stem)
            self.assertEqual(store.get(job)["status"], "done")
            self.assertEqual(len(generated), store.get(job)["total"])
            self.assertNotEqual(store.get(job)["total"], 0)


if __name__ == "__main__":
    unittest.main()
