"""T Builder: independent keyword workflow with canonical Z Builder library previews."""
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
    QAbstractItemView, QApplication, QCheckBox, QComboBox, QFileDialog, QFormLayout, QHBoxLayout, QHeaderView, QInputDialog,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QDoubleSpinBox,
    QSplitter, QStackedWidget, QTableWidget, QTableWidgetItem, QTabWidget,
    QProgressBar, QTextEdit, QVBoxLayout, QWidget
)

from z_builder.core import Plan, kind_of
from .catalog import Catalog
from .timeline import keyword, used, rebalance
from .generation import prepare, generate, audio_duration
from .capcut_controls_tab import CapcutControlsTab



from PySide6.QtCore import QSettings, QTimer
from PySide6.QtWidgets import QSlider, QScrollArea
from z_builder.ui import Window as LibraryWindow


class Task(QThread):
    done = Signal(object)
    failed = Signal(str)
    log = Signal(str)
    def __init__(self, fn):
        super().__init__()
        self.fn=fn
    def run(self):
        try: self.done.emit(self.fn(self.log.emit))
        except Exception as exc: self.failed.emit(str(exc))


class Strengths(QWidget):
    changed = Signal()
    def __init__(self):
        super().__init__()
        self.rows={};self.weights={};self.layout=QVBoxLayout(self)
        self.total=QLabel('Select keywords · Total 0%');self.layout.addWidget(self.total)
    def rebuild(self, counts):
        if {k:r[3] for k,r in self.rows.items()}==counts: return
        old=dict(self.weights)
        for check,slider,label,count,widget in self.rows.values():
            self.layout.removeWidget(widget);widget.deleteLater()
        self.rows={}
        self.weights=rebalance({k:v for k,v in old.items() if k in counts})
        for k,n in sorted(counts.items(),key=lambda x:x[0].casefold()):
            row=QWidget();box=QHBoxLayout(row);box.setContentsMargins(0,2,0,2)
            check=QCheckBox(f'{k} — {n} available');check.setMinimumWidth(220)
            slider=QSlider(Qt.Orientation.Horizontal);slider.setRange(0,100)
            label=QLabel('0%');label.setMinimumWidth(45)
            for w in (check,slider,label):box.addWidget(w)
            self.rows[k]=(check,slider,label,n,row);self.layout.addWidget(row)
            check.toggled.connect(lambda checked,k=k:self.select(k,checked))
            slider.valueChanged.connect(lambda v,k=k:self.adjust(k,v))
        self.paint()
    def select(self,k,checked):
        if checked:self.weights[k]=max(1,round(100/(len(self.weights)+1)))
        else:self.weights.pop(k,None)
        self.weights=rebalance(self.weights);self.paint();self.changed.emit()
    def adjust(self,k,value):
        if k in self.weights:
            self.weights=rebalance(self.weights,k,value);self.paint();self.changed.emit()
    def paint(self):
        for k,(check,slider,label,n,row) in self.rows.items():
            check.blockSignals(True);slider.blockSignals(True)
            check.setChecked(k in self.weights);slider.setEnabled(k in self.weights)
            slider.setValue(self.weights.get(k,0));label.setText(f'{self.weights.get(k,0)}%')
            check.blockSignals(False);slider.blockSignals(False)
        self.total.setText(f'{len(self.weights)} selected keywords · Total {sum(self.weights.values())}%')


