"""One prepared draft -> real CapCut 9.6 Export dialog -> verified MP4.

Windows Tkinter app. Uses GUI transport only after explicit user preflight.
No draft edits, DLL injection, config changes, cloud controls or uploads.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import queue
import shutil
import sys
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from capcut_auto_export_evidence.core import (
        Halt, Observer, atomic_json, expected_video, project_name,
        self_check, unresolved, validate_media,
    )
    from capcut_auto_export_evidence.windows import Driver
else:
    from .core import (
        Halt, Observer, atomic_json, expected_video, project_name,
        self_check, unresolved, validate_media,
    )
    from .windows import Driver

ROOT = Path(os.getenv("LOCALAPPDATA") or Path.home()) / "CapCutAutoExportEvidence"
SETTINGS = ROOT / "settings.json"
JOURNAL = ROOT / "last_job.json"
AUDIT_EDITOR_POINT = (.920, .023)
AUDIT_DIALOG_POINT = (.817, .959)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        ROOT.mkdir(parents=True, exist_ok=True)
        try:
            saved = json.loads(SETTINGS.read_text("utf-8"))
        except (OSError, ValueError):
            saved = {}
        self.name = tk.StringVar(value=saved.get("name", ""))
        self.folder = tk.StringVar(value=saved.get("folder", str(Path.home() / "Videos")))
        self.ffprobe = tk.StringVar(value=saved.get("ffprobe", shutil.which("ffprobe") or ""))
        self.minutes = tk.StringVar(value=str(saved.get("minutes", 120)))
        self.use_open = tk.BooleanVar(value=False)
        self.confirm = tk.BooleanVar(value=False)
        self.status = tk.StringVar(value="Prepare CapCut 9.6 once, then start a single draft export.")
        self.card = None
        self.messages = queue.Queue()
        self.stop = threading.Event()
        self.busy = False
        self.title("CapCut 9.6 Auto Export — Evidence Demo")
        self.geometry("840x690")
        self.minsize(720, 615)
        self.configure(bg="#151a24")
        self._build()
        self.after(140, self._drain)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _build(self):
        s = ttk.Style(self)
        if "clam" in s.theme_names():
            s.theme_use("clam")
        s.configure("TFrame", background="#151a24")
        s.configure("TLabel", background="#151a24", foreground="#e4eaf3", font=("Segoe UI", 10))
        s.configure("TButton", padding=(8, 7))
        s.configure("TCheckbutton", background="#151a24", foreground="#e4eaf3")
        s.configure("TEntry", padding=5)
        main = ttk.Frame(self, padding=18)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="CapCut 9.6 — Ready Draft Auto Export", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        ttk.Label(main, text="One draft proof-of-concept  |  Real CapCut renderer  |  No editing/settings changes").pack(anchor="w", pady=(3, 15))
        ttk.Label(main, text="Exact CapCut project name = existing native Export name = expected MP4 name").pack(anchor="w")
        ttk.Entry(main, textvariable=self.name).pack(fill="x", pady=(4, 11))
        ttk.Label(main, text="Final MP4 folder (must already match CapCut's own Export-to setting)").pack(anchor="w")
        folder = ttk.Frame(main)
        folder.pack(fill="x", pady=(4, 11))
        ttk.Entry(folder, textvariable=self.folder).pack(side="left", fill="x", expand=True)
        ttk.Button(folder, text="Browse", command=self._browse).pack(side="left", padx=(7,0))
        ttk.Label(main, text="FFprobe path (required to verify output streams)").pack(anchor="w")
        ttk.Entry(main, textvariable=self.ffprobe).pack(fill="x", pady=(4, 11))
        timeout = ttk.Frame(main)
        timeout.pack(fill="x")
        ttk.Label(timeout, text="Monitor timeout (minutes)").pack(side="left")
        ttk.Entry(timeout, textvariable=self.minutes, width=9).pack(side="left", padx=(12,0))
        ttk.Checkbutton(main, variable=self.use_open,
                        text="Use already-open CapCut editor (skip Home draft-card selection)").pack(anchor="w", pady=(12,8))
        actions = ttk.Frame(main)
        actions.pack(fill="x", pady=(2,8))
        self.capture_btn = ttk.Button(actions, text="1  Record Home draft card (5s countdown)", command=self._capture)
        self.capture_btn.pack(side="left", padx=(0,8))
        self.preview_btn = ttk.Button(actions, text="Preview existing Export button", command=self._preview)
        self.preview_btn.pack(side="left")
        ttk.Checkbutton(main, variable=self.confirm,
            text="I finalized draft and native Export name/folder/FPS/resolution; cloud sync is OFF; button placement checked."
        ).pack(anchor="w", pady=(8,12))
        runrow = ttk.Frame(main)
        runrow.pack(fill="x")
        self.start_btn = ttk.Button(runrow, text="2  START SINGLE DRAFT EXPORT", command=self._start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(runrow, text="Stop monitoring (not CapCut render)", command=self.stop.set)
        self.stop_btn.pack(side="left", padx=8)
        ttk.Button(runrow, text="Acknowledge uncertain attempt", command=self._ack).pack(side="right")
        ttk.Label(main, textvariable=self.status, wraplength=775).pack(anchor="w", pady=(14,8))
        self.logview = tk.Text(main, height=11, state="disabled", bg="#0b111b", fg="#c7dcf0",
                               font=("Consolas", 9), wrap="word", relief="flat")
        self.logview.pack(fill="both", expand=True)
        self._log("Source evidence: exact CapCut 9.6.0.4097 DLL hash, Export-<draft> window, native GUI Export.")
        self._log("Not certified: native lyra-cli runtime, headless, overnight queue, CapCut output visual parity.")

    def _log(self, message):
        line = f"{time.strftime('%H:%M:%S')}  {message}"
        self.logview.configure(state="normal")
        self.logview.insert("end", line + "\n")
        self.logview.see("end")
        self.logview.configure(state="disabled")
        try:
            with (ROOT / "export.log").open("a", encoding="utf-8") as out:
                out.write(line + "\n")
        except OSError:
            pass

    def _browse(self):
        location = filedialog.askdirectory()
        if location:
            self.folder.set(location)

    def _save_settings(self):
        atomic_json(SETTINGS, {"name": self.name.get(), "folder": self.folder.get(),
                  "ffprobe": self.ffprobe.get(), "minutes": self.minutes.get()})

    def _capture(self):
        if self.busy:
            return
        self.capture_btn.configure(state="disabled")
        self.status.set("Move your cursor to the CENTER of the exact ready draft in CapCut Home. 5 seconds...")
        self.after(5000, self._capture_now)

    def _capture_now(self):
        try:
            self.card = Driver().card_at_cursor()
            self.status.set(f"CapCut Home card recorded (x={self.card.rx:.3f}, y={self.card.ry:.3f}). Do not scroll/resize Home.")
            self._log("Home draft card recorded (window identity and geometry captured).")
        except Exception as exc:
            self.card = None
            self.status.set("Capture failed: " + str(exc))
            self._log("Capture failed: " + str(exc))
        finally:
            self.capture_btn.configure(state="normal")

    def _preview(self):
        if self.busy:
            return
        try:
            name = project_name(self.name.get())
            driver = Driver()
            # Preview is observation-only. The user manually opens Export beforehand.
            dialog = driver.dialog(name)
            image = ROOT / "evidence" / "export_button_preview.png"
            driver.screenshot_marker(dialog, AUDIT_DIALOG_POINT, image)
            os.startfile(image)
            self.status.set("Inspect the red marker. If it misses native Export, do NOT start.")
            self._log(f"Export screenshot saved locally: {image}")
        except Exception as exc:
            messagebox.showerror("Preview unavailable", str(exc))

    def _preflight(self):
        name = project_name(self.name.get())
        target = expected_video(self.folder.get(), name)
        minutes = int(self.minutes.get())
        if not 2 <= minutes <= 720:
            raise Halt("Monitor timeout must be between 2 and 720 minutes.")
        if not self.use_open.get() and self.card is None:
            raise Halt("Record the exact draft card in CapCut Home, or select already-open editor.")
        if not self.confirm.get():
            raise Halt("Confirm your preconfigured native CapCut export settings and button preview.")
        probe = self.ffprobe.get().strip()
        if not probe:
            raise Halt("Provide ffprobe.exe path; without it a finished MP4 cannot be verified.")
        if not Path(probe).is_file() and shutil.which(probe) is None:
            raise Halt("FFprobe executable not found.")
        if unresolved(JOURNAL):
            raise Halt("Previous attempt unresolved. Check CapCut and output, then Acknowledge manually.")
        self._save_settings()
        return name, target, minutes, probe

    def _start(self):
        if self.busy:
            return
        try:
            name, target, minutes, probe = self._preflight()
        except (ValueError, OSError, Halt) as exc:
            messagebox.showerror("Safe preflight failed", str(exc))
            return
        msg = (f"Export ONE prepared CapCut project '{name}' to:\n{target}\n\n"
               "No draft edits. Do not move the mouse, lock Windows, change display, or sleep PC.\n"
               "If monitoring fails, CapCut may still be exporting; no automatic retries.")
        if not messagebox.askyesno("Start native CapCut GUI export", msg):
            return
        self.busy = True
        self.stop.clear()
        self.capture_btn.configure(state="disabled")
        self.preview_btn.configure(state="disabled")
        self.start_btn.configure(state="disabled")
        card = self.card
        use_open = self.use_open.get()

        def emit(message):
            self.messages.put(("log", message))

        def journal(phase, **fields):
            atomic_json(JOURNAL, {"phase": phase, "project": name, "target": str(target),
                        "at": time.strftime("%Y-%m-%dT%H:%M:%S"), **fields})

        def worker():
            started = False
            try:
                journal("opening")
                driver = Driver()
                if use_open:
                    driver.editor()
                    emit("Existing editor fingerprint verified.")
                else:
                    emit("Opening recorded CapCut Home draft...")
                    driver.open_card(card, self.stop)
                    emit("CapCut editor opened and fingerprint verified.")
                if self.stop.is_set():
                    raise Halt("Stopped before native export.")
                emit("Opening native Export dialog; confirming exact project name...")
                driver.open_export(name, self.stop, editor_point=AUDIT_EDITOR_POINT)
                if self.stop.is_set():
                    raise Halt("Stopped before final Export click.")
                # Persist BEFORE clicking: interrupted attempts never auto-repeat the export.
                journal("export_requested")
                driver.start_export(name, ratio=AUDIT_DIALOG_POINT)
                started = True
                emit("Native Export clicked. Monitoring MP4 until stable (CapCut is rendering).")
                observer = Observer(target)
                deadline = time.monotonic() + minutes * 60
                last = ""
                while time.monotonic() < deadline:
                    if self.stop.is_set():
                        raise Halt("Monitor stopped. CapCut render may STILL be active; check manually.")
                    done, message = observer.poll()
                    if message != last:
                        emit(message)
                        last = message
                    if done:
                        emit("MP4 finalized. Running ffprobe validation...")
                        metadata = validate_media(target, probe)
                        journal("verified", media=metadata)
                        self.messages.put(("success", str(target)))
                        return
                    self.stop.wait(5)
                raise Halt("Monitoring timed out; CapCut may STILL be rendering.")
            except Exception as exc:
                journal("uncertain" if started or JOURNAL.exists() else "blocked", reason=str(exc))
                self.messages.put(("error", str(exc)))
            finally:
                self.messages.put(("done", None))
        threading.Thread(target=worker, daemon=True).start()

    def _ack(self):
        if self.busy:
            messagebox.showwarning("Export active", "Do not reset while the demo is running.")
            return
        if not unresolved(JOURNAL):
            messagebox.showinfo("No unresolved attempt", "No interrupted/uncertain export to acknowledge.")
            return
        if not messagebox.askyesno("Manual reconciliation required",
            "ONLY acknowledge AFTER checking that CapCut is idle and the previous output has been "
            "verified or safely handled. This never cancels CapCut nor deletes files. Continue?"):
            return
        atomic_json(JOURNAL, {"phase": "acknowledged", "at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        self.status.set("Previous attempt manually acknowledged. Recheck output folder before any new Start.")
        self._log("Operator acknowledged an uncertain attempt after manual reconciliation.")

    def _drain(self):
        try:
            while True:
                typ, msg = self.messages.get_nowait()
                if typ == "log":
                    self.status.set(str(msg))
                    self._log(msg)
                elif typ == "success":
                    self.status.set("VERIFIED: " + str(msg))
                    self._log("VERIFIED MP4: " + str(msg))
                    messagebox.showinfo("CapCut MP4 verified", str(msg))
                elif typ == "error":
                    self.status.set("HALTED: " + str(msg))
                    self._log("HALTED: " + str(msg))
                    messagebox.showerror("Safe halt", str(msg))
                elif typ == "done":
                    self.busy = False
                    self.capture_btn.configure(state="normal")
                    self.preview_btn.configure(state="normal")
                    self.start_btn.configure(state="normal")
        except queue.Empty:
            pass
        self.after(140, self._drain)

    def _close(self):
        if self.busy:
            if not messagebox.askyesno("Monitor still running",
                "Stop monitoring and close? CapCut may CONTINUE rendering. You must reconcile before retry."):
                return
            self.stop.set()
        try:
            self._save_settings()
        except OSError:
            pass
        self.destroy()


def main():
    if "--self-check" in sys.argv:
        result = json.dumps(self_check(), indent=2)
        idx = sys.argv.index("--self-check")
        if idx + 1 < len(sys.argv):
            Path(sys.argv[idx + 1]).write_text(result + "\n", encoding="utf-8")
        elif sys.stdout is not None:
            print(result)
        return
    if os.name != "nt":
        raise SystemExit("Real CapCut GUI export requires Windows 10/11.")
    App().mainloop()


if __name__ == "__main__":
    main()
