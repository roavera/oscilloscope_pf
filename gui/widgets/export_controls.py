"""Menú de exportación; toma la captura antes de abrir el diálogo."""
from datetime import datetime
from pathlib import Path
from PySide6.QtCore import QObject, Signal, Slot, QRunnable, QThreadPool, QSaveFile, QIODevice
from PySide6.QtWidgets import (QToolButton, QMenu, QFileDialog, QMessageBox, QSizePolicy,
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox, QComboBox, QPushButton)
from exporting.capture_export import write_csv


class ExportSignals(QObject):
    finished=Signal(str)


class CsvJob(QRunnable):
    def __init__(self,path,snapshot,channels,include_math,math_config):
        super().__init__()
        self.path,self.snapshot=path,snapshot
        self.channels,self.include_math,self.math_config=channels,include_math,math_config
        self.signals=ExportSignals()
    def run(self):
        try:
            write_csv(self.path,self.snapshot,self.channels,self.include_math,self.math_config)
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
        self.setObjectName("exportButton")
        self.setStyleSheet("""
            QToolButton#exportButton::menu-indicator {subcontrol-position:right center;right:6px;}
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
    # EXPORT_SELECTION_MATH_V1
    def _choose_export(self, kind):
        """Elegir señales, y tema para PNG, en el hilo de interfaz."""
        dialog = QDialog(self)
        dialog.setWindowTitle('Exportar ' + kind.upper())
        layout = QVBoxLayout(dialog)
        layout.addWidget(QLabel('Señales a incluir:'))
        checks=[]
        for label, enabled in (('CH1',True), ('CH2',True), ('MATH',False)):
            box=QCheckBox(label,dialog)
            box.setChecked(enabled)
            layout.addWidget(box)
            checks.append(box)
        theme=None
        if kind=='png':
            row=QHBoxLayout()
            row.addWidget(QLabel('Tema de la imagen:'))
            theme=QComboBox(dialog)
            theme.addItem('Oscuro','dark')
            theme.addItem('Claro','light')
            current=getattr(self.scope.plot,'display_theme','dark')
            theme.setCurrentIndex(max(0,theme.findData(current)))
            row.addWidget(theme)
            layout.addLayout(row)
        buttons=QHBoxLayout()
        cancel=QPushButton('Cancelar',dialog)
        accept=QPushButton('Continuar',dialog)
        buttons.addWidget(cancel)
        buttons.addWidget(accept)
        cancel.clicked.connect(dialog.reject)
        def validate():
            if not any(box.isChecked() for box in checks):
                QMessageBox.warning(dialog,'Exportar','Seleccioná al menos una señal')
                return
            dialog.accept()
        accept.clicked.connect(validate)
        layout.addLayout(buttons)
        if dialog.exec()!=QDialog.DialogCode.Accepted:
            return None
        return ((1 if checks[0].isChecked() else None,
                 2 if checks[1].isChecked() else None),
                checks[2].isChecked(),theme.currentData() if theme else None)

    @Slot()
    def export_png(self):
        selection=self._choose_export('png')
        if selection is None:return
        selected,include_math,theme=selection
        channels=tuple(ch for ch in selected if ch is not None)
        plot=self.scope.plot
        original_theme=plot.display_theme
        original_channels={ch:bool(plot.channel_visible[ch]) for ch in (1,2)}
        original_math=bool(plot.math_visible)
        # Captura temporal: no cambia permanentemente el display del usuario.
        try:
            for ch in (1,2):
                plot.set_channel_settings(ch,visible=ch in channels)
            plot.set_math_settings(visible=include_math)
            if theme!=original_theme:
                plot.set_display_theme(theme)
            from PySide6.QtWidgets import QApplication
            QApplication.processEvents()
            image=plot.grab()
        except Exception as exc:
            QMessageBox.warning(self,'No se pudo preparar PNG',str(exc))
            return
        finally:
            try:
                if plot.display_theme!=original_theme:
                    plot.set_display_theme(original_theme)
                for ch in (1,2):
                    plot.set_channel_settings(ch,visible=original_channels[ch])
                plot.set_math_settings(visible=original_math)
            except Exception as exc:
                QMessageBox.warning(self,'Restaurar display',str(exc))
        path=self.destination('png')
        if not path:return
        try:save_png(path,image)
        except Exception as exc:QMessageBox.warning(self,'No se pudo guardar',str(exc))
        else:self.setToolTip('Imagen guardada: '+path)

    @Slot()
    def export_csv(self):
        snapshot=self.scope.capture_archive.snapshot()
        if not snapshot or self.busy:return
        selection=self._choose_export('csv')
        if selection is None:return
        selected,include_math,_theme=selection
        channels=tuple(ch for ch in selected if ch is not None)
        # Configuración inmutable: no cambia al modificar MATH durante la escritura.
        math_config=(self.scope.math_processor.math.config if include_math else None)
        path=self.destination('csv')
        if not path:return
        self.busy=True
        self.refresh()
        self.setToolTip('Guardando CSV…')
        self.job=CsvJob(path,snapshot,channels,include_math,math_config)
        self.job.signals.finished.connect(self.finished)
        QThreadPool.globalInstance().start(self.job)
    @Slot(str)
    def finished(self,error):
        self.busy=False
        self.job=None
        self.refresh()
        if error:QMessageBox.warning(self,'No se pudo guardar el CSV',error)
        self.setToolTip('Error al guardar' if error else 'CSV guardado')
