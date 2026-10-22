"""Probe duration and find an FFmpeg executable without modifying the system."""
from __future__ import annotations

from pathlib import Path
import re
import shutil
import subprocess

from .core import classify


def ffmpeg_path() -> str:
    try:
        import imageio_ffmpeg
        exe = imageio_ffmpeg.get_ffmpeg_exe()
        if exe and Path(exe).is_file():
            return exe
    except (ImportError, OSError, RuntimeError):
        pass
    exe = shutil.which("ffmpeg")
    if not exe:
        raise RuntimeError("FFmpeg is unavailable; install the app's bundled Windows build")
    return exe


def duration_ms(path: str) -> int:
    kind = classify(path)
    if not Path(path).is_file():
        raise FileNotFoundError(path)
    if kind == "image":
        return 4000
    cmd = [ffmpeg_path(), "-hide_banner", "-i", path]
    result = subprocess.run(cmd, capture_output=True, text=True, errors="replace", timeout=30, check=False)
    match = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", result.stderr)
    if not match:
        raise ValueError(f"Unable to determine duration of {Path(path).name}")
    hours, minutes, seconds = match.groups()
    value = round((int(hours) * 3600 + int(minutes) * 60 + float(seconds)) * 1000)
    if value < 100:
        raise ValueError("Media is shorter than 100 milliseconds")
    return value
