"""CapCut Visual Controls standalone tester — Tkinter / no extra runtime dependencies."""
from __future__ import annotations
import os
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import traceback
from engine import BLURS, Options, create_preview, default_root, list_projects, load_project, project_fingerprint, save_project


class VisualApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("CapCut Visual Controls — Standalone Test v2")
        self.geometry("1250x850")
        self.minsize(990, 700)
        self.configure(bg="#f3f5f8")
        self.root_dir = tk.StringVar(value=str(default_root()))
        self.project = tk.StringVar()
        self.blur_enabled = tk.BooleanVar(value=True)
        self.blur_level = tk.StringVar(value="Level 2 — Medium")
        self.v_scale_enabled = tk.BooleanVar(value=True)
        self.v_y_enabled = tk.BooleanVar(value=True)
        self.i_scale_enabled = tk.BooleanVar(value=True)
        self.i_y_enabled = tk.BooleanVar(value=True)
        self.invert_y = tk.BooleanVar(value=False)
        self.fx_filter_enabled = tk.BooleanVar(value=True)
        self.fx_effect_enabled = tk.BooleanVar(value=True)
        self.fx_duration_label = tk.StringVar(value="Audio/timeline target: not yet scanned")
        self.values = {k: tk.StringVar(value=str(v)) for k, v in {
            "v_scale_min": 115, "v_scale_max": 125, "v_y_min": -220, "v_y_max": -120,
            "video_x": 0, "i_scale_min": 105, "i_scale_max": 110, "i_y_min": -50,
            "i_y_max": 0, "seed": 28}.items()}
        self.status = tk.StringVar(value="Select a CapCut project, preview changes, then Apply. Close CapCut before Apply.")
        self.cached = None
        # Any changed value invalidates the old preview; never apply stale settings.
        for var in list(self.values.values()) + [self.blur_level, self.root_dir, self.project]:
            var.trace_add("write", lambda *_: self._invalidate())
        self._setup_style()
        self._layout()
        self.refresh_projects()

    def _setup_style(self):
        s = ttk.Style(self)
        if "clam" in s.theme_names(): s.theme_use("clam")
        s.configure("TFrame", background="#f3f5f8")
        s.configure("TLabelframe", background="#f3f5f8", padding=8)
        s.configure("TLabelframe.Label", background="#f3f5f8", foreground="#273548", font=("Segoe UI", 10, "bold"))
        s.configure("TLabel", background="#f3f5f8", foreground="#263448", font=("Segoe UI", 9))
        s.configure("TCheckbutton", background="#f3f5f8", font=("Segoe UI", 9))
        s.configure("TButton", padding=6, font=("Segoe UI", 9))
        s.configure("Treeview", rowheight=26, font=("Segoe UI", 9))
        s.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"))

    def _layout(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=15, pady=(12, 6))
        ttk.Label(top, text="Standalone CapCut Visual Controls", font=("Segoe UI", 19, "bold")).pack(anchor="w")
        ttk.Label(top, text="Existing draft only  •  No timeline rebuild  •  Preview + guarded backup + rollback").pack(anchor="w")
        source = ttk.LabelFrame(self, text="1  Select existing CapCut project")
        source.pack(fill="x", padx=15, pady=6)
        line = ttk.Frame(source); line.pack(fill="x")
        ttk.Label(line, text="Projects folder", width=16).pack(side="left")
        ttk.Entry(line, textvariable=self.root_dir).pack(side="left", fill="x", expand=True, padx=4)
        ttk.Button(line, text="Browse", command=self.browse_root).pack(side="left", padx=4)
        ttk.Button(line, text="Refresh", command=self.refresh_projects).pack(side="left")
        line = ttk.Frame(source); line.pack(fill="x", pady=(6, 0))
        ttk.Label(line, text="Project", width=16).pack(side="left")
        self.project_choice = ttk.Combobox(line, textvariable=self.project, state="readonly")
        self.project_choice.pack(side="left", fill="x", expand=True, padx=4)
        self.project_choice.bind("<<ComboboxSelected>>", lambda _: self._invalidate())
        ttk.Button(line, text="Choose project folder", command=self.browse_project).pack(side="left", padx=4)

        settings = ttk.Frame(self); settings.pack(fill="x", padx=15, pady=5)
        left = ttk.LabelFrame(settings, text="2  Canvas blur and video controls"); left.pack(side="left", fill="both", expand=True, padx=(0, 5))
        r = ttk.Frame(left); r.pack(fill="x", pady=3)
        ttk.Checkbutton(r, text="Canvas Blur — ALL images and videos", variable=self.blur_enabled, command=self._invalidate).pack(side="left")
        ttk.Combobox(r, textvariable=self.blur_level, values=list(BLURS), state="readonly", width=22).pack(side="right")
        r = ttk.Frame(left); r.pack(fill="x", pady=3)
        ttk.Checkbutton(r, text="Videos: scale %", variable=self.v_scale_enabled, command=self._invalidate).pack(side="left")
        self._pair(r, "v_scale_min", "v_scale_max", "min / max")
        r = ttk.Frame(left); r.pack(fill="x", pady=3)
        ttk.Checkbutton(r, text="Videos: position Y (px)", variable=self.v_y_enabled, command=self._invalidate).pack(side="left")
        self._pair(r, "v_y_min", "v_y_max", "min / max")
        r = ttk.Frame(left); r.pack(fill="x", pady=3)
        ttk.Label(r, text="Videos X (px) — default 0").pack(side="left")
        ttk.Entry(r, textvariable=self.values["video_x"], width=8, justify="center").pack(side="right")

        right = ttk.LabelFrame(settings, text="3  Image controls"); right.pack(side="left", fill="both", expand=True, padx=(5, 0))
        r = ttk.Frame(right); r.pack(fill="x", pady=3)
        ttk.Checkbutton(r, text="Images: scale %", variable=self.i_scale_enabled, command=self._invalidate).pack(side="left")
        self._pair(r, "i_scale_min", "i_scale_max", "min / max")
        r = ttk.Frame(right); r.pack(fill="x", pady=3)
        ttk.Checkbutton(r, text="Images: position Y (px)", variable=self.i_y_enabled, command=self._invalidate).pack(side="left")
        self._pair(r, "i_y_min", "i_y_max", "min / max")
        ttk.Label(right, text="Image X is preserved. Animations/keyframes are preserved; their static transforms are skipped.", wraplength=420).pack(anchor="w", pady=(9, 3))
        r = ttk.Frame(right); r.pack(fill="x", pady=3)
        ttk.Label(r, text="Repeatable random seed").pack(side="left")
        ttk.Entry(r, textvariable=self.values["seed"], width=8, justify="center").pack(side="right")
        ttk.Checkbutton(right, text="Invert Y direction (only if CapCut preview indicates reverse movement)", variable=self.invert_y, command=self._invalidate).pack(anchor="w")

        fx = ttk.LabelFrame(self, text="4  Native Filters + Effects — detect and extend to audio / timeline end")
        fx.pack(fill="x", padx=15, pady=(4, 3))
        line = ttk.Frame(fx); line.pack(fill="x")
        ttk.Checkbutton(line, text="Extend detected FILTER tracks", variable=self.fx_filter_enabled,
                        command=self._invalidate).pack(side="left", padx=(0, 24))
        ttk.Checkbutton(line, text="Extend detected EFFECT tracks", variable=self.fx_effect_enabled,
                        command=self._invalidate).pack(side="left")
        ttk.Label(fx, textvariable=self.fx_duration_label).pack(anchor="w", pady=(5, 1))
        ttk.Label(fx, text="Uses existing CapCut-native FX only; effect/filter tracks with exactly one valid segment are eligible. "
                           "Multi-segment or clip-scoped FX are detected but never moved or stretched.",
                  wraplength=1140).pack(anchor="w")

        actions = ttk.Frame(self); actions.pack(fill="x", padx=15, pady=(6, 4))
        ttk.Button(actions, text="Scan + Preview changes", command=self.preview).pack(side="left", padx=(0, 8))
        self.apply_btn = ttk.Button(actions, text="Apply to CapCut draft (with backup)", command=self.apply, state="disabled")
        self.apply_btn.pack(side="left", padx=(0, 8))
        ttk.Button(actions, text="Open selected project folder", command=self.open_project).pack(side="left")
        ttk.Label(actions, text="First test on a duplicate CapCut project", foreground="#a43d27").pack(side="right")

        tabs = ttk.Notebook(self)
        tabs.pack(fill="both", expand=True, padx=15, pady=(4, 9))
        visuals = ttk.Frame(tabs)
        effects = ttk.Frame(tabs)
        tabs.add(visuals, text="5  Canvas / Image / Video Preview")
        tabs.add(effects, text="6  Detected Filters + Effects")
        cols = ("track", "clip", "kind", "name", "scale", "x", "y", "blur", "status")
        self.tree = ttk.Treeview(visuals, columns=cols, show="headings", height=9)
        labels = ["Track", "Clip", "Type", "Media file", "New scale", "New X", "New Y", "Blur", "Actions / warnings"]
        widths = [54, 46, 70, 260, 89, 85, 94, 70, 235]
        for c, lab, w in zip(cols, labels, widths):
            self.tree.heading(c, text=lab)
            self.tree.column(c, width=w, minwidth=40, stretch=c in ("name", "status"))
        scroll = ttk.Scrollbar(visuals, orient="vertical", command=self.tree.yview)
        self.tree.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        self.tree.pack(fill="both", expand=True)
        fx_cols = ("track", "segment", "kind", "name", "current", "target", "scope", "status")
        self.fx_tree = ttk.Treeview(effects, columns=fx_cols, show="headings", height=9)
        headers = ["Track", "FX #", "Type", "Native name", "Existing range", "New full range", "Scope", "Will apply / reason"]
        sizes = [55, 55, 70, 225, 150, 150, 120, 340]
        for c, lab, width in zip(fx_cols, headers, sizes):
            self.fx_tree.heading(c, text=lab)
            self.fx_tree.column(c, width=width, minwidth=40, stretch=c in ("name", "status"))
        fx_scroll = ttk.Scrollbar(effects, orient="vertical", command=self.fx_tree.yview)
        self.fx_tree.configure(yscrollcommand=fx_scroll.set)
        fx_scroll.pack(side="right", fill="y")
        self.fx_tree.pack(fill="both", expand=True)
        ttk.Label(self, textvariable=self.status, wraplength=1120).pack(fill="x", padx=15, pady=(0, 12))

    def _pair(self, parent, lo, hi, label):
        ttk.Label(parent, text=label).pack(side="right", padx=4)
        ttk.Entry(parent, textvariable=self.values[hi], width=7, justify="center").pack(side="right")
        ttk.Label(parent, text="to").pack(side="right", padx=3)
        ttk.Entry(parent, textvariable=self.values[lo], width=7, justify="center").pack(side="right")

    def _invalidate(self):
        self.cached = None
        self.apply_btn.configure(state="disabled")

    def browse_root(self):
        folder = filedialog.askdirectory(title="Choose CapCut projects root")
        if folder:
            self.root_dir.set(folder)
            self.refresh_projects()

    def browse_project(self):
        folder = filedialog.askdirectory(title="Choose one CapCut project")
        if folder:
            self.project_choice.configure(values=[folder])
            self.project.set(folder)
            self._invalidate()

    def refresh_projects(self):
        try:
            projects = [str(p) for p in list_projects(Path(self.root_dir.get()))]
            self.project_choice.configure(values=projects)
            self.project.set(projects[0] if projects else "")
            self.status.set(f"Found {len(projects)} CapCut project(s). Preview on a duplicate project recommended.")
            self._invalidate()
        except Exception as e:
            messagebox.showerror("Projects folder", str(e))

    def _options(self):
        v = {k: float(s.get()) for k, s in self.values.items() if k != "seed"}
        return Options(canvas_blur=self.blur_enabled.get(), blur_strength=BLURS[self.blur_level.get()],
                       video_scale=self.v_scale_enabled.get(), video_scale_min=v["v_scale_min"],
                       video_scale_max=v["v_scale_max"], video_position=self.v_y_enabled.get(),
                       video_y_min=v["v_y_min"], video_y_max=v["v_y_max"], video_x=v["video_x"],
                       image_scale=self.i_scale_enabled.get(), image_scale_min=v["i_scale_min"],
                       image_scale_max=v["i_scale_max"], image_position=self.i_y_enabled.get(),
                       image_y_min=v["i_y_min"], image_y_max=v["i_y_max"],
                       seed=int(self.values["seed"].get()), invert_y=self.invert_y.get(),
                       extend_filters=self.fx_filter_enabled.get(), extend_effects=self.fx_effect_enabled.get())

    def preview(self):
        try:
            self._invalidate()
            project = Path(self.project.get())
            opts = self._options()
            source, files, warnings = load_project(project)
            updated, rows, counts = create_preview(source, opts)
            for child in self.tree.get_children(): self.tree.delete(child)
            for row in rows:
                self.tree.insert("", "end", values=[row[c] for c in ("track", "clip", "kind", "name", "scale", "x", "y", "blur", "status")])
            for child in self.fx_tree.get_children(): self.fx_tree.delete(child)
            for row in counts["fx_rows"]:
                self.fx_tree.insert("", "end", values=[row[c] for c in
                                     ("track", "segment", "kind", "name", "current", "target", "scope", "status")])
            self.fx_duration_label.set(f"Target: {counts['timeline_target']}  |  "
                                       f"audio: {counts['audio_end_us']/1e6:.3f}s  |  "
                                       f"visual: {counts['visual_end_us']/1e6:.3f}s")
            self.cached = (project, opts, project_fingerprint(files))
            self.apply_btn.configure(state="normal" if updated != source else "disabled")
            self.status.set(f"Preview: {counts['videos']} videos, {counts['images']} images, "
                            f"{counts['transforms']} transforms, {counts['blurred']} blur targets, "
                            f"{counts['animated_skipped']} existing animated clips left untouched (except blur). "
                            f"Detected {counts['filters_found']} filters + {counts['effects_found']} effects; "
                            f"{counts['fx_extended']} eligible duration extension(s). "
                            + "; ".join(warnings))
        except Exception as e:
            messagebox.showerror("Preview failed", str(e))
            self.status.set(f"Preview failed: {e}")

    def apply(self):
        if not self.cached:
            return
        project, options, fingerprints = self.cached
        if not messagebox.askyesno("Apply native CapCut draft changes", "CapCut must be CLOSED.\n\n"
                                   "Edit selected project JSON after making recoverable backups?\n"
                                   "Media/audio/transitions and FX materials will be preserved; eligible "+
                                   "FX TRACK segment durations will be changed to the detected audio endpoint.\n\n"
                                   "For first test, use a disposable duplicate draft."):
            return
        try:
            result = save_project(project, options, expected=fingerprints)
            self._invalidate()
            self.status.set("Applied successfully. Backup folder: " + result["backup"] if result["saved"] else "Already matching; nothing written")
            messagebox.showinfo("CapCut visual controls", self.status.get() + "\n\nOpen CapCut and inspect the result.")
        except Exception as e:
            self._invalidate()
            self.status.set(f"Apply aborted: {e}")
            messagebox.showerror("Apply aborted — original project preserved or rolled back", str(e))

    def open_project(self):
        p = Path(self.project.get())
        if p.is_dir():
            try:
                if os.name == "nt": os.startfile(str(p))
                else: messagebox.showinfo("Project path", str(p))
            except Exception as e:
                messagebox.showerror("Open project", str(e))


if __name__ == "__main__":
    VisualApp().mainloop()

