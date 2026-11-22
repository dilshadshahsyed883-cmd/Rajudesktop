"""YouTube download and snapshots tab for Smart Media Manager."""
from __future__ import annotations

import hashlib
import json
import os
import queue
import re
import shutil
import subprocess
import sys
import threading
import uuid
from pathlib import Path
from urllib.parse import urlparse, parse_qs
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

QUALITIES = ("Best", "2160p", "1440p", "1080p", "720p", "480p", "360p")
RESOLUTIONS = ("Original", "1080p", "720p", "480p")

def valid_url(url):
    try:
        x = urlparse(url.strip())
        return x.scheme in ("http", "https") and (x.hostname or "").lower() in (
            "youtube.com", "www.youtube.com", "m.youtube.com", "music.youtube.com",
            "youtu.be", "www.youtube-nocookie.com") and bool(x.path.strip("/"))
    except ValueError:
        return False

def timestamp(value):
    if not str(value).strip():
        return 0
    parts = str(value).strip().split(":")
    if len(parts) > 3 or any(not x.isdecimal() for x in parts):
        raise ValueError("Use seconds, MM:SS or HH:MM:SS")
    if any(int(x) >= 60 for x in parts[1:]):
        raise ValueError("Invalid minutes/seconds")
    result = 0
    for x in parts:
        result = result * 60 + int(x)
    return result

def new_snapshot_job(config):
    """Validate and freeze one snapshot job for the durable FIFO queue."""
    from smart_media_manager.cutter_queue import safe_name, VIDEO_TYPES
    local = str(config.get("local_video") or "").strip()
    url = str(config.get("url") or "").strip()
    if local:
        video = Path(local).expanduser().resolve()
        if not video.is_file() or video.suffix.lower() not in VIDEO_TYPES:
            raise ValueError("Selected PC video is missing or unsupported")
        default_name = video.stem
        local = str(video)
        url = ""
    elif valid_url(url):
        parsed = urlparse(url)
        video_id = parse_qs(parsed.query).get("v", [""])[0] or parsed.path.rstrip("/").split("/")[-1]
        default_name = "YouTube " + video_id
    else:
        raise ValueError("Choose a PC video or enter a valid YouTube URL")
    interval = int(config["interval"])
    quality = int(config["quality"])
    start = timestamp(config.get("start", ""))
    end_raw = str(config.get("end", ""))
    end = timestamp(end_raw) if end_raw.strip() else None
    if not 1 <= interval <= 3600 or not 1 <= quality <= 100:
        raise ValueError("Interval must be 1-3600 seconds and quality must be 1-100")
    if end is not None and end <= start:
        raise ValueError("End time must follow start")
    if config.get("format") not in ("JPG", "PNG"):
        raise ValueError("Snapshot format must be JPG or PNG")
    if config.get("resolution") not in RESOLUTIONS:
        raise ValueError("Invalid snapshot resolution")
    if not str(config.get("output") or "").strip():
        raise ValueError("Choose an output folder")
    return {
        "id": uuid.uuid4().hex, "name": safe_name(config.get("name") or default_name),
        "url": url, "local_video": local, "output": str(config["output"]),
        "interval": str(interval), "format": config["format"],
        "quality": str(quality), "resolution": config["resolution"],
        "start": str(config.get("start", "")), "end": end_raw,
        "status": "Queued", "progress": 0, "frames": 0,
    }


def selector(mode, quality):
    number = re.search(r"\d+", quality)
    cap = "[height<=" + number.group(0) + "]" if number else ""
    if mode == "Audio Only":
        return "bestaudio[ext=m4a]/bestaudio/best"
    if mode == "Video Only":
        return "bestvideo" + cap + "[ext=mp4]/bestvideo" + cap
    return ("bestvideo" + cap + "[ext=mp4]+bestaudio[ext=m4a]/"
            "bestvideo" + cap + "+bestaudio/best" + cap)

def ffmpeg_paths():
    locations = [Path(sys.executable).resolve().parent / "bin",
                 Path(__file__).resolve().parent.parent / "video_clip_cutter" / "bin"]
    if getattr(sys, "_MEIPASS", None):
        locations.insert(0, Path(sys._MEIPASS) / "bin")
    for location in locations:
        ffmpeg = location / ("ffmpeg.exe" if os.name == "nt" else "ffmpeg")
        ffprobe = location / ("ffprobe.exe" if os.name == "nt" else "ffprobe")
        if ffmpeg.is_file() and ffprobe.is_file():
            return str(ffmpeg), str(ffprobe)
    return shutil.which("ffmpeg"), shutil.which("ffprobe")

