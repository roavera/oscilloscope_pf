"""Vista XY independiente; conserva intacta la vista temporal."""
import math
import csv
import numpy as np
import pyqtgraph as pg
from PySide6.QtCore import QTimer, Qt, QSignalBlocker
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QLabel, QPushButton, QComboBox, QDoubleSpinBox, QCheckBox, QFileDialog,
    QMessageBox, QButtonGroup)


class XYPanel(QWidget):
    def __init__(self, owner):
        super().__init__(owner.controls.math_controls.parentWidget())
        self.owner = owner
        self.scope = owner.plot
        self.math_panel = owner.controls.math_controls
        self.xy_active = False
        self.last_pairs = None
        self.last_meta = None
        self.root = QVBoxLayout(self)
        self.root.setContentsMargins(8, 5, 8, 5)
        self.root.setSpacing(6)
        row = QHBoxLayout()
        self.math_button = QPushButton('MATH · Y-T')
        self.xy_button = QPushButton('Modo X-Y')
        self.buttons = QButtonGroup(self)
        for b in (self.math_button, self.xy_button):
            b.setCheckable(True)
            self.buttons.addButton(b)
            row.addWidget(b)
        self.math_button.setChecked(True)
        self.root.addLayout(row)
        self.body = QWidget()
        self.root.addWidget(self.body)
        layout = QVBoxLayout(self.body)
        layout.setContentsMargins(0, 4, 0, 0)
        title = QLabel('X-Y · Amplitud frente a amplitud')
        title.setStyleSheet('font-weight: 600; font-size: 16px;')
        layout.addWidget(title)
        grid = QGridLayout()
        self.sources = []
        self.scales = []
        self.offsets = []
        for i, axis in enumerate(('X', 'Y')):
            heading = QLabel('Eje ' + axis)
            heading.setStyleSheet('font-weight: 600;')
            grid.addWidget(heading, 0, i+1)
            source = QComboBox()
            source.addItem('CH1', 0)
            source.addItem('CH2', 1)
            source.setCurrentIndex(i)
            grid.addWidget(source, 1, i+1)
            self.sources.append(source)
            scale = QComboBox()
            for e in range(-9, 10):
                for m in (1, 2, 5):
                    v = float(m * 10.0**e)
                    scale.addItem(f'{v:g}', v)
            scale.setCurrentIndex(scale.findData(1.0))
            grid.addWidget(scale, 2, i+1)
            self.scales.append(scale)
            offset = QDoubleSpinBox()
            offset.setRange(-6 if i == 0 else -4, 6 if i == 0 else 4)
            offset.setDecimals(2)
            offset.setSingleStep(.1)
            offset.setSuffix(' div')
            offset.setKeyboardTracking(False)
            grid.addWidget(offset, 3, i+1)
            self.offsets.append(offset)
        grid.addWidget(QLabel('Fuente'), 1, 0)
        grid.addWidget(QLabel('Escala / div'), 2, 0)
        grid.addWidget(QLabel('Posición'), 3, 0)
        grid.setColumnStretch(1, 1)
        grid.setColumnStretch(2, 1)
        layout.addLayout(grid)
        self.auto = QCheckBox('Escala automática en ambos ejes')
        self.auto.setChecked(True)
        layout.addWidget(self.auto)
        self.aspect = QCheckBox('Divisiones cuadradas (1:1 visual)')
        self.aspect.setChecked(True)
        layout.addWidget(self.aspect)
        row = QHBoxLayout()
        self.drawing = QComboBox()
        self.drawing.addItems(['Línea', 'Puntos'])
        row.addWidget(self.drawing, 1)
        swap = QPushButton('Intercambiar X/Y')
        center = QPushButton('Centrar')
        row.addWidget(swap)
        row.addWidget(center)
        layout.addLayout(row)
        self.status = QLabel('Esperando captura estéreo')
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        row = QHBoxLayout()
        self.csv_button = QPushButton('CSV X-Y')
        self.png_button = QPushButton('PNG X-Y')
        row.addWidget(self.csv_button)
        row.addWidget(self.png_button)
        layout.addLayout(row)
        hint = QLabel('Usa pares de muestras de la captura procesada, antes de la interpolación visual. Los controles temporales siguen configurando la adquisición.')
        hint.setWordWrap(True)
        layout.addWidget(hint)
        self.body.hide()
        self.xy_plot = pg.PlotWidget(parent=self.scope)
        self.xy_plot.setBackground('#151b24')
        self.xy_plot.showGrid(x=True, y=True, alpha=.25)
        self.xy_plot.setMenuEnabled(False)
        self.xy_plot.setMouseEnabled(x=False, y=False)
        self.xy_plot.hideButtons()
        self.xy_plot.setLabel('bottom', 'X', units='div')
        self.xy_plot.setLabel('left', 'Y', units='div')
        for name in ('bottom', 'left'):
            self.xy_plot.getAxis(name).setTickSpacing(1, .5)
            self.xy_plot.getAxis(name).setTextPen('#c3cbd6')
            self.xy_plot.getAxis(name).setPen('#738094')
        self.curve = self.xy_plot.plot([], [], pen=pg.mkPen('#6cdb97', width=1.6))
        self.scope.layout().insertWidget(0, self.xy_plot, 1)
        self.xy_plot.hide()
        self.math_button.clicked.connect(lambda: self.activate(False))
        self.xy_button.clicked.connect(lambda: self.activate(True))
        swap.clicked.connect(self.swap)
        center.clicked.connect(self.center)
        self.csv_button.clicked.connect(self.export_csv)
        self.png_button.clicked.connect(self.export_png)
        self.auto.toggled.connect(self.sync_controls)
        self.timer = QTimer(self)
        self.timer.setInterval(80)
        self.timer.timeout.connect(self.refresh)
        self.sync_controls()

    def sync_controls(self, *_):
        for scale in self.scales:
            scale.setEnabled(not self.auto.isChecked())
        self.refresh()

    def activate(self, enabled):
        self.xy_active = bool(enabled)
        self.math_button.setChecked(not enabled)
        self.xy_button.setChecked(enabled)
        self.body.setVisible(enabled)
        self.math_panel.setVisible(not enabled)
        self.scope.plot_widget.setVisible(not enabled)
        self.scope.timebase_strip.setVisible(not enabled)
        self.xy_plot.setVisible(enabled)
        if enabled:
            self.refresh()
            self.timer.start()
        else:
            self.timer.stop()
            self.last_pairs = None

    def center(self):
        for offset in self.offsets:
            offset.setValue(0)
        self.refresh()

    def swap(self):
        for pair in (self.sources, self.scales):
            a, b = (w.currentIndex() for w in pair)
            pair[0].setCurrentIndex(b)
            pair[1].setCurrentIndex(a)
        # Las posiciones pertenecen a cada eje, no al canal.
        self.refresh()

    def unit(self, ch):
        source = self.owner.acquisition.source
        calibration = self.owner.voltage_calibration
        if source == 'simulator':
            return 'V'
        if source == 'audio' and calibration.has_volts(source):
            return 'V'
        if source == 'blackpill_usb' and calibration.as_dict()['blackpill_usb'][f'ch{ch+1}']['verified']:
            return 'V'
        return 'u.a.'

    def unavailable(self, message):
        self.curve.setData([], [])
        self.last_pairs = None
        self.last_meta = None
        self.status.setText(message)
        self.csv_button.setEnabled(False)
        self.png_button.setEnabled(False)

    def refresh(self):
        if not self.xy_active:
            return
        mode = self.owner.acquisition_processor.get_mode()
        if mode not in ('sampling', 'average', 'high_resolution'):
            self.unavailable('X-Y disponible en Muestreo, Promedio y Alta resolución. Cambiá el modo de adquisición.')
            return
        if not all(self.owner.acquisition.active_channels):
            self.unavailable('Activá los dos canales de adquisición para usar X-Y.')
            return
        raw = self.scope._raw_channels
        if raw is None or raw.ndim != 2 or raw.shape[1] != 2 or len(raw) < 2:
            self.unavailable('Esperando una captura estéreo válida.')
            return
        channels = [int(w.currentData()) for w in self.sources]
        if channels[0] == channels[1]:
            self.unavailable('Elegí canales diferentes para los ejes X e Y.')
            return
        units = [self.unit(ch) for ch in channels]
        data = np.asarray(raw[:, channels], dtype=float)
        valid = np.isfinite(data).all(axis=1)
        if not valid.any():
            self.unavailable('La captura no contiene pares válidos.')
            return
        scales = []
        for i, combo in enumerate(self.scales):
            if self.auto.isChecked():
                peak = float(np.max(np.abs(data[valid, i])))
                required = peak / (5 if i == 0 else 3.3)
                idx = next((j for j in range(combo.count()) if combo.itemData(j) >= required), combo.count()-1) if required > 0 else combo.findData(1.0)
                with QSignalBlocker(combo):
                    combo.setCurrentIndex(idx)
            scales.append(float(combo.currentData()))
        # Dibujar en divisiones; conservar los valores físicos para CSV.
        values = data / np.array(scales) + np.array([w.value() for w in self.offsets])
        values[~valid] = np.nan
        self.xy_plot.setAspectLocked(self.aspect.isChecked(), ratio=1)
        self.xy_plot.setRange(xRange=(-6, 6), yRange=(-4, 4), padding=0, disableAutoRange=True)
        for axis, i in (('bottom', 0), ('left', 1)):
            self.xy_plot.setLabel(axis, f'{"X" if i == 0 else "Y"} · CH{channels[i]+1} · {scales[i]:.5g} {units[i]}/div')
        points = self.drawing.currentIndex() == 1
        self.curve.setData(values[:,0], values[:,1], connect='finite',
                           pen=None if points else pg.mkPen('#6cdb97', width=1.6),
                           symbol='o' if points else None, symbolSize=3,
                           symbolPen=None, symbolBrush='#6cdb97')
        self.last_pairs = data.copy()
        self.last_meta = (channels, units)
        state = 'RUN' if self.owner.running else 'STOP · última captura'
        self.status.setText(f'{state} · {int(valid.sum())} pares · CH{channels[0]+1} → X / CH{channels[1]+1} → Y')
        self.csv_button.setEnabled(True)
        self.png_button.setEnabled(True)

    def export_csv(self):
        if self.last_pairs is None:
            return
        pairs = self.last_pairs.copy()
        channels, units = self.last_meta
        path, _ = QFileDialog.getSaveFileName(self, 'Exportar pares X-Y', 'captura_xy.csv', 'CSV (*.csv)')
        if not path:
            return
        try:
            with open(path, 'w', newline='', encoding='utf-8-sig') as f:
                writer = csv.writer(f)
                writer.writerow([f'x_ch{channels[0]+1}_{units[0]}', f'y_ch{channels[1]+1}_{units[1]}'])
                writer.writerows(pairs)
        except OSError as exc:
            QMessageBox.warning(self, 'Exportación', str(exc))

    def export_png(self):
        if self.last_pairs is None:
            return
        from pyqtgraph.exporters import ImageExporter
        path, _ = QFileDialog.getSaveFileName(self, 'Exportar gráfico X-Y', 'captura_xy.png', 'PNG (*.png)')
        if path:
            try:
                ImageExporter(self.xy_plot.getPlotItem()).export(path)
            except Exception as exc:
                QMessageBox.warning(self, 'Exportación', str(exc))


def install_xy(owner):
    panel = XYPanel(owner)
    owner.xy_panel = panel
    math_panel = owner.controls.math_controls
    layout = math_panel.parentWidget().layout()
    layout.insertWidget(layout.indexOf(math_panel), panel)
