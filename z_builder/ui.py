"""Z Builder three-step Windows UI: timed plan+voice, library and timeline, CapCut.
CapCut draft files are created only on explicit user action.
"""
from __future__ import annotations

from pathlib import Path
import os
import subprocess
import sys
import traceback

from PySide6.QtCore import Qt, QThread, Signal, QUrl, QStandardPaths
from PySide6.QtGui import QPixmap
from PySide6.QtMultimedia import QAudioOutput, QMediaPlayer
from PySide6.QtMultimediaWidgets import QVideoWidget
from PySide6.QtWidgets import (
    QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QDoubleSpinBox,
    QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget,
    QTextEdit, QVBoxLayout, QWidget
)

from .core import Catalog, Plan, bind_media, kind_of, load_plan, open_project, preflight, save_project, timeline
from .capcut import export_capcut


class ExportWorker(QThread):
    succeeded = Signal(object)
    failed = Signal(str)

    def __init__(self, plan, drafts_root, launch):
        super().__init__()
        self.plan, self.drafts_root, self.launch = Plan.from_dict(plan.to_dict()), drafts_root, launch

    def run(self):
        try:
            self.succeeded.emit(export_capcut(self.plan, self.drafts_root, self.launch))
        except Exception as e:
            self.failed.emit(str(e))


