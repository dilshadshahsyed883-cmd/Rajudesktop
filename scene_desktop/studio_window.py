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
import os
import platform
import time

from PySide6.QtCore import Qt, QThread, QTimer, QUrl, Signal, QSize
from PySide6.QtGui import QAction, QColor, QBrush, QPen, QPixmap, QIcon, QDesktopServices, QImageReader
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QGraphicsItem, QGraphicsRectItem, QGraphicsPixmapItem, QGraphicsScene, QGraphicsSimpleTextItem,
    QGraphicsView, QGridLayout, QHBoxLayout, QInputDialog, QLabel,
    QLineEdit, QListWidget, QListWidgetItem, QMainWindow, QMessageBox,
    QPlainTextEdit, QProgressBar, QPushButton, QSlider, QSplitter,
    QTabWidget, QVBoxLayout, QWidget, QAbstractItemView, QStackedWidget,
)
from PySide6.QtCore import QStandardPaths

from .library import MediaLibrary
from .media import duration_ms, ffmpeg_path
from .timeline import StudioProject, Item, EditHistory, save, load, VISUAL_TRACKS, AUDIO_TRACKS
from .planner import create_scene_plan, match_media, append_scenes, Scene
from .captions import import_srt, export_srt
from .word_captions import import_word_json
from .speech import transcribe_local
from .waveforms import generate_waveform, waveform_path
from .resources import probe
from .local_ai import plan_with_local_ai
from .keyframes import set_keyframe,remove_keyframe
from .effects import COLOR_LOOKS, MOTIONS, GRAINS, TRANSITIONS
from .studio_render import render
from .live_preview import OpenGLTimelineCanvas
from .gpu_audio import GPUAudioMixThread,has_timeline_audio,audio_active_between,audio_window

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


class SpeechThread(QThread):
    ready = Signal(object)
    failed = Signal(str)
    stage = Signal(str)

    def __init__(self,source: str,model: str,cache: Path,allow_download: bool):
        super().__init__()
        self.source,self.model,self.cache=source,model,cache
        self.allow_download=allow_download

    def run(self):
        try:
            payload=transcribe_local(self.source,self.model,self.cache,
                                     allow_download=self.allow_download,
                                     progress=lambda label:self.stage.emit(label))
            self.ready.emit(payload)
        except Exception as exc:
            self.failed.emit(str(exc))


class WaveformThread(QThread):
    ready = Signal(str)

    def __init__(self,paths: list[str],cache_dir: Path):
        super().__init__()
        self.paths,self.cache_dir=paths,cache_dir

    def run(self):
        for path in self.paths[:30]:
            try:
                generate_waveform(path,self.cache_dir)
                self.ready.emit(path)
            except (RuntimeError,OSError,ValueError,subprocess.SubprocessError):
                continue


class AIPlanThread(QThread):
    ready = Signal(object)
    failed = Signal(str)

    def __init__(self, script: str, model: str):
        super().__init__()
        self.script, self.model = script, model

    def run(self):
        try:
            self.ready.emit(plan_with_local_ai(self.script, self.model))
        except Exception as exc:
            self.failed.emit(str(exc))


