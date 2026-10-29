"""Image-only native CapCut Combo controls embedded in Z Builder.

Reuses the independently tested Animations Only engine. Nothing in Z Builder's
Scene Plan, Media Library, CapCut exporter, or Transitions Only engine is called
by this panel.
"""
from __future__ import annotations

import json
import secrets
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QSettings, QItemSelectionModel
from PySide6.QtWidgets import (
    QAbstractItemView, QCheckBox, QComboBox, QFileDialog, QHBoxLayout,
    QHeaderView, QLabel, QLineEdit, QMessageBox, QPushButton, QTableWidget,
    QTableWidgetItem, QTextEdit, QVBoxLayout, QWidget,
)

from .engines.animations import (
    capcut_running, default_projects_dir, harvest_animations, image_clips,
    list_projects, load_project, make_plan, resource_is_available, save,
)


class CapcutAnimationsTab(QWidget):
    """Only photo clips are eligible; native video segments must remain intact."""

    def __init__(self, parent=None, controller=None):
        super().__init__(parent)
        import weakref
        self.controller = weakref.proxy(controller) if controller is not None else None
        self.settings = QSettings("Rajudesktop", "CapCut Controls Studio Animations")
        saved = str(self.settings.value("projects_folder", "") or "").strip()
        self.projects_root = Path(saved) if saved else default_projects_dir()
        self.projects = []
        self.catalog = []
        self.images = []
        self.favorite_ids = self._saved_ids("favorites")
        self.selected_effect_ids = self._saved_ids("selected_effect_ids")
        self.preview_rows = []
        self.preview_snapshot = None
        self.preview_result = None
        self.preview_project = None
        self.preview_catalog = []
        self.preview_effect_id = None
        self._drawing = False
        self._draw_ui()
        self.refresh()

    def _saved_ids(self, key):
        values = self.settings.value(key, [])
        if isinstance(values, str):
            return {values} if values else set()
        return set(map(str, values)) if isinstance(values, (list, tuple)) else set()

    def _persist(self):
        self.settings.setValue("projects_folder", str(self.projects_root))
        self.settings.setValue("favorites", sorted(self.favorite_ids))
        self.settings.setValue("selected_effect_ids", sorted(self.selected_effect_ids))

    @staticmethod
    def _button(name, handler):
        btn = QPushButton(name)
        btn.clicked.connect(handler)
        return btn

    @staticmethod
    def _table(columns):
        table = QTableWidget(0, len(columns))
        table.setHorizontalHeaderLabels(columns)
        table.verticalHeader().setVisible(False)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        return table

    def _draw_ui(self):
        layout = QVBoxLayout(self)
        if self.controller is not None:
            self.project_combo = self.controller.project_combo
            self.capcut_state = self.controller.capcut_state
            self.folder = self.controller.folder_edit
            self.summary = QLabel()
            layout.addWidget(self.summary)
        else:
            title = QLabel("CapCut Animations — existing native Combo → Trending presets")
            title.setStyleSheet("font-size:17px;font-weight:700;color:#eef6ff;")
            layout.addWidget(title)
            hint = QLabel("Only PHOTO clips. Animations already used in saved CapCut projects; videos, audio, transitions, timings and layers are preserved.")
            hint.setWordWrap(True)
            layout.addWidget(hint)

            folder = QHBoxLayout()
            folder.addWidget(QLabel("CapCut projects folder"))
            self.folder = QLineEdit(str(self.projects_root))
            self.folder.setReadOnly(True)
            folder.addWidget(self.folder, 1)
            folder.addWidget(self._button("Change folder", self.choose_folder))
            folder.addWidget(self._button("Refresh", self.refresh))
            layout.addLayout(folder)

            project = QHBoxLayout()
            project.addWidget(QLabel("Project"))
            self.project_combo = QComboBox()
            self.project_combo.currentIndexChanged.connect(self._project_changed)
            project.addWidget(self.project_combo, 1)
            self.capcut_state = QLabel()
            project.addWidget(self.capcut_state)
            layout.addLayout(project)
            self.summary = QLabel("Choose a CapCut project.")
            layout.addWidget(self.summary)

        mode_row = QHBoxLayout()
        mode_row.addWidget(QLabel("Apply mode"))
        self.mode = QComboBox()
        self.mode.addItem("Single animation", "single")
        self.mode.addItem("Random selected", "random_selected")
        self.mode.addItem("Random all available", "random_all")
        self.mode.currentIndexChanged.connect(self.invalidate)
        mode_row.addWidget(self.mode)
        mode_row.addWidget(self._button("Randomize ALL images", self.randomize_all))
        mode_row.addStretch()
        self.favorite_only = QCheckBox("Favorites only")
        self.favorite_only.toggled.connect(self.draw_catalog)
        mode_row.addWidget(self.favorite_only)
        layout.addLayout(mode_row)

        self.search = QLineEdit()
        self.search.setPlaceholderText("Search used native animations by name, category or resource ID")
        self.search.textChanged.connect(self.draw_catalog)
        layout.addWidget(self.search)
        self.catalog_table = self._table(["★", "Animation", "Category", "Native Resource ID", "Cache on this PC"])
        self.catalog_table.setMinimumHeight(130)
        self.catalog_table.itemSelectionChanged.connect(self._catalog_selected)
        layout.addWidget(self.catalog_table, 2)

        tools = QHBoxLayout()
        tools.addWidget(self._button("★ Toggle favorite", self.toggle_favorite))
        tools.addWidget(self._button("Mix favorites", self.mix_favorites))
        self.catalog_info = QLabel("")
        tools.addWidget(self.catalog_info, 1)
        layout.addLayout(tools)

        image_row = QHBoxLayout()
        image_row.addWidget(QLabel("Target images (Ctrl/Shift to multi-select)"))
        image_row.addStretch()
        image_row.addWidget(self._button("Clear selection", self.clear_images))
        image_row.addWidget(self._button("Select all images", self.select_all_images))
        layout.addLayout(image_row)
        self.image_table = self._table(["Layer / Index", "Image filename", "Duration", "Already applied"])
        self.image_table.setMinimumHeight(130)
        self.image_table.itemSelectionChanged.connect(self.invalidate)
        layout.addWidget(self.image_table, 3)

        self.preview_table = self._table(["Result", "Image", "Animation", "Applied duration / reason"])
        self.preview_table.setMaximumHeight(150)
        layout.addWidget(self.preview_table, 1)

        buttons = QHBoxLayout()
        buttons.addWidget(self._button("Preview & validate", self.validate))
        buttons.addWidget(self._button("Open backups", self.open_backups))
        buttons.addStretch()
        self.apply_button = self._button("Apply animations to selected images", self.apply)
        buttons.addWidget(self.apply_button)
        layout.addLayout(buttons)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumHeight(85)
        layout.addWidget(self.log)
        self.status = QLabel("Read-only until Apply. Short native animation records are fitted to the image duration.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

    def invalidate(self, *_):
        if hasattr(self, 'preview_table'):
            self.preview_table.setRowCount(0)
        self.preview_rows = []
        self.preview_snapshot = None
        self.preview_result = None
        self.preview_project = None
        self.preview_catalog = []
        self.preview_effect_id = None

    def selected_project(self):
        path = self.project_combo.currentData()
        return Path(path) if path else None

    def choose_folder(self):
        location = QFileDialog.getExistingDirectory(
            self, "Choose CapCut projects folder",
            str(self.projects_root if self.projects_root.exists() else Path.home()))
        if location:
            self.projects_root = Path(location)
            self.folder.setText(str(self.projects_root))
            self._persist()
            self.refresh()

    def refresh(self):
        if self.controller is not None:
            return self.reload_project()
        previous = self.project_combo.currentData()
        try:
            self.projects = list_projects(self.projects_root)
            self.catalog = []
        except Exception as exc:
            QMessageBox.warning(self, "Cannot scan CapCut projects", str(exc))
            return
        self.project_combo.blockSignals(True)
        self.project_combo.clear()
        for path in self.projects:
            self.project_combo.addItem(path.name, str(path))
        index = self.project_combo.findData(previous) if previous else -1
        if index >= 0:
            self.project_combo.setCurrentIndex(index)
        self.project_combo.blockSignals(False)
        self._update_capcut_status()
        self.reload_project()
        self.status.setText(f"{len(self.projects)} projects · {len(self.catalog)} previously used Trending Combo animations detected.")

    def _update_capcut_status(self):
        running = capcut_running()
        self.capcut_state.setText("CapCut OPEN — close before Apply" if running else "CapCut closed")
        self.capcut_state.setStyleSheet("color:#ffc2bd;" if running else "color:#a4e2ba;")

    def _project_changed(self, *_):
        self.reload_project()

    def reload_project(self):
        self.invalidate()
        self.selected_effect_ids.clear()
        snapshot = self.controller.snapshot
        self.catalog = snapshot.animations if snapshot else []
        self.draw_catalog()
        self.refresh_images()
        self.status.setText("Combo duration fits each image. In/Out retiming is unsupported." if self.catalog else "No supported Combo animations in this project. In/Out retiming is unsupported.")

    def refresh_images(self):
        self.images = []
        self.image_table.blockSignals(True)
        self.image_table.setRowCount(0)
        p = self.selected_project()
        if p:
            try:
                raw, warnings = self.controller.snapshot.raw, self.controller.snapshot.warnings
                self.images = image_clips(raw)
                animations = {m.get("id"): m for m in raw.get("materials", {}).get("material_animations", []) if isinstance(m, dict)}
                for clip in self.images:
                    seg = raw["tracks"][clip["track_index"]]["segments"][clip["segment_index"]]
                    names = []
                    for ref in seg.get("extra_material_refs") or []:
                        mat = animations.get(ref, {})
                        for anim in mat.get("animations") or []:
                            if anim.get("type") == "group":
                                names.append(str(anim.get("name") or "Unknown"))
                    r = self.image_table.rowCount()
                    self.image_table.insertRow(r)
                    vals = [
                        f"{clip['track_index']+1} / {clip['segment_index']+1}",
                        clip["name"],
                        f"{clip['duration_us']/1_000_000:g}s",
                        ", ".join(names) or "None",
                    ]
                    for col, value in enumerate(vals):
                        self.image_table.setItem(r, col, QTableWidgetItem(str(value)))
                self.summary.setText(f"{len(self.images)} photos eligible · Combo only; In/Out retiming unsupported · {len(warnings)} warnings")
            except Exception as exc:
                self.summary.setText(f"Cannot read project: {exc}")
        else:
            self.summary.setText("Choose a project containing CapCut photo clips.")
        self.image_table.blockSignals(False)

    def _catalog_selected(self):
        if self._drawing:
            return
        shown = {self.catalog_table.item(r, 3).text()
                 for r in range(self.catalog_table.rowCount()) if self.catalog_table.item(r, 3)}
        chosen = {self.catalog_table.item(i.row(), 3).text()
                  for i in self.catalog_table.selectionModel().selectedRows()}
        self.selected_effect_ids = (self.selected_effect_ids - shown) | chosen
        self._persist()
        self.invalidate()
        self._catalog_info()

    def _catalog_info(self):
        self.catalog_info.setText(
            f"{self.catalog_table.rowCount()} shown / {len(self.catalog)} detected · "
            f"{len(self.selected_effect_ids)} selected · {len(self.favorite_ids)} favorites")

    def draw_catalog(self, *_):
        self._drawing = True
        self.catalog_table.blockSignals(True)
        try:
            text = self.search.text().casefold().strip()
            only_favorites = self.favorite_only.isChecked()
            self.catalog_table.setRowCount(0)
            for entry in self.catalog:
                eid = str(entry["effect_id"])
                if only_favorites and eid not in self.favorite_ids:
                    continue
                if text and text not in (str(entry["name"])+" "+str(entry["category"])+" "+eid).casefold():
                    continue
                row = self.catalog_table.rowCount()
                self.catalog_table.insertRow(row)
                vals = ["★" if eid in self.favorite_ids else "", entry["name"], entry["category"],
                        eid, "Available" if entry.get("available", False) else "Missing"]
                for col, value in enumerate(vals):
                    self.catalog_table.setItem(row, col, QTableWidgetItem(str(value)))
                if eid in self.selected_effect_ids:
                    index = self.catalog_table.model().index(row, 0)
                    self.catalog_table.selectionModel().select(
                        index, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
        finally:
            self.catalog_table.blockSignals(False)
            self._drawing = False
        self._catalog_info()

    def toggle_favorite(self):
        for index in self.catalog_table.selectionModel().selectedRows():
            cell = self.catalog_table.item(index.row(), 3)
            if not cell:
                continue
            eid = cell.text()
            if eid in self.favorite_ids:
                self.favorite_ids.remove(eid)
            else:
                self.favorite_ids.add(eid)
        self._persist()
        self.draw_catalog()

    def mix_favorites(self):
        self.selected_effect_ids = set(self.favorite_ids)
        self.mode.setCurrentIndex(self.mode.findData("random_selected"))
        self._persist()
        self.draw_catalog()
        self.invalidate()

    def select_all_images(self):
        self.image_table.selectAll()
        self.invalidate()

    def clear_images(self):
        self.image_table.clearSelection()
        self.invalidate()

    def randomize_all(self):
        self.mode.setCurrentIndex(self.mode.findData("random_all"))
        self.select_all_images()
        self.validate()

    def _selected_images(self):
        indexes = sorted(i.row() for i in self.image_table.selectionModel().selectedRows())
        return [(self.images[i]["track_index"], self.images[i]["segment_index"]) for i in indexes]

    def _plan(self):
        raise RuntimeError("Use background Preview in CapCut Controls Studio.")

    def validate(self):
        from . import backend
        snapshot = self.controller.snapshot
        if not snapshot:
            self.controller.notify("Choose a valid CapCut project.", error=True)
            return False
        selected, mode = self._selected_images(), self.mode.currentData()
        ids, seed = set(self.selected_effect_ids), secrets.randbits(64)
        self.invalidate()
        def completed(result):
            rows, entries, effect_id, warnings = result
            self.preview_result, self.preview_snapshot = result, snapshot
            self.preview_rows, self.preview_project = rows, snapshot.project
            self.preview_catalog, self.preview_effect_id = entries, effect_id
            self.preview_table.setRowCount(len(rows))
            for row, entry in enumerate(rows):
                for col, val in enumerate([entry['status'],entry.get('name',''),entry.get('animation',''),entry.get('reason','')]):
                    self.preview_table.setItem(row,col,QTableWidgetItem(str(val)))
            count = sum(r.get('status') == 'Will Apply' for r in rows)
            self.log.setPlainText("\n".join(warnings) or "Native resources validated. Videos and audio are preserved.")
            self.status.setText(f"{count} images ready · duration fits each image · Apply creates a backup")
        return self.controller.run_job('Validating animations',lambda: backend.preview_animations(snapshot,selected,mode,ids,seed),completed)

    def apply(self):
        from . import backend
        if self.preview_snapshot is not self.controller.snapshot or not self.preview_rows or not any(r.get('status') == 'Will Apply' for r in self.preview_rows):
            self.controller.notify("Preview valid image animations before Apply.", error=True)
            return
        snapshot, result = self.preview_snapshot, self.preview_result
        self.controller.run_job('Applying animations · backing up draft',
            lambda: backend.apply_animations(snapshot,result),self.controller.saved,write=True)

    def open_backups(self):
        project = self.selected_project()
        if not project:
            return
        folder = project / ".animations_only_backups"
        if not folder.is_dir():
            QMessageBox.information(self, "Backups", "No animations-only backups have been created for this project.")
            return
        try:
            if sys.platform == "win32":
                import os
                os.startfile(folder)
            else:
                self.status.setText(str(folder))
        except Exception as exc:
            QMessageBox.warning(self, "Cannot open backup folder", str(exc))
