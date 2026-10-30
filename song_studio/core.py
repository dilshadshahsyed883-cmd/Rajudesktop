"""Song Studio Desktop: local media handoff, safe rendering and upload ledger.

No VPS APIs or credentials are required. Download engine is reused from
song_audio_downloader; Google OAuth tokens always remain on this Windows PC.
"""
from __future__ import annotations

import hashlib
from contextlib import contextmanager
import json
import os
import re
import sqlite3
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from smart_media_manager.youtube_downloader import ffmpeg_paths
from song_audio_downloader.core import download_video, video_id_from_url, valid_jpeg

VIDEO_ID = re.compile(r"^[A-Za-z0-9_-]{11}$")
AUDIO = {".mp3", ".m4a", ".wav"}
PICTURES = {".jpg", ".jpeg", ".png", ".webp"}
APP_HOME = Path(os.getenv("LOCALAPPDATA") or (Path.home() / ".local" / "share")) / "SongStudio"
SCOPES = ["https://www.googleapis.com/auth/youtube.upload", "https://www.googleapis.com/auth/youtube.readonly"]


def safe_folder(value: str) -> str:
    name = value.strip()
    if not name or len(name) > 80 or name in {".", ".."} or name.endswith((".", " ")):
        raise ValueError("Enter a folder name (1-80 characters).")
    if any(x in name for x in '<>:"/\\|?*') or any(ord(c) < 32 for c in name):
        raise ValueError("Folder name contains invalid Windows characters.")
    return name


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(block)
    return h.hexdigest()


def pairs(folder: Path) -> list[dict]:
    """Only exact stem matches. Never guess a thumbnail for a different Video ID."""
    p = Path(folder)
    if not p.is_dir():
        return []
    groups = {}
    for file in p.iterdir():
        if not file.is_file():
            continue
        ext = file.suffix.lower()
        if ext not in AUDIO | PICTURES:
            continue
        key = file.stem.casefold()
        entry = groups.setdefault(key, {"name": file.stem, "audio": [], "images": []})
        entry["audio" if ext in AUDIO else "images"].append(file)
    return [dict(name=e["name"], audio=e["audio"][0], image=e["images"][0])
            for _, e in sorted(groups.items()) if len(e["audio"]) == len(e["images"]) == 1]


def source_identity(video: Path) -> str:
    # Stable Video ID takes precedence over different encodes of the same song.
    name = Path(video).stem
    return "videoid:" + name if VIDEO_ID.fullmatch(name) else "sha256:" + sha256(video)


def ffmpeg_filter(resolution: str = "1080p", fit: str = "Fit") -> str:
    sizes = {"1080p": (1920, 1080), "720p": (1280, 720), "9:16": (1080, 1920)}
    if resolution not in sizes or fit not in {"Fit", "Blur"}:
        raise ValueError("Unsupported render settings")
    w, h = sizes[resolution]
    foreground = (f"scale={w}:{h}:force_original_aspect_ratio=decrease:flags=lanczos,"
                  f"pad={w}:{h}:(ow-iw)/2:(oh-ih)/2:black,setsar=1,format=yuv420p")
    if fit == "Fit":
        return foreground
    # The blurred image fills the canvas while a sharp uncropped foreground remains.
    return (f"split=2[bg][fg];[bg]scale={w}:{h}:force_original_aspect_ratio=increase,"
            f"crop={w}:{h},gblur=sigma=25[blur];[fg]scale={w}:{h}:force_original_aspect_ratio=decrease[front];"
            f"[blur][front]overlay=(W-w)/2:(H-h)/2,setsar=1,format=yuv420p")


