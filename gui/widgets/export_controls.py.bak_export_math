"""Menú de exportación; toma la captura antes de abrir el diálogo."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool, QSaveFile, QIODevice
from PySide6.QtWidgets import QToolButton, QMenu, QFileDialog, QMessageBox, QSizePolicy
from exporting.capture_export import write_csv


class ExportSignals(QObject):
    finished=Signal(str)


class CsvJob(QRunnable):
    def __init__(self,path,snapshot):
        super().__init__()
        self.path,self.snapshot=path,snapshot
        self.signals=ExportSignals()
    def run(self):
        try:
            write_csv(self.path,self.snapshot)
        except Exception as exc:
            self.signals.finished.emit(str(exc))
        else:
            self.signals.finished.emit('')


def save_png(path,pixmap):
    file=QSaveFile(str(path))
    if not file.open(QIODevice.OpenModeFlag.WriteOnly):
        raise OSError(file.errorString())
    if not pixmap.save(file,'PNG'):
        file.cancelWriting()
        raise OSError('No se pudo codificar la imagen PNG')
    if not file.commit():raise OSError(file.errorString())


class ExportControls(QToolButton):
    def __init__(self,scope):
        super().__init__(scope.controls)
        self.scope=scope
        self.busy=False
        self.last_directory=''
        self.job=None
        self.setText('Exportar')
        self.setToolTip('Guardar imagen PNG o exportar muestras CSV')
        self.setFixedHeight(24)
        self.setFixedWidth(110)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        self.setStyleSheet("""
            QToolButton {background:#34465a;color:#f0f4f8;border:1px solid #60758b;
                         border-radius:4px;padding:2px 16px;font-weight:bold;}
            QToolButton:hover {background:#465d76;}
            QToolButton::menu-indicator {subcontrol-position:right center;right:6px;}
        """)
        self.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        menu=QMenu(self)
        self.png_action=menu.addAction('Guardar imagen — PNG')
        self.csv_action=menu.addAction('Exportar muestras originales — CSV')
        self.setMenu(menu)
        self.png_action.triggered.connect(self.export_png)
        self.csv_action.triggered.connect(self.export_csv)
        menu.aboutToShow.connect(self.refresh)
        self.refresh()
    def refresh(self):
        self.csv_action.setEnabled(bool(self.scope.capture_archive.visible) and not self.busy)
    def destination(self,suffix):
        default=Path(self.last_directory)/('osciloscopio_'+datetime.now().strftime('%Y%m%d_%H%M%S')+'.'+suffix)
        path,_=QFileDialog.getSaveFileName(self,'Guardar '+suffix.upper(),str(default),suffix.upper()+' (*.'+suffix+')')
        if not path:return None
        if not path.lower().endswith('.'+suffix):
            path+='.'+suffix
            if Path(path).exists():
                answer=QMessageBox.question(self,'Reemplazar archivo',
                    'El archivo ya existe. ¿Querés reemplazarlo?',
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No)
                if answer != QMessageBox.StandardButton.Yes:return None
        self.last_directory=str(Path(path).parent)
        return path
    @Slot()
    def export_png(self):
        image=self.scope.plot.grab()  # Congelar antes del diálogo modal.
        path=self.destination('png')
        if not path:return
        try:save_png(path,image)
        except Exception as exc:QMessageBox.warning(self,'No se pudo guardar',str(exc))
        else:self.setToolTip('Imagen guardada: '+path)
    @Slot()
    def export_csv(self):
        snapshot=self.scope.capture_archive.snapshot()
        if not snapshot or self.busy:return
        path=self.destination('csv')
        if not path:return
        self.busy=True
        self.refresh()
        self.setToolTip('Guardando CSV…')
        self.job=CsvJob(path,snapshot)
        self.job.signals.finished.connect(self.finished)
        QThreadPool.globalInstance().start(self.job)
    @Slot(str)
    def finished(self,error):
        self.busy=False
        self.job=None
        self.refresh()
        if error:QMessageBox.warning(self,'No se pudo guardar el CSV',error)
        self.setToolTip('Error al guardar' if error else 'CSV guardado')
