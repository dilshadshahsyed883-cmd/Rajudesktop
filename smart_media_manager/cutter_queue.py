"""Unified local/YouTube cutter pipeline. Every job uses an isolated output directory."""
from __future__ import annotations

import re
import threading
from dataclasses import replace
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs

from smart_media_manager.youtube_downloader import ffmpeg_paths, valid_url
from video_clip_cutter.core import prepare_job, process_job, parse_duration, RESERVED_NAMES

VIDEO_TYPES = {".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".ts"}
CLIP_QUALITIES = ("720p", "1080p")
# A missing quality on old persisted jobs (or snapshot download jobs)
# retains the old uncapped behavior.
LEGACY_DOWNLOAD_FORMAT = "bv[ext=mp4]/bv"


def source_format(quality=None):
    """Download ONLY a video-only stream, preferring the selected quality.

    Strict bestvideo (bv) excludes audio tracks: no separate audio download
    or FFmpeg merge. If YouTube only offers muxed formats, fail rather than
    downloading audio unexpectedly.
    """
    if quality is None:
        return LEGACY_DOWNLOAD_FORMAT
    if quality not in CLIP_QUALITIES:
        raise ValueError("Video quality must be 720p or 1080p")
    cap = "[height<=" + quality[:-1] + "]"
    return f"bv{cap}[ext=mp4]/bv{cap}/{LEGACY_DOWNLOAD_FORMAT}"



def safe_name(value: str) -> str:
    result = re.sub(r'[<>:"/\\|?*\x00-\x1f]', " ", str(value))
    result = re.sub(r"\s+", " ", result).strip(" .")[:85].rstrip(" .")
    result = result or "Video"
    if result.split(".")[0].upper() in RESERVED_NAMES:
        result = "Video " + result
    return result


def new_job(source: str, kind: str, duration: str, output: str,
            keyword: str = "", quality: str = "720p") -> dict:
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
    if quality not in CLIP_QUALITIES:
        raise ValueError("Video quality must be 720p or 1080p")
    if not str(output).strip():
        raise ValueError("Choose an output folder")
    return {"id": uuid.uuid4().hex, "source": source, "kind": kind,
            "keyword": safe_name(keyword or default_name), "duration": str(duration),
            "quality": quality, "output": str(output),
            "status": "Queued", "progress": 0, "attempt": 0}


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
        "format": source_format(job.get("quality")),
        "outtmpl": str(folder / "source.%(ext)s"),
        "noplaylist": True, "continuedl": True, "overwrites": False,
        # One video-only stream: no audio formats, no remux step.
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


def cut_source(job: dict, source: Path, cancel: threading.Event, notify) -> tuple[int, Path]:
    """Cut only complete-length clips; never write a shorter final remainder.

    This rule belongs to Smart Media Manager. The independent video cutter
    retains its original behavior for short final segments.
    """
    if cancel.is_set():
        raise RuntimeError("Cancelled")
    folder = job_output(job)
    prepared = prepare_job(Path(source), folder, job["keyword"], job["duration"])
    full_clips = int(prepared.total // prepared.step)
    prepared = replace(prepared, total=prepared.step * full_clips)
    if not full_clips:
        notify("Cutting", 100, "Skipped video shorter than requested clip duration")
        return 0, folder
    if job.get("quality") is not None and job["quality"] not in CLIP_QUALITIES:
        raise ValueError("Video quality must be 720p or 1080p")
    # Stream copy only: no decode/re-encode, scaling or audio track.
    # YouTube quality limits the source download; PC inputs retain source
    # resolution. Segment boundaries are keyframe-aligned, not exact seconds.
    notify("Cutting", 0, f"Fast copying up to {full_clips} keyframe-aligned clips")
    clips = process_job(
        prepared, cancel=cancel, include_audio=False, fast_copy=True,
        progress=lambda i, n, path:
            notify("Cutting", round(i * 100 / n), f"Clip {i}/{n}: {path.name}"),
    )
    notify("Cutting", 100, f"Saved {len(clips)} clips without re-encoding")
    return len(clips), folder


def execute_job(job: dict, cancel: threading.Event, notify, cache_root: Path) -> tuple[int, Path]:
    """Original single-job API, using the Smart Media Manager full-length policy."""
    if cancel.is_set():
        raise RuntimeError("Cancelled")
    source = (download_source(job, cache_root, cancel, notify)
              if job["kind"] == "YouTube" else Path(job["source"]))
    return cut_source(job, source, cancel, notify)
