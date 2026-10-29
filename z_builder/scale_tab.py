"""Qt controls calling the original V2.1 native Scale/Position/Blur engine."""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
 QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget)
from capcut_visual_controls_standalone.engine import (
    BLURS, Options, create_preview, load_project, project_fingerprint, save_project)


class CapcutScaleTab(QWidget):
    def __init__(self, controller):
        super().__init__(controller)
        self.controller = controller
        self.projects_root = controller.projects_root
        self.invalidate()
        box = QVBoxLayout(self)
        row = QHBoxLayout()
        self.blur = QCheckBox('Canvas Blur — all images and videos')
        self.blur.setChecked(True)
        self.blur.toggled.connect(self.invalidate)
        row.addWidget(self.blur)
        self.level = QComboBox()
        for name, value in BLURS.items():
            self.level.addItem(name, value)
        self.level.setCurrentIndex(3)
        self.level.currentIndexChanged.connect(self.invalidate)
        row.addWidget(self.level)
        row.addStretch()
        box.addLayout(row)
        groups = QHBoxLayout()
        self.fields = {}
        for kind, defaults in [('Video', (150,170,-250,-190)), ('Image',(105,110,-50,0))]:
            group = QGroupBox(kind + ' Controls')
            form = QFormLayout(group)
            scale = QCheckBox('Scale enabled')
            scale.setChecked(True)
            scale.toggled.connect(self.invalidate)
            self.fields[kind.lower()+'_scale'] = scale
            form.addRow(scale)
            for suffix, label, value, lower, upper in [
                ('scale_min','Minimum scale %', defaults[0],25,400),
                ('scale_max','Maximum scale %', defaults[1],25,400),
                ('y_min','Minimum Y px',defaults[2],-2500,2500),
                ('y_max','Maximum Y px',defaults[3],-2500,2500)]:
                if suffix == 'y_min':
                    position = QCheckBox('Position Y enabled')
                    position.setChecked(True)
                    position.toggled.connect(self.invalidate)
                    self.fields[kind.lower()+'_position'] = position
                    form.addRow(position)
                spin = QDoubleSpinBox()
                spin.setRange(lower,upper)
                spin.setValue(value)
                spin.valueChanged.connect(self.invalidate)
                self.fields[kind.lower()+'_'+suffix] = spin
                form.addRow(label,spin)
            if kind == 'Video':
                spin = QDoubleSpinBox()
                spin.setRange(-2500,2500)
                spin.valueChanged.connect(self.invalidate)
                self.fields['video_x'] = spin
                form.addRow('Position X px',spin)
            else:
                form.addRow(QLabel('Existing image X preserved'))
            groups.addWidget(group)
        box.addLayout(groups)
        row = QHBoxLayout()
        row.addWidget(QLabel('Random seed'))
        self.seed = QSpinBox()
        self.seed.setRange(0,2147483647)
        self.seed.setValue(28)
        self.seed.valueChanged.connect(self.invalidate)
        row.addWidget(self.seed)
        self.invert = QCheckBox('Invert Y Direction')
        self.invert.toggled.connect(self.invalidate)
        row.addWidget(self.invert)
        row.addStretch()
        box.addLayout(row)
        note = QLabel('Clips with transform keyframes keep their transforms. Native animation references are preserved.')
        note.setWordWrap(True)
        box.addWidget(note)
        self.log = QTextEdit()
        self.log.setReadOnly(True)
        box.addWidget(self.log,1)
        row = QHBoxLayout()
        for name,handler in [('Preview Scale',self.preview),('Apply Scale / Position / Blur',self.apply)]:
            button = QPushButton(name)
            button.clicked.connect(handler)
            row.addWidget(button)
        box.addLayout(row)

    def options(self):
        values={key:(widget.isChecked() if isinstance(widget,QCheckBox) else widget.value())
                for key,widget in self.fields.items()}
        return Options(**values,canvas_blur=self.blur.isChecked(),blur_strength=self.level.currentData(),
                       seed=self.seed.value(),invert_y=self.invert.isChecked(),
                       extend_filters=False,extend_effects=False)

    def invalidate(self, *_):
        self.expected = None
        self.preview_project = None
        self.preview_options = None

    def reload_project(self):
        self.invalidate()
        self.log.clear()

    def preview(self):
        self.invalidate()
        try:
            self.controller.require_current()
            project = self.controller.selected_project()
            raw, paths, warnings = load_project(project)
            expected = project_fingerprint(paths)
            opts = self.options()
            _, rows, counts = create_preview(raw,opts)
            if project_fingerprint(paths) != expected:
                raise ValueError('Project changed during preview')
            self.preview_project,self.expected,self.preview_options = project,expected,opts
            self.log.setPlainText('\n'.join(warnings + [
                f"{counts['images']} images · {counts['videos']} videos · {counts['animated_skipped']} transforms preserved for keyframed clips"
            ] + [f"{r['name']} · scale {r['scale']} · X {r['x']} · Y {r['y']} · {r['status']}" for r in rows]))
            return True
        except Exception as exc:
            self.log.setPlainText(str(exc))
            return False

    def apply(self):
        try:
            self.controller.require_current()
            if self.expected is None:
                if not self.preview():
                    return
            if self.preview_project != self.controller.selected_project() or self.preview_options != self.options():
                raise ValueError('Selection or settings changed; preview again.')
            if QMessageBox.question(self,'Apply native controls',f'Apply to {self.preview_project.name}? A recoverable backup will be created.',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No) != QMessageBox.StandardButton.Yes:
                return
            self.controller.require_current()
            result = save_project(self.preview_project,self.preview_options,self.expected)
            self.controller.load_selected(force=True)
            self.log.setPlainText('Saved. Backup: '+result['backup'] if result['saved'] else 'Already matching; no changes written.')
        except Exception as exc:
            QMessageBox.warning(self,'Scale controls',str(exc))
