"""Kokoro-inspired native Windows Edge TTS desktop GUI."""
from __future__ import annotations

import asyncio
from pathlib import Path
import threading
from uuid import uuid4

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal, QStandardPaths
from PySide6.QtGui import QDesktopServices
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QFrame,
    QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QInputDialog, QPlainTextEdit, QPushButton, QSlider, QSplitter, QStackedWidget,
    QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget, QAbstractItemView,
)

from .core import english_voice, safe_title
from .engine import generate_preview, list_english_voices, render_job, to_wav
from .store import Store

DARK = {
    "bg": "#0F1727", "panel": "#19283D", "input": "#1D3049", "text": "#EAF1FF",
    "muted": "#9CB2D0", "accent": "#2461D8", "border": "#354F6E",
    "hover": "#294567", "navy": "#10284A", "sidebar": "#15263F",
    "nav_active": "#234978",
}
LIGHT = {
    "bg": "#F2F6FC", "panel": "#FFFFFF", "input": "#FAFCFF", "text": "#12315B",
    "muted": "#536D92", "accent": "#1756D9", "border": "#D3E0F0",
    "hover": "#E6F0FF", "navy": "#102A4B", "sidebar": "#EDF4FF",
    "nav_active": "#DDEAFF",
}


def stylesheet(theme: str) -> str:
    """Navy header, pale workspace, white cards, blue actions."""
    c = DARK if theme == "Dark" else LIGHT
    return """
    QMainWindow, QWidget#root, QWidget#workspace, QStackedWidget {
      background: %(bg)s; color: %(text)s;
    }
    QWidget { color: %(text)s; font-family: 'Segoe UI'; font-size: 13px; }
    QFrame#header { background: %(navy)s; border: 0; border-radius: 11px; }
    QFrame#header QLabel { color: #FFFFFF; background: transparent; }
    QFrame#header QPushButton {
      background: #193F70; color: #FFFFFF; border: 1px solid #40658D;
    }
    QFrame#header QPushButton:hover { background: #27558B; }
    QFrame#sidebar {
      background: %(sidebar)s; border: 1px solid %(border)s; border-radius: 13px;
    }
    QFrame#sidebar QLabel { background: transparent; }
    QFrame#card {
      background: %(panel)s; border: 1px solid %(border)s; border-radius: 12px;
    }
    QFrame#card QLabel, QFrame#card QCheckBox {
      background: transparent; border: 0;
    }
    QLineEdit, QPlainTextEdit, QListWidget, QTableWidget, QComboBox {
      background: %(input)s; color: %(text)s; border: 1px solid %(border)s;
      border-radius: 7px; padding: 8px; selection-background-color: %(accent)s;
    }
    QPlainTextEdit { padding: 12px; }
    QPushButton {
      background: %(panel)s; color: %(text)s; border: 1px solid %(border)s;
      border-radius: 7px; padding: 9px 12px; font-weight: 600;
    }
    QPushButton:hover { background: %(hover)s; }
    QPushButton#primary { background: %(accent)s; color: #FFFFFF; border: 0; }
    QPushButton#primary:hover { background: #0B47BB; }
    QPushButton#nav {
      text-align: left; border: 0; background: transparent; padding: 12px;
      color: %(text)s;
    }
    QPushButton#nav:hover { background: %(hover)s; }
    QPushButton#nav:checked {
      background: %(nav_active)s; color: %(accent)s; border-left: 4px solid %(accent)s;
    }
    QSlider::groove:horizontal { height: 5px; background: %(border)s; border-radius: 2px; }
    QSlider::handle:horizontal {
      background: %(accent)s; width: 15px; margin: -5px 0; border-radius: 7px;
    }
    QTableWidget {
      gridline-color: %(border)s; alternate-background-color: %(panel)s;
    }
    QHeaderView::section {
      background: %(sidebar)s; color: %(text)s; padding: 8px; border: 0;
    }
    QScrollBar:vertical { background: %(bg)s; width: 10px; }
    QScrollBar::handle:vertical { background: %(border)s; border-radius: 5px; }
    QLabel#muted { color: %(muted)s; }
    """ % c


def default_output_folder() -> Path:
    """Honor OS-managed Documents path including Windows OneDrive redirection."""
    documents = QStandardPaths.writableLocation(
        QStandardPaths.StandardLocation.DocumentsLocation
    )
    return Path(documents or str(Path.home() / "Documents")) / "EdgeVoiceStudio"


def card() -> tuple[QFrame, QVBoxLayout]:
    outer = QFrame()
    outer.setObjectName("card")
    layout = QVBoxLayout(outer)
    layout.setContentsMargins(18, 18, 18, 18)
    layout.setSpacing(12)
    return outer, layout