class ImportThread(QThread):
    completed = Signal(int, list)
    progress = Signal(int)

    def __init__(self, library: MediaLibrary, paths: list[str] | None = None,
                 folder: str | None = None):
        super().__init__()
        self.library, self.paths, self.folder = library, paths or [], folder
        self.cancel_flag = threading.Event()

    def run(self):
        count, errors = 0, []
        if self.folder:
            root = Path(self.folder).expanduser().resolve()
            sources = []
            for item in root.rglob("*"):
                if self.cancel_flag.is_set() or len(sources) >= 5000:
                    break
                if item.is_file() and item.suffix.lower() in {
                    ".mp4",".mov",".mkv",".webm",".avi",".m4v",
                    ".png",".jpg",".jpeg",".webp",".bmp"
                }:
                    sources.append(str(item))
        else:
            sources = self.paths
        for source in sources:
            if self.cancel_flag.is_set():
                break
            try:
                self.library.ingest(source)
                count += 1
            except Exception as exc:
                errors.append(f"{Path(source).name}: {exc}")
            if count % 10 == 0:
                self.progress.emit(count)
        self.completed.emit(count, errors[:16])


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
                 preview: bool = False, window=None, preview_side: int = 360):
        super().__init__()
        self.snapshot = StudioProject.from_dict(project.to_dict())
        self.dest, self.cache = dest, cache
        self.preview, self.window = preview, window
        self.preview_side = preview_side
        self.stop = threading.Event()

    def run(self):
        try:
            result = render(self.snapshot, self.dest, cache_dir=self.cache,
                            preview=self.preview, window=self.window,
                            preview_side=self.preview_side,
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
        if item.kind == "audio":
            try:
                image=waveform_path(item.asset,editor.waveform_dir)
                if image.is_file():
                    pix=QPixmap(str(image)).scaled(
                        max(16,round(self.rect().width())-4),24,
                        Qt.AspectRatioMode.IgnoreAspectRatio,
                        Qt.TransformationMode.SmoothTransformation,
                    )
                    picture=QGraphicsPixmapItem(pix,self)
                    picture.setPos(2,18)
                    picture.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
            except OSError:
                pass
        elif item.kind in {"image","video"}:
            if item.kind=="image":
                candidate=item.asset
            else:
                record=editor.media_lookup.get(str(Path(item.asset).resolve()))
                candidate=str(editor.library.cache / (record["sha256"][:20]+".jpg")) if record else ""
            if candidate and Path(candidate).is_file():
                reader=QImageReader(candidate)
                limits=QSize(min(90,max(20,round(self.rect().width())-6)),34)
                native=reader.size()
                if native.isValid():
                    reader.setScaledSize(native.scaled(limits,Qt.AspectRatioMode.KeepAspectRatio))
                image=reader.read()
                pix=QPixmap.fromImage(image)
                picture=QGraphicsPixmapItem(pix,self)
                picture.setPos(3,10)
                picture.setAcceptedMouseButtons(Qt.MouseButton.NoButton)
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
        self.playhead_line = self.canvas.addLine(playhead_x, 0, playhead_x, TOP + rows * ROW,
                            QPen(QColor("#f5c454"), 2))

    def move_playhead(self,ms: int):
        if hasattr(self,"playhead_line"):
            x=LEFT+ms*SCALE
            self.playhead_line.setLine(x,0,x,TOP+len(self.editor.project.tracks)*ROW)


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
        self.media_lookup = {}
        self.waveform_dir=app_directory() / "waveforms"
        self.waveform_thread: WaveformThread | None = None
        self.project.media_db = str(self.library.database)
        self.thumbnail_thread: ThumbnailThread | None = None
        self.import_thread: ImportThread | None = None
        self.ai_thread: AIPlanThread | None = None
        self.speech_thread: SpeechThread | None = None
        self.worker: RenderThread | None = None
        self.preview_pending = False
        self._preview_output = None
        self.gpu_canvas: OpenGLTimelineCanvas | None = None
        self.gpu_active = False
        self.gpu_audio_output=QAudioOutput(self)
        self.gpu_audio_player=QMediaPlayer(self)
        self.gpu_audio_player.setAudioOutput(self.gpu_audio_output)
        self.gpu_audio_player.mediaStatusChanged.connect(self._on_gpu_audio_loaded)
        self.gpu_audio_job: GPUAudioMixThread | None = None
        self.gpu_audio_generation=0
        self.gpu_audio_range=(0,0)
        self.gpu_audio_file=""
        self._gpu_audio_last_sync=0.
        self._gpu_user_selected = False
        self.last_export: Path | None = None
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
        # CPU-first is the safe default; GPU Live is an optional manual choice.

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
                              ("Redo", self.redo), ("Export MP4", self.export_video),
                              ("Open Last Video", self.open_last_export)]:
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
        preview_column.addWidget(QLabel("<b>LIVE TIMELINE PREVIEW</b> — GPU composition with FFmpeg-accurate fallback"))
        backend_row = QHBoxLayout()
        self.preview_backend = QComboBox()
        self.preview_backend.addItems(["GPU Live — optional hardware", "CPU Proxy — accurate effects/audio"])
        self.preview_backend.setCurrentIndex(1)
        self.preview_backend.currentIndexChanged.connect(self.set_preview_backend)
        backend_row.addWidget(self.preview_backend,1)
        self.cpu_profile = QComboBox()
        self.cpu_profile.addItem("360p · Low CPU", 360)
        self.cpu_profile.addItem("540p · Balanced", 540)
        self.cpu_profile.addItem("720p · Detailed", 720)
        self.cpu_profile.setCurrentIndex(0)
        self.cpu_profile.currentIndexChanged.connect(self.preview_quality_changed)
        backend_row.addWidget(self.cpu_profile)
        hardware = QPushButton("Preview Diagnostics")
        hardware.clicked.connect(self.show_preview_diagnostics)
        backend_row.addWidget(hardware)
        preview_column.addLayout(backend_row)
        self.preview_mode_status = QLabel("CPU Proxy 360p: cached FFmpeg + audio; full-resolution export remains unchanged")
        preview_column.addWidget(self.preview_mode_status)
        self.preview_stack = QStackedWidget()
        self.video = QVideoWidget()
        self.video.setMinimumHeight(175)
        self.player.setVideoOutput(self.video)
        self.preview_stack.addWidget(self.video)
        preview_column.addWidget(self.preview_stack,1)
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
        refresh.clicked.connect(self.refresh_preview)
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
                              ("Whisper Voice", self.transcribe_voice),
                              ("Word JSON", self.import_word_captions),
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
        for title, cb in [("Import Files", self.import_files), ("Import Folder", self.import_folder),
                          ("Cancel Import", self.cancel_import), ("Add Audio", self.add_audio)]:
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
        ai_row = QHBoxLayout()
        self.ai_model = QLineEdit()
        self.ai_model.setPlaceholderText("Optional installed local Ollama model name")
        ai_row.addWidget(self.ai_model)
        ai_button = QPushButton("AI Scene Plan")
        ai_button.clicked.connect(self.plan_ai_scenes)
        ai_row.addWidget(ai_button)
        lay.addLayout(ai_row)
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
        lut_row = QHBoxLayout()
        self.lut_path = QLineEdit()
        self.lut_path.setPlaceholderText("Optional .cube LUT (not bundled)")
        lut_row.addWidget(self.lut_path)
        choose_lut = QPushButton("...")
        choose_lut.clicked.connect(self.choose_lut)
        lut_row.addWidget(choose_lut)
        form.addRow("3D LUT File", lut_row)
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
        lay.addWidget(QLabel("<b>CLIP KEYFRAMES</b>"))
        self.keyframe_property = QComboBox()
        self.keyframe_property.addItems(["zoom","brightness","saturation"])
        lay.addWidget(self.keyframe_property)
        keys_row = QHBoxLayout()
        key_add = QPushButton("◇ Add at playhead")
        key_add.clicked.connect(self.add_keyframe)
        keys_row.addWidget(key_add)
        key_delete = QPushButton("Delete keyframe")
        key_delete.clicked.connect(self.delete_keyframe)
        keys_row.addWidget(key_delete)
        lay.addLayout(keys_row)
        self.keyframes_info = QLabel("Select clip to animate zoom / brightness / saturation")
        self.keyframes_info.setWordWrap(True)
        lay.addWidget(self.keyframes_info)
        self.details = QLabel()
        self.details.setWordWrap(True)
        lay.addWidget(self.details)
        lay.addStretch()

    def choose_lut(self):
        path, _ = QFileDialog.getOpenFileName(self,"Choose a 3D color LUT","","3D LUT (*.cube)")
        if path:
            self.lut_path.setText(str(Path(path).resolve()))

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

    def cancel_import(self):
        if self.import_thread and self.import_thread.isRunning():
            self.import_thread.cancel_flag.set()
            self.message("Stopping media import after the current file")
        else:
            self.message("No media import is active")

    def _start_import(self, paths: list[str] | None = None, folder: str | None = None):
        if self.import_thread and self.import_thread.isRunning():
            self.message("A media import is already running")
            return
        self.import_thread = ImportThread(self.library, paths, folder)
        self.import_thread.completed.connect(self._import_complete)
        self.import_thread.progress.connect(lambda n: self.message(f"Indexed {n} media files..."))
        self.import_thread.start()
        self.message("Media catalog indexing started in the background")

    def _import_complete(self, count: int, errors: list):
        self.refresh_library()
        self.message(f"Imported {count} assets", errors)

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import media files", "",
            "Media (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.jpg *.jpeg *.png *.webp *.bmp)"
        )
        if paths:
            self._start_import(paths=paths)

    def import_folder(self):
        directory = QFileDialog.getExistingDirectory(self, "Scan media folder")
        if directory:
            self._start_import(folder=directory)

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

    def plan_ai_scenes(self):
        if self.ai_thread and self.ai_thread.isRunning():
            self.message("Local AI plan is already running")
            return
        self.ai_thread = AIPlanThread(self.script.toPlainText(), self.ai_model.text())
        self.ai_thread.ready.connect(self._ai_plan_ready)
        self.ai_thread.failed.connect(lambda error: self.message("Local AI: " + error[:250]))
        self.ai_thread.start()
        self.message("Local AI scene plan requested; current media remains unchanged")

    def _ai_plan_ready(self, scenes):
        self.history.checkpoint()
        self.scenes = scenes
        self.scene_page = 0
        self.populate_scenes()
        self._persist_scenes()
        self.message(f"AI proposed {len(scenes)} scenes — approval required before timeline placement")

    def import_script(self):
        path, _ = QFileDialog.getOpenFileName(self, "Import narration script", "", "Plain text (*.txt)")
        if path:
            try:
                self.script.setPlainText(Path(path).read_text(encoding="utf-8-sig"))
            except Exception as exc:
                QMessageBox.warning(self, "Script import", str(exc))

    def _persist_scenes(self, immediate: bool = False):
        self.project.scenes = [asdict(scene) for scene in self.scenes]
        self.project.revision += 1
        if immediate:
            self.autosave()
        else:
            self.save_timer.start()

    def _restore_scenes_from_project(self):
        self.scenes = []
        for record in self.project.scenes:
            if not isinstance(record,dict):
                continue
            try:
                self.scenes.append(Scene(**{k:v for k,v in record.items()
                                           if k in Scene.__dataclass_fields__}))
            except (ValueError,TypeError):
                continue
        self.scene_page = 0
        self.populate_scenes()

    def plan_scenes(self):
        self.history.checkpoint()
        self.scenes = create_scene_plan(self.script.toPlainText())
        self.scene_page = 0
        self.populate_scenes()
        self._persist_scenes()
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
        self.history.checkpoint()
        first = self.scene_page*5
        approved = 0
        for scene in self.scenes[first:first+5]:
            if scene.media_path:
                scene.approved = True
                scene.locked = True
                approved += 1
        self.populate_scenes()
        self._persist_scenes(immediate=True)
        self.message(f"Approved {approved} current-page media/scene assignments; review next five")

    def match_scenes(self):
        self.history.checkpoint()
        policies = ["local_first", "local_only", "alternate", "video_only", "image_only"]
        self.scenes = match_media(self.scenes, self.library,
                                  policies[self.source_policy.currentIndex()],
                                  self.reuse.isChecked(),
                                  auto_approve=self.scene_auto_approve.isChecked())
        self.populate_scenes()
        self._persist_scenes()
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
            self.history.checkpoint()
            rec = next(x for x in candidates if x["name"] == name)
            scene = self.scenes[index]
            scene.media_id, scene.media_path, scene.media_kind = rec["id"], rec["path"], rec["kind"]
            scene.approved = True
            scene.locked = True
            scene.match_reason = "Manually selected and locked"
            self.populate_scenes()
            self._persist_scenes(immediate=True)

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
        self.start_waveforms()

    def transcribe_voice(self):
        if self.speech_thread and self.speech_thread.isRunning():
            self.message("Whisper transcription is already running")
            return
        path, _ = QFileDialog.getOpenFileName(
            self,"Choose narration to transcribe locally","",
            "Narration (*.mp3 *.wav *.aac *.m4a *.mp4 *.mov *.mkv)"
        )
        if not path:
            return
        model, chosen = QInputDialog.getItem(
            self,"Local Whisper model","CPU model: tiny is quickest, small is most demanding",
            ["tiny","base","small"],0,False
        )
        if not chosen:
            return
        reply=QMessageBox.question(
            self,"Whisper Model Weights",
            "Use a locally cached Whisper model. If it is absent, do you "
            "explicitly authorize downloading model weights to this PC? "
            "Audio is processed locally and is not uploaded.",
            QMessageBox.StandardButton.Yes |
            QMessageBox.StandardButton.No |
            QMessageBox.StandardButton.Cancel,
            QMessageBox.StandardButton.No
        )
        if reply == QMessageBox.StandardButton.Cancel:
            return
        allow_download=(reply==QMessageBox.StandardButton.Yes)
        cache=app_directory() / "whisper-models"
        self.speech_thread=SpeechThread(path,model,cache,allow_download)
        self.speech_thread.stage.connect(self.message)
        self.speech_thread.failed.connect(
            lambda error: QMessageBox.warning(self,"Local Whisper",error))
        self.speech_thread.ready.connect(self._transcription_ready)
        self.speech_thread.start()
        self.message("Local Whisper CPU transcription initiated")

    def _transcription_ready(self, payload: dict):
        folder=app_directory() / "transcripts"
        folder.mkdir(parents=True,exist_ok=True)
        path=folder / (uuid.uuid4().hex + ".json")
        path.write_text(json.dumps(payload,ensure_ascii=False,indent=2),
                        encoding="utf-8")
        self.history.checkpoint()
        try:
            total=import_word_json(self.project,path)
        except Exception as exc:
            self.project=self.history.undo()
            self.history.project=self.project
            QMessageBox.warning(self,"Whisper captions",str(exc))
            return
        self.mark_changed()
        self.message(f"Local Whisper recognized {len(payload['words'])} words; "
                     f"created {total} editable karaoke phrases ({payload['language']})")

    def import_word_captions(self):
        path, _ = QFileDialog.getOpenFileName(
            self,"Import word-aligned Whisper transcript","","Whisper Word JSON (*.json)"
        )
        if not path:
            return
        self.history.checkpoint()
        try:
            count = import_word_json(self.project,path)
        except Exception as exc:
            self.project = self.history.undo()
            self.history.project = self.project
            QMessageBox.warning(self,"Word captions import",str(exc))
            return
        self.mark_changed()
        self.message(f"Imported {count} karaoke phrases with word-level timing")

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

    def start_waveforms(self):
        if self.waveform_thread and self.waveform_thread.isRunning():
            return
        sources = sorted({x.asset for x in self.project.items if x.kind=="audio"
                          and Path(x.asset).is_file()})
        pending = [src for src in sources if not waveform_path(src,self.waveform_dir).exists()]
        if pending:
            self.waveform_thread = WaveformThread(pending,self.waveform_dir)
            self.waveform_thread.ready.connect(lambda _path:self.timeline.redraw())
            self.waveform_thread.start()

    def redraw_timeline(self):
        self.media_lookup = {str(Path(r["path"]).resolve()):r
                             for r in self.library.list()}
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
        self.lut_path.setText(str(obj.effects.get("lut_file","")))
        self.noise_select.setCurrentText(str(obj.effects.get("grain_style","film")))
        self.source_audio_check.setEnabled(obj.kind == "video")
        self.source_audio_check.setChecked(bool(obj.effects.get("source_audio",False)))
        self.transition.setCurrentText(obj.transition_in)
        self.caption_text.setText(obj.text)
        count = sum(len(v) for v in obj.keyframes.values())
        self.keyframes_info.setText(f"{count} saved clip-local animation keyframes")

    def add_keyframe(self):
        if not self.selected_id:
            self.message("Select a timeline clip for keyframe editing")
            return
        clip = self.project.item(self.selected_id)
        if clip.kind not in {"image","video"}:
            self.message("Zoom/color keyframes require image or video clips")
            return
        at = self.playhead_ms - clip.start_ms
        if not 0 <= at <= clip.duration_ms:
            self.message("Move playhead inside the selected clip to add a keyframe")
            return
        prop = self.keyframe_property.currentText()
        value = {
            "zoom": self.zoom_spin.value()/100,
            "brightness": self.brightness_spin.value()/100,
            "saturation": self.saturation_spin.value()/100,
        }[prop]
        try:
            changed = set_keyframe(clip.keyframes,prop,int(at),value,clip.duration_ms)
            self.history.checkpoint()
            clip.keyframes = changed
            self.project.revision += 1
            self.mark_changed()
            self.message(f"Saved {prop} keyframe at {at/1000:.2f}s of selected clip")
        except ValueError as exc:
            QMessageBox.warning(self,"Invalid keyframe",str(exc))

    def delete_keyframe(self):
        if not self.selected_id:
            return
        clip = self.project.item(self.selected_id)
        prop = self.keyframe_property.currentText()
        frames = clip.keyframes.get(prop,[])
        if not frames:
            self.message("No keyframes for this property")
            return
        labels = [f"{x['at_ms']/1000:.3f}s | {x['value']:.3f}" for x in frames]
        choice, yes = QInputDialog.getItem(
            self,"Remove a clip keyframe","Choose keyframe",labels,0,False
        )
        if yes:
            at = frames[labels.index(choice)]["at_ms"]
            self.history.checkpoint()
            clip.keyframes = remove_keyframe(clip.keyframes,prop,at)
            self.project.revision += 1
            self.mark_changed()

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
                                 "source_audio": self.source_audio_check.isChecked() if item.kind=="video" else False,
                                 "lut_file": self.lut_path.text().strip()})
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
        self._restore_scenes_from_project()
        self.selected_id = ""
        self.mark_changed()

    def redo(self):
        self.project = self.history.redo()
        self._restore_scenes_from_project()
        self.selected_id = ""
        self.mark_changed()

    def mark_changed(self):
        self.redraw_timeline()
        self.save_timer.start()
        if self.gpu_active and self.gpu_canvas:
            self.preview_timer.stop()
            self._stop_gpu_audio()
            self.gpu_canvas.set_project(self.project)
            self.gpu_canvas.seek(self.playhead_ms)
        else:
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
        if self.gpu_canvas:
            self.gpu_canvas.pause()
        self.project = StudioProject()
        self.history = EditHistory(self.project)
        self.scenes = []
        self.selected_id = ""
        self.project_path = None
        self.playhead_ms = 0
        self.script.setPlainText("")
        self.populate_scenes()
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
                self._restore_scenes_from_project()
                self.script.setPlainText("\n".join(x.text for x in self.scenes))
                self.redraw_timeline()
                if self.gpu_canvas:
                    self.gpu_canvas.set_project(self.project)
                    self.gpu_canvas.seek(0)
                self.start_waveforms()
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
        if (not self.gpu_active and status == QMediaPlayer.MediaStatus.EndOfMedia
                and self.project.duration_ms > 0):
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

    def preview_quality_changed(self, _index: int):
        if not self.gpu_active:
            self.preview_timer.start()

    def set_preview_backend(self, index: int):
        if index != 0:
            self._stop_gpu_audio()
            self.gpu_active = False
            self.preview_timer.stop()
            if self.gpu_canvas:
                self.gpu_canvas.pause()
            self.preview_stack.setCurrentWidget(self.video)
            side=self.cpu_profile.currentData()
            self.preview_mode_status.setText(
                f"CPU Proxy {side}p (long side): FFmpeg effects/audio; export stays full-resolution")
            return
        if self.gpu_canvas is None:
            try:
                self.gpu_canvas = OpenGLTimelineCanvas(self)
                self.gpu_canvas.positionChanged.connect(self._on_gpu_position)
                self.gpu_canvas.playbackStopped.connect(self.gpu_audio_player.stop)
                self.gpu_canvas.rendererDetected.connect(self._on_gl_renderer)
                self.gpu_canvas.previewError.connect(
                    lambda msg:self.statusBar().showMessage("GPU preview: "+msg[:150]))
                self.preview_stack.addWidget(self.gpu_canvas)
            except (ImportError,RuntimeError) as exc:
                self._fallback_from_gpu("GPU preview unavailable: "+str(exc))
                return
        self.player.stop()
        self.preview_timer.stop()
        self.gpu_active = True
        self.preview_stack.setCurrentWidget(self.gpu_canvas)
        self.gpu_canvas.set_project(self.project)
        self.gpu_canvas.seek(self.playhead_ms)
        self.preview_mode_status.setText(
            "GPU Live — OpenGL visuals, CPU decode and independently mixed audio; "
            "use FFmpeg Accurate for complete effects parity"
        )
        QTimer.singleShot(1200,self._verify_gpu_context)

    def _fallback_from_gpu(self,reason: str):
        self._stop_gpu_audio()
        self.gpu_active=False
        self.preview_backend.blockSignals(True)
        self.preview_backend.setCurrentIndex(1)
        self.preview_backend.blockSignals(False)
        if self.gpu_canvas:
            self.gpu_canvas.pause()
        self.preview_stack.setCurrentWidget(self.video)
        self.preview_mode_status.setText(reason+" — FFmpeg Accurate selected")
        self.statusBar().showMessage(reason)

    def _verify_gpu_context(self):
        if not self.gpu_active or not self.gpu_canvas:
            return
        if not self.gpu_canvas.isValid():
            self._fallback_from_gpu("GPU/OpenGL context creation failed")
            return
        if not self.gpu_canvas.is_hardware():
            self._fallback_from_gpu("GPU renderer unverified or software-only")

    def _on_gl_renderer(self,renderer: str,vendor: str,hardware: bool):
        label=("Hardware candidate" if hardware else "Software/unknown")
        self.statusBar().showMessage(f"Live OpenGL: {label} | {vendor} | {renderer}")

    def _on_gpu_position(self,position: int):
        if not self.gpu_active:
            return
        self.playhead_ms=position
        self.seek.blockSignals(True)
        self.seek.setValue(position)
        self.seek.blockSignals(False)
        self.clock.setText(f"{human(position)} / {human(self.project.duration_ms)}")
        self.timeline.move_playhead(position)
        if (self.gpu_canvas and self.gpu_canvas.playing and
                has_timeline_audio(self.project)):
            left,right=self.gpu_audio_range
            if not left <= position < right-100:
                self._queue_gpu_audio(position)
            elif (self.gpu_audio_player.playbackState()
                    == QMediaPlayer.PlaybackState.PlayingState and
                    time.monotonic()-self._gpu_audio_last_sync>.7):
                target=max(0,position-left)
                if abs(self.gpu_audio_player.position()-target)>260:
                    self.gpu_audio_player.setPosition(target)
                self._gpu_audio_last_sync=time.monotonic()

    def _stop_gpu_audio(self):
        self.gpu_audio_generation+=1
        self.gpu_audio_player.stop()
        self.gpu_audio_range=(0,0)
        self.gpu_audio_file=""
        if self.gpu_audio_job and self.gpu_audio_job.isRunning():
            self.gpu_audio_job.stop_event.set()

    def _queue_gpu_audio(self,start_ms: int):
        if not self.gpu_active or not has_timeline_audio(self.project):
            return
        if self.gpu_audio_job and self.gpu_audio_job.isRunning():
            return
        start,end=audio_window(self.project,start_ms)
        if not audio_active_between(self.project,start,end):
            # Treat a silent gap as a covered window, so no busy polling.
            self.gpu_audio_range=(start,end)
            return
        self.gpu_audio_generation+=1
        target=app_directory() / "gpu-preview-audio" / (uuid.uuid4().hex+".m4a")
        thread=GPUAudioMixThread(self.project,start_ms,target,self.gpu_audio_generation)
        self.gpu_audio_job=thread
        thread.ready.connect(self._on_gpu_audio_ready)
        thread.failed.connect(lambda err:self.statusBar().showMessage(
            "GPU audio preview unavailable: "+err[:180]))
        thread.finished.connect(self._on_gpu_audio_finished)
        thread.start()

    def _on_gpu_audio_finished(self):
        if (self.gpu_active and self.gpu_canvas and self.gpu_canvas.playing
                and has_timeline_audio(self.project)):
            left,right=self.gpu_audio_range
            if not left<=self.playhead_ms<right-100:
                QTimer.singleShot(50,lambda:self._queue_gpu_audio(self.playhead_ms))

    def _on_gpu_audio_ready(self,filename: str,start: int,end: int,generation: int):
        if generation!=self.gpu_audio_generation or not self.gpu_active:
            return
        self.gpu_audio_range=(start,end)
        self.gpu_audio_file=filename
        self.gpu_audio_player.stop()
        self.gpu_audio_player.setSource(QUrl.fromLocalFile(filename))
        self._prune_gpu_audio_files(filename)

    def _on_gpu_audio_loaded(self,status):
        if (status not in (QMediaPlayer.MediaStatus.LoadedMedia,
                           QMediaPlayer.MediaStatus.BufferedMedia)
                or not self.gpu_active or not self.gpu_canvas
                or not self.gpu_canvas.playing):
            return
        left,right=self.gpu_audio_range
        if left<=self.playhead_ms<right:
            self.gpu_audio_player.setPosition(self.playhead_ms-left)
            self.gpu_audio_player.play()

    def _prune_gpu_audio_files(self,active_file: str):
        directory=app_directory() / "gpu-preview-audio"
        files=sorted(directory.glob("*.m4a"),key=lambda p:p.stat().st_mtime)
        for stale in files[:-8]:
            if str(stale)!=active_file and stale.is_file() and not stale.is_symlink():
                try:
                    stale.unlink()
                except OSError:
                    pass

    def show_preview_diagnostics(self):
        if not self.gpu_canvas:
            QMessageBox.information(self,"GPU Preview","Switch to GPU Live to inspect the actual OpenGL renderer")
            return
        stats=self.gpu_canvas.diagnostics()
        stats["audio"]=("20-second sliding FFmpeg mix, aligned to GPU playhead"
                         if has_timeline_audio(self.project) else "no active audio tracks")
        result="\n".join(f"{key}: {value}" for key,value in stats.items())
        QMessageBox.information(self,"GPU Preview Diagnostic (current PC)",result)

    def refresh_preview(self):
        if self.gpu_active and self.gpu_canvas:
            self.gpu_canvas.set_project(self.project)
            self.gpu_canvas.seek(self.playhead_ms)
        else:
            self.render_preview()

    def scrub(self):
        self.playhead_ms = self.seek.value()
        if self.gpu_active and self.gpu_canvas:
            self._stop_gpu_audio()
            self.gpu_canvas.seek(self.playhead_ms)
            if self.gpu_canvas.playing:
                self._queue_gpu_audio(self.playhead_ms)
        else:
            self.redraw_timeline()
            self.preview_timer.start()

    def toggle_preview(self):
        if self.gpu_active and self.gpu_canvas:
            if self.gpu_canvas.playing:
                self.gpu_canvas.pause()
                self.gpu_audio_player.pause()
            else:
                self.gpu_canvas.play()
                left,right=self.gpu_audio_range
                if (self.gpu_audio_file and left<=self.playhead_ms<right):
                    self.gpu_audio_player.setPosition(self.playhead_ms-left)
                    self.gpu_audio_player.play()
                else:
                    self._queue_gpu_audio(self.playhead_ms)
            return
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        elif self._preview_output:
            self.player.play()
        else:
            self.render_preview()

    def render_preview(self):
        if self.gpu_active and self.gpu_canvas:
            self.gpu_canvas.seek(self.playhead_ms)
            return
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
        self.worker = RenderThread(self.project, filename, cache, preview=True,
                                   window=(start,end),
                                   preview_side=int(self.cpu_profile.currentData() or 360))
        self.worker.done.connect(self._preview_ready)
        self.worker.failed.connect(lambda err: self.message("Preview: " + err[:180]))
        self.worker.finished.connect(self._preview_finish)
        self.worker.start()
        self.message(f"CPU proxy {self.cpu_profile.currentData()}p preview (cached chunks)...")

    def _preview_ready(self, filename: str):
        self._preview_output = filename
        self._prune_preview_files(filename)
        if self.gpu_active:
            # Completed stale FFmpeg visual proxies must not play audio behind GPU mode.
            self.player.stop()
            return
        self.player.stop()
        self.player.setSource(QUrl.fromLocalFile(filename))
        self.player.play()
        self.message("Preview ready (low-resolution cached composition)")

    def _prune_preview_files(self, active_file: str):
        # Only our app-generated short previews; never user's input media.
        folder = app_directory() / "previews"
        files = sorted((p for p in folder.glob("*.mp4") if p.is_file()
                        and not p.is_symlink()),key=lambda p: p.stat().st_mtime)
        for candidate in files[:-20]:
            if str(candidate) != str(active_file):
                try:
                    candidate.unlink()
                except OSError:
                    pass

    def _preview_finish(self):
        if self.preview_pending:
            self.preview_pending = False
            if not self.gpu_active:
                self.preview_timer.start()

    def open_last_export(self):
        if self.last_export and self.last_export.is_file():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(self.last_export)))
        else:
            self.message("No completed export in this session")

    def _on_export_done(self, dest: str):
        self.last_export = Path(dest)
        QMessageBox.information(self, "Export complete",
                                f"Verified new video saved:\n{dest}\n"
                                "Use Open Last Video to play the MP4.")
        self.message("Export complete: " + dest)

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
        self.worker.progress.connect(lambda n, msg: self.message(f"Export {n}% | {msg}"))
        self.worker.done.connect(self._on_export_done)
        self.worker.failed.connect(lambda msg: QMessageBox.warning(self, "Export error", msg))
        self.worker.start()
        self.message("Export started; original media will not be modified")

    def closeEvent(self, event):
        if self.worker and self.worker.isRunning():
            self.message("Finish export/preview before closing the Studio")
            event.ignore()
            return
        if self.speech_thread and self.speech_thread.isRunning():
            self.message("Local Whisper transcription is active; close when it finishes")
            event.ignore()
            return
        if self.ai_thread and self.ai_thread.isRunning():
            self.message("Local AI planning is active; close after it completes")
            event.ignore()
            return
        if self.import_thread and self.import_thread.isRunning():
            self.message("Media import is active; complete or cancel import before exiting")
            event.ignore()
            return
        if self.waveform_thread and self.waveform_thread.isRunning():
            if not self.waveform_thread.wait(5000):
                self.message("Audio waveforms are still building")
                event.ignore()
                return
        if self.thumbnail_thread and self.thumbnail_thread.isRunning():
            if not self.thumbnail_thread.wait(5000):
                self.message("Thumbnails are still building; close after they finish")
                event.ignore()
                return
        self.autosave()
        self.player.stop()
        self._stop_gpu_audio()
        if self.gpu_audio_job and self.gpu_audio_job.isRunning():
            if not self.gpu_audio_job.wait(5000):
                self.message("Audio preview is stopping; close when it finishes")
                event.ignore()
                return
        if self.gpu_canvas:
            self.gpu_canvas.shutdown()
        super().closeEvent(event)
