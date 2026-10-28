"""Native fourth tab for Smart Media Manager: YouTube video, audio and snapshots."""
from __future__ import annotations

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
from urllib.parse import urlparse
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
    folder = Path(config["output"]).expanduser()
    if local:
        from smart_media_manager.cutter_queue import safe_name, VIDEO_TYPES
        source = Path(local).expanduser().resolve()
        if not source.is_file() or source.suffix.lower() not in VIDEO_TYPES:
            raise ValueError("Choose a valid video file on your PC")
        # A dedicated folder avoids accidental filename collisions between videos.
        folder = folder / (safe_name(source.stem) + " snapshots")
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
        import yt_dlp
        cache = folder / ".snapshot_cache"
        cache.mkdir(parents=True, exist_ok=True)
        opts = {"format": "best[ext=mp4]/best", "outtmpl": str(cache / "%(id)s.%(ext)s"),
                "noplaylist": True, "quiet": True, "continuedl": True,
                "ffmpeg_location": str(Path(ffmpeg).parent)}
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(config["url"], download=False)
            video_id = str(info.get("id", "video"))
            source = next((p for p in cache.glob(video_id + ".*")
                           if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")), None)
            if source is None:
                if cancel.is_set():
                    return 0
                notify("Downloading snapshot source", 0, 0)
                ydl.extract_info(config["url"], download=True)
                source = next((p for p in cache.glob(video_id + ".*")
                               if p.suffix.lower() in (".mp4", ".mkv", ".webm", ".mov")), None)
        if source is None:
            raise RuntimeError("Source video missing after download")
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
        target = folder / f"snapshot_{index:05d}_{hour:02d}-{minute:02d}-{secs:02d}{suffix}"
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
        self.downloading = False
        self.snap_running = False
        self.running = False
        self.queue_file = (Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share")
                           / "SmartMediaManager" / "youtube_queue.json")
        self.jobs = self._read_queue()
        self.output = tk.StringVar(value=prefs.get("yt_output", str(Path.home() / "Documents" / "YouTube Downloads")))
        self.mode = tk.StringVar(value=prefs.get("yt_mode", "Full Video"))
        self.quality = tk.StringVar(value=prefs.get("yt_quality", "1080p"))
        self.video_format = tk.StringVar(value=prefs.get("yt_video_format", "MP4"))
        self.audio_format = tk.StringVar(value=prefs.get("yt_audio_format", "MP3"))
        self.snapshot_url = tk.StringVar()
        self.snapshot_local = tk.StringVar()
        self.snapshot_output = tk.StringVar(value=prefs.get("yt_snap_output", str(Path.home() / "Documents" / "YouTube Snapshots")))
        self.interval = tk.StringVar(value="5")
        self.snap_format = tk.StringVar(value="JPG")
        self.snap_quality = tk.StringVar(value="90")
        self.resolution = tk.StringVar(value="Original")
        self.start_time = tk.StringVar()
        self.end_time = tk.StringVar()
        self.status = tk.StringVar(value="Ready")
        self.snap_status = tk.StringVar(value="Ready")
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
        ttk.Label(sn, text="YouTube URL (optional if using a video from PC)").pack(anchor="w")
        ttk.Entry(sn, textvariable=self.snapshot_url).pack(fill="x", pady=6)
        ttk.Label(sn, text="Or select a local video — no download needed").pack(anchor="w")
        source_row = ttk.Frame(sn)
        source_row.pack(fill="x", pady=(5, 9))
        ttk.Entry(source_row, textvariable=self.snapshot_local).pack(side="left", fill="x", expand=True)
        ttk.Button(source_row, text="Choose Video from PC", command=self.choose_snapshot_video).pack(side="left", padx=(6, 0))
        ttk.Button(source_row, text="Clear", command=lambda: self.snapshot_local.set("")).pack(side="left", padx=(6, 0))
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
        ttk.Button(row, text="Start Snapshots", command=self.start_snapshots).pack(side="left")
        ttk.Button(row, text="Pause / Resume", command=self.pause_snapshots).pack(side="left", padx=9)
        ttk.Button(row, text="Stop", command=self.stop_snapshots).pack(side="left")
        ttk.Label(sn, textvariable=self.snap_status).pack(anchor="w", pady=8)
        ttk.Label(sn, text="Cached source and completed frames are reused on restart.",
                  style="Muted.TLabel").pack(anchor="w", pady=8)
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

    def start_snapshots(self):
        if self.snap_running:
            return
        local = self.snapshot_local.get().strip()
        if not local and not valid_url(self.snapshot_url.get()):
            messagebox.showerror("Source", "Choose a PC video or enter a valid YouTube URL")
            return
        if local and (not Path(local).is_file() or Path(local).suffix.lower() not in
                      (".mp4", ".mov", ".mkv", ".avi", ".webm", ".m4v", ".wmv", ".ts")):
            messagebox.showerror("Source", "Selected PC video is missing or unsupported")
            return
        try:
            assert 1 <= int(self.interval.get()) <= 3600
            assert 1 <= int(self.snap_quality.get()) <= 100
            start = timestamp(self.start_time.get())
            end = timestamp(self.end_time.get()) if self.end_time.get().strip() else None
            if end is not None and end <= start:
                raise ValueError("End time must follow start")
        except (AssertionError, ValueError):
            messagebox.showerror("Options", "Check interval, quality and optional start/end times")
            return
        self.prefs.set("yt_snap_output", self.snapshot_output.get())
        self.snap_cancel.clear()
        self.snap_pause.clear()
        self.snap_running = self.running = True
        config = {"url": self.snapshot_url.get(), "local_video": local, "output": self.snapshot_output.get(),
                  "interval": self.interval.get(), "format": self.snap_format.get(),
                  "quality": self.snap_quality.get(), "resolution": self.resolution.get(),
                  "start": self.start_time.get(), "end": self.end_time.get()}
        def work():
            try:
                count = snapshot_video(config, self.snap_cancel, self.snap_pause,
                                       lambda desc, i, n: self.events.put(("frame", desc, i, n)))
                status = "Completed: " + str(count) + " frames"
            except Exception as exc:
                status = "Failed: " + str(exc)
            self.events.put(("snapshot_done", status))
        threading.Thread(target=work, daemon=True).start()
        self.snap_status.set("Preparing local snapshots..." if local else "Preparing YouTube snapshots...")

    def pause_snapshots(self):
        if self.snap_running:
            if self.snap_pause.is_set():
                self.snap_pause.clear()
                self.snap_status.set("Resuming...")
            else:
                self.snap_pause.set()
                self.snap_status.set("Paused")

    def stop_snapshots(self):
        self.snap_cancel.set()
        self.snap_pause.clear()

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
                elif item[0] == "frame":
                    _, name, i, n = item
                    self.snap_status.set(str(i) + " / " + str(n) + " — " + name)
                elif item[0] == "snapshot_done":
                    self.snap_running = False
                    self.running = self.downloading
                    self.snap_status.set(item[1])
        except queue.Empty:
            pass
        self.after(150, self._poll)