def button(label: str, callback, primary=False) -> QPushButton:
    b = QPushButton(label)
    if primary:
        b.setObjectName("primary")
    b.clicked.connect(callback)
    return b


class NetworkTask(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, kind: str, args=()):
        super().__init__()
        self.kind = kind
        self.args = args

    def run(self):
        try:
            if self.kind == "voices":
                outcome = asyncio.run(list_english_voices())
            elif self.kind == "preview":
                outcome = asyncio.run(generate_preview(*self.args))
            elif self.kind == "wav":
                mp3, target = self.args
                to_wav(mp3, target)
                outcome = target
            else:
                raise ValueError("Unknown task")
            self.succeeded.emit(outcome)
        except Exception as exc:
            self.failed.emit(str(exc))


class QueueWorker(QThread):
    changed = Signal()
    note = Signal(str)

    def __init__(self, store: Store, output: Path, cache: Path):
        super().__init__()
        self.store, self.output, self.cache = store, output, cache
        self.stop_flag = threading.Event()

    def stop(self):
        self.stop_flag.set()

    def run(self):
        while not self.stop_flag.is_set():
            job = self.store.next_queued()
            if not job:
                return
            try:
                asyncio.run(render_job(
                    self.store, job["id"], self.output, self.cache,
                    stopped=self.stop_flag.is_set,
                    progress=lambda _done, _total: self.changed.emit()))
                self.note.emit("Completed: " + job["title"])
            except Exception as exc:
                self.note.emit(job["title"] + ": " + str(exc)[:170])
            self.changed.emit()


