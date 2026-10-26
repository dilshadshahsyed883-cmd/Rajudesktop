"""Offline desktop Image Renamer; independent of all other Rajudesktop apps."""
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .core import EXTENSIONS, execute, make_plan, save_history, scan_folder, undo_last

DATA = Path(os.environ.get("LOCALAPPDATA") or Path.home() / ".image-renamer") / "ImageRenamer"
SETTINGS = DATA / "settings.json"
HISTORY = DATA / "last-rename.json"
BG, PANEL, FIELD, FG, MUTED, ACCENT = "#101827", "#1b2940", "#263751", "#eef4ff", "#b2c2d8", "#3b82f6"

class RenamerWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Image Renamer — Offline")
        self.geometry("980x715")
        self.minsize(760, 560)
        self.configure(bg=BG)
        self.files, self.plan = [], []
        self.last_folder = None
        self.busy = False
        self.events = queue.Queue()
        try:
            opts = json.loads(SETTINGS.read_text(encoding="utf-8"))
        except (ValueError, OSError):
            opts = {}
        self.folder = tk.StringVar(value="No image folder selected")
        self.keyword = tk.StringVar(value="Alexa")
        self.start_at = tk.StringVar(value="1")
        self.destination = tk.StringVar(value=opts.get("output", str(Path.home() / "Documents" / "Renamed Images")))
        self.mode = tk.StringVar(value="copy")
        self.subfolders = tk.BooleanVar(value=False)
        self.summary = tk.StringVar(value="Choose images to get started")
        self.status = tk.StringVar(value="Ready")
        self._layout()
        for var in (self.keyword, self.start_at, self.destination, self.mode):
            var.trace_add("write", self.refresh)
        self.mode.trace_add("write", self.sync_mode)
        self.sync_mode()
        self.refresh()
        self.after(100, self.poll)

    @staticmethod
    def label(parent, value="", muted=False, bold=False, **kwargs):
        return tk.Label(parent, text=value, bg=parent["bg"], fg=MUTED if muted else FG,
                        font=("Segoe UI", 10, "bold" if bold else "normal"), **kwargs)

    @staticmethod
    def button(parent, text, action, primary=False):
        return tk.Button(parent, text=text, command=action, bg=ACCENT if primary else FIELD,
                         fg=FG, relief="flat", borderwidth=0, cursor="hand2", padx=14, pady=8,
                         activebackground="#2563eb", activeforeground=FG,
                         font=("Segoe UI", 10, "bold"))

    @staticmethod
    def input(parent, var, width=25):
        return tk.Entry(parent, textvariable=var, width=width, bg=FIELD, fg=FG,
                        insertbackground=FG, relief="flat", font=("Segoe UI", 11),
                        highlightthickness=1, highlightbackground="#435774",
                        highlightcolor=ACCENT)

    def _layout(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Images.Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=FG, rowheight=27)
        style.configure("Images.Treeview.Heading", background=FIELD, foreground=FG,
                        font=("Segoe UI", 10, "bold"))
        style.configure("Images.Horizontal.TProgressbar", background=ACCENT, troughcolor=FIELD)
        outer = tk.Frame(self, bg=BG, padx=20, pady=16)
        outer.pack(fill="both", expand=True)
        self.label(outer, "IMAGE RENAMER", bold=True).pack(anchor="w")
        self.label(outer, "Offline bulk naming · Original quality preserved", muted=True).pack(anchor="w", pady=(2, 12))
        area = tk.Frame(outer, bg=PANEL, padx=15, pady=10)
        area.pack(fill="x")
        self.label(area, "1   SELECT IMAGES", bold=True).pack(anchor="w")
        row = tk.Frame(area, bg=PANEL)
        row.pack(fill="x", pady=7)
        self.button(row, "Choose Folder", self.choose_folder).pack(side="left")
        self.button(row, "Add Images", self.add_images).pack(side="left", padx=8)
        self.label(row, "JPG · PNG · WEBP · TIFF · GIF · BMP", muted=True).pack(side="left", padx=5)
        tk.Checkbutton(area, text="Include subfolders", variable=self.subfolders, command=self.rescan,
                       bg=PANEL, fg=FG, selectcolor=FIELD, activebackground=PANEL,
                       activeforeground=FG).pack(anchor="w")
        self.label(area, textvariable=self.folder, muted=True, anchor="w").pack(fill="x")

        options = tk.Frame(outer, bg=PANEL, padx=15, pady=10)
        options.pack(fill="x", pady=10)
        self.label(options, "2   KEYWORD AND DESTINATION", bold=True).pack(anchor="w")
        row = tk.Frame(options, bg=PANEL)
        row.pack(fill="x", pady=8)
        self.label(row, "Keyword").pack(side="left")
        self.input(row, self.keyword, 30).pack(side="left", padx=(10, 24), ipady=7)
        self.label(row, "Start at").pack(side="left")
        self.input(row, self.start_at, 8).pack(side="left", padx=10, ipady=7)
        row = tk.Frame(options, bg=PANEL)
        row.pack(fill="x")
        for title, value in (("New output folder (keep originals)", "copy"), ("Rename originals (Undo supported)", "move")):
            tk.Radiobutton(row, text=title, variable=self.mode, value=value, bg=PANEL,
                           fg=FG, selectcolor=FIELD, activebackground=PANEL,
                           activeforeground=FG).pack(side="left", padx=(0, 25))
        row = tk.Frame(options, bg=PANEL)
        row.pack(fill="x", pady=7)
        self.label(row, "Output").pack(side="left")
        self.path_input = self.input(row, self.destination, 60)
        self.path_input.pack(side="left", fill="x", expand=True, padx=10, ipady=7)
        self.browse_button = self.button(row, "Browse", self.choose_output)
        self.browse_button.pack(side="left")

        preview = tk.Frame(outer, bg=PANEL, padx=15, pady=10)
        preview.pack(fill="both", expand=True)
        row = tk.Frame(preview, bg=PANEL)
        row.pack(fill="x")
        self.label(row, "3   LIVE FILENAME PREVIEW", bold=True).pack(side="left")
        self.label(row, textvariable=self.summary, muted=True).pack(side="right")
        panel = tk.Frame(preview, bg=PANEL)
        panel.pack(fill="both", expand=True, pady=(8, 0))
        self.tree = ttk.Treeview(panel, columns=("old", "new"), show="headings",
                                 selectmode="none", style="Images.Treeview")
        for col, title in (("old", "Original filename"), ("new", "New filename")):
            self.tree.heading(col, text=title)
            self.tree.column(col, minwidth=130, width=380, stretch=True)
        scroll = ttk.Scrollbar(panel, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        footer = tk.Frame(outer, bg=BG)
        footer.pack(fill="x", pady=(12, 0))
        self.progress = ttk.Progressbar(footer, style="Images.Horizontal.TProgressbar")
        self.progress.pack(fill="x", pady=(0, 9))
        self.label(footer, textvariable=self.status, muted=True).pack(side="left")
        self.rename_button = self.button(footer, "Rename All Images", self.rename, True)
        self.rename_button.pack(side="right")
        self.undo_button = self.button(footer, "Undo Last Rename", self.undo)
        self.undo_button.pack(side="right", padx=7)
        self.button(footer, "Open Output Folder", self.open_output).pack(side="right", padx=5)

    def sync_mode(self, *_):
        state = "disabled" if self.mode.get() == "move" else "normal"
        self.path_input.config(state=state)
        self.browse_button.config(state=state)

    def choose_folder(self):
        selected = filedialog.askdirectory(title="Select folder of images")
        if selected:
            self.folder.set(selected)
            self.rescan()

    def rescan(self):
        if Path(self.folder.get()).is_dir():
            try:
                self.files = scan_folder(Path(self.folder.get()), self.subfolders.get())
            except (ValueError, OSError) as exc:
                messagebox.showerror("Cannot open images", str(exc))
            self.refresh()

    def add_images(self):
        chosen = filedialog.askopenfilenames(title="Select images", filetypes=[
            ("Image files", "*.jpg *.jpeg *.png *.webp *.bmp *.tif *.tiff *.gif"), ("All", "*.*")])
        if chosen:
            existing = {str(path).casefold() for path in self.files}
            for name in chosen:
                path = Path(name)
                if path.suffix.lower() in EXTENSIONS and str(path).casefold() not in existing:
                    self.files.append(path)
                    existing.add(str(path).casefold())
            self.folder.set(f"{len(self.files)} images selected individually")
            self.refresh()

    def choose_output(self):
        selected = filedialog.askdirectory(title="Choose output folder")
        if selected:
            self.destination.set(selected)
            self.save_settings()

    def save_settings(self):
        try:
            DATA.mkdir(parents=True, exist_ok=True)
            SETTINGS.write_text(json.dumps({"output": self.destination.get()}), encoding="utf-8")
        except OSError:
            pass

    def refresh(self, *_):
        if self.busy or not hasattr(self, "tree"):
            return
        self.plan = []
        self.tree.delete(*self.tree.get_children())
        try:
            if not self.files:
                raise ValueError("No images selected")
            output = Path(self.destination.get()) if self.mode.get() == "copy" else None
            self.plan = make_plan(self.files, self.keyword.get(), int(self.start_at.get()),
                                  output, in_place=self.mode.get() == "move")
            for item in self.plan[:300]:
                self.tree.insert("", "end", values=(item.source.name, item.target.name))
            extra = " (first 300 shown)" if len(self.plan) > 300 else ""
            self.summary.set(f"{len(self.plan):,} images ready" + extra)
            self.rename_button.config(state="normal")
        except (ValueError, RuntimeError, OSError) as exc:
            self.summary.set(str(exc))
            self.rename_button.config(state="disabled")
        self.undo_button.config(state="normal" if HISTORY.exists() else "disabled")

    @staticmethod
    def do_rename(plan, in_place, progress):
        count = execute(plan, in_place, progress)
        if in_place:
            save_history(HISTORY, plan)
        return count

    def start_job(self, fn, args, count, status):
        self.busy = True
        self.rename_button.config(state="disabled")
        self.undo_button.config(state="disabled")
        self.status.set(status)
        self.progress.config(value=0, maximum=max(1, count))
        def worker():
            try:
                result = fn(*args, progress=lambda n, total: self.events.put(("progress", n, total)))
                self.events.put(("done", result, None))
            except Exception as exc:
                self.events.put(("done", None, str(exc)))
        threading.Thread(target=worker, daemon=True).start()

    def rename(self):
        self.refresh()
        if not self.plan:
            return
        move = self.mode.get() == "move"
        if move and not messagebox.askyesno("Change originals?", "This changes original filenames. Continue?"):
            return
        self.save_settings()
        plan = list(self.plan)
        self.last_folder = plan[0].target.parent
        self.start_job(self.do_rename, (plan, move), len(plan),
                       "Renaming images..." if move else "Copying images safely...")

    def undo(self):
        if not HISTORY.exists():
            return
        if not messagebox.askyesno("Undo", "Restore the previous image filenames?"):
            return
        try:
            count = len(json.loads(HISTORY.read_text(encoding="utf-8"))["entries"])
        except (ValueError, OSError, KeyError):
            count = 1
        self.start_job(undo_last, (HISTORY,), count, "Restoring original names...")

    def poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                if event[0] == "progress":
                    _, num, total = event
                    self.progress.config(value=num, maximum=total)
                    self.status.set(f"{num:,}/{total:,} processed")
                else:
                    _, count, err = event
                    self.busy = False
                    if err:
                        self.status.set("Failed: " + err)
                        messagebox.showerror("Image Renamer", err)
                    else:
                        self.status.set(f"Success: {count:,} images")
                        messagebox.showinfo("Image Renamer", f"Completed {count:,} images.")
                        if self.mode.get() == "move":
                            self.files = []
                    self.refresh()
        except queue.Empty:
            pass
        self.after(100, self.poll)

    def open_output(self):
        path = self.last_folder or Path(self.destination.get())
        if not path.is_dir():
            messagebox.showinfo("Output", "The output folder does not exist yet.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(path))
            else:
                subprocess.Popen(["open" if sys.platform == "darwin" else "xdg-open", str(path)])
        except OSError as exc:
            messagebox.showerror("Output", str(exc))


def main():
    RenamerWindow().mainloop()
    return 0
