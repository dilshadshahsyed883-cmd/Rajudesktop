"""One project controller for independent native draft controls."""
from pathlib import Path

from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import (QComboBox, QFileDialog, QHBoxLayout, QLabel,
                               QLineEdit, QPushButton, QTabWidget, QVBoxLayout, QWidget)
from capcut_visual_controls_standalone.engine import (
    capcut_running, default_root, list_projects, load_project, project_fingerprint)
from .transitions_tab import CapcutTransitionsTab
from .scale_tab import CapcutScaleTab


def fingerprint(project):
    """Hash authoritative drafts and timeline selection, never backup directories."""
    _, paths, _ = load_project(project)
    index = project / 'Timelines' / 'project.json'
    if index.is_file():
        paths.append(index)
    return project_fingerprint(paths)


class CapcutControlsTab(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.settings = QSettings('Rajudesktop', 'Z Builder Capcut Controls')
        self.projects_root = Path(str(self.settings.value('projects_folder', '') or default_root()))
        self._snapshot = None
        self._loaded_project = None
        self._loading = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        row = QHBoxLayout()
        row.addWidget(QLabel('CapCut projects folder'))
        self.folder_edit = QLineEdit(str(self.projects_root))
        self.folder_edit.setReadOnly(True)
        row.addWidget(self.folder_edit, 1)
        choose = QPushButton('Change Folder')
        choose.clicked.connect(self.choose_folder)
        row.addWidget(choose)
        refresh = QPushButton('Refresh Projects')
        refresh.clicked.connect(self.refresh)
        row.addWidget(refresh)
        layout.addLayout(row)
        row = QHBoxLayout()
        row.addWidget(QLabel('Project'))
        self.project_combo = QComboBox()
        self.project_combo.setMinimumContentsLength(18)
        row.addWidget(self.project_combo, 1)
        self.capcut_state = QLabel()
        row.addWidget(self.capcut_state)
        layout.addLayout(row)
        self.summary = QLabel('No selected project')
        self.summary.setWordWrap(True)
        layout.addWidget(self.summary)
        self.sections = QTabWidget(self)
        layout.addWidget(self.sections, 1)
        self.transitions_tab = CapcutTransitionsTab(self, controller=self)
        self.scale_tab = CapcutScaleTab(self)
        self.panels = [self.transitions_tab, self.scale_tab]
        for panel, title in zip(self.panels, ['Transitions', 'Scale']):
            self.sections.addTab(panel, title)
        self.project_combo.currentIndexChanged.connect(self.load_selected)
        self.sections.currentChanged.connect(self.check_external)
        self.refresh()
        self.timer = QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.check_external)
        self.timer.start()

    def selected_project(self):
        p = self.project_combo.currentData()
        return Path(p) if p else None

    def choose_folder(self):
        path = QFileDialog.getExistingDirectory(self, 'CapCut projects folder', str(self.projects_root))
        if path:
            self.projects_root = Path(path)
            self.settings.setValue('projects_folder', path)
            self.folder_edit.setText(path)
            self.refresh()

    def refresh(self):
        self.folder_edit.setText(str(self.projects_root))
        old = self.project_combo.currentData()
        self.project_combo.blockSignals(True)
        try:
            self.project_combo.clear()
            for project in list_projects(self.projects_root):
                self.project_combo.addItem(project.name, str(project))
            idx = self.project_combo.findData(old) if old else -1
            if idx >= 0:
                self.project_combo.setCurrentIndex(idx)
        finally:
            self.project_combo.blockSignals(False)
        self.load_selected(force=True)

    def load_selected(self, *_, force=False):
        if self._loading:
            return
        self._loading = True
        try:
            project = self.selected_project()
            self._snapshot = None
            self._loaded_project = project
            for panel in self.panels:
                panel.projects_root = self.projects_root
                panel.invalidate()
                panel.setEnabled(False)
            if project:
                before = fingerprint(project)
                for panel in self.panels:
                    panel.reload_project()
                after = fingerprint(project)
                if before != after:
                    raise ValueError('Project changed during detection. Refresh Projects again.')
                self._snapshot = after
                raw, _, warnings = load_project(project)
                visuals = sum(len(t.get('segments', [])) for t in raw['tracks'] if t.get('type') == 'video')
                self.summary.setText(f'{project.name} · {visuals} clips · '
                    f'{len(self.transitions_tab.catalog)} project transitions · '
                    f'{len(warnings)} warnings')
                for panel in self.panels:
                    panel.setEnabled(True)
            else:
                # Clear every panel when the selected folder has no projects.
                for panel in self.panels:
                    panel.reload_project()
                self.summary.setText('No CapCut projects found in this folder.')
        except Exception as exc:
            self.summary.setText(f'Cannot inspect selected project: {exc}')
            for panel in self.panels:
                panel.invalidate()
                if hasattr(panel, 'catalog'):
                    panel.catalog = []
                    panel.draw_catalog()
                panel.setEnabled(False)
        finally:
            self._loading = False
            self.update_state()

    def update_state(self):
        self.capcut_state.setText('CapCut OPEN — close before Apply' if capcut_running() else 'CapCut closed')

    def check_external(self, *_):
        if self._loading:
            return
        self.update_state()
        project = self.selected_project()
        try:
            changed = project != self._loaded_project or (project and fingerprint(project) != self._snapshot)
        except Exception:
            changed = True
        if changed:
            self.load_selected(force=True)

    def require_current(self):
        project = self.selected_project()
        try:
            valid = project and project == self._loaded_project and fingerprint(project) == self._snapshot
        except Exception:
            valid = False
        if not valid:
            self.load_selected(force=True)
            raise ValueError('Project changed; resources reloaded. Select the desired resources and preview again.')
