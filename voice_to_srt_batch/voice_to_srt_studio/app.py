"""Dark Tkinter UI for Voice → SRT Studio, single and batch operations."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from .engine import (
    AUDIO_EXTENSIONS, LANGUAGES, MODELS, PRESETS, Cancelled,
    collect_folder, make_model, output_path, render_srt, save_atomic,
    transcribe_one, unique_valid_sources,
)

BG = "#101827"
PANEL = "#1c293e"
FIELD = "#273951"
TEXT = "#f4f7ff"
SUBTLE = "#a9bedd"
ACCENT = "#4598f4"

@dataclass
class Item:
    source: Path
    state: str = "Queued"
    progress: int = 0
    detail: str = ""
    destination: Path | None = None


class Studio:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title("Voice to SRT Studio — Batch")
        self.root.geometry("1360x860")
        self.root.minsize(960, 625)
        self.root.configure(bg=BG)
        self.items: dict[str, Item] = {}
        self.counter = 0
        self.running = False
        self.stop_event = threading.Event()
        self.events: queue.Queue[tuple] = queue.Queue()
        self.model_choice = tk.StringVar(value="small")
        self.language_choice = tk.StringVar(value="English")
        self.length_choice = tk.StringVar(value="Recommended (3-4 sec)")
        self.policy_choice = tk.StringVar(value="Skip existing SRT")
        self.same_folder = tk.BooleanVar(value=True)
        self.output_folder = tk.StringVar()
        self.recursive = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Ready • Add one voice or a batch of voices")
        self.summary = tk.StringVar(value="0 files • 0 complete • 0 failed")
        self._configure_style()
        self._layout()
        self.root.after(100, self._drain_events)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _configure_style(self) -> None:
        style = ttk.Style(self.root)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("Studio.Treeview", background=PANEL, foreground=TEXT,
                        fieldbackground=PANEL, borderwidth=0, rowheight=27,
                        font=("Segoe UI", 10))
        style.configure("Studio.Treeview.Heading", background=FIELD,
                        foreground=TEXT, relief="flat", font=("Segoe UI", 10, "bold"))
        style.map("Studio.Treeview", background=[("selected", "#2b5e9c")],
                  foreground=[("selected", "#ffffff")])
        style.configure("Studio.TCombobox", fieldbackground="#ecf0f7", padding=5)
        style.configure("Studio.Horizontal.TProgressbar", background=ACCENT,
                        troughcolor=FIELD, borderwidth=0)

    def _label(self, parent, title: str, row: int, column: int = 0) -> None:
        tk.Label(parent, text=title, fg=TEXT, bg=PANEL,
                 font=("Segoe UI", 10)).grid(row=row, column=column,
                                                sticky="w", pady=(7, 4))

    def _button(self, parent, label: str, action, *, primary=False, width=None):
        btn = tk.Button(parent, text=label, command=action,
                        bg=ACCENT if primary else FIELD,
                        fg="#ffffff", activebackground="#3374ba",
                        activeforeground="#ffffff", borderwidth=0,
                        padx=12, pady=8, cursor="hand2",
                        font=("Segoe UI", 10, "bold" if primary else "normal"))
        if width:
            btn.config(width=width)
        return btn

    def _layout(self) -> None:
        header = tk.Frame(self.root, bg=BG, padx=20, pady=14)
        header.pack(fill="x")
        tk.Label(header, text="VOICE → SRT STUDIO", font=("Segoe UI", 23, "bold"),
                 fg=TEXT, bg=BG).pack(anchor="w")
        tk.Label(header, text="Single voice + batch voices  •  Accurate aligned subtitles  •  English, Urdu, Hindi",
                 font=("Segoe UI", 10), fg=SUBTLE, bg=BG).pack(anchor="w", pady=(2, 0))

        settings = tk.Frame(self.root, bg=PANEL, padx=16, pady=10)
        settings.pack(fill="x", padx=20)
        settings.columnconfigure(0, weight=1)
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(2, weight=1)
        settings.columnconfigure(3, weight=1)

        self._label(settings, "1. Save .srt files", 0, 0)
        out_row = tk.Frame(settings, bg=PANEL)
        out_row.grid(row=1, column=0, columnspan=4, sticky="ew")
        tk.Checkbutton(out_row, text="Same folder as each voice", variable=self.same_folder,
                       command=self._sync_output, bg=PANEL, fg=TEXT,
                       selectcolor=FIELD, activebackground=PANEL,
                       activeforeground=TEXT).pack(side="left", padx=(0, 12))
        self.folder_field = tk.Entry(out_row, textvariable=self.output_folder,
                                     bg=FIELD, fg=TEXT, insertbackground=TEXT,
                                     relief="flat", font=("Segoe UI", 10))
        self.folder_field.pack(side="left", fill="x", expand=True, ipady=8)
        self.choose_folder_button = self._button(out_row, "Choose output folder", self._choose_output)
        self.choose_folder_button.pack(side="left", padx=(7, 0))
        self._sync_output()

        widgets = [("Speech model", self.model_choice, MODELS),
                   ("Language", self.language_choice, LANGUAGES.keys()),
                   ("Subtitle length", self.length_choice, PRESETS.keys()),
                   ("Existing SRT", self.policy_choice,
                    ("Skip existing SRT", "Overwrite existing SRT"))]
        for col, (title, variable, values) in enumerate(widgets):
            self._label(settings, title, 2, col)
            combo = ttk.Combobox(settings, textvariable=variable, values=list(values),
                                 state="readonly", style="Studio.TCombobox")
            combo.grid(row=3, column=col, sticky="ew", padx=(0 if col == 0 else 6, 6), pady=(0, 7))
        tk.Label(settings,
                 text="Model loads once per queue. First use may download it; subsequent runs can work offline.",
                 bg=PANEL, fg=SUBTLE, anchor="w", font=("Segoe UI", 9)).grid(
                     row=4, column=0, columnspan=4, sticky="w")

        tools = tk.Frame(self.root, bg=BG, padx=20, pady=13)
        tools.pack(fill="x")
        tk.Label(tools, text="2. Voice queue", font=("Segoe UI", 13, "bold"),
                 fg=TEXT, bg=BG).pack(side="left", padx=(0, 14))
        self.add_button = self._button(tools, "+ Add audio files", self._choose_files, primary=True)
        self.add_button.pack(side="left", padx=(0, 7))
        self.add_folder_button = self._button(tools, "+ Add folder", self._choose_source_folder)
        self.add_folder_button.pack(side="left", padx=(0, 7))
        tk.Checkbutton(tools, text="Include subfolders", variable=self.recursive,
                       bg=BG, fg=TEXT, selectcolor=FIELD,
                       activebackground=BG, activeforeground=TEXT).pack(side="left", padx=(0, 10))
        self.remove_button = self._button(tools, "Remove selected", self._remove_selected)
        self.remove_button.pack(side="right", padx=(5, 0))
        self.clear_button = self._button(tools, "Clear queue", self._clear)
        self.clear_button.pack(side="right", padx=(5, 0))
        self.retry_button = self._button(tools, "Retry incomplete", self._retry_incomplete)
        self.retry_button.pack(side="right", padx=(5, 0))

        table_outer = tk.Frame(self.root, bg=PANEL)
        table_outer.pack(fill="both", expand=True, padx=20)
        columns = ("file", "state", "progress", "output")
        self.tree = ttk.Treeview(table_outer, columns=columns, show="headings",
                                 selectmode="extended", style="Studio.Treeview")
        self.tree.heading("file", text="Audio file")
        self.tree.heading("state", text="Status")
        self.tree.heading("progress", text="Progress")
        self.tree.heading("output", text="Output / Error")
        self.tree.column("file", width=340, stretch=True)
        self.tree.column("state", width=110, stretch=False)
        self.tree.column("progress", width=85, stretch=False, anchor="center")
        self.tree.column("output", width=420, stretch=True)
        scroll = ttk.Scrollbar(table_outer, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")
        self.tree.bind("<<TreeviewSelect>>", self._selected_preview)

        action = tk.Frame(self.root, bg=BG, padx=20, pady=10)
        action.pack(fill="x")
        self.run_button = self._button(action, "Generate batch SRT", self._start, primary=True)
        self.run_button.pack(side="left", padx=(0, 8))
        self.cancel_button = self._button(action, "Cancel", self._cancel)
        self.cancel_button.pack(side="left")
        self.cancel_button.config(state="disabled")
        self.open_button = self._button(action, "Open output folder", self._open_output)
        self.open_button.pack(side="right")
        tk.Label(action, textvariable=self.summary, bg=BG, fg=SUBTLE,
                 font=("Segoe UI", 10)).pack(side="right", padx=12)

        tk.Label(self.root, textvariable=self.status, fg=SUBTLE, bg=BG,
                 anchor="w", font=("Segoe UI", 10)).pack(fill="x", padx=20)
        self.progressbar = ttk.Progressbar(self.root, maximum=100,
                                           style="Studio.Horizontal.TProgressbar")
        self.progressbar.pack(fill="x", padx=20, pady=(6, 10))
        tk.Label(self.root, text="SRT preview / errors", bg=BG, fg=SUBTLE,
                 font=("Segoe UI", 10), anchor="w").pack(fill="x", padx=20)
        preview_box = tk.Frame(self.root, bg=PANEL)
        preview_box.pack(fill="both", padx=20, pady=(4, 15), expand=False)
        self.preview = tk.Text(preview_box, bg=PANEL, fg=TEXT, insertbackground=TEXT,
                               relief="flat", height=7, wrap="word", padx=10, pady=8,
                               font=("Consolas", 10))
        self.preview.pack(fill="both", expand=True)
        self._preview("Add one or more voice files, then click Generate batch SRT.\n\n"
                      "Each voice gets a matching .srt file with word-aligned timestamps.")

    def _sync_output(self) -> None:
        if self.same_folder.get():
            self.folder_field.config(state="disabled")
            self.choose_folder_button.config(state="disabled")
        else:
            self.folder_field.config(state="normal")
            self.choose_folder_button.config(state="normal")

    def _choose_output(self) -> None:
        folder = filedialog.askdirectory(title="SRT output folder")
        if folder:
            self.output_folder.set(folder)

    def _choose_files(self) -> None:
        filenames = filedialog.askopenfilenames(title="Select voice files (multiple allowed)",
                                                filetypes=[("Audio/video files", " ".join("*" + e for e in sorted(AUDIO_EXTENSIONS))),
                                                           ("All files", "*.*")])
        self._add_paths(filenames)

    def _choose_source_folder(self) -> None:
        folder = filedialog.askdirectory(title="Folder containing voice files")
        if folder:
            self._add_paths(collect_folder(Path(folder), recursive=self.recursive.get()))

    def _add_paths(self, paths) -> None:
        if self.running:
            return
        existing = {os.path.normcase(os.path.abspath(it.source)) for it in self.items.values()}
        count = 0
        for source in unique_valid_sources(paths):
            key = os.path.normcase(os.path.abspath(source))
            if key in existing:
                continue
            existing.add(key)
            self.counter += 1
            iid = str(self.counter)
            self.items[iid] = Item(source=source)
            self._render_item(iid)
            count += 1
        self.status.set(f"Added {count} new voice(s). {len(self.items)} in queue.")
        self._summary()

    def _render_item(self, iid: str) -> None:
        item = self.items[iid]
        extra = str(item.destination) if item.destination else item.detail or str(item.source.parent)
        values = (item.source.name, item.state, f"{item.progress}%", extra)
        if self.tree.exists(iid):
            self.tree.item(iid, values=values)
        else:
            self.tree.insert("", "end", iid=iid, values=values)

    def _summary(self) -> None:
        counts = {name: sum(x.state == name for x in self.items.values())
                  for name in ("Done", "Failed", "Skipped", "Cancelled")}
        self.summary.set(f"{len(self.items)} files  •  {counts['Done']} done  •  "
                         f"{counts['Skipped']} skipped  •  {counts['Failed']} failed")
        if self.items and not self.running:
            finished = sum(x.state in ("Done", "Skipped", "Failed", "Cancelled")
                           for x in self.items.values())
            self.progressbar["value"] = finished / len(self.items) * 100

    def _remove_selected(self) -> None:
        if self.running:
            return
        for iid in self.tree.selection():
            self.items.pop(iid, None)
            self.tree.delete(iid)
        self._summary()

    def _clear(self) -> None:
        if self.running:
            return
        self.items.clear()
        for iid in self.tree.get_children():
            self.tree.delete(iid)
        self.progressbar["value"] = 0
        self._summary()
        self._preview("Queue cleared. Audio files on disk were not deleted.")

    def _retry_incomplete(self) -> None:
        if self.running:
            return
        num = 0
        for iid, item in self.items.items():
            if item.state in ("Failed", "Cancelled", "Skipped"):
                item.state, item.progress, item.detail, item.destination = "Queued", 0, "", None
                self._render_item(iid)
                num += 1
        self.status.set(f"Requeued {num} incomplete item(s).")
        self.progressbar["value"] = 0
        self._summary()

    def _set_running(self, value: bool) -> None:
        self.running = value
        for btn in (self.add_button, self.add_folder_button, self.remove_button,
                    self.clear_button, self.retry_button, self.run_button):
            btn.config(state="disabled" if value else "normal")
        self.cancel_button.config(state="normal" if value else "disabled")
        self._sync_output()
        if value:
            self.folder_field.config(state="disabled")
            self.choose_folder_button.config(state="disabled")

    def _start(self) -> None:
        if self.running:
            return
        pending = [iid for iid, item in self.items.items() if item.state in ("Queued", "Failed", "Cancelled")]
        if not pending:
            messagebox.showinfo("Voice to SRT", "Add audio files or requeue incomplete items first.")
            return
        directory = None
        if not self.same_folder.get():
            value = self.output_folder.get().strip()
            if not value:
                messagebox.showwarning("Output folder", "Please choose an output folder first.")
                return
            directory = Path(value).expanduser()
            try:
                directory.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                messagebox.showerror("Output folder", str(exc))
                return
        self.stop_event.clear()
        for iid in pending:
            item = self.items[iid]
            item.state, item.progress, item.detail, item.destination = "Queued", 0, "", None
            self._render_item(iid)
        self._set_running(True)
        self.progressbar["value"] = 0
        opts = (self.model_choice.get(), self.length_choice.get(), self.language_choice.get(),
                self.policy_choice.get() == "Overwrite existing SRT")
        snapshot = [(iid, self.items[iid].source) for iid in pending]
        threading.Thread(target=self._worker, args=(snapshot, directory, opts),
                         daemon=True, name="srt-batch-worker").start()

    def _worker(self, snapshot, directory, opts) -> None:
        model_name, preset, language, overwrite = opts
        model = None
        try:
            for index, (iid, source) in enumerate(snapshot):
                if self.stop_event.is_set():
                    self.events.put(("item", iid, "Cancelled", 0, "Stopped by user", ""))
                    continue
                dest = output_path(source, directory)
                if dest.exists() and not overwrite:
                    self.events.put(("item", iid, "Skipped", 100, "Existing SRT was preserved", str(dest)))
                    continue
                if not source.is_file():
                    self.events.put(("item", iid, "Failed", 0, "Source audio is missing", ""))
                    continue
                try:
                    if model is None:
                        self.events.put(("message", "Loading speech model once for the batch..."))
                        model = make_model(model_name)
                    self.events.put(("item", iid, "Processing", 0, "Transcribing voice...", ""))
                    last_percent = [-1]
                    def progress(ratio: float):
                        percent = min(99, max(0, int(ratio * 100)))
                        if percent != last_percent[0]:
                            last_percent[0] = percent
                            self.events.put(("progress", iid, percent))
                    cues = transcribe_one(model, source, preset, language, progress, self.stop_event.is_set)
                    if not cues:
                        raise RuntimeError("No audible speech was detected; no empty SRT was written")
                    if self.stop_event.is_set():
                        raise Cancelled()
                    save_atomic(dest, render_srt(cues))
                    self.events.put(("item", iid, "Done", 100, f"{len(cues)} subtitles", str(dest)))
                except Cancelled:
                    self.events.put(("item", iid, "Cancelled", 0, "Stopped by user", ""))
                except Exception as exc:
                    self.events.put(("item", iid, "Failed", 0, str(exc)[:350], ""))
        finally:
            self.events.put(("finished",))

    def _cancel(self) -> None:
        if self.running:
            self.stop_event.set()
            self.status.set("Cancel requested • Stopping when the speech engine returns control...")
            self.cancel_button.config(state="disabled")

    def _drain_events(self) -> None:
        try:
            for _ in range(150):
                try:
                    event = self.events.get_nowait()
                except queue.Empty:
                    break
                kind = event[0]
                if kind == "message":
                    self.status.set(event[1])
                elif kind == "item":
                    _, iid, state, pct, detail, destination = event
                    if iid in self.items:
                        item = self.items[iid]
                        item.state, item.progress, item.detail = state, pct, detail
                        item.destination = Path(destination) if destination else None
                        self._render_item(iid)
                        self.status.set(f"{item.source.name}  •  {state}: {detail}")
                        if state == "Done":
                            self._show_file(item.destination)
                        elif state == "Failed":
                            self._preview(f"{item.source.name}\n\nERROR: {detail}")
                elif kind == "progress":
                    _, iid, pct = event
                    if iid in self.items:
                        self.items[iid].progress = pct
                        self._render_item(iid)
                elif kind == "finished":
                    self._set_running(False)
                    self.status.set("Batch finished • Review each row for result, and retry incomplete if needed.")
                self._summary()
                if self.running and self.items:
                    done = sum(1 for x in self.items.values() if x.state in
                               ("Done", "Skipped", "Failed", "Cancelled"))
                    partial = sum(x.progress / 100 for x in self.items.values()
                                  if x.state == "Processing")
                    self.progressbar["value"] = (done + partial) / len(self.items) * 100
        finally:
            self.root.after(100, self._drain_events)

    def _preview(self, message: str) -> None:
        self.preview.delete("1.0", "end")
        self.preview.insert("1.0", message)

    def _show_file(self, path: Path | None) -> None:
        if not path or not path.is_file():
            return
        try:
            with path.open("r", encoding="utf-8-sig") as handle:
                content = handle.read(12000)
            self._preview(content)
        except OSError as exc:
            self._preview(f"Could not preview file: {exc}")

    def _selected_preview(self, _event=None) -> None:
        selected = self.tree.selection()
        if not selected:
            return
        item = self.items.get(selected[0])
        if item:
            if item.destination and item.destination.exists():
                self._show_file(item.destination)
            else:
                self._preview(f"Audio: {item.source}\nStatus: {item.state}\n{item.detail}")

    def _open_output(self) -> None:
        selected = self.tree.selection()
        destination = (self.items[selected[0]].destination if selected and selected[0] in self.items else None)
        if destination:
            folder = destination.parent
        elif self.same_folder.get():
            folder = next(iter(self.items.values())).source.parent if self.items else None
        else:
            folder = Path(self.output_folder.get()).expanduser() if self.output_folder.get().strip() else None
        if not folder or not folder.is_dir():
            messagebox.showinfo("Output folder", "No output folder is available yet.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(folder))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(folder)])
            else:
                subprocess.Popen(["xdg-open", str(folder)])
        except OSError as exc:
            messagebox.showerror("Open output folder", str(exc))

    def _close(self) -> None:
        if self.running:
            messagebox.showinfo("Batch active", "Cancel the batch and let it stop before closing.")
            return
        self.root.destroy()


def main() -> None:
    root = tk.Tk()
    Studio(root)
    root.mainloop()