class Window(LibraryWindow):
    def __init__(self, home=None):
        QMainWindow.__init__(self)
        self.home=Path(home) if home else Path(QStandardPaths.writableLocation(QStandardPaths.StandardLocation.AppLocalDataLocation))
        self.home.mkdir(parents=True,exist_ok=True)
        self.catalog=Catalog(self.home/'library.sqlite3')
        self.settings=QSettings('Rajudesktop','T Builder')
        self.plan=None;self.worker=None;self.assets=[];self._last_export_sources=();self.duration=0
        self.setWindowTitle('T Builder');self.resize(1440,890);self.setMinimumSize(1060,700)
        self._ui();self.refresh_library()
        self.refresh_timer=QTimer(self);self.refresh_timer.setInterval(5000)
        self.refresh_timer.timeout.connect(self.refresh_idle);self.refresh_timer.start()

    def _ui(self):
        base=QWidget();outer=QVBoxLayout(base)
        title=QLabel('T BUILDER');title.setStyleSheet('font-size:20px;font-weight:800')
        outer.addWidget(title);self.tabs=QTabWidget();outer.addWidget(self.tabs,1);self.setCentralWidget(base)
        self.setStyleSheet('''
            QMainWindow,QWidget {background:#101a2b;color:#eaf2ff;font-size:13px;}
            QTabBar::tab {background:#1c2a40;padding:5px 12px;border:1px solid #324761;}
            QTabBar::tab:selected {background:#2669ad;color:white;}
            QPushButton {background:#2467a4;border:1px solid #4b83ba;border-radius:5px;padding:6px 10px;color:white;font-weight:600;}
            QPushButton:hover {background:#3386d0;}
            QProgressBar {background:#14243a;border:1px solid #405473;border-radius:5px;min-height:12px;}
            QProgressBar::chunk {background:#3394e7;border-radius:4px;}
            QTableWidget,QTextEdit,QLineEdit,QDoubleSpinBox {background:#14243a;color:#f6f9ff;border:1px solid #405473;}
            QHeaderView::section {background:#253b57;color:#eef6ff;padding:5px;}
            QTableWidget::item:selected {background:#235d9a;}
            QLabel {background:transparent;}
        ''')

        self.media_tab = QWidget()
        media_layout = QVBoxLayout(self.media_tab)
        mcontrols = QHBoxLayout()
        mcontrols.addWidget(self._button('Import Folder', self.import_folder))
        mcontrols.addWidget(self._button('Import Files', self.import_files))
        mcontrols.addWidget(self._button('Download Summary .txt', self.save_summary))
        self.clean_library_button = self._button('Clean Entire Library', self.clean_entire_library)
        self.clean_library_button.setStyleSheet(
            'QPushButton { background:#7b303e;border:1px solid #c15c67;color:white;}'
            'QPushButton:hover {background:#9f3f50;}')
        mcontrols.addWidget(self.clean_library_button)
        self.media_filter = QComboBox()
        self.media_filter.addItems(['All Media', 'Images', 'Videos', 'Used in CapCut Export'])
        self.media_filter.currentIndexChanged.connect(self.refresh_library)
        mcontrols.addWidget(self.media_filter)
        self.media_count = QLabel()
        mcontrols.addWidget(self.media_count, 1)
        media_layout.addLayout(mcontrols)
        split = QSplitter(Qt.Orientation.Horizontal)
        self.media_table = self._table(['Filename', 'Type', 'Status', 'Tags', 'Full path'])
        self.media_table.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
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
        sl.addWidget(self._button('Select All Used Media', self.select_all_used))
        self.render_confirm = QCheckBox('Final CapCut video rendered + checked')
        sl.addWidget(self.render_confirm)
        sl.addWidget(self._button('Delete Selected Used Media (Recycle Bin)', self.delete_used_media))
        sl.addWidget(QLabel('Only media from successful CapCut exports can be recycled.\n'
                            'Nothing is deleted automatically; original files go to Recycle Bin.'))
        sl.addStretch()
        split.addWidget(side)
        split.setSizes([970, 360])
        media_layout.addWidget(split, 1)

        self.tabs.addTab(self.media_tab,'Media Library')
        search_row=QHBoxLayout();self.search=QLineEdit();self.search.setPlaceholderText('Search filenames, tags, keywords or paths')
        self.search.textChanged.connect(self.refresh_library);search_row.addWidget(self.search)
        search_row.addWidget(self._button('Refresh Library / Keywords',self.refresh_library))
        media_layout.insertLayout(1,search_row)
        self.media_filter.setItemText(3,'Used Media Record')
        self.timeline_tab=QWidget();box=QVBoxLayout(self.timeline_tab);self.steps=QTabWidget();box.addWidget(self.steps)
        self.tabs.addTab(self.timeline_tab,'Timeline Builder')
        setup=QWidget();form=QFormLayout(setup)
        self.library_root=QComboBox();self.library_root.currentIndexChanged.connect(self.refresh_keywords)
        form.addRow('Selected media library folder',self.library_root)
        row=QHBoxLayout();self.audio_path=QLineEdit();self.audio_path.setReadOnly(True);row.addWidget(self.audio_path,1)
        row.addWidget(self._button('Select Audio from PC',self.choose_audio));form.addRow('Narration',row)
        self.audio_info=QLabel('Select narration to read its exact duration');form.addRow(self.audio_info)
        row=QHBoxLayout();self.drafts=QLineEdit(str(self.settings.value('drafts','')));row.addWidget(self.drafts,1)
        row.addWidget(self._button('Browse',self.choose_drafts));form.addRow('CapCut drafts folder',row)
        self.project_name=QLineEdit('T Builder Timeline');form.addRow('New project name',self.project_name)
        self.cleanup_check=QCheckBox('Delete Previous Used Media Before Generation');form.addRow(self.cleanup_check)
        form.addRow(QLabel('Cleanup is OFF by default. Review eligible files before confirming. Existing project references are protected.'))
        self.steps.addTab(setup,'Audio & Timeline Setup')
        selection=QWidget();sel=QVBoxLayout(selection)
        sel.addWidget(QLabel('Images · 3–5 seconds · continuous lower visual layer'))
        self.image_strengths=Strengths();area=QScrollArea();area.setWidgetResizable(True);area.setWidget(self.image_strengths);sel.addWidget(area,1)
        self.video_enabled=QCheckBox('Enable Video Selection');sel.addWidget(self.video_enabled)
        self.video_box=QWidget();vb=QVBoxLayout(self.video_box)
        vb.addWidget(QLabel('Videos · 2.5–4 seconds · muted upper visual layer · alternating keywords'))
        self.video_strengths=Strengths();area=QScrollArea();area.setWidgetResizable(True);area.setWidget(self.video_strengths);vb.addWidget(area,1)
        self.coverage=QSlider(Qt.Orientation.Horizontal);self.coverage.setRange(0,100);self.coverage.setValue(20)
        vb.addWidget(self.coverage);self.coverage_info=QLabel();vb.addWidget(self.coverage_info)
        self.coverage.valueChanged.connect(self.update_coverage)
        sel.addWidget(self.video_box,1);self.video_box.hide()
        self.video_enabled.toggled.connect(self.video_box.setVisible);self.update_coverage()
        self.steps.addTab(selection,'Media Selection')
        output=QWidget();out=QVBoxLayout(output)
        out.addWidget(QLabel('Generate a new editable CapCut project: images below, videos above, original narration on its own track.'))
        self.launch=QCheckBox('Launch CapCut after draft verification (select the new project from CapCut Home)');self.launch.setChecked(True);out.addWidget(self.launch)
        self.generate_button=self._button('Generate Timeline & Open in CapCut',self.start_generation);out.addWidget(self.generate_button)
        self.progress=QProgressBar();self.progress.setRange(0,0);self.progress.hide();out.addWidget(self.progress)
        self.export_log=QTextEdit();self.export_log.setReadOnly(True);out.addWidget(self.export_log,1)
        self.steps.addTab(output,'Generate & Open in CapCut')
        self.capcut_controls_tab=CapcutControlsTab(self);self.tabs.addTab(self.capcut_controls_tab,'CapCut Controls')
        self.capcut_controls_tab.project_combo.currentIndexChanged.connect(self.remember_controls_root)
        self.statusBar().showMessage('Ready · independent T Builder catalog')

    def run_task(self,fn,done):
        if self.worker and self.worker.isRunning():return
        self.media_tab.setEnabled(False);self.steps.widget(0).setEnabled(False);self.steps.widget(1).setEnabled(False)
        self.generate_button.setEnabled(False);self.capcut_controls_tab.setEnabled(False);self.progress.show()
        task=Task(fn);self.worker=task
        task.log.connect(self.export_log.append)
        task.done.connect(lambda result:self.task_done(result,done))
        task.failed.connect(self.task_failed)
        task.start()
    def idle(self):
        self.media_tab.setEnabled(True);self.steps.widget(0).setEnabled(True);self.steps.widget(1).setEnabled(True)
        self.generate_button.setEnabled(True);self.capcut_controls_tab.setEnabled(True);self.progress.hide()
    def task_done(self,result,done):
        self.worker.wait();self.idle();self.refresh_library();done(result)
    def task_failed(self,message):
        self.worker.wait();self.idle();self.refresh_library();self.export_log.append(message);self.alert('Operation incomplete',message)
    def refresh_idle(self):
        if not (self.worker and self.worker.isRunning()):
            self.remember_controls_root();self.refresh_library()
    def import_folder(self):
        folder=QFileDialog.getExistingDirectory(self,'Import media folder recursively')
        if folder:self.run_task(lambda log:self.catalog.add_folder(folder),lambda r:self.statusBar().showMessage(f'Imported {r[0]} files; {len(r[1])} errors'))
    def import_files(self):
        names,_=QFileDialog.getOpenFileNames(self,'Import media','','Media (*.jpg *.jpeg *.png *.webp *.bmp *.mp4 *.m4v *.mov *.mkv *.webm *.avi)')
        if not names:return
        def work(log):
            errors=[]
            for name in names:
                try:self.catalog.add_root(Path(name).parent);self.catalog.add(name)
                except Exception as exc:errors.append(f'{name}: {exc}')
            return errors
        self.run_task(work,lambda errors:self.alert('Import warnings','\n'.join(errors)) if errors else None)
    def refresh_library(self,*_):
        self.assets=self.catalog.assets();choice=self.media_filter.currentIndex()
        query=self.search.text().casefold() if hasattr(self,'search') else ''
        selected_paths={self.visible_assets[i.row()]['path'] for i in self.media_table.selectionModel().selectedRows() if i.row()<len(getattr(self,'visible_assets',[]))}
        self.visible_assets=[a for a in self.assets if (choice==0 or choice==3 and a['used'] or choice in (1,2) and a['kind']==('image' if choice==1 else 'video')) and query in ' '.join(str(a[k]) for k in ('filename','tags','keyword','path')).casefold()]
        signature=(choice,query,str(self.assets))
        if signature==getattr(self,'_library_signature',None):
            self.refresh_keywords();return
        self._library_signature=signature
        self.media_table.setRowCount(len(self.visible_assets))
        for row,a in enumerate(self.visible_assets):
            status='Used' if a['used'] else 'Ready' if a['exists'] else 'Missing'
            for col,val in enumerate([a['filename'],a['kind'],status,a['tags'],a['path']]):self.media_table.setItem(row,col,QTableWidgetItem(str(val)))
        for i,a in enumerate(self.visible_assets):
            if a['path'] in selected_paths:self.media_table.selectRow(i)
        self.media_count.setText(f"{len(self.assets)} files · {sum(a['used'] for a in self.assets)} used")
        if hasattr(self,'library_root'):
            roots=self.catalog.roots();old=self.library_root.currentText()
            if roots!=[self.library_root.itemText(i) for i in range(self.library_root.count())]:
                self.library_root.blockSignals(True);self.library_root.clear();self.library_root.addItems(roots)
                if old in roots:self.library_root.setCurrentText(old)
                self.library_root.blockSignals(False)
            self.refresh_keywords()
    def refresh_keywords(self,*_):
        if not hasattr(self,'image_strengths'):return
        root=self.library_root.currentText();counts={'image':{},'video':{}}
        for a in self.assets:
            if root and Path(a['path']).resolve().is_relative_to(Path(root)) and a['exists'] and not a['used']:
                k=a['keyword'];counts[a['kind']][k]=counts[a['kind']].get(k,0)+1
        self.image_strengths.rebuild(counts['image']);self.video_strengths.rebuild(counts['video'])
    def choose_audio(self):
        path,_=QFileDialog.getOpenFileName(self,'Select narration','','Audio (*.mp3 *.wav *.m4a *.aac *.flac *.ogg *.opus *.wma);;All files (*)')
        if path:
            def done(duration):
                self.duration=duration;self.audio_path.setText(path);self.audio_info.setText(f'{duration:.6f} seconds');self.update_coverage()
            self.run_task(lambda log:audio_duration(path),done)
    def choose_drafts(self):
        path=QFileDialog.getExistingDirectory(self,'CapCut drafts folder',self.drafts.text())
        if path:self.drafts.setText(path);self.settings.setValue('drafts',path)
    def update_coverage(self,*_):
        self.coverage_info.setText(f'{self.coverage.value()}% video coverage · {self.duration*self.coverage.value()/100:.6f} seconds requested · feasibility checked before moving media')
    def remember_controls_root(self,*_):
        root=self.capcut_controls_tab.projects_root
        if root.is_dir():self.catalog.remember_drafts(root)
    def draft_locations(self):
        from capcut_visual_controls_standalone.engine import default_root
        roots=[self.drafts.text(),str(self.capcut_controls_tab.projects_root)]
        default=Path(default_root())
        if default.exists():roots.append(str(default))
        return roots
    def start_generation(self):
        self.export_log.clear();self.steps.setCurrentIndex(2)
        args=(self.catalog,self.library_root.currentText(),self.audio_path.text(),dict(self.image_strengths.weights),dict(self.video_strengths.weights) if self.video_enabled.isChecked() else None,self.coverage.value(),self.project_name.text(),self.drafts.text())
        cleanup=self.cleanup_check.isChecked();root=self.library_root.currentText();locations=self.draft_locations();launch=self.launch.isChecked()
        def preflight(log):
            prepared=prepare(*args,log=log)
            candidates,protected=self.catalog.cleanup_candidates(root,locations) if cleanup else ([],[])
            return prepared,candidates,protected
        def ready(result):
            prepared,candidates,protected=result
            if cleanup and candidates:
                dialog=QMessageBox(self);dialog.setWindowTitle('Confirm previous used-media cleanup')
                dialog.setText(f'{len(candidates)} eligible files will go to Recycle Bin. {len(protected)} referenced files protected.')
                dialog.setDetailedText('\n'.join(candidates));dialog.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No);dialog.setDefaultButton(QMessageBox.StandardButton.No)
                if dialog.exec()!=QMessageBox.StandardButton.Yes:
                    self.export_log.append('Generation cancelled. Cleanup was not confirmed.');return
            def work(log):
                if cleanup and candidates:
                    n=self.catalog.cleanup(root,candidates,locations,confirmed=True);log(f'Recycled {n} previously used files')
                return generate(self.catalog,prepared,launch,log)
            self.run_task(work,self.generation_complete)
        self.run_task(preflight,ready)
    def generation_complete(self,result):
        self.export_log.append('SUCCESS · verified editable project: '+result['folder'])
        self.capcut_controls_tab.projects_root=Path(result['folder']).parent;self.capcut_controls_tab.refresh()
        self.statusBar().showMessage('Verified project: '+result['folder'])
    def clean_entire_library(self):
        """Manually clear all catalog items, with distinct keep-files/recycle choices."""
        if self.worker is not None and self.worker.isRunning():
            self.alert('Export in progress', 'Finish the CapCut export before cleaning the library.')
            return
        entries = self.catalog.assets()
        if not entries:
            QMessageBox.information(self, 'Library is empty', 'No images or videos to clean.')
            return
        options = [
            'Clear Library Only (keep ALL original PC files)',
            'Move ALL Library Original Files to Windows Recycle Bin',
        ]
        choice, accepted = QInputDialog.getItem(
            self, 'Clean Entire Media Library',
            f'Choose how to clean {len(entries)} library items.\n'
            'Default keeps all original PC files intact.', options, 0, False)
        if not accepted:
            return
        recycle_originals = choice == options[1]
        n_images = sum(a['kind'] == 'image' for a in entries)
        n_videos = len(entries) - n_images
        if recycle_originals and not self.render_confirm.isChecked():
            self.alert('Render confirmation required',
                       'To remove ALL original PC media, confirm that your final CapCut '
                       'videos have been rendered and verified by ticking the checkbox '
                       'in the right panel. Otherwise choose Clear Library Only.')
            return
        if recycle_originals:
            action_details = (
                'Original PC images/videos imported from ANY folder will be moved '
                'to the Windows Recycle Bin, including UNUSED media.\n'
                'This may break other CapCut projects that still reference these files.\n'
                'T Builder cannot verify final render completion.\n'
                'Failed files will remain in the library for review.')
        else:
            action_details = (
                'Only T Builder library entries, tags, and used-media history will be cleared.\n'
                'No originals, CapCut drafts, or final renders will be deleted.')
        result = QMessageBox.question(
            self, 'Confirm Whole Library Cleanup',
            f'{len(entries)} files: {n_images} images + {n_videos} videos.\n\n'
            f'{action_details}\n\nContinue?',
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No)
        if result != QMessageBox.StandardButton.Yes:
            return
        if recycle_originals:
            phrase, confirmed = QInputDialog.getText(
                self, 'Final confirmation',
                'Type DELETE ALL to move every library original file to Recycle Bin:')
            if not confirmed or phrase.strip() != 'DELETE ALL':
                return
        self.clean_library_button.setEnabled(False)
        self.player.stop()
        self.player.setSource(QUrl())
        self.image.clear()
        try:
            if recycle_originals:
                references=self.catalog.project_references(self.draft_locations())
                protected=[a['path'] for a in entries if str(Path(a['path']).resolve()).casefold() in references]
                if protected:
                    self.alert('Cleanup blocked', f'{len(protected)} files are referenced by active projects. All originals were preserved.');return
                moved, missing, failures = self.catalog.recycle_entire_library()
                text = (f'{len(moved)} original files moved to Recycle Bin.\n'
                        f'{len(missing)} missing original references removed.\n'
                        f'{len(failures)} files could not be cleaned and remain listed.')
                self.statusBar().showMessage(text.replace('\n', '  |  '))
                if failures:
                    self.alert('Partial Library Cleanup',
                               text + '\n\nErrors:\n' + '\n'.join(failures[:15]))
                else:
                    QMessageBox.information(self, 'Library Cleaned', text)
            else:
                removed = self.catalog.clear_library_records()
                self.statusBar().showMessage(
                    f'Cleared {removed} library records. All original PC media preserved.')
                QMessageBox.information(
                    self, 'Library Cleaned',
                    f'{removed} library entries cleared. Original PC media was NOT deleted.')
        except Exception as exc:
            self.alert('Library cleanup error', str(exc))
        finally:
            self.render_confirm.setChecked(False)
            self.media_filter.setCurrentIndex(0)
            self.refresh_library()
            self.clean_library_button.setEnabled(True)

    def delete_used_media(self):
        selected=[self.visible_assets[i.row()]['path'] for i in self.media_table.selectionModel().selectedRows()]
        if not selected:return
        if not self.render_confirm.isChecked():self.alert('Confirmation required','Confirm your final video has been rendered and checked.');return
        try:
            eligible,protected=self.catalog.cleanup_candidates(self.library_root.currentText(),self.draft_locations())
            if not set(selected).issubset(eligible):raise ValueError('Selection includes protected, unrelated or unavailable media. Only unreferenced tracked used files can be recycled.')
            dialog=QMessageBox(self);dialog.setWindowTitle('Recycle selected used media?');dialog.setText(f'{len(selected)} eligible files');dialog.setDetailedText('\n'.join(selected));dialog.setStandardButtons(QMessageBox.StandardButton.Yes|QMessageBox.StandardButton.No);dialog.setDefaultButton(QMessageBox.StandardButton.No)
            if dialog.exec()==QMessageBox.StandardButton.Yes:
                self.player.stop();self.player.setSource(QUrl());self.image.clear()
                self.catalog.cleanup(self.library_root.currentText(),selected,self.draft_locations(),confirmed=True);self.refresh_library()
        except Exception as exc:self.alert('Cleanup blocked',str(exc))
    def closeEvent(self,event):
        if self.worker and self.worker.isRunning():
            self.statusBar().showMessage('Wait for the current operation to complete before closing.');event.ignore();return
        self.player.stop();self.capcut_controls_tab.timer.stop();self.refresh_timer.stop();event.accept()


def main():
    app=QApplication.instance() or QApplication(sys.argv)
    app.setOrganizationName('Rajudesktop');app.setApplicationName('T Builder')
    if os.name=='nt':
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID('Rajudesktop.TBuilder.Desktop')
    window=Window();window.show();return app.exec()
