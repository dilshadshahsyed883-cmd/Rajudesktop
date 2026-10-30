"""Song Audio Downloader: use Smart Media Manager's yt-dlp selectors, with ID naming."""
from __future__ import annotations
import re
import threading
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from smart_media_manager.youtube_downloader import selector, ffmpeg_paths

VIDEO_ID = re.compile(r"[A-Za-z0-9_-]{11}\Z")
VIDEO_EXT = ("mp4", "mkv", "webm")


def video_id_from_url(url: str) -> str:
    if not isinstance(url, str) or len(url) > 350:
        raise ValueError("Invalid YouTube URL")
    try:
        parsed = urlsplit(url.strip())
        if parsed.scheme not in ("http", "https") or parsed.username or parsed.password or parsed.port:
            raise ValueError("Invalid YouTube authority")
    except ValueError as exc:
        raise ValueError("Invalid YouTube video URL") from exc
    host = (parsed.hostname or "").lower()
    parts = parsed.path.strip("/").split("/")
    if host in ("youtu.be", "www.youtu.be"):
        candidate = parts[0] if len(parts) == 1 else ""
    elif host in ("youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com"):
        if parsed.path == "/watch":
            ids = parse_qs(parsed.query).get("v", [])
            candidate = ids[0] if len(ids) == 1 else ""
        elif len(parts) == 2 and parts[0] in ("shorts", "live"):
            candidate = parts[1]
        else:
            candidate = ""
    else:
        candidate = ""
    if not VIDEO_ID.fullmatch(candidate):
        raise ValueError("Enter a single YouTube video URL containing an 11-character Video ID")
    return candidate


def canonical_url(url: str) -> str:
    return "https://www.youtube.com/watch?v=" + video_id_from_url(url)


def planned_paths(item: dict):
    vid = video_id_from_url(item["url"])
    folder = Path(item["output"]).expanduser()
    mode = item["mode"]
    if mode == "Audio Only":
        ext = str(item.get("audio_format", "MP3")).lower()
        if ext not in ("mp3", "wav", "m4a"):
            raise ValueError("Unsupported audio format")
    elif mode in ("Video Only", "Full Video"):
        ext = str(item.get("video_format", "MP4")).lower()
        if ext not in ("mp4", "mkv"):
            raise ValueError("Unsupported video format")
    else:
        raise ValueError("Unsupported mode")
    return folder, folder / (vid + "." + ext), folder / (vid + ".jpg") if item.get("download_thumbnail") else None


def valid_jpeg(path: Path) -> bool:
    try:
        with path.open("rb") as f:
            return path.stat().st_size >= 100 and f.read(3) == b"\xff\xd8\xff"
    except OSError:
        return False


def download_video(item: dict, cancel: threading.Event, notify) -> None:
    """Keep original yt-dlp API, format selector, retry and extract-audio pipeline."""
    import yt_dlp

    vid = video_id_from_url(item["url"])
    folder, expected, image = planned_paths(item)
    folder.mkdir(parents=True, exist_ok=True)
    ffmpeg, _ = ffmpeg_paths()
    if (item["mode"] in ("Audio Only", "Full Video") or image is not None) and not ffmpeg:
        raise RuntimeError("FFmpeg is required. Use the bundled Windows EXE.")

    def hook(d):
        if cancel.is_set():
            raise RuntimeError("Cancelled; partial downloads retained")
        n = float(d.get("downloaded_bytes") or 0)
        total = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
        notify(round(100 * n / total, 1) if total else 0)

    opts = {
        "format": selector(item["mode"], item["quality"]),
        "outtmpl": str(folder / "%(id)s.%(ext)s"),
        "noplaylist": True, "continuedl": True, "overwrites": False,
        "quiet": True, "progress_hooks": [hook],
    }
    if ffmpeg:
        opts["ffmpeg_location"] = str(Path(ffmpeg).parent)
    processors = []
    if item["mode"] == "Audio Only":
        processors.append({"key": "FFmpegExtractAudio",
                           "preferredcodec": item["audio_format"].lower(), "preferredquality": "192"})
    elif item["mode"] == "Full Video":
        opts["merge_output_format"] = item["video_format"].lower()
    if image is not None and not valid_jpeg(image):
        opts["writethumbnail"] = True
        processors.append({"key": "FFmpegThumbnailsConvertor", "format": "jpg"})
    if processors:
        opts["postprocessors"] = processors

    def media_exists():
        if expected.is_file() and expected.stat().st_size > 0:
            return True
        if item["mode"] == "Video Only":
            return any((folder / (vid + "." + ext)).is_file() for ext in VIDEO_EXT)
        return False

    if cancel.is_set():
        raise RuntimeError("Cancelled")
    ready_media = media_exists()
    ready_image = image is None or valid_jpeg(image)
    if ready_media and ready_image:
        notify(100)
        return
    if ready_media:
        # Never re-download or overwrite an existing audio file just for its thumbnail.
        opts["skip_download"] = True
        opts["writethumbnail"] = True
        opts["postprocessors"] = [{"key": "FFmpegThumbnailsConvertor", "format": "jpg"}]
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(canonical_url(item["url"]), download=True)
        if not info or str(info.get("id") or "") != vid:
            raise RuntimeError("YouTube did not return the requested Video ID")
    if cancel.is_set():
        raise RuntimeError("Cancelled; partial files retained")
    if not media_exists():
        raise RuntimeError("Downloaded media missing: " + expected.name)
    if image is not None and not valid_jpeg(image):
        raise RuntimeError("Matching JPG thumbnail unavailable; audio kept for retry")
    notify(100)
