"""Read-only bridge from Desktop SML's own SQLite to Scene Editor catalog.

Both libraries stay independent. This bridge only reads SML's DB and
registers *existing* verified local media paths in the editor SQLite;
it does not copy/re-encode/delete original SML files or modify SML rows.
"""
from __future__ import annotations
from pathlib import Path
from types import SimpleNamespace
import hashlib
import json
import sqlite3
from contextlib import closing
import threading

from .library import MediaLibrary

LOCAL_ORIGIN = "desktop-local://self-media-library"


def hash_file(path: Path) -> str:
    sha=hashlib.sha256()
    with path.open("rb") as source:
        for block in iter(lambda:source.read(1024*1024),b""):
            sha.update(block)
    return sha.hexdigest()


def sync_approved_media(root: Path, library: MediaLibrary, *,
                        limit: int = 10000,
                        cancel: threading.Event | None = None,
                        progress=None) -> dict:
    data=Path(root).expanduser().resolve()
    database=data/"library.db"
    if not database.is_file():
        return {"added":0,"skipped":0,"errors":["SML database not initialized"]}
    uri=f"file:{database.as_posix()}?mode=ro"
    with closing(sqlite3.connect(uri,uri=True,timeout=10)) as conn:
        conn.row_factory=sqlite3.Row
        rows=[]
        for row in conn.execute(
            """SELECT c.id AS remote_id, c.filename AS stored_name,
                      c.sha256 AS digest, c.source_id, 'video' AS kind
               FROM clips c WHERE c.deleted_at IS NULL AND c.status='approved'
               ORDER BY c.created_at DESC LIMIT ?""",(limit,)
        ):
            item=dict(row)
            item["keywords"]=[x[0] for x in conn.execute(
                "SELECT keyword FROM clip_keywords WHERE clip_id=?",
                (item["remote_id"],)).fetchall()]
            rows.append(item)
        if len(rows)<limit:
            for row in conn.execute(
                """SELECT id AS remote_id, stored_name, sha256 AS digest,
                          'image' AS kind, keywords_json
                   FROM image_assets WHERE deleted_at IS NULL AND status='approved'
                   ORDER BY created_at DESC LIMIT ?""",(limit-len(rows),)
            ):
                item=dict(row)
                try:
                    item["keywords"]=json.loads(item.pop("keywords_json") or "[]")
                except (ValueError,TypeError):
                    item["keywords"]=[]
                item["source_id"]=item["remote_id"]
                rows.append(item)
    existing={r["remote_id"]:r for r in library.sml_imports(LOCAL_ORIGIN)}
    added=skipped=0
    errors=[]
    for index,item in enumerate(rows):
        if cancel and cancel.is_set():
            break
        target=(data/("clips" if item["kind"]=="video" else "images")/
                item["stored_name"]).resolve()
        if not target.is_relative_to(data) or not target.is_file() or target.is_symlink():
            errors.append(f"{item['remote_id']}: missing/unsafe path")
            continue
        digest=str(item.get("digest") or "").lower()
        if len(digest)!=64 or any(x not in "0123456789abcdef" for x in digest):
            errors.append(f"{item['remote_id']}: invalid stored digest")
            continue
        if item["remote_id"] in existing and existing[item["remote_id"]]["remote_sha256"]==digest:
            # Do not re-hash/reindex if already registered and file is intact.
            skipped+=1
            continue
        if hash_file(target)!=digest:
            errors.append(f"{item['remote_id']}: SHA-256 mismatch")
            continue
        try:
            record=library.ingest(target)
            tags=list(dict.fromkeys(
                [*record["tags"],"offline-sml",f"sml:{item['remote_id']}",
                 *(str(x)[:60] for x in item.get("keywords",[])[:40] if str(x).strip())]
            ))
            library.set_tags(record["id"],tags)
            library.set_status([record["id"]],"approved")
            library.record_sml_import(
                LOCAL_ORIGIN,
                SimpleNamespace(id=item["remote_id"],sha256=digest,
                                kind=item["kind"],source_id=item["source_id"]),
                record["id"],index
            )
            added+=1
        except (OSError,ValueError,RuntimeError) as exc:
            errors.append(f"{item['remote_id']}: {type(exc).__name__}")
        if progress and index%25==0:
            progress(index+1,len(rows))
    return {"added":added,"skipped":skipped,"errors":errors[:40],
            "scanned":len(rows),"cancelled":bool(cancel and cancel.is_set())}
