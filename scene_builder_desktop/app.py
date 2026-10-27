"""Native Windows Scene Builder shell: media library, V25 plan and timeline.

No VPS authentication, shell subprocesses or network endpoints are used here.
All source files remain on this PC. Export uses scene_desktop's existing FFmpeg.
"""
from __future__ import annotations

from pathlib import Path
import json

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QSettings
from PySide6.QtGui import QAction, QColor
from PySide6.QtWidgets import (
    QApplication, QComboBox, QFileDialog, QHBoxLayout, QLabel, QMainWindow,
    QMessageBox, QPlainTextEdit, QPushButton, QTabWidget, QTableWidget,
    QTableWidgetItem, QVBoxLayout, QWidget, QHeaderView,
)
from scene_desktop.window import EditorWindow

from .desktop_catalog import DesktopCatalog
from .director_bridge import build_rough_cut, inspect_plan
from .director_v25 import DirectorSpecError


MEDIA_PATTERN = "Images & videos (*.png *.jpg *.jpeg *.webp *.bmp *.gif *.mp4 *.mov *.m4v *.webm *.mkv)"
STYLE = """
QWidget {background: #101827; color: #e8f0ff; font-size: 13px;}
QMainWindow, QTabWidget::pane {background: #101827;}
QTabBar::tab {background: #202d44; padding: 11px 17px; margin-right: 2px; border-radius: 5px;}
QTabBar::tab:selected {background: #376ad6; color: white;}
QPushButton {background: #254776; color: #fff; padding: 9px 14px; border: 1px solid #4e6b98; border-radius: 6px;}
QPushButton:hover {background: #365d96;}
QPushButton:disabled {background: #2a3040; color: #8994a7;}
QPlainTextEdit, QTableWidget, QComboBox {background: #172238; color: white; border: 1px solid #435573; padding: 5px;}
QHeaderView::section {background: #253756; color: #f5f7ff; padding: 8px;}
QTableWidget::item:selected {background: #315e9b; color: white;}
QLabel#heading {font-size: 23px; font-weight: bold;}
QLabel#subheading {color: #acbdd4;}
"""


class ImportWorker(QThread):
    finished_import = Signal(int, int, list)

    def __init__(self, catalog: DesktopCatalog, paths: list[str]):
        super().__init__()
        self.catalog = catalog
        self.paths = paths

    def run(self):
        added, duplicates, errors = 0, 0, []
        for path in self.paths:
            try:
                item = self.catalog.import_path(path)
                if item["duplicate"]:
                    duplicates += 1
                else:
                    added += 1
            except Exception as exc:
                errors.append(Path(path).name + ": " + str(exc))
        self.finished_import.emit(added, duplicates, errors)


class SceneBuilderWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Scene Builder Desktop — Rajudesktop")
        self.resize(1440, 900)
        self.setMinimumSize(980, 650)
        self.settings = QSettings("Rajudesktop", "SceneBuilderDesktop")
        media_root = Path.home() / "Documents" / "SceneBuilderDesktop" / "MediaLibrary"
        self.catalog = DesktopCatalog(media_root)
        self._worker = None

        content = QWidget(self)
        main = QVBoxLayout(content)
        heading = QLabel("SCENE BUILDER  |  DESKTOP STUDIO")
        heading.setObjectName("heading")
        main.addWidget(heading)
        subtitle = QLabel("Local projects • Private media library • Director V25 plan • Timeline editor")
        subtitle.setObjectName("subheading")
        main.addWidget(subtitle)
        self.tabs = QTabWidget()
        main.addWidget(self.tabs, 1)
        self.setCentralWidget(content)

        self.dashboard_tab = QWidget()
        self.library_tab = QWidget()
        self.director_tab = QWidget()
        self.editor = EditorWindow()
        self.tabs.addTab(self.dashboard_tab, "Dashboard")
        self.tabs.addTab(self.library_tab, "Media Library")
        self.tabs.addTab(self.director_tab, "Director V25")
        self.tabs.addTab(self.editor, "Timeline & Export")
        self._make_dashboard()
        self._make_library()
        self._make_director()
        self.refresh_library()
        self.statusBar().showMessage("Standalone Windows workspace. VPS production is not connected.")
        self.setStyleSheet(STYLE)

    def _make_dashboard(self):
        box = QVBoxLayout(self.dashboard_tab)
        box.addWidget(QLabel("<h2>Local Scene Builder</h2>"))
        box.addWidget(QLabel(
            "Import approved media, validate Director V25 TXT and assemble a local rough-cut draft. "
            "The Timeline tab edits clips, previews media and exports MP4 via FFmpeg."
        ))
        self.library_stats = QLabel("Checking local library…")
        box.addWidget(self.library_stats)
        bar = QHBoxLayout()
        for text, tab in (
            ("Media Library", self.library_tab),
            ("Director Scene Plan", self.director_tab),
            ("Open Timeline Editor", self.editor),
        ):
            button = QPushButton(text)
            button.clicked.connect(lambda checked=False, target=tab: self.tabs.setCurrentWidget(target))
            bar.addWidget(button)
        box.addLayout(bar)
        box.addWidget(QLabel(
            "<b>Compatibility:</b> This first Windows build supports local files, "
            "cut-based previews and MP4 export. Full VPS-only automation, "
            "Pexels downloading, animation, LUT, caption rendering and perfect "
            "narration alignment are NOT implemented. V25 intent is checked, "
            "and advanced instructions block rough-cut export rather than being silently ignored."
        ))
        box.addStretch()

    def _make_library(self):
        box = QVBoxLayout(self.library_tab)
        box.addWidget(QLabel("<h2>Scene Builder Media Library</h2>"))
        box.addWidget(QLabel("Files are copied to Documents/SceneBuilderDesktop/MediaLibrary. Originals remain untouched."))
        buttons = QHBoxLayout()
        self.import_files_btn = QPushButton("+ Import Files")
        self.import_files_btn.clicked.connect(self.import_files)
        buttons.addWidget(self.import_files_btn)
        self.import_folder_btn = QPushButton("+ Import Folder")
        self.import_folder_btn.clicked.connect(self.import_folder)
        buttons.addWidget(self.import_folder_btn)
        summary_btn = QPushButton("Download Media Summary TXT")
        summary_btn.clicked.connect(self.save_summary)
        buttons.addWidget(summary_btn)
        remove_btn = QPushButton("Delete Selected from Library")
        remove_btn.clicked.connect(self.remove_selected)
        buttons.addWidget(remove_btn)
        clean_btn = QPushButton("Clean Library")
        clean_btn.clicked.connect(self.clean_library)
        buttons.addWidget(clean_btn)
        box.addLayout(buttons)
        self.import_notice = QLabel("")
        box.addWidget(self.import_notice)
        self.media_table = QTableWidget(0, 4)
        self.media_table.setHorizontalHeaderLabels(["Original filename", "Type", "Size (MB)", "Asset ID"])
        self.media_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.media_table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.media_table.setSelectionMode(QTableWidget.SelectionMode.ExtendedSelection)
        self.media_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        box.addWidget(self.media_table, 1)

    def _make_director(self):
        box = QVBoxLayout(self.director_tab)
        box.addWidget(QLabel("<h2>Director V25 Scene Plan</h2>"))
        box.addWidget(QLabel("Validate the exact TXT and approved asset names before creating a manual-review rough cut."))
        bar = QHBoxLayout()
        load = QPushButton("Import Scene Plan .TXT")
        load.clicked.connect(self.load_plan)
        bar.addWidget(load)
        bar.addWidget(QLabel("Media source:"))
        self.source_mode = QComboBox()
        self.source_mode.addItem("Scene Media Library Only", "library_only")
        self.source_mode.addItem("Scene Library First / Pexels Fallback (validation only)", "scene_first")
        index = max(0, self.source_mode.findData(self.settings.value("source_mode", "library_only")))
        self.source_mode.setCurrentIndex(index)
        self.source_mode.currentIndexChanged.connect(self.persist_mode)
        bar.addWidget(self.source_mode)
        box.addLayout(bar)
        self.plan_text = QPlainTextEdit()
        self.plan_text.setPlaceholderText("Paste SCENE_PLAN_VERSION=2 Director TXT here, or import a .txt file…")
        box.addWidget(self.plan_text, 2)
        line = QHBoxLayout()
        choose_voice = QPushButton("Select Local Narration (optional)")
        choose_voice.clicked.connect(self.choose_voice)
        line.addWidget(choose_voice)
        self.voice_path = QLabel("No narration chosen")
        self.voice_path.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        line.addWidget(self.voice_path, 1)
        box.addLayout(line)
        buttons = QHBoxLayout()
        preflight = QPushButton("Validate V25 Plan")
        preflight.clicked.connect(self.validate_plan)
        buttons.addWidget(preflight)
        build = QPushButton("Create Editable Rough Cut")
        build.clicked.connect(self.build_plan)
        buttons.addWidget(build)
        box.addLayout(buttons)
        self.result_view = QPlainTextEdit()
        self.result_view.setReadOnly(True)
        self.result_view.setPlaceholderText("Preflight result and render compatibility blockers appear here.")
        box.addWidget(self.result_view, 1)

    def persist_mode(self):
        self.settings.setValue("source_mode", self.source_mode.currentData())

    def refresh_library(self):
        rows = self.catalog.list(limit=100000)
        self.media_table.setRowCount(len(rows))
        for index, media in enumerate(rows):
            fields = [
                media["original_name"], media["kind"],
                f"{media['bytes'] / (1024 * 1024):.2f}", media["id"],
            ]
            for column, value in enumerate(fields):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, media["id"])
                self.media_table.setItem(index, column, item)
        stats = self.catalog.summary()
        self.library_stats.setText(
            f"Approved images: {stats['images']}   |   Approved videos: {stats['videos']}   "
            f"|   Stored: {stats['bytes'] / (1024 * 1024):,.1f} MB"
        )

    def import_files(self):
        paths, _ = QFileDialog.getOpenFileNames(self, "Import local approved media", "", MEDIA_PATTERN)
        self._import(paths)

    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Import folder into Scene Media Library")
        if not folder:
            return
        from .scene_media_library import ALLOWED
        paths = sorted(
            str(p) for p in Path(folder).rglob("*")
            if p.is_file() and not p.is_symlink() and p.suffix.lower() in ALLOWED
        )
        self._import(paths)

    def _import(self, paths):
        if not paths:
            return
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "Already importing", "One batch is already in progress.")
            return
        self.import_files_btn.setEnabled(False)
        self.import_folder_btn.setEnabled(False)
        self.import_notice.setText(f"Importing {len(paths)} files in the background…")
        self._worker = ImportWorker(self.catalog, list(paths))
        self._worker.finished_import.connect(self._on_import_finish)
        self._worker.start()

    def _on_import_finish(self, added, duplicates, errors):
        self.import_files_btn.setEnabled(True)
        self.import_folder_btn.setEnabled(True)
        self.refresh_library()
        self.import_notice.setText(
            f"Imported: {added}  •  Already present: {duplicates}  •  Errors: {len(errors)}"
        )
        if errors:
            QMessageBox.warning(self, "Some files were skipped", "\n".join(errors[:15]))

    def _selected_ids(self):
        return list({
            self.media_table.item(index.row(), 0).data(Qt.ItemDataRole.UserRole)
            for index in self.media_table.selectionModel().selectedRows()
        })

    def _in_active_project(self, asset_ids):
        current_paths = {Path(clip.path).resolve() for clip in self.editor.project.clips}
        for media_id in asset_ids:
            try:
                path, _ = self.catalog.file(media_id)
                if path.resolve() in current_paths:
                    return True
            except FileNotFoundError:
                pass
        return False

    def remove_selected(self):
        ids = self._selected_ids()
        if not ids:
            return
        if self._in_active_project(ids):
            QMessageBox.warning(self, "Media in use", "Remove these clips from the current timeline first.")
            return
        if QMessageBox.question(
            self, "Remove local library assets",
            f"Delete {len(ids)} imported media items from the isolated library? Original PC files are safe."
        ) != QMessageBox.StandardButton.Yes:
            return
        for media_id in ids:
            self.catalog.delete(media_id)
        self.refresh_library()

    def clean_library(self):
        ids = [row["id"] for row in self.catalog.list(limit=100000)]
        if self._in_active_project(ids):
            QMessageBox.warning(self, "Media in use", "Current timeline uses library media. Close/clear it first.")
            return
        if QMessageBox.question(
            self, "Confirm full library cleanup",
            f"Delete all {len(ids)} imported images/videos from this Scene Builder library? "
            "Original PC source files are untouched."
        ) != QMessageBox.StandardButton.Yes:
            return
        count = self.catalog.clean()
        self.refresh_library()
        self.import_notice.setText(f"Cleaned {count} local library items.")

    def save_summary(self):
        destination, _ = QFileDialog.getSaveFileName(
            self, "Save media summary", str(Path.home() / "Documents" / "SceneBuilder_Media_Summary.txt"),
            "Text files (*.txt)")
        if destination:
            Path(destination).write_text(self.catalog.report(), encoding="utf-8")
            self.statusBar().showMessage("Saved summary to " + destination)

    def load_plan(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Open V25 Scene Plan", "", "TXT (*.txt)")
        if filename:
            if Path(filename).stat().st_size > 10 * 1024 * 1024:
                QMessageBox.warning(self, "TXT too large", "The Director TXT limit is 10 MB.")
                return
            self.plan_text.setPlainText(Path(filename).read_text(encoding="utf-8-sig"))

    def choose_voice(self):
        filename, _ = QFileDialog.getOpenFileName(
            self, "Choose local narration", "", "Audio (*.wav *.mp3 *.m4a *.aac)")
        if filename:
            self.voice_path.setText(filename)

    def validate_plan(self):
        report = inspect_plan(self.plan_text.toPlainText(), self.catalog,
                              self.source_mode.currentData())
        self.result_view.setPlainText(json.dumps(report, ensure_ascii=False, indent=2))
        self.statusBar().showMessage(
            "Director preflight: " + report["status"] +
            ("; rough-cut compatible" if report["desktop_rough_cut_ready"] else "; rough-cut blocked")
        )

    def build_plan(self):
        if self.editor._export_thread and self.editor._export_thread.isRunning():
            QMessageBox.warning(self, "Export active", "Wait until the current export has finished.")
            return
        try:
            project = build_rough_cut(self.plan_text.toPlainText(), self.catalog,
                                      self.source_mode.currentData())
            voice = self.voice_path.text()
            if voice != "No narration chosen":
                if not Path(voice).is_file() or Path(voice).suffix.lower() not in {
                    ".wav", ".mp3", ".m4a", ".aac"
                }:
                    raise ValueError("Chosen narration file is unavailable or unsupported")
                project.narration = str(Path(voice).resolve())
            self.editor.pause()
            self.editor.project = project
            self.editor.project_path = None
            self.editor.current_index = -1
            self.editor._refresh()
            self.editor._mark_changed()
            if project.narration:
                self.editor.narration_player.setSource(QUrl.fromLocalFile(project.narration))
            self.tabs.setCurrentWidget(self.editor)
            QMessageBox.information(
                self, "Editable rough cut prepared",
                f"Prepared {len(project.clips)} local clips. Timing is estimated (up to 3s/shot) "
                "and NOT voice-aligned. Review duration, narration and preview before export. "
                "Use the Editor's Save Project/Export MP4 actions."
            )
        except Exception as exc:
            QMessageBox.warning(self, "Director rough cut blocked", str(exc))
            self.validate_plan()

    def closeEvent(self, event):
        if self._worker and self._worker.isRunning():
            QMessageBox.information(self, "Import active", "Finish current media import before closing.")
            event.ignore()
            return
        if self.editor._export_thread and self.editor._export_thread.isRunning():
            QMessageBox.information(self, "Export active", "Finish/cancel the export before closing.")
            event.ignore()
            return
        super().closeEvent(event)


def main() -> int:
    import sys
    app = QApplication(sys.argv)
    app.setApplicationName("Scene Builder Desktop")
    app.setOrganizationName("Rajudesktop")
    app.setStyle("Fusion")
    window = SceneBuilderWindow()
    window.show()
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())