def download_video(item, cancel, notify):
    import yt_dlp
    if not valid_url(item["url"]):
        raise ValueError("Invalid YouTube URL")
    folder = Path(item["output"]).expanduser()
    folder.mkdir(parents=True, exist_ok=True)
    ffmpeg, _ = ffmpeg_paths()
    def hook(d):
        if cancel.is_set():
            raise RuntimeError("Cancelled — part files kept for resume")
        downloaded = float(d.get("downloaded_bytes") or 0)
        total = float(d.get("total_bytes") or d.get("total_bytes_estimate") or 0)
        notify(round(downloaded * 100 / total, 1) if total else 0)
    opts = {"format": selector(item["mode"], item["quality"]),
            "outtmpl": str(folder / "%(title).150B [%(id)s].%(ext)s"),
            "noplaylist": True, "continuedl": True, "overwrites": False,
            "quiet": True, "progress_hooks": [hook]}
    if ffmpeg:
        opts["ffmpeg_location"] = str(Path(ffmpeg).parent)
    if item["mode"] == "Audio Only":
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                   "preferredcodec": item["audio_format"].lower(),
                                   "preferredquality": "192"}]
    elif item["mode"] == "Full Video":
        opts["merge_output_format"] = item["video_format"].lower()
    with yt_dlp.YoutubeDL(opts) as ydl:
        if not ydl.extract_info(item["url"], download=True):
            raise RuntimeError("Download did not return a video")
    if cancel.is_set():
        raise RuntimeError("Cancelled — part files kept for resume")

def snapshot_video(config, cancel, pause, notify):
    """Extract snapshots from a downloaded YouTube video or directly from a PC video."""
    local = str(config.get("local_video") or "").strip()
    if not local and not valid_url(config.get("url", "")):
        raise ValueError("Choose a video from PC or enter a valid YouTube URL")
    ffmpeg, ffprobe = ffmpeg_paths()
    if not ffmpeg or not ffprobe:
        raise RuntimeError("FFmpeg and FFprobe required")
    root = Path(config["output"]).expanduser()
    folder = root
    if config.get("id"):
        # Each queued job owns an isolated destination, including on retry.
        from smart_media_manager.cutter_queue import safe_name
        folder = root / f'{safe_name(config["name"])} [{config["id"][:8]}]'
    elif local:
        from smart_media_manager.cutter_queue import safe_name, VIDEO_TYPES
        source = Path(local).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() not in VIDEO_TYPES:
            raise ValueError("Choose a valid video file on your PC")
        # Legacy direct snapshots keep their previous destination format.
        folder = root / (safe_name(source.stem) + " snapshots")
    if local and config.get("id"):
        from smart_media_manager.cutter_queue import VIDEO_TYPES
        source = Path(local).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() not in VIDEO_TYPES:
            raise ValueError("Choose a valid video file on your PC")
    folder.mkdir(parents=True, exist_ok=True)
    start = timestamp(config["start"])
    end = timestamp(config["end"]) if config["end"].strip() else None
    interval = int(config["interval"])
    if interval < 1 or interval > 3600:
        raise ValueError("Interval must be 1–3600 seconds")
    if end is not None and end <= start:
        raise ValueError("End must follow start")
    notify("Reading local video" if local else "Reading YouTube video", 0, 0)
    if not local:
        # Reuse the Video Clip Cutter downloader, including its format selection,
        # FFmpeg configuration, resume behavior and completed-source cache.
        # A stable ID lets snapshots reuse the same source after a restart without
        # mixing different URLs together in the shared snapshot cache.
        from smart_media_manager.cutter_queue import download_source
        url = config["url"].strip()
        source_job = {
            "id": hashlib.sha256(url.encode("utf-8")).hexdigest()[:24],
            "source": url,
        }
        if cancel.is_set():
            return 0
        try:
            source = download_source(
                source_job, (root if config.get("id") else folder) / ".snapshot_cache", cancel,
                lambda stage, percent, detail:
                    notify(f"{detail} ({percent}%)", 0, 0))
        except Exception as exc:
            if "Requested format is not available" in str(exc):
                raise RuntimeError(
                    "YouTube did not provide an accessible video format. "
                    "Snapshots use the same download engine as Video Clip Cutter. "
                    "Try an updated yt-dlp or a different accessible video, "
                    "or use 'Choose Video from PC'.") from exc
            raise
        if cancel.is_set():
            return 0
    probe = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                            "-of", "default=noprint_wrappers=1:nokey=1", str(source)],
                           capture_output=True, text=True, timeout=40, check=True)
    duration = float(probe.stdout.strip())
    finish = min(duration, end) if end is not None else duration
    if finish <= start:
        raise ValueError("Start exceeds video duration")
    times = [x for x in range(start, int(finish) + 1, interval) if x < duration]
    if len(times) > 20000:
        raise ValueError("Increase interval: more than 20,000 frames")
    fmt = config["format"].lower()
    quality = max(1, min(100, int(config["quality"])))
    scale = [] if config["resolution"] == "Original" else [
        "-vf", "scale=-2:" + re.search(r"\d+", config["resolution"]).group(0)]
    completed = 0
    for index, second in enumerate(times, 1):
        if cancel.is_set():
            break
        while pause.is_set() and not cancel.wait(0.15):
            pass
        if cancel.is_set():
            break
        hour, rem = divmod(second, 3600)
        minute, secs = divmod(rem, 60)
        suffix = ".png" if fmt == "png" else ".jpg"
        prefix = (config["name"] + " ") if config.get("id") else "snapshot_"
        target = folder / f"{prefix}{index:05d}_{hour:02d}-{minute:02d}-{secs:02d}{suffix}"
        if not target.is_file():
            temp = folder / (target.stem + ".partial" + suffix)
            args = [ffmpeg, "-hide_banner", "-loglevel", "error", "-y",
                    "-ss", str(second), "-i", str(source), "-frames:v", "1", *scale]
            args += ["-compression_level", "3"] if fmt == "png" else [
                "-q:v", str(max(2, round(31 - quality * 29 / 100)))]
            try:
                subprocess.run([*args, str(temp)], check=True, capture_output=True, timeout=90)
                os.replace(temp, target)
            finally:
                temp.unlink(missing_ok=True)
        completed += 1
        notify(target.name, index, len(times))
    return completed

