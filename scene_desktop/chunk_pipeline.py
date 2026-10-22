"""Frame-aligned render chunks, durable checkpoints and verified restart reuse.

Only the caller-designated cache directory is touched. A checkpoint is not a
license to trust a partial MP4: each committed chunk is SHA-256 checked before
reuse, and its receipt matches the exact frame range and content fingerprint.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import hashlib
import json
import math
import os
import tempfile


@dataclass(frozen=True)
class Chunk:
    start_frame: int
    end_frame: int
    start_ms: int
    end_ms: int

    @property
    def frames(self) -> int:
        return self.end_frame - self.start_frame


def plan_chunks(project, start_ms: int, end_ms: int,
                max_ms: int = 5000) -> list[Chunk]:
    """Global frame grid + edit boundaries: edits never shift earlier chunks.

    At final export, chunk edges are snapped to project frame boundaries.
    Preview windows can begin at arbitrary times and are quantized similarly.
    """
    fps = project.fps
    first = max(0, round(start_ms * fps / 1000))
    last = max(first + 1, math.ceil(end_ms * fps / 1000))
    span = max(1, round(max_ms * fps / 1000))
    bounds = {first, last}
    for frame in range(((first // span) + 1) * span, last, span):
        bounds.add(frame)
    for item in project.items:
        if item.kind not in {"image", "video", "text"}:
            continue
        for edge in (item.start_ms, item.end_ms):
            frame = round(edge * fps / 1000)
            if first < frame < last:
                bounds.add(frame)
    frames = sorted(bounds)
    return [
        Chunk(left, right, round(left * 1000 / fps), round(right * 1000 / fps))
        for left, right in zip(frames, frames[1:]) if right > left
    ]


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def _write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n",
                                     dir=path.parent, prefix=".chunk-", suffix=".tmp",
                                     delete=False) as file:
        temporary = Path(file.name)
        json.dump(value, file, ensure_ascii=False, sort_keys=True)
        file.flush()
        os.fsync(file.fileno())
    try:
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


class ChunkStore:
    """Content-addressed chunk store with SHA receipts and resumable job index."""

    def __init__(self, cache_dir: str | Path):
        self.root = Path(cache_dir).expanduser().resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.receipts = self.root / "chunk-receipts"
        self.jobs = self.root / "render-jobs"

    def section_path(self, key: str) -> Path:
        return self.root / f"{key}.mp4"

    def receipt_path(self, key: str) -> Path:
        return self.receipts / f"{key}.json"

    def valid(self, key: str, chunk: Chunk) -> bool:
        path = self.section_path(key)
        receipt = self.receipt_path(key)
        if not path.is_file() or path.is_symlink() or not receipt.is_file():
            return False
        try:
            data = json.loads(receipt.read_text(encoding="utf-8"))
            return (data.get("schema") == 1 and data.get("key") == key
                    and data.get("first_frame") == chunk.start_frame
                    and data.get("end_frame") == chunk.end_frame
                    and data.get("bytes") == path.stat().st_size
                    and data["bytes"] > 1000
                    and data.get("sha256") == file_sha256(path))
        except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
            return False

    def commit(self, key: str, chunk: Chunk, source: Path) -> Path:
        """Publish complete MP4 first; receipt last marks it safe for reuse."""
        if not source.is_file() or source.stat().st_size <= 1000:
            raise RuntimeError("Cannot checkpoint incomplete chunk")
        dest = self.section_path(key)
        temporary = dest.with_suffix(".incoming")
        self.receipt_path(key).unlink(missing_ok=True)
        try:
            with source.open("rb") as inp, temporary.open("wb") as out:
                while block := inp.read(1024 * 1024):
                    out.write(block)
                out.flush()
                os.fsync(out.fileno())
            os.replace(temporary, dest)
        finally:
            temporary.unlink(missing_ok=True)
        _write_json_atomic(self.receipt_path(key), {
            "schema": 1, "key": key,
            "first_frame": chunk.start_frame,
            "end_frame": chunk.end_frame,
            "bytes": dest.stat().st_size,
            "sha256": file_sha256(dest),
        })
        return dest

    def job_path(self, output: Path) -> Path:
        return self.jobs / (hashlib.sha256(
            str(output.resolve()).encode("utf-8")).hexdigest() + ".json")

    def checkpoint(self, output: Path, signatures: list[str],
                   verified: list[str], state: str) -> None:
        # The chunk files, not the job index, are the resumable truth.
        _write_json_atomic(self.job_path(output), {
            "schema": 1, "output": str(output.resolve()), "state": state,
            "planned": signatures, "verified": verified,
        })
