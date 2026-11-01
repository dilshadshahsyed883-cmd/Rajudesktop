"""Pure, evidence-grounded controls. No CapCut mutation or UI dependencies."""
from __future__ import annotations
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import struct
import subprocess
import tempfile

SUPPORTED_VERSION = "9.6.0.4097"
LYRA_DLL_SHA256 = "878df7053d8eb83bf2bf35621fbdc7652e80836680a658a786560689f788f9f7"
CAPCUT_EXE_SHA256 = "1bf33b74a2638ad665ae77c44d7df4cc1b0082d8c305c5d4292321a467d30873"
ARCHIVE_SHA256 = "389c0ad94cc7f6e967b8be374e78f4640496194e12671567ad19d752e5e84cbd"
EXPORT_RE = re.compile(r"^Export[-–](.+)$", re.IGNORECASE)


class Halt(RuntimeError):
    """Fail closed without attempting another export."""


def project_name(value: str) -> str:
    name = value.strip()
    if (not name or name in (".", "..") or len(name) > 180
        or name.endswith((" ", ".")) or any(c in name for c in '\\/:*?"<>|')
        or any(ord(c) < 32 for c in name)):
        raise Halt("Use the exact project name as a valid Windows filename (1–180 characters).")
    return name


def expected_video(folder: str, name: str) -> Path:
    name = project_name(name)
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise Halt(f"Output folder does not exist: {root}")
    target = root / f"{name}.mp4"
    if target.exists():
        raise Halt(f"Output already exists; no overwrite or automatic retry: {target}")
    return target


def export_dialog_match(title: str, name: str) -> bool:
    m = EXPORT_RE.fullmatch(title.strip())
    return bool(m and m.group(1).strip().casefold() == project_name(name).casefold())


def sha256_file(file: Path) -> str:
    h = hashlib.sha256()
    with file.open("rb") as stream:
        for block in iter(lambda: stream.read(4 * 1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def installed_evidence(capcut_exe: Path) -> dict:
    """Exact installed DLL hash is stronger than a UI-reported version alone."""
    dll = capcut_exe.parent / "lyra_cli_client.dll"
    if not capcut_exe.is_file() or not dll.is_file():
        raise Halt("Expected installed CapCut.exe and lyra_cli_client.dll in same directory.")
    if capcut_exe.parent.name != SUPPORTED_VERSION:
        raise Halt(f"CapCut path must be version {SUPPORTED_VERSION}: {capcut_exe.parent}")
    digest = sha256_file(dll)
    if digest != LYRA_DLL_SHA256:
        raise Halt("CapCut 9.6 native DLL differs from the supplied verified archive; stop.")
    return {"version": SUPPORTED_VERSION, "lyra_dll_sha256": digest,
            "exe_sha256": sha256_file(capcut_exe), "source_archive_sha256": ARCHIVE_SHA256}


def _box_tags(path: Path) -> bool:
    """Top-level MP4 box walk; reject incomplete writes and premature EOF."""
    try:
        size = path.stat().st_size
        if size < 4096:
            return False
        seen = set()
        with path.open("rb") as stream:
            position = 0
            while position + 8 <= size:
                stream.seek(position)
                header = stream.read(8)
                length, kind = struct.unpack(">I4s", header)
                overhead = 8
                if length == 1:
                    length = struct.unpack(">Q", stream.read(8))[0]
                    overhead = 16
                elif length == 0:
                    length = size - position
                if length < overhead or position + length > size:
                    return False
                seen.add(kind)
                position += length
            return position == size and {b"ftyp", b"mdat", b"moov"} <= seen
    except (OSError, ValueError, struct.error):
        return False


@dataclass
class Observer:
    file: Path
    old: tuple[int, int] | None = None
    stable: int = 0

    def poll(self) -> tuple[bool, str]:
        try:
            st = self.file.stat()
        except FileNotFoundError:
            self.stable = 0
            return False, "Waiting for MP4"
        except OSError as e:
            self.stable = 0
            return False, f"Cannot access output: {e}"
        current = (st.st_size, st.st_mtime_ns)
        self.stable = (self.stable + 1) if self.old == current else 0
        self.old = current
        if self.stable < 3:
            return False, f"Writing {st.st_size / (1024*1024):.1f} MiB; stability {self.stable}/3"
        if not _box_tags(self.file):
            return False, "MP4 container not finalized"
        return True, "Stable finalized MP4 container detected"


def validate_media(file: Path, ffprobe: str) -> dict:
    """Require duration, video, and decoded metadata; never claim visual/audio parity."""
    if not ffprobe or not Path(ffprobe).is_file() and shutil.which(ffprobe) is None:
        raise Halt("ffprobe is required for verified output. Set its full path or install FFmpeg.")
    try:
        r = subprocess.run([ffprobe, "-v", "error", "-show_format", "-show_streams",
                            "-of", "json", str(file)], capture_output=True, text=True,
                           encoding="utf-8", timeout=90, check=False)
    except (OSError, subprocess.TimeoutExpired) as e:
        raise Halt(f"ffprobe unavailable or timed out: {e}") from e
    if r.returncode:
        raise Halt(f"ffprobe rejected output: {r.stderr[:300]}")
    try:
        obj = json.loads(r.stdout)
        duration = float(obj["format"]["duration"])
        video = next(s for s in obj["streams"] if s["codec_type"] == "video")
        width, height = int(video["width"]), int(video["height"])
    except (ValueError, KeyError, TypeError, StopIteration) as e:
        raise Halt("ffprobe output lacks a valid duration or video stream.") from e
    if duration <= 0 or width <= 0 or height <= 0:
        raise Halt("Invalid final video dimensions/duration.")
    return {"duration_sec": duration, "video_codec": video.get("codec_name"),
            "width": width, "height": height,
            "audio_streams": sum(s.get("codec_type") == "audio" for s in obj["streams"]),
            "sha256": sha256_file(file), "bytes": file.stat().st_size}


def atomic_json(file: Path, data: dict) -> None:
    """Replace our own JSON state only; never edits any CapCut draft file."""
    file.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".__export_", suffix=".tmp", dir=file.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as out:
            json.dump(data, out, indent=2, ensure_ascii=False)
            out.flush()
            os.fsync(out.fileno())
        os.replace(tmp, file)
    finally:
        if Path(tmp).exists():
            Path(tmp).unlink()


def unresolved(state_file: Path) -> bool:
    try:
        state = json.loads(state_file.read_text(encoding="utf-8"))
        return state.get("phase") in ("opening", "export_requested", "monitor_stopped", "uncertain")
    except FileNotFoundError:
        return False
    except (OSError, ValueError):
        return True  # corrupted journal: refuse new action


def self_check() -> dict:
    return {"app": "CapCut Auto Export Evidence Demo", "capcut_version_expected": SUPPORTED_VERSION,
            "archive_fingerprint": ARCHIVE_SHA256,
            "windows_export_tested": False, "unattended_batch_certified": False}