class YoutubeTab(ttk.Frame):
    def __init__(self, parent, prefs):
        super().__init__(parent, padding=18)
        self.prefs = prefs
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.snap_cancel = threading.Event()
        self.snap_pause = threading.Event()
        self.snap_stop_queue = threading.Event()
        self.snap_work_items = None
        self.snap_active_id = None
        self.downloading = False
        self.snap_running = False
        self.running = False
        self.queue_file = (Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
                           / "SmartMediaManager" / "youtube_queue.json")
        self.jobs = self._read_queue()
        self.snapshot_queue_file = self.queue_file.with_name("snapshot_queue.json")
        self.snapshot_jobs = self._read_snapshot_queue()
        self.output = tk.StringVar(value=prefs.get("yt_output", str(Path.home() / "Documents" / "YouTube Downloads")))
        self.mode = tk.StringVar(value=prefs.get("yt_mode", "Full Video"))
        self.quality = tk.StringVar(value=prefs.get("yt_quality", "1080p"))
        self.video_format = tk.StringVar(value=prefs.get("yt_video_format", "MP4"))
        self.audio_format = tk.StringVar(value=prefs.get("yt_audio_format", "MP3"))
        self.snapshot_local = tk.StringVar()
        self.snapshot_name = tk.StringVar()
        self.snapshot_output = tk.StringVar(value=prefs.get("yt_snap_output", str(Path.home() / "Documents" / "YouTube Snapshots")))
        self.interval = tk.StringVar(value="5")
        self.snap_format = tk.StringVar(value="JPG")
        self.snap_quality = tk.StringVar(value="90")
        self.resolution = tk.StringVar(value="Original")
        self.start_time = tk.StringVar()
        self.end_time = tk.StringVar()
        self.status = tk.StringVar(value="Ready")
        self.snap_status = tk.StringVar(value="Ready")
        self.snapshot_stats = tk.StringVar(value="")
        self.percent = tk.DoubleVar(value=0)
        self._build()
        self.after(150, self._poll)

    def _read_queue(self):
        try:
            data = json.loads(self.queue_file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            result = [x for x in data if isinstance(x, dict) and all(
                name in x for name in ("id", "url", "output", "mode", "quality"))]
            for row in result:
                if row.get("status") == "Downloading":
                    row["status"] = "Queued"
            return result[-500:]
        except (OSError, ValueError):
            return []

    def _save(self):
        self.queue_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.queue_file.with_suffix(".tmp")
        temp.write_text(json.dumps(self.jobs[-500:], indent=2), encoding="utf-8")
        os.replace(temp, self.queue_file)

    def _read_snapshot_queue(self):
        try:
            data = json.loads(self.snapshot_queue_file.read_text(encoding="utf-8"))
            if not isinstance(data, list):
                return []
            required = ("id", "name", "output", "interval", "format",
                        "quality", "resolution", "status")
            jobs = [job for job in data[-500:] if isinstance(job, dict)
                    and all(field in job for field in required)]
            for job in jobs:
                if job["status"] in ("Downloading", "Extracting", "Preparing"):
                    job["status"] = "Queued"
                    job["progress"] = 0
            return jobs
        except (OSError, ValueError):
            return []

    def _save_snapshot_queue(self):
        self.snapshot_queue_file.parent.mkdir(parents=True, exist_ok=True)
        temp = self.snapshot_queue_file.with_suffix(".tmp")
        temp.write_text(json.dumps(self.snapshot_jobs, ensure_ascii=False, indent=2),
                        encoding="utf-8")
        os.replace(temp, self.snapshot_queue_file)

    def _refresh_snapshot_queue(self):
        selected = set(self.snapshot_tree.selection())
        self.snapshot_tree.delete(*self.snapshot_tree.get_children())
        for job in self.snapshot_jobs:
            source = "PC" if job.get("local_video") else "YouTube"
            self.snapshot_tree.insert(
                "", "end", iid=job["id"],
                values=(job["name"], source, str(job["interval"]) + "s",
                        job["format"], str(round(job.get("progress", 0))) + "%",
                        str(job["status"])[:105]))
        for identifier in selected:
            if self.snapshot_tree.exists(identifier):
                self.snapshot_tree.selection_add(identifier)
        waiting = sum(j["status"] == "Queued" for j in self.snapshot_jobs)
        done = sum(j["status"] == "Completed" for j in self.snapshot_jobs)
        self.snapshot_stats.set(
            f"{len(self.snapshot_jobs)} total  •  {waiting} waiting  •  {done} completed")

    def _set_snapshot_running(self, running):
        self.snap_running = running
        self.running = self.downloading or running
        for control in (self.snapshot_start_button, self.snapshot_retry_button,
                        self.snapshot_remove_button, self.snapshot_clear_button):
            control.configure(state="disabled" if running else "normal")
        self.snapshot_pause_button.configure(state="normal" if running else "disabled")
        self.snapshot_cancel_button.configure(state="normal" if running else "disabled")
        self.snapshot_stop_button.configure(state="normal" if running else "disabled")

    def _folder(self, parent, variable):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(5, 13))
        ttk.Entry(row, textvariable=variable).pack(side="left", fill="x", expand=True)
        def choose():
            folder = filedialog.askdirectory()
            if folder:
                variable.set(folder)
        ttk.Button(row, text="Browse", command=choose).pack(side="left", padx=5)
        ttk.Button(row, text="Open Folder", command=lambda: self.open_folder(variable.get())).pack(side="left")

    @staticmethod
    def open_folder(value):
        folder = Path(value).expanduser()
        if not folder.is_dir():
            messagebox.showinfo("Output", "Output folder does not exist yet")
        elif os.name == "nt":
            os.startfile(str(folder))
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(folder)])

    def _build(self):
        ttk.Label(self, text="YouTube Video Downloader", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(self, text="Full video, silent video, audio, snapshot frames and saved queue",
                  style="Muted.TLabel").pack(anchor="w", pady=(3, 12))
        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True)
        dl = ttk.Frame(tabs, padding=12)
        sn = ttk.Frame(tabs, padding=12)
        jobs = ttk.Frame(tabs, padding=12)
        tabs.add(dl, text="Download")
        tabs.add(sn, text="Snapshots")
        tabs.add(jobs, text="Queue")
        ttk.Label(dl, text="YouTube URLs (one per line)").pack(anchor="w")
        self.links = tk.Text(dl, height=5)
        self.links.pack(fill="x", pady=6)
        row = ttk.Frame(dl)
        row.pack(fill="x", pady=9)
        for label, var, values in (
            ("Mode", self.mode, ("Full Video", "Video Only", "Audio Only")),
            ("Quality", self.quality, QUALITIES),
            ("Video format", self.video_format, ("MP4", "MKV")),
            ("Audio format", self.audio_format, ("MP3", "M4A", "WAV"))):
            cell = ttk.Frame(row)
            cell.pack(side="left", padx=(0, 13))
            ttk.Label(cell, text=label).pack(anchor="w")
            ttk.Combobox(cell, state="readonly", textvariable=var,
                         values=values, width=15).pack()
        ttk.Label(dl, text="Output folder").pack(anchor="w")
        self._folder(dl, self.output)
        row = ttk.Frame(dl)
        row.pack(fill="x", pady=9)
        ttk.Button(row, text="Add to Queue & Start", command=self.add).pack(side="left")
        ttk.Button(row, text="Cancel Current", command=self.cancel_current).pack(side="left", padx=10)
        ttk.Button(row, text="Retry Failed", command=self.retry).pack(side="left")
        ttk.Progressbar(dl, maximum=100, variable=self.percent).pack(fill="x", pady=12)
        ttk.Label(dl, textvariable=self.status).pack(anchor="w")
        ttk.Label(dl, text="Only download content you have permission to use.",
                  style="Muted.TLabel").pack(anchor="w", pady=12)
        ttk.Label(sn, text="YouTube URLs (one per line; optional if using PC videos)").pack(anchor="w")
        self.snapshot_links = tk.Text(sn, height=2, wrap="word")
        self.snapshot_links.pack(fill="x", pady=6)
        ttk.Label(sn, text="Or select a local video — no download needed").pack(anchor="w")
        source_row = ttk.Frame(sn)
        source_row.pack(fill="x", pady=(5, 9))
        ttk.Entry(source_row, textvariable=self.snapshot_local).pack(side="left", fill="x", expand=True)
        ttk.Button(source_row, text="Choose Video from PC", command=self.choose_snapshot_video).pack(side="left", padx=(6, 0))
        ttk.Button(source_row, text="Add PC Videos", command=self.add_snapshot_pc_batch).pack(side="left", padx=(6, 0))
        ttk.Button(source_row, text="Clear", command=lambda: self.snapshot_local.set("")).pack(side="left", padx=(6, 0))
        ttk.Label(sn, text="Snapshot name (optional; used for folder and filenames)").pack(anchor="w")
        ttk.Entry(sn, textvariable=self.snapshot_name).pack(fill="x", pady=(4, 9))
        ttk.Label(sn, text="Output folder").pack(anchor="w")
        self._folder(sn, self.snapshot_output)
        row = ttk.Frame(sn)
        row.pack(fill="x", pady=8)
        for label, var, choices, width in (
            ("Interval (sec)", self.interval, None, 9),
            ("Format", self.snap_format, ("JPG", "PNG"), 7),
            ("Quality (1-100)", self.snap_quality, None, 8),
            ("Resolution", self.resolution, RESOLUTIONS, 13)):
            cell = ttk.Frame(row)
            cell.pack(side="left", padx=(0, 13))
            ttk.Label(cell, text=label).pack(anchor="w")
            widget = (ttk.Combobox(cell, textvariable=var, values=choices, width=width, state="readonly")
                      if choices else ttk.Entry(cell, textvariable=var, width=width))
            widget.pack()
        row = ttk.Frame(sn)
        row.pack(fill="x", pady=8)
        for label, var in (("Start", self.start_time), ("End", self.end_time)):
            ttk.Label(row, text=label + " (optional)").pack(side="left", padx=5)
            ttk.Entry(row, textvariable=var, width=15).pack(side="left", padx=8)
        row = ttk.Frame(sn)
        row.pack(fill="x", pady=10)
        ttk.Button(row, text="Add to Queue", command=self.add_snapshots).pack(side="left")
        ttk.Button(row, text="Add & Start", command=self.start_snapshots).pack(side="left", padx=6)
        self.snapshot_start_button = ttk.Button(row, text="Start Queue", command=self.start_snapshot_queue)
        self.snapshot_start_button.pack(side="left", padx=6)
        self.snapshot_pause_button = ttk.Button(row, text="Pause / Resume", command=self.pause_snapshots, state="disabled")
        self.snapshot_pause_button.pack(side="left", padx=6)
        self.snapshot_cancel_button = ttk.Button(row, text="Cancel Current", command=self.cancel_snapshot_current, state="disabled")
        self.snapshot_cancel_button.pack(side="left", padx=6)
        self.snapshot_stop_button = ttk.Button(row, text="Stop Queue", command=self.stop_snapshots, state="disabled")
        self.snapshot_stop_button.pack(side="left", padx=6)
        ttk.Label(sn, textvariable=self.snap_status).pack(anchor="w", pady=(2, 6))
        heading = ttk.Frame(sn)
        heading.pack(fill="x", pady=(3, 3))
        ttk.Label(heading, text="Snapshot processing queue", style="Section.TLabel").pack(side="left")
        ttk.Label(heading, textvariable=self.snapshot_stats, style="Muted.TLabel").pack(side="right")
        table_area = ttk.Frame(sn)
        table_area.pack(fill="both", expand=True)
        columns = ("name", "source", "interval", "format", "progress", "status")
        self.snapshot_tree = ttk.Treeview(
            table_area, columns=columns, show="headings", height=6,
            selectmode="extended", style="Queue.Treeview")
        for col, title, width in (
            ("name", "Snapshot name", 220), ("source", "Input", 75),
            ("interval", "Interval", 75), ("format", "Format", 65),
            ("progress", "Progress", 90), ("status", "Status", 230)):
            self.snapshot_tree.heading(col, text=title)
            self.snapshot_tree.column(col, width=width, minwidth=60,
                                      stretch=col in ("name", "status"))
        self.snapshot_tree.pack(side="left", fill="both", expand=True)
        scrollbar = ttk.Scrollbar(table_area, orient="vertical",
                                 command=self.snapshot_tree.yview)
        self.snapshot_tree.configure(yscrollcommand=scrollbar.set)
        scrollbar.pack(side="right", fill="y")
        snap_actions = ttk.Frame(sn)
        snap_actions.pack(fill="x", pady=(6, 3))
        self.snapshot_retry_button = ttk.Button(
            snap_actions, text="Retry Failed", command=self.retry_snapshot_failed)
        self.snapshot_retry_button.pack(side="left")
        self.snapshot_remove_button = ttk.Button(
            snap_actions, text="Remove Completed", command=self.remove_completed_snapshots)
        self.snapshot_remove_button.pack(side="left", padx=6)
        self.snapshot_clear_button = ttk.Button(
            snap_actions, text="Remove Selected", command=self.remove_selected_snapshots)
        self.snapshot_clear_button.pack(side="left", padx=6)
        ttk.Label(sn, text="One snapshot job at a time • named output folders • saved queue • cached YouTube sources",
                  style="Muted.TLabel").pack(anchor="w", pady=(4, 0))
        self.tree = ttk.Treeview(jobs, columns=("url", "mode", "pct", "status"), show="headings")
        for col, width in (("url", 450), ("mode", 120), ("pct", 70), ("status", 180)):
            self.tree.heading(col, text=col.title())
            self.tree.column(col, width=width)
        self.tree.pack(fill="both", expand=True)
        row = ttk.Frame(jobs)
        row.pack(fill="x", pady=9)
        ttk.Button(row, text="Retry Selected", command=self.retry_selected).pack(side="left")
        ttk.Button(row, text="Remove Completed", command=self.remove_completed).pack(side="left", padx=8)
        self._refresh()
        self._refresh_snapshot_queue()

    def _refresh(self):
        self.tree.delete(*self.tree.get_children())
        for job in self.jobs:
            self.tree.insert("", "end", iid=job["id"], values=(
                job["url"][:90], job["mode"], str(round(job.get("progress", 0))) + "%",
                job.get("status", "Queued")[:100]))

    def add(self):
        links = [x.strip() for x in self.links.get("1.0", "end").splitlines() if x.strip()]
        if not links or any(not valid_url(x) for x in links):
            messagebox.showerror("Links", "Enter valid YouTube URLs, one per line")
            return
        for key, var in (("yt_output", self.output), ("yt_mode", self.mode),
                         ("yt_quality", self.quality), ("yt_video_format", self.video_format),
                         ("yt_audio_format", self.audio_format)):
            self.prefs.set(key, var.get())
        for link in links:
            self.jobs.append({"id": uuid.uuid4().hex, "url": link, "mode": self.mode.get(),
                              "quality": self.quality.get(), "video_format": self.video_format.get(),
                              "audio_format": self.audio_format.get(), "output": self.output.get(),
                              "status": "Queued", "progress": 0})
        self._save()
        self._refresh()
        self.links.delete("1.0", "end")
        self._next()

    def _next(self):
        if self.downloading:
            return
        job = next((x for x in self.jobs if x.get("status") == "Queued"), None)
        if not job:
            self.running = self.snap_running
            return
        self.cancel.clear()
        self.downloading = self.running = True
        job["status"] = "Downloading"
        self._refresh()
        identifier = job["id"]
        def work():
            try:
                download_video(job.copy(), self.cancel, lambda pct: self.events.put(("progress", identifier, pct)))
                state = "Completed"
            except Exception as exc:
                state = ("Cancelled" if self.cancel.is_set() else "Failed: " + str(exc))
            self.events.put(("done", identifier, state))
        threading.Thread(target=work, daemon=True).start()

    def cancel_current(self):
        self.cancel.set()

    def retry(self):
        for job in self.jobs:
            if job.get("status", "").startswith(("Failed", "Cancelled")):
                job["status"] = "Queued"
        self._save()
        self._refresh()
        self._next()

    def retry_selected(self):
        for identifier in self.tree.selection():
            job = next((x for x in self.jobs if x["id"] == identifier), None)
            if job and job.get("status") != "Downloading":
                job["status"] = "Queued"
        self._save()
        self._refresh()
        self._next()

    def remove_completed(self):
        self.jobs = [x for x in self.jobs if x.get("status") != "Completed"]
        self._save()
        self._refresh()

    def choose_snapshot_video(self):
        chosen = filedialog.askopenfilename(title="Choose video for snapshots", filetypes=[
            ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wmv *.ts"),
            ("All files", "*.*")])
        if chosen:
            self.snapshot_local.set(chosen)

    def add_snapshot_pc_batch(self):
        chosen = filedialog.askopenfilenames(
            title="Add multiple PC videos to snapshot queue", filetypes=[
                ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wmv *.ts"),
                ("All files", "*.*")])
        if chosen:
            self._queue_snapshots(locals=list(chosen))

    def _queue_snapshots(self, locals=None, start=False):
        """Freeze all settings for each newly queued source, even while running."""
        if locals is None:
            local = self.snapshot_local.get().strip()
            if local:
                locals = [local]
                urls = []
            else:
                locals = []
                urls = [s.strip() for s in self.snapshot_links.get("1.0", "end").splitlines()
                        if s.strip()]
        else:
            urls = []
        sources = [("local_video", source) for source in locals]
        sources += [("url", url) for url in urls]
        if not sources:
            messagebox.showerror("Snapshot source", "Choose PC videos or paste YouTube URLs")
            return
        try:
            if len(self.snapshot_jobs) + len(sources) > 500:
                raise ValueError("Snapshot queue limit is 500 items. Remove old jobs first.")
            base = {
                "output": self.snapshot_output.get(), "interval": self.interval.get(),
                "format": self.snap_format.get(), "quality": self.snap_quality.get(),
                "resolution": self.resolution.get(), "start": self.start_time.get(),
                "end": self.end_time.get(),
            }
            name = self.snapshot_name.get().strip()
            additions = []
            for index, (kind, source) in enumerate(sources, 1):
                config = dict(base)
                config.update({"local_video": "", "url": "", "name":
                               f"{name} {index}" if name and len(sources) > 1 else name})
                config[kind] = source
                additions.append(new_snapshot_job(config))
            self.prefs.set("yt_snap_output", self.snapshot_output.get())
            self.snapshot_jobs.extend(additions)
            self._save_snapshot_queue()
            self._refresh_snapshot_queue()
            if not locals:
                self.snapshot_links.delete("1.0", "end")
            if self.snap_running and self.snap_work_items is not None and not self.snap_stop_queue.is_set():
                for job in additions:
                    self.snap_work_items.put(job.copy())
                self.snap_status.set(f"Added {len(additions)} job(s) to running snapshot queue")
            else:
                self.snap_status.set(f"Added {len(additions)} snapshot job(s) to queue")
                if start and not self.snap_running:
                    self.start_snapshot_queue()
        except (ValueError, OSError, TypeError) as exc:
            messagebox.showerror("Snapshot queue", str(exc))

    def add_snapshots(self):
        self._queue_snapshots()

    def start_snapshots(self):
        # Preserve the original quick-start action, now adding to a durable queue.
        self._queue_snapshots(start=True)

    def start_snapshot_queue(self):
        if self.snap_running:
            return
        pending = [job.copy() for job in self.snapshot_jobs if job["status"] == "Queued"]
        if not pending:
            messagebox.showinfo("Snapshot queue", "No queued snapshot jobs")
            return
        self.snap_cancel.clear()
        self.snap_stop_queue.clear()
        self.snap_pause.clear()
        self.snap_work_items = queue.Queue()
        for job in pending:
            self.snap_work_items.put(job)
        self._set_snapshot_running(True)
        self.snap_status.set(f"Starting snapshot queue: {len(pending)} item(s)")
        threading.Thread(target=self._snapshot_worker, daemon=True,
                         name="snapshot-queue").start()

    def _snapshot_worker(self):
        """Process one snapshot job at a time; allow additions during a running job."""
        completed = 0
        while not self.snap_stop_queue.is_set():
            try:
                job = self.snap_work_items.get(timeout=0.15)
            except queue.Empty:
                break
            identifier = job["id"]
            self.snap_cancel.clear()
            self.events.put(("snap_state", identifier, "Preparing"))
            def notify(detail, index, total, job_id=identifier):
                self.events.put(("snap_progress", job_id, detail, index, total))
            try:
                frames = snapshot_video(job, self.snap_cancel, self.snap_pause, notify)
                if self.snap_cancel.is_set():
                    state = "Cancelled"
                else:
                    completed += 1
                    state = "Completed"
                self.events.put(("snap_done", identifier, state, frames))
            except Exception as exc:
                state = ("Cancelled" if self.snap_cancel.is_set()
                         else "Failed: " + str(exc)[:160])
                self.events.put(("snap_done", identifier, state, 0))
        self.events.put(("snap_finished", completed, self.snap_stop_queue.is_set()))

    def pause_snapshots(self):
        if self.snap_running:
            if self.snap_pause.is_set():
                self.snap_pause.clear()
                self.snap_status.set("Resuming snapshot queue...")
            else:
                self.snap_pause.set()
                self.snap_status.set("Pausing snapshot extraction...")

    def cancel_snapshot_current(self):
        if self.snap_running:
            self.snap_cancel.set()
            self.snap_pause.clear()
            self.snap_status.set("Cancelling current snapshot; next queued item will continue")

    def stop_snapshots(self):
        if self.snap_running:
            self.snap_stop_queue.set()
            self.snap_cancel.set()
            self.snap_pause.clear()
            self.snap_status.set("Stopping snapshot queue; pending jobs remain saved")

    def retry_snapshot_failed(self):
        if self.snap_running:
            return
        changed = False
        for job in self.snapshot_jobs:
            if str(job["status"]).startswith(("Failed", "Cancelled")):
                job["status"] = "Queued"
                job["progress"] = 0
                changed = True
        if changed:
            self._save_snapshot_queue()
            self._refresh_snapshot_queue()
            self.snap_status.set("Failed/cancelled snapshot jobs requeued")

    def remove_completed_snapshots(self):
        if self.snap_running:
            return
        self.snapshot_jobs = [job for job in self.snapshot_jobs
                              if job["status"] != "Completed"]
        self._save_snapshot_queue()
        self._refresh_snapshot_queue()

    def remove_selected_snapshots(self):
        if self.snap_running:
            return
        selected = set(self.snapshot_tree.selection())
        self.snapshot_jobs = [job for job in self.snapshot_jobs
                              if job["id"] not in selected]
        self._save_snapshot_queue()
        self._refresh_snapshot_queue()

    def _poll(self):
        try:
            for _ in range(80):
                item = self.events.get_nowait()
                if item[0] == "progress":
                    _, identifier, pct = item
                    job = next((x for x in self.jobs if x["id"] == identifier), None)
                    if job:
                        job["progress"] = pct
                        self.percent.set(pct)
                        self.status.set("Downloading: " + str(pct) + "%")
                        if self.tree.exists(identifier):
                            self.tree.item(identifier, values=(
                                job["url"][:90], job["mode"], str(round(pct)) + "%", job["status"]))
                elif item[0] == "done":
                    _, identifier, state = item
                    job = next((x for x in self.jobs if x["id"] == identifier), None)
                    if job:
                        job["status"] = state
                        if state == "Completed":
                            job["progress"] = 100
                    self.downloading = False
                    self.running = self.snap_running
                    self.status.set(state)
                    self._save()
                    self._refresh()
                    self._next()
                elif item[0] == "snap_state":
                    _, identifier, stage = item
                    job = next((j for j in self.snapshot_jobs if j["id"] == identifier), None)
                    if job:
                        job["status"] = stage
                        self.snap_active_id = identifier
                        self._save_snapshot_queue()
                        self._refresh_snapshot_queue()
                elif item[0] == "snap_progress":
                    _, identifier, detail, i, n = item
                    job = next((j for j in self.snapshot_jobs if j["id"] == identifier), None)
                    if job:
                        job["status"] = "Extracting" if n else "Downloading"
                        job["progress"] = round(i * 100 / n, 1) if n else 0
                        self.snap_status.set(job["name"] + " — " + str(detail))
                        if self.snapshot_tree.exists(identifier):
                            self.snapshot_tree.item(
                                identifier,
                                values=(job["name"], "PC" if job.get("local_video") else "YouTube",
                                        str(job["interval"]) + "s", job["format"],
                                        str(round(job["progress"])) + "%", job["status"]))
                        if n and (i % 25 == 0 or i == n):
                            self._save_snapshot_queue()
                elif item[0] == "snap_done":
                    _, identifier, stage, frames = item
                    job = next((j for j in self.snapshot_jobs if j["id"] == identifier), None)
                    if job:
                        job["status"] = stage
                        job["frames"] = frames
                        if stage == "Completed":
                            job["progress"] = 100
                        self.snap_status.set(f"{job['name']} — {stage} ({frames} frames)")
                        self._save_snapshot_queue()
                        self._refresh_snapshot_queue()
                elif item[0] == "snap_finished":
                    _, completed, stopped = item
                    self._set_snapshot_running(False)
                    self.snap_work_items = None
                    self.snap_active_id = None
                    self._save_snapshot_queue()
                    self._refresh_snapshot_queue()
                    if not stopped and any(j["status"] == "Queued" for j in self.snapshot_jobs):
                        # An add can race with the worker's empty-queue check.
                        self.start_snapshot_queue()
                    else:
                        self.snap_status.set(
                            f"Snapshot queue ended: {completed} completed this run" +
                            ("; stopped by user" if stopped else ""))
        except queue.Empty:
            pass
        self.after(150, self._poll)