class StudioWindow(QMainWindow):
    PAGES = ["Voice Studio", "Favorites", "Queue", "Batch Studio", "Audio Library", "Settings"]

    def __init__(self):
        super().__init__()
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        self.data = Path(base or str(Path.home() / ".edge-voice-studio"))
        self.store = Store(self.data / "edge-voice.db")
        self.voices: list[dict] = self.store.get_setting("voices_cache", [])
        self.selected_voice = self.store.get_setting("selected_voice", "en-US-AndrewNeural")
        self.queue_worker: QueueWorker | None = None
        self.tasks: list[NetworkTask] = []
        self._queue_snapshot = None
        self._library_snapshot = None
        self._closing = False
        self.setWindowTitle("Edge Voice Studio — Rajudesktop")
        self.setMinimumSize(1050, 700)
        self.resize(1450, 890)
        self.output = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.output)
        self.output.setVolume(0.85)
        self.player.positionChanged.connect(self._playback_moved)
        self.player.durationChanged.connect(self._playback_duration)
        self.setStyleSheet(stylesheet(self.store.get_setting("theme", "Navy Light")))
        # Apply the requested screenshot palette once, including to existing installs.
        if not self.store.get_setting("navy_light_v11_applied", False):
            self.store.set_setting("theme", "Navy Light")
            self.store.set_setting("navy_light_v11_applied", True)
        self.setStyleSheet(stylesheet(self.store.get_setting("theme", "Navy Light")))
        self._build()
        self._show_page(0)
        self._filter_voices()
        self._refresh_presets()
        self._refresh_queue()
        self._refresh_library()
        self.poll = QTimer(self)
        self.poll.timeout.connect(self._poll)
        self.poll.start(1200)
        self.autosave = QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(800)
        self.autosave.timeout.connect(
            lambda: self.store.set_setting("draft_script", self.script.toPlainText()))
        self.script.setPlainText(self.store.get_setting("draft_script", ""))
        self._update_count()
        QTimer.singleShot(150, self.refresh_voices)
        QTimer.singleShot(400, self._start_queue)

    def _build(self):
        root = QWidget()
        self.setCentralWidget(root)
        root.setObjectName("root")
        outer = QVBoxLayout(root)
        outer.setContentsMargins(10, 10, 10, 10)
        outer.setSpacing(11)

        header = QFrame()
        header.setObjectName("header")
        header.setFixedHeight(74)
        header_row = QHBoxLayout(header)
        header_row.setContentsMargins(20, 9, 15, 9)
        headline = QVBoxLayout()
        app_title = QLabel("◆  Edge Voice Studio")
        app_title.setStyleSheet("font-size: 21px; font-weight: 750;")
        tagline = QLabel("Natural English voices  ·  Narration  ·  Batch processing")
        tagline.setStyleSheet("color: #D4E2F4; font-size: 11px;")
        headline.addWidget(app_title)
        headline.addWidget(tagline)
        header_row.addLayout(headline, 1)
        header_row.addWidget(button("New Script", self.new_script))
        header_row.addWidget(button("Open TXT", self.import_script))
        header_row.addWidget(button("Save TXT", self.save_script))
        header_row.addWidget(button("Settings", lambda: self._show_page(5)))
        outer.addWidget(header)

        main = QHBoxLayout()
        main.setSpacing(12)
        outer.addLayout(main, 1)
        nav, nav_layout = card()
        nav.setObjectName("sidebar")
        nav.setFixedWidth(202)
        nav_layout.addWidget(QLabel("CONTROL ROOM"))
        lbl = QLabel("ENGLISH VOICE TOOLS")
        lbl.setObjectName("muted")
        nav_layout.addWidget(lbl)
        nav_layout.addSpacing(12)
        self.nav_buttons = []
        glyphs = ["◉", "★", "☷", "▦", "♫", "⚙"]
        for i, name in enumerate(self.PAGES):
            btn = button(f"{glyphs[i]}   {name}", lambda _=False, index=i: self._show_page(index))
            btn.setObjectName("nav")
            btn.setCheckable(True)
            btn.setMinimumHeight(46)
            nav_layout.addWidget(btn)
            self.nav_buttons.append(btn)
        nav_layout.addStretch()
        nav_layout.addWidget(QLabel("Internet required for synthesis"))
        main.addWidget(nav)

        self.stack = QStackedWidget()
        main.addWidget(self.stack, 1)
        self._voice_page()
        self._favorites_page()
        self._queue_page()
        self._batch_page()
        self._library_page()
        self._settings_page()

    def _page(self, title: str, subtitle: str) -> tuple[QWidget, QVBoxLayout]:
        p = QWidget()
        lay = QVBoxLayout(p)
        lay.setSpacing(14)
        title_label = QLabel(title)
        title_label.setStyleSheet("font-size: 24px; font-weight: 700;")
        lay.addWidget(title_label)
        sub = QLabel(subtitle)
        sub.setObjectName("muted")
        lay.addWidget(sub)
        self.stack.addWidget(p)
        return p, lay

    def _show_page(self, index: int):
        self.stack.setCurrentIndex(index)
        for i, btn in enumerate(self.nav_buttons):
            btn.setChecked(i == index)
        if index == 1:
            self._refresh_favorites()
        if index == 4:
            self._refresh_library()

    def _voice_page(self):
        _, page = self._page("Voice Studio", "Create natural English narration using your saved settings.")
        top = QSplitter(Qt.Orientation.Horizontal)
        top.setChildrenCollapsible(False)
        left, ll = card()
        ll.addWidget(QLabel("NARRATION SCRIPT"))
        self.title_input = QLineEdit()
        self.title_input.setPlaceholderText("Project title")
        self.title_input.setText("My Narration")
        ll.addWidget(self.title_input)
        self.script = QPlainTextEdit()
        self.script.setPlaceholderText("Paste English text or import a .txt file...")
        self.script.setMinimumHeight(230)
        self.script.textChanged.connect(self._script_changed)
        ll.addWidget(self.script, 1)
        self.counter = QLabel("0 words · 0 characters")
        self.counter.setObjectName("muted")
        ll.addWidget(self.counter)
        actions = QHBoxLayout()
        actions.addWidget(button("Import TXT", self.import_script))
        actions.addWidget(button("▶ Preview", self.preview_voice))
        actions.addWidget(button("+ Add to Queue", self.enqueue_current, True))
        ll.addLayout(actions)
        top.addWidget(left)

        right, rl = card()
        rl.addWidget(QLabel("ENGLISH VOICES"))
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search voice or accent...")
        self.search.textChanged.connect(self._filter_voices)
        rl.addWidget(self.search)
        filter_row = QHBoxLayout()
        self.gender = QComboBox()
        self.gender.addItems(["Any gender", "Male", "Female"])
        self.gender.currentIndexChanged.connect(self._filter_voices)
        self.accent = QComboBox()
        self.accent.addItems(["All accents", "US", "GB", "AU", "IN", "CA", "Other"])
        self.accent.currentIndexChanged.connect(self._filter_voices)
        filter_row.addWidget(self.gender)
        filter_row.addWidget(self.accent)
        rl.addLayout(filter_row)
        self.only_stars = QCheckBox("Favorites only")
        self.only_stars.toggled.connect(self._filter_voices)
        rl.addWidget(self.only_stars)
        self.voice_list = QListWidget()
        self.voice_list.currentItemChanged.connect(self._voice_selected)
        rl.addWidget(self.voice_list, 1)
        row = QHBoxLayout()
        row.addWidget(button("★ Toggle Favorite", self.toggle_favorite))
        row.addWidget(button("Refresh Voices", self.refresh_voices))
        rl.addLayout(row)
        self.selected_label = QLabel("Selected: Andrew (en-US)")
        rl.addWidget(self.selected_label)
        top.addWidget(right)
        top.setSizes([630, 470])
        page.addWidget(top, 1)

        settings_card, settings = card()
        settings.addWidget(QLabel("VOICE CONTROLS & PRESETS"))
        self.rate_slider, self.rate_value = self._add_slider(settings, "Speed", -50, 50, "%")
        self.pitch_slider, self.pitch_value = self._add_slider(settings, "Pitch", -100, 100, "Hz")
        self.volume_slider, self.volume_value = self._add_slider(settings, "Volume", -50, 50, "%")
        row = QHBoxLayout()
        self.presets = QComboBox()
        self.presets.addItem("Saved presets...")
        self.presets.currentTextChanged.connect(self.load_preset)
        self.preset_name = QLineEdit()
        self.preset_name.setPlaceholderText("Preset name")
        row.addWidget(self.presets)
        row.addWidget(self.preset_name)
        row.addWidget(button("Save Preset", self.save_preset))
        row.addWidget(button("Reset Controls", self.reset_sliders))
        settings.addLayout(row)
        self.subtitles = QCheckBox("Export SRT subtitles when word timings are available")
        self.subtitles.setChecked(True)
        settings.addWidget(self.subtitles)
        page.addWidget(settings_card)
        self.rate_slider.setValue(0)
        self.pitch_slider.setValue(0)
        self.volume_slider.setValue(0)

    def _add_slider(self, parent: QVBoxLayout, title: str, lo: int, hi: int, unit: str):
        row = QHBoxLayout()
        name = QLabel(title)
        name.setFixedWidth(72)
        slider = QSlider(Qt.Orientation.Horizontal)
        slider.setRange(lo, hi)
        output = QLabel("0" + unit)
        output.setFixedWidth(60)
        slider.valueChanged.connect(
            lambda value: output.setText(f"{value:+d}{unit}" if value else "0" + unit))
        row.addWidget(name)
        row.addWidget(slider, 1)
        row.addWidget(output)
        parent.addLayout(row)
        return slider, output

    def _favorites_page(self):
        _, page = self._page("Favorite Voices", "Your starred English voices, available across sessions.")
        c, lay = card()
        self.favorite_list = QListWidget()
        self.favorite_list.itemDoubleClicked.connect(self._favorite_open)
        lay.addWidget(self.favorite_list)
        lay.addWidget(button("Open Voice in Studio", self._favorite_open))
        page.addWidget(c, 1)

    def _queue_page(self):
        _, page = self._page("Generation Queue", "Jobs are saved locally; interrupted work resumes by chunk.")
        c, lay = card()
        self.queue_table = QTableWidget(0, 5)
        self.queue_table.setHorizontalHeaderLabels(["Title", "Voice", "Progress", "Status", "Output / Error"])
        self.queue_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.queue_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.queue_table.setColumnWidth(0, 220)
        self.queue_table.setColumnWidth(1, 180)
        self.queue_table.setColumnWidth(2, 95)
        self.queue_table.setColumnWidth(3, 95)
        self.queue_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.queue_table, 1)
        controls = QHBoxLayout()
        for label, method in [
            ("Pause", lambda: self.set_job_status("paused")),
            ("Resume / Retry", lambda: self.set_job_status("queued")),
            ("Cancel", lambda: self.set_job_status("cancelled")),
            ("Remove Row", self.remove_job),
            ("Open Output", self.open_job_output),
        ]:
            controls.addWidget(button(label, method))
        lay.addLayout(controls)
        page.addWidget(c, 1)

    def _batch_page(self):
        _, page = self._page("Batch Studio", "Import multiple TXT files. Each script becomes its own independent job.")
        c, lay = card()
        lay.addWidget(QLabel("MULTI-FILE GENERATION"))
        info = QLabel("Each imported script uses the voice and controls currently selected in Voice Studio. "
                      "Empty files are skipped. The queue renders jobs one at a time.")
        info.setWordWrap(True)
        lay.addWidget(info)
        lay.addWidget(button("+ Import TXT Scripts to Queue", self.import_batch, True))
        self.batch_info = QLabel("No batch submitted in this session.")
        self.batch_info.setObjectName("muted")
        lay.addWidget(self.batch_info)
        lay.addStretch()
        page.addWidget(c, 1)

    def _library_page(self):
        _, page = self._page("Audio Library", "Play finished voiceovers or open the verified output folder.")
        c, lay = card()
        self.library_search = QLineEdit()
        self.library_search.setPlaceholderText("Search completed narrations...")
        self.library_search.textChanged.connect(self._refresh_library)
        lay.addWidget(self.library_search)
        self.audio_table = QTableWidget(0, 3)
        self.audio_table.setHorizontalHeaderLabels(["Project", "Voice", "File"])
        self.audio_table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.audio_table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.audio_table.setColumnWidth(0, 220)
        self.audio_table.setColumnWidth(1, 180)
        self.audio_table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(self.audio_table, 1)
        row = QHBoxLayout()
        for label, handler in [
            ("▶ Play", self.play_audio),
            ("Ⅱ Pause", self.player.pause),
            ("■ Stop", self.player.stop),
            ("Rename", self.rename_audio),
            ("Delete", self.delete_audio),
            ("Export WAV", self.export_wav),
            ("Open Folder", self.open_audio_folder),
            ("Refresh", self._refresh_library),
        ]:
            row.addWidget(button(label, handler))
        lay.addLayout(row)
        self.playback_seek = QSlider(Qt.Orientation.Horizontal)
        self.playback_seek.setRange(0, 0)
        self.playback_seek.sliderReleased.connect(
            lambda: self.player.setPosition(self.playback_seek.value()))
        lay.addWidget(self.playback_seek)
        page.addWidget(c, 1)

    def _settings_page(self):
        _, page = self._page("Settings", "Choose storage locations and appearance. No cloud account required.")
        c, lay = card()
        self.output_path = QLineEdit(self.store.get_setting(
            "output_folder", str(default_output_folder())))
        self.cache_path = QLineEdit(self.store.get_setting(
            "cache_folder", str(self.data / "chunk_cache")))
        for name, edit in [("Output folder", self.output_path), ("Chunk cache", self.cache_path)]:
            lay.addWidget(QLabel(name))
            row = QHBoxLayout()
            row.addWidget(edit, 1)
            row.addWidget(button("Browse", lambda _=False, e=edit: self.select_folder(e)))
            lay.addLayout(row)
        folder_help = QLabel(
            "MP3, WAV and SRT output goes into the folder above. "
            "It remains your default after restarting, until you change it and click Save Settings."
        )
        folder_help.setObjectName("muted")
        folder_help.setWordWrap(True)
        lay.addWidget(folder_help)
        lay.addWidget(button(
            "Restore Documents Default",
            lambda: self.output_path.setText(str(default_output_folder())),
        ))
        lay.addWidget(QLabel("Theme"))
        self.theme = QComboBox()
        self.theme.addItems(["Navy Light", "Dark"])
        self.theme.setCurrentText(self.store.get_setting("theme", "Navy Light"))
        lay.addWidget(self.theme)
        lay.addWidget(button("Save Settings", self.save_settings, True))
        warning = QLabel("Edge TTS needs an internet connection. All scripts, favorites, "
                         "queue metadata and rendered files stay on this PC.")
        warning.setWordWrap(True)
        warning.setObjectName("muted")
        lay.addWidget(warning)
        lay.addStretch()
        page.addWidget(c, 1)

    def _script_changed(self):
        self._update_count()
        self.autosave.start()

    def _update_count(self):
        text = self.script.toPlainText()
        self.counter.setText(f"{len(text.split()):,} words · {len(text):,} characters")

    def new_script(self):
        self.script.clear()
        self.title_input.setText("My Narration")
        self._show_page(0)

    def save_script(self):
        path, _ = QFileDialog.getSaveFileName(
            self, "Save narration text", str(default_output_folder() / "narration.txt"),
            "Text (*.txt)")
        if not path:
            return
        try:
            Path(path).write_text(self.script.toPlainText(), encoding="utf-8")
            self._message("Narration script saved: " + path)
        except OSError as exc:
            self._error(str(exc))

    def import_script(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import TXT script", "", "Text (*.txt)")
        if path:
            try:
                self.script.setPlainText(Path(path).read_text(encoding="utf-8-sig"))
                self.title_input.setText(Path(path).stem)
            except Exception as exc:
                self._error(str(exc))

    def refresh_voices(self):
        task = NetworkTask("voices")
        task.succeeded.connect(self._voices_received)
        task.failed.connect(lambda msg: self._message("Voice service unavailable: " + msg))
        self._run_task(task)

    def _run_task(self, task: NetworkTask):
        self.tasks.append(task)
        task.finished.connect(lambda t=task: self.tasks.remove(t) if t in self.tasks else None)
        task.start()

    def _voices_received(self, voices):
        if not voices:
            self._message("No English neural voices returned by the service")
            return
        self.voices = voices
        self.store.set_setting("voices_cache", voices)
        if self.selected_voice not in {v["name"] for v in voices}:
            self.selected_voice = voices[0]["name"]
        self._filter_voices()
        self._refresh_favorites()
        self._message(f"Loaded {len(voices)} English voices")

    def _filter_voices(self, *_args):
        if not hasattr(self, "voice_list"):
            return
        phrase = self.search.text().lower().strip()
        gender = self.gender.currentText()
        accent = self.accent.currentText()
        stars = self.store.favorites()
        self.voice_list.blockSignals(True)
        self.voice_list.clear()
        for voice in self.voices:
            if phrase and phrase not in (voice["name"] + " " + voice["locale"]).lower():
                continue
            if gender != "Any gender" and voice["gender"] != gender:
                continue
            if accent != "All accents":
                country = voice["locale"].split("-")[-1].upper()
                if accent == "Other" and country in {"US", "GB", "AU", "IN", "CA"}:
                    continue
                if accent != "Other" and country != accent:
                    continue
            if self.only_stars.isChecked() and voice["name"] not in stars:
                continue
            item = QListWidgetItem(
                ("★  " if voice["name"] in stars else "☆  ") +
                f"{voice['display']}   ·   {voice['locale']}   ·   {voice['gender']}")
            item.setData(Qt.ItemDataRole.UserRole, voice["name"])
            self.voice_list.addItem(item)
            if voice["name"] == self.selected_voice:
                self.voice_list.setCurrentItem(item)
        self.voice_list.blockSignals(False)
        self.selected_label.setText("Selected: " + self.selected_voice)

    def _voice_selected(self, current, _previous):
        if current is not None:
            self.selected_voice = current.data(Qt.ItemDataRole.UserRole)
            self.store.set_setting("selected_voice", self.selected_voice)
            self.selected_label.setText("Selected: " + self.selected_voice)

    def toggle_favorite(self):
        if not english_voice(self.selected_voice):
            self._error("Select an English voice")
            return
        self.store.toggle_favorite(self.selected_voice)
        self._filter_voices()
        self._refresh_favorites()

    def _refresh_favorites(self):
        self.favorite_list.clear()
        stars = self.store.favorites()
        for voice in self.voices:
            if voice["name"] in stars:
                item = QListWidgetItem(f"★  {voice['display']}  ·  {voice['locale']}  ·  {voice['gender']}")
                item.setData(Qt.ItemDataRole.UserRole, voice["name"])
                self.favorite_list.addItem(item)

    def _favorite_open(self, *_args):
        item = self.favorite_list.currentItem()
        if item:
            self.selected_voice = item.data(Qt.ItemDataRole.UserRole)
            self.store.set_setting("selected_voice", self.selected_voice)
            self.only_stars.setChecked(False)
            self.search.clear()
            self.gender.setCurrentIndex(0)
            self.accent.setCurrentIndex(0)
            self._filter_voices()
            self._show_page(0)

    def control_values(self):
        return self.rate_slider.value(), self.pitch_slider.value(), self.volume_slider.value()

    def reset_sliders(self):
        for slider in (self.rate_slider, self.pitch_slider, self.volume_slider):
            slider.setValue(0)

    def save_preset(self):
        name = self.preset_name.text().strip()
        if not name:
            self._error("Enter a preset name")
            return
        rate, pitch, volume = self.control_values()
        self.store.save_preset(name, {
            "voice": self.selected_voice, "rate": rate, "pitch": pitch, "volume": volume})
        self._refresh_presets()
        self.presets.setCurrentText(name)
        self._message("Preset saved: " + name)

    def _refresh_presets(self):
        self.presets.blockSignals(True)
        self.presets.clear()
        self.presets.addItem("Saved presets...")
        self.presets.addItems(sorted(self.store.get_setting("presets", {})))
        self.presets.blockSignals(False)

    def load_preset(self, name):
        entry = self.store.get_setting("presets", {}).get(name)
        if not entry:
            return
        self.selected_voice = entry["voice"]
        self.rate_slider.setValue(int(entry["rate"]))
        self.pitch_slider.setValue(int(entry["pitch"]))
        self.volume_slider.setValue(int(entry["volume"]))
        self._filter_voices()

    def enqueue_current(self):
        script = self.script.toPlainText()
        try:
            rate, pitch, volume = self.control_values()
            self.store.add_job(self.title_input.text() or "Narration", script,
                               self.selected_voice, rate, pitch, volume,
                               self.subtitles.isChecked())
        except Exception as exc:
            self._error(str(exc))
            return
        self._refresh_queue()
        self._start_queue()
        self._message("Narration added to queue")

    def preview_voice(self):
        text = self.script.toPlainText().strip()
        if not text:
            self._error("Enter text to preview")
            return
        target = self.data / "previews" / (uuid4().hex + ".mp3")
        rate, pitch, volume = self.control_values()
        task = NetworkTask("preview", (text, self.selected_voice, rate, pitch, volume, target))
        task.succeeded.connect(lambda path: self._play_path(Path(path)))
        task.failed.connect(self._error)
        self._run_task(task)
        self._message("Generating short voice preview...")

    def import_batch(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import narration scripts", "", "Text (*.txt)")
        added, errors = 0, []
        rate, pitch, volume = self.control_values()
        for raw in paths:
            p = Path(raw)
            try:
                self.store.add_job(p.stem, p.read_text(encoding="utf-8-sig"),
                                   self.selected_voice, rate, pitch, volume,
                                   self.subtitles.isChecked())
                added += 1
            except Exception as exc:
                errors.append(p.name + ": " + str(exc))
        self.batch_info.setText(f"{added} files queued" +
                                (f" · {len(errors)} skipped" if errors else ""))
        self._refresh_queue()
        if added:
            self._start_queue()
        if errors:
            self._error("\n".join(errors[:8]))

    def _start_queue(self):
        if self._closing or (self.queue_worker and self.queue_worker.isRunning()):
            return
        if not self.store.next_queued():
            return
        # The queue uses SAVED settings only; uncommitted field edits cannot redirect output.
        worker = QueueWorker(
            self.store,
            Path(self.store.get_setting("output_folder", str(default_output_folder()))).expanduser(),
            Path(self.store.get_setting("cache_folder", str(self.data / "chunk_cache"))).expanduser(),
        )
        self.queue_worker = worker
        worker.changed.connect(self._refresh_queue)
        worker.note.connect(self._message)
        worker.finished.connect(self._worker_finished)
        worker.start()

    def _worker_finished(self):
        self._refresh_queue()
        self._refresh_library()
        if self._closing:
            QTimer.singleShot(0, self.close)
        else:
            QTimer.singleShot(100, self._start_queue)

    def _poll(self):
        self._refresh_queue()
        self._refresh_library()

    def _selected_job(self):
        row = self.queue_table.currentRow()
        if row < 0:
            return None
        item = self.queue_table.item(row, 0)
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _refresh_queue(self):
        jobs = self.store.all_jobs()
        snapshot = tuple((j["id"], j["completed"], j["total"], j["status"],
                          j["output"], j["error"]) for j in jobs)
        if snapshot == self._queue_snapshot:
            return
        self._queue_snapshot = snapshot
        selected = self._selected_job()
        self.queue_table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            cells = [
                job["title"], job["voice"].replace("Neural", ""),
                f"{job['completed']}/{job['total']}", job["status"],
                job["output"] or job["error"][:200]]
            for col, value in enumerate(cells):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, job["id"])
                self.queue_table.setItem(row, col, item)
                if selected == job["id"]:
                    self.queue_table.selectRow(row)

    def set_job_status(self, status):
        id_ = self._selected_job()
        if not id_:
            self._message("Select a queue row first")
            return
        job = self.store.get(id_)
        if job["status"] == "done" and status != "cancelled":
            self._message("Completed jobs cannot be resumed")
            return
        if job["status"] == "done":
            self._message("Finished outputs are preserved. Use Remove Row if needed.")
            return
        self.store.set_status(id_, status)
        self._refresh_queue()
        if status == "queued":
            self._start_queue()

    def remove_job(self):
        id_ = self._selected_job()
        if not id_:
            return
        try:
            self.store.delete_job(id_)
            self._refresh_queue()
            self._message("Queue row removed; rendered media left intact")
        except Exception as exc:
            self._error(str(exc))

    def open_job_output(self):
        id_ = self._selected_job()
        if id_:
            path = Path(self.store.get(id_)["output"])
            if path.is_file():
                QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))
            else:
                self._message("This job has no finished output yet")

    def _refresh_library(self):
        phrase = self.library_search.text().strip().lower()
        jobs = [j for j in self.store.all_jobs()
                if j["status"] == "done" and Path(j["output"]).is_file()
                and (not phrase or phrase in (j["title"] + " " + j["voice"]).lower())]
        snapshot = tuple((j["id"], j["output"], j["title"]) for j in jobs)
        if snapshot == self._library_snapshot:
            return
        self._library_snapshot = snapshot
        self.audio_table.setRowCount(len(jobs))
        for row, job in enumerate(jobs):
            for col, value in enumerate((job["title"], job["voice"], job["output"])):
                item = QTableWidgetItem(str(value))
                if col == 0:
                    item.setData(Qt.ItemDataRole.UserRole, job["id"])
                self.audio_table.setItem(row, col, item)

    def _selected_audio(self):
        row = self.audio_table.currentRow()
        item = self.audio_table.item(row, 0) if row >= 0 else None
        return Path(self.store.get(item.data(Qt.ItemDataRole.UserRole))["output"]) if item else None

    def _play_path(self, path: Path):
        if not path.is_file():
            self._error("Audio file is missing")
            return
        self.player.setSource(QUrl.fromLocalFile(str(path)))
        self.player.play()
        self._message("Playing: " + path.name)

    def play_audio(self):
        path = self._selected_audio()
        if path:
            self._play_path(path)

    def _playback_moved(self, position):
        if hasattr(self, "playback_seek") and not self.playback_seek.isSliderDown():
            self.playback_seek.setValue(int(position))

    def _playback_duration(self, duration):
        if hasattr(self, "playback_seek"):
            self.playback_seek.setMaximum(max(0, int(duration)))

    def rename_audio(self):
        path = self._selected_audio()
        if not path or not path.is_file():
            self._error("Choose a finished narration")
            return
        row = self.audio_table.currentRow()
        item = self.audio_table.item(row, 0)
        job_id = item.data(Qt.ItemDataRole.UserRole)
        current = self.store.get(job_id)
        title, accepted = QInputDialog.getText(
            self, "Rename narration", "New title:", text=current["title"])
        if not accepted or not title.strip():
            return
        new_path = path.with_name(safe_title(title) + "-" + job_id[:8] + ".mp3")
        moves = [(path.with_suffix(ext), new_path.with_suffix(ext))
                 for ext in (".mp3", ".wav", ".srt") if path.with_suffix(ext).exists()]
        if any(dest.exists() and dest != source for source, dest in moves):
            self._error("A file with that name already exists")
            return
        moved = []
        try:
            for source, dest in moves:
                source.rename(dest)
                moved.append((source, dest))
            self.store.rename_finished(job_id, title, str(new_path))
        except Exception as exc:
            for source, dest in reversed(moved):
                try:
                    dest.rename(source)
                except OSError:
                    pass
            self._error("Rename failed: " + str(exc))
            return
        self._library_snapshot = None
        self._queue_snapshot = None
        self._refresh_library()
        self._refresh_queue()
        self._message("Narration renamed")

    def delete_audio(self):
        path = self._selected_audio()
        if not path or not path.is_file():
            self._error("Select a completed narration")
            return
        result = QMessageBox.question(
            self, "Delete narration",
            "Permanently delete this generated MP3 and matching WAV/SRT files? "
            "Unrelated source files will not be touched.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if result != QMessageBox.StandardButton.Yes:
            return
        row = self.audio_table.currentRow()
        job_id = self.audio_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        self.player.stop()
        try:
            for ext in (".mp3", ".wav", ".srt"):
                path.with_suffix(ext).unlink(missing_ok=True)
            self.store.delete_job(job_id)
            self._queue_snapshot = None
            self._library_snapshot = None
            self._refresh_queue()
            self._refresh_library()
            self._message("Generated narration deleted")
        except Exception as exc:
            self._error(str(exc))

    def export_wav(self):
        path = self._selected_audio()
        if path is None or not path.is_file():
            self._error("Choose a finished narration")
            return
        target = path.with_suffix(".wav")
        task = NetworkTask("wav", (path, target))
        task.succeeded.connect(lambda p: self._message("WAV saved: " + str(p)))
        task.failed.connect(self._error)
        self._run_task(task)
        self._message("Converting WAV in the background...")

    def open_audio_folder(self):
        path = self._selected_audio()
        if path and path.exists():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(path.parent)))

    def select_folder(self, edit: QLineEdit):
        location = QFileDialog.getExistingDirectory(
            self, "Choose folder", edit.text() or str(Path.home()))
        if location:
            edit.setText(location)

    def save_settings(self):
        output, cache = Path(self.output_path.text()).expanduser(), Path(self.cache_path.text()).expanduser()
        try:
            output.mkdir(parents=True, exist_ok=True)
            cache.mkdir(parents=True, exist_ok=True)
            if output.resolve() == cache.resolve():
                raise ValueError("Choose separate output and chunk cache directories")
            self.store.set_setting("output_folder", str(output))
            self.store.set_setting("cache_folder", str(cache))
            self.store.set_setting("theme", self.theme.currentText())
            self.setStyleSheet(stylesheet(self.theme.currentText()))
            self._message("Saved output folder: " + str(output))
        except Exception as exc:
            self._error(str(exc))

    def _message(self, msg: str):
        self.statusBar().showMessage(msg, 12000)

    def _error(self, msg: str):
        QMessageBox.warning(self, "Edge Voice Studio", msg[:1200])

    def closeEvent(self, event):
        self.store.set_setting("draft_script", self.script.toPlainText())
        if self.queue_worker and self.queue_worker.isRunning():
            self._closing = True
            self.queue_worker.stop()
            self._message("Pausing generation safely before closing...")
            event.ignore()
        elif any(task.isRunning() for task in self.tasks):
            self._closing = True
            self._message("Finishing network task before closing...")
            QTimer.singleShot(300, self.close)
            event.ignore()
        else:
            self.player.stop()
            event.accept()


def main() -> int:
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("Edge Voice Studio")
    app.setOrganizationName("Rajudesktop")
    app.setStyle("Fusion")
    window = StudioWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
