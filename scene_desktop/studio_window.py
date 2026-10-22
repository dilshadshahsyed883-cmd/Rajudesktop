"""Unified Desktop Studio UI: indexed library + director + graphical multitrack edit."""
from __future__ import annotations
from dataclasses import asdict
from pathlib import Path
import copy
import json
import tempfile
import threading
import subprocess
import uuid

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal
from PySide6.QtGui import QAction, QColor, QBrush, QPen, QPixmap, QIcon
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGraphicsItem, QGraphicsRectItem, QGraphicsScene, QGraphicsSimpleTextItem,
    QGraphicsView, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSlider, QSplitter,
    QTabWidget, QVBoxLayout, QWidget, QAbstractItemView,
)
from PySide6.QtCore import QStandardPaths

from .library import MediaLibrary
from .media import duration_ms, ffmpeg_path
from .timeline import StudioProject, Item, EditHistory, save, load, VISUAL_TRACKS, AUDIO_TRACKS
from .planner import create_scene_plan, match_media, append_scenes, Scene
from .captions import import_srt, export_srt
from .resources import probe
from .effects import COLOR_LOOKS, MOTIONS, GRAINS, TRANSITIONS
from .studio_render import render

SCALE = 0.035       # 35 px per second
LEFT = 135
ROW = 56
TOP = 28
PALETTE = {
    "video": "#277db0", "overlay": "#7257b2", "image": "#945bb7",
    "captions": "#b88439", "narration": "#277964", "music": "#396b8a",
    "sfx": "#8d6350", "audio": "#338b78",
}


def human(ms: int) -> str:
    seconds = max(0, ms) // 1000
    return f"{seconds // 60:02}:{seconds % 60:02}"


def app_directory() -> Path:
    value = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
    root = Path(value or str(Path.home() / ".scene-desktop-studio"))
    root.mkdir(parents=True, exist_ok=True)
    return root


class ThumbnailThread(QThread):
    ready = Signal(str, str)

    def __init__(self, library: MediaLibrary, records: list[dict]):
        super().__init__()
        self.library = library
        self.records = records

    def run(self):
        for record in self.records[:40]:
            try:
                self.ready.emit(record["id"], str(self.library.thumbnail(record["id"])))
            except (OSError, RuntimeError, subprocess.SubprocessError):
                continue


class RenderThread(QThread):
    done = Signal(str)
    failed = Signal(str)
    progress = Signal(int, str)

    def __init__(self, project: StudioProject, dest: Path, cache: Path,
                 preview: bool = False, window=None):
        super().__init__()
        self.snapshot = StudioProject.from_dict(project.to_dict())
        self.dest, self.cache = dest, cache
        self.preview, self.window = preview, window
        self.stop = threading.Event()

    def run(self):
        try:
            result = render(self.snapshot, self.dest, cache_dir=self.cache,
                            preview=self.preview, window=self.window,
                            progress=lambda n, s: self.progress.emit(n, s),
                            stop=self.stop)
            self.done.emit(str(result))
        except Exception as exc:
            self.failed.emit(str(exc))


class ClipBlock(QGraphicsRectItem):
    def __init__(self, item: Item, track_index: int, editor: "StudioWindow"):
        self.ref = item.id
        self.editor = editor
        self.drag_from = (item.track_id, item.start_ms)
        super().__init__(0, 0, max(10, item.duration_ms * SCALE), ROW - 12)
        self.setPos(LEFT + item.start_ms * SCALE, TOP + track_index * ROW + 4)
        tr = editor.project.track(item.track_id)
        color = PALETTE.get(tr.kind, "#506070")
        self.setBrush(QBrush(QColor(color)))
        self.setPen(QPen(QColor("#b5d6ee"), 2 if editor.selected_id == item.id else 0.6))
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        name = item.text[:35] if item.kind == "text" else Path(item.asset).name[:32]
        label = QGraphicsSimpleTextItem(name or "(caption)", self)
        label.setBrush(QBrush(QColor("#ffffff")))
        label.setPos(5, 10)
        label.setAcceptedMouseButtons(Qt.MouseButton.NoButton)

    def mousePressEvent(self, event):
        self.editor.selected_id = self.ref
        self.editor.show_inspector()
        super().mousePressEvent(event)

    def mouseReleaseEvent(self, event):
        super().mouseReleaseEvent(event)
        if not self.editor.project.items:
            return
        x = max(0, round((self.pos().x() - LEFT) / SCALE / 100) * 100)
        track_idx = max(0, min(len(self.editor.project.tracks) - 1,
                               round((self.pos().y() - TOP - 4) / ROW)))
        target = self.editor.project.tracks[track_idx].id
        old_item = self.editor.project.item(self.ref)
        if (old_item.track_id, old_item.start_ms) != (target, x):
            try:
                self.editor.history.checkpoint()
                self.editor.project.move(self.ref, target, x)
                self.editor.mark_changed()
            except Exception as exc:
                # Invalid moves (including locked/incompatible tracks) are rejected.
                self.editor.history.undo()
                self.editor.project = self.editor.history.project
                self.editor.statusBar().showMessage(str(exc))
        self.editor.redraw_timeline()


