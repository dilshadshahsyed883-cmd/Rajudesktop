"""Tkinter Windows interface; processing occurs exclusively in a worker thread."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import (Cancelled, CutterError, default_output_folder, prepare_job,
                   process_job, read_settings, write_settings, parse_duration)

NAVY = "#14243A"
BLUE = "#2869E8"
WHITE = "#FFFFFF"
INK = "#1D2B41"
GREY = "#68778D"
PALE = "#F3F6FB"
BORDER = "#DBE3EF"


class VideoClipCutter(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Video Clip Cutter")
        self.geometry("1100x740")
        self.minsize(890, 620)
        self.configure(bg=PALE)
        self.events: queue.Queue = queue.Queue()
        self.cancel = threading.Event()
        self.processing = False
        self.worker: threading.Thread | None = None
        saved = read_settings()
        self.video = tk.StringVar()
        self.name_input = tk.StringVar()
        self.duration_input = tk.StringVar(value=str(saved.get("duration", "4")))
        self.output = tk.StringVar(value=str(saved.get("output_folder") or default_output_folder()))
        self.message = tk.StringVar(value="Ready — select a video to begin")
        self.file_info = tk.StringVar(value="No video selected")
        self.progress_info = tk.StringVar(value="0 / 0 clips")
        self.percent_info = tk.StringVar(value="0%")
        self.progress = tk.DoubleVar(value=0.0)
        self.count_info = tk.StringVar(value="Estimated clips: —")
        self._build()
        self.video.trace_add("write", self._estimate)
        self.duration_input.trace_add("write", self._estimate)
        self.after(100, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _label(self, parent, text, *, size=10, color=INK, weight="normal", **kwargs):
        return tk.Label(parent, text=text, bg=kwargs.pop("bg", WHITE), fg=color,
                        font=("Segoe UI", size, weight), **kwargs)

    def _build(self):
        sidebar = tk.Frame(self, bg=NAVY, width=218)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        tk.Label(sidebar, text="◧  RAJU DESKTOP", font=("Segoe UI", 14, "bold"),
                 fg=WHITE, bg=NAVY).pack(anchor="w", padx=22, pady=(36, 6))
        tk.Label(sidebar, text="Independent video tools", font=("Segoe UI", 9),
                 fg="#A1B3D0", bg=NAVY).pack(anchor="w", padx=22, pady=(0, 45))
        tk.Label(sidebar, text="  ▣  Clip Cutter", bg="#244363", fg=WHITE,
                 font=("Segoe UI", 11, "bold"), anchor="w", padx=14,
                 height=3).pack(fill="x", padx=12)
        tk.Label(sidebar, text="LOCAL • OFFLINE", bg=NAVY, fg="#9CB4CF",
                 font=("Segoe UI", 9, "bold")).pack(side="bottom", anchor="w", padx=24, pady=28)

        surface = tk.Frame(self, bg=PALE)
        surface.pack(side="left", fill="both", expand=True, padx=34, pady=27)
        self._label(surface, "Video Clip Cutter", size=22, weight="bold", bg=PALE).pack(anchor="w")
        self._label(surface, "Split videos into numbered clips while preserving resolution and audio.",
                    color=GREY, size=10, bg=PALE).pack(anchor="w", pady=(5, 18))

        card = tk.Frame(surface, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x")
        inner = tk.Frame(card, bg=WHITE)
        inner.pack(fill="x", padx=24, pady=21)

        self._label(inner, "1  Select Video", size=12, weight="bold").pack(anchor="w")
        video_row = tk.Frame(inner, bg=WHITE)
        video_row.pack(fill="x", pady=(9, 6))
        self._entry(video_row, self.video).pack(side="left", fill="x", expand=True, ipady=8)
        self.browse_btn = self._button(video_row, "Browse Video", self._browse)
        self.browse_btn.pack(side="left", padx=(10, 0))
        self._label(inner, "MP4 • MOV • MKV • AVI • WEBM • M4V • WMV • TS", color=GREY, size=9).pack(anchor="w")

        tk.Frame(inner, height=1, bg=BORDER).pack(fill="x", pady=18)
        row = tk.Frame(inner, bg=WHITE)
        row.pack(fill="x")
        name_col = tk.Frame(row, bg=WHITE)
        name_col.pack(side="left", fill="x", expand=True, padx=(0, 12))
        self._label(name_col, "2  Output Filename *", size=11, weight="bold").pack(anchor="w", pady=(0, 7))
        self._entry(name_col, self.name_input).pack(fill="x", ipady=8)
        self._label(name_col, "Example: Nature → Nature 1.mp4, Nature 2.mp4...",
                    color=GREY, size=9).pack(anchor="w", pady=(6, 0))
        duration_col = tk.Frame(row, bg=WHITE)
        duration_col.pack(side="left", anchor="n")
        self._label(duration_col, "3  Clip Duration", size=11, weight="bold").pack(anchor="w", pady=(0, 7))
        chooser = tk.Frame(duration_col, bg=WHITE)
        chooser.pack(anchor="w")
        self.duration_spin = tk.Spinbox(chooser, textvariable=self.duration_input, from_=0.1, to=3600,
                                       increment=0.5, width=8, font=("Segoe UI", 11),
                                       relief="solid", bd=1, highlightthickness=0)
        self.duration_spin.pack(side="left", ipady=6)
        self._label(chooser, "sec", color=GREY).pack(side="left", padx=(8, 0))
        preset_row = tk.Frame(duration_col, bg=WHITE)
        preset_row.pack(anchor="w", pady=(8, 0))
        for n in (2, 4, 5, 10):
            tk.Button(preset_row, text=f"{n}s", command=lambda x=n: self.duration_input.set(str(x)),
                      bg=PALE, fg=INK, relief="flat", bd=0, padx=8,
                      font=("Segoe UI", 9), cursor="hand2").pack(side="left", padx=(0, 5))
        tk.Frame(inner, height=1, bg=BORDER).pack(fill="x", pady=18)
        self._label(inner, "4  Output Folder", size=11, weight="bold").pack(anchor="w")
        folder_row = tk.Frame(inner, bg=WHITE)
        folder_row.pack(fill="x", pady=(9, 7))
        self._entry(folder_row, self.output).pack(side="left", fill="x", expand=True, ipady=8)
        self.folder_btn = self._button(folder_row, "Change Folder", self._change_folder, primary=False)
        self.folder_btn.pack(side="left", padx=(10, 0))
        self._label(inner, "Default: Documents\\ProcessedClips • Remembered until changed", color=GREY, size=9).pack(anchor="w")

        action = tk.Frame(surface, bg=PALE)
        action.pack(fill="x", pady=(19, 10))
        self.start_btn = self._button(action, "▶   Start Processing", self._start)
        self.start_btn.pack(side="left")
        self.cancel_btn = self._button(action, "■   Cancel", self._cancel, primary=False)
        self.cancel_btn.config(state="disabled")
        self.cancel_btn.pack(side="left", padx=(9, 0))
        self.open_btn = self._button(action, "▤   Open Output Folder", self._open_folder, primary=False)
        self.open_btn.pack(side="right")

        status = tk.Frame(surface, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        status.pack(fill="x", pady=(5, 0))
        status_inner = tk.Frame(status, bg=WHITE)
        status_inner.pack(fill="x", padx=24, pady=17)
        status_head = tk.Frame(status_inner, bg=WHITE)
        status_head.pack(fill="x")
        self._label(status_head, "Processing Status", size=11, weight="bold").pack(side="left")
        self._label(status_head, "0%", color=BLUE, weight="bold", textvariable=self.percent_info).pack(side="right")
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("VCC.Horizontal.TProgressbar", troughcolor=PALE, background=BLUE,
                        thickness=10, borderwidth=0)
        ttk.Progressbar(status_inner, variable=self.progress, maximum=100,
                        style="VCC.Horizontal.TProgressbar").pack(fill="x", pady=(15, 11))
        lower = tk.Frame(status_inner, bg=WHITE)
        lower.pack(fill="x")
        self._label(lower, "", color=GREY, textvariable=self.message, anchor="w").pack(side="left")
        self._label(lower, "", color=GREY, textvariable=self.progress_info).pack(side="right")
        self._label(status_inner, "", color=GREY, textvariable=self.count_info).pack(anchor="w", pady=(9, 0))

    def _entry(self, frame, variable):
        return tk.Entry(frame, textvariable=variable, font=("Segoe UI", 10), relief="solid",
                        bd=1, highlightthickness=0, bg=WHITE, fg=INK)

    def _button(self, frame, title, command, *, primary=True):
        return tk.Button(frame, text=title, command=command, bg=BLUE if primary else "#E9EFF8",
                         fg=WHITE if primary else INK, activebackground="#1951BC" if primary else BORDER,
                         activeforeground=WHITE if primary else INK, relief="flat", bd=0,
                         padx=15, pady=10, font=("Segoe UI", 10, "bold"), cursor="hand2")

    def _browse(self):
        selected = filedialog.askopenfilename(title="Choose a video", filetypes=[
            ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wmv *.ts"), ("All files", "*.*")])
        if selected:
            self.video.set(selected)
            if not self.name_input.get().strip():
                self.name_input.set(Path(selected).stem)
            self.message.set("Video selected — choose filename and duration")

    def _estimate(self, *args):
        try:
            if self.video.get().strip() and Path(self.video.get()).is_file():
                self.file_info.set(Path(self.video.get()).name)
            else:
                self.file_info.set("No video selected")
            parse_duration(self.duration_input.get())
            self.count_info.set("Clip count calculated when processing starts")
        except CutterError:
            self.count_info.set("Enter a duration between 0.1 and 3600 seconds")

    def _save_preferences(self):
        write_settings({"duration": self.duration_input.get().strip(),
                        "output_folder": self.output.get().strip()})

    def _change_folder(self):
        chosen = filedialog.askdirectory(title="Select output folder", initialdir=self.output.get() if Path(self.output.get()).is_dir() else str(Path.home()))
        if chosen:
            self.output.set(chosen)
            try:
                self._save_preferences()
            except OSError as ex:
                messagebox.showwarning("Preferences", f"Could not save folder preference: {ex}")

    def _set_running(self, value: bool):
        self.processing = value
        for widget in (self.start_btn, self.browse_btn, self.folder_btn, self.duration_spin):
            widget.config(state="disabled" if value else "normal")
        self.cancel_btn.config(state="normal" if value else "disabled")

    def _start(self):
        if self.processing:
            return
        if not self.video.get().strip():
            messagebox.showerror("Video required", "Select a video first.")
            return
        if not self.name_input.get().strip():
            messagebox.showerror("Filename required", "Enter an output filename.")
            return
        try:
            parse_duration(self.duration_input.get())
            self._save_preferences()
        except (CutterError, OSError) as ex:
            messagebox.showerror("Settings", str(ex))
            return
        self.cancel.clear()
        self.progress.set(0)
        self.percent_info.set("0%")
        self.progress_info.set("0 / 0 clips")
        self.message.set("Inspecting video...")
        self._set_running(True)
        source, output, name, duration = self.video.get(), self.output.get(), self.name_input.get(), self.duration_input.get()
        self.worker = threading.Thread(target=self._work, args=(source, output, name, duration), daemon=True)
        self.worker.start()

    def _work(self, source, output, name, duration):
        try:
            job = prepare_job(Path(source), Path(output), name, duration)
            self.events.put(("count", len(job.parts)))
            finished = process_job(job, cancel=self.cancel,
                                   progress=lambda i, n, p: self.events.put(("progress", i, n, p.name)))
            self.events.put(("done", len(finished), str(job.folder)))
        except Cancelled as ex:
            self.events.put(("cancelled", str(ex)))
        except (CutterError, OSError) as ex:
            self.events.put(("error", str(ex)))
        except Exception as ex:
            self.events.put(("error", f"Unexpected processing error: {ex}"))

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "count":
                    self.progress_info.set(f"0 / {event[1]} clips")
                    self.count_info.set(f"Total clips: {event[1]}")
                    self.message.set("Cutting and exporting clips...")
                elif kind == "progress":
                    _, i, n, filename = event
                    percent = 100 * i / n
                    self.progress.set(percent)
                    self.percent_info.set(f"{percent:.0f}%")
                    self.progress_info.set(f"{i} / {n} clips")
                    self.message.set(f"Saved: {filename}")
                elif kind == "done":
                    self._set_running(False)
                    self.message.set(f"Complete — {event[1]} clips saved")
                    messagebox.showinfo("Complete", f"Saved {event[1]} clips to:\n{event[2]}")
                elif kind == "cancelled":
                    self._set_running(False)
                    self.message.set(event[1])
                elif kind == "error":
                    self._set_running(False)
                    self.message.set("Processing failed")
                    messagebox.showerror("Clip Cutter", event[1])
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def _cancel(self):
        self.cancel.set()
        self.message.set("Cancelling current clip...")
        self.cancel_btn.config(state="disabled")

    def _open_folder(self):
        folder = Path(self.output.get()).expanduser()
        if not folder.is_dir():
            messagebox.showwarning("Output folder", "No clips yet — output folder does not exist.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as ex:
            messagebox.showerror("Open folder", str(ex))

    def _close(self):
        if self.processing:
            if not messagebox.askyesno("Close", "Processing is running. Cancel and close? Completed clips will remain."):
                return
            self.cancel.set()
            if self.worker and self.worker.is_alive():
                self.after(120, self._close_when_idle)
                return
        self.destroy()

    def _close_when_idle(self):
        if self.worker and self.worker.is_alive():
            self.after(120, self._close_when_idle)
        else:
            self.destroy()


def main():
    app = VideoClipCutter()
    app.mainloop()


if __name__ == "__main__":
    main()
