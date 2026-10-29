"""Compact AutoCapCut-inspired shell over the extracted native controls."""
from __future__ import annotations

from pathlib import Path
import os
import sys
import traceback

from PySide6.QtCore import QSettings, QThread, QTimer, Signal, Slot, Qt
from PySide6.QtWidgets import (QApplication, QComboBox, QFileDialog, QFrame, QHBoxLayout,
 QLabel, QLineEdit, QMainWindow, QProgressBar, QPushButton, QTabWidget, QTableWidget, QVBoxLayout, QWidget)

from . import __version__, backend
from .animations_tab import CapcutAnimationsTab
from .transitions_tab import CapcutTransitionsTab
from .scale_tab import CapcutScaleTab


class Task(QThread):
    result = Signal(object)
    failed = Signal(str)
    stage = Signal(int)

    def __init__(self, operation, parent=None):
        super().__init__(parent)
        self.operation = operation

    def run(self):
        try:
            self.stage.emit(15)
            value = self.operation()
            self.stage.emit(100)
            self.result.emit(value)
        except Exception as exc:
            self.failed.emit(str(exc))


STYLE = '''
QMainWindow {background:#191a1d;}
QWidget {color:#e6e6e8;font-family:"Segoe UI";font-size:12px;}
QFrame#surface {background:#242528;border:1px solid #38393d;border-radius:18px;}
QLabel {background:transparent;}
QLabel#appTitle {font-size:18px;font-weight:700;}
QLabel#muted {color:#96979e;}
QLabel#version {color:#d8b66d;border:1px solid #726348;border-radius:9px;padding:3px 9px;}
QLabel#processState {color:#abd4c1;background:#2b3631;border-radius:9px;padding:4px 10px;}
QLabel#message {color:#b8cfc5;}
QComboBox,QLineEdit,QDoubleSpinBox,QSpinBox {background:#202125;border:1px solid #414248;border-radius:7px;padding:5px 8px;selection-background-color:#4c555f;}
QComboBox#projectPicker {font-size:14px;padding:9px 12px;min-height:20px;}
QComboBox QAbstractItemView {background:#25262a;color:#eee;selection-background-color:#4c555f;}
QPushButton {background:#292a2f;border:1px solid #45464d;border-radius:8px;padding:6px 11px;}
QPushButton:hover {background:#37393f;border-color:#777981;}
QPushButton:pressed {background:#474950;}
QPushButton:disabled {color:#74757c;border-color:#37383d;}
QPushButton#primaryAction {background:#f1f1f3;color:#202126;border:1px solid #fff;font-weight:700;min-height:25px;padding:8px 16px;border-radius:10px;}
QPushButton#primaryAction:hover {background:white;}
QPushButton#primaryAction:disabled {background:#77797f;color:#2b2b2f;border-color:#77797f;}
QTabWidget::pane {border:1px solid #3b3c42;background:#25262a;border-radius:8px;top:-1px;}
QTabBar::tab {background:transparent;color:#95969f;padding:10px 16px;border-bottom:2px solid transparent;}
QTabBar::tab:selected {background:#2a2b30;color:#f3f3f5;border-bottom:2px solid #d3d8df;font-weight:600;}
QTableWidget,QTextEdit {background:#202125;border:1px solid #3d3e45;border-radius:6px;gridline-color:#34353b;selection-background-color:#49515b;}
QTableWidget::item {padding:3px;}
QHeaderView::section {background:#2b2c32;color:#a9aab2;border:0;border-bottom:1px solid #42434a;padding:5px;}
QGroupBox {border:1px solid #3e3f46;border-radius:9px;margin-top:12px;padding:10px;}
QGroupBox::title {subcontrol-origin:margin;left:12px;padding:0 4px;color:#c3c4cb;}
QCheckBox {spacing:7px;}
QCheckBox::indicator {width:14px;height:14px;}
QProgressBar {background:#202125;border:1px solid #3b3c42;border-radius:4px;min-height:6px;max-height:7px;text-align:center;}
QProgressBar::chunk {background:#a6cbbb;border-radius:3px;}
QScrollBar:vertical {background:#25262a;width:9px;margin:0;}
QScrollBar::handle:vertical {background:#575961;min-height:25px;border-radius:4px;}
QScrollBar::add-line:vertical,QScrollBar::sub-line:vertical {height:0;}
'''


