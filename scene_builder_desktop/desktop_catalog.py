"""Disk-backed, Scene Builder-only Windows media import.

Original input files are never modified. Imported assets are copied to an
isolated library under Documents, retaining the VPS catalog's filenames, IDs,
hash deduplication and approved status.
"""
from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import tempfile
import uuid

from .scene_media_library import ALLOWED, InvalidMedia, SceneMediaLibrary, _signature_ok


class DesktopCatalog(SceneMediaLibrary):
    def import_path(self, source: str | Path) -> dict:
        candidate = Path(source).expanduser()
        if candidate.is_symlink() or not candidate.is_file():
            raise InvalidMedia("Source must be a regular local file, not a symlink")
        src = candidate.resolve(strict=True)
        name = src.name[:180]
        ext = src.suffix.casefold()
        kind = ALLOWED.get(ext)
        if not kind:
            raise InvalidMedia("Unsupported video/image extension: " + ext)
        digest = hashlib.sha256()
        total = 0
        header = b""
        fd, temp_name = tempfile.mkstemp(prefix=".scene-pc-", dir=str(self.assets))
        try:
            with os.fdopen(fd, "wb") as out, src.open("rb") as stream:
                while True:
                    data = stream.read(1024 * 1024)
                    if not data:
                        break
                    total += len(data)
                    digest.update(data)
                    if len(header) < 32:
                        header = (header + data)[:32]
                    out.write(data)
                out.flush()
                os.fsync(out.fileno())
            if total < 12 or not _signature_ok(ext, header):
                raise InvalidMedia("File signature does not match " + ext)
            with self.lock:
                with self._db() as conn:
                    found = conn.execute(
                        "SELECT * FROM media WHERE sha256=? AND bytes=? LIMIT 1",
                        (digest.hexdigest(), total),
                    ).fetchone()
                    if found is not None:
                        return {**self._row(found), "duplicate": True}
                    media_id = uuid.uuid4().hex
                    destination = self.assets / (media_id + ext)
                    os.replace(temp_name, destination)
                    try:
                        conn.execute(
                            """INSERT INTO media(id,original_name,kind,extension,bytes,sha256,approved,created_at)
                            VALUES(?,?,?,?,?,?,1,?)""",
                            (media_id, name, kind, ext, total, digest.hexdigest(),
                             datetime.now(timezone.utc).isoformat()),
                        )
                    except Exception:
                        destination.unlink(missing_ok=True)
                        raise
                return {**self._row(self._one(media_id)), "duplicate": False}
        finally:
            try:
                os.unlink(temp_name)
            except FileNotFoundError:
                pass
