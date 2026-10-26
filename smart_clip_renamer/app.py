"""Standalone offline Windows Tkinter UI for safe video clip rearrangement."""
from __future__ import annotations

import os
import queue
import subprocess
import sys
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .core import Cancelled, RenamerError, RenamePlan, create_plan, execute_plan

NAVY, NAVY_LIGHT = "#14243A", "#234361"
BLUE, INK, WHITE = "#2869E8", "#1D2B41", "#FFFFFF"
GREY, PALE, BORDER = "#68778D", "#F3F6FB", "#DBE3EF"


class SmartClipRenamer(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Smart Clip Renamer — Raju Desktop")
        self.geometry("1190x790")
        self.minsize(940, 610)
        self.configure(bg=PALE)
        self.source_var = tk.StringVar()
        self.output_var = tk.StringVar()
        self.keyword_var = tk.StringVar()
        self.summary_var = tk.StringVar(value="Select a folder to preview your clips.")
        self.warning_var = tk.StringVar(value="")
        self.status_var = tk.StringVar(value="Ready")
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_text_var = tk.StringVar(value="0 / 0")
        self.plan: RenamePlan | None = None
        self.events: queue.Queue = queue.Queue()
        self.cancel_event = threading.Event()
        self.running = False
        self.last_output: Path | None = None
        self._build()
        for variable in (self.source_var, self.output_var, self.keyword_var):
            variable.trace_add("write", self._invalidate)
        self.after(90, self._poll)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _label(self, parent, text, size=10, color=INK, weight="normal", bg=WHITE, **kw):
        return tk.Label(parent, text=text, font=("Segoe UI", size, weight),
                        fg=color, bg=bg, **kw)

    def _button(self, parent, text, command, primary=False):
        return tk.Button(parent, text=text, command=command,
                         font=("Segoe UI", 10, "bold"), padx=14, pady=9,
                         bg=BLUE if primary else "#E9EFF8",
                         fg=WHITE if primary else INK,
                         activebackground="#1951BC" if primary else BORDER,
                         relief="flat", borderwidth=0, cursor="hand2")

    def _entry(self, parent, var):
        return tk.Entry(parent, textvariable=var, font=("Segoe UI", 11),
                        fg=INK, bg=WHITE, relief="solid", bd=1)

    def _build(self):
        sidebar = tk.Frame(self, bg=NAVY, width=215)
        sidebar.pack(side="left", fill="y")
        sidebar.pack_propagate(False)
        self._label(sidebar, "▣  RAJU DESKTOP", 14, WHITE, "bold", NAVY).pack(
            anchor="w", padx=20, pady=(32, 5))
        self._label(sidebar, "Independent media tools", 9, "#ADC1DD", bg=NAVY).pack(
            anchor="w", padx=20, pady=(0, 38))
        self._label(sidebar, "  Smart Clip Renamer", 11, WHITE, "bold", NAVY_LIGHT,
                    anchor="w", padx=10, height=3).pack(fill="x", padx=9)
        self._label(sidebar, "LOCAL  •  NO RE-ENCODING", 9, "#ADC1DD", "bold", NAVY).pack(
            side="bottom", anchor="w", padx=20, pady=24)

        surface = tk.Frame(self, bg=PALE)
        surface.pack(side="left", fill="both", expand=True, padx=28, pady=23)
        self._label(surface, "Smart Clip Renamer", 23, INK, "bold", PALE).pack(anchor="w")
        self._label(surface, "Mix the original clip order, then generate continuous new names.", 10,
                    GREY, bg=PALE).pack(anchor="w", pady=(3, 17))

        card = tk.Frame(surface, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        card.pack(fill="x")
        form = tk.Frame(card, bg=WHITE)
        form.pack(fill="x", padx=20, pady=17)
        self._label(form, "1  Main clips folder", 11, weight="bold").pack(anchor="w")
        line1 = tk.Frame(form, bg=WHITE)
        line1.pack(fill="x", pady=(7, 11))
        self.source_entry = self._entry(line1, self.source_var)
        self.source_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.source_button = self._button(line1, "Select Folder", self._choose_source)
        self.source_button.pack(side="left", padx=(8, 0))
        self._label(form, "2  Output keyword", 11, weight="bold").pack(anchor="w")
        line2 = tk.Frame(form, bg=WHITE)
        line2.pack(fill="x", pady=(7, 11))
        self.keyword_entry = self._entry(line2, self.keyword_var)
        self.keyword_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self._label(line2, "Example: Alexa 1.mp4, Alexa 2.mp4...", 9, GREY).pack(
            side="left", padx=(12, 0))
        self._label(form, "3  Destination (new subfolder created for every job)", 11,
                    weight="bold").pack(anchor="w")
        line3 = tk.Frame(form, bg=WHITE)
        line3.pack(fill="x", pady=(7, 0))
        self.output_entry = self._entry(line3, self.output_var)
        self.output_entry.pack(side="left", fill="x", expand=True, ipady=7)
        self.output_button = self._button(line3, "Change Folder", self._choose_output)
        self.output_button.pack(side="left", padx=(8, 0))

        controls = tk.Frame(surface, bg=PALE)
        controls.pack(fill="x", pady=(13, 12))
        self.preview_button = self._button(controls, "Preview Smart Order", self._preview, True)
        self.preview_button.pack(side="left")
        self.start_button = self._button(controls, "Create Renamed Clips", self._start, True)
        self.start_button.pack(side="left", padx=(9, 0))
        self.cancel_button = self._button(controls, "Cancel", self._cancel)
        self.cancel_button.pack(side="left", padx=(9, 0))
        self.cancel_button.config(state="disabled")
        self.open_button = self._button(controls, "Open Output", self._open_output)
        self.open_button.pack(side="right")

        preview_card = tk.Frame(surface, bg=WHITE, highlightbackground=BORDER, highlightthickness=1)
        preview_card.pack(fill="both", expand=True)
        preview_header = tk.Frame(preview_card, bg=WHITE)
        preview_header.pack(fill="x", padx=18, pady=(13, 7))
        self._label(preview_header, "Rename Preview", 12, weight="bold").pack(side="left")
        self._label(preview_header, "", 10, GREY, textvariable=self.summary_var).pack(side="right")
        self._label(preview_card, "", 9, "#B45309", textvariable=self.warning_var, anchor="w",
                    wraplength=690, justify="left").pack(fill="x", padx=18, pady=(0, 6))
        grid = tk.Frame(preview_card, bg=WHITE)
        grid.pack(fill="both", expand=True, padx=18, pady=(0, 12))
        self.tree = ttk.Treeview(grid, columns=("position", "before", "after", "original_no"),
                                 show="headings", height=11, selectmode="browse")
        for key, title, width, anchor in [
            ("position", "#", 50, "center"), ("before", "Original Clip", 300, "w"),
            ("after", "Output Filename", 250, "w"),
            ("original_no", "Original #", 90, "center")
        ]:
            self.tree.heading(key, text=title)
            self.tree.column(key, width=width, minwidth=45, anchor=anchor,
                             stretch=key in {"before", "after"})
        scrollbar = ttk.Scrollbar(grid, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")

        footer = tk.Frame(surface, bg=PALE)
        footer.pack(fill="x", pady=(11, 0))
        self.progress = ttk.Progressbar(footer, variable=self.progress_var, maximum=100)
        self.progress.pack(fill="x", pady=(0, 5))
        self._label(footer, "", 10, GREY, bg=PALE, textvariable=self.status_var).pack(side="left")
        self._label(footer, "", 10, GREY, bg=PALE,
                    textvariable=self.progress_text_var).pack(side="right")

    def _invalidate(self, *_):
        if self.plan is not None:
            self.plan = None
            self.status_var.set("Settings changed — preview again before processing.")
            self.summary_var.set("Preview needed")
            self.warning_var.set("")
            for item in self.tree.get_children():
                self.tree.delete(item)

    def _choose_source(self):
        directory = filedialog.askdirectory(title="Select folder containing selected clips")
        if directory:
            self.source_var.set(directory)
            if not self.output_var.get().strip():
                self.output_var.set(str(Path(directory) / "Renamed_Output"))

    def _choose_output(self):
        directory = filedialog.askdirectory(title="Choose output destination")
        if directory:
            self.output_var.set(directory)

    def _preview(self):
        if self.running:
            return
        try:
            if not self.source_var.get().strip() or not self.output_var.get().strip():
                raise RenamerError("Choose input and output folders.")
            plan = create_plan(Path(self.source_var.get()), Path(self.output_var.get()),
                               self.keyword_var.get())
        except (RenamerError, OSError) as exc:
            messagebox.showerror("Cannot preview", str(exc))
            return
        self.plan = plan
        for item in self.tree.get_children():
            self.tree.delete(item)
        for n, row in enumerate(plan.items, start=1):
            self.tree.insert("", "end", values=(
                n, row.original.name, row.renamed, row.original_number
                if row.original_number is not None else "—"))
        self.summary_var.set(f"{len(plan.items)} clips • originals untouched")
        if plan.remaining_adjacent_pairs:
            self.warning_var.set(f"Warning: {plan.remaining_adjacent_pairs} consecutive original "
                                 "pair(s) could not be separated with this selection. "
                                 "Add more clips for better spacing.")
        else:
            self.warning_var.set("Separation check passed: no consecutive numbered originals adjacent.")
        self.status_var.set(f"Preview ready — output: {plan.destination}")
        self.progress_var.set(0)
        self.progress_text_var.set(f"0 / {len(plan.items)}")

    def _set_running(self, running):
        self.running = running
        for w in (self.preview_button, self.start_button, self.source_button,
                  self.output_button, self.source_entry, self.output_entry,
                  self.keyword_entry):
            w.config(state="disabled" if running else "normal")
        self.cancel_button.config(state="normal" if running else "disabled")

    def _start(self):
        if self.running:
            return
        if self.plan is None:
            self._preview()
            if self.plan is None:
                return
        self.cancel_event.clear()
        self._set_running(True)
        self.progress_var.set(0)
        self.status_var.set("Copying selected clips safely...")
        threading.Thread(target=self._work, args=(self.plan,), daemon=True).start()

    def _work(self, plan: RenamePlan):
        try:
            destination = execute_plan(
                plan, self.cancel_event,
                lambda i, n, name: self.events.put(("progress", i, n, name)))
            self.events.put(("done", str(destination), len(plan.items)))
        except Cancelled as exc:
            self.events.put(("cancelled", str(exc)))
        except Exception as exc:
            self.events.put(("error", str(exc)))

    def _poll(self):
        try:
            while True:
                event = self.events.get_nowait()
                kind = event[0]
                if kind == "progress":
                    _, i, n, name = event
                    self.progress_var.set(i / n * 100)
                    self.progress_text_var.set(f"{i} / {n}")
                    self.status_var.set(f"Copied: {name}")
                elif kind == "done":
                    _, destination, count = event
                    self._set_running(False)
                    self.last_output = Path(destination)
                    self.plan = None
                    self.progress_var.set(100)
                    self.status_var.set(f"Completed {count} clips — {destination}")
                    messagebox.showinfo("Completed", f"Renamed {count} clips.\n\nSaved to:\n{destination}\n\nOriginals were not changed.")
                else:
                    self._set_running(False)
                    self.plan = None
                    self.status_var.set(event[1])
                    if kind == "error":
                        messagebox.showerror("Rename failed", event[1])
        except queue.Empty:
            pass
        self.after(90, self._poll)

    def _cancel(self):
        if self.running:
            self.cancel_event.set()
            self.status_var.set("Cancelling and removing incomplete job output...")

    def _open_output(self):
        target = self.last_output
        if target is None and self.output_var.get().strip():
            target = Path(self.output_var.get())
        if target is None or not target.exists():
            messagebox.showinfo("Output folder", "No output folder exists yet.")
            return
        if sys.platform == "win32":
            os.startfile(str(target))
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(target)])
        else:
            subprocess.Popen(["xdg-open", str(target)])

    def _close(self):
        if self.running:
            messagebox.showwarning("Processing", "Cancel processing before closing the app.")
            return
        self.destroy()


def main():
    SmartClipRenamer().mainloop()


if __name__ == "__main__":
    main()
