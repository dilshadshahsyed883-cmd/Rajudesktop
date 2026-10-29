"""Independent CapCut transitions panel embedded as Z Builder tab four.

Uses the proven standalone transition-only engine without invoking any Z Builder
Scene Plan export functions. Native timeline segments are never regenerated.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QItemSelectionModel
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QDoubleSpinBox,
    QFileDialog, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
    QTableWidget, QTableWidgetItem, QTabWidget, QTextEdit, QVBoxLayout,
    QWidget, QHeaderView,
)

from autocapcut_transitions_only.transition_engine import (
    capcut_running, cut_inventory, default_projects_dir, harvest_transitions,
    list_projects, load_project, parse_edit_file, plan_transitions,
    save_transitions,
)

EXAMPLE_EDIT_FILE = json.dumps({
    "version": 1,
    "transitions": [
        {"after": "0-00.png", "transition": "Flash Zoom", "duration": 0.6},
        {"after": "1-41.mp4", "transition": "Blink", "effect_id": "REPLACE_WITH_REAL_EFFECT_ID"},
    ],
}, indent=2)


class CapcutTransitionsTab(QWidget):
    """Standalone transition workflow inside the main window, not a new window."""

    def __init__(self, parent=None, controller=None):
        super().__init__(parent)
        self.controller = controller
        self.settings = QSettings("Rajudesktop", "Z Builder Capcut Transitions")
        saved_root = str(self.settings.value("projects_folder", "") or "").strip()
        self.projects_root = Path(saved_root) if saved_root else default_projects_dir()
        self.projects = []
        self.catalog = []
        self.favorite_ids = self._saved_ids("favorites")
        self.selected_ids = self._saved_ids("selected_ids")
        self.spec = None
        self.spec_file = None
        self.plan = None
        self.preview_project = None
        self._drawing = False
        self._build_ui()
        self.refresh()

    def _saved_ids(self, key):
        value = self.settings.value(key, [])
        if isinstance(value, str):
            return {value} if value else set()
        return {str(x) for x in value} if isinstance(value, (list, tuple)) else set()

    def _save_preferences(self):
        self.settings.setValue("projects_folder", str(self.projects_root))
        self.settings.setValue("favorites", sorted(self.favorite_ids))
        self.settings.setValue("selected_ids", sorted(self.selected_ids))

    @staticmethod
    def _button(label, callback):
        b = QPushButton(label)
        b.clicked.connect(callback)
        return b

    @staticmethod
    def _table(columns):
        t = QTableWidget(0, len(columns))
        t.setHorizontalHeaderLabels(columns)
        t.verticalHeader().setVisible(False)
        t.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        t.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        t.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        t.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return t

    def _build_ui(self):
        box = QVBoxLayout(self)
        if self.controller is not None:
            self.project_combo = self.controller.project_combo
            self.capcut_state = self.controller.capcut_state
            self.folder_edit = self.controller.folder_edit
            self.summary = QLabel()
            box.addWidget(self.summary)
        else:
            heading = QLabel("Capcut Transitions — independent native transition editor")
            heading.setStyleSheet("font-size:17px;font-weight:700;color:#eef6ff;")
            box.addWidget(heading)
            description = QLabel(
                "Apply transitions to an existing CapCut project. Videos, images, timing, "
                "layers, motions and audio are never rebuilt. Close CapCut before applying.")
            description.setWordWrap(True)
            box.addWidget(description)

            row = QHBoxLayout()
            row.addWidget(QLabel("CapCut projects folder"))
            self.folder_edit = QLineEdit(str(self.projects_root))
            self.folder_edit.setReadOnly(True)
            row.addWidget(self.folder_edit, 1)
            row.addWidget(self._button("Change folder", self.choose_folder))
            row.addWidget(self._button("Refresh", self.refresh))
            box.addLayout(row)

            project_row = QHBoxLayout()
            project_row.addWidget(QLabel("Project"))
            self.project_combo = QComboBox()
            self.project_combo.currentIndexChanged.connect(self._project_changed)
            project_row.addWidget(self.project_combo, 1)
            self.capcut_state = QLabel()
            project_row.addWidget(self.capcut_state)
            box.addLayout(project_row)
            self.summary = QLabel("Choose a CapCut project to inspect eligible cuts.")
            box.addWidget(self.summary)

        self.sections = QTabWidget()
        box.addWidget(self.sections, 1)
        trans_tab = QWidget()
        edit_tab = QWidget()
        preview_tab = QWidget()
        self.sections.addTab(trans_tab, "Transitions")
        self.sections.addTab(edit_tab, "Edit file")
        self.sections.addTab(preview_tab, "Preview / Log")

        trans = QVBoxLayout(trans_tab)
        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Apply mode"))
        self.mode = QComboBox()
        self.mode.addItem("Edit file only (no baseline changes)", "none")
        self.mode.addItem("Single transition", "single")
        self.mode.addItem("Random mix", "mix")
        self.mode.currentIndexChanged.connect(self.invalidate)
        mode_row.addWidget(self.mode)
        mode_row.addStretch()
        mode_row.addWidget(QLabel("Duration (seconds)"))
        self.duration = QDoubleSpinBox()
        self.duration.setRange(0.2, 1.5)
        self.duration.setSingleStep(0.1)
        self.duration.setDecimals(1)
        self.duration.setValue(0.5)
        self.duration.valueChanged.connect(self.invalidate)
        mode_row.addWidget(self.duration)
        trans.addLayout(mode_row)
        filter_row = QHBoxLayout()
        self.search = QLineEdit()
        self.search.setPlaceholderText("Search native transitions by name, category or effect ID")
        self.search.textChanged.connect(self.draw_catalog)
        filter_row.addWidget(self.search, 1)
        self.favorites_only = QCheckBox("Favorites only")
        self.favorites_only.toggled.connect(self.draw_catalog)
        filter_row.addWidget(self.favorites_only)
        trans.addLayout(filter_row)
        trans.addWidget(QLabel("Transitions are discovered from existing saved CapCut projects. Ctrl/Shift selects multiple."))
        self.catalog_table = self._table(["★", "Transition", "Category", "Effect ID"])
        self.catalog_table.itemSelectionChanged.connect(self._selected_changed)
        trans.addWidget(self.catalog_table, 1)
        favorite_row = QHBoxLayout()
        favorite_row.addWidget(self._button("★ Toggle favorite", self.toggle_favorite))
        favorite_row.addWidget(self._button("Mix favorites", self.mix_favorites))
        self.catalog_info = QLabel()
        favorite_row.addWidget(self.catalog_info, 1)
        trans.addLayout(favorite_row)

        edit = QVBoxLayout(edit_tab)
        explanation = QLabel("Optional AutoCapCut v1 JSON: transition after a filename overrides the baseline choice for that cut.")
        explanation.setWordWrap(True)
        edit.addWidget(explanation)
        edit_row = QHBoxLayout()
        edit_row.addWidget(self._button("Load Edit File (.json)", self.load_edit))
        edit_row.addWidget(self._button("Clear file", self.clear_edit))
        edit_row.addWidget(self._button("Copy sample JSON", self.copy_example))
        edit_row.addStretch()
        edit.addLayout(edit_row)
        self.edit_file_label = QLabel("No Edit File selected")
        edit.addWidget(self.edit_file_label)
        self.example = QTextEdit()
        self.example.setReadOnly(True)
        self.example.setPlainText(EXAMPLE_EDIT_FILE)
        edit.addWidget(self.example, 1)
        note = QLabel("Only transitions already present in saved CapCut projects can apply. Missing and ambiguous names are safely reported in Preview.")
        note.setWordWrap(True)
        edit.addWidget(note)

        prev = QVBoxLayout(preview_tab)
        prev.addWidget(QLabel("Dry-run validation: no CapCut timeline changes until Apply is confirmed."))
        self.preview_table = self._table(["Status", "After", "Transition", "Reason / cut"])
        prev.addWidget(self.preview_table, 1)
        self.warning_box = QTextEdit()
        self.warning_box.setReadOnly(True)
        self.warning_box.setMaximumHeight(120)
        prev.addWidget(self.warning_box)

        footer = QHBoxLayout()
        footer.addWidget(self._button("Validate / Preview", self.validate))
        footer.addWidget(self._button("Open backups folder", self.open_backups))
        footer.addWidget(self._button("Open CapCut", self.open_capcut))
        footer.addStretch()
        self.apply_button = self._button("Apply transitions only", self.apply)
        footer.addWidget(self.apply_button)
        box.addLayout(footer)
        self.status = QLabel("Ready — existing clips, audio and layers will be preserved.")
        self.status.setWordWrap(True)
        box.addWidget(self.status)

    def invalidate(self, *_):
        self.plan = None
        self.preview_project = None

    def selected_project(self):
        value = self.project_combo.currentData()
        if not value:
            return None
        return Path(value)

    def choose_folder(self):
        folder = QFileDialog.getExistingDirectory(
            self, "Choose CapCut projects folder",
            str(self.projects_root if self.projects_root.is_dir() else Path.home()))
        if folder:
            self.projects_root = Path(folder)
            self.folder_edit.setText(str(self.projects_root))
            self._save_preferences()
            self.refresh()

    def refresh(self):
        if self.controller is not None:
            return self.reload_project()
        current = self.project_combo.currentData()
        try:
            self.projects = list_projects(self.projects_root)
            self.catalog = []
        except Exception as exc:
            QMessageBox.warning(self, "Cannot scan CapCut projects", str(exc))
            return
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        for project in self.projects:
            self.project_combo.addItem(project.name, str(project))
        if current:
            index = self.project_combo.findData(current)
            if index >= 0:
                self.project_combo.setCurrentIndex(index)
        self.project_combo.blockSignals(False)
        self._update_capcut_state()
        self.reload_project()
        self.status.setText(f"{len(self.projects)} CapCut projects; {len(self.catalog)} native transition effects detected.")

    def _update_capcut_state(self):
        running = capcut_running()
        self.capcut_state.setText("CapCut OPEN — close before Apply" if running else "CapCut closed")
        self.capcut_state.setStyleSheet("color:#ffc2bd;" if running else "color:#a4e2ba;")

    def _project_changed(self, *_):
        self.reload_project()

    def reload_project(self):
        self.invalidate()
        self.selected_ids.clear()
        project = self.selected_project()
        self.catalog = harvest_transitions(self.projects_root, project=project) if project else []
        self.draw_catalog()
        self.refresh_summary()
        if not self.catalog:
            self.status.setText("No supported native resources in this project. In/Out animations are not supported; only native Combo records are editable.")


    def refresh_summary(self):
        project = self.selected_project()
        if project is None:
            self.summary.setText("No CapCut projects found. Choose the folder containing project draft subfolders.")
            return
        try:
            draft, _, _, warnings = load_project(project)
            eligible, skipped = cut_inventory(draft)
            visual = sum(len(t.get("segments", []))
                         for t in draft.get("tracks", []) if t.get("type") == "video")
            self.summary.setText(
                f"{visual} existing visual clips · {len(eligible)} eligible same-track cuts "
                f"· {len(skipped) + len(warnings)} warnings · {len(self.catalog)} transitions")
        except Exception as exc:
            self.summary.setText(f"Cannot inspect project: {exc}")

    def _visible_selected_ids(self):
        chosen = set()
        for idx in self.catalog_table.selectionModel().selectedRows():
            item = self.catalog_table.item(idx.row(), 3)
            if item:
                chosen.add(item.text())
        return chosen

    def _selected_changed(self):
        if self._drawing:
            return
        shown = {self.catalog_table.item(r, 3).text()
                 for r in range(self.catalog_table.rowCount()) if self.catalog_table.item(r, 3)}
        self.selected_ids = (self.selected_ids - shown) | self._visible_selected_ids()
        self._save_preferences()
        self.invalidate()
        self._update_catalog_info()

    def _update_catalog_info(self):
        self.catalog_info.setText(
            f"{self.catalog_table.rowCount()} shown / {len(self.catalog)} detected · "
            f"{len(self.selected_ids)} selected · {len(self.favorite_ids)} favorites")

    def draw_catalog(self, *_):
        self._drawing = True
        self.catalog_table.blockSignals(True)
        try:
            search = self.search.text().casefold().strip()
            only_favorites = self.favorites_only.isChecked()
            self.catalog_table.setRowCount(0)
            for entry in self.catalog:
                eid = str(entry["effect_id"])
                if only_favorites and eid not in self.favorite_ids:
                    continue
                if search and search not in (
                    str(entry.get("name", "")) + " " + str(entry.get("category", "")) + " " + eid
                ).casefold():
                    continue
                row = self.catalog_table.rowCount()
                self.catalog_table.insertRow(row)
                for col, value in enumerate(
                    ["★" if eid in self.favorite_ids else "", entry.get("label", entry["name"]),
                     entry.get("category", ""), eid]
                ):
                    self.catalog_table.setItem(row, col, QTableWidgetItem(str(value)))
                if eid in self.selected_ids:
                    selection = self.catalog_table.model().index(row, 0)
                    self.catalog_table.selectionModel().select(
                        selection, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        finally:
            self.catalog_table.blockSignals(False)
            self._drawing = False
        self._update_catalog_info()

    def toggle_favorite(self):
        for eid in self._visible_selected_ids():
            if eid in self.favorite_ids:
                self.favorite_ids.remove(eid)
            else:
                self.favorite_ids.add(eid)
        self._save_preferences()
        self.draw_catalog()

    def mix_favorites(self):
        self.selected_ids = set(self.favorite_ids)
        self.mode.setCurrentIndex(self.mode.findData("mix"))
        self._save_preferences()
        self.draw_catalog()
        self.invalidate()

    def load_edit(self):
        path, _ = QFileDialog.getOpenFileName(self, "Choose AutoCapCut Edit File", "", "JSON (*.json);;All files (*)")
        if not path:
            return
        try:
            data = parse_edit_file(Path(path).read_text(encoding="utf-8-sig"))
        except (OSError, ValueError) as exc:
            QMessageBox.warning(self, "Invalid Edit File", str(exc))
            return
        self.spec = data
        self.spec_file = Path(path)
        self.edit_file_label.setText(f"{self.spec_file.name} · {len(self.spec['transitions'])} rules loaded")
        self.invalidate()
        self.sections.setCurrentIndex(1)

    def clear_edit(self):
        self.spec = None
        self.spec_file = None
        self.edit_file_label.setText("No Edit File selected")
        self.invalidate()

    def copy_example(self):
        QGuiApplication.clipboard().setText(EXAMPLE_EDIT_FILE)
        self.status.setText("Example copied — replace transition names and effect IDs with actual catalog entries.")

    def _build_plan(self):
        if self.controller is not None:
            self.controller.require_current()
        path = self.selected_project()
        if path is None:
            raise ValueError("Select an existing CapCut project first.")
        draft, _, _, warnings = load_project(path)
        mode = self.mode.currentData()
        ids = [entry["effect_id"] for entry in self.catalog if entry["effect_id"] in self.selected_ids]
        if mode == "single" and len(ids) != 1:
            raise ValueError("Single mode requires exactly one selected transition.")
        if mode == "mix" and not ids:
            raise ValueError("Random mix requires one or more selected transitions.")
        plan = plan_transitions(draft, self.catalog, mode, ids, self.duration.value(), self.spec)
        plan.warnings = warnings + plan.warnings
        return path, plan

    def validate(self):
        try:
            path, plan = self._build_plan()
        except Exception as exc:
            QMessageBox.warning(self, "Cannot validate transitions", str(exc))
            return False
        self.plan = plan
        self.preview_project = path
        self.preview_table.setRowCount(len(plan.rows))
        for row, entry in enumerate(plan.rows):
            for col, value in enumerate(
                [entry["status"], entry["after"], entry["transition"], entry["reason"]]
            ):
                self.preview_table.setItem(row, col, QTableWidgetItem(str(value)))
        self.warning_box.setPlainText("\n".join(plan.warnings) if plan.warnings
                                      else "No unsafe gaps or overlaps in eligible cuts.")
        counts = plan.counts
        self.status.setText(
            f"Preview: {counts['eligible_cuts']} eligible cuts · {len(plan.chosen)} selected · "
            f"{counts['will_apply']} Will Apply · {counts['missing']} Missing · {counts['skipped']} Skipped")
        self.sections.setCurrentIndex(2)
        return True

    def apply(self):
        # Validate immediately before writing; the engine performs a fresh guarded read.
        if not self.validate():
            return
        if not self.plan or not self.plan.chosen:
            QMessageBox.information(self, "Nothing to apply",
                                    "Choose at least one transition or load a valid Edit File JSON.")
            return
        if capcut_running():
            self._update_capcut_state()
            QMessageBox.warning(self, "Close CapCut", "Close CapCut before applying. Autosave could overwrite the change.")
            return
        question = (
            f"Apply {len(self.plan.chosen)} transition(s) to {self.preview_project.name}?\n\n"
            "Your images, videos, layer order, source and target timings, audio and motions remain intact.\n"
            "A dated, recoverable backup is created before writing.")
        if QMessageBox.question(self, "Apply transitions only?", question,
                                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                                QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
            return
        self.apply_button.setEnabled(False)
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            if self.controller is not None:
                self.controller.require_current()
            result = save_transitions(self.preview_project, self.catalog, self.plan)
        except Exception as exc:
            QMessageBox.critical(self, "Transition application failed", str(exc))
            return
        finally:
            QApplication.restoreOverrideCursor()
            self.apply_button.setEnabled(True)
        if result["saved"]:
            message = (f"Applied {result['changed']} native transition(s); "
                       f"{result['already_matching']} already matched.\n"
                       f"Backup folder: {result['backup_dir']}\n"
                       "Reopen CapCut and check the project.")
        else:
            message = f"Already matching on {result['already_matching']} selected cut(s). No changes written."
        self.status.setText(message.replace("\n", "  "))
        self.refresh_summary()
        if self.controller is not None:
            self.controller.load_selected(force=True)
        QMessageBox.information(self, "CapCut transitions", message)

    def open_backups(self):
        project = self.selected_project()
        if not project:
            return
        directory = project / ".transition_only_backups"
        if not directory.is_dir():
            QMessageBox.information(self, "No backups", "No transitions-only backups found yet.")
            return
        try:
            if sys.platform == "win32":
                os.startfile(str(directory))  # type: ignore[attr-defined]
            else:
                QMessageBox.information(self, "Backups path", str(directory))
        except OSError as exc:
            QMessageBox.warning(self, "Cannot open backups", str(exc))

    def open_capcut(self):
        try:
            if sys.platform == "win32":
                os.startfile("capcut:")  # type: ignore[attr-defined]
            else:
                QMessageBox.information(self, "Open CapCut", "Open CapCut manually on this system.")
        except OSError as exc:
            QMessageBox.warning(self, "CapCut launch unavailable", str(exc))
