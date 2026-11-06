"""Offline regression coverage for bounded PC Edge TTS throughput and stalls."""
import asyncio
import os
import sqlite3
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from edge_voice_studio.core import split_script
from edge_voice_studio.engine import (
    RenderStopped, edge_stream_count, render_job,
)
from edge_voice_studio.store import Store


SCRIPT = "Narration testing with full sentences and stable boundaries. " * 230


def pretend_concat(parts, output):
    assert all(p.is_file() and p.stat().st_size > 0 for p in parts)
    output.write_bytes(b"verified ordered audio fixture")


class SlowVoiceTests(unittest.TestCase):
    def test_five_streams_default_and_one_stream_fallback(self):
        with patch.dict(os.environ, {"EDGE_VOICE_STREAMS": "5"}):
            self.assertEqual(edge_stream_count(), 5)
        with patch.dict(os.environ, {"EDGE_VOICE_STREAMS": "1"}):
            self.assertEqual(edge_stream_count(), 1)
        with patch.dict(os.environ, {"EDGE_VOICE_STREAMS": "30"}):
            self.assertEqual(edge_stream_count(), 5)
        with patch.dict(os.environ, {"EDGE_VOICE_STREAMS": "broken"}):
            self.assertEqual(edge_stream_count(), 5)
        self.assertEqual(edge_stream_count(3), 3)
        self.assertEqual(edge_stream_count(5), 5)
        self.assertEqual(edge_stream_count(10), 5)

    def test_bounded_concurrency_preserves_order_and_queue_outputs(self):
        self.assertGreaterEqual(len(split_script(SCRIPT)), 5)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"EDGE_VOICE_STREAMS": "1"}), \
             patch("edge_voice_studio.engine.concat_mp3", side_effect=pretend_concat):
            root = Path(tmp)
            store = Store(root / "jobs.db")
            jid = store.add_job("long", SCRIPT, "en-US-AndrewNeural", subtitles=True)
            active = 0
            peak = 0
            generated = []
            seen = []

            async def fake(text, voice, rate, pitch, volume, target, stopped):
                nonlocal active, peak
                self.assertFalse(stopped())
                active += 1
                peak = max(active, peak)
                try:
                    await asyncio.sleep(0.015)
                    self.assertFalse(stopped())
                    target.write_bytes(b"fake mp3")
                    generated.append(target.name)
                    return []
                finally:
                    active -= 1

            output = asyncio.run(render_job(
                store, jid, root / "output", root / "cache",
                synthesis=fake, parallel_chunks=5,
                progress=lambda done, total: seen.append(done)))
            row = store.get(jid)
            self.assertEqual(peak, 5)
            self.assertEqual(active, 0)
            self.assertEqual(row["status"], "done")
            self.assertEqual(row["srt_status"], "pending")
            self.assertEqual(row["completed"], row["total"])
            self.assertEqual(seen, list(range(1, row["total"] + 1)))
            self.assertEqual(len(generated), row["total"])
            self.assertTrue(output.exists())
            logs = list((root / "cache").rglob("performance.log"))
            self.assertEqual(len(logs), 1)
            self.assertIn("event=success", logs[0].read_text())

    def test_pause_and_restart_reuse_completed_chunk_pairs(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"EDGE_VOICE_STREAMS": "2"}), \
             patch("edge_voice_studio.engine.concat_mp3", side_effect=pretend_concat):
            root = Path(tmp)
            store = Store(root / "db")
            jid = store.add_job("pause", SCRIPT, "en-US-AndrewNeural", subtitles=False)
            stop = [False]
            called = []

            async def fake(text, voice, rate, pitch, volume, target, stopped):
                called.append(target.name)
                await asyncio.sleep(0.015)
                if stopped():
                    raise RenderStopped("Paused")
                target.write_bytes(b"fake mp3")
                return []

            def progress(done, total):
                if done == 1:
                    stop[0] = True

            with self.assertRaises(RenderStopped):
                asyncio.run(render_job(
                    store, jid, root / "out", root / "cache",
                    synthesis=fake, stopped=lambda: stop[0], progress=progress))
            self.assertEqual(store.get(jid)["status"], "paused")
            self.assertGreaterEqual(store.get(jid)["completed"], 1)
            first_run_count = len(called)
            stop[0] = False
            store.set_status(jid, "queued")
            result = asyncio.run(render_job(
                store, jid, root / "out", root / "cache", synthesis=fake))
            self.assertTrue(result.is_file())
            self.assertEqual(store.get(jid)["status"], "done")
            self.assertLessEqual(len(called), first_run_count + store.get(jid)["total"])
            self.assertIn("event=cached", next((root / "cache").rglob("performance.log")).read_text())

    def test_new_job_chunk_setting_persists_per_job_and_restart(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "settings.db"
            store = Store(db)
            old = store.add_job("old", SCRIPT, "en-US-AndrewNeural")
            store.set_setting("chunk_size", 1200)
            new = store.add_job("new", SCRIPT, "en-US-AndrewNeural",
                                chunk_size=store.get_setting("chunk_size", 2600))
            self.assertEqual(store.get(old)["chunk_size"], 2600)
            self.assertEqual(store.get(new)["chunk_size"], 1200)
            self.assertEqual(store.get(old)["total"], len(split_script(SCRIPT, limit=2600)))
            self.assertEqual(store.get(new)["total"], len(split_script(SCRIPT, limit=1200)))
            store2 = Store(db)
            store2.set_setting("chunk_size", 800)
            self.assertEqual(store2.get(old)["chunk_size"], 2600)
            self.assertEqual(store2.get(new)["chunk_size"], 1200)
            self.assertEqual(store2.get_setting("chunk_size"), 800)
            with self.assertRaisesRegex(ValueError, "Chunk size"):
                store2.add_job("invalid", SCRIPT, "en-US-AndrewNeural",
                               chunk_size=100)

    def test_pre_settings_db_migration_keeps_default_2600(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            with sqlite3.connect(db) as connection:
                connection.execute("""CREATE TABLE jobs(
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, script TEXT NOT NULL,
                    voice TEXT NOT NULL, rate INTEGER NOT NULL,
                    pitch INTEGER NOT NULL, volume INTEGER NOT NULL,
                    subtitles INTEGER NOT NULL DEFAULT 1,
                    srt_status TEXT NOT NULL DEFAULT 'off',
                    srt_error TEXT NOT NULL DEFAULT '',
                    status TEXT NOT NULL DEFAULT 'queued',
                    completed INTEGER NOT NULL DEFAULT 0, total INTEGER NOT NULL DEFAULT 0,
                    output TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
                connection.execute(
                    "INSERT INTO jobs(id,title,script,voice,rate,pitch,volume,total) "
                    "VALUES ('legacy','old',?,'en-US-AndrewNeural',0,0,0,?)",
                    (SCRIPT, len(split_script(SCRIPT))))
            store = Store(db)
            self.assertEqual(store.get("legacy")["chunk_size"], 2600)
            self.assertEqual(store.get("legacy")["total"], len(split_script(SCRIPT)))
            self.assertEqual(Store(db).get("legacy")["chunk_size"], 2600)

    def test_selected_chunk_size_is_used_for_render_not_current_preference(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"EDGE_VOICE_STREAMS": "2"}), \
             patch("edge_voice_studio.engine.concat_mp3", side_effect=pretend_concat):
            root = Path(tmp)
            store = Store(root / "db")
            jid = store.add_job("small", SCRIPT, "en-US-AndrewNeural",
                                subtitles=False, chunk_size=800)
            store.set_setting("chunk_size", 2600)
            samples = []

            async def fake(text, voice, rate, pitch, volume, target, stopped):
                samples.append(text)
                target.write_bytes(b"fake mp3")
                return []

            output = asyncio.run(render_job(store, jid, root / "out", root / "cache",
                                            synthesis=fake))
            self.assertTrue(output.is_file())
            self.assertTrue(all(len(t) <= 800 for t in samples))
            self.assertEqual(len(samples), len(split_script(SCRIPT, limit=800)))
            self.assertEqual(store.get(jid)["completed"], len(samples))

    def test_hung_network_chunk_has_bounded_attempts_and_no_final_mp3(self):
        with tempfile.TemporaryDirectory() as tmp, \
             patch.dict(os.environ, {"EDGE_VOICE_STREAMS": "1"}), \
             patch("edge_voice_studio.engine.SYNTH_TIMEOUT_SECONDS", 0.01):
            root = Path(tmp)
            store = Store(root / "db")
            jid = store.add_job("slow", "Hello world.", "en-US-AndrewNeural")
            attempts = []

            async def hanging(text, voice, rate, pitch, volume, target, stopped):
                attempts.append(1)
                await asyncio.sleep(60)
                return []

            with self.assertRaisesRegex(RuntimeError, "TimeoutError"):
                asyncio.run(render_job(
                    store, jid, root / "output", root / "cache", synthesis=hanging))
            self.assertEqual(len(attempts), 3)
            self.assertEqual(store.get(jid)["status"], "failed")
            self.assertEqual(list((root / "output").glob("*.mp3")), [])
            diag = next((root / "cache").rglob("performance.log")).read_text()
            self.assertEqual(diag.count("event=timeout"), 3)


if __name__ == "__main__":
    unittest.main()
