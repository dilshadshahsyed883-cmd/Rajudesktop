"""Publish completed clips into a shared folder without exposing partial MP4s."""
from __future__ import annotations

import os
import re
import shutil
import tempfile
import unicodedata
from contextlib import contextmanager
from pathlib import Path

from video_clip_cutter.core import CutterError, video_duration


def default_output_folder() -> Path:
    """Respect the redirected Windows Desktop; retain an explicit folder picker."""
    desktop = Path.home() / "Desktop"
    if os.name == "nt":
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\Windows\CurrentVersion\Explorer\User Shell Folders") as key:
                value, _ = winreg.QueryValueEx(key, "Desktop")
                desktop = Path(os.path.expandvars(value))
        except (OSError, ValueError):
            pass
    return desktop / "Alexa Media" / "clips"


def validate_output(folder: Path) -> Path:
    folder = folder.expanduser().resolve()
    if folder.parent == folder:
        raise CutterError("Choose a clips subfolder rather than a drive root.")
    # The portable Windows app must also work without long-path support.
    if os.name == "nt" and len(str(folder)) > 160:
        raise CutterError("Choose a shorter output folder path (at most 160 characters).")
    folder.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryFile(dir=folder):
        pass
    return folder


@contextmanager
def publish_lock(folder: Path):
    # Lock beside the target, never inside the selectable clip library. OS locks
    # are released on crashes. All app processes targeting this folder serialize.
    lock = folder.parent / ("." + folder.name + ".smart-media.lock")
    with lock.open("a+b") as handle:
        handle.seek(0, os.SEEK_END)
        if not handle.tell():
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        if os.name == "nt":
            import msvcrt
            msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
        else:
            import fcntl
            fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            handle.seek(0)
            if os.name == "nt":
                msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                fcntl.flock(handle, fcntl.LOCK_UN)


def _key(name: str) -> str:
    return unicodedata.normalize("NFC", name).casefold()


def publish_clip(clip: Path, folder: Path, keyword: str, minimum) -> Path:
    """Probe, copy privately on the destination volume, then publish atomically.

    Keep the cutter's existing `keyword N.mp4` style and continue its numbering
    using actual target files (including case variants), across jobs/retries.
    """
    if video_duration(clip) < minimum:
        raise CutterError("Completed clip is shorter than the requested duration.")
    if shutil.disk_usage(folder).free < clip.stat().st_size + 1024 * 1024:
        raise CutterError("Not enough free space in the selected output folder.")
    # Same-volume staging also supports source caches on another drive. Neither
    # incomplete files nor internal folders appear inside the selected library.
    with tempfile.TemporaryDirectory(prefix=".smart-media-publish-", dir=folder.parent) as staging:
        ready = Path(staging) / "ready.mp4"
        shutil.copyfile(clip, ready)
        with ready.open("rb+") as handle:
            os.fsync(handle.fileno())
        with publish_lock(folder):
            existing = {_key(p.name) for p in folder.iterdir()}
            pattern = re.compile(re.escape(_key(keyword)) + r" (\d+)\.mp4$")
            numbers = [int(m.group(1)) for name in existing if (m := pattern.fullmatch(name))]
            number = max(numbers, default=0) + 1
            while True:
                target = folder / f"{keyword} {number}.mp4"
                if _key(target.name) in existing:
                    number += 1
                    continue
                try:
                    if os.name == "nt":
                        # Windows rename never replaces an existing destination.
                        os.rename(ready, target)
                    else:
                        # POSIX rename overwrites: exclusive hard-link instead.
                        os.link(ready, target)
                    return target
                except FileExistsError:
                    number += 1
