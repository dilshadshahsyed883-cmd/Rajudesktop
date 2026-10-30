"""Standalone GUI based on the original Smart Media Manager YouTube tab."""
from __future__ import annotations
import json
import os
import threading
import uuid
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox
from smart_media_manager.youtube_downloader import YoutubeTab
from song_audio_downloader.core import canonical_url, download_video

ROOT = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "SongAudioDownloader"


class Preferences:
    def __init__(self):
        self.path = ROOT / "settings.json"
        try:
            obj = json.loads(self.path.read_text(encoding="utf-8"))
            self.values = obj if isinstance(obj, dict) else {}
        except (ValueError, OSError):
            self.values = {}

    def get(self, key, default=""):
        if key == "yt_output" and key not in self.values:
            return str(Path.home() / "Documents" / "Song Audio Downloads")
        return self.values.get(key, default)

    def set(self, key, value):
        self.values[key] = value
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.values, indent=2), encoding="utf-8")
        os.replace(temp, self.path)


class SongDownloaderTab(YoutubeTab):
    def __init__(self, parent, prefs):
        self.thumb_enabled = tk.BooleanVar(master=parent, value=prefs.get("download_thumbnail", "true") == "true")
        super().__init__(parent, prefs)

    def _read_queue(self):
        # Override the legacy app queue before any jobs are loaded.
        self.queue_file = ROOT / "youtube_queue.json"
        return super()._read_queue()

    def _build(self):
        super()._build()
        for widget in self.winfo_children():
            if isinstance(widget, ttk.Label) and widget.cget("text") == "YouTube Video Downloader":
                widget.configure(text="Song Audio Downloader")
                break
        tabs = next(w for w in self.winfo_children() if isinstance(w, ttk.Notebook))
        dl = self.nametowidget(tabs.tabs()[0])
        actions = next(w for w in dl.winfo_children() if isinstance(w, ttk.Frame) and
                       any(isinstance(child, ttk.Button) and child.cget("text") == "Add to Queue & Start"
                           for child in w.winfo_children()))
        ttk.Checkbutton(dl, text="Download matching thumbnail (VideoID.jpg)",
                        variable=self.thumb_enabled,
                        command=lambda: self.prefs.set("download_thumbnail",
                                                       str(self.thumb_enabled.get()).lower())).pack(
                            before=actions, anchor="w", pady=(0, 7))
        ttk.Label(dl, text="Same YouTube Video ID is used for both audio and JPG.",
                  style="Muted.TLabel").pack(before=actions, anchor="w", pady=(0, 6))

    def add(self):
        raw = [x.strip() for x in self.links.get("1.0", "end").splitlines() if x.strip()]
        try:
            links = [canonical_url(url) for url in raw]
        except ValueError as exc:
            messagebox.showerror("Invalid link", str(exc))
            return
        if not links:
            messagebox.showerror("Links", "Enter one or more YouTube video URLs")
            return
        for key, var in (("yt_output", self.output), ("yt_mode", self.mode),
                         ("yt_quality", self.quality), ("yt_video_format", self.video_format),
                         ("yt_audio_format", self.audio_format)):
            self.prefs.set(key, var.get())
        self.prefs.set("download_thumbnail", str(self.thumb_enabled.get()).lower())
        seen = {(x["url"], x["mode"], x.get("audio_format"), x.get("video_format"))
                for x in self.jobs if x.get("status") in ("Queued", "Downloading", "Completed")}
        new = 0
        for link in links:
            identity = (link, self.mode.get(), self.audio_format.get(), self.video_format.get())
            if identity in seen:
                continue
            seen.add(identity)
            self.jobs.append({"id": uuid.uuid4().hex, "url": link, "mode": self.mode.get(),
                              "quality": self.quality.get(), "video_format": self.video_format.get(),
                              "audio_format": self.audio_format.get(), "output": self.output.get(),
                              "download_thumbnail": self.thumb_enabled.get(),
                              "status": "Queued", "progress": 0})
            new += 1
        self._save()
        self._refresh()
        self.links.delete("1.0", "end")
        if not new:
            self.status.set("Duplicate(s) skipped; use Retry Selected if needed")
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
        jid = job["id"]

        def worker():
            try:
                download_video(job.copy(), self.cancel,
                               lambda pct: self.events.put(("progress", jid, pct)))
                status = "Completed"
            except Exception as exc:
                status = "Cancelled" if self.cancel.is_set() else "Failed: " + str(exc)
            self.events.put(("done", jid, status))
        threading.Thread(target=worker, daemon=True).start()


class SongAudioDownloader(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Song Audio Downloader")
        self.geometry("1050x780")
        self.minsize(860, 650)
        self.configure(bg="#f3f6fb")
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background="#f3f6fb")
        style.configure("TLabel", background="#f3f6fb", foreground="#1d2b41", font=("Segoe UI", 10))
        style.configure("Heading.TLabel", foreground="#14243a", font=("Segoe UI", 17, "bold"))
        style.configure("Muted.TLabel", foreground="#68778d", font=("Segoe UI", 9))
        style.configure("TButton", padding=7)
        style.configure("Horizontal.TProgressbar", background="#2869e8", troughcolor="#dbe3ef")
        banner = tk.Frame(self, bg="#14243a", height=88)
        banner.pack(fill="x")
        banner.pack_propagate(False)
        tk.Label(banner, text="SONG AUDIO DOWNLOADER", fg="white", bg="#14243a",
                 font=("Segoe UI", 19, "bold")).pack(anchor="w", padx=28, pady=(12, 0))
        tk.Label(banner, text="Audio • Matching JPG • Video • Snapshots • Queue", fg="#b8cbea",
                 bg="#14243a", font=("Segoe UI", 10)).pack(anchor="w", padx=30, pady=(3, 0))
        self.tab = SongDownloaderTab(self, Preferences())
        self.tab.pack(fill="both", expand=True, padx=14, pady=12)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def close(self):
        if self.tab.running:
            messagebox.showwarning("Download active", "Cancel or finish current jobs first")
        else:
            self.destroy()


def main():
    SongAudioDownloader().mainloop()
