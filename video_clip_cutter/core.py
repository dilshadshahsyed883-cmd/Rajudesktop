"""Independent, lossless-timeline (frame accurate) video segment exporter.

Requires ffmpeg and ffprobe executables. All outputs are encoded to MP4.
"""
from __future__ import annotations

import json
import math
import os
import re
import shutil
import subprocess
import sys
import threading
import uuid
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable

INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
RESERVED_NAMES = {"CON", "PRN", "AUX", "NUL"} | {f"COM{x}" for x in range(1, 10)} | {f"LPT{x}" for x in range(1, 10)}
VIDEO_EXTS = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".ts"}


class CutterError(Exception):
    """Actionable problem that can be shown in the UI."""


class Cancelled(CutterError):
    pass


def default_output_folder() -> Path:
    """Use the Windows Documents shell location, including OneDrive redirection."""
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                value, _ = winreg.QueryValueEx(key, "Personal")
                return Path(os.path.expandvars(value)) / "ProcessedClips"
        except (OSError, ValueError):
            pass
    return Path.home() / "Documents" / "ProcessedClips"


def settings_path() -> Path:
    home = Path(os.environ.get("LOCALAPPDATA", Path.home())) if os.name == "nt" else Path.home() / ".config"
    return home / "VideoClipCutter" / "settings.json"


def read_settings(path: Path | None = None) -> dict:
    path = path or settings_path()
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        return value if isinstance(value, dict) else {}
    except (OSError, ValueError):
        return {}


def write_settings(value: dict, path: Path | None = None) -> None:
    path = path or settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_suffix(".json.tmp")
    partial.write_text(json.dumps(value, indent=2), encoding="utf-8")
    os.replace(partial, path)


def validate_name(name: str) -> str:
    name = name.strip()
    if not name:
        raise CutterError("Output filename is required.")
    if len(name) > 100:
        raise CutterError("Filename must be at most 100 characters.")
    if name.endswith(".") or INVALID_CHARS.search(name) or name in {".", ".."}:
        raise CutterError('Filename cannot contain \\/:*?"<>| or control characters, or end in a dot.')
    if name.split(".")[0].upper() in RESERVED_NAMES:
        raise CutterError("This filename is reserved by Windows. Choose another name.")
    return name


def parse_duration(raw: str | int | float | Decimal) -> Decimal:
    try:
        duration = Decimal(str(raw).strip())
    except (InvalidOperation, ValueError):
        raise CutterError("Enter a valid clip duration in seconds.") from None
    if not duration.is_finite() or not (Decimal("0.1") <= duration <= Decimal("3600")):
        raise CutterError("Clip duration must be between 0.1 and 3600 seconds.")
    return duration


def find_executable(name: str) -> str:
    exe = f"{name}.exe" if os.name == "nt" else name
    roots = [Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)),
             Path(sys.executable).resolve().parent, Path(__file__).resolve().parent]
    for root in roots:
        for candidate in (root / "bin" / exe, root / exe):
            if candidate.is_file():
                return str(candidate)
    from_path = shutil.which(exe) or shutil.which(name)
    if from_path:
        return from_path
    raise CutterError(f"{name} was not found. Use the bundled Windows application or install FFmpeg and add it to PATH.")


def video_duration(source: Path, ffprobe: str | None = None) -> Decimal:
    if not source.is_file():
        raise CutterError("Select an existing video file.")
    if source.suffix.lower() not in VIDEO_EXTS:
        raise CutterError("Unsupported file type. Choose MP4, MOV, MKV, AVI, WEBM, M4V, WMV, or TS.")
    executable = ffprobe or find_executable("ffprobe")
    command = [executable, "-v", "error", "-show_entries", "format=duration:stream=codec_type",
               "-of", "json", str(source)]
    try:
        process = subprocess.run(command, capture_output=True, text=True, timeout=45, check=False,
                                 encoding="utf-8", errors="replace", creationflags=_flags())
    except (OSError, subprocess.TimeoutExpired) as ex:
        raise CutterError(f"Could not inspect video: {ex}") from ex
    if process.returncode:
        raise CutterError("Could not read video. The file may be damaged or unsupported.")
    try:
        data = json.loads(process.stdout)
        if not any(s.get("codec_type") == "video" for s in data.get("streams", [])):
            raise CutterError("Selected file has no video stream.")
        seconds = Decimal(str(data["format"]["duration"]))
        if not seconds.is_finite() or seconds <= 0:
            raise ValueError("Bad duration")
        return seconds
    except (KeyError, ValueError, InvalidOperation) as ex:
        raise CutterError("Could not determine video duration.") from ex