class Window(QMainWindow):
    def __init__(self, root=None, autostart=True):
        super().__init__()
        self.settings = QSettings('Rajudesktop','CapCut Controls Studio')
        self.projects_root = Path(root or self.settings.value('projects_folder','') or backend.visual.default_root()).resolve()
        self.snapshot = None
        self.worker = None
        self.generation = 0
        self.pending_scan = False
        self._outcome = None
        self._completion_message = None
        self.setWindowTitle('CapCut Controls Studio')
        self.resize(980,820)
        self.setMinimumSize(840,720)
        self.setStyleSheet(STYLE)
        host = QWidget()
        shell = QVBoxLayout(host)
        shell.setContentsMargins(12,12,12,12)
        surface = QFrame()
        surface.setObjectName('surface')
        shell.addWidget(surface)
        layout = QVBoxLayout(surface)
        layout.setContentsMargins(17,15,17,15)
        layout.setSpacing(10)
        row = QHBoxLayout()
        title = QLabel('●  CapCut Controls Studio')
        title.setObjectName('appTitle')
        row.addWidget(title,1)
        version = QLabel('v'+__version__)
        version.setObjectName('version')
        row.addWidget(version)
        self.capcut_state = QLabel('Detecting CapCut…')
        self.capcut_state.setObjectName('processState')
        row.addWidget(self.capcut_state)
        layout.addLayout(row)
        label = QLabel('PROJECT')
        label.setObjectName('muted')
        layout.addWidget(label)
        row = QHBoxLayout()
        self.project_combo = QComboBox()
        self.project_combo.setObjectName('projectPicker')
        self.project_combo.setMinimumContentsLength(25)
        self.project_combo.setSizeAdjustPolicy(QComboBox.SizeAdjustPolicy.AdjustToMinimumContentsLengthWithIcon)
        self.project_combo.currentIndexChanged.connect(self.project_changed)
        row.addWidget(self.project_combo,1)
        self.refresh_button = QPushButton('↻  Refresh')
        self.refresh_button.clicked.connect(self.refresh)
        row.addWidget(self.refresh_button)
        layout.addLayout(row)
        self.summary = QLabel('Choose the CapCut projects folder to begin.')
        self.summary.setWordWrap(True)
        self.summary.setObjectName('muted')
        layout.addWidget(self.summary)
        row = QHBoxLayout()
        self.folder_edit = QLineEdit(str(self.projects_root))
        self.folder_edit.setReadOnly(True)
        self.folder_edit.setToolTip(str(self.projects_root))
        row.addWidget(self.folder_edit,1)
        self.folder_button = QPushButton('Change Folder')
        self.folder_button.clicked.connect(self.choose_folder)
        row.addWidget(self.folder_button)
        layout.addLayout(row)
        self.sections = QTabWidget()
        self.transitions_tab = CapcutTransitionsTab(self,controller=self)
        self.animations_tab = CapcutAnimationsTab(self,controller=self)
        self.scale_tab = CapcutScaleTab(self)
        self.panels = [self.transitions_tab,self.animations_tab,self.scale_tab]
        for panel,name in zip(self.panels,['Transitions','Animations','Scale']):
            panel.layout().setContentsMargins(10,10,10,10)
            panel.layout().setSpacing(7)
            self.sections.addTab(panel,name)
            for table in panel.findChildren(QTableWidget):
                table.verticalHeader().setDefaultSectionSize(26)
        self.transitions_tab.apply_button.setObjectName('primaryAction')
        self.animations_tab.apply_button.setObjectName('primaryAction')
        for button in self.scale_tab.findChildren(QPushButton):
            if button.text().startswith('Apply '):button.setObjectName('primaryAction')
        self.sections.currentChanged.connect(self.check_external)
        layout.addWidget(self.sections,1)
        self.progress = QProgressBar()
        self.progress.setRange(0,100)
        self.progress.setValue(0)
        self.progress.setTextVisible(False)
        layout.addWidget(self.progress)
        self.message = QLabel('Ready · Preview first. Apply automatically creates a recoverable backup.')
        self.message.setWordWrap(True)
        self.message.setObjectName('message')
        layout.addWidget(self.message)
        self.setCentralWidget(host)
        self.timer = QTimer(self)
        self.timer.setInterval(3000)
        self.timer.timeout.connect(self.check_external)
        for panel in self.panels:panel.setEnabled(False)
        if autostart:
            QTimer.singleShot(0,self.refresh)
            self.timer.start()

    def selected_project(self):
        data = self.project_combo.currentData()
        return Path(data).resolve() if data else None

    def notify(self,message,error=False):
        self.message.setText(message)
        self.message.setStyleSheet('color:#f0b0a5;' if error else 'color:#b8cfc5;')

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(self,'CapCut projects folder',str(self.projects_root))
        if folder:
            self.projects_root = Path(folder).resolve()
            self.settings.setValue('projects_folder',str(self.projects_root))
            self.folder_edit.setText(str(self.projects_root))
            self.folder_edit.setToolTip(str(self.projects_root))
            self.generation += 1
            self.snapshot = None
            self.project_combo.blockSignals(True)
            self.project_combo.clear()
            self.project_combo.blockSignals(False)
            self.clear_panels()
            self.refresh()

    def clear_panels(self):
        for panel in self.panels:
            panel.invalidate()
            panel.reload_project()
            panel.setEnabled(False)

    def project_changed(self,*_):
        self.generation += 1
        self.snapshot = None
        self.clear_panels()
        self.refresh()

    def refresh(self,*_):
        return self.start_scan(quiet=False)

    def start_scan(self,quiet=True):
        if self.worker:
            self.pending_scan = True
            return False
        root,selected,previous = self.projects_root,self.selected_project(),self.snapshot if quiet else None
        if not selected:
            saved = self.settings.value('last_project','')
            selected = Path(saved) if saved else None
        return self.run_job('Reading CapCut projects',lambda:backend.scan(root,selected,previous),self.scanned,background=quiet,scan=True)

    def check_external(self,*_):
        if self.worker is None and not self.project_combo.view().isVisible():
            self.start_scan(quiet=True)

    def scanned(self,result):
        projects,snapshot,running = result
        old_snapshot = self.snapshot
        values = [self.project_combo.itemData(i) for i in range(self.project_combo.count())]
        desired = [str(p) for p in projects]
        if values != desired or (snapshot and self.selected_project() != snapshot.project):
            self.project_combo.blockSignals(True)
            self.project_combo.clear()
            for project in projects:self.project_combo.addItem(project.name,str(project))
            if snapshot:
                self.project_combo.setCurrentIndex(self.project_combo.findData(str(snapshot.project)))
            self.project_combo.blockSignals(False)
        self.capcut_state.setText('●  CapCut open' if running else '●  CapCut closed')
        self.snapshot = snapshot
        if snapshot:
            self.settings.setValue('last_project',str(snapshot.project))
            if old_snapshot is not snapshot:
                for panel in self.panels:
                    panel.projects_root = self.projects_root
                    panel.reload_project()
                raw = snapshot.raw
                mats = {m['id']:m for m in raw['materials'].get('videos',[]) if isinstance(m,dict) and 'id' in m}
                segments = [s for t in raw['tracks'] if t.get('type')=='video' for s in t.get('segments',[])]
                photos = sum(mats.get(s.get('material_id'),{}).get('type')=='photo' for s in segments)
                duration = int(raw.get('duration') or 0)/1e6
                self.summary.setText(f'{photos} images · {len(segments)-photos} videos · {duration:.1f}s · '
                                     f'{len(snapshot.transitions)} transitions · {len(snapshot.animations)} Combo animations')
                self.notify(self._completion_message or 'Project loaded · Preview first. Apply creates a recoverable backup.')
                self._completion_message = None
        else:
            self.clear_panels()
            self.summary.setText('No projects found. Select the folder containing CapCut draft subfolders.')

    def require_current(self):
        # Native content is checked in the worker immediately before previews/writes.
        if self.snapshot is None or self.snapshot.project != self.selected_project():
            raise ValueError('Wait for the selected project to finish loading.')

    def run_job(self,label,operation,completed,*,write=False,background=False,scan=False):
        if self.worker:
            self.notify('Another operation is running. Please wait.',error=True)
            return False
        token = self.generation
        self._outcome = None
        self._job = (token,completed,write,background,scan)
        self.worker = Task(operation,self)
        self.worker.result.connect(self._result)
        self.worker.failed.connect(self._failed)
        self.worker.stage.connect(self._stage)
        self.worker.finished.connect(self._finished)
        if not background:
            self.notify(label+'…')
            self.progress.setRange(0,0)
        self.folder_button.setEnabled(False)
        self.refresh_button.setEnabled(False)
        if not scan:
            self.project_combo.setEnabled(False)
            for panel in self.panels:panel.setEnabled(False)
        self.worker.start()
        return True

    @Slot(object)
    def _result(self,value):
        self._outcome = (True,value)

    @Slot(str)
    def _failed(self,message):
        self._outcome = (False,message)

    @Slot(int)
    def _stage(self,value):
        if value == 100:
            self.progress.setRange(0,100)
            self.progress.setValue(100)

    @Slot()
    def _finished(self):
        thread = self.worker
        self.worker = None
        token,completed,write,background,scan = self._job
        self._job = None
        outcome,self._outcome = self._outcome,None
        self.folder_button.setEnabled(True)
        self.refresh_button.setEnabled(True)
        self.project_combo.setEnabled(True)
        if token == self.generation and outcome:
            if outcome[0]:
                try:
                    completed(outcome[1])
                    if not scan and not write:self.notify('Preview ready · Apply creates a backup and changes only this project.')
                except Exception as exc:
                    self.notify(str(exc),error=True)
            else:
                self.notify(outcome[1],error=True)
                if scan:
                    self.snapshot = None
                    self.clear_panels()
                    self.summary.setText('Could not read this project. Check the folder and Refresh.')
        self.progress.setRange(0,100)
        self.progress.setValue(100 if outcome and outcome[0] else 0)
        for panel in self.panels:panel.setEnabled(self.snapshot is not None and self.worker is None)
        thread.wait()
        thread.operation = None
        thread.deleteLater()
        if self.pending_scan:
            self.pending_scan = False
            QTimer.singleShot(0,self.refresh)

    def saved(self,result):
        saved = result.get('saved',False)
        backup = result.get('backup') or result.get('backup_dir') or ''
        self.snapshot = None
        self.clear_panels()
        self._completion_message = 'Saved · Backup: '+str(backup) if saved else 'Already matching · No changes written.'
        self.notify(self._completion_message)
        # Preserve the completion message while the background rescan synchronizes tabs.
        self.pending_scan = True

    def closeEvent(self,event):
        if self.worker:
            self.notify('Finishing the current operation before closing. Please close again when it finishes.')
            event.ignore()
            return
        self.timer.stop()
        super().closeEvent(event)


def main():
    app = QApplication.instance() or QApplication(sys.argv)
    app.setApplicationName('CapCut Controls Studio')
    app.setOrganizationName('Rajudesktop')
    window = Window()
    window.show()
    return app.exec()