class TimelineView(QGraphicsView):
    def __init__(self, editor: "StudioWindow"):
        super().__init__()
        self.editor = editor
        self.canvas = QGraphicsScene(self)
        self.setScene(self.canvas)
        self.setRenderHints(self.renderHints())
        self.setDragMode(QGraphicsView.DragMode.RubberBandDrag)
        self.setMinimumHeight(260)
        self.setStyleSheet("background:#171e28; border:1px solid #354256;")
        self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)

    def redraw(self):
        self.canvas.clear()
        project = self.editor.project
        length = max(700, LEFT + project.duration_ms * SCALE + 250)
        rows = len(project.tracks)
        self.canvas.setSceneRect(0, 0, length, TOP + rows * ROW + 22)
        for second in range(0, project.duration_ms // 1000 + 15, 5):
            x = LEFT + second * 1000 * SCALE
            ruler = self.canvas.addSimpleText(f"{second}s")
            ruler.setBrush(QBrush(QColor("#8896ad")))
            ruler.setPos(x, 2)
            self.canvas.addLine(x, TOP, x, TOP + rows * ROW, QPen(QColor("#29374b"), 1))
        for idx, track in enumerate(project.tracks):
            y = TOP + idx * ROW
            rect = self.canvas.addRect(0, y, length, ROW - 2,
                                       QPen(QColor("#334456"), 1),
                                       QBrush(QColor("#202b38" if idx % 2 == 0 else "#253144")))
            name = self.canvas.addSimpleText(("🔒 " if track.locked else "") + track.name[:20])
            name.setBrush(QBrush(QColor("#e5e7eb")))
            name.setPos(4, y + 15)
        for item in project.items:
            try:
                index = next(i for i,t in enumerate(project.tracks) if t.id == item.track_id)
                self.canvas.addItem(ClipBlock(item, index, self.editor))
            except StopIteration:
                continue
        playhead_x = LEFT + self.editor.playhead_ms * SCALE
        self.canvas.addLine(playhead_x, 0, playhead_x, TOP + rows * ROW,
                            QPen(QColor("#f5c454"), 2))


class StudioWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = StudioProject()
        self.history = EditHistory(self.project)
        self.project_path: Path | None = None
        self.selected_id = ""
        self.playhead_ms = 0
        self.scenes: list[Scene] = []
        self.scene_page = 0
        self.library = MediaLibrary(app_directory() / "catalog.sqlite3")
        self.project.media_db = str(self.library.database)
        self.thumbnail_thread: ThumbnailThread | None = None
        self.worker: RenderThread | None = None
        self.preview_pending = False
        self._preview_output = None
        self.setWindowTitle("Scene Desktop Studio — Unified Editor")
        self.resize(1530, 940)
        self.setMinimumSize(1020, 650)
        self.audio = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self._preview_start = 0
        self.player.positionChanged.connect(self._on_preview_position)
        self.player.mediaStatusChanged.connect(self._on_media_status)
        self.build_ui()
        for label, key, callback in [
            ("Save", "Ctrl+S", self.save_project), ("Undo", "Ctrl+Z", self.undo),
            ("Redo", "Ctrl+Shift+Z", self.redo), ("Export", "Ctrl+E", self.export_video),
            ("Play", "Space", self.toggle_preview),
        ]:
            action = QAction(label, self)
            action.setShortcut(key)
            action.triggered.connect(callback)
            self.addAction(action)
        self.preview_timer = QTimer(self)
        self.preview_timer.setSingleShot(True)
        self.preview_timer.setInterval(650)
        self.preview_timer.timeout.connect(self.render_preview)
        self.save_timer = QTimer(self)
        self.save_timer.setSingleShot(True)
        self.save_timer.setInterval(1800)
        self.save_timer.timeout.connect(self.autosave)
        self.refresh_library()
        self.redraw_timeline()

    def build_ui(self):
        self.setStyleSheet("""
            QMainWindow,QWidget{background:#181d26;color:#e5eaf2;font-size:12px}
            QPushButton{background:#334457;border:1px solid #4c6075;border-radius:5px;padding:8px}
            QPushButton:hover{background:#435e75}
            QListWidget,QPlainTextEdit,QLineEdit,QComboBox,QDoubleSpinBox{background:#222c39;color:#fff;border:1px solid #405064;padding:3px}
            QTabWidget::pane{border:1px solid #405064}
            QTabBar::tab{background:#253144;color:#d2dceb;padding:8px}
            QTabBar::tab:selected{background:#365c86}
        """)
        main = QWidget()
        self.setCentralWidget(main)
        outer = QVBoxLayout(main)
        toolrow = QHBoxLayout()
        for title, action in [("New", self.new_project), ("Open", self.open_project),
                              ("Save", self.save_project), ("Recover", self.recover_autosave),
                              ("Relink Media", self.relink_media),
                              ("PC Resources", self.show_resources), ("Undo", self.undo),
                              ("Redo", self.redo), ("Export MP4", self.export_video)]:
            b = QPushButton(title)
            b.clicked.connect(action)
            toolrow.addWidget(b)
        self.size_selector = QComboBox()
        self.size_selector.addItems(["1080p 16:9", "1080p 9:16", "720p 16:9", "720p 9:16"])
        self.size_selector.currentIndexChanged.connect(self.set_output_format)
        toolrow.addWidget(self.size_selector)
        outer.addLayout(toolrow)
        frame = QSplitter(Qt.Orientation.Horizontal)
        outer.addWidget(frame, 1)
        self.left = QTabWidget()
        frame.addWidget(self.left)
        self.build_library_panel()
        self.build_scene_panel()
        center = QSplitter(Qt.Orientation.Vertical)
        frame.addWidget(center)
        preview_panel = QWidget()
        preview_column = QVBoxLayout(preview_panel)
        preview_column.addWidget(QLabel("<b>COMPOSITED LIVE PREVIEW</b> — cached FFmpeg scene renderer"))
        self.video = QVideoWidget()
        self.video.setMinimumHeight(175)
        self.player.setVideoOutput(self.video)
        preview_column.addWidget(self.video, 1)
        controls = QHBoxLayout()
        play = QPushButton("▶ / ❚❚")
        play.clicked.connect(self.toggle_preview)
        controls.addWidget(play)
        controls.addWidget(QLabel("Playhead"))
        self.seek = QSlider(Qt.Orientation.Horizontal)
        self.seek.setRange(0, 0)
        self.seek.sliderReleased.connect(self.scrub)
        controls.addWidget(self.seek, 1)
        self.clock = QLabel("00:00 / 00:00")
        controls.addWidget(self.clock)
        refresh = QPushButton("Refresh Preview")
        refresh.clicked.connect(self.render_preview)
        controls.addWidget(refresh)
        preview_column.addLayout(controls)
        center.addWidget(preview_panel)
        timeline_panel = QWidget()
        tl = QVBoxLayout(timeline_panel)
        tl.addWidget(QLabel("<b>MULTI-TRACK TIMELINE</b> — drag items to reposition or switch compatible tracks"))
        self.timeline = TimelineView(self)
        tl.addWidget(self.timeline, 1)
        commands = QHBoxLayout()
        for title, action in [("Add selected media", self.add_selected_media),
                              ("Split", self.split_item), ("Delete", self.delete_item),
                              ("Duplicate", self.duplicate_item),
                              ("Track Controls", self.track_controls),
                              ("Add caption", self.add_caption),
                              ("Import SRT", self.import_subtitles),
                              ("Export SRT", self.export_subtitles)]:
            b = QPushButton(title)
            b.clicked.connect(action)
            commands.addWidget(b)
        cancel = QPushButton("Cancel Render / Preview")
        cancel.clicked.connect(self.cancel_render)
        commands.addWidget(cancel)
        tl.addLayout(commands)
        zoom_row = QHBoxLayout()
        zoom_row.addWidget(QLabel("Timeline zoom"))
        self.timeline_zoom = QSlider(Qt.Orientation.Horizontal)
        self.timeline_zoom.setRange(20, 180)
        self.timeline_zoom.setValue(35)
        self.timeline_zoom.valueChanged.connect(self.set_timeline_zoom)
        zoom_row.addWidget(self.timeline_zoom)
        tl.addLayout(zoom_row)
        center.addWidget(timeline_panel)
        center.setSizes([380, 410])
        right = QWidget()
        frame.addWidget(right)
        self.build_inspector(right)
        frame.setSizes([320, 910, 300])
        self.status = QLabel("MVP: local projects; no VPS/YouTube/Drive integration. All edits non-destructive.")
        outer.addWidget(self.status)
        self.statusBar().showMessage("Ready")

    def build_library_panel(self):
        widget = QWidget()
        lay = QVBoxLayout(widget)
        top = QHBoxLayout()
        for title, cb in [("Import Files", self.import_files), ("Import Folder", self.import_folder), ("Add Audio", self.add_audio)]:
            b = QPushButton(title)
            b.clicked.connect(cb)
            top.addWidget(b)
        lay.addLayout(top)
        self.media_search = QLineEdit()
        self.media_search.setPlaceholderText("Search by filename or tags")
        self.media_search.textChanged.connect(self.refresh_library)
        lay.addWidget(self.media_search)
        self.status_filter = QComboBox()
        self.status_filter.addItems(["All media", "Approved", "Candidate", "Rejected"])
        self.status_filter.currentIndexChanged.connect(self.refresh_library)
        lay.addWidget(self.status_filter)
        self.media_list = QListWidget()
        self.media_list.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.media_list.itemDoubleClicked.connect(lambda _item: self.add_selected_media())
        self.media_list.itemSelectionChanged.connect(self.refresh_counts)
        lay.addWidget(self.media_list, 1)
        flags = QHBoxLayout()
        for title, value in [("Approve", "approved"), ("Reject", "rejected"), ("Candidate", "candidate")]:
            b = QPushButton(title)
            b.clicked.connect(lambda _checked=False, s=value: self.change_media_status(s))
            flags.addWidget(b)
        lay.addLayout(flags)
        tags = QPushButton("Edit Tags")
        tags.clicked.connect(self.edit_media_tags)
        lay.addWidget(tags)
        dup = QPushButton("Find Exact Duplicates")
        dup.clicked.connect(self.show_duplicates)
        lay.addWidget(dup)
        self.counts = QLabel()
        lay.addWidget(self.counts)
        self.left.addTab(widget, "Media Library")

    def build_scene_panel(self):
        widget = QWidget()
        lay = QVBoxLayout(widget)
        lay.addWidget(QLabel("<b>SCENE DIRECTOR</b>"))
        self.script = QPlainTextEdit()
        self.script.setPlaceholderText("Paste narration script or paragraphs here...")
        lay.addWidget(self.script)
        script_import = QPushButton("Import Script TXT")
        script_import.clicked.connect(self.import_script)
        lay.addWidget(script_import)
        policy = QHBoxLayout()
        self.source_policy = QComboBox()
        self.source_policy.addItems(["Local First", "Local Only", "Alternate Image/Video", "Video Only", "Image Only"])
        policy.addWidget(self.source_policy)
        self.reuse = QCheckBox("Allow media reuse")
        policy.addWidget(self.reuse)
        lay.addLayout(policy)
        self.scene_auto_approve = QCheckBox("Auto-approve all matched scenes (optional)")
        lay.addWidget(self.scene_auto_approve)
        for title, cb in [("1. Generate timed scene plan", self.plan_scenes),
                          ("2. Match approved library assets", self.match_scenes),
                          ("3. Place approved scenes on timeline", self.place_scenes)]:
            b = QPushButton(title)
            b.clicked.connect(cb)
            lay.addWidget(b)
        self.scene_list = QListWidget()
        self.scene_list.itemDoubleClicked.connect(self.choose_scene_media)
        lay.addWidget(self.scene_list, 1)
        pages = QHBoxLayout()
        prev = QPushButton("← Previous 5")
        prev.clicked.connect(self.previous_scene_page)
        pages.addWidget(prev)
        self.scene_page_info = QLabel("0 scenes")
        pages.addWidget(self.scene_page_info)
        next_page = QPushButton("Next 5 →")
        next_page.clicked.connect(self.next_scene_page)
        pages.addWidget(next_page)
        lay.addLayout(pages)
        approve = QPushButton("Approve & Lock Current 5 Scenes")
        approve.clicked.connect(self.approve_scene_page)
        lay.addWidget(approve)
        self.left.addTab(widget, "Scene Builder")

    def build_inspector(self, host: QWidget):
        lay = QVBoxLayout(host)
        lay.addWidget(QLabel("<b>SELECTED CLIP INSPECTOR</b>"))
        self.selected_name = QLabel("Select a clip from the timeline")
        self.selected_name.setWordWrap(True)
        lay.addWidget(self.selected_name)
        form = QFormLayout()
        self.track_select = QComboBox()
        form.addRow("Track", self.track_select)
        self.start_spin = self._spin(0, 360000)
        self.in_spin = self._spin(0, 360000)
        self.out_spin = self._spin(0, 360000)
        form.addRow("Timeline start", self.start_spin)
        form.addRow("Source in", self.in_spin)
        form.addRow("Source out", self.out_spin)
        self.zoom_spin = self._spin(50, 300, 100)
        form.addRow("Zoom %", self.zoom_spin)
        self.mirror_check = QCheckBox("Horizontal Mirror")
        form.addRow("Mirror", self.mirror_check)
        self.motion_select = QComboBox()
        self.motion_select.addItems(sorted(MOTIONS))
        form.addRow("Image/Video motion", self.motion_select)
        self.look_select = QComboBox()
        self.look_select.addItems(list(COLOR_LOOKS))
        form.addRow("Color look (23)", self.look_select)
        self.look_strength_spin = self._spin(0, 100, 100)
        form.addRow("Look strength %", self.look_strength_spin)
        self.noise_select = QComboBox()
        self.noise_select.addItems(sorted(GRAINS))
        form.addRow("Grain/Noise style", self.noise_select)
        self.source_audio_check = QCheckBox("Include original video audio")
        form.addRow("Source audio", self.source_audio_check)
        self.grain_spin = self._spin(0, 40, 0)
        form.addRow("Film grain", self.grain_spin)
        self.brightness_spin = self._spin(-100, 100, 0)
        form.addRow("Brightness", self.brightness_spin)
        self.saturation_spin = self._spin(0, 400, 100)
        form.addRow("Saturation %", self.saturation_spin)
        self.transition = QComboBox()
        self.transition.addItems(sorted(TRANSITIONS))
        form.addRow("Transition in", self.transition)
        self.trans_spin = self._spin(0, 5, 0)
        form.addRow("Transition sec", self.trans_spin)
        self.volume_spin = self._spin(0, 400, 100)
        form.addRow("Audio volume %", self.volume_spin)
        self.fade_in_spin = self._spin(0, 20, 0)
        self.fade_out_spin = self._spin(0, 20, 0)
        form.addRow("Fade in (sec)", self.fade_in_spin)
        form.addRow("Fade out (sec)", self.fade_out_spin)
        self.caption_text = QLineEdit()
        form.addRow("Caption text", self.caption_text)
        lay.addLayout(form)
        b = QPushButton("Apply Clip Settings")
        b.clicked.connect(self.apply_inspector)
        lay.addWidget(b)
        rb = QPushButton("Replace Clip with Selected Library Media")
        rb.clicked.connect(self.replace_selected)
        lay.addWidget(rb)
        self.details = QLabel()
        self.details.setWordWrap(True)
        lay.addWidget(self.details)
        lay.addStretch()

    def _spin(self, minimum, maximum, value=0):
        widget = QDoubleSpinBox()
        widget.setRange(minimum, maximum)
        widget.setDecimals(2)
        widget.setSingleStep(.1)
        widget.setValue(value)
        return widget

    def _selected_library_records(self) -> list[dict]:
        ids = [x.data(Qt.ItemDataRole.UserRole) for x in self.media_list.selectedItems()]
        return [self.library.get(x) for x in ids]

    def refresh_library(self, *_):
        if not hasattr(self, "media_list"):
            return
        state = ["", "approved", "candidate", "rejected"][self.status_filter.currentIndex()]
        rows = self.library.list(search=self.media_search.text(), status=state)
        self.media_list.clear()
        for rec in rows:
            marker = "✓" if rec["status"]=="approved" else "×" if rec["status"]=="rejected" else "·"
            label = f"{marker} {rec['name']}  [{rec['kind']}]"
            if rec["missing"]:
                label += " [MISSING]"
            line = QListWidgetItem(label)
            line.setData(Qt.ItemDataRole.UserRole, rec["id"])
            self.media_list.addItem(line)
        self.refresh_counts()
        if not self.thumbnail_thread or not self.thumbnail_thread.isRunning():
            self.thumbnail_thread = ThumbnailThread(self.library, rows)
            self.thumbnail_thread.ready.connect(self.thumbnail_ready)
            self.thumbnail_thread.start()

    def refresh_counts(self):
        stats = self.library.summary()
        selected = self._selected_library_records()
        self.counts.setText(f"{stats['total']} total | {stats['videos']} clips | "
                            f"{stats['images']} images | {stats['approved']} approved | "
                            f"{len(selected)} selected")

    def thumbnail_ready(self, media_id: str, path: str):
        for i in range(self.media_list.count()):
            line = self.media_list.item(i)
            if line.data(Qt.ItemDataRole.UserRole) == media_id:
                line.setIcon(QIcon(path))
                return

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Import media files", "", "Media (*.mp4 *.mov *.mkv *.webm *.avi *.jpg *.jpeg *.png *.webp)")
        success = 0
        errors = []
        for path in paths:
            try:
                self.library.ingest(path)
                success += 1
            except Exception as exc:
                errors.append(f"{Path(path).name}: {exc}")
        self.refresh_library()
        self.message(f"Imported {success} assets", errors)

    def import_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Scan media folder")
        if directory:
            rows, errors = self.library.import_folder(directory)
            self.refresh_library()
            self.message(f"Indexed {len(rows)} media items", errors)

    def message(self, msg: str, errors=None):
        self.status.setText(msg)
        self.statusBar().showMessage(msg)
        if errors:
            QMessageBox.warning(self, "Some tasks failed", "\n".join(errors[:8]))

    def change_media_status(self, status: str):
        ids = [rec["id"] for rec in self._selected_library_records()]
        self.library.set_status(ids, status)
        self.refresh_library()
        self.message(f"{len(ids)} items marked {status}")

    def edit_media_tags(self):
        rec = next(iter(self._selected_library_records()), None)
        if not rec:
            return
        tags, ok = QInputDialog.getText(self, "Media tags", "Comma-separated tags", text=", ".join(rec["tags"]))
        if ok:
            self.library.set_tags(rec["id"], tags.split(","))
            self.refresh_library()

    def show_duplicates(self):
        groups = self.library.duplicates()
        description = "\n".join(" / ".join(x["name"] for x in g) for g in groups[:12])
        QMessageBox.information(self, "Exact Duplicate Review",
                                description or "No identical file hashes found. No files were deleted.")

    def import_script(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import narration script", "", "Plain text (*.txt)")
        if path:
            try:
                self.script.setPlainText(Path(path).read_text(encoding="utf-8-sig"))
            except Exception as exc:
                QMessageBox.warning(self, "Script import", str(exc))

    def plan_scenes(self):
        self.scenes = create_scene_plan(self.script.toPlainText())
        self.scene_page = 0
        self.populate_scenes()
        self.message(f"Planned {len(self.scenes)} editable scenes (timing estimate, not speech timestamps)")

    def populate_scenes(self):
        self.scene_list.clear()
        if not self.scenes:
            self.scene_page_info.setText("0 scenes")
            return
        self.scene_page = max(0, min(self.scene_page, (len(self.scenes)-1)//5))
        first = self.scene_page*5
        for idx, scene in enumerate(self.scenes[first:first+5], start=first):
            self.scene_list.addItem(
                f"{idx+1:03d} {human(scene.start_ms)} {scene.text[:45]}\n"
                f"{'✓ approved' if scene.approved else '● pending'} "
                f"{Path(scene.media_path).name if scene.media_path else 'No media'} · "
                f"{scene.match_reason[:55]}"
            )
        self.scene_page_info.setText(f"{first+1}–{min(len(self.scenes),first+5)} / {len(self.scenes)}")

    def previous_scene_page(self):
        self.scene_page = max(0, self.scene_page-1)
        self.populate_scenes()

    def next_scene_page(self):
        self.scene_page = min(max(0,(len(self.scenes)-1)//5), self.scene_page+1)
        self.populate_scenes()

    def approve_scene_page(self):
        first = self.scene_page*5
        approved = 0
        for scene in self.scenes[first:first+5]:
            if scene.media_path:
                scene.approved = True
                scene.locked = True
                approved += 1
        self.populate_scenes()
        self.message(f"Approved {approved} current-page media/scene assignments; review next five")

    def match_scenes(self):
        policies = ["local_first", "local_only", "alternate", "video_only", "image_only"]
        self.scenes = match_media(self.scenes, self.library,
                                  policies[self.source_policy.currentIndex()],
                                  self.reuse.isChecked(),
                                  auto_approve=self.scene_auto_approve.isChecked())
        self.populate_scenes()
        self.message(f"{sum(s.approved for s in self.scenes)}/{len(self.scenes)} scenes matched approved media")

    def choose_scene_media(self, item):
        index = self.scene_page*5 + self.scene_list.row(item)
        if index >= len(self.scenes):
            return
        candidates = self.library.list(status="approved")
        if not candidates:
            QMessageBox.information(self, "No approved sources", "Approve media in the Library tab first")
            return
        names = [x["name"] for x in candidates]
        name, accepted = QInputDialog.getItem(self, "Choose scene media", "Approved asset", names, 0, False)
        if accepted and name:
            rec = next(x for x in candidates if x["name"] == name)
            scene = self.scenes[index]
            scene.media_id, scene.media_path, scene.media_kind = rec["id"], rec["path"], rec["kind"]
            scene.approved = True
            scene.locked = True
            scene.match_reason = "Manually selected and locked"
            self.populate_scenes()

    def place_scenes(self):
        if not self.scenes:
            return
        self.history.checkpoint()
        try:
            count = append_scenes(self.project, self.scenes)
        except Exception as exc:
            self.project = self.history.undo()
            self.history.project = self.project
            QMessageBox.warning(self, "Scene placement error", str(exc))
            return
        self.mark_changed()
        self.message(f"Added {count} approved visuals to main video track")

    def add_selected_media(self):
        records = self._selected_library_records()
        if not records:
            return
        target_label, accepted = QInputDialog.getItem(
            self, "Add media to timeline", "Choose visual track",
            ["Main Video", "Video Overlay"], 0, False
        )
        if not accepted:
            return
        target = "v2" if target_label == "Video Overlay" else "v1"
        self.history.checkpoint()
        try:
            for rec in records:
                if rec["missing"]:
                    raise FileNotFoundError(rec["path"])
                self.project.add(rec["path"], rec["kind"], target, rec["duration_ms"])
        except Exception as exc:
            self.project = self.history.undo()
            self.history.project = self.project
            QMessageBox.warning(self, "Cannot add media", str(exc))
            return
        self.mark_changed()

    def add_audio(self):
        path, _ = QFileDialog.getOpenFileName(
            self, "Add audio or use audio from a video source", "",
            "Audio/video (*.wav *.mp3 *.m4a *.aac *.mp4 *.mov *.mkv)"
        )
        if not path:
            return
        # FFmpeg -i Duration is sufficient for a first local-audio metadata probe.
        import re
        import subprocess
        r = subprocess.run([ffmpeg_path(), "-hide_banner", "-i", path], capture_output=True,
                           text=True, errors="replace", timeout=30)
        m = re.search(r"Duration:\s*(\d+):(\d+):(\d+(?:\.\d+)?)", r.stderr)
        if not m:
            QMessageBox.warning(self, "Unsupported audio", "Cannot determine duration")
            return
        h, minute, second = m.groups()
        dur = round((int(h)*3600+int(minute)*60+float(second))*1000)
        selected, yes = QInputDialog.getItem(
            self, "Audio track", "Place audio on",
            ["Narration", "Background Music", "Sound Effects"], 0, False
        )
        if not yes:
            return
        tracks = {"Narration":"voice","Background Music":"music","Sound Effects":"sfx"}
        self.history.checkpoint()
        self.project.add(path, "audio", tracks[selected], dur, start_ms=self.playhead_ms)
        self.mark_changed()

    def import_subtitles(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import timed captions", "", "SubRip subtitles (*.srt)")
        if not path:
            return
        self.history.checkpoint()
        try:
            count = import_srt(self.project, path)
        except Exception as exc:
            self.project = self.history.undo()
            self.history.project = self.project
            QMessageBox.warning(self, "Subtitle import error", str(exc))
            return
        self.mark_changed()
        self.message(f"Imported {count} timed captions")

    def export_subtitles(self):
        path, _ = QFileDialog.getSaveFileName(self, "Export editable captions", "", "SubRip subtitles (*.srt)")
        if path:
            try:
                export_srt(self.project, Path(path).with_suffix(".srt"))
                self.message(f"Captions exported: {path}")
            except Exception as exc:
                QMessageBox.warning(self, "Subtitle export", str(exc))

    def add_caption(self):
        text, ok = QInputDialog.getMultiLineText(self, "Caption", "Caption shown at the playhead")
        if ok and text.strip():
            self.history.checkpoint()
            self.project.add("", "text", "captions", 3000, start_ms=self.playhead_ms, text=text)
            self.mark_changed()

    def set_timeline_zoom(self, value: int):
        global SCALE
        SCALE = max(.02, value/1000)
        self.redraw_timeline()

    def duplicate_item(self):
        if not self.selected_id:
            return
        source = self.project.item(self.selected_id)
        if self.project.track(source.track_id).locked:
            self.message("Selected track is locked")
            return
        self.history.checkpoint()
        duplicate = copy.deepcopy(source)
        duplicate.id = uuid.uuid4().hex
        duplicate.start_ms = source.end_ms
        duplicate.transition_in, duplicate.transition_ms = "cut", 0
        self.project.items.append(duplicate)
        self.project.validate()
        self.project.revision += 1
        self.selected_id = duplicate.id
        self.mark_changed()

    def track_controls(self):
        if not self.project.tracks:
            return
        names = [f"{i+1}. {track.name}" for i,track in enumerate(self.project.tracks)]
        selected, ok = QInputDialog.getItem(self,"Track controls","Track",names,0,False)
        if not ok:
            return
        track = self.project.tracks[names.index(selected)]
        options = ["Toggle Lock", "Toggle Mute", "Toggle Visibility"]
        action, yes = QInputDialog.getItem(self,"Track controls",track.name,options,0,False)
        if not yes:
            return
        self.history.checkpoint()
        if action == options[0]:
            track.locked = not track.locked
        elif action == options[1]:
            track.muted = not track.muted
        else:
            track.visible = not track.visible
        self.project.revision += 1
        self.mark_changed()
        self.message(f"{track.name}: lock={track.locked}, mute={track.muted}, visible={track.visible}")

    def redraw_timeline(self):
        self.timeline.redraw()
        self.seek.setMaximum(max(0, self.project.duration_ms))
        self.clock.setText(f"{human(self.playhead_ms)} / {human(self.project.duration_ms)}")
        self.details.setText(f"{len(self.project.items)} timeline items\n"
                             f"{len(self.project.tracks)} independent tracks\n"
                             f"{self.project.width}×{self.project.height}")
        self.show_inspector()

    def show_inspector(self):
        if not self.selected_id:
            return
        try:
            obj = self.project.item(self.selected_id)
        except StopIteration:
            self.selected_id = ""
            return
        self.selected_name.setText(obj.text[:100] if obj.kind=="text" else Path(obj.asset).name)
        self.track_select.blockSignals(True)
        self.track_select.clear()
        for track in self.project.tracks:
            self.track_select.addItem(track.name, track.id)
        self.track_select.setCurrentIndex(next((i for i,t in enumerate(self.project.tracks)
                                                if t.id==obj.track_id), 0))
        self.track_select.blockSignals(False)
        for widget, val in [(self.start_spin, obj.start_ms/1000),
                             (self.in_spin, obj.in_ms/1000), (self.out_spin, obj.out_ms/1000),
                             (self.zoom_spin, float(obj.effects.get("zoom",1))*100),
                             (self.grain_spin, int(obj.effects.get("grain",0))),
                             (self.brightness_spin, float(obj.effects.get("brightness",0))*100),
                             (self.saturation_spin, float(obj.effects.get("saturation",1))*100),
                             (self.trans_spin, obj.transition_ms/1000),
                             (self.volume_spin, obj.volume*100),
                             (self.look_strength_spin, float(obj.effects.get("look_intensity",100))),
                             (self.fade_in_spin, obj.fade_in_ms/1000),
                             (self.fade_out_spin, obj.fade_out_ms/1000)]:
            widget.setValue(val)
        self.mirror_check.setChecked(bool(obj.effects.get("mirror",False)))
        self.motion_select.setCurrentText(str(obj.effects.get("motion","none")))
        self.look_select.setCurrentText(str(obj.effects.get("look","neutral")))
        self.noise_select.setCurrentText(str(obj.effects.get("grain_style","film")))
        self.source_audio_check.setEnabled(obj.kind == "video")
        self.source_audio_check.setChecked(bool(obj.effects.get("source_audio",False)))
        self.transition.setCurrentText(obj.transition_in)
        self.caption_text.setText(obj.text)

    def apply_inspector(self):
        if not self.selected_id:
            return
        item = self.project.item(self.selected_id)
        self.history.checkpoint()
        previous = copy.deepcopy(item)
        try:
            item.track_id = self.track_select.currentData()
            item.start_ms = round(self.start_spin.value()*1000)
            item.in_ms = round(self.in_spin.value()*1000)
            item.out_ms = round(self.out_spin.value()*1000)
            item.effects.update({"zoom": self.zoom_spin.value()/100,
                                 "mirror": self.mirror_check.isChecked(),
                                 "grain": int(self.grain_spin.value()),
                                 "brightness": self.brightness_spin.value()/100,
                                 "saturation": self.saturation_spin.value()/100,
                                 "look": self.look_select.currentText(),
                                 "look_intensity": self.look_strength_spin.value(),
                                 "motion": self.motion_select.currentText(),
                                 "grain_style": self.noise_select.currentText(),
                                 "source_audio": self.source_audio_check.isChecked() if item.kind=="video" else False})
            item.transition_in = self.transition.currentText()
            item.transition_ms = round(self.trans_spin.value()*1000)
            item.volume = self.volume_spin.value()/100
            item.fade_in_ms = round(self.fade_in_spin.value()*1000)
            item.fade_out_ms = round(self.fade_out_spin.value()*1000)
            item.text = self.caption_text.text()
            self.project.validate()
            self.project.revision += 1
        except Exception as exc:
            self.project = self.history.undo()
            self.history.project = self.project
            QMessageBox.warning(self, "Invalid edit", str(exc))
            return
        self.mark_changed()

    def replace_selected(self):
        rec = next(iter(self._selected_library_records()), None)
        if not rec or not self.selected_id:
            return
        obj = self.project.item(self.selected_id)
        if obj.kind != rec["kind"]:
            QMessageBox.warning(self, "Incompatible media", "Replacement must be the same media kind")
            return
        self.history.checkpoint()
        try:
            self.project.replace_asset(self.selected_id, rec["path"])
        except Exception as exc:
            self.project = self.history.undo()
            self.history.project = self.project
            self.message(str(exc))
            return
        self.mark_changed()

    def split_item(self):
        if not self.selected_id:
            return
        self.history.checkpoint()
        try:
            item = self.project.split(self.selected_id, self.playhead_ms)
            self.selected_id = item.id
        except Exception as exc:
            self.project = self.history.undo()
            self.history.project = self.project
            self.message(str(exc))
            return
        self.mark_changed()

    def delete_item(self):
        if not self.selected_id:
            return
        self.history.checkpoint()
        self.project.remove(self.selected_id)
        self.selected_id = ""
        self.mark_changed()

    def undo(self):
        self.project = self.history.undo()
        self.selected_id = ""
        self.mark_changed()

    def redo(self):
        self.project = self.history.redo()
        self.selected_id = ""
        self.mark_changed()

    def mark_changed(self):
        self.redraw_timeline()
        self.save_timer.start()
        self.preview_timer.start()
        self.setWindowTitle(f"Scene Desktop Studio — {self.project.title} •")

    def autosave(self):
        try:
            save(self.project, app_directory() / "autosave.sds2")
        except Exception as exc:
            self.message(f"Autosave error: {exc}")

    def set_output_format(self, idx: int):
        formats = [(1920,1080),(1080,1920),(1280,720),(720,1280)]
        self.history.checkpoint()
        self.project.width, self.project.height = formats[max(0,idx)]
        self.mark_changed()

    def new_project(self):
        if self.worker and self.worker.isRunning():
            self.message("Cancel or complete render before switching projects")
            return
        self.player.stop()
        self.project = StudioProject()
        self.history = EditHistory(self.project)
        self.scenes = []
        self.selected_id = ""
        self.project_path = None
        self.playhead_ms = 0
        self.script.setPlainText("")
        self.mark_changed()

    def open_project(self):
        path, _ = QFileDialog.getOpenFileName(self, "Open Scene Desktop project", "", "Scene Studio (*.sds2)")
        if path:
            try:
                self.player.stop()
                self.project = load(path)
                self.history = EditHistory(self.project)
                self.project_path = Path(path)
                self.selected_id = ""
                self.playhead_ms = 0
                self.redraw_timeline()
                self.message(f"Opened {Path(path).name}")
            except Exception as exc:
                QMessageBox.warning(self, "Cannot open", str(exc))

    def show_resources(self):
        try:
            metrics = probe(app_directory())
            body = "\n".join([
                f"OS: {metrics['system']}",
                f"CPU: {metrics['cpu']} / logical cores: {metrics['logical_cores']}",
                f"RAM: {metrics['ram_total_gib']} GiB total, {metrics['ram_available_gib']} GiB available",
                f"Free disk: {metrics['disk_free_gib']} / {metrics['disk_total_gib']} GiB",
                f"GPU: {metrics['gpu_name']}",
                f"FFmpeg encoders in build: {', '.join(metrics['ffmpeg_encoders_present'])}",
                "GPU encoding not validated by this report",
                *(["Warnings:"] + metrics['warnings'] if metrics["warnings"] else []),
            ])
            QMessageBox.information(self, "Read-only PC resources", body)
        except Exception as exc:
            QMessageBox.warning(self, "Resource probe", str(exc))

    def recover_autosave(self):
        path = app_directory() / "autosave.sds2"
        if not path.is_file():
            self.message("No recovery autosave found")
            return
        try:
            self.project = load(path)
            self.history = EditHistory(self.project)
            self.project_path = None
            self.selected_id = ""
            self.playhead_ms = 0
            self.mark_changed()
            self.message("Recovered draft; use Save to keep it as a project")
        except Exception as exc:
            QMessageBox.warning(self, "Recovery error", str(exc))

    def relink_media(self):
        missing = [item for item in self.project.items if item.kind != "text"
                   and not Path(item.asset).is_file()]
        if not missing:
            self.message("All timeline media references are available")
            return
        directory = QFileDialog.getExistingDirectory(self, "Choose folder with missing files")
        if not directory:
            return
        found = {}
        for path in Path(directory).rglob("*"):
            if path.is_file():
                found.setdefault(path.name.lower(), []).append(path)
        changed = 0
        self.history.checkpoint()
        for item in missing:
            options = found.get(Path(item.asset).name.lower(), [])
            if len(options) == 1:
                item.asset = str(options[0].resolve())
                changed += 1
        if changed:
            self.project.revision += 1
            self.mark_changed()
        self.message(f"Relinked {changed}/{len(missing)} missing media. Originals preserved.")

    def save_project(self):
        if self.project_path is None:
            path, _ = QFileDialog.getSaveFileName(self, "Save editable project", self.project.title + ".sds2",
                                                   "Scene Studio (*.sds2)")
            if not path:
                return
            self.project_path = Path(path).with_suffix(".sds2")
        try:
            save(self.project, self.project_path)
            self.setWindowTitle(f"Scene Desktop Studio — {self.project.title}")
            self.message("Saved " + str(self.project_path))
        except Exception as exc:
            QMessageBox.warning(self, "Save error", str(exc))

    def cancel_render(self):
        if self.worker and self.worker.isRunning():
            self.worker.stop.set()
            self.message("Cancelling current render safely...")
        else:
            self.message("No active render job")

    def _on_media_status(self, status):
        # Automatically continue playback into the following cached preview
        # window; never confuse a paused player with end-of-timeline.
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.project.duration_ms > 0:
            nxt = self._preview_start + self.player.duration()
            if nxt + 100 < self.project.duration_ms:
                self.playhead_ms = nxt
                self.render_preview()

    def _on_preview_position(self, ms: int):
        if not self._preview_output or not self.project.duration_ms:
            return
        self.playhead_ms = min(self.project.duration_ms, self._preview_start + ms)
        self.seek.blockSignals(True)
        self.seek.setValue(self.playhead_ms)
        self.seek.blockSignals(False)
        self.clock.setText(f"{human(self.playhead_ms)} / {human(self.project.duration_ms)}")

    def scrub(self):
        self.playhead_ms = self.seek.value()
        self.redraw_timeline()
        self.preview_timer.start()

    def toggle_preview(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif self._preview_output:
            self.player.play()
        else:
            self.render_preview()

    def render_preview(self):
        if self.worker and self.worker.isRunning():
            self.preview_pending = True
            return
        if self.project.duration_ms < 100:
            return
        start = max(0, min(self.playhead_ms, self.project.duration_ms - 100))
        self._preview_start = start
        end = min(self.project.duration_ms, start + 4000)
        filename = app_directory() / "previews" / (uuid.uuid4().hex + ".mp4")
        filename.parent.mkdir(parents=True, exist_ok=True)
        cache = app_directory() / "segment-cache"
        self.worker = RenderThread(self.project, filename, cache, preview=True, window=(start,end))
        self.worker.done.connect(self._preview_ready)
        self.worker.failed.connect(lambda err: self.message("Preview: " + err[:180]))
        self.worker.finished.connect(self._preview_finish)
        self.worker.start()
        self.message("Rendering preview segment...")

    def _preview_ready(self, filename: str):
        self._preview_output = filename
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(filename))
        self.player.play()
        self.message("Preview ready (low-resolution cached composition)")

    def _preview_finish(self):
        if self.preview_pending:
            self.preview_pending = False
            self.preview_timer.start()

    def export_video(self):
        if self.worker and self.worker.isRunning():
            self.message("Preview/export already active")
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export new video version", "",
                                               "MP4 Video (*.mp4)")
        if not path:
            return
        out = Path(path).with_suffix(".mp4")
        self.worker = RenderThread(self.project, out, app_directory() / "segment-cache")
        self.worker.progress.connect(lambda n, msg: self.message(f"{n}% — {msg}"))
        self.worker.done.connect(lambda dest: QMessageBox.information(
            self, "Export complete", f"New video saved:\n{dest}"
        ))
        self.worker.failed.connect(lambda msg: QMessageBox.warning(self, "Export error", msg))
        self.worker.start()
        self.message("Export started; original media will not be modified")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.message("Finish export/preview before closing the Studio")
            event.ignore()
            return
        if self.thumbnail_thread and self.thumbnail_thread.isRunning():
            # Do not destroy an active QThread object when closing the window.
            self.thumbnail_thread.wait(5000)
        self.autosave()
        self.player.stop()
        super().closeEvent(event)
