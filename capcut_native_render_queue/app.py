"""All CapCut drafts -> serial native renders. No FFmpeg or coordinate macros."""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import sys
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from capcut_native_render_queue.core import (
        NativeIPC, NativeUnavailable, atomic_write, bind_projects, candidate_roots,
        locate_capcut, safe_filename, scan_drafts, sha256, verify_output)
else:
    from .core import (NativeIPC, NativeUnavailable, atomic_write, bind_projects,
                       candidate_roots, locate_capcut, safe_filename, scan_drafts,
                       sha256, verify_output)

STATE_DIR = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "CapCutNativeRenderQueue"
STATE = STATE_DIR / "queue.json"
SETTINGS = STATE_DIR / "settings.json"


def read_json(path, fallback):
    try: return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError): return fallback


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        settings = read_json(SETTINGS, {})
        self.title("CapCut Native Render Queue — 9.6")
        self.geometry("1020x650")
        self.minsize(790, 510)
        self.drafts = []
        self.engine = None
        self.inbox = queue.Queue()
        self.stop_after = threading.Event()
        self.busy = False
        self.since = None
        self.root_var = tk.StringVar(value=settings.get("draft_root", ""))
        self.out_var = tk.StringVar(value=settings.get("output", str(Path.home() / "Videos" / "CapCut Native Renders")))
        self.engine_label = tk.StringVar(value="Checking CapCut's native engine…")
        self.status = tk.StringVar(value="Finding all local drafts…")
        self._build()
        self.after(120, self._poll)
        self.after(250, self.refresh)
        self.protocol("WM_DELETE_WINDOW", self.close)

    def _build(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names(): style.theme_use("clam")
        style.configure("Treeview", rowheight=27, font=("Segoe UI", 10))
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"))
        panel = ttk.Frame(self, padding=17)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="CapCut Native Render Queue", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        ttk.Label(panel, text="All drafts  •  One Start Render  •  CapCut's own engine  •  No FFmpeg / mouse recording").pack(anchor="w", pady=(4, 15))
        for title, variable, picker in [
            ("Drafts folder (blank = automatic)", self.root_var, self.select_root),
            ("Export MP4 folder", self.out_var, self.select_output),
        ]:
            line = ttk.Frame(panel)
            line.pack(fill="x", pady=4)
            ttk.Label(line, text=title, width=31).pack(side="left")
            ttk.Entry(line, textvariable=variable).pack(side="left", fill="x", expand=True, padx=8)
            ttk.Button(line, text="Browse", command=picker).pack(side="left")
        ttk.Label(panel, textvariable=self.engine_label, wraplength=950).pack(anchor="w", pady=(10, 7))
        columns = ("name", "modified", "engine", "queue")
        self.table = ttk.Treeview(panel, columns=columns, show="headings", selectmode="browse")
        for key, caption, width in [
            ("name", "CapCut draft", 350), ("modified", "Last edited", 155),
            ("engine", "Native ref", 130), ("queue", "Render status", 230),
        ]:
            self.table.heading(key, text=caption)
            self.table.column(key, width=width, stretch=key == "name")
        self.table.pack(fill="both", expand=True, pady=(6, 10))
        actions = ttk.Frame(panel)
        actions.pack(fill="x")
        self.start_button = ttk.Button(actions, text="▶ START RENDER", command=self.start)
        self.start_button.pack(side="left", padx=(0, 10))
        ttk.Button(actions, text="Refresh drafts", command=self.refresh).pack(side="left", padx=(0, 10))
        ttk.Button(actions, text="Stop after current", command=self.stop_after.set).pack(side="left", padx=(0, 10))
        ttk.Button(actions, text="Requeue selected", command=self.requeue_selected).pack(side="left")
        ttk.Label(panel, textvariable=self.status, wraplength=950).pack(anchor="w", pady=(12, 4))
        ttk.Label(panel, text="Native IPC must confirm each project before render. Errors halt the queue; no blind retries.").pack(anchor="w")

    def select_root(self):
        root = filedialog.askdirectory(title="Choose CapCut Projects directory")
        if root:
            self.root_var.set(root)
            self.refresh()

    def select_output(self):
        root = filedialog.askdirectory(title="Choose MP4 output directory")
        if root:
            self.out_var.set(root)
            self.save_settings()

    def save_settings(self):
        atomic_write(SETTINGS, {"draft_root": self.root_var.get(), "output": self.out_var.get()})

    def save_queue(self):
        atomic_write(STATE, {"items": {x["key"]: {
            "status": x["status"], "ref": x["ref"], "output": x.get("output", "")
        } for x in self.drafts}, "updated": time.time()})

    def redraw(self):
        for item in self.table.get_children(): self.table.delete(item)
        for index, row in enumerate(self.drafts):
            edited = time.strftime("%Y-%m-%d %H:%M", time.localtime(row["updated"])) if row["updated"] else "native project"
            self.table.insert("", "end", iid=str(index),
                              values=(row["title"], edited, "Verified" if row["ref"] else "Not bound", row["status"]))

    def refresh(self):
        if self.busy: return
        self.start_button.configure(state="disabled")
        self.status.set("Discovering local CapCut projects and checking native IPC…")
        prior = (read_json(STATE, {}).get("items", {}) if not self.drafts else
                 {r["key"]: {"status": r["status"], "ref": r["ref"], "output": r.get("output", "")}
                  for r in self.drafts})
        self.save_settings()
        root = self.root_var.get()
        def worker():
            try:
                disk = scan_drafts(candidate_roots(root))
                engine = NativeIPC(locate_capcut())
                native = engine.list()  # exact native refs, read-only
                rows = bind_projects(disk, native)
                info = f"CapCut 9.6 native IPC connected: {len(native)} verified project references."
            except Exception as exc:
                engine = None
                rows = bind_projects(scan_drafts(candidate_roots(root)), [])
                info = "Native IPC unavailable (render disabled): " + str(exc)
            for row in rows:
                old = prior.get(row["key"], {})
                if old.get("ref") != row["ref"] or not row["ref"]: continue
                if old.get("status") == "Completed":
                    path = Path(old.get("output", ""))
                    if path.is_file(): row["status"], row["output"] = "Completed", str(path)
                elif old.get("status") in ("Rendering", "Review"):
                    row["status"] = "Review"  # interrupted job never retried automatically
            self.inbox.put(("refresh", (rows, engine, info)))
        threading.Thread(target=worker, daemon=True).start()

    def start(self):
        if self.busy: return
        if self.engine is None:
            messagebox.showwarning("Native engine unavailable", "CapCut native IPC must respond. No FFmpeg fallback.")
            return
        pending = [r for r in self.drafts if r["ref"] and r["status"] == "Queued"]
        if not pending:
            messagebox.showinfo("No native drafts ready", "Refresh or select Requeue. Unbound drafts cannot render.")
            return
        target_dir = Path(self.out_var.get()).expanduser()
        try: target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            messagebox.showerror("MP4 folder", str(exc)); return
        self.save_settings()
        self.stop_after.clear()
        self.busy = True
        self.since = time.monotonic()
        self.start_button.configure(state="disabled")
        self.status.set(f"Starting {len(pending)} sequential CapCut engine renders…")
        def worker():
            for item in pending:
                if self.stop_after.is_set(): break
                target = target_dir / safe_filename(item["title"], item["ref"])
                if target.exists():
                    self.inbox.put(("error", (item["key"], "Existing output; refusing overwrite: " + str(target))))
                    break
                src = None
                for name in ("draft_content.json", "draft_info.json"):
                    p = Path(item["folder"]) / name if item["folder"] else None
                    if p and p.is_file(): src = (p, sha256(p)); break
                # Persist *before* invoking CapCut export: crash recovery never blind-repeats.
                # Write the crash-recovery record synchronously BEFORE starting CapCut.
                journal = read_json(STATE, {})
                journal.setdefault("items", {})[item["key"]] = {
                    "status": "Rendering", "ref": item["ref"], "output": str(target)}
                atomic_write(STATE, journal)
                self.inbox.put(("rendering", (item["key"], str(target))))
                try:
                    self.engine.render(item["ref"], target, minutes=180)
                    media = verify_output(target, seconds=180)
                    if src and src[0].is_file() and sha256(src[0]) != src[1]:
                        raise NativeUnavailable("Draft source changed during export. Manual review required.")
                    self.inbox.put(("completed", (item["key"], str(target), media)))
                except Exception as exc:
                    self.inbox.put(("error", (item["key"], str(exc))))
                    break
            self.inbox.put(("finished", None))
        threading.Thread(target=worker, daemon=True).start()

    def requeue_selected(self):
        if self.busy: return
        selection = self.table.selection()
        if not selection: return
        item = self.drafts[int(selection[0])]
        if not item["ref"]:
            messagebox.showwarning("Not bound", "Native IPC has not confirmed this draft reference.")
            return
        if item["status"] == "Review":
            if not messagebox.askyesno("Reconcile prior export",
                    "First verify CapCut is idle and prior output was resolved. Requeue?"):
                return
        item["status"] = "Queued"
        item["output"] = ""
        self.save_queue(); self.redraw()

    def _poll(self):
        try:
            while True:
                event, value = self.inbox.get_nowait()
                if event == "refresh":
                    self.drafts, self.engine, detail = value
                    self.engine_label.set(detail)
                    self.status.set(f"{len(self.drafts)} drafts shown; {sum(bool(r['ref']) for r in self.drafts)} native-bound.")
                    self.start_button.configure(state="normal" if self.engine else "disabled")
                    self.redraw(); self.save_queue()
                elif event in ("rendering", "completed", "error"):
                    row = next((r for r in self.drafts if r["key"] == value[0]), None)
                    if row:
                        if event == "rendering":
                            row["status"], row["output"] = "Rendering", value[1]
                            self.status.set("CapCut rendering: " + row["title"])
                        elif event == "completed":
                            row["status"], row["output"] = "Completed", value[1]
                            self.status.set("Completed: " + row["title"])
                        else:
                            row["status"] = "Review"
                            self.status.set("Stopped for manual review: " + value[1])
                        self.redraw(); self.save_queue()
                elif event == "finished":
                    self.busy = False
                    self.start_button.configure(state="normal" if self.engine else "disabled")
                    if self.stop_after.is_set(): self.status.set("Paused after current; remaining queue saved.")
        except queue.Empty: pass
        if self.busy and self.since:
            self.title(f"CapCut Native Render Queue — elapsed {int(time.monotonic()-self.since)}s")
        self.after(150, self._poll)

    def close(self):
        if self.busy and not messagebox.askyesno("Native render active",
             "Closing this app may leave CapCut rendering. The next run will require review. Close?"):
            return
        self.save_settings()
        self.destroy()


def main():
    if os.name != "nt": raise SystemExit("CapCut native rendering requires Windows 10/11.")
    App().mainloop()


if __name__ == "__main__":
    main()