def segments(total: Decimal, step: Decimal) -> list[tuple[Decimal, Decimal]]:
    """Return (start, length) pairs, preserving the short final segment."""
    count = int((total / step).to_integral_value(rounding="ROUND_CEILING"))
    if count > 100_000:
        raise CutterError("Too many clips (limit: 100,000). Increase clip duration.")
    return [(step * i, min(step, total - step * i)) for i in range(count)]


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0)


def _number(value: Decimal) -> str:
    return format(value, "f")


@dataclass(frozen=True)
class Job:
    source: Path
    folder: Path
    name: str
    step: Decimal
    total: Decimal

    @property
    def parts(self) -> list[tuple[Decimal, Decimal]]:
        return segments(self.total, self.step)

    @property
    def targets(self) -> list[Path]:
        return [self.folder / f"{self.name} {n}.mp4" for n in range(1, len(self.parts) + 1)]


def prepare_job(source: Path, folder: Path, name: str, duration: str, *, ffprobe: str | None = None) -> Job:
    name = validate_name(name)
    step = parse_duration(duration)
    if not str(folder).strip():
        raise CutterError("Select an output folder.")
    source = Path(source).expanduser().resolve()
    folder = Path(folder).expanduser().resolve()
    total = video_duration(source, ffprobe)
    job = Job(source=source, folder=folder, name=name, step=step, total=total)
    existing = [p.name for p in job.targets if p.exists()]
    if existing:
        raise CutterError(f"Output already exists ({existing[0]}). Change filename or destination to protect existing files.")
    if job.parts and not folder.exists():
        try:
            folder.mkdir(parents=True, exist_ok=True)
        except OSError as ex:
            raise CutterError(f"Unable to create output folder: {ex}") from ex
    return job


def process_job(job: Job, *, ffmpeg: str | None = None, cancel: threading.Event | None = None,
                progress: Callable[[int, int, Path], None] | None = None,
                process_callback: Callable[[subprocess.Popen | None], None] | None = None) -> list[Path]:
    """Write each clip to temporary MP4, then commit. Never overwrite output files."""
    binary = ffmpeg or find_executable("ffmpeg")
    cancel = cancel or threading.Event()
    completed: list[Path] = []
    for index, ((start, length), target) in enumerate(zip(job.parts, job.targets), 1):
        if cancel.is_set():
            raise Cancelled(f"Cancelled. {len(completed)} completed clip(s) kept.")
        if target.exists():
            raise CutterError(f"Output already exists: {target.name}. Existing clips were not overwritten.")
        temp = job.folder / f".{uuid.uuid4().hex}.part.mp4"
        command = [binary, "-hide_banner", "-loglevel", "error", "-nostdin", "-ss", _number(start),
                   "-i", str(job.source), "-t", _number(length), "-map", "0:v:0", "-map", "0:a?",
                   "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
                   "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", "-y", str(temp)]
        process: subprocess.Popen | None = None
        try:
            process = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
                                       text=True, encoding="utf-8", errors="replace", creationflags=_flags())
            if process_callback:
                process_callback(process)
            while process.poll() is None:
                if cancel.is_set():
                    process.terminate()
                    try:
                        process.wait(timeout=3)
                    except subprocess.TimeoutExpired:
                        process.kill()
                        process.wait()
                    raise Cancelled(f"Cancelled. {len(completed)} completed clip(s) kept.")
                cancel.wait(0.12)
            stderr = process.stderr.read() if process.stderr else ""
            if process.returncode != 0 or not temp.is_file() or temp.stat().st_size == 0:
                raise CutterError(f"Clip {index} failed: {stderr.strip()[-500:] or 'FFmpeg produced no output'}")
            # Exclusive destination: cannot silently replace a file produced by another process.
            try:
                os.link(temp, target)
                temp.unlink()
            except FileExistsError:
                raise CutterError(f"Output already exists: {target.name}. Existing clips were not overwritten.")
            except OSError:
                # Filesystems without hard-link support still use a preflight check.
                if target.exists():
                    raise CutterError(f"Output already exists: {target.name}. Existing clips were not overwritten.")
                os.rename(temp, target)
            completed.append(target)
            if progress:
                progress(index, len(job.parts), target)
        except OSError as ex:
            raise CutterError(f"Cannot write clip {index}: {ex}") from ex
        finally:
            if process_callback:
                process_callback(None)
            if process and process.stderr:
                process.stderr.close()
            temp.unlink(missing_ok=True)
    return completed