def render(image: Path, audio: Path, output: Path, resolution="1080p", fit="Fit",
           quality="Balanced", progress=None, cancelled=None) -> Path:
    image, audio, output = Path(image), Path(audio), Path(output)
    if not image.is_file() or image.suffix.lower() not in PICTURES:
        raise ValueError("Image missing or unsupported")
    if not audio.is_file() or audio.suffix.lower() not in AUDIO:
        raise ValueError("Audio missing or unsupported")
    if image.stem.casefold() != audio.stem.casefold():
        raise ValueError("Audio and image filenames must match exactly")
    if output.exists():
        raise FileExistsError("MP4 already exists; will not overwrite a prior render")
    ffmpeg, ffprobe = ffmpeg_paths()
    if not ffmpeg or not ffprobe:
        raise RuntimeError("Bundled FFmpeg / FFprobe not found")
    crf = {"High": "18", "Balanced": "20", "Compact": "23"}.get(quality)
    if not crf:
        raise ValueError("Unsupported quality preset")
    output.parent.mkdir(parents=True, exist_ok=True)
    temporary = output.with_suffix(".rendering.mp4")
    if temporary.exists():
        raise RuntimeError("Existing partial render found; inspect or remove it before retrying")
    filter_graph = ffmpeg_filter(resolution, fit)
    filters = (["-filter_complex", "[0:v]" + filter_graph + "[out]", "-map", "[out]"]
               if fit == "Blur" else ["-vf", filter_graph, "-map", "0:v:0"])
    command = [str(ffmpeg), "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
               "-loop", "1", "-framerate", "1", "-i", str(image), "-i", str(audio),
               *filters, "-map", "1:a:0", "-c:v", "libx264", "-preset", "veryfast",
               "-tune", "stillimage", "-crf", crf, "-pix_fmt", "yuv420p",
               "-r", "25", "-c:a", "aac", "-b:a", "192k", "-shortest",
               "-movflags", "+faststart", str(temporary)]
    try:
        p = subprocess.Popen(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        while p.poll() is None:
            if cancelled and cancelled.is_set():
                p.kill()
                p.wait()
                raise RuntimeError("Render cancelled")
            time.sleep(0.25)
        err = p.stderr.read().decode("utf-8", "replace")[-1200:]
        p.stderr.close()
        if p.returncode:
            raise RuntimeError("FFmpeg render failed: " + err)
        probe = subprocess.run([str(ffprobe), "-v", "error", "-show_entries",
                                "stream=codec_name", "-of", "json", str(temporary)],
                               capture_output=True, text=True, timeout=30, check=True)
        codecs = {s["codec_name"] for s in json.loads(probe.stdout).get("streams", [])}
        if not {"h264", "aac"}.issubset(codecs) or temporary.stat().st_size <= 0:
            raise RuntimeError("Rendered MP4 failed codec verification")
        temporary.replace(output)
        if progress:
            progress(100)
        return output
    except Exception:
        temporary.unlink(missing_ok=True)
        raise


def download(url: str, folder: Path, progress=None, cancel=None) -> Path:
    # Exact original JPEG and audio produced by the existing tested downloader.
    vid = video_id_from_url(url)
    item = {"url": url, "output": str(folder), "mode": "Audio Only",
            "quality": "Best", "audio_format": "MP3", "video_format": "MP4",
            "download_thumbnail": True}
    download_video(item, cancel or threading.Event(), progress or (lambda _: None))
    audio = Path(folder) / (vid + ".mp3")
    thumb = Path(folder) / (vid + ".jpg")
    if not audio.is_file() or not valid_jpeg(thumb):
        raise RuntimeError("Matching MP3 and original JPEG are required")
    return audio


class StudioStore:
    def __init__(self, root: Path = APP_HOME, media: Path | None = None):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)
        self.media = Path(media) if media else Path.home() / "Documents" / "Song Studio"
        self.media.mkdir(parents=True, exist_ok=True)
        self.tokens = self.root / "tokens"
        self.tokens.mkdir(exist_ok=True)
        self.db = self.root / "studio.sqlite3"
        with self.connect() as db:
            db.executescript("""
                CREATE TABLE IF NOT EXISTS channels (
                    id TEXT PRIMARY KEY, name TEXT NOT NULL, token_file TEXT NOT NULL,
                    group_name TEXT NOT NULL DEFAULT 'Default');
                CREATE TABLE IF NOT EXISTS profiles (
                    id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT NOT NULL UNIQUE,
                    group_name TEXT NOT NULL, folder TEXT NOT NULL,
                    title TEXT NOT NULL DEFAULT '', description TEXT NOT NULL DEFAULT '',
                    category TEXT NOT NULL DEFAULT '10', privacy TEXT NOT NULL DEFAULT 'private');
                CREATE TABLE IF NOT EXISTS uploads (
                    channel_id TEXT NOT NULL, identity TEXT NOT NULL,
                    state TEXT NOT NULL, youtube_id TEXT DEFAULT '',
                    thumbnail_done INTEGER NOT NULL DEFAULT 0,
                    error TEXT DEFAULT '', created TEXT NOT NULL,
                    PRIMARY KEY(channel_id, identity));
            """)

    @contextmanager
    def connect(self):
        db = sqlite3.connect(self.db, timeout=20)
        try:
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA journal_mode=WAL")
            db.execute("PRAGMA busy_timeout=20000")
            with db:
                yield db
        finally:
            db.close()

    def folders(self) -> list[str]:
        return sorted([p.name for p in self.media.iterdir() if p.is_dir() and not p.is_symlink()],
                      key=str.casefold)

    def folder(self, name: str) -> Path:
        selected = self.media / safe_folder(name)
        if selected.is_symlink():
            raise ValueError("Folder symlinks not supported")
        selected.mkdir(exist_ok=True)
        return selected

    def add_channel(self, channel_id: str, name: str, token_file: Path, group="Default"):
        if not channel_id or not name or token_file.parent.resolve() != self.tokens.resolve():
            raise ValueError("Invalid channel or token path")
        with self.connect() as db:
            db.execute("""INSERT INTO channels VALUES(?,?,?,?)
                ON CONFLICT(id) DO UPDATE SET name=excluded.name,
                token_file=excluded.token_file""", (channel_id, name, str(token_file), group))

    def channels(self, group=None):
        with self.connect() as db:
            sql = "SELECT * FROM channels"
            args = []
            if group:
                sql += " WHERE group_name=?"
                args.append(group)
            return [dict(r) for r in db.execute(sql + " ORDER BY name", args)]

    def groups(self):
        return sorted({r["group_name"] for r in self.channels()} | {"Default"})

    def set_group(self, channel_id: str, group: str):
        group = safe_folder(group)
        with self.connect() as db:
            db.execute("UPDATE channels SET group_name=? WHERE id=?", (group, channel_id))

    def save_profile(self, name, group, folder, title, description, category, privacy):
        if not name.strip() or not group.strip() or not folder.strip():
            raise ValueError("Profile name, group and source folder required")
        if privacy not in {"private", "unlisted", "public"}:
            raise ValueError("Invalid privacy")
        if not category.isdecimal():
            raise ValueError("Category must be numeric")
        self.folder(folder)
        with self.connect() as db:
            db.execute("""INSERT INTO profiles(name,group_name,folder,title,description,category,privacy)
              VALUES(?,?,?,?,?,?,?) ON CONFLICT(name) DO UPDATE SET
              group_name=excluded.group_name,folder=excluded.folder,title=excluded.title,
              description=excluded.description,category=excluded.category,privacy=excluded.privacy""",
              (name.strip(), group, folder, title, description, category, privacy))

    def profiles(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute("SELECT * FROM profiles ORDER BY name")]

    def ledger(self):
        with self.connect() as db:
            return [dict(r) for r in db.execute(
                "SELECT * FROM uploads ORDER BY created DESC LIMIT 300")]

    def reserve(self, channel_id: str, identity: str) -> bool:
        with self.connect() as db:
            cur = db.execute("""INSERT OR IGNORE INTO uploads(channel_id,identity,state,created)
                                VALUES(?,?,'reserved',?)""",
                             (channel_id, identity, datetime.now(timezone.utc).isoformat()))
            return cur.rowcount == 1

    def receipt(self, channel_id, identity, youtube_id, thumbnail_done=False, error=""):
        with self.connect() as db:
            db.execute("""UPDATE uploads SET youtube_id=?,state='uploaded',
                thumbnail_done=?,error=? WHERE channel_id=? AND identity=?""",
                (youtube_id, int(thumbnail_done), str(error)[:1000], channel_id, identity))

    def needs_review(self, channel_id, identity, error):
        with self.connect() as db:
            db.execute("""UPDATE uploads SET state='needs_review',error=?
                         WHERE channel_id=? AND identity=? AND state='reserved'""",
                       (str(error)[:1000], channel_id, identity))


