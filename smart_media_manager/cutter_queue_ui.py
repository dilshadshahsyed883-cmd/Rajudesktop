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

from smart_media_manager.clip_output import default_output_folder, validate_output
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
        self.adding = False
        self.work_items = None  # Thread-safe incoming queue for active runs.
        self.duration = tk.StringVar(value=prefs.get("cutter_duration", "4"))
        self.quality = tk.StringVar(value=prefs.get("cutter_quality", "720p"))
        if self.quality.get() not in ("720p", "1080p"):
            self.quality.set("720p")
        self.output = tk.StringVar(value=prefs.get("cutter_output", str(default_output_folder())))
        self.keyword = tk.StringVar()
        self.status = tk.StringVar(value="Ready — add PC videos or YouTube links")
        self.stats = tk.StringVar()
        self.percent = tk.DoubleVar(value=0)
        self.active_id = None
        self._build()
        self._refresh()
        self.after(120, self._poll)
        self.after_idle(self.start_queue)

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
        """Keep the queue/actions visible; scroll and reflow only the inputs."""
        self.columnconfigure(0, weight=1)
        self.rowconfigure(2, weight=1)

        # The upper controls have their own scrollable viewport. When screen
        # height shrinks, the queue and bottom action bar never disappear.
        self._upper_canvas = tk.Canvas(
            self, background="#f3f6fb", borderwidth=0, highlightthickness=0,
            height=350,
        )
        self._upper_canvas.grid(row=0, column=0, sticky="ew")
        upper_scrollbar = ttk.Scrollbar(
            self, orient="vertical", command=self._upper_canvas.yview,
        )
        upper_scrollbar.grid(row=0, column=1, sticky="ns")
        self._upper_canvas.configure(yscrollcommand=upper_scrollbar.set)
        self._upper_body = ttk.Frame(self._upper_canvas)
        self._upper_body.columnconfigure(0, weight=1)
        self._upper_window = self._upper_canvas.create_window(
            (0, 0), anchor="nw", window=self._upper_body,
        )
        self._upper_body.bind("<Configure>", self._update_scroll_region)
        self._upper_canvas.bind("<Configure>", self._size_upper_body)

        ttk.Label(
            self._upper_body, text="Batch Video Clip Cutter", style="Heading.TLabel",
        ).grid(row=0, column=0, sticky="w")
        self._subtitle = ttk.Label(
            self._upper_body,
            text="Local videos + YouTube URLs  •  Download automatically  •  Cut one-by-one  •  Resume saved queue",
            style="Muted.TLabel",
        )
        self._subtitle.grid(row=1, column=0, sticky="w", pady=(2, 12))

        self._inputs = ttk.Frame(self._upper_body)
        self._inputs.grid(row=2, column=0, sticky="ew")
        self._input_left = ttk.LabelFrame(
            self._inputs, text="1  •  Videos from PC", padding=12,
        )
        ttk.Label(
            self._input_left, text="Choose multiple local videos in one selection",
        ).pack(anchor="w", pady=(2, 9))
        self.pc_button = ttk.Button(
            self._input_left, text="＋  Add Videos from PC",
            command=self.add_pc, style="Primary.TButton",
        )
        self.pc_button.pack(anchor="w", pady=(0, 6))
        ttk.Label(
            self._input_left, text="Supports MP4, MOV, MKV, WEBM and more",
            style="Muted.TLabel",
        ).pack(anchor="w")

        self._input_right = ttk.LabelFrame(
            self._inputs, text="2  •  YouTube videos", padding=12,
        )
        ttk.Label(
            self._input_right, text="Paste one YouTube URL per line",
        ).pack(anchor="w")
        self.links = tk.Text(
            self._input_right, height=3, wrap="word", font=("Segoe UI", 9),
            relief="solid", borderwidth=1, background="#ffffff",
        )
        self.links.pack(fill="x", pady=(5, 6))
        self.yt_button = ttk.Button(
            self._input_right, text="＋  Add Links to Queue", command=self.add_links,
        )
        self.yt_button.pack(anchor="e")

        settings = ttk.LabelFrame(
            self._upper_body, text="3  •  Settings for new queue items", padding=10,
        )
        settings.grid(row=3, column=0, sticky="ew", pady=(12, 7))
        settings.columnconfigure(0, weight=1)
        self._settings_controls = ttk.Frame(settings)
        self._settings_controls.grid(row=0, column=0, sticky="ew")

        keyword_group = ttk.Frame(self._settings_controls)
        ttk.Label(keyword_group, text="Keyword (optional)").pack(anchor="w")
        ttk.Entry(
            keyword_group, textvariable=self.keyword, width=22,
        ).pack(fill="x", pady=(5, 0))

        duration_group = ttk.Frame(self._settings_controls)
        ttk.Label(duration_group, text="Clip seconds").pack(anchor="w")
        self.seconds = ttk.Spinbox(
            duration_group, textvariable=self.duration, from_=0.1,
            to=3600, increment=0.5, width=8,
        )
        self.seconds.pack(anchor="w", pady=(5, 0))

        presets_group = ttk.Frame(self._settings_controls)
        ttk.Label(presets_group, text="Quick duration").pack(anchor="w")
        preset_buttons = ttk.Frame(presets_group)
        preset_buttons.pack(anchor="w", pady=(5, 0))
        for seconds in (2, 4, 5, 10):
            ttk.Button(
                preset_buttons, text=f"{seconds}s", width=4,
                command=lambda value=seconds: self.duration.set(str(value)),
            ).pack(side="left", padx=(0, 4))

        quality_group = ttk.Frame(self._settings_controls)
        ttk.Label(quality_group, text="YouTube quality").pack(anchor="w")
        self.quality_select = ttk.Combobox(
            quality_group, textvariable=self.quality,
            values=("720p", "1080p"), width=9, state="readonly",
        )
        self.quality_select.pack(anchor="w", pady=(5, 0))
        self._setting_panels = (
            keyword_group, duration_group, presets_group, quality_group,
        )

        self._fast_copy_note = ttk.Label(
            settings,
            text="Fast Copy: no re-encoding. Cuts follow keyframes; PC files keep original resolution.",
            style="Muted.TLabel",
        )
        self._fast_copy_note.grid(
            row=1, column=0, sticky="w", pady=(9, 0),
        )

        self._output_layout = ttk.Frame(settings)
        self._output_layout.grid(
            row=2, column=0, sticky="ew", pady=(9, 0),
        )
        self._output_layout.columnconfigure(0, weight=1)
        self._output_field = ttk.Frame(self._output_layout)
        self._output_field.columnconfigure(1, weight=1)
        ttk.Label(self._output_field, text="Output Folder").grid(
            row=0, column=0, sticky="w", padx=(0, 9),
        )
        ttk.Entry(
            self._output_field, textvariable=self.output,
        ).grid(row=0, column=1, sticky="ew")
        self._output_buttons = ttk.Frame(self._output_layout)
        ttk.Button(
            self._output_buttons, text="Browse", command=self.choose_output,
        ).pack(side="left", padx=(0, 6))
        ttk.Button(
            self._output_buttons, text="Open Folder", command=self.open_output,
        ).pack(side="left")

        queue_heading = ttk.Frame(self)
        queue_heading.grid(
            row=1, column=0, columnspan=2, sticky="ew", pady=(8, 4),
        )
        queue_heading.columnconfigure(0, weight=1)
        self._queue_title = ttk.Label(
            queue_heading, text="4  •  Processing queue", style="Section.TLabel",
        )
        self._queue_title.grid(row=0, column=0, sticky="w")
        self._queue_stats = ttk.Label(
            queue_heading, textvariable=self.stats, style="Muted.TLabel",
        )
        self._queue_stats.grid(row=0, column=1, sticky="e")
        self._queue_heading = queue_heading

        table_frame = ttk.Frame(self)
        table_frame.grid(row=2, column=0, columnspan=2, sticky="nsew")
        table_frame.rowconfigure(0, weight=1)
        table_frame.columnconfigure(0, weight=1)
        cols = ("name", "source", "length", "quality", "progress", "status")
        self.tree = ttk.Treeview(
            table_frame, columns=cols, show="headings", height=3,
            selectmode="extended", style="Queue.Treeview",
        )
        widths = {
            "name": 320, "source": 110, "length": 85, "quality": 90,
            "progress": 100, "status": 215,
        }
        labels = {
            "name": "Video / output keyword", "source": "Input",
            "length": "Clip length", "quality": "Quality",
            "progress": "Progress", "status": "Status",
        }
        for column in cols:
            self.tree.heading(column, text=labels[column])
            self.tree.column(
                column, width=widths[column], minwidth=70,
                stretch=column in ("name", "status"),
            )
        vertical = ttk.Scrollbar(
            table_frame, orient="vertical", command=self.tree.yview,
        )
        horizontal = ttk.Scrollbar(
            table_frame, orient="horizontal", command=self.tree.xview,
        )
        self.tree.configure(
            yscrollcommand=vertical.set, xscrollcommand=horizontal.set,
        )
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal.grid(row=1, column=0, sticky="ew")

        self._action_bar = ttk.Frame(self)
        self._action_bar.grid(
            row=3, column=0, columnspan=2, sticky="ew", pady=(9, 5),
        )
        self.cancel_button = ttk.Button(
            self._action_bar, text="■  Cancel Current",
            command=self.cancel_current, state="disabled",
        )
        self.retry_button = ttk.Button(
            self._action_bar, text="Retry Failed", command=self.retry_failed,
        )
        self.remove_button = ttk.Button(
            self._action_bar, text="Remove Completed",
            command=self.remove_completed,
        )
        self.clear_button = ttk.Button(
            self._action_bar, text="Remove Selected",
            command=self.remove_selected,
        )
        self._actions = (
            self.cancel_button, self.retry_button,
            self.remove_button, self.clear_button,
        )

        self.progress_bar = ttk.Progressbar(
            self, maximum=100, variable=self.percent,
        )
        self.progress_bar.grid(
            row=4, column=0, columnspan=2, sticky="ew", pady=(3, 5),
        )
        self._status_label = ttk.Label(
            self, textvariable=self.status,
        )
        self._status_label.grid(
            row=5, column=0, columnspan=2, sticky="w",
        )
        self._safety_note = ttk.Label(
            self,
            text="New clips go directly into the selected folder. Existing files are preserved. Adding videos starts the queue.",
            style="Muted.TLabel",
        )
        self._safety_note.grid(
            row=6, column=0, columnspan=2, sticky="w", pady=(5, 0),
        )

        self._layout_mode = None
        self._top_height = None
        self.bind("<Configure>", self._on_resize, add="+")
        self._bind_scroll_wheel(self._upper_body)
        self._upper_canvas.bind("<MouseWheel>", self._scroll_upper, add="+")
        self._upper_canvas.bind("<Button-4>", self._scroll_upper, add="+")
        self._upper_canvas.bind("<Button-5>", self._scroll_upper, add="+")
        self.after_idle(self._on_resize)

    def _update_scroll_region(self, _event=None):
        bounds = self._upper_canvas.bbox("all")
        if bounds:
            self._upper_canvas.configure(scrollregion=bounds)

    def _size_upper_body(self, event):
        self._upper_canvas.itemconfigure(self._upper_window, width=event.width)
        self._update_scroll_region()

    def _bind_scroll_wheel(self, widget):
        """Scroll top controls without stealing wheel input from the queue."""
        if not isinstance(widget, tk.Text):
            for sequence in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
                widget.bind(sequence, self._scroll_upper, add="+")
        for child in widget.winfo_children():
            self._bind_scroll_wheel(child)

    def _scroll_upper(self, event):
        if getattr(event, "num", None) == 4:
            steps = -1
        elif getattr(event, "num", None) == 5:
            steps = 1
        else:
            delta = getattr(event, "delta", 0)
            steps = -(1 if delta > 0 else -1) if delta else 0
        if steps:
            self._upper_canvas.yview_scroll(steps, "units")
            return "break"

    def _on_resize(self, event=None):
        width = self.winfo_width()
        height = self.winfo_height()
        if width < 200 or height < 200:
            return
        mode = ("wide" if width >= 1130 else
                "medium" if width >= 800 else "narrow" if width >= 550 else "tiny")
        if mode != self._layout_mode:
            self._layout_mode = mode
            self._reflow_controls(mode)

        wrap = max(230, width - 70)
        self._subtitle.configure(wraplength=wrap)
        self._fast_copy_note.configure(wraplength=wrap - 20)
        self._status_label.configure(wraplength=wrap)
        self._safety_note.configure(wraplength=wrap)

        # Keep a useful queue viewport and pinned actions, even on 600px-high
        # displays. Upper inputs scroll when they cannot all fit at once.
        reserved = 245 if mode in ("narrow", "tiny") else 210
        maximum = max(125, int((height - reserved) * 0.60))
        desired = min(self._upper_body.winfo_reqheight(), maximum)
        if desired != self._top_height:
            self._top_height = desired
            self._upper_canvas.configure(height=desired)
        self._update_scroll_region()

    def _reflow_controls(self, mode):
        stacked_inputs = mode in ("narrow", "tiny")
        for frame in (self._input_left, self._input_right):
            frame.grid_forget()
        for col in (0, 1):
            self._inputs.columnconfigure(col, weight=0)
        if stacked_inputs:
            self._inputs.columnconfigure(0, weight=1)
            self._input_left.grid(row=0, column=0, sticky="ew", pady=(0, 7))
            self._input_right.grid(row=1, column=0, sticky="ew")
        else:
            self._inputs.columnconfigure(0, weight=1, uniform="input")
            self._inputs.columnconfigure(1, weight=1, uniform="input")
            self._input_left.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
            self._input_right.grid(row=0, column=1, sticky="nsew", padx=(7, 0))

        for frame in self._setting_panels:
            frame.grid_forget()
        columns = 4 if mode == "wide" else 2 if mode == "medium" else 1
        for col in range(4):
            self._settings_controls.columnconfigure(col, weight=int(col < columns))
        for index, frame in enumerate(self._setting_panels):
            frame.grid(
                row=index // columns, column=index % columns, sticky="ew",
                padx=(0, 10), pady=(0, 8),
            )

        self._output_field.grid_forget()
        self._output_buttons.grid_forget()
        if mode in ("wide", "medium"):
            self._output_field.grid(row=0, column=0, sticky="ew", padx=(0, 8))
            self._output_buttons.grid(row=0, column=1, sticky="e")
        else:
            self._output_field.grid(row=0, column=0, sticky="ew")
            self._output_buttons.grid(row=1, column=0, sticky="e", pady=(7, 0))

        self._queue_stats.grid_forget()
        if mode in ("narrow", "tiny"):
            self._queue_stats.grid(row=1, column=0, sticky="w", pady=(3, 0))
        else:
            self._queue_stats.grid(row=0, column=1, sticky="e")

        for button in self._actions:
            button.grid_forget()
        columns = 4 if mode == "wide" else 3 if mode == "medium" else 2 if mode == "narrow" else 1
        for col in range(4):
            self._action_bar.columnconfigure(
                col, weight=int(col < columns and columns < 4),
            )
        for index, button in enumerate(self._actions):
            button.grid(
                row=index // columns, column=index % columns,
                sticky="ew" if columns < 4 else "w",
                padx=(0, 7), pady=(0, 5),
            )

    def _refresh(self):
        selected = set(self.tree.selection())
        self.tree.delete(*self.tree.get_children())
        for job in self.jobs:
            self.tree.insert("", "end", iid=job["id"],
                             values=(job["keyword"], job["kind"], str(job["duration"]) + " s",
                                     job.get("quality") or "Original",
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
        self.prefs.set("cutter_quality", self.quality.get())

    def _add(self, sources, kind):
        if not sources or self.adding:
            return
        if len(self.jobs) + len(sources) > 500:
            messagebox.showerror("Queue inputs", "Queue limit is 500 items. Remove completed items first.")
            return
        settings = (self.duration.get(), self.output.get(), self.keyword.get().strip(), self.quality.get())
        self.adding = True
        self.pc_button.configure(state="disabled")
        self.yt_button.configure(state="disabled")
        self.links.configure(state="disabled")
        self.progress_bar.configure(mode="indeterminate")
        self.progress_bar.start(12)
        self.status.set("Checking inputs and output folder…")
        def validate():
            try:
                duration, output, keyword, quality = settings
                if not output.strip():
                    raise ValueError("Choose an output folder")
                folder = validate_output(Path(output))
                additions = []
                seen = set()
                for source in sources:
                    job = new_job(source, kind, duration, str(folder), keyword, quality=quality)
                    if kind == "Local":
                        job["source"] = str(Path(source).resolve())
                    key = self._source_key(job)
                    if key not in seen:
                        additions.append(job)
                        seen.add(key)
                self.events.put(("add_ready", additions, kind, str(folder), output))
            except Exception as exc:
                self.events.put(("add_error", str(exc)))
        threading.Thread(target=validate, daemon=True, name="smart-media-enqueue").start()

    @staticmethod
    def _source_key(job):
        if job["kind"] == "Local":
            return ("Local", os.path.normpath(job["source"]).casefold())
        from urllib.parse import urlparse, parse_qs
        url = urlparse(job["source"])
        identifier = parse_qs(url.query).get("v", [""])[0] or url.path.rstrip("/").split("/")[-1]
        return ("YouTube", identifier)

    def _finish_add(self, additions, kind, folder, selected=None):
        active = {self._source_key(j) for j in self.jobs
                  if j["status"] in ("Queued", "Downloading", "Ready to Cut", "Cutting")}
        additions = [j for j in additions if self._source_key(j) not in active]
        previous = list(self.jobs)
        try:
            if selected is None or self.output.get() == selected:
                self.output.set(folder)
            self._remember()
            self.jobs.extend(additions)
            self._save()  # Durable before any worker receives new jobs.
        except OSError as exc:
            self.jobs = previous
            self.status.set(f"Could not save queue: {exc}")
            messagebox.showerror("Queue inputs", str(exc))
            return
        if kind == "YouTube":
            self.links.delete("1.0", "end")
        self._refresh()
        if self.running and self.work_items is not None and not self.cancel.is_set():
            for job in additions:
                self.work_items.put(job.copy())
        elif not self.running:
            self.start_queue()
        if not additions:
            self.status.set("These videos are already waiting or processing.")

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
        for control in (self.retry_button,
                        self.remove_button, self.clear_button):
            control.configure(state="disabled" if running else "normal")
        self.cancel_button.configure(state="normal" if running else "disabled")

    def start_queue(self):
        if self.running:
            return
        pending = [j.copy() for j in self.jobs if j["status"] == "Queued"]
        if not pending:
            return
        try:
            self._remember()
        except OSError as exc:
            self.status.set(f"Could not save queue settings: {exc}")
            return
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
            self.start_queue()

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
                if kind in ("add_ready", "add_error"):
                    self.progress_bar.stop()
                    self.progress_bar.configure(mode="determinate")
                    self.links.configure(state="normal")
                    self.adding = False
                    self.pc_button.configure(state="normal")
                    self.yt_button.configure(state="normal")
                    if kind == "add_ready":
                        self._finish_add(*item[1:])
                    else:
                        self.status.set("Could not add items: " + item[1])
                        messagebox.showerror("Queue inputs", item[1])
                elif kind == "state":
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
                                job.get("quality") or "Original",
                                str(round(percent)) + "%", stage))
                elif kind == "worker_error":
                    self.status.set("Worker error: " + item[1])
                elif kind == "finished":
                    self._set_running(False)
                    self.work_items = None
                    self._save()
                    self._refresh()
                    if any(job["status"] == "Queued" for job in self.jobs):
                        # An add may race with the worker's idle shutdown: do not lose it.
                        self.start_queue()
                    else:
                        self.status.set(f'Queue ended: {item[1]} completed in this run. ' +
                                        ("Cancelled by user." if item[3] else "Check individual statuses."))
        except queue.Empty:
            pass
        except OSError as exc:
            self.status.set(f"Could not save queue state: {exc}")
        self.after(120, self._poll)
