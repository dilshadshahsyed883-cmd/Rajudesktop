"""Visible, non-disappearing Windows GUI for the read-only CapCut 9.7 probe.

Unlike the original console app, this never silently closes after running a scan.
It never starts CapCut, edits projects or modifies an installation.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import queue
import sys
import threading
import traceback
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from capcut_home_native_probe import probe, bridge_inspection
else:
    from . import probe, bridge_inspection

WINDOW_TITLE = "CapCut 9.7 Home Native Probe — read-only"


def initial_folder():
    try:
        return str(probe.default_root())
    except ValueError:
        return ""


def readable_state(result):
    if result["status"] == "NATIVE_HOME_EXPORT_SYMBOLS_FOUND":
        return "PASS — original 9.7 binaries and known native Home/queue symbols verified. This is NOT an exporter."
    missing = [name for name, info in result["modules"].items() if not info["present"]]
    altered = [name for name, info in result["modules"].items()
               if info["present"] and not info["verified_exact_archive"]]
    if missing:
        return "NOT VERIFIED — missing from selected folder: " + ", ".join(missing)
    if altered:
        return "NOT VERIFIED — file version or SHA-256 differs: " + ", ".join(altered)
    return "NOT VERIFIED — one or more native Home/queue markers are missing."


def summary_lines(result):
    lines = [readable_state(result), "", "Exact CapCut version: " + result["version"],
             "Selected files are read-only. No CapCut process or render engine was started.", ""]
    for name, item in result["modules"].items():
        if not item["present"]:
            lines.append(name + ": MISSING")
            continue
        lines.append(name + ": " + ("MATCH" if item["verified_exact_archive"] else "DIFFERENT VERSION"))
        for marker, present in item["markers"].items():
            lines.append("    " + marker + ": " + ("FOUND" if present else "MISSING"))
    bridge = result.get("bridge_inspection")
    if bridge:
        lines.append("")
        lines.append("NATIVE HOME BRIDGE INSPECTION")
        lines.append("Bridge classification: " + bridge["bridge_level"])
        for name, module in bridge["modules"].items():
            lines.append(name + " public PE exports: " + str(module["pe_export_count"]) +
                         " / " + str(module.get("declared_export_names", "?")) +
                         " (skipped: " + str(module.get("skipped_export_names", "?")) + ")")
            lines.append("  Direct target callable PE names: " +
                         (", ".join(module["target_backend_exports"]) or "NONE"))
        for name, error in bridge["errors"].items():
            lines.append(name + " inspection error: " + error)
        lines.append("Private Qt/QML callable interface: NOT VERIFIED")
    lines.extend(["", "Home checkboxes installed: NO", "Native export working: NOT VERIFIED",
                  "Your CapCut files were not changed."])
    return "\n".join(lines)


def valid_report_target(target, root):
    """Do not save reports inside the application installation tree."""
    target, root = Path(target).resolve(), Path(root).resolve()
    return target != root and root not in target.parents


class ProbeWindow(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(WINDOW_TITLE)
        self.geometry("950x630")
        self.minsize(680, 475)
        self.events = queue.Queue()
        self.result = None
        self.running = False
        self.folder = tk.StringVar(value=initial_folder())
        self.status = tk.StringVar(value="Ready. Choose the CapCut 9.7 folder, then click Scan.")
        self._layout()
        self.after(120, self._poll)

    def _layout(self):
        panel = ttk.Frame(self, padding=18)
        panel.pack(fill="both", expand=True)
        ttk.Label(panel, text="CapCut 9.7 — Home Native Probe",
                  font=("Segoe UI", 17, "bold")).pack(anchor="w")
        ttk.Label(panel,
                  text="Read-only diagnostic — this does not add export checkboxes or render MP4s.",
                  wraplength=900).pack(anchor="w", pady=(3, 16))
        folder_line = ttk.Frame(panel)
        folder_line.pack(fill="x", pady=4)
        ttk.Label(folder_line, text="9.7.0.4153 folder").pack(side="left")
        ttk.Entry(folder_line, textvariable=self.folder).pack(side="left", expand=True,
                                                               fill="x", padx=10)
        ttk.Button(folder_line, text="Browse", command=self.browse).pack(side="left")
        actions = ttk.Frame(panel)
        actions.pack(fill="x", pady=(12, 5))
        self.scan_button = ttk.Button(actions, text="Scan original CapCut files", command=self.scan)
        self.scan_button.pack(side="left")
        self.save_button = ttk.Button(actions, text="Save report", command=self.save, state="disabled")
        self.save_button.pack(side="left", padx=10)
        ttk.Button(actions, text="Close", command=self.destroy).pack(side="right")
        ttk.Label(panel, textvariable=self.status, wraplength=900).pack(anchor="w", pady=(7, 9))
        body = ttk.Frame(panel)
        body.pack(expand=True, fill="both")
        self.output = tk.Text(body, wrap="word", font=("Consolas", 10), state="disabled",
                              padx=12, pady=10)
        bar = ttk.Scrollbar(body, command=self.output.yview)
        self.output.configure(yscrollcommand=bar.set)
        self.output.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        self._show("This window stays open after a result or error.\n\n"
                   "Choose the folder containing CapCut.exe, VECreator.dll, "
                   "cccreator.dll and videoeditor.dll.\n"
                   "Nothing will be modified. The scan can take a little time.")

    def _show(self, value):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", value)
        self.output.configure(state="disabled")

    def browse(self):
        folder = filedialog.askdirectory(title="Choose CapCut 9.7.0.4153 installation folder")
        if folder:
            self.folder.set(folder)

    def scan(self):
        if self.running:
            return
        folder = Path(self.folder.get().strip()).expanduser()
        if not folder.is_dir():
            self.status.set("Folder not found. Select the versioned 9.7.0.4153 directory.")
            self._show("The folder does not exist:\n" + str(folder) +
                       "\n\nUse Browse to choose the directory containing CapCut.exe.")
            return
        self.result = None
        self.running = True
        self.scan_button.configure(state="disabled")
        self.save_button.configure(state="disabled")
        self.status.set("Scanning and hashing the original files…")
        self._show("Scanning read-only, no CapCut installation changes.\n"
                   "The largest DLL is approximately 281 MB; the window remains responsive.")

        def run():
            try:
                # Original probe only opens files in binary read mode.
                result = probe.audit(folder)
                if result["status"] == "NATIVE_HOME_EXPORT_SYMBOLS_FOUND":
                    result["bridge_inspection"] = bridge_inspection.inspect_install(folder)
                self.events.put(("done", result))
            except Exception:
                self.events.put(("error", traceback.format_exc(limit=10)))
        threading.Thread(target=run, daemon=True).start()

    def _poll(self):
        try:
            while True:
                kind, data = self.events.get_nowait()
                self.running = False
                self.scan_button.configure(state="normal")
                if kind == "done":
                    self.result = data
                    self.status.set(readable_state(data))
                    self._show(summary_lines(data))
                    self.save_button.configure(state="normal")
                else:
                    self.status.set("Scan failed, but the program is still open.")
                    self._show("Diagnostic error (no installation changes were made):\n\n" + data)
        except queue.Empty:
            pass
        self.after(120, self._poll)

    def save(self):
        if not self.result:
            return
        dest = filedialog.asksaveasfilename(
            title="Save diagnostic JSON outside CapCut", defaultextension=".json",
            filetypes=[("JSON report", "*.json")], initialfile="capcut-home-native-probe.json")
        if not dest:
            return
        if not valid_report_target(dest, self.folder.get()):
            messagebox.showerror("Unsafe destination",
                                 "Choose Desktop/Documents, not the CapCut installation folder.")
            return
        try:
            Path(dest).write_text(json.dumps(self.result, indent=2) + "\n", encoding="utf-8")
        except OSError as exc:
            messagebox.showerror("Save error", str(exc))
        else:
            self.status.set("Report saved. Original CapCut files unchanged.")


def main(argv=None):
    args = list(sys.argv[1:] if argv is None else argv)
    # Exercise actual Tk window creation in Windows CI, not only the CLI parser.
    if len(args) == 2 and args[0] == "--gui-smoke":
        app = ProbeWindow()
        try:
            app.update_idletasks()
            app.update()
            app.folder.set(str(Path(args[1]).parent / "intentionally-missing-capcut"))
            app.scan()
            app.update()
            assert "Folder not found" in app.status.get()
            Path(args[1]).write_text(json.dumps({"gui_window_created": True,
                "error_does_not_close_window": bool(app.winfo_exists()),
                "live_export_verified": False}), encoding="utf-8")
        finally:
            app.destroy()
        return 0
    # Preserve automation compatibility: --self-check and --root/--json use CLI.
    if args:
        return probe.main(args)
    if os.name != "nt":
        raise SystemExit("The graphical probe is built for Windows.")
    ProbeWindow().mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
