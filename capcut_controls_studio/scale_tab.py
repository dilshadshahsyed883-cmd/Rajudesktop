"""Qt controls calling the original V2.1 native Scale/Position/Blur engine."""
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
 QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton, QSpinBox, QTextEdit, QVBoxLayout, QWidget)
from .engines.visual import (
    BLURS, Options, create_preview, load_project, project_fingerprint, save_project)


class CapcutScaleTab(QWidget):
    def __init__(self, controller):
        super().__init__(controller)
        import weakref
        self.controller = weakref.proxy(controller) if controller is not None else None
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
                       seed=self.seed.value(),invert_y=self.invert.isChecked())

    def invalidate(self, *_):
        if hasattr(self, 'log'):
            self.log.clear()
        self.expected = None
        self.preview_snapshot = None
        self.preview_project = None
        self.preview_options = None

    def reload_project(self):
        self.invalidate()
        self.log.clear()

    def preview(self):
        from . import backend
        self.invalidate()
        snapshot = self.controller.snapshot
        if not snapshot:
            self.controller.notify("Choose a valid CapCut project.", error=True)
            return False
        try:
            opts = self.options()
            opts.validate()
        except ValueError as exc:
            self.controller.notify(str(exc), error=True)
            return False
        def completed(result):
            _, rows, counts = result
            self.preview_snapshot, self.preview_options = snapshot, opts
            self.expected, self.preview_project = snapshot.fingerprint, snapshot.project
            self.log.setPlainText("\n".join(snapshot.warnings + [
                f"{counts['images']} images · {counts['videos']} videos · {counts['animated_skipped']} keyframed transforms preserved"
            ] + [f"{r['name']} · scale {r['scale']} · X {r['x']} · Y {r['y']} · {r['status']}" for r in rows]))
        return self.controller.run_job('Previewing Scale / Position / Blur',lambda: backend.preview_scale(snapshot,opts),completed)

    def apply(self):
        from . import backend
        if self.expected is None or self.preview_snapshot is not self.controller.snapshot or self.preview_options != self.options():
            self.controller.notify("Preview these Scale settings before Apply.", error=True)
            return
        snapshot, options = self.preview_snapshot, self.preview_options
        self.controller.run_job('Applying Scale · backing up draft',
            lambda: backend.apply_scale(snapshot,options),self.controller.saved,write=True)