def authenticate(client_secrets: Path, tokens_dir: Path):
    """Run the official installed-app OAuth flow; never commit or print secrets."""
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build
    flow = InstalledAppFlow.from_client_secrets_file(str(client_secrets), scopes=SCOPES)
    creds = flow.run_local_server(port=0, open_browser=True, prompt="consent")
    service = build("youtube", "v3", credentials=creds, cache_discovery=False)
    result = service.channels().list(part="snippet", mine=True).execute()
    channels = result.get("items", [])
    if len(channels) != 1:
        raise RuntimeError("OAuth account must have exactly one selected YouTube channel")
    channel = channels[0]
    ident = channel["id"]
    dest = Path(tokens_dir) / (ident + ".json")
    pending = dest.with_suffix(".tmp")
    pending.write_text(creds.to_json(), encoding="utf-8")
    os.replace(pending, dest)
    return ident, channel["snippet"]["title"], dest


def credentials(token_file: Path):
    from google.oauth2.credentials import Credentials
    from google.auth.transport.requests import Request
    creds = Credentials.from_authorized_user_file(str(token_file), SCOPES)
    if not creds.valid and creds.expired and creds.refresh_token:
        creds.refresh(Request())
        temp = Path(token_file).with_suffix(".tmp")
        temp.write_text(creds.to_json(), encoding="utf-8")
        os.replace(temp, token_file)
    if not creds.valid:
        raise RuntimeError("Reconnect this channel through Google OAuth")
    return creds


