"""Local media catalog, thumbnails, approvals, tags and exact duplicate review."""
from __future__ import annotations
from pathlib import Path
from contextlib import contextmanager
import hashlib
import json
import sqlite3
import subprocess
import threading

from .core import classify
from .media import duration_ms, ffmpeg_path


class MediaLibrary:
    def __init__(self, database: str | Path):
        self.database = Path(database).expanduser()
        self.database.parent.mkdir(parents=True, exist_ok=True)
        self.cache = self.database.parent / "thumbnails"
        self.cache.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        with self._db() as conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS media (
              id TEXT PRIMARY KEY, path TEXT NOT NULL UNIQUE,
              sha256 TEXT NOT NULL, kind TEXT NOT NULL, duration_ms INTEGER NOT NULL,
              size_bytes INTEGER NOT NULL, name TEXT NOT NULL, tags TEXT NOT NULL DEFAULT '[]',
              status TEXT NOT NULL DEFAULT 'candidate', thumbnail TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS media_hash ON media(sha256);
            CREATE INDEX IF NOT EXISTS media_status ON media(status);
            """)

    @contextmanager
    def _db(self):
        conn = sqlite3.connect(self.database, timeout=20)
        conn.row_factory = sqlite3.Row
        try:
            conn.execute("PRAGMA busy_timeout=20000")
            with conn:
                yield conn
        finally:
            conn.close()

    @staticmethod
    def digest(path: Path) -> str:
        sha = hashlib.sha256()
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                sha.update(chunk)
        return sha.hexdigest()

    def ingest(self, path: str | Path) -> dict:
        source = Path(path).expanduser().resolve()
        if not source.is_file():
            raise FileNotFoundError(str(source))
        kind = classify(str(source))
        info = source.stat()
        identity = self.digest(source)
        media_id = hashlib.sha256(str(source).encode("utf-8")).hexdigest()[:24]
        duration = duration_ms(str(source))
        with self._lock, self._db() as conn:
            current = conn.execute("SELECT * FROM media WHERE path=?", (str(source),)).fetchone()
            tags = current["tags"] if current else "[]"
            status = current["status"] if current and current["sha256"] == identity else "candidate"
            conn.execute("""INSERT INTO media
                (id, path, sha256, kind, duration_ms, size_bytes, name, tags, status)
                VALUES (?,?,?,?,?,?,?,?,?)
                ON CONFLICT(path) DO UPDATE SET
                  sha256=excluded.sha256, kind=excluded.kind,
                  duration_ms=excluded.duration_ms, size_bytes=excluded.size_bytes,
                  name=excluded.name, tags=excluded.tags, status=excluded.status""",
                (media_id, str(source), identity, kind, duration, info.st_size, source.name, tags, status))
        return self.get(media_id)

    def import_folder(self, folder: str | Path, max_files: int = 5000) -> tuple[list[dict], list[str]]:
        root = Path(folder).expanduser().resolve()
        if not root.is_dir():
            raise NotADirectoryError(str(root))
        records, errors = [], []
        for candidate in root.rglob("*"):
            if len(records) >= max_files:
                errors.append(f"Scan limited to {max_files} files")
                break
            if not candidate.is_file():
                continue
            try:
                classify(str(candidate))
            except ValueError:
                continue
            try:
                records.append(self.ingest(candidate))
            except Exception as exc:
                errors.append(f"{candidate.name}: {exc}")
        return records, errors

    def get(self, media_id: str) -> dict:
        with self._lock, self._db() as conn:
            item = conn.execute("SELECT * FROM media WHERE id=?", (media_id,)).fetchone()
        if not item:
            raise KeyError(media_id)
        return self._plain(item)

    @staticmethod
    def _plain(row) -> dict:
        value = dict(row)
        value["tags"] = json.loads(value["tags"])
        value["missing"] = not Path(value["path"]).is_file()
        return value

    def list(self, search: str = "", status: str = "", kind: str = "") -> list[dict]:
        filters, args = [], []
        if search:
            filters.append("(lower(name) LIKE ? OR lower(tags) LIKE ?)")
            args.extend([f"%{search.lower()}%"] * 2)
        if status:
            filters.append("status=?")
            args.append(status)
        if kind:
            filters.append("kind=?")
            args.append(kind)
        sql = "SELECT * FROM media" + (" WHERE " + " AND ".join(filters) if filters else "") + " ORDER BY name"
        with self._lock, self._db() as conn:
            return [self._plain(x) for x in conn.execute(sql, args).fetchall()]

    def set_status(self, media_ids: list[str], status: str) -> int:
        if status not in {"candidate", "approved", "rejected"}:
            raise ValueError("Unknown status")
        if not media_ids:
            return 0
        with self._lock, self._db() as conn:
            cursor = conn.executemany("UPDATE media SET status=? WHERE id=?", [(status, x) for x in media_ids])
            return cursor.rowcount

    def set_tags(self, media_id: str, tags: list[str]):
        value = [x.strip() for x in tags if x.strip()]
        with self._lock, self._db() as conn:
            conn.execute("UPDATE media SET tags=? WHERE id=?", (json.dumps(value), media_id))

    def duplicates(self) -> list[list[dict]]:
        with self._lock, self._db() as conn:
            groups = conn.execute(
                "SELECT sha256 FROM media GROUP BY sha256 HAVING count(*)>1"
            ).fetchall()
            result = []
            for group in groups:
                rows = conn.execute("SELECT * FROM media WHERE sha256=?", (group[0],)).fetchall()
                result.append([self._plain(x) for x in rows])
        return result

    def thumbnail(self, media_id: str) -> Path:
        item = self.get(media_id)
        output = self.cache / (item["sha256"][:20] + ".jpg")
        if output.is_file() and output.stat().st_size > 0:
            return output
        if item["missing"]:
            raise FileNotFoundError(item["path"])
        ffmpeg = ffmpeg_path()
        cmd = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y"]
        if item["kind"] == "video":
            cmd += ["-ss", f"{min(item['duration_ms']/2500, 12):.3f}"]
        cmd += ["-i", item["path"], "-frames:v", "1", "-vf",
                "scale=w=320:h=180:force_original_aspect_ratio=decrease,"
                "pad=320:180:(ow-iw)/2:(oh-ih)/2", str(output)]
        subprocess.run(cmd, check=True, timeout=45, capture_output=True)
        return output

    def summary(self) -> dict:
        rows = self.list()
        return {"total": len(rows), "images": sum(r["kind"]=="image" for r in rows),
                "videos": sum(r["kind"]=="video" for r in rows),
                "approved": sum(r["status"]=="approved" for r in rows),
                "selected": 0, "missing": sum(r["missing"] for r in rows)}