class Window(QMainWindow):
    def __init__(self):
        super().__init__()
        home = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.DocumentsLocation)
        self.home = Path(home or str(Path.home() / 'Documents')) / 'Z Builder'
        self.home.mkdir(parents=True, exist_ok=True)
        self.catalog = Catalog(self.home / 'library.sqlite3')
        self.plan: Plan | None = None
        self.pending_voice = ''
        self.worker = None
        self.assets = []
        self.setWindowTitle('Z Builder — Scene Plan · Media Library · CapCut')
        self.resize(1440, 890)
        self.setMinimumSize(1060, 700)
        self._ui()
        self.refresh_library()

    def _button(self, text, callback):
        b = QPushButton(text)
        b.clicked.connect(callback)
        return b

    def _table(self, heads):
        table = QTableWidget(0, len(heads))
        table.setHorizontalHeaderLabels(heads)
        table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        table.verticalHeader().setVisible(False)
        return table

    def _ui(self):
        base = QWidget()
        outer = QVBoxLayout(base)
        title = QLabel('Z BUILDER')
        title.setStyleSheet('font-size:26px;font-weight:800;color:#eff6ff;')
        outer.addWidget(title)
        subtitle = QLabel('1  Input: Scene Plan + Voice    →    2  Select Media + Build Timeline    →    3  Open in CapCut')
        outer.addWidget(subtitle)
        self.tabs = QTabWidget()
        outer.addWidget(self.tabs, 1)
        self.setCentralWidget(base)
        self.setStyleSheet('''
            QMainWindow,QWidget {background:#101a2b;color:#eaf2ff;font-size:13px;}
            QTabBar::tab {background:#1c2a40;padding:12px 19px;border:1px solid #324761;}
            QTabBar::tab:selected {background:#2669ad;color:white;}
            QPushButton {background:#2467a4;border:1px solid #4b83ba;border-radius:5px;padding:8px 12px;color:white;font-weight:600;}
            QPushButton:hover {background:#3386d0;}
            QTableWidget,QTextEdit,QLineEdit,QDoubleSpinBox {background:#14243a;color:#f6f9ff;border:1px solid #405473;}
            QHeaderView::section {background:#253b57;color:#eef6ff;padding:7px;}
            QTableWidget::item:selected {background:#235d9a;}
            QLabel {background:transparent;}
        ''')

        self.media_tab = QWidget()
        media_layout = QVBoxLayout(self.media_tab)
        mcontrols = QHBoxLayout()
        mcontrols.addWidget(self._button('Import Folder', self.import_folder))
        mcontrols.addWidget(self._button('Import Files', self.import_files))
        mcontrols.addWidget(self._button('Download Summary .txt', self.save_summary))
        self.media_filter = QComboBox()
        self.media_filter.addItems(['All Media', 'Images', 'Videos'])
        self.media_filter.currentIndexChanged.connect(self.refresh_library)
        mcontrols.addWidget(self.media_filter)
        self.media_count = QLabel()
        mcontrols.addWidget(self.media_count, 1)
        media_layout.addLayout(mcontrols)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.media_table = self._table(['Filename', 'Type', 'Status', 'Tags', 'Full path'])
        self.media_table.itemSelectionChanged.connect(self.select_library)
        split.addWidget(self.media_table)
        side = QWidget()
        sl = QVBoxLayout(side)
        self.preview = QStackedWidget()
        self.image = QLabel('Select an image or video')
        self.image.setMinimumSize(230, 170)
        self.image.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.image.setWordWrap(True)
        self.video = QVideoWidget()
        self.preview.addWidget(self.image)
        self.preview.addWidget(self.video)
        sl.addWidget(self.preview)
        self.audio = QAudioOutput(self)
        self.player = QMediaPlayer(self)
        self.player.setAudioOutput(self.audio)
        self.player.setVideoOutput(self.video)
        sl.addWidget(self._button('Play / Pause video', self.toggle_video))
        sl.addWidget(QLabel('Search tags for selected media (comma-separated)'))
        self.tags = QLineEdit()
        sl.addWidget(self.tags)
        sl.addWidget(self._button('Save Tags', self.save_tags))
        sl.addWidget(self._button('Remove from Library (keep original)', self.remove_catalog_item))
        sl.addStretch()
        split.addWidget(side)
        split.setSizes([970, 360])
        media_layout.addWidget(split, 1)
        # Scene Media Library is included inside the Media Selection step.

        plan_tab = QWidget()
        pl = QVBoxLayout(plan_tab)
        b = QHBoxLayout()
        b.addWidget(self._button('Import Simple Scene Plan TXT', self.import_plan))
        b.addWidget(self._button('Open Z Builder Project', self.open_project))
        b.addWidget(self._button('Save Z Builder Project', self.save_project))
        pl.addLayout(b)
        self.plan_info = QLabel('Simple plan: 00:00 --> 00:02.500 | video | clip1.mp4 | in=0.500  (or  | image | photo.jpg)')
        voice_row = QHBoxLayout()
        voice_row.addWidget(self._button('Choose Voice MP3/WAV', self.choose_voice))
        self.voice_info = QLabel('No narration selected')
        voice_row.addWidget(self.voice_info, 1)
        pl.addLayout(voice_row)
        pl.addWidget(self.plan_info)
        self.plan_table = self._table(['Shot', 'Start–End', 'Media type', 'Requested file / keyword', 'Source in', 'Duration'])
        pl.addWidget(self.plan_table, 1)
        self.plan_warnings = QTextEdit()
        self.plan_warnings.setReadOnly(True)
        self.plan_warnings.setMaximumHeight(180)
        pl.addWidget(self.plan_warnings)
        pl.addWidget(self._button('Next → Select Media and Build Timeline', self.go_media_selection))
        self.tabs.addTab(plan_tab, '1  Input — Scene Plan + Voice')

        select_tab = QWidget()
        sel = QVBoxLayout(select_tab)
        buttons = QHBoxLayout()
        buttons.addWidget(self._button('Match All From Library', self.match_all))
        buttons.addWidget(self._button('Replace Selected Media', self.replace_selected))
        self.match_count = QLabel('No scene plan')
        buttons.addWidget(self.match_count, 1)
        sel.addLayout(buttons)
        self.match_table = self._table(['Shot', 'Start–End', 'Requested', 'Matched media', 'Source trim', 'Status'])
        self.match_table.itemDoubleClicked.connect(lambda _: self.replace_selected())
        sel.addWidget(self.match_table, 1)
        sel.addWidget(QLabel('4-sec videos are trimmed to the exact scene slot without changing source files. Images hold for the whole slot.'))
        sel.addWidget(self._button('Next → Open in CapCut', self.go_capcut))
        self.select_tabs = QTabWidget()
        self.select_tabs.addTab(select_tab, 'Scene Timeline')
        self.select_tabs.addTab(self.media_tab, 'Media Library')
        self.tabs.addTab(self.select_tabs, '2  Media Selection + Timeline')

        export_tab = QWidget()
        ex = QVBoxLayout(export_tab)
        ex.addWidget(QLabel('CapCut Desktop Export — source assets remain untouched; a new CapCut draft is created.'))
        form = QFormLayout()
        path_row = QHBoxLayout()
        self.drafts = QLineEdit()
        self.drafts.setPlaceholderText('Empty = Z Studio auto-detects CapCut drafts location')
        path_row.addWidget(self.drafts)
        path_row.addWidget(self._button('Browse', self.choose_drafts))
        form.addRow('CapCut drafts folder', path_row)
        ex.addLayout(form)
        self.launch = QCheckBox('Launch CapCut after creating verified draft (open it from CapCut Home)')
        self.launch.setChecked(True)
        ex.addWidget(self.launch)
        controls = QHBoxLayout()
        controls.addWidget(self._button('Preflight', self.show_preflight))
        self.export_button = self._button('Create Editable CapCut Project', self.start_export)
        controls.addWidget(self.export_button)
        ex.addLayout(controls)
        self.export_log = QTextEdit()
        self.export_log.setReadOnly(True)
        self.export_log.setText('Native CapCut draft writing follows the Z Studio 9.4 format. CapCut version compatibility must be checked on your PC.')
        ex.addWidget(self.export_log, 1)
        self.tabs.addTab(export_tab, '3  Open in CapCut')
        self.statusBar().showMessage('Ready — catalog is local to Documents/Z Builder')

    def alert(self, title, message):
        QMessageBox.warning(self, title, message)

    def import_files(self):
        names, _ = QFileDialog.getOpenFileNames(self, 'Import media', '', 'Media (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.png *.jpg *.jpeg *.webp *.bmp)')
        problems = []
        for name in names:
            try:
                self.catalog.add(name)
            except Exception as e:
                problems.append(f'{name}: {e}')
        self.refresh_library()
        if problems:
            self.alert('Import warnings', '\n'.join(problems[:12]))

    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, 'Import folder recursively')
        if folder:
            try:
                n, errors = self.catalog.add_folder(folder)
                self.refresh_library()
                self.statusBar().showMessage(f'Imported {n} approved image/video files')
                if errors:
                    self.alert('Some files failed', '\n'.join(errors[:12]))
            except Exception as e:
                self.alert('Import failed', str(e))

    def refresh_library(self):
        self.assets = self.catalog.assets()
        choice = self.media_filter.currentIndex()
        self.visible_assets = [a for a in self.assets if choice == 0 or a['kind'] == ('image' if choice == 1 else 'video')]
        self.media_table.setRowCount(len(self.visible_assets))
        for i, a in enumerate(self.visible_assets):
            status = 'Ready' if a['approved'] and a['exists'] else 'Missing / unapproved'
            for col, val in enumerate([a['filename'], a['kind'], status, a['tags'], a['path']]):
                self.media_table.setItem(i, col, QTableWidgetItem(str(val)))
        images = sum(a['kind'] == 'image' for a in self.assets)
        videos = len(self.assets) - images
        self.media_count.setText(f'{len(self.assets)} items  |  {images} images  |  {videos} videos')
        if self.plan:
            self.match_all()

    def select_library(self):
        row = self.media_table.currentRow()
        if row < 0 or row >= len(self.visible_assets):
            return
        a = self.visible_assets[row]
        self.tags.setText(a['tags'])
        self.player.stop()
        self.preview.setCurrentWidget(self.image)
        if a['kind'] == 'image':
            pic = QPixmap(a['path'])
            if pic.isNull():
                self.image.setText('Unable to load image')
            else:
                self.image.setPixmap(pic.scaled(400, 340, Qt.AspectRatioMode.KeepAspectRatio, Qt.TransformationMode.SmoothTransformation))
        else:
            self.preview.setCurrentWidget(self.video)
            self.player.setSource(QUrl.fromLocalFile(a['path']))

    def toggle_video(self):
        if self.player.playbackState() == QMediaPlayer.PlaybackState.PlayingState:
            self.player.pause()
        else:
            self.player.play()

    def save_tags(self):
        row = self.media_table.currentRow()
        if 0 <= row < len(self.visible_assets):
            self.catalog.update_tags(self.visible_assets[row]['id'], self.tags.text())
            self.refresh_library()

    def remove_catalog_item(self):
        row = self.media_table.currentRow()
        if 0 <= row < len(self.visible_assets):
            self.catalog.remove(self.visible_assets[row]['id'])
            self.refresh_library()

    def save_summary(self):
        path, _ = QFileDialog.getSaveFileName(self, 'Save media summary', str(self.home / 'Media_Summary.txt'), 'Text (*.txt)')
        if path:
            Path(path).write_text(self.catalog.summary(), encoding='utf-8')
            self.statusBar().showMessage(f'Summary saved: {path}')

    def import_plan(self):
        path, _ = QFileDialog.getOpenFileName(self, 'Import timed Scene Plan TXT', '', 'Scene Plan (*.txt *.ini)')
        if path:
            try:
                self.plan = load_plan(Path(path).read_text(encoding='utf-8-sig'))
                if self.pending_voice:
                    self.plan.narration_path = self.pending_voice
                self.match_all()
                self.tabs.setCurrentIndex(0)
            except Exception as e:
                self.alert('Invalid Scene Plan', str(e))

    def display_plan(self):
        if not self.plan:
            return
        p = self.plan
        self.plan_info.setText(f'{p.name}  •  {p.source_mode}  •  {p.width}×{p.height}  •  {p.fps} FPS  •  {len(p.shots)} shots  •  {p.duration:.1f}s')
        self.plan_table.setRowCount(len(p.shots))
        for i, (start, end, shot) in enumerate(timeline(p)):
            for c, val in enumerate([shot.section, f'{start:.3f}–{end:.3f}', shot.media_type,
                                     shot.filename or 'keyword: ' + shot.keyword,
                                     f'{shot.source_in_seconds:.3f}s' if shot.media_type == 'video' else '—',
                                     f'{shot.duration:.3f}s']):
                self.plan_table.setItem(i, c, QTableWidgetItem(val))
        warnings = list(p.warnings)
        warnings += [f'{shot.section}: video requires {shot.source_in_seconds + shot.duration:.3f}s from a 4-second source; shorten/reselect' for shot in p.shots
                     if shot.media_type == 'video' and shot.source_in_seconds + shot.duration > 4.002]
        self.plan_warnings.setPlainText('\n'.join(warnings[:150]) or 'Scene Plan timing validated')
        self.voice_info.setText(p.narration_path or 'No narration selected')

    def match_all(self):
        if not self.plan:
            self.alert('No plan', 'Import a Scene Plan first')
            return
        issues = bind_media(self.plan, self.catalog.assets())
        self.display_plan()
        self.match_table.setRowCount(len(self.plan.shots))
        for i, s in enumerate(self.plan.shots):
            for j, val in enumerate([s.section, s.filename, Path(s.assigned_path).name if s.assigned_path else '—',
                                     s.source, s.warning or 'READY']):
                self.match_table.setItem(i, j, QTableWidgetItem(val))
        self.match_count.setText(f'{len(self.plan.shots) - len(issues)}/{len(self.plan.shots)} media resolved')
        self.statusBar().showMessage(f'{len(issues)} unresolved media assignments')

    def replace_selected(self):
        if not self.plan:
            return
        index = self.match_table.currentRow()
        if index < 0 or index >= len(self.plan.shots):
            return
        shot = self.plan.shots[index]
        name, _ = QFileDialog.getOpenFileName(self, f'Choose {shot.media_type} for {shot.section}', '',
                                              'Media (*.mp4 *.mov *.mkv *.webm *.avi *.m4v *.png *.jpg *.jpeg *.webp *.bmp)')
        if not name:
            return
        if kind_of(name) != shot.media_type:
            self.alert('Type mismatch', f'{shot.section} requires {shot.media_type}')
            return
        asset_id = self.catalog.add(name)
        shot.assigned_id = asset_id
        self.refresh_library()
        self.match_table.setCurrentCell(index, 0)

    def save_project(self):
        if self.plan:
            file, _ = QFileDialog.getSaveFileName(self, 'Save Z Builder Project', str(self.home / (self.plan.name + '.zbproj')), 'Z Builder (*.zbproj)')
            if file:
                save_project(self.plan, file)
                self.statusBar().showMessage('Project saved')

    def open_project(self):
        file, _ = QFileDialog.getOpenFileName(self, 'Open Z Builder Project', str(self.home), 'Z Builder (*.zbproj)')
        if file:
            try:
                self.plan = open_project(file)
                self.match_all()
                self.tabs.setCurrentIndex(1)
            except Exception as e:
                self.alert('Cannot open project', str(e))

    def choose_voice(self):
        file, _ = QFileDialog.getOpenFileName(self, 'Choose narration', '', 'Audio (*.wav *.mp3 *.aac *.m4a)')
        if file:
            self.pending_voice = file
            if self.plan:
                self.plan.narration_path = file
            self.voice_info.setText(file)

    def go_media_selection(self):
        if not self.plan:
            self.alert('Input required', 'Import a Scene Plan first')
            return
        self.match_all()
        self.select_tabs.setCurrentIndex(0)
        self.tabs.setCurrentIndex(1)

    def go_capcut(self):
        if not self.plan:
            self.alert('Input required', 'Import a Scene Plan first')
            return
        self.show_preflight()

    def choose_drafts(self):
        folder = QFileDialog.getExistingDirectory(self, 'Select CapCut draft folder')
        if folder:
            self.drafts.setText(folder)

    def show_preflight(self):
        if not self.plan:
            self.alert('No plan', 'Import Scene Plan first')
            return
        issues = preflight(self.plan)
        self.export_log.setPlainText('\n'.join(issues) if issues else 'PREFLIGHT PASS: all timeline slots have media, video trims fit 4 seconds, and voice is selected.')
        self.tabs.setCurrentIndex(2)

    def start_export(self):
        if not self.plan:
            self.alert('No plan', 'Import Scene Plan first')
            return
        problems = preflight(self.plan)
        if problems:
            self.export_log.setPlainText('EXPORT BLOCKED\n' + '\n'.join(problems[:60]))
            return
        self.export_button.setEnabled(False)
        self.export_log.setPlainText('Creating CapCut draft and verifying files...')
        self.worker = ExportWorker(self.plan, self.drafts.text().strip(), self.launch.isChecked())
        self.worker.succeeded.connect(self.export_complete)
        self.worker.failed.connect(self.export_failed)
        self.worker.start()

    def export_complete(self, result):
        self.export_button.setEnabled(True)
        issues = result.get('warnings', [])
        compat = result.get('capcut', {}).get('compatibility', {})
        self.export_log.setPlainText('CAPCUT DRAFT CREATED\n' + result['folder'] +
            f'\nTracks: {result["tracks"]}, segments: {result["segments"]}' +
            '\n\nOpen it from CapCut Home > Projects.' +
            '\n\nCompatibility: ' + str(compat.get('level', 'unknown')) +
            '\n' + '\n'.join(compat.get('notes', [])) +
            '\n\nSCENE PLAN EXPORT NOTES\n' + ('\n'.join(issues) if issues else 'None'))

    def export_failed(self, message):
        self.export_button.setEnabled(True)
        self.export_log.setPlainText('EXPORT FAILED\n' + message)


def main():
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    win = Window()
    win.show()
    return app.exec()