def upload(studio: StudioStore, channel: dict, video: Path, thumbnail: Path | None,
           title: str, description: str, category="10", privacy="private",
           progress=None) -> tuple[str, bool]:
    """Exactly one automatic attempt per channel/source identity.

    Ambiguous API failures are never automatically retried: review in YouTube
    Studio first to prevent duplicate uploads after a lost API response.
    """
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload

    video = Path(video)
    if not video.is_file() or video.suffix.lower() != ".mp4":
        raise ValueError("Choose a valid rendered MP4")
    if not title.strip() or len(title) > 100:
        raise ValueError("YouTube title must be 1-100 characters")
    if len(description) > 5000 or not str(category).isdecimal():
        raise ValueError("Invalid YouTube metadata")
    if privacy not in {"private", "unlisted", "public"}:
        raise ValueError("Invalid privacy")
    original = Path(thumbnail) if thumbnail else None
    if original is not None:
        if not original.is_file() or original.suffix.lower() != ".jpg" or not valid_jpeg(original):
            raise ValueError("Original JPEG thumbnail is missing")
        if original.stat().st_size > 2_000_000:
            raise ValueError("Original JPEG is over YouTube's 2 MB thumbnail limit")
    creds = credentials(Path(channel["token_file"]))
    service = build("youtube", "v3", credentials=creds, cache_discovery=False)
    identity = source_identity(video)
    if not studio.reserve(channel["id"], identity):
        raise RuntimeError("Already uploaded, queued or needs manual review for this channel/source")
    try:
        request = service.videos().insert(part="snippet,status",
            body={"snippet": {"title": title, "description": description,
                              "categoryId": str(category)},
                  "status": {"privacyStatus": privacy, "selfDeclaredMadeForKids": False}},
            media_body=MediaFileUpload(str(video), mimetype="video/mp4", chunksize=8*1024*1024, resumable=True))
        result = None
        while result is None:
            status, result = request.next_chunk()
            if progress and status:
                progress(round(status.progress() * 100))
        youtube_id = str(result.get("id") or "")
        if not youtube_id:
            raise RuntimeError("YouTube did not return a video ID; check Studio manually")
        # Receipt BEFORE thumbnail: never re-upload an already published video.
        studio.receipt(channel["id"], identity, youtube_id)
        thumbnail_done = False
        if original is not None:
            try:
                service.thumbnails().set(videoId=youtube_id, media_body=MediaFileUpload(
                    str(original), mimetype="image/jpeg", resumable=False)).execute()
                thumbnail_done = True
            except Exception as exc:
                studio.receipt(channel["id"], identity, youtube_id, False,
                               "Video uploaded; thumbnail needs attention: " + str(exc))
                return youtube_id, False
        studio.receipt(channel["id"], identity, youtube_id, thumbnail_done)
        return youtube_id, thumbnail_done
    except Exception as exc:
        studio.needs_review(channel["id"], identity, exc)
        raise


def retry_thumbnail(studio: StudioStore, channel: dict, identity: str, image: Path):
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload
    with studio.connect() as db:
        row = db.execute("""SELECT * FROM uploads WHERE channel_id=? AND identity=?""",
                         (channel["id"], identity)).fetchone()
    if not row or row["state"] != "uploaded" or not row["youtube_id"]:
        raise ValueError("There is no confirmed uploaded video for this channel/source")
    if not valid_jpeg(image) or image.stat().st_size > 2_000_000:
        raise ValueError("Choose the unchanged original JPEG under 2 MB")
    service = build("youtube", "v3", credentials=credentials(Path(channel["token_file"])),
                    cache_discovery=False)
    service.thumbnails().set(videoId=row["youtube_id"], media_body=MediaFileUpload(
        str(image), mimetype="image/jpeg")).execute()
    studio.receipt(channel["id"], identity, row["youtube_id"], True)
