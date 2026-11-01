"""Guarded receipt verification for an ORIGINAL CapCut-produced MP4.

This does not render video, invoke private CapCut methods, or assert that an
MP4 was produced by CapCut. The *trusted in-process host* must prove the
original engine accepted the exact draft and output destination before calling
begin_export, and emit exportVerified only after verify_completed succeeds.

ffprobe is only a read-only validator, NEVER a replacement renderer.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time
from typing import Callable


class NativeOutputError(ValueError):
    """The candidate output cannot safely complete the active native job."""


@dataclass(frozen=True)
class ExportTicket:
    key: str
    draft_id: str
    project_path: str
    output_path: Path
    admission_started_ns: int


@dataclass(frozen=True)
class VerifiedOutput:
    key: str
    output_path: str
    sha256: str
    size_bytes: int
    duration_seconds: float
    width: int
    height: int


def _canonical(path: os.PathLike[str] | str) -> Path:
    if not isinstance(path, (str, os.PathLike)) or not str(path):
        raise NativeOutputError("An explicit absolute path is required")
    p = Path(path)
    if not p.is_absolute():
        raise NativeOutputError("Relative paths cannot identify a native output")
    if p.is_symlink():
        raise NativeOutputError("Symlink paths are not accepted")
    return p.resolve(strict=False)


def begin_export(key: str, draft_id: str, project_path: str, output_path: str,
                 *, now_ns: Callable[[], int] = time.time_ns) -> ExportTicket:
    """Prepare the ticket immediately BEFORE native job submission.

    Host must only trust this ticket after the original engine confirms
    admission for the exact draft/target pair. Pre-existing files are
    rejected rather than overwritten or mistaken for a new output.
    """
    if not all(isinstance(x, str) and x.strip() for x in
               (key, draft_id, project_path, output_path)):
        raise NativeOutputError("Draft identity, project and target must be set")
    source = _canonical(project_path)
    output = _canonical(output_path)
    if output.suffix.lower() != ".mp4":
        raise NativeOutputError("Native completion target must be MP4")
    if output == source or output.is_dir() or output.exists():
        raise NativeOutputError("Output target exists or conflicts with source")
    # The host still owns proof that the original CapCut engine admitted this
    # exact (draft ID, source path, target path) tuple.
    return ExportTicket(key, draft_id, str(source), output, now_ns())


def _probe_json(path: Path, *, executable: str, timeout_seconds: float) -> dict:
    try:
        process = subprocess.run(
            [executable, "-v", "error", "-show_entries",
             "format=duration:stream=codec_type,width,height,duration",
             "-of", "json", str(path)],
            check=False, capture_output=True, text=True,
            timeout=timeout_seconds,
        )
    except (FileNotFoundError, OSError, subprocess.TimeoutExpired) as exc:
        raise NativeOutputError("ffprobe validation unavailable or timed out") from exc
    if process.returncode != 0:
        raise NativeOutputError("MP4 fails ffprobe decode/header inspection")
    try:
        parsed = json.loads(process.stdout)
    except (json.JSONDecodeError, ValueError) as exc:
        raise NativeOutputError("ffprobe returned malformed metadata") from exc
    if not isinstance(parsed, dict):
        raise NativeOutputError("ffprobe metadata must be an object")
    return parsed


def verify_completed(ticket: ExportTicket, reported_path: str, *,
                     executable: str = "ffprobe", timeout_seconds: float = 25,
                     stability_seconds: float = 0.5,
                     sleep: Callable[[float], None] = time.sleep) -> VerifiedOutput:
    """Return a receipt only for the exact newly generated, stable video file.

    The receipt proves file validation and binding to a ticket, but not by
    itself the private CapCut engine provenance; the trusted host must supply
    and retain the corresponding native admission evidence.
    """
    if not isinstance(ticket, ExportTicket):
        raise NativeOutputError("A genuine export ticket is required")
    output = _canonical(reported_path)
    if output != ticket.output_path or output.is_symlink():
        raise NativeOutputError("Output path differs from the admitted native job")
    try:
        first = output.stat()
    except (FileNotFoundError, OSError) as exc:
        raise NativeOutputError("Native MP4 does not exist") from exc
    if not output.is_file() or first.st_size < 1024:
        raise NativeOutputError("MP4 missing or too small")
    # File must have been written after the guarded admission. Windows file
    # timestamp precision varies; a 2-second margin is allowed. Existing files
    # are separately rejected by begin_export.
    if first.st_mtime_ns < ticket.admission_started_ns - 2_000_000_000:
        raise NativeOutputError("Candidate MP4 predates native admission")

    metadata = _probe_json(output, executable=executable,
                           timeout_seconds=timeout_seconds)
    videos = [s for s in metadata.get("streams", [])
              if isinstance(s, dict) and s.get("codec_type") == "video"]
    if not videos:
        raise NativeOutputError("MP4 has no video stream")
    stream = videos[0]
    try:
        width, height = int(stream.get("width", 0)), int(stream.get("height", 0))
        duration = float(metadata.get("format", {}).get("duration") or
                         stream.get("duration") or 0)
    except (ValueError, TypeError, OverflowError) as exc:
        raise NativeOutputError("Invalid MP4 video stream metadata") from exc
    if width < 1 or height < 1 or not 0 < duration < float("inf"):
        raise NativeOutputError("MP4 stream lacks usable dimensions or duration")

    if stability_seconds < 0 or stability_seconds > 30:
        raise NativeOutputError("Unreasonable stability interval")
    sleep(stability_seconds)
    try:
        second = output.stat()
    except (FileNotFoundError, OSError) as exc:
        raise NativeOutputError("MP4 disappeared during validation") from exc
    if (first.st_size, first.st_mtime_ns, first.st_ino) != (
            second.st_size, second.st_mtime_ns, second.st_ino):
        raise NativeOutputError("MP4 changed while being verified")

    digest = hashlib.sha256()
    try:
        with output.open("rb") as file:
            while chunk := file.read(1024 * 1024):
                digest.update(chunk)
        third = output.stat()
    except (FileNotFoundError, OSError) as exc:
        raise NativeOutputError("MP4 became inaccessible during hashing") from exc
    if (second.st_size, second.st_mtime_ns, second.st_ino) != (
            third.st_size, third.st_mtime_ns, third.st_ino):
        raise NativeOutputError("MP4 changed during hashing")
    return VerifiedOutput(ticket.key, str(output), digest.hexdigest(),
                          third.st_size, duration, width, height)
