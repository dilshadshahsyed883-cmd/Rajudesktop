"""Native desktop GUI for the separate Short Maker and Short Uploader."""
from __future__ import annotations

import json
import queue
import subprocess
import sys
import threading
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from tkinter import Tk, StringVar, BooleanVar, filedialog, messagebox, simpledialog, ttk
import tkinter as tk

from .core import AUDIO_EXTS, IMAGE_EXTS, RenderOptions, ROOT, Store, render_one
from . import uploader

BG, PANEL, TEXT, MUTED, ACCENT = "#111827", "#1c2736", "#f8fafc", "#a9b8c9", "#3b82f6"


class ShortStudioApp:
    def __init__(self, root: Tk):
        self.root = root
        self.root.title("Short Studio | Windows")
        self.root.geometry("1210x790")
        self.root.minsize(960, 650)
        self.store = Store()
        self.work = ThreadPoolExecutor(max_workers=1, thread_name_prefix="short-render")
        self.messages = queue.Queue()
        self.busy_upload = False
        self.images_dir = StringVar(value="")
        self.audio_files: list[Path] = []
        self.folder = StringVar(value="Default")
        self.render_seconds = StringVar(value="16")
        self.image_seconds = StringVar(value="3")
        self.output_count = StringVar(value="1")
        self.fps = StringVar(value="30")
        self.crf = StringVar(value="20")
        self.fit = StringVar(value="fill_crop")
        self.motion = StringVar(value="random")
        self.order = StringVar(value="random")
        self.group_name = StringVar()
        self.profile_name = StringVar()
        self.profile_group = StringVar()
        self.profile_folder = StringVar(value="Default")
        self.title = StringVar(value="{filename}")
        self.category = StringVar(value="22")
        self.privacy = StringVar(value="private")
        self.daily_limit = StringVar(value="4")
        self.schedule = StringVar(value="12:00")
        self.delete_after = BooleanVar(value=True)
        self.selected_profile = StringVar()
        self.log_lines = []
        self._style()
        self._build()
        self._refresh_all()
        self.root.after(250, self._drain)
        self.root.protocol("WM_DELETE_WINDOW", self._close)

    def _style(self):
        self.root.configure(bg=BG)
        style = ttk.Style()
        style.theme_use("clam")
        style.configure(".", font=("Segoe UI", 10), background=BG, foreground=TEXT)
        style.configure("TFrame", background=BG)
        style.configure("Card.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT)
        style.configure("Muted.TLabel", background=BG, foreground=MUTED)
        style.configure("Title.TLabel", font=("Segoe UI Semibold", 18), background=BG)
        style.configure("TNotebook", background=BG, borderwidth=0)
        style.configure("TNotebook.Tab", background=PANEL, foreground=MUTED, padding=(19, 11))
        style.map("TNotebook.Tab", background=[("selected", ACCENT)],
                  foreground=[("selected", "#ffffff")])
        style.configure("TButton", padding=(11, 8), background="#29384d", foreground=TEXT)
        style.map("TButton", background=[("active", ACCENT)])
        style.configure("Accent.TButton", background=ACCENT, foreground="#ffffff")
        style.configure("TEntry", fieldbackground="#ffffff", foreground="#111827", padding=5)
        style.configure("TCombobox", fieldbackground="#ffffff", foreground="#111827")
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL,
                        foreground=TEXT, rowheight=29, borderwidth=0)
        style.map("Treeview", background=[("selected", ACCENT)])
        style.configure("Treeview.Heading", background="#263448", foreground=TEXT, padding=7)
        style.configure("TCheckbutton", background=BG, foreground=TEXT)
        style.configure("TLabelframe", background=BG, foreground=TEXT)
        style.configure("TLabelframe.Label", background=BG, foreground=TEXT)

    @staticmethod
    def row(parent, pad=7):
        frame = ttk.Frame(parent)
        frame.pack(fill="x", padx=15, pady=pad)
        return frame

    @staticmethod
    def label_entry(parent, label, var, width=22):
        box = ttk.Frame(parent)
        box.pack(side="left", padx=(0, 13))
        ttk.Label(box, text=label).pack(anchor="w", pady=(0, 4))
        entry = ttk.Entry(box, textvariable=var, width=width)
        entry.pack(anchor="w")
        return entry

    @staticmethod
    def label_combo(parent, label, var, options, width=23):
        box = ttk.Frame(parent)
        box.pack(side="left", padx=(0, 13))
        ttk.Label(box, text=label).pack(anchor="w", pady=(0, 4))
        combo = ttk.Combobox(box, textvariable=var, values=options,
                             state="readonly", width=width)
        combo.pack(anchor="w")
        return combo

    def _build(self):
        header = ttk.Frame(self.root)
        header.pack(fill="x", padx=24, pady=(18, 14))
        ttk.Label(header, text="SHORT STUDIO", style="Title.TLabel").pack(side="left")
        ttk.Label(header, text="Local Windows workspace  •  Short Maker + Short Uploader",
                  style="Muted.TLabel").pack(side="right")
        self.tabs = ttk.Notebook(self.root)
        self.tabs.pack(fill="both", expand=True, padx=18, pady=6)
        panels = {}
        for title in ("Short Maker", "Render Queue", "Auto Engine", "Channels & Groups", "Upload Records", "Settings"):
            panel = ttk.Frame(self.tabs)
            self.tabs.add(panel, text=title)
            panels[title] = panel
        self._maker(panels["Short Maker"])
        self._queue(panels["Render Queue"])
        self._engine(panels["Auto Engine"])
        self._channels(panels["Channels & Groups"])
        self._records(panels["Upload Records"])
        self._settings(panels["Settings"])
        self.status = StringVar(value="Ready • Local output is private until you explicitly upload")
        ttk.Label(self.root, textvariable=self.status, style="Muted.TLabel").pack(
            fill="x", padx=26, pady=(0, 13))

    def _maker(self, page):
        ttk.Label(page, text="Create vertical 9:16 Shorts from images and audio",
                  style="Title.TLabel").pack(anchor="w", padx=16, pady=(18, 7))
        r = self.row(page)
        self.folder_combo = self.label_combo(r, "Destination folder", self.folder, self.store.folders())
        ttk.Button(r, text="+ Create Folder", command=self._new_folder).pack(side="left", padx=5, pady=(21, 0))
        ttk.Button(r, text="Delete Empty", command=self._delete_folder).pack(side="left", padx=5, pady=(21, 0))
        r = self.row(page)
        self.label_entry(r, "Images folder (PC)", self.images_dir, 75)
        ttk.Button(r, text="Browse...", command=self._browse_images).pack(side="left", pady=(21, 0))
        r = self.row(page)
        self.audio_note = StringVar(value="No audio selected (optional)")
        ttk.Label(r, textvariable=self.audio_note).pack(side="left", padx=(0, 12))
        ttk.Button(r, text="+ Add Audio", command=self._add_audio).pack(side="left")
        ttk.Button(r, text="Clear Audio", command=self._clear_audio).pack(side="left", padx=7)
        ttk.Separator(page).pack(fill="x", padx=16, pady=(12, 8))
        r = self.row(page)
        self.label_entry(r, "Video duration (sec)", self.render_seconds, 15)
        self.label_entry(r, "Image duration (sec)", self.image_seconds, 15)
        self.label_entry(r, "Output videos", self.output_count, 15)
        r = self.row(page)
        self.label_combo(r, "Image fit", self.fit, ["fill_crop", "blur", "black"])
        self.label_combo(r, "Image motion", self.motion,
                         ["random", "zoom_in", "zoom_out", "pan_lr", "pan_rl", "none"])
        self.label_combo(r, "Image order", self.order, ["random", "filename"])
        r = self.row(page)
        self.label_combo(r, "FPS", self.fps, ["24", "30", "50", "60"], 15)
        self.label_entry(r, "Video CRF", self.crf, 15)
        ttk.Label(r, text="Default resolution: 1080 × 1920", style="Muted.TLabel").pack(
            side="left", pady=(19, 0))
        r = self.row(page, 17)
        ttk.Button(r, text="Add to Render Queue", style="Accent.TButton",
                   command=self._start_render).pack(side="left")
        ttk.Button(r, text="Open Output Folder", command=self._open_folder).pack(side="left", padx=12)
        ttk.Label(page, text="Names: Folder 001_abcdef.mp4, 002_abcdef.mp4; each batch gets a unique tag.",
                  style="Muted.TLabel").pack(anchor="w", padx=16)

    def _queue(self, page):
        r = self.row(page, 17)
        ttk.Label(r, text="Render Queue", style="Title.TLabel").pack(side="left")
        ttk.Button(r, text="Refresh", command=self._refresh_jobs).pack(side="right")
        self.jobs_table = self._table(page, ("Folder", "Status", "Message", "Outputs"),
                                      (160, 120, 480, 110))

    def _engine(self, page):
        ttk.Label(page, text="Short Uploader · Group Profiles", style="Title.TLabel").pack(
            anchor="w", padx=15, pady=(14, 6))
        r = self.row(page)
        self.label_entry(r, "Profile name", self.profile_name, 22)
        self.profile_group_combo = self.label_combo(r, "Channel group", self.profile_group, [], 27)
        self.profile_folder_combo = self.label_combo(r, "Shorts folder", self.profile_folder, self.store.folders())
        r = self.row(page)
        self.label_entry(r, "Title (use {filename})", self.title, 38)
        self.label_combo(r, "Category ID", self.category, list(uploader.VIDEO_CATEGORY.values()), 14)
        self.label_combo(r, "Privacy", self.privacy, ["private", "unlisted", "public"], 14)
        r = self.row(page)
        ttk.Label(r, text="Description (saved on this PC)").pack(anchor="w")
        self.description_box = tk.Text(page, height=3, bg="#ffffff", fg="#111827",
                                       wrap="word", relief="flat", font=("Segoe UI", 10))
        self.description_box.pack(fill="x", padx=16, pady=4)
        r = self.row(page)
        self.label_entry(r, "Per-channel daily limit", self.daily_limit, 14)
        self.label_entry(r, "Schedule time (PKT)", self.schedule, 14)
        ttk.Checkbutton(r, text="Delete local MP4 after all queued channel uploads succeed",
                        variable=self.delete_after).pack(side="left", pady=(20, 0))
        r = self.row(page)
        ttk.Button(r, text="Save Group Profile", command=self._save_profile).pack(side="left")
        ttk.Label(r, text="Public = scheduled private upload; other privacy settings upload immediately",
                  style="Muted.TLabel").pack(side="left", padx=14)
        r = self.row(page)
        self.profile_select = self.label_combo(r, "Choose saved profile", self.selected_profile, [], 50)
        ttk.Button(r, text="Queue Folder Videos", command=self._queue_uploads).pack(
            side="left", padx=8, pady=(21, 0))
        ttk.Button(r, text="Start Upload Queue", style="Accent.TButton",
                   command=self._start_uploads).pack(side="left", padx=6, pady=(21, 0))
        self.profile_table = self._table(page, ("Profile", "Group", "Channels", "Folder", "Time PKT"),
                                         (210, 230, 95, 210, 105), height=5)

    def _channels(self, page):
        ttk.Label(page, text="Connected YouTube channels", style="Title.TLabel").pack(
            anchor="w", padx=15, pady=(14, 5))
        r = self.row(page)
        ttk.Button(r, text="+ Connect Channel (OAuth)", command=self._connect).pack(side="left")
        ttk.Label(r, text="Requires your own Google Cloud Desktop OAuth client JSON.",
                  style="Muted.TLabel").pack(side="left", padx=14)
        self.channels_table = self._table(page, ("Channel", "YouTube channel ID"),
                                          (330, 450), height=5)
        r = self.row(page, 14)
        self.label_entry(r, "New group name", self.group_name, 28)
        ttk.Button(r, text="Create Group from Selected Channels",
                   command=self._create_group).pack(side="left", pady=(20, 0))
        ttk.Label(page, text="Ctrl-click multiple channels above, then create a group.",
                  style="Muted.TLabel").pack(anchor="w", padx=15)
        self.groups_table = self._table(page, ("Group", "Channels"), (480, 120), height=5)

    def _records(self, page):
        r = self.row(page, 16)
        ttk.Label(r, text="YouTube Upload Records", style="Title.TLabel").pack(side="left")
        ttk.Button(r, text="Refresh", command=self._refresh_records).pack(side="right")
        self.records_table = self._table(page, ("File", "Channel", "Status", "YouTube ID", "Error"),
                                         (290, 160, 110, 170, 390), height=17)
        ttk.Label(page, text="Uncertain = request may have reached YouTube; verify manually. Never auto-retry.",
                  style="Muted.TLabel").pack(anchor="w", padx=16, pady=9)

    def _settings(self, page):
        ttk.Label(page, text="Application Settings", style="Title.TLabel").pack(anchor="w", padx=15, pady=16)
        for note in (
            "Storage: " + str(self.store.root),
            "Render: 9:16 vertical, 1080 × 1920, 30 FPS default",
            "Local folder output is available to Short Uploader by default.",
            "YouTube authentication is stored locally; no credentials are committed to GitHub.",
            "Google Drive upload is not enabled in this standalone release.",
            "VPS Short Studio and Auto Script remain completely untouched.",
        ):
            ttk.Label(page, text=note, style="Muted.TLabel").pack(anchor="w", padx=17, pady=8)
        ttk.Button(page, text="Open Application Data", command=lambda: self._open_path(self.store.root)).pack(
            anchor="w", padx=17, pady=18)

    def _table(self, page, cols, widths, height=11):
        frame = ttk.Frame(page)
        frame.pack(fill="both", expand=True, padx=15, pady=8)
        tree = ttk.Treeview(frame, columns=cols, show="headings", height=height, selectmode="extended")
        for col, width in zip(cols, widths):
            tree.heading(col, text=col)
            tree.column(col, width=width, anchor="w", minwidth=80)
        scrollbar = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        return tree

    def _call(self, fn):
        try:
            return fn()
        except Exception as exc:
            messagebox.showerror("Short Studio", str(exc))
            self._log(str(exc))

    def _log(self, line):
        self.log_lines.append(line)
        self.log_lines = self.log_lines[-200:]
        self.status.set(line[:180])

    def _new_folder(self):
        name = simpledialog.askstring("New folder", "Folder name:", parent=self.root)
        if name:
            def act():
                self.store.create_folder(name)
                self.folder.set(name.strip())
                self.profile_folder.set(name.strip())
                self._refresh_all()
            self._call(act)

    def _delete_folder(self):
        name = self.folder.get()
        if not messagebox.askyesno("Delete empty folder", f"Delete EMPTY folder {name}?"):
            return
        def act():
            self.store.delete_empty_folder(name)
            self.folder.set("Default")
            self.profile_folder.set("Default")
            self._refresh_all()
        self._call(act)

    def _browse_images(self):
        chosen = filedialog.askdirectory(title="Choose images folder")
        if chosen:
            self.images_dir.set(chosen)

    def _add_audio(self):
        selected = filedialog.askopenfilenames(title="Add music / voice files")
        for item in selected:
            p = Path(item)
            if p.suffix.lower() in AUDIO_EXTS and p not in self.audio_files:
                self.audio_files.append(p)
        self.audio_note.set(f"{len(self.audio_files)} audio file(s) selected")

    def _clear_audio(self):
        self.audio_files.clear()
        self.audio_note.set("No audio selected (optional)")

    @staticmethod
    def _open_path(path: Path):
        import os
        import subprocess
        if sys.platform == "win32":
            os.startfile(str(path))
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _open_folder(self):
        self._call(lambda: self._open_path(self.store.folder_path(self.folder.get())))

    def _start_render(self):
        def act():
            images_folder = Path(self.images_dir.get())
            if not images_folder.is_dir():
                raise ValueError("Choose a PC images folder")
            images = sorted(p for p in images_folder.rglob("*")
                            if p.is_file() and p.suffix.lower() in IMAGE_EXTS)
            if not images:
                raise ValueError("The selected folder contains no supported images")
            opt = RenderOptions(float(self.render_seconds.get()),
                                float(self.image_seconds.get()),
                                int(self.output_count.get()),
                                int(self.fps.get()), int(self.crf.get()),
                                self.fit.get(), self.motion.get(), self.order.get())
            opt.validate()
            paths = self.store.reserve_names(self.folder.get(), opt.count)
            job_id = self.store.add_job(self.folder.get(), paths)
            audios = list(self.audio_files)
            self.work.submit(self._render_worker, job_id, images, audios, paths, opt)
            self._refresh_jobs()
            self.tabs.select(1)
            self._log(f"Queued {opt.count} Short(s) in {self.folder.get()}")
        self._call(act)

    def _render_worker(self, job_id, images, audios, paths, opt):
        try:
            self.store.set_job(job_id, "running", "Rendering")
            for i, output in enumerate(paths, 1):
                render_one(images, audios, output, opt,
                           notify=lambda msg: self.messages.put(("progress", f"{i}/{len(paths)} {msg}")))
                self.messages.put(("progress", f"Rendered {output.name}"))
            self.store.set_job(job_id, "completed", f"{len(paths)} MP4 completed")
        except Exception as exc:
            self.store.set_job(job_id, "failed", str(exc)[:450])
            self.messages.put(("progress", f"Render failed: {exc}"))
        self.messages.put(("refresh", ""))

    def _refresh_jobs(self):
        self.jobs_table.delete(*self.jobs_table.get_children())
        for job in self.store.jobs():
            self.jobs_table.insert("", "end",
                values=(job["folder"], job["status"], job["message"], len(job["files"])))

    def _connect(self):
        secret = filedialog.askopenfilename(title="Google OAuth Desktop client JSON",
                                            filetypes=[("JSON", "*.json")])
        if not secret:
            return
        def worker():
            try:
                cid, name = uploader.connect_channel(self.store, secret)
                self.messages.put(("connected", name + " (" + cid + ")"))
            except Exception as exc:
                self.messages.put(("error", str(exc)))
        threading.Thread(target=worker, daemon=True).start()
        self._log("Browser OAuth started. Choose the intended YouTube channel.")

    def _create_group(self):
        def act():
            selected = self.channels_table.selection()
            ids = [self.channels_table.item(item, "values")[1] for item in selected]
            uploader.create_group(self.store, self.group_name.get(), ids)
            self.group_name.set("")
            self._refresh_all()
        self._call(act)

    def _save_profile(self):
        def act():
            groups = self._group_names()
            group_id = groups.get(self.profile_group.get())
            if not group_id:
                raise ValueError("Select a channel group")
            uploader.create_profile(
                self.store, self.profile_name.get(), group_id, self.profile_folder.get(),
                self.title.get(), self.description_box.get("1.0", "end-1c"),
                self.category.get(), self.privacy.get(), int(self.daily_limit.get()),
                self.schedule.get(), self.delete_after.get())
            self.profile_name.set("")
            self._refresh_all()
        self._call(act)

    def _profile_names(self):
        return {p["name"] + " | " + p["id"][:8]: p["id"] for p in uploader.profiles(self.store)}

    def _group_names(self):
        with self.store.db() as conn:
            return {n: key for key, n in conn.execute("SELECT id,name FROM groups ORDER BY name")}

    def _queue_uploads(self):
        def act():
            key = self._profile_names().get(self.selected_profile.get())
            if not key:
                raise ValueError("Choose a saved profile")
            count = uploader.enqueue_profile(self.store, key)
            self._refresh_records()
            self._log(f"{count} unique upload(s) queued; existing channel/file pairs skipped")
        self._call(act)

    def _start_uploads(self):
        if self.busy_upload:
            return
        if not messagebox.askyesno("Start YouTube Upload", "Start uploading queued videos to connected channels?"):
            return
        self.busy_upload = True
        def worker():
            try:
                count = uploader.upload_pending(self.store,
                            lambda msg: self.messages.put(("progress", msg)))
                self.messages.put(("progress", f"Upload run finished: {count} successful"))
            except Exception as exc:
                self.messages.put(("error", str(exc)))
            finally:
                self.messages.put(("upload_done", ""))
        threading.Thread(target=worker, daemon=True).start()

    def _refresh_records(self):
        self.records_table.delete(*self.records_table.get_children())
        for item in uploader.upload_rows(self.store):
            self.records_table.insert("", "end", values=(
                Path(item["file_path"]).name, item["channel_id"], item["state"],
                item["youtube_id"], item["error"][:140]))

    def _refresh_all(self):
        folders = self.store.folders()
        self.folder_combo.configure(values=folders)
        self.profile_folder_combo.configure(values=folders)
        groups = self._group_names()
        self.profile_group_combo.configure(values=list(groups))
        if self.profile_group.get() not in groups and groups:
            self.profile_group.set(next(iter(groups)))
        names = self._profile_names()
        self.profile_select.configure(values=list(names))
        if self.selected_profile.get() not in names and names:
            self.selected_profile.set(next(iter(names)))
        self.channels_table.delete(*self.channels_table.get_children())
        with self.store.db() as conn:
            for cid, name in conn.execute("SELECT id,label FROM channels ORDER BY label"):
                self.channels_table.insert("", "end", values=(name, cid))
            self.groups_table.delete(*self.groups_table.get_children())
            for group, count in conn.execute("""SELECT g.name,COUNT(m.channel_id) FROM groups g
                LEFT JOIN memberships m ON g.id=m.group_id GROUP BY g.id ORDER BY g.name"""):
                self.groups_table.insert("", "end", values=(group, count))
        self.profile_table.delete(*self.profile_table.get_children())
        for p in uploader.profiles(self.store):
            self.profile_table.insert("", "end", values=(
                p["name"], p["group_name"], p["channels"], p["folder"], p["schedule_pkt"]))
        self._refresh_jobs()
        self._refresh_records()

    def _drain(self):
        try:
            while True:
                kind, value = self.messages.get_nowait()
                if kind == "progress":
                    self._log(value)
                elif kind == "connected":
                    self._refresh_all()
                    self._log("Connected: " + value)
                elif kind == "upload_done":
                    self.busy_upload = False
                    self._refresh_records()
                elif kind == "refresh":
                    self._refresh_jobs()
                elif kind == "error":
                    self._log("Error: " + value)
                    messagebox.showerror("Short Studio", value)
        except queue.Empty:
            pass
        self.root.after(300, self._drain)

    def _close(self):
        if any(j["status"] in ("running", "queued") for j in self.store.jobs()) or self.busy_upload:
            if not messagebox.askyesno("Jobs running", "Jobs are active; close anyway?"):
                return
        self.root.destroy()


def main():
    app = Tk()
    ShortStudioApp(app)
    app.mainloop()
