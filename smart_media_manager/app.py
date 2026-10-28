"""One Windows application with four independent media tool tabs.

Existing production-tested processing cores remain the single source of truth.
No operation silently deletes originals or overwrites outputs.
"""
from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from image_renamer.core import (
    EXTENSIONS as IMAGE_EXTENSIONS, execute as image_execute,
    make_plan as image_make_plan, save_history as image_save_history,
    scan_folder as image_scan_folder, natural_key as image_natural_key, undo_last as image_undo_last,
)
from smart_clip_renamer.core import RenamerError, create_plan as clip_create_plan, execute_plan as clip_execute_plan
from smart_media_manager.youtube_downloader import YoutubeTab
from smart_media_manager.cutter_queue_ui import BatchCutterTab
from video_clip_cutter.core import (
    default_output_folder, prepare_job, process_job, read_settings, write_settings,
)

NAVY = "#14243a"
BLUE = "#2869e8"
PALE = "#f3f6fb"
INK = "#1d2b41"
GREY = "#68778d"


def data_dir() -> Path:
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".local" / "share") / "SmartMediaManager"


def image_history() -> Path:
    # Compatible with the original Image Renamer's Undo Last Rename.
    return Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".image-renamer") / "ImageRenamer" / "last-rename.json"


class Preferences:
    def __init__(self, location: Path | None = None):
        self.location = location or data_dir() / "settings.json"
        try:
            data = json.loads(self.location.read_text(encoding="utf-8"))
            self.values = data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            self.values = {}

    def get(self, key: str, default: str = "") -> str:
        value = self.values.get(key, default)
        return value if isinstance(value, str) else default

    def set(self, key: str, value: str) -> None:
        self.values[key] = value
        self.location.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.location.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.values, indent=2), encoding="utf-8")
        os.replace(temporary, self.location)


def open_folder(folder: str | Path) -> None:
    path = Path(folder).expanduser()
    if not path.is_dir():
        messagebox.showinfo("Output", "Output folder does not exist yet.")
        return
    try:
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
    except OSError as exc:
        messagebox.showerror("Open output", str(exc))


def folder_entry(parent, value: tk.StringVar, command, title: str):
    line = ttk.Frame(parent)
    line.pack(fill="x", pady=(3, 13))
    ttk.Entry(line, textvariable=value).pack(side="left", fill="x", expand=True, padx=(0, 8))
    ttk.Button(line, text=title, command=command).pack(side="right")
    return line


def action_button(parent, title: str, fn):
    b = ttk.Button(parent, text=title, command=fn)
    b.pack(side="left", padx=(0, 9))
    return b


