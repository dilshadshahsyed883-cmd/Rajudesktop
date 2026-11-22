"""Batch Video Clip Cutter UI: mixed local files and YouTube links in a durable FIFO queue."""
from __future__ import annotations

import json
import os
import queue
import threading
from concurrent.futures import ThreadPoolExecutor
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from smart_media_manager.cutter_queue import cut_source, download_source, new_job


def state_root() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "SmartMediaManager"


class BatchCutterTab(ttk.Frame):
    def __init__(self, parent, prefs):
        super().__init__(parent, padding=18)
        self.prefs = prefs
        self.queue_path = state_root() / "cutter_queue.json"
        self.jobs = self._load()
        self.events = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.work_items = None  # Thread-safe incoming queue for active runs.
        self.duration = tk.StringVar(value=prefs.get("cutter_duration", "4"))
        self.output = tk.StringVar(value=prefs.get("cutter_output", str(Path.home() / "Documents" / "ProcessedClips")))
        self.keyword = tk.StringVar()
        self.status = tk.StringVar(value="Ready — add PC videos or YouTube links")
        self.stats = tk.StringVar()
        self.percent = tk.DoubleVar(value=0)
        self.active_id = None
        self._build()
        self._refresh()
        self.after(120, self._poll)

    def _load(self):
        try:
            value = json.loads(self.queue_path.read_text(encoding="utf-8"))
            if not isinstance(value, list):
                return []
            result = []
            for item in value[-500:]:
                if not isinstance(item, dict) or not all(k in item for k in
                        ("id", "source", "kind", "keyword", "duration", "output", "status")):
                    continue
                if item["status"] in ("Downloading", "Ready to Cut", "Cutting"):
                    item["status"] = "Queued"
                result.append(item)
            return result
        except (OSError, ValueError):
            return []

    def _save(self):
        self.queue_path.parent.mkdir(parents=True, exist_ok=True)
        temp = self.queue_path.with_suffix(".tmp")
        temp.write_text(json.dumps(self.jobs[-500:], ensure_ascii=False, indent=2), encoding="utf-8")
        os.replace(temp, self.queue_path)

    def _build(self):
        ttk.Label(self, text="Batch Video Clip Cutter", style="Heading.TLabel").pack(anchor="w")
        ttk.Label(self, text="Local videos + YouTube URLs  •  Download automatically  •  Cut one-by-one  •  Resume saved queue",
                  style="Muted.TLabel").pack(anchor="w", pady=(2, 12))

        inputs = ttk.Frame(self)
        inputs.pack(fill="x")
        left = ttk.LabelFrame(inputs, text="1  •  Videos from PC", padding=12)
        left.pack(side="left", fill="both", expand=True, padx=(0, 7))
        ttk.Label(left, text="Choose multiple local videos in one selection").pack(anchor="w", pady=(2, 9))
        self.pc_button = ttk.Button(left, text="＋  Add Videos from PC", command=self.add_pc, style="Primary.TButton")
        self.pc_button.pack(anchor="w", pady=(0, 6))
        ttk.Label(left, text="Supports MP4, MOV, MKV, WEBM and more", style="Muted.TLabel").pack(anchor="w")
        right = ttk.LabelFrame(inputs, text="2  •  YouTube videos", padding=12)
        right.pack(side="left", fill="both", expand=True, padx=(7, 0))
        ttk.Label(right, text="Paste one YouTube URL per line").pack(anchor="w")
        self.links = tk.Text(right, height=3, wrap="word", font=("Segoe UI", 9),
                             relief="solid", borderwidth=1, background="#ffffff")
        self.links.pack(fill="x", pady=(5, 6))
        self.yt_button = ttk.Button(right, text="＋  Add Links to Queue", command=self.add_links)
        self.yt_button.pack(anchor="e")

        settings = ttk.LabelFrame(self, text="3  •  Settings for new queue items", padding=10)
        settings.pack(fill="x", pady=(12, 7))
        line = ttk.Frame(settings)
        line.pack(fill="x")
        ttk.Label(line, text="Keyword (optional)").pack(side="left")
        ttk.Entry(line, textvariable=self.keyword, width=27).pack(side="left", padx=(7, 14))
        ttk.Label(line, text="Clip seconds").pack(side="left")
        self.seconds = ttk.Spinbox(line, textvariable=self.duration, from_=0.1, to=3600,
                                   increment=0.5, width=8)
        self.seconds.pack(side="left", padx=(8, 12))
        for s in (2, 4, 5, 10):
            ttk.Button(line, text=f"{s}s", width=4,
                       command=lambda n=s: self.duration.set(str(n))).pack(side="left", padx=2)
        output = ttk.Frame(settings)
        output.pack(fill="x", pady=(9, 0))
        ttk.Label(output, text="Output").pack(side="left")
        ttk.Entry(output, textvariable=self.output).pack(side="left", fill="x", expand=True, padx=(9, 7))
        ttk.Button(output, text="Browse", command=self.choose_output).pack(side="left")
        ttk.Button(output, text="Open Folder", command=self.open_output).pack(side="left", padx=(7, 0))

        heading = ttk.Frame(self)
        heading.pack(fill="x", pady=(11, 5))
        ttk.Label(heading, text="4  •  Processing queue", style="Section.TLabel").pack(side="left")
        ttk.Label(heading, textvariable=self.stats, style="Muted.TLabel").pack(side="right")
        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True)
        cols = ("name", "source", "length", "progress", "status")
        self.tree = ttk.Treeview(table_frame, columns=cols, show="headings", height=9,
                                 selectmode="extended", style="Queue.Treeview")
        widths = {"name": 320, "source": 110, "length": 85, "progress": 100, "status": 215}
        labels = {"name": "Video / output keyword", "source": "Input", "length": "Clip length",
                  "progress": "Progress", "status": "Status"}
        for col in cols:
            self.tree.heading(col, text=labels[col])
            self.tree.column(col, width=widths[col], minwidth=70, stretch=col in ("name", "status"))
        scroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        controls = ttk.Frame(self)
        controls.pack(fill="x", pady=(10, 6))
        self.run_button = ttk.Button(controls, text="▶  Start Queue", command=self.start_queue,
                                     style="Primary.TButton")
        self.run_button.pack(side="left", padx=(0, 7))
        self.cancel_button = ttk.Button(controls, text="■  Cancel Current", command=self.cancel_current,
                                        state="disabled")
        self.cancel_button.pack(side="left", padx=3)
        self.retry_button = ttk.Button(controls, text="Retry Failed", command=self.retry_failed)
        self.retry_button.pack(side="left", padx=3)
        self.remove_button = ttk.Button(controls, text="Remove Completed", command=self.remove_completed)
        self.remove_button.pack(side="left", padx=3)
        self.clear_button = ttk.Button(controls, text="Remove Selected", command=self.remove_selected)
        self.clear_button.pack(side="left", padx=3)
        self.progress_bar = ttk.Progressbar(self, maximum=100, variable=self.percent)
        self.progress_bar.pack(fill="x", pady=(3, 5))
        ttk.Label(self, textvariable=self.status).pack(anchor="w")
        ttk.Label(self, text="Each video gets its own numbered-clips folder. Originals and previous results are never overwritten.",
                  style="Muted.TLabel").pack(anchor="w", pady=(5, 0))

    def _refresh(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        for job in self.jobs:
            self.tree.insert("", "end", iid=job["id"],
                             values=(job["keyword"], job["kind"], str(job["duration"]) + " s",
                                     str(round(job.get("progress", 0))) + "%", job["status"]))
        for identifier in selected:
            if self.tree.exists(identifier):
                self.tree.selection_add(identifier)
        queued = sum(j["status"] == "Queued" for j in self.jobs)
        done = sum(j["status"] == "Completed" for j in self.jobs)
        failed = sum(str(j["status"]).startswith(("Failed", "Cancelled")) for j in self.jobs)
        self.stats.set(f"{len(self.jobs)} total   •   {queued} waiting   •   {done} completed   •   {failed} failed/cancelled")

    def _remember(self):
        self.prefs.set("cutter_output", self.output.get())
        self.prefs.set("cutter_duration", self.duration.get())

    def _add(self, sources, kind):
        if not sources:
            return
        try:
            # Never truncate an active job when new sources are added.
            if len(self.jobs) + len(sources) > 500:
                raise ValueError("Queue limit is 500 items. Remove completed items before adding more.")
            self._remember()
            additions = []
            for i, source in enumerate(sources, 1):
                prefix = self.keyword.get().strip()
                if prefix and len(sources) > 1:
                    prefix = f"{prefix} {i}"
                additions.append(new_job(source, kind, self.duration.get(), self.output.get(), prefix))
            self.jobs.extend(additions)
            self._save()
            self._refresh()
            if self.running and self.work_items is not None and not self.cancel.is_set():
                for job in additions:
                    self.work_items.put(job.copy())
                self.status.set(f"Added {len(additions)} {kind.lower()} video(s) to the running queue.")
            else:
                self.status.set(f"Added {len(additions)} {kind.lower()} video(s). Press Start Queue.")
        except (OSError, ValueError) as exc:
            self.status.set(f"Could not add items: {exc}")
            messagebox.showerror("Queue inputs", str(exc))

    def add_pc(self):
        files = filedialog.askopenfilenames(title="Select videos to cut", filetypes=[
            ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wmv *.ts"),
            ("All files", "*.*")])
        self._add(files, "Local")

    def add_links(self):
        from smart_media_manager.youtube_downloader import valid_url
        links = [s.strip() for s in self.links.get("1.0", "end").splitlines() if s.strip()]
        if not links or any(not valid_url(u) for u in links):
            messagebox.showerror("YouTube URLs", "Paste valid YouTube video links, one per line.")
            return
        self._add(links, "YouTube")
        self.links.delete("1.0", "end")

    def choose_output(self):
        choice = filedialog.askdirectory(title="Choose processed clips output folder")
        if choice:
            self.output.set(choice)
            self._remember()

    def open_output(self):
        import subprocess
        import sys
        path = Path(self.output.get()).expanduser()
        if not path.is_dir():
            messagebox.showinfo("Output", "Output directory has not been created yet")
            return
        if os.name == "nt":
            os.startfile(str(path))
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])

    def _set_running(self, running):
        self.running = running
        # Keep source inputs and clip-duration presets usable during processing.
        for control in (self.run_button, self.retry_button,
                        self.remove_button, self.clear_button):
            control.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")

    def start_queue(self):
        if self.running:
            return
        pending = [j.copy() for j in self.jobs if j["status"] == "Queued"]
        if not pending:
            messagebox.showinfo("Queue", "No waiting videos. Add videos or retry failed items.")
            return
        self._remember()
        self.cancel.clear()
        self.work_items = queue.Queue()
        for job in pending:
            self.work_items.put(job)
        self._set_running(True)
        self.status.set(f"Starting queue of {len(pending)} videos...")
        self.percent.set(0)
        self.worker = threading.Thread(target=self._worker, daemon=True)
        self.worker.start()

    def _cut_downloaded(self, job, source):
        """Single cutting lane; downloaded sources are processed in arrival order."""
        identity = job["id"]
        if self.cancel.is_set():
            # This job never started cutting; keep it retryable without an extra attempt.
            self.events.put(("state", identity, "Queued"))
            return False
        self.events.put(("state", identity, "Cutting"))
        def notify(stage, pct, info):
            self.events.put(("progress", identity, stage, pct, info))
        try:
            count, folder = cut_source(job, source, self.cancel, notify)
            self.events.put(("state", identity, "Completed", str(folder)))
            return True
        except Exception as exc:
            status = "Cancelled" if self.cancel.is_set() else "Failed: " + str(exc)[:140]
            self.events.put(("state", identity, status))
            return False

    def _worker(self):
        """Download sequentially, overlapping downloads with one FFmpeg cutter.

        Jobs appended while a cut is running enter the same live incoming queue.
        The final finished event comes only after all submitted cuts finish.
        """
        submitted = []
        started = 0
        try:
            with ThreadPoolExecutor(max_workers=1, thread_name_prefix="smart-media-cut") as cuts:
                while not self.cancel.is_set():
                    try:
                        job = self.work_items.get(timeout=0.12)
                    except queue.Empty:
                        if all(future.done() for future in submitted):
                            break
                        continue
                    started += 1
                    identity = job["id"]
                    if job["kind"] == "YouTube":
                        self.events.put(("state", identity, "Downloading"))
                        def notify(stage, pct, info, job_id=identity):
                            self.events.put(("progress", job_id, stage, pct, info))
                        try:
                            source = download_source(
                                job, state_root() / "cutter_sources", self.cancel, notify)
                        except Exception as exc:
                            status = "Cancelled" if self.cancel.is_set() else "Failed: " + str(exc)[:140]
                            self.events.put(("state", identity, status))
                            continue
                    else:
                        source = Path(job["source"])
                    if self.cancel.is_set():
                        self.events.put(("state", identity, "Queued"))
                        break
                    self.events.put(("state", identity, "Ready to Cut"))
                    submitted.append(cuts.submit(self._cut_downloaded, job, source))
        except Exception as exc:
            self.events.put(("worker_error", str(exc)[:200]))
        completed = 0
        for future in submitted:
            try:
                completed += bool(future.result())
            except Exception as exc:
                self.events.put(("worker_error", str(exc)[:200]))
        self.events.put(("finished", completed, started, self.cancel.is_set()))

    def cancel_current(self):
        if self.running:
            self.cancel.set()
            self.status.set("Cancelling current operation — completed clips are retained")

    def retry_failed(self):
        if self.running:
            return
        changed = False
        for job in self.jobs:
            if str(job["status"]).startswith(("Failed", "Cancelled")):
                job["status"] = "Queued"
                job["progress"] = 0
                job["attempt"] = int(job.get("attempt", 0)) + 1
                changed = True
        if changed:
            self._save()
            self._refresh()
            self.status.set("Failed/cancelled videos requeued. Press Start Queue.")

    def remove_completed(self):
        if self.running:
            return
        self.jobs = [j for j in self.jobs if j["status"] != "Completed"]
        self._save()
        self._refresh()

    def remove_selected(self):
        if self.running:
            return
        selected = set(self.tree.selection())
        self.jobs = [j for j in self.jobs if j["id"] not in selected]
        self._save()
        self._refresh()

    def _poll(self):
        try:
            for _ in range(150):
                item = self.events.get_nowait()
                kind = item[0]
                if kind == "state":
                    job = next((j for j in self.jobs if j["id"] == item[1]), None)
                    if job:
                        job["status"] = item[2]
                        if item[2] == "Completed":
                            job["progress"] = 100
                            job["last_output"] = item[3]
                        self._save()
                        self._refresh()
                elif kind == "progress":
                    _, identifier, stage, percent, detail = item
                    job = next((j for j in self.jobs if j["id"] == identifier), None)
                    if job:
                        job["progress"] = float(percent)
                        job["status"] = stage
                        self.active_id = identifier
                        self.percent.set(percent)
                        self.status.set(job["keyword"] + " — " + detail)
                        if self.tree.exists(identifier):
                            self.tree.item(identifier, values=(
                                job["keyword"], job["kind"], str(job["duration"]) + " s",
                                str(round(percent)) + "%", stage))
                elif kind == "worker_error":
                    self.status.set("Worker error: " + item[1])
                elif kind == "finished":
                    self._set_running(False)
                    self.work_items = None
                    self._save()
                    self._refresh()
                    if not item[3] and any(job["status"] == "Queued" for job in self.jobs):
                        # An add may race with the worker's idle shutdown: do not lose it.
                        self.start_queue()
                    else:
                        self.status.set(f'Queue ended: {item[1]} completed in this run. ' +
                                        ("Cancelled by user." if item[3] else "Check individual statuses."))
        except queue.Empty:
            pass
        self.after(120, self._poll)
