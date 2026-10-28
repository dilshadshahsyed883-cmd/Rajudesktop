"""AutoCapCut Transitions Only — standalone desktop UI, never rebuilds the timeline."""
from __future__ import annotations

import json
import os
import subprocess
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from transition_engine import (
    capcut_running, cut_inventory, default_projects_dir, harvest_transitions,
    list_projects, load_project, parse_edit_file, plan_transitions, save_transitions,
)

BG, PANEL, INPUT, TEXT, MUTED, ACCENT, DANGER = "#15171d", "#22252e", "#303541", "#f1f2f5", "#a4a9b7", "#c9d9ff", "#ff9c9c"


def config_path() -> Path:
    return Path.home() / ".autocapcut_transitions_only.json"


class TransitionApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("AutoCapCut — Transitions Only")
        self.geometry("1030x790")
        self.minsize(850, 640)
        self.configure(bg=BG)
        self.settings = self._load_settings()
        self.root_dir = Path(self.settings.get("projects_folder") or default_projects_dir())
        self.projects = []
        self.catalog = []
        self.loaded_spec = None
        self.spec_file = None
        self.plan = None
        self.preview_path = None
        self.selected_ids = set(self.settings.get("selected_ids", []))
        self.favorites = set(self.settings.get("favorites", []))
        self.mode = tk.StringVar(value="none")
        self.duration = tk.DoubleVar(value=0.5)
        self.search = tk.StringVar(value="")
        self.favorites_only = tk.BooleanVar(value=False)
        self.folder_label = tk.StringVar(value=str(self.root_dir))
        self.project_var = tk.StringVar(value="")
        self.summary_var = tk.StringVar(value="Choose a project and validate transitions")
        self.status_var = tk.StringVar(value="Ready — originals are not modified until you click Apply")
        self._setup_style()
        self._build_ui()
        self.refresh()

    def _load_settings(self):
        try:
            return json.loads(config_path().read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def _save_settings(self):
        try:
            settings = dict(projects_folder=str(self.root_dir), favorites=sorted(self.favorites), selected_ids=sorted(self.selected_ids))
            config_path().write_text(json.dumps(settings, indent=2), encoding="utf-8")
        except OSError:
            pass

    def _setup_style(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", foreground=MUTED)
        style.configure("Header.TLabel", foreground=TEXT, font=("Segoe UI Semibold", 19))
        style.configure("TButton", background=PANEL, foreground=TEXT, padding=(12, 8), borderwidth=0, font=("Segoe UI", 10))
        style.map("TButton", background=[("active", "#3b4050")], foreground=[("disabled", "#888c9b")])
        style.configure("Primary.TButton", background="#6488df", foreground="#ffffff", padding=(14, 10), font=("Segoe UI Semibold", 11))
        style.map("Primary.TButton", background=[("active", "#4b70ca")])
        style.configure("TCombobox", fieldbackground=INPUT, background=INPUT, foreground=TEXT, arrowcolor=TEXT, padding=7)
        style.map("TCombobox", fieldbackground=[("readonly", INPUT)], foreground=[("readonly", TEXT)])
        style.configure("TRadiobutton", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.map("TRadiobutton", background=[("active", BG)])
        style.configure("TCheckbutton", background=BG, foreground=TEXT)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(18, 9))
        style.map("TNotebook.Tab", background=[("selected", "#333947")], foreground=[("selected", TEXT)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=28, borderwidth=0)
        style.map("Treeview", background=[("selected", "#465d88")])
        style.configure("Treeview.Heading", background=INPUT, foreground=TEXT, font=("Segoe UI Semibold", 9))

    def _build_ui(self):
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="AutoCapCut · Transitions Only", style="Header.TLabel").pack(anchor="w")
        ttk.Label(outer, text="Original AutoCapCut and Z Builder remain untouched. No media, timing, audio or track rebuilds.", style="Muted.TLabel").pack(anchor="w", pady=(4, 15))
        top = ttk.Frame(outer)
        top.pack(fill="x", pady=(0, 6))
        ttk.Label(top, text="CapCut projects folder", style="Muted.TLabel").pack(side="left")
        ttk.Button(top, text="Change folder", command=self.change_folder).pack(side="right")
        folder = tk.Label(outer, textvariable=self.folder_label, bg=BG, fg=MUTED, anchor="w", font=("Segoe UI", 9))
        folder.pack(fill="x", pady=(0, 11))
        pick = ttk.Frame(outer)
        pick.pack(fill="x", pady=(0, 8))
        ttk.Label(pick, text="Project").pack(side="left", padx=(0, 12))
        self.project_combo = ttk.Combobox(pick, textvariable=self.project_var, state="readonly")
        self.project_combo.pack(side="left", fill="x", expand=True)
        self.project_combo.bind("<<ComboboxSelected>>", lambda _e: self._project_changed())
        ttk.Button(pick, text="Refresh", command=self.refresh).pack(side="left", padx=(10, 0))
        self.cc_label = tk.Label(pick, text="", bg=BG, fg=MUTED, font=("Segoe UI", 9))
        self.cc_label.pack(side="left", padx=(12, 0))
        ttk.Label(outer, textvariable=self.summary_var, style="Muted.TLabel").pack(anchor="w", pady=(0, 10))
        tabs = ttk.Notebook(outer)
        tabs.pack(fill="both", expand=True)
        transitions_tab, edit_tab, preview_tab = ttk.Frame(tabs, padding=(10, 12)), ttk.Frame(tabs, padding=(10, 12)), ttk.Frame(tabs, padding=(10, 12))
        tabs.add(transitions_tab, text="Transitions")
        tabs.add(edit_tab, text="Edit file")
        tabs.add(preview_tab, text="Preview / Log")
        self.tabs = tabs
        mode_bar = ttk.Frame(transitions_tab)
        mode_bar.pack(fill="x", pady=(0, 12))
        for name, label in [("none", "Edit file only"), ("single", "Single"), ("mix", "Random mix")]:
            ttk.Radiobutton(mode_bar, text=label, value=name, variable=self.mode, command=self.invalidate).pack(side="left", padx=(0, 20))
        ttk.Label(transitions_tab, text="Select transitions already saved in any CapCut project (Ctrl/Shift for multiple)", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        findbar = ttk.Frame(transitions_tab)
        findbar.pack(fill="x", pady=(0, 8))
        entry = tk.Entry(findbar, textvariable=self.search, bg=INPUT, fg=TEXT, insertbackground=TEXT, relief="flat", font=("Segoe UI", 10))
        entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.search.trace_add("write", lambda *_: self.draw_catalog())
        ttk.Checkbutton(findbar, text="Favorites only", variable=self.favorites_only, command=self.draw_catalog).pack(side="left", padx=12)
        table_frame = ttk.Frame(transitions_tab)
        table_frame.pack(fill="both", expand=True)
        self.catalog_tree = ttk.Treeview(table_frame, columns=("favorite", "name", "category", "effect"), show="headings", selectmode="extended", height=9)
        for col, width in [("favorite", 34), ("name", 280), ("category", 140), ("effect", 240)]:
            self.catalog_tree.heading(col, text={"favorite":"★", "name":"Transition", "category":"Category", "effect":"Effect ID"}[col])
            self.catalog_tree.column(col, width=width, stretch=(col != "favorite"))
        self.catalog_tree.pack(side="left", fill="both", expand=True)
        sb = ttk.Scrollbar(table_frame, command=self.catalog_tree.yview)
        sb.pack(side="right", fill="y")
        self.catalog_tree.configure(yscrollcommand=sb.set)
        self.catalog_tree.bind("<<TreeviewSelect>>", self._selection_changed)
        controls = ttk.Frame(transitions_tab)
        controls.pack(fill="x", pady=(10, 0))
        ttk.Button(controls, text="★ Toggle favorite", command=self.toggle_favorite).pack(side="left", padx=(0, 8))
        ttk.Button(controls, text="Mix favorites", command=self.mix_favorites).pack(side="left")
        ttk.Label(controls, text="Duration").pack(side="left", padx=(25, 8))
        tk.Scale(controls, from_=0.2, to=1.5, resolution=0.1, orient="horizontal", variable=self.duration,
                 command=lambda _v: self.invalidate(), bg=BG, fg=TEXT, troughcolor=INPUT, highlightthickness=0,
                 length=190, showvalue=True).pack(side="left")
        self.catalog_count = tk.Label(transitions_tab, text="", bg=BG, fg=MUTED, anchor="w", font=("Segoe UI", 9))
        self.catalog_count.pack(fill="x", pady=(6, 0))
        ttk.Label(edit_tab, text="AutoCapCut v1 JSON: a named transition after a filename overrides the tab baseline.", style="Muted.TLabel").pack(anchor="w", pady=(0, 12))
        edit_actions = ttk.Frame(edit_tab)
        edit_actions.pack(fill="x", pady=(0, 10))
        ttk.Button(edit_actions, text="Load edit file (.json)", command=self.load_edit).pack(side="left", padx=(0, 8))
        ttk.Button(edit_actions, text="Clear file", command=self.clear_edit).pack(side="left", padx=(0, 8))
        ttk.Button(edit_actions, text="Copy sample JSON", command=self.copy_example).pack(side="left", padx=(0, 8))
        self.edit_label = ttk.Label(edit_tab, text="No JSON file selected", style="Muted.TLabel")
        self.edit_label.pack(anchor="w", pady=(0, 12))
        sample = '{\n  "version": 1,\n  "transitions": [\n    { "after": "0-00.png", "transition": "Flash Zoom", "duration": 0.6 },\n    { "after": "1-41.png", "transition": "Blink", "effect_id": "REAL_EFFECT_ID" }\n  ]\n}'
        self.sample = sample
        box = tk.Text(edit_tab, height=10, bg=PANEL, fg=TEXT, relief="flat", font=("Consolas", 10), wrap="word")
        box.pack(fill="both", expand=True)
        box.insert("1.0", sample)
        box.configure(state="disabled")
        ttk.Label(edit_tab, text="Will Apply / Missing / Skipped results appear in Preview / Log. Missing effects must first be used in a CapCut project.", style="Muted.TLabel", wraplength=800).pack(anchor="w", pady=10)
        ttk.Label(preview_tab, text="Preview checks exact existing cuts; it never rebuilds or moves media.", style="Muted.TLabel").pack(anchor="w", pady=(0, 8))
        prev_frame = ttk.Frame(preview_tab)
        prev_frame.pack(fill="both", expand=True)
        self.preview_tree = ttk.Treeview(prev_frame, columns=("status", "after", "transition", "reason"), show="headings", height=13)
        for col, width in [("status", 100), ("after", 160), ("transition", 165), ("reason", 390)]:
            self.preview_tree.heading(col, text=col.title())
            self.preview_tree.column(col, width=width, stretch=col != "status")
        self.preview_tree.pack(side="left", fill="both", expand=True)
        prevscroll = ttk.Scrollbar(prev_frame, command=self.preview_tree.yview)
        prevscroll.pack(side="right", fill="y")
        self.preview_tree.configure(yscrollcommand=prevscroll.set)
        self.warn_box = tk.Text(preview_tab, height=4, bg=PANEL, fg="#efd8a4", relief="flat", wrap="word", font=("Segoe UI", 9))
        self.warn_box.pack(fill="x", pady=(8, 0))
        self.warn_box.configure(state="disabled")
        footer = ttk.Frame(outer)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Button(footer, text="Validate / Preview", command=self.validate).pack(side="left")
        ttk.Button(footer, text="Open backups folder", command=self.open_backups).pack(side="left", padx=8)
        ttk.Button(footer, text="Open CapCut", command=self.open_capcut).pack(side="left", padx=2)
        self.apply_btn = ttk.Button(footer, text="Apply transitions only", style="Primary.TButton", command=self.apply)
        self.apply_btn.pack(side="right")
        self.status_label = tk.Label(outer, textvariable=self.status_var, bg=BG, fg=ACCENT, anchor="w", wraplength=950, font=("Segoe UI", 9))
        self.status_label.pack(fill="x", pady=(10, 0))

    def selected_project(self):
        for p in self.projects:
            if p.name == self.project_var.get():
                return p
        return None

    def invalidate(self):
        self.plan = None
        self.preview_path = None

    def _project_changed(self):
        self.invalidate()
        self.refresh_summary()

    def change_folder(self):
        folder = filedialog.askdirectory(title="Choose CapCut projects folder", initialdir=str(self.root_dir if self.root_dir.is_dir() else Path.home()))
        if folder:
            self.root_dir = Path(folder)
            self.folder_label.set(str(self.root_dir))
            self._save_settings()
            self.refresh()

    def refresh(self):
        previous = self.project_var.get()
        self.projects = list_projects(self.root_dir)
        self.project_combo["values"] = [p.name for p in self.projects]
        self.project_var.set(previous if any(p.name == previous for p in self.projects) else (self.projects[0].name if self.projects else ""))
        self.catalog = harvest_transitions(self.root_dir)
        self.cc_label.configure(text="CapCut OPEN" if capcut_running() else "CapCut closed", fg=DANGER if capcut_running() else "#92dbb0")
        self.invalidate()
        self.draw_catalog()
        self.refresh_summary()
        self.status_var.set(f"{len(self.projects)} projects / {len(self.catalog)} distinct transitions detected")

    def refresh_summary(self):
        project = self.selected_project()
        if project:
            try:
                source, _, _, warnings = load_project(project)
                cuts, skipped = cut_inventory(source)
                videos = sum(len(t.get("segments", [])) for t in source.get("tracks", []) if t.get("type") == "video")
                self.summary_var.set(f"{videos} visual segments · {len(cuts)} eligible same-track cuts · {len(skipped)} warning(s) · {len(self.catalog)} transitions detected")
            except Exception as e:
                self.summary_var.set(f"Project cannot be read: {e}")
        else:
            self.summary_var.set("No projects found. Choose the folder containing CapCut draft subfolders.")

    def draw_catalog(self):
        self.catalog_tree.delete(*self.catalog_tree.get_children())
        query = self.search.get().casefold().strip()
        count = 0
        for item in self.catalog:
            eid = item["effect_id"]
            if self.favorites_only.get() and eid not in self.favorites:
                continue
            if query and query not in (str(item["name"]) + " " + str(item["category"]) + " " + eid).casefold():
                continue
            self.catalog_tree.insert("", "end", iid=eid, values=("★" if eid in self.favorites else "", item["label"], item["category"], eid))
            count += 1
        self.catalog_tree.selection_set([x for x in self.selected_ids if self.catalog_tree.exists(x)])
        self.catalog_count.configure(text=f"{count} shown / {len(self.catalog)} available · {len(self.selected_ids)} selected · ★ {len(self.favorites)} favorites")

    def _selection_changed(self, _event=None):
        shown = set(self.catalog_tree.get_children())
        self.selected_ids = (self.selected_ids - shown) | set(self.catalog_tree.selection())
        self._save_settings()
        self.invalidate()
        self.catalog_count.configure(text=f"{len(self.catalog)} available · {len(self.selected_ids)} selected · ★ {len(self.favorites)} favorites")

    def toggle_favorite(self):
        for eid in self.catalog_tree.selection():
            if eid in self.favorites:
                self.favorites.remove(eid)
            else:
                self.favorites.add(eid)
        self._save_settings()
        self.draw_catalog()

    def mix_favorites(self):
        self.selected_ids = self.favorites.copy()
        self.mode.set("mix")
        self.draw_catalog()
        self.invalidate()

    def load_edit(self):
        filename = filedialog.askopenfilename(title="Select Edit File", filetypes=[("JSON", "*.json"), ("All files", "*.*")])
        if filename:
            try:
                self.loaded_spec = parse_edit_file(Path(filename).read_text(encoding="utf-8-sig"))
            except (OSError, ValueError) as e:
                messagebox.showerror("Invalid Edit File", str(e))
                return
            self.spec_file = Path(filename)
            self.edit_label.configure(text=f"{self.spec_file.name} · {len(self.loaded_spec['transitions'])} rules")
            self.invalidate()
            self.tabs.select(1)

    def clear_edit(self):
        self.loaded_spec = None
        self.spec_file = None
        self.edit_label.configure(text="No JSON file selected")
        self.invalidate()

    def copy_example(self):
        self.clipboard_clear()
        self.clipboard_append(self.sample)
        self.status_var.set("Example Edit File JSON copied to clipboard (replace placeholder names / effect IDs)")

    def _make_plan(self):
        path = self.selected_project()
        if not path:
            raise ValueError("Select a CapCut project")
        source, _, _, io_warnings = load_project(path)
        catalog_ids = {x["effect_id"] for x in self.catalog}
        ids = [c["effect_id"] for c in self.catalog if c["effect_id"] in self.selected_ids and c["effect_id"] in catalog_ids]
        mode = self.mode.get()
        if mode == "single" and len(ids) != 1:
            raise ValueError("Single mode needs exactly one selected transition")
        if mode == "mix" and not ids:
            raise ValueError("Random mix needs at least one selected transition")
        plan = plan_transitions(source, self.catalog, mode, ids, self.duration.get(), self.loaded_spec)
        plan.warnings = io_warnings + plan.warnings
        return path, plan

    def validate(self):
        try:
            path, plan = self._make_plan()
        except Exception as e:
            messagebox.showerror("Cannot validate", str(e))
            return False
        self.preview_tree.delete(*self.preview_tree.get_children())
        for row in plan.rows:
            self.preview_tree.insert("", "end", values=(row["status"], row["after"], row["transition"], row["reason"]))
        self.warn_box.configure(state="normal")
        self.warn_box.delete("1.0", "end")
        self.warn_box.insert("end", "\n".join(plan.warnings) if plan.warnings else "No unsafe gaps / overlaps detected in eligible cuts.")
        self.warn_box.configure(state="disabled")
        self.plan = plan
        self.preview_path = path
        counts = plan.counts
        self.status_var.set(f"Preview: {counts['eligible_cuts']} eligible cuts · {len(plan.chosen)} selected · {counts['will_apply']} JSON Will Apply · {counts['missing']} Missing · {counts['skipped']} Skipped")
        self.tabs.select(2)
        return True

    def apply(self):
        # Fresh preflight, then a second read inside save_transitions.
        if not self.validate():
            return
        if not self.plan or not self.plan.chosen:
            messagebox.showwarning("Nothing to apply", "Select an available transition or load an Edit File containing valid rules.")
            return
        if capcut_running():
            messagebox.showerror("Close CapCut", "CapCut is still open. Close it first; otherwise CapCut autosave can overwrite your transitions.")
            return
        project = self.preview_path
        if not messagebox.askyesno("Apply transitions only?", f"Project: {project.name}\n\nApply transitions to {len(self.plan.chosen)} existing cuts?\n\nAll image/video clips, audio, time ranges and motions will be preserved. A recoverable backup will be created before writing."):
            return
        try:
            result = save_transitions(project, self.catalog, self.plan)
        except Exception as e:
            messagebox.showerror("No unsafe changes committed", f"Apply failed:\n{e}\n\nCheck project backups before reopening CapCut.")
            return
        if result["saved"]:
            text = f"Applied {result['changed']} transitions; {result['already_matching']} already matched.\n\nBackup: {result['backup_dir']}\n\nNow reopen the project in CapCut and inspect it."
        else:
            text = f"All {result['already_matching']} selected cuts already have matching transitions. No write needed."
        messagebox.showinfo("Transitions-only result", text)
        self.status_var.set(text.replace("\n", " "))
        self.refresh_summary()

    def open_capcut(self):
        try:
            if sys.platform == "win32":
                os.startfile("capcut:")  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", "-b", "com.lemon.lvoverseas"])
            else:
                messagebox.showinfo("Open CapCut", "Open CapCut manually on this operating system.")
        except Exception as e:
            messagebox.showerror("Open CapCut", f"CapCut launch failed: {e}\nOpen it manually from Windows Start menu.")

    def open_backups(self):
        project = self.selected_project()
        if not project:
            return
        path = project / ".transition_only_backups"
        if not path.exists():
            messagebox.showinfo("No backups", "No transitions-only backups exist for this project yet.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(path)  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as e:
            messagebox.showerror("Could not open folder", str(e))


if __name__ == "__main__":
    TransitionApp().mainloop()
