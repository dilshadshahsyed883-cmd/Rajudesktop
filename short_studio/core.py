"""Local Short Studio engine. Does not connect to or modify VPS production."""
from __future__ import annotations

import hashlib
import json
import os
import random
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
import uuid
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

try:
    from PIL import Image, ImageFilter, ImageOps
except ImportError:
    Image = ImageFilter = ImageOps = None

WIDTH, HEIGHT = 1080, 1920
IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp", ".tif", ".tiff", ".jfif"}
AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus"}
FOLDER_RE = re.compile(r"[A-Za-z0-9][A-Za-z0-9 _-]{0,63}\Z")
ROOT = Path(os.environ.get("SHORT_STUDIO_HOME") or
            (Path(os.environ.get("LOCALAPPDATA") or Path.home()) / "ShortStudio"))
_lock = threading.RLock()


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def safe_folder(name: str) -> str:
    name = str(name).strip()
    if not FOLDER_RE.fullmatch(name):
        raise ValueError("Folder: use 1-64 letters, numbers, spaces, _ or -")
    return name


def ffmpeg_exe() -> str:
    bundled = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent)) / "bin" / "ffmpeg.exe"
    if bundled.is_file():
        return str(bundled)
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise RuntimeError("FFmpeg not found (install FFmpeg or use bundled Windows EXE)")


def run_ffmpeg(args: list[str], timeout: int = 1800) -> None:
    result = subprocess.run([ffmpeg_exe(), "-hide_banner", "-loglevel", "error", "-y",
                             *args], capture_output=True, text=True, timeout=timeout)
    if result.returncode:
        raise RuntimeError("FFmpeg: " + (result.stderr or "process failed")[-1300:])


class Store:
    def __init__(self, root: Path | str = ROOT):
        self.root = Path(root)
        self.media = self.root / "Folders"
        self.media.mkdir(parents=True, exist_ok=True)
        self.db_path = self.root / "short_studio.sqlite3"
        with self.db() as conn:
            conn.executescript("""
                CREATE TABLE IF NOT EXISTS folders(name TEXT PRIMARY KEY);
                CREATE TABLE IF NOT EXISTS sequences(folder TEXT PRIMARY KEY, last_number INTEGER NOT NULL);
                CREATE TABLE IF NOT EXISTS jobs(
                    id TEXT PRIMARY KEY, folder TEXT NOT NULL, status TEXT NOT NULL,
                    message TEXT NOT NULL DEFAULT '', created TEXT NOT NULL,
                    output_files TEXT NOT NULL DEFAULT '[]');
                CREATE TABLE IF NOT EXISTS channels(
                    id TEXT PRIMARY KEY, label TEXT NOT NULL, token_file TEXT NOT NULL);
                CREATE TABLE IF NOT EXISTS groups(id TEXT PRIMARY KEY, name TEXT UNIQUE NOT NULL);
                CREATE TABLE IF NOT EXISTS memberships(
                    group_id TEXT NOT NULL, channel_id TEXT NOT NULL,
                    PRIMARY KEY(group_id, channel_id));
                CREATE TABLE IF NOT EXISTS profiles(
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, group_id TEXT NOT NULL,
                    folder TEXT NOT NULL, title TEXT NOT NULL, description TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT '22', privacy TEXT NOT NULL DEFAULT 'private',
                    daily_limit INTEGER NOT NULL DEFAULT 4, schedule_pkt TEXT NOT NULL DEFAULT '12:00',
                    delete_after INTEGER NOT NULL DEFAULT 1);
                CREATE TABLE IF NOT EXISTS uploads(
                    id TEXT PRIMARY KEY, channel_id TEXT NOT NULL, sha256 TEXT NOT NULL,
                    file_path TEXT NOT NULL, profile_id TEXT NOT NULL, state TEXT NOT NULL,
                    youtube_id TEXT NOT NULL DEFAULT '', error TEXT NOT NULL DEFAULT '',
                    attempted TEXT NOT NULL, updated TEXT NOT NULL,
                    UNIQUE(channel_id, sha256));
                """)
            conn.execute("INSERT OR IGNORE INTO folders(name) VALUES('Default')")
        (self.media / "Default").mkdir(exist_ok=True)

    @contextmanager
    def db(self):
        with _lock:
            con = sqlite3.connect(self.db_path, timeout=30)
            try:
                con.execute("PRAGMA foreign_keys=OFF")
                yield con
                con.commit()
            except BaseException:
                con.rollback()
                raise
            finally:
                con.close()

    def folders(self) -> list[str]:
        with self.db() as con:
            return [r[0] for r in con.execute("SELECT name FROM folders ORDER BY name COLLATE NOCASE")]

    def folder_path(self, name: str) -> Path:
        safe_folder(name)
        with self.db() as con:
            if not con.execute("SELECT 1 FROM folders WHERE name=?", (name,)).fetchone():
                raise ValueError("Choose an existing Short Studio folder")
        path = self.media / name
        if path.is_symlink() or self.media.is_symlink():
            raise ValueError("Folder symlinks are not allowed")
        return path

    def create_folder(self, name: str) -> Path:
        name = safe_folder(name)
        path = self.media / name
        if path.is_symlink() or path.exists() and not path.is_dir():
            raise ValueError("Unsafe folder")
        path.mkdir(exist_ok=True)
        with self.db() as con:
            con.execute("INSERT OR IGNORE INTO folders(name) VALUES(?)", (name,))
        return path

    def delete_empty_folder(self, name: str) -> None:
        if name == "Default":
            raise ValueError("Default folder is protected")
        path = self.folder_path(name)
        with self.db() as con:
            if con.execute("SELECT 1 FROM profiles WHERE folder=?", (name,)).fetchone():
                raise ValueError("Folder is used by an uploader profile")
            path.rmdir()  # intentional: never delete files or nonempty folders
            con.execute("DELETE FROM folders WHERE name=?", (name,))

    def reserve_names(self, folder: str, count: int) -> list[Path]:
        if not 1 <= count <= 999:
            raise ValueError("Output count must be 1-999")
        path = self.folder_path(folder)
        with self.db() as con:
            row = con.execute("SELECT last_number FROM sequences WHERE folder=?", (folder,)).fetchone()
            highest = row[0] if row else 0
            pattern = re.compile(re.escape(folder) + r" (\d{3,})_[a-f0-9]{6}\.mp4\Z", re.I)
            for f in path.iterdir():
                match = pattern.fullmatch(f.name)
                if match:
                    highest = max(highest, int(match.group(1)))
            tag = uuid.uuid4().hex[:6]
            names = [path / f"{folder} {n:03d}_{tag}.mp4"
                     for n in range(highest + 1, highest + count + 1)]
            con.execute("INSERT INTO sequences(folder,last_number) VALUES(?,?) "
                        "ON CONFLICT(folder) DO UPDATE SET last_number=excluded.last_number",
                        (folder, highest + count))
            return names

    def add_job(self, folder: str, paths: list[Path]) -> str:
        key = uuid.uuid4().hex
        with self.db() as con:
            con.execute("INSERT INTO jobs(id,folder,status,message,created,output_files) VALUES(?,?,?,?,?,?)",
                        (key, folder, "queued", "Waiting to render", utc_now(),
                         json.dumps([str(p) for p in paths])))
        return key

    def set_job(self, job_id: str, status: str, message: str) -> None:
        with self.db() as con:
            con.execute("UPDATE jobs SET status=?,message=? WHERE id=?", (status, message, job_id))

    def jobs(self):
        with self.db() as con:
            return [dict(id=r[0], folder=r[1], status=r[2], message=r[3],
                         created=r[4], files=json.loads(r[5]))
                    for r in con.execute("SELECT id,folder,status,message,created,output_files FROM jobs "
                                         "ORDER BY created DESC LIMIT 200")]

    def list_mp4(self, folder: str) -> list[Path]:
        return sorted((p for p in self.folder_path(folder).glob("*.mp4")
                       if p.is_file() and not p.is_symlink()), key=lambda p: p.name.lower())