class WorkTab(ttk.Frame):
    """Runs file operations off the Tk thread; all Tk updates occur in poll()."""
    def __init__(self, master, prefs: Preferences):
        super().__init__(master, padding=20)
        self.prefs = prefs
        self.events: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.running = False
        self.status = tk.StringVar(value="Ready")
        self.progress = tk.DoubleVar(value=0)
        self.progress_label = tk.StringVar(value="")
        self._done = None
        self._busy_widgets = []
        self.after(100, self._poll)

    def heading(self, title: str, description: str):
        ttk.Label(self, text=title, style="Heading.TLabel").pack(anchor="w")
        ttk.Label(self, text=description, style="Muted.TLabel").pack(anchor="w", pady=(3, 19))

    def row_title(self, title: str):
        ttk.Label(self, text=title, style="Section.TLabel").pack(anchor="w", pady=(7, 4))

    def footer(self):
        bottom = ttk.Frame(self)
        bottom.pack(fill="x", side="bottom", pady=(14, 0))
        ttk.Progressbar(bottom, variable=self.progress, maximum=100).pack(fill="x", pady=(0, 6))
        ttk.Label(bottom, textvariable=self.status).pack(side="left")
        ttk.Label(bottom, textvariable=self.progress_label, style="Muted.TLabel").pack(side="right")

    def table(self, columns):
        container = ttk.Frame(self)
        container.pack(fill="both", expand=True, pady=(8, 0))
        tree = ttk.Treeview(container, columns=tuple(columns), show="headings", height=10)
        for name, label in columns.items():
            tree.heading(name, text=label)
            tree.column(name, anchor="w", width=200, minwidth=90)
        scrollbar = ttk.Scrollbar(container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return tree

    def busy_widgets(self, *widgets):
        self._busy_widgets.extend(widgets)

    def start(self, job, done):
        if self.running:
            return
        self.running = True
        self.cancel_event.clear()
        self.progress.set(0)
        self.progress_label.set("")
        self._done = done
        for widget in self._busy_widgets:
            widget.config(state="disabled")

        def work():
            try:
                self.events.put(("done", job(), None))
            except Exception as exc:
                self.events.put(("done", None, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def emit(self, done: int, total: int, message: str = ""):
        self.events.put(("progress", done, total, message))

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    _, done, total, detail = event
                    self.progress.set(100 * done / max(1, total))
                    self.progress_label.set(f"{done} / {total}")
                    if detail:
                        self.status.set(detail)
                else:
                    _, result, error = event
                    self.running = False
                    if hasattr(self, "stop_button"):
                        self.stop_button.config(state="disabled")
                    for widget in self._busy_widgets:
                        widget.config(state="normal")
                    if error:
                        self.status.set("Failed: " + error)
                        messagebox.showerror("Smart Media Manager", error)
                    elif self._done:
                        self.progress.set(100)
                        self._done(result)
        except queue.Empty:
            pass
        self.after(100, self._poll)


class CutterTab(WorkTab):
    def __init__(self, master, prefs: Preferences):
        super().__init__(master, prefs)
        old = read_settings()
        self.source = tk.StringVar()
        self.keyword = tk.StringVar()
        self.duration = tk.StringVar(value=prefs.get("cutter_duration", str(old.get("duration", "4"))))
        self.output = tk.StringVar(value=prefs.get("cutter_output", str(old.get("output_folder") or default_output_folder())))
        self.last_output = None
        self.heading("Video Clip Cutter", "Cut a local video into numbered clips, keeping video quality and audio.")
        self.row_title("1. Select a video")
        folder_entry(self, self.source, self.choose_video, "Browse Video")
        self.row_title("2. Output keyword and clip length")
        opts = ttk.Frame(self)
        opts.pack(fill="x", pady=(0, 12))
        ttk.Label(opts, text="Keyword").pack(side="left")
        ttk.Entry(opts, textvariable=self.keyword, width=40).pack(side="left", padx=(8, 26))
        ttk.Label(opts, text="Seconds").pack(side="left")
        ttk.Spinbox(opts, from_=0.1, to=3600, increment=0.5, textvariable=self.duration, width=8).pack(side="left", padx=8)
        for seconds in (2, 4, 5, 10):
            ttk.Button(opts, text=f"{seconds}s", command=lambda n=seconds: self.duration.set(str(n))).pack(side="left", padx=2)
        self.row_title("3. Output folder (Documents/ProcessedClips by default)")
        folder_entry(self, self.output, self.choose_output, "Change Folder")
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(8, 10))
        self.run_button = action_button(buttons, "Start Cutting", self.run)
        self.stop_button = action_button(buttons, "Cancel", self.stop)
        self.stop_button.config(state="disabled")
        ttk.Button(buttons, text="Open Output", command=lambda: open_folder(self.last_output or self.output.get())).pack(side="right")
        ttk.Label(self, text="Existing output files are never overwritten. Cancel retains completed clips.", style="Muted.TLabel").pack(anchor="w")
        self.busy_widgets(self.run_button)
        self.footer()

    def choose_video(self):
        name = filedialog.askopenfilename(title="Choose a video", filetypes=[
            ("Video files", "*.mp4 *.mov *.mkv *.avi *.webm *.m4v *.wmv *.ts"), ("All files", "*.*")])
        if name:
            self.source.set(name)
            if not self.keyword.get():
                self.keyword.set(Path(name).stem)

    def choose_output(self):
        name = filedialog.askdirectory(title="Choose clip output folder")
        if name:
            self.output.set(name)
            self.prefs.set("cutter_output", name)

    def run(self):
        source, folder, name, duration = self.source.get(), self.output.get(), self.keyword.get(), self.duration.get()
        if not source or not folder:
            messagebox.showerror("Missing input", "Select a video and output folder.")
            return
        self.prefs.set("cutter_output", folder)
        self.prefs.set("cutter_duration", duration)
        write_settings({"output_folder": folder, "duration": duration})
        self.stop_button.config(state="normal")
        self.status.set("Inspecting video and preparing clips...")

        def job():
            prepared = prepare_job(Path(source), Path(folder), name, duration)
            self.emit(0, len(prepared.parts), f"Creating {len(prepared.parts)} clips...")
            clips = process_job(prepared, cancel=self.cancel_event,
                                progress=lambda i, n, path: self.emit(i, n, f"Created {path.name}"))
            return len(clips), str(prepared.folder)

        def finished(result):
            self.stop_button.config(state="disabled")
            count, out = result
            self.last_output = out
            self.status.set(f"Completed: {count} clips")
            messagebox.showinfo("Clip Cutter", f"Saved {count} clips to:\n{out}")

        self.start(job, finished)

    def stop(self):
        if self.running:
            self.cancel_event.set()
            self.status.set("Stopping after current operation...")


class ImagesTab(WorkTab):
    def __init__(self, master, prefs: Preferences):
        super().__init__(master, prefs)
        self.source = tk.StringVar()
        self.keyword = tk.StringVar(value="Alexa")
        self.start_no = tk.StringVar(value="1")
        self.recursive = tk.BooleanVar(value=False)
        self.mode = tk.StringVar(value="copy")
        self.output = tk.StringVar(value=prefs.get("images_output", str(Path.home() / "Documents" / "Renamed Images")))
        self.files = []
        self.plan = None
        self.last_output = None
        self.heading("Image Batch Renamer", "Rename photos in natural order. Default copies preserve every original.")
        self.row_title("1. Choose folder or individual images")
        folder_entry(self, self.source, self.choose_folder, "Choose Folder")
        sel = ttk.Frame(self)
        sel.pack(fill="x", pady=(0, 10))
        ttk.Button(sel, text="Add Images", command=self.add_images).pack(side="left")
        ttk.Checkbutton(sel, text="Include subfolders", variable=self.recursive, command=self.scan).pack(side="left", padx=15)
        self.row_title("2. Keyword, numbering and output")
        opts = ttk.Frame(self)
        opts.pack(fill="x")
        ttk.Label(opts, text="Keyword").pack(side="left")
        ttk.Entry(opts, textvariable=self.keyword, width=30).pack(side="left", padx=(8, 25))
        ttk.Label(opts, text="Start at").pack(side="left")
        ttk.Entry(opts, textvariable=self.start_no, width=8).pack(side="left", padx=8)
        modes = ttk.Frame(self)
        modes.pack(fill="x", pady=(12, 5))
        ttk.Radiobutton(modes, text="Make renamed copies (safe)", variable=self.mode, value="copy").pack(side="left")
        ttk.Radiobutton(modes, text="Rename originals (Undo available)", variable=self.mode, value="move").pack(side="left", padx=22)
        folder_entry(self, self.output, self.choose_output, "Change Folder")
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(0, 5))
        self.preview_button = action_button(buttons, "Preview Names", self.preview)
        self.run_button = action_button(buttons, "Rename Images", self.run)
        self.undo_button = action_button(buttons, "Undo Last Rename", self.undo)
        ttk.Button(buttons, text="Open Output", command=lambda: open_folder(self.last_output or self.output.get())).pack(side="right")
        self.busy_widgets(self.preview_button, self.run_button, self.undo_button)
        self.footer()
        self.preview_tree = self.table({"before": "Original image", "after": "Output image"})
        for var in (self.keyword, self.start_no, self.mode, self.output):
            var.trace_add("write", self.invalidate)

    def invalidate(self, *_):
        self.plan = None

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Select image folder")
        if folder:
            self.source.set(folder)
            self.scan()

    def scan(self):
        source = Path(self.source.get())
        if not source.is_dir():
            return
        try:
            self.files = image_scan_folder(source, recursive=self.recursive.get())
            self.plan = None
            self.status.set(f"{len(self.files)} images found")
        except (ValueError, OSError) as exc:
            messagebox.showerror("Image folder", str(exc))

    def add_images(self):
        chosen = filedialog.askopenfilenames(title="Add individual images", filetypes=[
            ("Images", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.gif")])
        if chosen:
            already = {str(p).casefold() for p in self.files}
            for file in chosen:
                path = Path(file)
                if path.suffix.lower() in IMAGE_EXTENSIONS and str(path).casefold() not in already:
                    self.files.append(path)
                    already.add(str(path).casefold())
            self.files.sort(key=image_natural_key)
            self.source.set(f"{len(self.files)} individually selected")
            self.invalidate()
            self.status.set(f"{len(self.files)} images selected")

    def choose_output(self):
        folder = filedialog.askdirectory(title="Choose image output folder")
        if folder:
            self.output.set(folder)
            self.prefs.set("images_output", folder)

    def preview(self):
        if self.running:
            return False
        self.preview_tree.delete(*self.preview_tree.get_children())
        try:
            move = self.mode.get() == "move"
            output = None if move else Path(self.output.get())
            self.plan = image_make_plan(self.files, self.keyword.get(), int(self.start_no.get()), output, in_place=move)
            for row in self.plan[:500]:
                self.preview_tree.insert("", "end", values=(row.source.name, row.target.name))
            self.status.set(f"{len(self.plan)} images ready — first 500 shown" if len(self.plan) > 500 else f"{len(self.plan)} images ready")
            return True
        except (ValueError, OSError, RuntimeError) as exc:
            self.plan = None
            self.status.set(str(exc))
            messagebox.showerror("Image preview", str(exc))
            return False

    def run(self):
        if not self.plan and not self.preview():
            return
        move = self.mode.get() == "move"
        if move and not messagebox.askyesno("Rename originals?", "This changes original image filenames. Continue?"):
            return
        plan = tuple(self.plan)
        self.prefs.set("images_output", self.output.get())
        self.status.set("Renaming original files..." if move else "Copying renamed images...")
        def job():
            count = image_execute(plan, in_place=move, progress=lambda i, n: self.emit(i, n))
            if move:
                image_save_history(image_history(), plan)
            return count, str(plan[0].target.parent)

        def finished(result):
            count, output = result
            self.last_output = output
            self.status.set(f"Completed: {count} images")
            if move:
                self.files.clear()
                self.plan = None
                self.preview_tree.delete(*self.preview_tree.get_children())
            messagebox.showinfo("Image Renamer", f"Completed {count} images.\nSaved to:\n{output}")
        self.start(job, finished)

    def undo(self):
        history = image_history()
        if not history.is_file():
            messagebox.showinfo("Undo", "No previous in-place rename is recorded.")
            return
        if not messagebox.askyesno("Undo last rename", "Restore the previous original image names?"):
            return
        self.status.set("Restoring image names...")
        def job():
            return image_undo_last(history, progress=lambda i, n: self.emit(i, n))
        def finished(count):
            self.plan = None
            self.status.set(f"Restored {count} original names")
            messagebox.showinfo("Undo complete", f"Restored {count} original image names.")
        self.start(job, finished)


class ClipsTab(WorkTab):
    def __init__(self, master, prefs: Preferences):
        super().__init__(master, prefs)
        self.source = tk.StringVar()
        self.keyword = tk.StringVar(value="Alexa")
        self.output = tk.StringVar(value=prefs.get("clips_output", str(Path.home() / "Documents" / "Renamed Clips")))
        self.plan = None
        self.last_output = None
        self.heading("Smart Video Clip Renamer", "Combine selected clips, smart-shuffle their original sequence, then rename.")
        self.row_title("1. Main input folder (keep only wanted clips here)")
        folder_entry(self, self.source, self.choose_folder, "Choose Folder")
        self.row_title("2. Output keyword")
        ttk.Entry(self, textvariable=self.keyword).pack(fill="x", pady=(2, 10))
        self.row_title("3. Output root (a new job folder is created on each run)")
        folder_entry(self, self.output, self.choose_output, "Change Folder")
        buttons = ttk.Frame(self)
        buttons.pack(fill="x", pady=(7, 9))
        self.preview_button = action_button(buttons, "Preview Smart Order", self.preview)
        self.run_button = action_button(buttons, "Create Renamed Clips", self.run)
        self.stop_button = action_button(buttons, "Cancel", self.stop)
        self.stop_button.config(state="disabled")
        ttk.Button(buttons, text="Open Output", command=lambda: open_folder(self.last_output or self.output.get())).pack(side="right")
        self.note = tk.StringVar(value="Originals remain untouched; input siblings are separated where possible.")
        ttk.Label(self, textvariable=self.note, style="Muted.TLabel", wraplength=890).pack(anchor="w", pady=(0, 7))
        self.busy_widgets(self.preview_button, self.run_button)
        self.footer()
        self.preview_tree = self.table({"number": "#", "before": "Original clip", "after": "New clip", "source_num": "Original #"})
        for var in (self.source, self.keyword, self.output):
            var.trace_add("write", self.invalidate)

    def invalidate(self, *_):
        self.plan = None

    def choose_folder(self):
        folder = filedialog.askdirectory(title="Choose clips folder")
        if folder:
            self.source.set(folder)

    def choose_output(self):
        folder = filedialog.askdirectory(title="Choose output folder")
        if folder:
            self.output.set(folder)
            self.prefs.set("clips_output", folder)

    def preview(self):
        if self.running:
            return False
        try:
            plan = clip_create_plan(Path(self.source.get()), Path(self.output.get()), self.keyword.get())
        except (ValueError, OSError, RenamerError) as exc:
            self.plan = None
            messagebox.showerror("Clip preview", str(exc))
            return False
        self.plan = plan
        self.preview_tree.delete(*self.preview_tree.get_children())
        for i, item in enumerate(plan.items[:500], 1):
            self.preview_tree.insert("", "end", values=(i, item.original.name, item.renamed, item.original_number or "—"))
        warning = (f"{plan.remaining_adjacent_pairs} adjacent original pairs could not be separated."
                   if plan.remaining_adjacent_pairs else "Original consecutive siblings are separated.")
        self.note.set(warning)
        self.status.set(f"{len(plan.items)} clips ready (first 500 shown)" if len(plan.items) > 500 else f"{len(plan.items)} clips ready")
        return True

    def run(self):
        if self.plan is None and not self.preview():
            return
        plan = self.plan
        self.prefs.set("clips_output", self.output.get())
        self.stop_button.config(state="normal")
        self.status.set("Copying and renaming clips...")
        def job():
            return str(clip_execute_plan(plan, cancel=self.cancel_event,
                                         progress=lambda i, n, name: self.emit(i, n, f"Copied {name}")))

        def finished(destination):
            self.stop_button.config(state="disabled")
            self.plan = None
            self.last_output = destination
            self.status.set(f"Completed {len(plan.items)} clips")
            messagebox.showinfo("Smart Clip Renamer", f"Created {len(plan.items)} renamed clips.\nSaved to:\n{destination}")
        self.start(job, finished)

    def stop(self):
        if self.running:
            self.cancel_event.set()
            self.status.set("Cancelling and cleaning partial output...")


class SmartMediaManager(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Media Manager — Rajudesktop")
        self.geometry("1260x900")
        self.minsize(1020, 760)
        self.configure(bg=PALE)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=PALE)
        style.configure("TLabel", background=PALE, foreground=INK, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground=GREY, font=("Segoe UI", 9))
        style.configure("Heading.TLabel", foreground=NAVY, font=("Segoe UI", 22, "bold"))
        style.configure("Section.TLabel", foreground=INK, font=("Segoe UI", 10, "bold"))
        style.configure("TNotebook", background=PALE, borderwidth=0)
        style.configure("TNotebook.Tab", font=("Segoe UI", 11, "bold"), padding=(24, 13))
        style.configure("TButton", padding=(12, 8), font=("Segoe UI", 10),
                        background="#e6edf7", foreground=NAVY, relief="flat")
        style.map("TButton", background=[("active", "#d6e6ff"), ("disabled", "#edf0f4")])
        style.configure("Primary.TButton", padding=(16, 9), font=("Segoe UI", 10, "bold"),
                        background=BLUE, foreground="white", relief="flat")
        style.map("Primary.TButton", background=[("active", "#164db4"), ("disabled", "#b6c7e4")],
                  foreground=[("disabled", "#f6f8fc")])
        style.configure("TLabelframe", background=PALE, bordercolor="#d4deeb", relief="solid")
        style.configure("TLabelframe.Label", background=PALE, foreground=NAVY,
                        font=("Segoe UI", 10, "bold"))
        style.configure("Queue.Treeview", background="white", fieldbackground="white", rowheight=29,
                        foreground=INK, font=("Segoe UI", 9), borderwidth=0)
        style.configure("Queue.Treeview.Heading", font=("Segoe UI", 9, "bold"),
                        background="#dfe8f5", foreground=NAVY, padding=(8, 7))
        style.map("Queue.Treeview", background=[("selected", "#cde2ff")],
                  foreground=[("selected", NAVY)])
        style.configure("Horizontal.TProgressbar", background=BLUE, troughcolor="#dbe3ef")
        header = tk.Frame(self, bg=NAVY, height=95)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="SMART MEDIA MANAGER", fg="white", bg=NAVY,
                 font=("Segoe UI", 19, "bold")).pack(anchor="w", padx=28, pady=(14, 0))
        tk.Label(header, text="RAJU DESKTOP  •  4 tools  •  Local Windows processing",
                 fg="#b8cbea", bg=NAVY, font=("Segoe UI", 10)).pack(anchor="w", padx=30, pady=(3, 0))
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=14, pady=12)
        preferences = Preferences()
        self.tabs = [
            BatchCutterTab(notebook, preferences),
            ImagesTab(notebook, preferences),
            ClipsTab(notebook, preferences),
            YoutubeTab(notebook, preferences),
        ]
        for tab, title in zip(self.tabs, ("Video Clip Cutter", "Image Renamer", "Smart Clip Renamer", "YouTube Downloader")):
            notebook.add(tab, text=title)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def close(self):
        if any(tab.running for tab in self.tabs):
            messagebox.showwarning("Processing active", "Cancel or complete running media jobs before closing.")
            return
        self.destroy()


def main():
    SmartMediaManager().mainloop()


if __name__ == "__main__":
    main()
