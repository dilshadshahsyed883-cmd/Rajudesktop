"""Offline integration tests for the one-checkbox Edge-to-Whisper pipeline."""
import asyncio
from pathlib import Path
import sqlite3
import subprocess
import tempfile
import unittest
from unittest.mock import patch

from edge_voice_studio.engine import ffmpeg_path, render_job
from edge_voice_studio.store import Store
from edge_voice_studio.srt_tasks import transcribe_completed_voice
from voice_to_srt_batch.voice_to_srt_studio.engine import Word, build_cues


class AutomaticSRTTests(unittest.TestCase):
    def test_submission_toggle_and_restart_migration(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "state.db"
            store = Store(path)
            yes = store.add_job("yes", "first narration", "en-US-AndrewNeural", subtitles=True)
            no = store.add_job("no", "second narration", "en-US-AndrewNeural", subtitles=False)
            self.assertEqual(store.get(yes)["srt_status"], "waiting")
            self.assertEqual(store.get(no)["srt_status"], "off")
            self.assertIsNone(store.claim_srt_job())
            store.complete_voice(yes, str(Path(tmp) / "yes.mp3"), 1)
            store.complete_voice(no, str(Path(tmp) / "no.mp3"), 1)
            self.assertEqual(store.claim_srt_job()["id"], yes)
            self.assertIsNone(store.claim_srt_job())
            # Crash recovery returns interrupted SRT to pending.
            again = Store(path)
            self.assertEqual(again.get(yes)["srt_status"], "pending")
            self.assertEqual(again.claim_srt_job()["id"], yes)
            again.set_srt_status(yes, "failed", "model unavailable")
            self.assertEqual(again.get(yes)["status"], "done")
            self.assertEqual(again.get(yes)["srt_error"], "model unavailable")
            again.retry_srt(yes)
            self.assertEqual(again.get(yes)["srt_status"], "pending")
            self.assertEqual(again.get(no)["srt_status"], "off")

    def test_legacy_sqlite_schema_migrates_without_retranscription(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = Path(tmp) / "legacy.db"
            with sqlite3.connect(db) as con:
                con.execute("""CREATE TABLE jobs (
                    id TEXT PRIMARY KEY, title TEXT NOT NULL, script TEXT NOT NULL,
                    voice TEXT NOT NULL, rate INTEGER NOT NULL, pitch INTEGER NOT NULL,
                    volume INTEGER NOT NULL, subtitles INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'queued', completed INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0, output TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)""")
                con.execute("""INSERT INTO jobs (id,title,script,voice,rate,pitch,volume,
                    subtitles,status,total) VALUES ('old','old','text',
                    'en-US-AndrewNeural',0,0,0,1,'done',1)""")
            store = Store(db)
            self.assertEqual(store.get("old")["srt_status"], "off")
            self.assertIsNone(store.claim_srt_job())

    def test_mp3_success_precedes_srt_and_turned_off_stays_off(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            store = Store(root / "db")
            yes = store.add_job("yes", "This is a real audio test", "en-US-AndrewNeural")
            no = store.add_job("no", "This is another audio test",
                               "en-US-AndrewNeural", subtitles=False)
            async def synth(text, voice, rate, pitch, volume, path, stopped):
                proc = subprocess.run(
                    [ffmpeg_path(), "-hide_banner", "-loglevel", "error",
                     "-f", "lavfi", "-i", "sine=frequency=400:duration=0.3",
                     "-c:a", "libmp3lame", "-q:a", "5", "-y", str(path)],
                    capture_output=True, text=True, timeout=30)
                if proc.returncode:
                    raise RuntimeError(proc.stderr)
                return []
            for job in (yes, no):
                audio = asyncio.run(render_job(
                    store, job, root / "narrations", root / "cache", synthesis=synth))
                self.assertTrue(audio.is_file())
                self.assertFalse(audio.with_suffix(".srt").exists())
            self.assertEqual(store.get(yes)["srt_status"], "pending")
            self.assertEqual(store.get(no)["srt_status"], "off")
            self.assertEqual(store.claim_srt_job()["id"], yes)

    def test_same_folder_accurate_grouping_and_existing_srt(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "Project.mp3"
            audio.write_bytes(b"mp3 placeholder for mocked alignment")
            mock_cues = build_cues([
                Word(" Hello", 0.0, 1.2), Word(" world", 1.2, 3.6),
                Word(" Again", 4.0, 5.3), Word(" today", 5.3, 7.3),
            ])
            with patch("edge_voice_studio.srt_tasks.transcribe_one", return_value=mock_cues) as transcribe:
                result = transcribe_completed_voice(audio, object(), lambda: False)
                self.assertEqual(result, "done")
                self.assertEqual(transcribe.call_count, 1)
                self.assertEqual(transcribe.call_args.args[2], "Recommended (3-4 sec)")
            target = root / "Project.srt"
            self.assertIn("00:00:00,000 --> 00:00:03,600", target.read_text())
            original = target.read_bytes()
            self.assertEqual(transcribe_completed_voice(audio, None, lambda: False), "skipped")
            self.assertEqual(target.read_bytes(), original)

    def test_failed_transcription_preserves_voice_and_retry(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            audio = root / "Project.mp3"
            audio.write_bytes(b"do not delete")
            with patch("edge_voice_studio.srt_tasks.transcribe_one", side_effect=RuntimeError("offline")):
                with self.assertRaisesRegex(RuntimeError, "offline"):
                    transcribe_completed_voice(audio, object(), lambda: False)
            self.assertEqual(audio.read_bytes(), b"do not delete")
            self.assertFalse(audio.with_suffix(".srt").exists())


if __name__ == "__main__":
    unittest.main()