@dataclass(frozen=True)
class RenderOptions:
    video_seconds: float = 16.0
    image_seconds: float = 3.0
    count: int = 1
    fps: int = 30
    crf: int = 20
    fit: str = "fill_crop"
    motion: str = "random"
    order: str = "random"

    def validate(self):
        if not (0.25 <= self.video_seconds <= 3600 and 0.25 <= self.image_seconds <= 600):
            raise ValueError("Durations out of range")
        if not 1 <= self.count <= 999 or self.fps not in (24, 30, 50, 60) or not 16 <= self.crf <= 28:
            raise ValueError("Invalid count, FPS or CRF")
        if self.fit not in ("fill_crop", "black", "blur") or self.order not in ("random", "filename"):
            raise ValueError("Invalid fit/order")
        if self.motion not in ("none", "random", "zoom_in", "zoom_out", "pan_lr", "pan_rl"):
            raise ValueError("Invalid motion")


def motion_filter(choice: str, frames: int, fps: int) -> str:
    if choice == "random":
        choice = random.choice(["zoom_in", "zoom_out", "pan_lr", "pan_rl"])
    denominator = max(1, frames - 1)
    if choice == "none":
        return f"fps={fps},format=yuv420p"
    if choice == "zoom_in":
        zoom, x = f"1+0.15*on/{denominator}", "iw/2-(iw/zoom/2)"
    elif choice == "zoom_out":
        zoom, x = f"1.15-0.15*on/{denominator}", "iw/2-(iw/zoom/2)"
    elif choice == "pan_lr":
        zoom, x = "1.12", f"(iw-iw/zoom)*on/{denominator}"
    else:
        zoom, x = "1.12", f"(iw-iw/zoom)*(1-on/{denominator})"
    return (f"zoompan=z='{zoom}':x='{x}':y='ih/2-(ih/zoom/2)':"
            f"d={frames}:s={WIDTH}x{HEIGHT}:fps={fps},format=yuv420p")


