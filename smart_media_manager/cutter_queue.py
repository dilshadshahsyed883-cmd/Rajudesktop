"""Unified local/YouTube cutter pipeline. Every job uses an isolated output directory."""
from __future__ import annotations

import re
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from smart_media_manager.youtube_downloader import ffmpeg_paths, valid_url
from video_clip_cutter.core import prepare_job, process_job, parse_duration, RESERVED_NAMES

VIDEO_TYPES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".ts"}


def safe_name(value: str) -> str:
    result = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(value))
    result = re.sub(r"\s+", " ", result).strip(" .")[:85].rstrip(" .")
    result = result or "Video"
    if result.split(".")[0].upper() in RESERVED_NAMES:
        result = "Video " + result
    return result


def new_job(source: str, kind: str, duration: str, output: str, keyword: str = "") -> dict:
    if kind not in ("Local", "YouTube"):
        raise ValueError("Unknown input type")
    if kind == "YouTube":
        if not valid_url(source):
            raise ValueError("Invalid YouTube link")
        parsed = urlparse(source)
        video_id = parse_qs(parsed.query).get("v", [""])[0] or parsed.path.rstrip("/").split("/")[-1]
        default_name = "YouTube " + safe_name(video_id)[:28]
    else:
        if not Path(source).is_file() or Path(source).suffix.lower() not in VIDEO_TYPES:
            raise ValueError("Select an existing supported video file")
        default_name = Path(source).stem
    parse_duration(duration)
    if not str(output).strip():
        raise ValueError("Choose an output folder")
    return {"id": uuid.uuid4().hex, "source": source, "kind": kind,
            "keyword": safe_name(keyword or default_name), "duration": str(duration),
            "output": str(output), "status": "Queued", "progress": 0, "attempt": 0}


def job_output(job: dict) -> Path:
    root = Path(job["output"]).expanduser()
    label = f'{safe_name(job["keyword"])} [{job["id"][:8]}]'
    if job.get("attempt", 0):
        label += f' retry-{int(job["attempt"])}'
    return root / label


def download_source(job: dict, cache_root: Path, cancel: threading.Event, notify) -> Path:
    """Download permitted YouTube content for later local cutting; resume partial files."""
    import yt_dlp
    if not valid_url(job["source"]):
        raise ValueError("Invalid YouTube URL")
    folder = cache_root / job["id"]
    folder.mkdir(parents=True, exist_ok=True)
    finished = [p for p in folder.glob("source.*")
                if p.is_file() and p.suffix.lower() in VIDEO_TYPES and p.stat().st_size]
    if finished:
        notify("Downloading", 100, "Reusing downloaded video")
        return finished[0]
    ffmpeg, _ = ffmpeg_paths()

    def progress_hook(data):
        if cancel.is_set():
            raise RuntimeError("Download cancelled")
        downloaded = float(data.get("downloaded_bytes") or 0)
        total = float(data.get("total_bytes") or data.get("total_bytes_estimate") or 0)
        if total:
            notify("Downloading", min(99, round(100 * downloaded / total)), "Downloading video")

    opts = {
        "format": "bv*[ext=mp4]+ba[ext=m4a]/b[ext=mp4]/bv*+ba/best",
        "outtmpl": str(folder / "source.%(ext)s"),
        "noplaylist": True, "continuedl": True, "overwrites": False,
        "merge_output_format": "mp4",
        "progress_hooks": [progress_hook], "quiet": True,
    }
    if ffmpeg:
        opts["ffmpeg_location"] = str(Path(ffmpeg).parent)
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(job["source"], download=True)
        if not info:
            raise RuntimeError("YouTube returned no downloadable video")
    if cancel.is_set():
        raise RuntimeError("Download cancelled")
    finished = [p for p in folder.glob("source.*")
                if p.is_file() and p.suffix.lower() in VIDEO_TYPES and p.stat().st_size]
    if not finished:
        raise RuntimeError("Download completed but no source video was found")
    notify("Downloading", 100, "Download complete; cutting next")
    return finished[0]


def execute_job(job: dict, cancel: threading.Event, notify, cache_root: Path) -> tuple[int, Path]:
    """Notify(stage, percentage, message); return clip count and folder."""
    if cancel.is_set():
        raise RuntimeError("Cancelled")
    if job["kind"] == "YouTube":
        source = download_source(job, cache_root, cancel, notify)
    else:
        source = Path(job["source"])
    if cancel.is_set():
        raise RuntimeError("Cancelled")
    folder = job_output(job)
    prepared = prepare_job(source, folder, job["keyword"], job["duration"])
    notify("Cutting", 0, f'Cutting {len(prepared.parts)} clips')
    clips = process_job(prepared, cancel=cancel, progress=lambda i, n, path:
                        notify("Cutting", round(i * 100 / n), f'Clip {i}/{n}: {path.name}'))
    return len(clips), folder
