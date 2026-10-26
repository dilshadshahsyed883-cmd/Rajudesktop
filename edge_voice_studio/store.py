"""Thread-safe-by-connection SQLite job and preference store."""
from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from uuid import uuid4

from .core import english_voice, split_script, safe_title


class Store:
    def __init__(self, db_path: str | Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connect() as con:
            con.executescript("""
                CREATE TABLE IF NOT EXISTS jobs (
                    id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    script TEXT NOT NULL,
                    voice TEXT NOT NULL,
                    rate INTEGER NOT NULL,
                    pitch INTEGER NOT NULL,
                    volume INTEGER NOT NULL,
                    subtitles INTEGER NOT NULL DEFAULT 1,
                    status TEXT NOT NULL DEFAULT 'queued',
                    completed INTEGER NOT NULL DEFAULT 0,
                    total INTEGER NOT NULL DEFAULT 0,
                    output TEXT NOT NULL DEFAULT '',
                    error TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                    updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS favorites (voice TEXT PRIMARY KEY);
            """)
            con.execute("UPDATE jobs SET status='queued' WHERE status='processing'")

    def connect(self):
        con = sqlite3.connect(str(self.path), timeout=15)
        con.row_factory = sqlite3.Row
        con.execute("PRAGMA busy_timeout=15000")
        con.execute("PRAGMA journal_mode=WAL")
        return con

    def add_job(self, title: str, script: str, voice: str, rate=0, pitch=0,
                volume=0, subtitles=True) -> str:
        if not english_voice(voice):
            raise ValueError("Select an English neural voice")
        chunks = split_script(script)
        for n, lo, hi in [(rate, -50, 50), (pitch, -100, 100), (volume, -50, 50)]:
            if not lo <= int(n) <= hi:
                raise ValueError("Voice control outside supported UI range")
        id_ = uuid4().hex
        with self.connect() as con:
            con.execute("""INSERT INTO jobs
                (id,title,script,voice,rate,pitch,volume,subtitles,total)
                VALUES (?,?,?,?,?,?,?,?,?)""",
                (id_, safe_title(title), script.strip(), voice, int(rate), int(pitch),
                 int(volume), int(bool(subtitles)), len(chunks)))
        return id_

    def all_jobs(self) -> list[dict]:
        with self.connect() as con:
            return [dict(r) for r in con.execute(
                "SELECT * FROM jobs ORDER BY created_at DESC, rowid DESC")]

    def get(self, id_: str) -> dict:
        with self.connect() as con:
            row = con.execute("SELECT * FROM jobs WHERE id=?", (id_,)).fetchone()
        if row is None:
            raise KeyError(id_)
        return dict(row)

    def next_queued(self) -> dict | None:
        with self.connect() as con:
            row = con.execute(
                "SELECT * FROM jobs WHERE status='queued' ORDER BY created_at, rowid LIMIT 1"
            ).fetchone()
            return dict(row) if row is not None else None

    def update(self, id_: str, *, status: str | None = None, completed: int | None = None,
               output: str | None = None, error: str | None = None) -> None:
        fields, params = [], []
        for key, val in (("status", status), ("completed", completed),
                         ("output", output), ("error", error)):
            if val is not None:
                fields.append(f"{key}=?")
                params.append(val)
        if not fields:
            return
        with self.connect() as con:
            con.execute(
                "UPDATE jobs SET " + ", ".join(fields) +
                ", updated_at=CURRENT_TIMESTAMP WHERE id=?", (*params, id_))

    def set_status(self, id_: str, status: str) -> None:
        if status not in {"queued", "paused", "cancelled", "failed"}:
            raise ValueError("Invalid user status")
        with self.connect() as con:
            con.execute("UPDATE jobs SET status=?, updated_at=CURRENT_TIMESTAMP "
                        "WHERE id=?", (status, id_))

    def delete_job(self, id_: str) -> None:
        with self.connect() as con:
            row = con.execute("SELECT status FROM jobs WHERE id=?", (id_,)).fetchone()
            if row and row["status"] == "processing":
                raise RuntimeError("Pause the active job before removing it")
            con.execute("DELETE FROM jobs WHERE id=?", (id_,))

    def get_setting(self, key: str, default=None):
        with self.connect() as con:
            row = con.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return json.loads(row["value"]) if row is not None else default

    def set_setting(self, key: str, value) -> None:
        with self.connect() as con:
            con.execute("INSERT INTO settings(key,value) VALUES(?,?) "
                        "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                        (key, json.dumps(value, ensure_ascii=False)))

    def favorites(self) -> set[str]:
        with self.connect() as con:
            return {r["voice"] for r in con.execute("SELECT voice FROM favorites")}

    def toggle_favorite(self, voice: str) -> bool:
        if not english_voice(voice):
            raise ValueError("Favorites are restricted to English voices")
        with self.connect() as con:
            exists = con.execute("SELECT 1 FROM favorites WHERE voice=?", (voice,)).fetchone()
            if exists:
                con.execute("DELETE FROM favorites WHERE voice=?", (voice,))
                return False
            con.execute("INSERT INTO favorites(voice) VALUES(?)", (voice,))
            return True

    def save_preset(self, name: str, values: dict):
        presets = self.get_setting("presets", {})
        presets[name[:50]] = values
        self.set_setting("presets", presets)
