"""Initial native desktop UI: media, editable cut timeline, preview and export.

Milestone 1 is deliberately cut-based. Advanced multitrack compositing, exact
preview/export parity for LUTs, speech alignment and effects are not claimed.
"""
from __future__ import annotations

from pathlib import Path
import threading
import time

from PySide6.QtCore import Qt, QTimer, QUrl, Signal, QThread
from PySide6.QtGui import QAction, QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QComboBox, QDoubleSpinBox, QFileDialog, QFormLayout,
    QHBoxLayout, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QMessageBox, QProgressDialog, QPushButton, QSlider, QSplitter,
    QStackedWidget, QStatusBar, QVBoxLayout, QWidget, QAbstractItemView,
)
from PySide6.QtCore import QStandardPaths

from .core import Project, load_project, save_project
from .export import export_mp4
from .media import duration_ms


def timestamp(ms: int) -> str:
    value = max(0, ms) // 1000
    return f"{value // 60:02}:{value % 60:02}"


class TimelineList(QListWidget):
    moved = Signal()

    def __init__(self):
        super().__init__()
        self.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)

    def dropEvent(self, event):
        super().dropEvent(event)
        if event.isAccepted():
            self.moved.emit()


class ExportThread(QThread):
    changed = Signal(int, str)
    completed = Signal(str)
    failed = Signal(str)

    def __init__(self, project: Project, destination: str):
        super().__init__()
        self.project = Project.from_dict(project.to_dict())
        self.destination = destination
        self.stop_flag = threading.Event()

    def cancel(self):
        self.stop_flag.set()

    def run(self):
        try:
            result = export_mp4(
                self.project, self.destination,
                progress=lambda n, msg: self.changed.emit(n, msg),
                stop=self.stop_flag,
            )
            self.completed.emit(str(result))
        except Exception as exc:
            self.failed.emit(str(exc))


class EditorWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.project = Project()
        self.project_path: Path | None = None
        self.current_index = -1
        self.playing = False
        self._pending_seek = None
        self._changing_ui = False
        self._last_tick = time.monotonic()
        self._export_thread: ExportThread | None = None
        self.setWindowTitle("Scene Desktop Studio — Untitled")
        self.resize(1400, 850)
        self.setMinimumSize(940, 620)
        self.setStatusBar(QStatusBar(self))

        self.audio_out = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio_out)
        self.narration_out = QAudioOutput(self)
        self.narration_player = QMediaPlayer(self)
        self.narration_player.setAudioOutput(self.narration_out)
        self.narration_out.setVolume(0.85)
        self.player.positionChanged.connect(self._on_video_position)
        self.player.mediaStatusChanged.connect(self._on_media_status)

        self._build_actions()
        self._build_ui()
        self.tick = QTimer(self)
        self.tick.setInterval(80)
        self.tick.timeout.connect(self._tick)
        self.tick.start()
        self.autosave = QTimer(self)
        self.autosave.setSingleShot(True)
        self.autosave.setInterval(1500)
        self.autosave.timeout.connect(self._save_recovery)
        self._refresh()
        self.statusBar().showMessage("Import video or images to start. Originals are never edited.")

    def _build_actions(self):
        bar = self.menuBar().addMenu("&Project")
        for title, handler, shortcut in [
            ("New Project", self.new_project, "Ctrl+N"),
            ("Open Project", self.open_project, "Ctrl+O"),
            ("Save Project", self.save_project_as, "Ctrl+S"),
            ("Recover Autosave", self.recover_project, ""),
            ("Export MP4", self.export_video, "Ctrl+E"),
        ]:
            a = QAction(title, self)
            a.triggered.connect(handler)
            if shortcut:
                a.setShortcut(shortcut)
            bar.addAction(a)

    def _build_ui(self):
        root = QSplitter(Qt.Orientation.Horizontal)
        root.setChildrenCollapsible(False)
        self.setCentralWidget(root)

        library_box = QWidget()
        library_layout = QVBoxLayout(library_box)
        library_layout.addWidget(QLabel("<b>MEDIA LIBRARY</b>"))
        library_layout.addWidget(QLabel("Local files used in this project"))
        self.library = QListWidget()
        library_layout.addWidget(self.library, 1)
        import_button = QPushButton("+ Import images/videos")
        import_button.clicked.connect(self.import_media)
        library_layout.addWidget(import_button)
        library_layout.addWidget(QLabel("<b>NARRATION</b>"))
        self.narration_label = QLabel("No narration selected")
        self.narration_label.setWordWrap(True)
        library_layout.addWidget(self.narration_label)
        narration_btn = QPushButton("Choose narration WAV/MP3")
        narration_btn.clicked.connect(self.choose_narration)
        library_layout.addWidget(narration_btn)
        root.addWidget(library_box)

        middle = QSplitter(Qt.Orientation.Vertical)
        middle.setChildrenCollapsible(False)
        root.addWidget(middle)

        preview_pane = QWidget()
        preview_layout = QVBoxLayout(preview_pane)
        header = QHBoxLayout()
        header.addWidget(QLabel("<b>LIVE PREVIEW — CUT TIMELINE MVP</b>"), 1)
        self.aspect = QComboBox()
        self.aspect.addItems(["1080p · 16:9", "1080p · 9:16", "720p · 16:9", "720p · 9:16"])
        self.aspect.currentIndexChanged.connect(self._change_aspect)
        header.addWidget(self.aspect)
        preview_layout.addLayout(header)

        self.preview_stack = QStackedWidget()
        self.image_preview = QLabel("Add media to view")
        self.image_preview.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image_preview.setStyleSheet("background:#121820;color:#cad6e5;font-size:18px;")
        self.image_preview.setMinimumHeight(170)
        self.video_preview = QVideoWidget()
        self.preview_stack.addWidget(self.image_preview)
        self.preview_stack.addWidget(self.video_preview)
        self.player.setVideoOutput(self.video_preview)
        preview_layout.addWidget(self.preview_stack, 1)
        controls = QHBoxLayout()
        self.play_button = QPushButton("▶ Play")
        self.play_button.clicked.connect(self.toggle_play)
        controls.addWidget(self.play_button)
        controls.addWidget(QLabel("Timeline"))
        self.seek_slider = QSlider(Qt.Orientation.Horizontal)
        self.seek_slider.setRange(0, 0)
        self.seek_slider.sliderReleased.connect(self._seek_from_slider)
        controls.addWidget(self.seek_slider, 1)
        self.clock = QLabel("00:00 / 00:00")
        controls.addWidget(self.clock)
        preview_layout.addLayout(controls)
        middle.addWidget(preview_pane)

        timeline_box = QWidget()
        timeline_layout = QVBoxLayout(timeline_box)
        timeline_layout.addWidget(QLabel("<b>V1 — EDITABLE VIDEO / IMAGE TIMELINE</b>"))
        timeline_layout.addWidget(QLabel("Drag clips up/down to reorder; select a clip to trim or split."))
        self.timeline = TimelineList()
        self.timeline.moved.connect(self._sync_reorder)
        self.timeline.currentItemChanged.connect(self._selection_changed)
        timeline_layout.addWidget(self.timeline, 1)
        tools = QHBoxLayout()
        for title, handler in [
            ("Split at Playhead", self.split_selected),
            ("Remove Clip", self.remove_selected),
            ("Save", self.save_project_as),
            ("Export MP4", self.export_video),
        ]:
            btn = QPushButton(title)
            btn.clicked.connect(handler)
            tools.addWidget(btn)
        timeline_layout.addLayout(tools)
        middle.addWidget(timeline_box)

        inspector = QWidget()
        inspector_layout = QVBoxLayout(inspector)
        inspector_layout.addWidget(QLabel("<b>CLIP INSPECTOR</b>"))
        self.info_label = QLabel("Choose a timeline clip")
        self.info_label.setWordWrap(True)
        inspector_layout.addWidget(self.info_label)
        form = QFormLayout()
        self.trim_in = QDoubleSpinBox()
        self.trim_out = QDoubleSpinBox()
        for spin in (self.trim_in, self.trim_out):
            spin.setDecimals(2)
            spin.setSingleStep(0.1)
            spin.setRange(0, 360000)
            spin.setSuffix(" sec")
        form.addRow("Source in", self.trim_in)
        form.addRow("Source out", self.trim_out)
        inspector_layout.addLayout(form)
        apply_trim = QPushButton("Apply Trim")
        apply_trim.clicked.connect(self.apply_trim)
        inspector_layout.addWidget(apply_trim)
        inspector_layout.addWidget(QLabel("<b>PROJECT</b>"))
        self.summary = QLabel()
        self.summary.setWordWrap(True)
        inspector_layout.addWidget(self.summary)
        inspector_layout.addWidget(QLabel(
            "Milestone 1: cut timeline and MP4 export. Advanced transitions, "
            "LUTs, multitrack audio mixing and source-video audio export are pending."
        ))
        inspector_layout.addStretch()
        root.addWidget(inspector)
        root.setSizes([250, 860, 280])
        middle.setSizes([470, 330])

    def _mark_changed(self):
        self.setWindowTitle(f"Scene Desktop Studio — {self.project.name} •")
        self.autosave.start()

    def _refresh(self, selected_id: str | None = None):
        old_block = self.timeline.blockSignals(True)
        self.timeline.clear()
        for idx, clip in enumerate(self.project.clips):
            item = QListWidgetItem(
                f"{idx + 1:03d}   {'▣' if clip.kind == 'video' else '▧'}  "
                f"{Path(clip.path).name}   {clip.duration_ms / 1000:.2f}s"
            )
            item.setData(Qt.ItemDataRole.UserRole, clip.id)
            if not Path(clip.path).is_file():
                item.setText(item.text() + "  [MISSING]")
            self.timeline.addItem(item)
        self.timeline.blockSignals(old_block)

        self.library.clear()
        for src in sorted({c.path for c in self.project.clips}):
            self.library.addItem(Path(src).name + (" [MISSING]" if not Path(src).exists() else ""))
        self.seek_slider.setMaximum(max(0, self.project.duration_ms))
        self.summary.setText(
            f"{len(self.project.clips)} clips | {timestamp(self.project.duration_ms)}\n"
            f"{self.project.width}×{self.project.height} at {self.project.fps} FPS"
        )
        self.narration_label.setText(
            Path(self.project.narration).name if self.project.narration else "No narration selected"
        )
        index = next((i for i, c in enumerate(self.project.clips) if c.id == selected_id), 0)
        if self.project.clips:
            self.timeline.setCurrentRow(index)
            self._show_properties(index)
            if self.current_index != index:
                self._load_clip(index, 0)
        else:
            self.current_index = -1
            self.player.stop()
            self.preview_stack.setCurrentWidget(self.image_preview)
            self.image_preview.setText("Add media to view")
            self.info_label.setText("Choose a timeline clip")
            self.clock.setText("00:00 / 00:00")
        self.aspect.blockSignals(True)
        self.aspect.setCurrentIndex(
            {(1920, 1080): 0, (1080, 1920): 1, (1280, 720): 2, (720, 1280): 3}[
                (self.project.width, self.project.height)
            ]
        )
        self.aspect.blockSignals(False)

    def import_media(self):
        paths, _ = QFileDialog.getOpenFileNames(
            self, "Import source media", "", "Media (*.mp4 *.mov *.mkv *.webm *.m4v *.avi *.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not paths:
            return
        count, errors = 0, []
        for path in paths:
            try:
                self.project.add_media(path, duration_ms(path))
                count += 1
            except Exception as exc:
                errors.append(f"{Path(path).name}: {exc}")
        if count:
            self._mark_changed()
            self._refresh(self.project.clips[-1].id)
        if errors:
            QMessageBox.warning(self, "Import problems", "\n".join(errors[:12]))
        self.statusBar().showMessage(f"Imported {count} media items")

    def choose_narration(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose voice-over", "", "Audio (*.wav *.mp3 *.m4a *.aac)")
        if path:
            self.project.narration = str(Path(path).resolve())
            self.narration_player.setSource(QUrl.fromLocalFile(self.project.narration))
            self._mark_changed()
            self._refresh(self._current_clip_id())

    def _current_clip_id(self):
        item = self.timeline.currentItem()
        return item.data(Qt.ItemDataRole.UserRole) if item else None

    def _selection_changed(self, current, _previous):
        if self._changing_ui or current is None:
            return
        clip_id = current.data(Qt.ItemDataRole.UserRole)
        idx = next((i for i, c in enumerate(self.project.clips) if c.id == clip_id), -1)
        if idx >= 0:
            self._show_properties(idx)
            self.seek_global(self.project.start_of(idx))

    def _show_properties(self, idx: int):
        if idx < 0 or idx >= len(self.project.clips):
            return
        clip = self.project.clips[idx]
        self.info_label.setText(f"{Path(clip.path).name}\n{clip.kind.upper()} | Source {clip.source_duration_ms / 1000:.2f}s")
        self.trim_in.setMaximum(clip.source_duration_ms / 1000)
        self.trim_out.setMaximum(clip.source_duration_ms / 1000)
        self.trim_in.setValue(clip.in_ms / 1000)
        self.trim_out.setValue(clip.out_ms / 1000)

    def apply_trim(self):
        idx = self.timeline.currentRow()
        if idx < 0:
            return
        clip = self.project.clips[idx]
        try:
            clip.trim(round(self.trim_in.value() * 1000), round(self.trim_out.value() * 1000))
        except ValueError as exc:
            QMessageBox.warning(self, "Invalid trim", str(exc))
            return
        self._mark_changed()
        self._refresh(clip.id)
        self.seek_global(self.project.start_of(idx))

    def split_selected(self):
        idx = self.timeline.currentRow()
        if idx < 0:
            return
        clip = self.project.clips[idx]
        local = self.seek_slider.value() - self.project.start_of(idx)
        try:
            _, right = self.project.split(idx, clip.in_ms + local)
        except ValueError as exc:
            QMessageBox.warning(self, "Cannot split here", str(exc))
            return
        self._mark_changed()
        self._refresh(right.id)
        self.seek_global(self.project.start_of(idx + 1))

    def remove_selected(self):
        idx = self.timeline.currentRow()
        if idx < 0:
            return
        self.pause()
        self.project.clips.pop(idx)
        self._mark_changed()
        self.current_index = -1
        self._refresh()

    def _sync_reorder(self):
        order = [self.timeline.item(i).data(Qt.ItemDataRole.UserRole)
                 for i in range(self.timeline.count())]
        try:
            self.project.reorder(order)
        except ValueError as exc:
            QMessageBox.warning(self, "Reorder failed", str(exc))
            self._refresh()
            return
        self.pause()
        self._mark_changed()
        self.current_index = -1
        self._refresh(self._current_clip_id())
        self.seek_global(0)

    def _change_aspect(self, index):
        sizes = [(1920, 1080), (1080, 1920), (1280, 720), (720, 1280)]
        if index < 0:
            return
        self.project.width, self.project.height = sizes[index]
        self._mark_changed()
        self.summary.setText(
            f"{len(self.project.clips)} clips | {timestamp(self.project.duration_ms)}\n"
            f"{self.project.width}×{self.project.height} at {self.project.fps} FPS"
        )

    def seek_global(self, ms: int):
        if not self.project.clips:
            return
        idx, offset = self.project.locate(ms)
        if idx != self.current_index:
            self._load_clip(idx, offset)
        else:
            clip = self.project.clips[idx]
            if clip.kind == "video":
                self.player.setPosition(clip.in_ms + offset)
            self._last_tick = time.monotonic()
        self._display_time(self.project.start_of(idx) + offset)
        if self.project.narration:
            self.narration_player.setPosition(self.project.start_of(idx) + offset)

    def _seek_from_slider(self):
        self.seek_global(self.seek_slider.value())

    def _load_clip(self, idx: int, offset: int):
        if not 0 <= idx < len(self.project.clips):
            return
        clip = self.project.clips[idx]
        self.current_index = idx
        self._last_tick = time.monotonic()
        self.player.stop()
        if clip.kind == "image":
            self.preview_stack.setCurrentWidget(self.image_preview)
            pix = QPixmap(clip.path)
            if pix.isNull():
                self.image_preview.setText("Image unavailable: " + Path(clip.path).name)
            else:
                self.image_preview.setPixmap(
                    pix.scaled(960, 520, Qt.AspectRatioMode.KeepAspectRatio,
                               Qt.TransformationMode.SmoothTransformation)
                )
        else:
            self.preview_stack.setCurrentWidget(self.video_preview)
            self._pending_seek = clip.in_ms + offset
            self.player.setSource(QUrl.fromLocalFile(clip.path))
            self.player.setPosition(self._pending_seek)
            if self.playing:
                self.player.play()
        self._changing_ui = True
        self.timeline.setCurrentRow(idx)
        self._changing_ui = False
        self._show_properties(idx)

    def _on_media_status(self, status):
        if self.current_index < 0:
            return
        clip = self.project.clips[self.current_index]
        if clip.kind != "video":
            return
        if status == QMediaPlayer.MediaStatus.LoadedMedia and self._pending_seek is not None:
            self.player.setPosition(self._pending_seek)
            self._pending_seek = None
            if self.playing:
                self.player.play()
        if status == QMediaPlayer.MediaStatus.EndOfMedia and self.playing:
            self._advance()

    def _on_video_position(self, pos):
        if self.current_index < 0 or not self.project.clips:
            return
        clip = self.project.clips[self.current_index]
        if clip.kind != "video" or self._pending_seek is not None:
            return
        if pos < clip.in_ms:
            return
        offset = max(0, pos - clip.in_ms)
        if offset >= clip.duration_ms and self.playing:
            self._advance()
            return
        self._display_time(self.project.start_of(self.current_index) + min(offset, clip.duration_ms))

    def _tick(self):
        if not self.playing or self.current_index < 0:
            return
        clip = self.project.clips[self.current_index]
        now = time.monotonic()
        delta = int((now - self._last_tick) * 1000)
        self._last_tick = now
        if clip.kind == "image":
            idx, offset = self.project.locate(self.seek_slider.value())
            if idx != self.current_index:
                return
            if offset + delta >= clip.duration_ms:
                self._advance()
            else:
                self._display_time(self.project.start_of(idx) + offset + delta)

    def _advance(self):
        next_index = self.current_index + 1
        if next_index >= len(self.project.clips):
            self.pause()
            self._display_time(self.project.duration_ms)
            return
        self._load_clip(next_index, 0)
        self._display_time(self.project.start_of(next_index))

    def _display_time(self, ms: int):
        self.seek_slider.blockSignals(True)
        self.seek_slider.setValue(ms)
        self.seek_slider.blockSignals(False)
        self.clock.setText(f"{timestamp(ms)} / {timestamp(self.project.duration_ms)}")

    def toggle_play(self):
        if not self.project.clips:
            return
        if self.playing:
            self.pause()
            return
        self.playing = True
        self._last_tick = time.monotonic()
        self.play_button.setText("❚❚ Pause")
        if self.current_index < 0:
            self._load_clip(0, 0)
        if self.project.clips[self.current_index].kind == "video":
            self.player.play()
        if self.project.narration:
            self.narration_player.setPosition(self.seek_slider.value())
            self.narration_player.play()

    def pause(self):
        self.playing = False
        self.player.pause()
        self.narration_player.pause()
        self.play_button.setText("▶ Play")

    def new_project(self):
        if self._export_thread and self._export_thread.isRunning():
            QMessageBox.warning(self, "Export active", "Finish or cancel export before switching projects")
            return
        self.pause()
        self.project = Project()
        self.project_path = None
        self.current_index = -1
        self.player.stop()
        self.narration_player.stop()
        self._refresh()
        self._mark_changed()

    def open_project(self):
        if self._export_thread and self._export_thread.isRunning():
            QMessageBox.warning(self, "Export active", "Finish or cancel export before switching projects")
            return
        path, _ = QFileDialog.getOpenFileName(self, "Open desktop project", "", "Scene Desktop Projects (*.sdsproj)")
        if path:
            self._open_path(Path(path))

    def _open_path(self, path: Path):
        try:
            project = load_project(path)
        except Exception as exc:
            QMessageBox.critical(self, "Cannot open project", str(exc))
            return
        self.pause()
        self.project = project
        self.project_path = path
        self.current_index = -1
        self._refresh()
        if self.project.narration and Path(self.project.narration).is_file():
            self.narration_player.setSource(QUrl.fromLocalFile(self.project.narration))
        missing = sum(not Path(c.path).is_file() for c in self.project.clips)
        self.setWindowTitle(f"Scene Desktop Studio — {self.project.name}")
        self.statusBar().showMessage(f"Opened {path.name}; {missing} missing source files")

    def save_project_as(self):
        if self.project_path is None:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save editable project", self.project.name + ".sdsproj",
                "Scene Desktop Projects (*.sdsproj)"
            )
            if not path:
                return
            self.project_path = Path(path).with_suffix(".sdsproj")
        try:
            save_project(self.project, self.project_path)
            self.setWindowTitle(f"Scene Desktop Studio — {self.project.name}")
            self.statusBar().showMessage(f"Saved project: {self.project_path}")
        except Exception as exc:
            QMessageBox.critical(self, "Save failed", str(exc))

    def _recovery_path(self):
        base = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppDataLocation)
        return Path(base or str(Path.home() / ".scene-desktop-studio")) / "recovery.sdsproj"

    def _save_recovery(self):
        try:
            save_project(self.project, self._recovery_path())
        except Exception as exc:
            self.statusBar().showMessage(f"Autosave failed: {exc}")

    def recover_project(self):
        path = self._recovery_path()
        if not path.exists():
            QMessageBox.information(self, "Recovery", "No autosave is available")
            return
        self._open_path(path)
        self.project_path = None
        self._mark_changed()

    def export_video(self):
        if not self.project.clips:
            QMessageBox.warning(self, "Nothing to export", "Import media first")
            return
        if self._export_thread and self._export_thread.isRunning():
            return
        path, _ = QFileDialog.getSaveFileName(self, "Export new MP4", "", "MP4 Video (*.mp4)")
        if not path:
            return
        destination = str(Path(path).with_suffix(".mp4"))
        self._export_thread = ExportThread(self.project, destination)
        progress = QProgressDialog("Preparing export", "Cancel", 0, 100, self)
        progress.setWindowModality(Qt.WindowModality.NonModal)
        progress.setAutoClose(False)
        progress.setValue(0)
        progress.canceled.connect(self._export_thread.cancel)
        def show_progress(value, message):
            progress.setLabelText(message)
            progress.setValue(value)
        def done(result):
            progress.setValue(100)
            progress.close()
            self.statusBar().showMessage(f"Export complete: {result}")
            QMessageBox.information(self, "Export ready", "MP4 created:\n" + result)
        def failed(message):
            progress.close()
            QMessageBox.critical(self, "Export failed", message)
        self._export_thread.changed.connect(show_progress)
        self._export_thread.completed.connect(done)
        self._export_thread.failed.connect(failed)
        self._export_thread.start()
        progress.show()

    def closeEvent(self, event):
        if self._export_thread and self._export_thread.isRunning():
            QMessageBox.warning(self, "Export active", "Cancel or finish export before closing")
            event.ignore()
            return
        self._save_recovery()
        self.pause()
        super().closeEvent(event)