def prepare_frame(source: Path, destination: Path, fit: str):
    if Image is None:
        raise RuntimeError("Install Pillow for Short Maker image rendering")
    with Image.open(source) as raw:
        im = ImageOps.exif_transpose(raw).convert("RGB")
        if fit == "fill_crop":
            image = ImageOps.fit(im, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
        elif fit == "blur":
            image = ImageOps.fit(im, (WIDTH, HEIGHT), method=Image.Resampling.LANCZOS)
            image = image.filter(ImageFilter.GaussianBlur(radius=28))
            foreground = ImageOps.contain(im, (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            image.paste(foreground, ((WIDTH - foreground.width)//2, (HEIGHT - foreground.height)//2))
        else:
            image = Image.new("RGB", (WIDTH, HEIGHT))
            foreground = ImageOps.contain(im, (WIDTH, HEIGHT), Image.Resampling.LANCZOS)
            image.paste(foreground, ((WIDTH - foreground.width)//2, (HEIGHT - foreground.height)//2))
        image.save(destination, "JPEG", quality=93)


def render_one(images: list[Path], audio: list[Path], output: Path,
               opt: RenderOptions, notify: Callable[[str], None] = lambda _: None):
    opt.validate()
    images = [Path(p) for p in images if Path(p).suffix.lower() in IMAGE_EXTS and Path(p).is_file()]
    audio = [Path(p) for p in audio if Path(p).suffix.lower() in AUDIO_EXTS and Path(p).is_file()]
    if not images:
        raise ValueError("Choose a folder with readable images")
    if output.exists():
        raise FileExistsError(output.name)
    with tempfile.TemporaryDirectory(prefix="short-studio-") as work:
        temp = Path(work)
        remaining, clips, pos = opt.video_seconds, [], 0
        sequence = sorted(images) if opt.order == "filename" else random.sample(images, len(images))
        while remaining > 0.0001:
            duration = min(opt.image_seconds, remaining)
            img = sequence[pos % len(sequence)]
            if opt.order == "random" and pos and pos % len(sequence) == 0:
                sequence = random.sample(images, len(images))
                img = sequence[0]
            source = temp / f"image_{pos:05d}.jpg"
            clip = temp / f"clip_{pos:05d}.mp4"
            notify(f"Image {pos+1}: {img.name}")
            prepare_frame(img, source, opt.fit)
            frames = max(1, round(duration * opt.fps))
            run_ffmpeg(["-loop", "1", "-i", str(source), "-vf",
                        motion_filter(opt.motion, frames, opt.fps), "-frames:v", str(frames),
                        "-an", "-c:v", "libx264", "-preset", "veryfast",
                        "-crf", str(opt.crf), "-pix_fmt", "yuv420p", str(clip)])
            clips.append(clip)
            remaining -= duration
            pos += 1
        listing = temp / "concat.txt"
        # List is generated with known local filenames only, and no external paths.
        listing.write_text("".join(f"file 'clip_{i:05d}.mp4'\n" for i in range(len(clips))), encoding="utf-8")
        joined = temp / "joined.mp4"
        run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(listing),
                    "-c", "copy", str(joined)])
        if audio:
            normalized = []
            for i, song in enumerate(audio):
                target = temp / f"sound_{i:04d}.m4a"
                notify(f"Preparing audio {i+1}/{len(audio)}")
                run_ffmpeg(["-i", str(song), "-vn", "-ac", "2", "-ar", "48000",
                            "-c:a", "aac", str(target)])
                normalized.append(target)
            if len(normalized) == 1:
                soundtrack = normalized[0]
            else:
                audio_list = temp / "audio.txt"
                audio_list.write_text("".join(f"file 'sound_{i:04d}.m4a'\n"
                                              for i in range(len(normalized))), encoding="utf-8")
                soundtrack = temp / "audio.m4a"
                run_ffmpeg(["-f", "concat", "-safe", "0", "-i", str(audio_list),
                            "-c", "copy", str(soundtrack)])
            run_ffmpeg(["-i", str(joined), "-i", str(soundtrack),
                        "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy",
                        "-c:a", "aac", "-af", f"apad=whole_dur={opt.video_seconds:.6f}",
                        "-t", str(opt.video_seconds), "-movflags", "+faststart", str(output)])
        else:
            run_ffmpeg(["-i", str(joined), "-an", "-c", "copy",
                        "-t", str(opt.video_seconds), "-movflags", "+faststart", str(output)])
        if not output.exists() or output.stat().st_size == 0:
            raise RuntimeError("Output MP4 was not created")
    return output


def file_hash(path: Path) -> str:
    sha = hashlib.sha256()
    with Path(path).open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            sha.update(chunk)
    return sha.hexdigest()
