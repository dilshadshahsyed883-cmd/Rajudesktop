"""Three-in-one Windows GUI: downloader, maker and uploader share one local library."""
from __future__ import annotations

import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, simpledialog, ttk

from .core import (APP_HOME, StudioStore, authenticate, import_existing_token, credentials, download,
                   pairs, render, retry_thumbnail, source_identity, upload)


class SongStudio(tk.Tk):
    NAV = ("Dashboard", "Audio Downloader", "Song Maker", "Song Uploader", "Settings")
    BG, PANEL, DARK, INK, MUTED, ACCENT = "#eff3f9", "#ffffff", "#122036", "#1c2b43", "#65758a", "#2563eb"

    def __init__(self):
        super().__init__()
        self.title("Song Studio | Windows")
        self.geometry("1240x800")
        self.minsize(1020, 680)
        self.configure(bg=self.BG)
        self.store = StudioStore()
        self.events = queue.Queue()
        self.running = False
        self.cancel = threading.Event()
        self.preferences = self._read_preferences()
        self.current_folder = tk.StringVar(value=self.preferences.get("folder", "Default"))
        self.store.folder(self.current_folder.get())
        self.page = ""
        self.items = {}
        self.profiles = {}
        self.nav_buttons = {}
        self._style()
        self._shell()
        self.show("Dashboard")
        self.after(140, self._events)
        self.protocol("WM_DELETE_WINDOW", self._close)

    def _read_preferences(self):
        try:
            data = json.loads((self.store.root / "settings.json").read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def _save_preferences(self):
        self.preferences["folder"] = self.current_folder.get()
        target = self.store.root / "settings.json"
        temporary = target.with_suffix(".tmp")
        temporary.write_text(json.dumps(self.preferences, indent=2), encoding="utf-8")
        os.replace(temporary, target)

    def _style(self):
        style = ttk.Style(self)
        if "clam" in style.theme_names():
            style.theme_use("clam")
        style.configure("TFrame", background=self.PANEL)
        style.configure("TLabel", background=self.PANEL, foreground=self.INK, font=("Segoe UI", 10))
        style.configure("Title.TLabel", font=("Segoe UI", 20, "bold"), foreground=self.INK)
        style.configure("Sub.TLabel", font=("Segoe UI", 10), foreground=self.MUTED)
        style.configure("TButton", font=("Segoe UI", 10), padding=(11, 8))
        style.configure("Primary.TButton", foreground="#ffffff", background=self.ACCENT)
        style.map("Primary.TButton", background=[("active", "#1d4ed8"), ("disabled", "#9daac0")])
        style.configure("TEntry", padding=7)
        style.configure("TCombobox", padding=6)
        style.configure("Treeview", font=("Segoe UI", 10), rowheight=30,
                        background="#ffffff", fieldbackground="#ffffff", foreground=self.INK)
        style.configure("Treeview.Heading", font=("Segoe UI", 10, "bold"), padding=7)
        style.configure("Horizontal.TProgressbar", background=self.ACCENT, troughcolor="#dce5f1")
        style.configure("TCheckbutton", background=self.PANEL, foreground=self.INK)

    def _shell(self):
        self.sidebar = tk.Frame(self, bg=self.DARK, width=232)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text="SONG STUDIO", font=("Segoe UI", 17, "bold"),
                 fg="#ffffff", bg=self.DARK).pack(anchor="w", padx=23, pady=(27, 5))
        tk.Label(self.sidebar, text="Desktop  •  Windows", font=("Segoe UI", 9),
                 fg="#a8bad2", bg=self.DARK).pack(anchor="w", padx=24, pady=(0, 38))
        for page in self.NAV:
            button = tk.Button(self.sidebar, text="   " + page, anchor="w", bd=0,
                               bg=self.DARK, fg="#cedaeb", activebackground="#253b5a",
                               activeforeground="#ffffff", relief="flat",
                               font=("Segoe UI", 11), cursor="hand2",
                               padx=15, pady=13, command=lambda name=page: self.show(name))
            button.pack(fill="x", padx=12, pady=3)
            self.nav_buttons[page] = button
        tk.Label(self.sidebar, text="LOCAL-FIRST  /  NO VPS CHANGES",
                 fg="#8196b0", bg=self.DARK, font=("Segoe UI", 8)).pack(
                     side="bottom", anchor="w", padx=20, pady=22)
        wrapper = tk.Frame(self, bg=self.BG)
        wrapper.pack(fill="both", expand=True)
        header = tk.Frame(wrapper, bg="#ffffff", height=73)
        header.pack(fill="x")
        header.pack_propagate(False)
        tk.Label(header, text="Song Studio", font=("Segoe UI", 15, "bold"),
                 bg="#ffffff", fg=self.DARK).pack(side="left", padx=29)
        self.status = tk.StringVar(value="Ready")
        tk.Label(header, textvariable=self.status, fg=self.MUTED,
                 bg="#ffffff", font=("Segoe UI", 10)).pack(side="right", padx=26)
        self.content = tk.Frame(wrapper, bg=self.BG)
        self.content.pack(fill="both", expand=True, padx=28, pady=24)

    def show(self, page):
        self.page = page
        for name, button in self.nav_buttons.items():
            button.configure(bg="#254477" if name == page else self.DARK,
                             fg="#ffffff" if name == page else "#cedaeb")
        for child in self.content.winfo_children():
            child.destroy()
        self.items = {}
        getattr(self, "_page_" + page.lower().replace(" ", "_"))()

    def _panel(self, parent=None):
        panel = tk.Frame(parent or self.content, bg="#ffffff", highlightbackground="#dce5ef",
                         highlightthickness=1)
        panel.pack(fill="x", pady=(0, 16))
        return panel

    def _body(self, frame):
        body = ttk.Frame(frame, padding=19)
        body.pack(fill="both", expand=True)
        return body

    def _intro(self, title, summary):
        ttk.Label(self.content, text=title, style="Title.TLabel", background=self.BG).pack(
            anchor="w", pady=(0, 6))
        ttk.Label(self.content, text=summary, style="Sub.TLabel", background=self.BG).pack(
            anchor="w", pady=(0, 20))

    def _line(self, parent, *items):
        row = ttk.Frame(parent)
        row.pack(fill="x", pady=(0, 12))
        for element in items:
            element(row)
        return row

    def _select_folder(self, parent):
        ttk.Label(parent, text="VPS-independent local folder").pack(side="left", padx=(0, 12))
        values = self.store.folders()
        self.folder_combo = ttk.Combobox(parent, textvariable=self.current_folder,
                                         values=values, state="readonly", width=27)
        self.folder_combo.pack(side="left", padx=(0, 9))
        self.folder_combo.bind("<<ComboboxSelected>>", lambda _: self._folder_change())
        ttk.Button(parent, text="+ New folder", command=self._new_folder).pack(side="left", padx=5)
        ttk.Button(parent, text="Open folder", command=self._open_folder).pack(side="left", padx=5)

    def _folder_change(self):
        self._save_preferences()
        if self.page in {"Song Maker", "Song Uploader"}:
            self.show(self.page)

    def _new_folder(self):
        name = simpledialog.askstring("Create media folder", "Folder name:", parent=self)
        if name is None:
            return
        try:
            self.store.folder(name)
            self.current_folder.set(name.strip())
            self._save_preferences()
            self.show(self.page)
        except Exception as exc:
            messagebox.showerror("Folder not created", str(exc), parent=self)

    def _open_folder(self):
        folder = self.store.folder(self.current_folder.get())
        try:
            os.startfile(folder)  # Windows Explorer; never execute arbitrary commands.
        except AttributeError:
            messagebox.showinfo("Media folder", str(folder))

    def _page_dashboard(self):
        self._intro("Your production desk", "One workspace for downloading, creating and publishing your songs.")
        panel = self._panel()
        body = self._body(panel)
        ttk.Label(body, text="01  Download  →  02  Make MP4  →  03  Upload",
                  font=("Segoe UI", 16, "bold")).pack(anchor="w", pady=(0, 16))
        ttk.Label(body, text="Audio and its original JPEG keep the same YouTube Video ID. "
                  "The finished MP4 is available to your selected channel group.",
                  style="Sub.TLabel", wraplength=750).pack(anchor="w", pady=(0, 16))
        self._line(body, lambda row: self._select_folder(row))
        self._line(body, lambda row: ttk.Button(row, text="Start downloading", style="Primary.TButton",
                  command=lambda: self.show("Audio Downloader")).pack(side="left", padx=(0, 8)),
                  lambda row: ttk.Button(row, text="Open Song Maker",
                  command=lambda: self.show("Song Maker")).pack(side="left", padx=8),
                  lambda row: ttk.Button(row, text="Open Uploader",
                  command=lambda: self.show("Song Uploader")).pack(side="left", padx=8))
        profiles = len(self.store.profiles())
        channels = len(self.store.channels())
        uploads = len([r for r in self.store.ledger() if r["state"] == "uploaded"])
        small = self._panel()
        area = self._body(small)
        ttk.Label(area, text=f"Connected channels: {channels}    Saved profiles: {profiles}    "
                  f"Upload receipts: {uploads}").pack(anchor="w")

    def _page_audio_downloader(self):
        self._intro("Audio Downloader", "Reuse the working yt-dlp engine. Download an MP3 with its exact original VideoID.jpg.")
        panel = self._panel()
        body = self._body(panel)
        self._line(body, lambda row: self._select_folder(row))
        ttk.Label(body, text="YouTube video URLs (one per line)").pack(anchor="w", pady=(0, 6))
        self.urls = tk.Text(body, height=6, font=("Consolas", 11), relief="solid",
                            bd=1, wrap="none", highlightthickness=0)
        self.urls.pack(fill="x", pady=(0, 13))
        self.auto_render = tk.BooleanVar(value=False)
        self._line(body, lambda row: ttk.Checkbutton(row, text="Auto-render matched audio + JPEG after download",
                  variable=self.auto_render).pack(side="left"))
        self._line(body, lambda row: ttk.Button(row, text="Download matching pairs",
                  style="Primary.TButton", command=self._download).pack(side="left"),
                  lambda row: ttk.Button(row, text="Cancel current job", command=self.cancel.set).pack(
                      side="left", padx=12))
        self.progress = ttk.Progressbar(body, orient="horizontal", mode="determinate", maximum=100)
        self.progress.pack(fill="x", pady=(5, 7))
        self.log = tk.Text(body, height=9, font=("Consolas", 9), state="disabled",
                           bg="#f7f9fd", relief="flat")
        self.log.pack(fill="both", expand=True)

    def _download(self):
        urls = [u.strip() for u in self.urls.get("1.0", "end").splitlines() if u.strip()]
        if not urls:
            messagebox.showwarning("Missing URLs", "Enter at least one YouTube URL.")
            return
        folder = self.store.folder(self.current_folder.get())
        render_after = self.auto_render.get()
        def worker():
            for url in dict.fromkeys(urls):
                if self.cancel.is_set():
                    break
                try:
                    self._log("Downloading " + url)
                    audio = download(url, folder, lambda n: self.events.put(("progress", n)), self.cancel)
                    self._log("Downloaded " + audio.name + " + matching JPG")
                    if render_after:
                        image = audio.with_suffix(".jpg")
                        video = folder / "renders" / (audio.stem + ".mp4")
                        if not video.exists():
                            render(image, audio, video, cancelled=self.cancel)
                        self._log("Rendered " + video.name)
                except Exception as exc:
                    self._log("Download failed: " + str(exc))
            self._log("Download queue finished")
        self._start(worker)

    def _page_song_maker(self):
        self._intro("Song Maker", "Create H.264/AAC MP4s from matched audio + images without touching original source files.")
        panel = self._panel()
        body = self._body(panel)
        self._line(body, lambda row: self._select_folder(row))
        self.resolution = tk.StringVar(value=self.preferences.get("resolution", "1080p"))
        self.fit = tk.StringVar(value=self.preferences.get("fit", "Fit"))
        self.quality = tk.StringVar(value=self.preferences.get("quality", "Balanced"))
        self._line(body, lambda row: ttk.Label(row, text="Size").pack(side="left", padx=(0, 7)),
                   lambda row: ttk.Combobox(row, textvariable=self.resolution, state="readonly",
                       values=["1080p", "720p", "9:16"], width=10).pack(side="left", padx=(0, 17)),
                   lambda row: ttk.Label(row, text="Canvas").pack(side="left", padx=(0, 7)),
                   lambda row: ttk.Combobox(row, textvariable=self.fit, state="readonly",
                       values=["Fit", "Blur"], width=10).pack(side="left", padx=(0, 17)),
                   lambda row: ttk.Label(row, text="Quality").pack(side="left", padx=(0, 7)),
                   lambda row: ttk.Combobox(row, textvariable=self.quality, state="readonly",
                       values=["High", "Balanced", "Compact"], width=12).pack(side="left"))
        self.maker_list = ttk.Treeview(body, columns=("audio", "image", "state"),
                                       show="headings", height=10, selectmode="extended")
        for key, label, width in [("audio", "Audio", 240), ("image", "Image", 220),
                                  ("state", "MP4 status", 160)]:
            self.maker_list.heading(key, text=label)
            self.maker_list.column(key, width=width)
        self.maker_list.pack(fill="both", expand=True, pady=(4, 11))
        self._line(body, lambda row: ttk.Button(row, text="Refresh pairs",
                  command=self._refresh_pairs).pack(side="left"),
                  lambda row: ttk.Button(row, text="Render selected", style="Primary.TButton",
                  command=lambda: self._render_selected(False)).pack(side="left", padx=9),
                  lambda row: ttk.Button(row, text="Render all new",
                  command=lambda: self._render_selected(True)).pack(side="left", padx=5),
                  lambda row: ttk.Button(row, text="Cancel", command=self.cancel.set).pack(
                      side="left", padx=10))
        self._refresh_pairs()

    def _refresh_pairs(self):
        folder = self.store.folder(self.current_folder.get())
        self.song_pairs = pairs(folder)
        self.maker_list.delete(*self.maker_list.get_children())
        for n, item in enumerate(self.song_pairs):
            target = folder / "renders" / (item["audio"].stem + ".mp4")
            self.maker_list.insert("", "end", iid=str(n),
               values=(item["audio"].name, item["image"].name,
                       "Rendered" if target.exists() else "Ready"))

    def _render_selected(self, all_new):
        folder = self.store.folder(self.current_folder.get())
        indices = ([i for i, item in enumerate(self.song_pairs)
                    if not (folder / "renders" / (item["audio"].stem + ".mp4")).exists()]
                   if all_new else [int(x) for x in self.maker_list.selection()])
        if not indices:
            messagebox.showinfo("No pairs", "Select matched pairs or choose Render all new.")
            return
        options = self.resolution.get(), self.fit.get(), self.quality.get()
        self.preferences.update(zip(("resolution", "fit", "quality"), options))
        self._save_preferences()
        songs = [self.song_pairs[i] for i in indices]
        def worker():
            for item in songs:
                if self.cancel.is_set():
                    break
                target = folder / "renders" / (item["audio"].stem + ".mp4")
                try:
                    self._log("Rendering " + target.name)
                    render(item["image"], item["audio"], target, *options, cancelled=self.cancel)
                    self._log("Ready: " + str(target))
                except Exception as exc:
                    self._log("Render failed for " + item["name"] + ": " + str(exc))
            self.events.put(("refresh", "Song Maker"))
        self._start(worker)

    def _page_song_uploader(self):
        self._intro("Song Uploader", "Connect your channels, manage group profiles and review upload receipts.")
        tabs = ttk.Notebook(self.content)
        tabs.pack(fill="both", expand=True)
        channel_page = ttk.Frame(tabs, padding=4)
        profile_page = ttk.Frame(tabs, padding=4)
        history_page = ttk.Frame(tabs, padding=4)
        tabs.add(profile_page, text="  Profiles & Upload  ")
        tabs.add(channel_page, text="  Channels & Groups  ")
        tabs.add(history_page, text="  Upload History  ")
        pane = self._panel(channel_page)
        body = self._body(pane)
        self._line(body, lambda row: ttk.Button(row, text="+ Connect channel (OAuth)",
                     style="Primary.TButton", command=self._connect).pack(side="left"),
                   lambda row: ttk.Button(row, text="Import PC token JSON",
                     command=self._import_token).pack(side="left", padx=10))
        self.channels_list = ttk.Treeview(body, columns=("name", "group", "id"),
                                          show="headings", height=4, selectmode="extended")
        for key, caption, width in [("name", "Channel", 200), ("group", "Group", 180),
                                     ("id", "YouTube Channel ID", 290)]:
            self.channels_list.heading(key, text=caption)
            self.channels_list.column(key, width=width)
        self.channels_list.pack(fill="x", pady=(0, 9))
        self.group_name = tk.StringVar(value="Default")
        self._line(body, lambda row: ttk.Label(row, text="Assign selected channel(s) to group").pack(
                      side="left", padx=(0, 8)),
                   lambda row: ttk.Entry(row, textvariable=self.group_name, width=24).pack(side="left"),
                   lambda row: ttk.Button(row, text="Assign", command=self._assign_group).pack(
                       side="left", padx=8))
        self._refresh_channels()
        pane = self._panel(profile_page)
        body = self._body(pane)
        ttk.Label(body, text="Uploader profile", font=("Segoe UI", 12, "bold")).pack(
            anchor="w", pady=(0, 12))
        self.profile_name = tk.StringVar()
        self.profile_group = tk.StringVar(value="Default")
        self.profile_folder = tk.StringVar(value=self.current_folder.get())
        self.profile_privacy = tk.StringVar(value="private")
        self.profile_category = tk.StringVar(value="10")
        self.profile_title = tk.StringVar(value="{filename}")
        self._line(body, lambda row: ttk.Label(row, text="Profile").pack(side="left", padx=(0, 7)),
                   lambda row: ttk.Entry(row, textvariable=self.profile_name, width=20).pack(
                       side="left", padx=(0, 16)),
                   lambda row: ttk.Label(row, text="Group").pack(side="left", padx=(0, 7)),
                   lambda row: self._group_widget(row),
                   lambda row: ttk.Label(row, text="Folder").pack(side="left", padx=(17, 7)),
                   lambda row: self._folder_widget(row))
        self._line(body, lambda row: ttk.Label(row, text="Privacy").pack(side="left", padx=(0, 7)),
                   lambda row: ttk.Combobox(row, textvariable=self.profile_privacy,
                       values=["private", "unlisted", "public"], state="readonly",
                       width=12).pack(side="left", padx=(0, 17)),
                   lambda row: ttk.Label(row, text="Category ID").pack(side="left", padx=(0, 7)),
                   lambda row: ttk.Entry(row, textvariable=self.profile_category,
                       width=7).pack(side="left", padx=(0, 16)),
                   lambda row: ttk.Label(row, text="Title template").pack(side="left", padx=(0, 7)),
                   lambda row: ttk.Entry(row, textvariable=self.profile_title,
                       width=28).pack(side="left"))
        ttk.Label(body, text="Description  •  {filename} inserts source stem; "
                  "the source JPEG is used unchanged for thumbnails.",
                  style="Sub.TLabel").pack(anchor="w")
        self.profile_description = tk.Text(body, height=3, relief="solid", bd=1)
        self.profile_description.pack(fill="x", pady=(5, 9))
        self._line(body, lambda row: ttk.Button(row, text="Save profile",
                   style="Primary.TButton", command=self._save_profile).pack(side="left"))
        self.profile_select = tk.StringVar()
        self._line(body, lambda row: ttk.Label(row, text="Saved profile").pack(
                    side="left", padx=(0, 8)),
                   lambda row: self._profile_widget(row),
                   lambda row: ttk.Button(row, text="Load",
                     command=self._load_profile).pack(side="left", padx=8),
                   lambda row: ttk.Button(row, text="Upload all new videos for group",
                     style="Primary.TButton", command=self._upload_profile).pack(
                         side="right", padx=8))
        self.progress = ttk.Progressbar(body, orient="horizontal", maximum=100)
        self.progress.pack(fill="x", pady=(0, 6))
        self.log = tk.Text(body, height=5, font=("Consolas", 9), state="disabled",
                           bg="#f7f9fd", relief="flat")
        self.log.pack(fill="both", expand=True)
        self._reload_profiles()
        self._upload_history(history_page)

    def _upload_history(self, parent):
        pane = self._panel(parent)
        body = self._body(pane)
        ttk.Label(body, text="Per-channel upload receipts", font=("Segoe UI", 12, "bold")).pack(
            anchor="w", pady=(0, 10))
        ttk.Label(body, text="Unknown outcomes are held for manual verification to avoid duplicate uploads. "
                  "MP4s are never automatically removed.", style="Sub.TLabel",
                  wraplength=740).pack(anchor="w", pady=(0, 12))
        self.receipt_list = ttk.Treeview(body, columns=("channel", "source", "state",
                                              "youtube_id", "thumbnail"), show="headings",
                                         height=12, selectmode="browse")
        for key, caption, width in [("channel", "Channel", 130), ("source", "Source identity", 235),
                                    ("state", "Upload status", 135), ("youtube_id", "YouTube ID", 145),
                                    ("thumbnail", "Original JPEG", 130)]:
            self.receipt_list.heading(key, text=caption)
            self.receipt_list.column(key, width=width)
        self.receipt_list.pack(fill="both", expand=True, pady=(0, 12))
        self.receipt_rows = {}
        for index, record in enumerate(self.store.ledger()):
            key = str(index)
            self.receipt_rows[key] = record
            self.receipt_list.insert("", "end", iid=key,
                values=(record["channel_id"], record["identity"], record["state"],
                        record["youtube_id"], "Applied" if record["thumbnail_done"] else "Pending"))
        ttk.Button(body, text="Retry JPEG on confirmed upload",
                   command=self._retry_thumbnail).pack(anchor="w")

    def _retry_thumbnail(self):
        selection = self.receipt_list.selection()
        if not selection:
            messagebox.showinfo("Choose receipt", "Select an uploaded video with a pending thumbnail.")
            return
        row = self.receipt_rows[selection[0]]
        if row["state"] != "uploaded" or not row["youtube_id"] or row["thumbnail_done"]:
            messagebox.showinfo("No retry", "Only uploaded videos with a pending JPEG can be updated.")
            return
        image_name = filedialog.askopenfilename(
            title="Choose original matching JPEG", filetypes=[("JPEG files", "*.jpg")], parent=self)
        if not image_name:
            return
        image = Path(image_name)
        if row["identity"].startswith("videoid:") and image.stem != row["identity"].split(":", 1)[1]:
            messagebox.showerror("Mismatch", "Original JPG filename does not match the YouTube source Video ID.")
            return
        channel = next((x for x in self.store.channels() if x["id"] == row["channel_id"]), None)
        if not channel:
            messagebox.showerror("Missing channel", "Reconnect the channel before retrying.")
            return
        def worker():
            try:
                retry_thumbnail(self.store, channel, row["identity"], image)
                self._log("Original thumbnail restored on " + row["youtube_id"])
                self.events.put(("refresh", "Song Uploader"))
            except Exception as exc:
                self._log("Thumbnail retry failed: " + str(exc))
        self._start(worker)

    def _group_widget(self, row):
        self.group_combo = ttk.Combobox(row, textvariable=self.profile_group,
                      values=self.store.groups(), width=15, state="readonly")
        self.group_combo.pack(side="left")

    def _folder_widget(self, row):
        self.profile_folder_combo = ttk.Combobox(row, textvariable=self.profile_folder,
                     values=self.store.folders(), width=17, state="readonly")
        self.profile_folder_combo.pack(side="left")

    def _profile_widget(self, row):
        self.profile_combo = ttk.Combobox(row, textvariable=self.profile_select,
                      width=25, state="readonly")
        self.profile_combo.pack(side="left")

    def _refresh_channels(self):
        self.channels_list.delete(*self.channels_list.get_children())
        for item in self.store.channels():
            self.channels_list.insert("", "end", iid=item["id"],
                         values=(item["name"], item["group_name"], item["id"]))
        if hasattr(self, "group_combo"):
            self.group_combo.configure(values=self.store.groups())

    def _connect(self):
        path = filedialog.askopenfilename(title="Select Desktop OAuth client JSON",
                filetypes=[("Google OAuth client JSON", "*.json")], parent=self)
        if not path:
            return
        def worker():
            try:
                channel_id, title, dest = authenticate(Path(path), self.store.tokens)
                self.store.add_channel(channel_id, title, dest)
                self._log("Connected " + title + " [" + channel_id + "]")
                self.events.put(("refresh", "Song Uploader"))
            except Exception as exc:
                self._log("Google OAuth failed: " + str(exc))
        self._start(worker)

    def _import_token(self):
        path = filedialog.askopenfilename(title="Choose existing authorized-user token",
                filetypes=[("Google token JSON", "*.json")], parent=self)
        if not path:
            return
        def worker():
            try:
                channel_id, title, dest = import_existing_token(Path(path), self.store.tokens)
                self.store.add_channel(channel_id, title, dest)
                self._log("Imported local token: " + title + " [" + channel_id + "]")
                self.events.put(("refresh", "Song Uploader"))
            except Exception as exc:
                self._log("Token import needs reconnection: " + str(exc))
        self._start(worker)

    def _assign_group(self):
        try:
            channels = self.channels_list.selection()
            if not channels:
                raise ValueError("Select at least one connected channel")
            for channel_id in channels:
                self.store.set_group(channel_id, self.group_name.get())
            self._refresh_channels()
        except Exception as exc:
            messagebox.showerror("Cannot assign group", str(exc))

    def _save_profile(self):
        try:
            self.store.save_profile(self.profile_name.get(), self.profile_group.get(),
                    self.profile_folder.get(), self.profile_title.get(),
                    self.profile_description.get("1.0", "end").strip(),
                    self.profile_category.get(), self.profile_privacy.get())
            self._reload_profiles()
            self.profile_select.set(self.profile_name.get())
            self.status.set("Profile saved locally")
        except Exception as exc:
            messagebox.showerror("Profile not saved", str(exc))

    def _reload_profiles(self):
        self.profiles = {r["name"]: r for r in self.store.profiles()}
        self.profile_combo.configure(values=list(self.profiles))

    def _load_profile(self):
        chosen = self.profiles.get(self.profile_select.get())
        if not chosen:
            return
        self.profile_name.set(chosen["name"])
        self.profile_group.set(chosen["group_name"])
        self.profile_folder.set(chosen["folder"])
        self.profile_title.set(chosen["title"])
        self.profile_category.set(chosen["category"])
        self.profile_privacy.set(chosen["privacy"])
        self.profile_description.delete("1.0", "end")
        self.profile_description.insert("1.0", chosen["description"])

    def _upload_profile(self):
        selected = self.profiles.get(self.profile_select.get())
        if not selected:
            messagebox.showwarning("Missing profile", "Save and select an uploader profile first.")
            return
        channels = self.store.channels(selected["group_name"])
        folder = self.store.folder(selected["folder"])
        videos = sorted((folder / "renders").glob("*.mp4"))
        if not channels or not videos:
            messagebox.showwarning("Nothing to upload", "This profile needs connected group channels and rendered MP4s.")
            return
        if not messagebox.askyesno("Confirm YouTube uploads",
              f"Upload up to {len(videos)} rendered MP4s to {len(channels)} channels "
              f"({selected['group_name']}) with {selected['privacy']} privacy?\n"
              "Existing receipts and uncertain attempts will be skipped.",
              parent=self):
            return
        def worker():
            for video in videos:
                if self.cancel.is_set():
                    break
                thumbnail = folder / (video.stem + ".jpg")
                for channel in channels:
                    if self.cancel.is_set():
                        break
                    title = (selected["title"] or "{filename}").replace("{filename}", video.stem)
                    desc = selected["description"].replace("{filename}", video.stem)
                    try:
                        video_id, thumb_ok = upload(
                            self.store, channel, video, thumbnail,
                            title, desc, selected["category"], selected["privacy"],
                            lambda x: self.events.put(("progress", x)))
                        self._log(channel["name"] + ": uploaded " + video.name +
                                  " -> " + video_id + (" + JPG" if thumb_ok else " (thumbnail pending)"))
                    except Exception as exc:
                        self._log(channel["name"] + " / " + video.name + ": " + str(exc))
            self._log("Upload batch finished. Review receipts before removing local MP4s.")
        self._start(worker)

    def _page_settings(self):
        self._intro("Settings & safety", "Local data, independent source files and upload records remain on this PC.")
        panel = self._panel()
        body = self._body(panel)
        self._line(body, lambda row: self._select_folder(row))
        for line in [("Workspace", str(self.store.media)),
                     ("App data / upload history", str(self.store.root)),
                     ("YouTube OAuth tokens", str(self.store.tokens)),
                     ("Duplicate protection", "One upload attempt per channel and source Video ID"),
                     ("Uncertain upload results", "Hold for manual verification in YouTube Studio"),
                     ("After successful upload", "MP4 and original audio/JPG remain locally until you delete them"),
                     ("Default export", "1920×1080 H.264 + AAC")]:
            self._line(body, lambda row, item=line: ttk.Label(row,
                       text=item[0] + ":   " + item[1],
                       wraplength=770, justify="left").pack(side="left"))
        ttk.Button(body, text="Open application data", command=self._open_data).pack(anchor="w")
        ttk.Label(body, text="Windows may require a verified Google OAuth app for channel access. "
                  "Song Studio does not bypass YouTube authorization or service limits.",
                  style="Sub.TLabel", wraplength=800).pack(anchor="w", pady=(14, 0))

    def _open_data(self):
        if hasattr(os, "startfile"):
            os.startfile(self.store.root)

    def _start(self, target):
        if self.running:
            messagebox.showwarning("Job in progress", "Finish or cancel the current job first.")
            return
        self.cancel.clear()
        self.running = True
        self.status.set("Working...")
        def run():
            try:
                target()
            finally:
                self.events.put(("done",))
        threading.Thread(target=run, daemon=True).start()

    def _log(self, value):
        self.events.put(("log", str(value)))

    def _events(self):
        try:
            while True:
                message = self.events.get_nowait()
                event = message[0]
                if event == "done":
                    self.running = False
                    self.status.set("Ready")
                elif event == "log":
                    if hasattr(self, "log") and self.log.winfo_exists():
                        self.log.configure(state="normal")
                        self.log.insert("end", message[1] + "\n")
                        self.log.see("end")
                        self.log.configure(state="disabled")
                    self.status.set(message[1][:85])
                elif event == "progress" and hasattr(self, "progress") and self.progress.winfo_exists():
                    self.progress["value"] = float(message[1])
                elif event == "refresh" and message[1] == self.page:
                    self.show(self.page)
        except queue.Empty:
            pass
        self.after(140, self._events)

    def _close(self):
        if self.running:
            messagebox.showwarning("Job running", "Cancel the job, then close the app.")
            return
        self.destroy()


def main():
    SongStudio().mainloop()
