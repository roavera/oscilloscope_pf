"""Panel de filtros: edición explícita y respuesta teórica del diseño."""
import numpy as np
import pyqtgraph as pg
from scipy.signal import freqz, sosfreqz
from PySide6.QtCore import Signal, QTimer, Qt, QSignalBlocker
from PySide6.QtWidgets import (QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout,
    QGroupBox, QLabel, QPushButton, QVBoxLayout, QHBoxLayout, QWidget)
from processing.filters import FilterConfig, design_filter


class FilterControls(QGroupBox):
    configuration_changed = Signal(bool, str, str, float, float, str, int)
    _UI_VERSION = 'FILTER_PANEL_V4'

    def __init__(self, parent=None):
        super().__init__('Filtros digitales', parent)
        self._rate = None
        self._applied = None
        self._valid = False
        layout = QVBoxLayout(self)
        layout.setContentsMargins(10, 12, 10, 10)
        layout.setSpacing(7)
        self.enabled_checkbox = QCheckBox('Activar filtro')
        self.status_label = QLabel('Filtro desactivado')
        self.status_label.setWordWrap(True)
        layout.addWidget(self.enabled_checkbox)
        layout.addWidget(self.status_label)
        self.summary = QLabel('')
        self.summary.setWordWrap(True)
        self.summary.setStyleSheet('font-size: 15px; font-weight: 600;')
        layout.addWidget(self.summary)
        self.rate_label = QLabel('Fs: —  ·  Nyquist: —')
        layout.addWidget(self.rate_label)
        form = QFormLayout()
        form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
        self.family_combo = QComboBox()
        self.family_combo.addItem('IIR · Butterworth', 'iir')
        self.family_combo.addItem('FIR · Hamming', 'fir')
        self.kind_combo = QComboBox()
        for label, value in (('Pasa bajos', 'lowpass'), ('Pasa altos', 'highpass'),
                             ('Pasa banda', 'bandpass'), ('Rechaza banda', 'bandstop')):
            self.kind_combo.addItem(label, value)
        self.channel_combo = QComboBox()
        for label, value in (('Ambos canales', 'both'), ('CH1', 'ch1'), ('CH2', 'ch2')):
            self.channel_combo.addItem(label, value)
        self.taps_combo = QComboBox()
        for taps in (33, 65, 129, 257, 513, 1025):
            self.taps_combo.addItem(f'{taps} coef. · orden {taps-1}', taps)
        self.taps_combo.setCurrentIndex(self.taps_combo.findData(129))
        self.order_label = QLabel('Orden 4 · Butterworth')
        self.low_input = self._frequency_input(1000.0)
        self.high_input = self._frequency_input(5000.0)
        self.low_label = QLabel('Frecuencia de corte')
        self.high_label = QLabel('Corte superior')
        self.taps_label = QLabel('Coeficientes FIR')
        form.addRow('Familia', self.family_combo)
        form.addRow('Respuesta', self.kind_combo)
        form.addRow('Aplicar a', self.channel_combo)
        form.addRow(self.low_label, self.low_input)
        form.addRow(self.high_label, self.high_input)
        form.addRow(self.taps_label, self.taps_combo)
        layout.addLayout(form)
        layout.addWidget(self.order_label)
        self.detail = QLabel('')
        self.detail.setWordWrap(True)
        layout.addWidget(self.detail)
        self.cutoff_note = QLabel()
        self.cutoff_note.setWordWrap(True)
        layout.addWidget(self.cutoff_note)
        self.info_button = QPushButton('▸  Filtros disponibles y características')
        self.info_button.setCheckable(True)
        layout.addWidget(self.info_button)
        self.info = QLabel(
            'IIR · Butterworth: respuesta de magnitud máximamente plana en banda pasante; '
            'fase generalmente no lineal; implementación SOS. Orden de diseño fijo: 4 '
            '(orden total 4 para pasa bajos/altos, 8 para pasa/rechaza banda).\n\n'
            'FIR · Hamming: respuesta impulsional finita, coeficientes simétricos y fase lineal. '
            'Coeficientes / orden: 33/32, 65/64, 129/128, 257/256, 513/512, 1025/1024. '
            'Retardo de grupo = orden / (2·Fs).\n\n'
            'Ambas familias: pasa bajos, pasa altos, pasa banda y rechaza banda. '
            'Un orden mayor suele permitir una transición más estrecha, con mayor coste de cálculo '
            'y, en FIR, mayor retardo. Los cortes deben ser menores que Nyquist.')
        self.info.setWordWrap(True)
        self.info.hide()
        layout.addWidget(self.info)
        self.info_button.toggled.connect(self.info.setVisible)
        self.info_button.toggled.connect(lambda opened: self.info_button.setText(
            ('▾' if opened else '▸') + '  Filtros disponibles y características'))
        self.response_toggle = QCheckBox('Ver respuesta en frecuencia')
        self.response_toggle.setChecked(True)
        layout.addWidget(self.response_toggle)
        self.response = pg.PlotWidget(background='#17202b')
        self.response.setMinimumHeight(145)
        self.response.setMaximumHeight(190)
        self.response.setMenuEnabled(False)
        self.response.setMouseEnabled(x=False, y=False)
        self.response.hideButtons()
        self.response.showGrid(x=True, y=True, alpha=.25)
        for name in ('left', 'bottom'):
            axis = self.response.getAxis(name)
            axis.setPen(pg.mkPen('#8495a8'))
            axis.setTextPen(pg.mkPen('#dce5ef'))
        self.response.setLabel('left', 'Ganancia', units='dB', color='#dce5ef')
        self.response.setLabel('bottom', 'Frecuencia', units='Hz', color='#dce5ef')
        self.response.setYRange(-90, 5, padding=0)
        self.curve = self.response.plot([], [], pen=pg.mkPen('#6cdb97', width=2))
        self.markers = []
        for _ in range(2):
            marker = pg.InfiniteLine(angle=90, movable=False,
                pen=pg.mkPen('#f0bd62', width=1, style=Qt.PenStyle.DashLine))
            self.response.addItem(marker)
            marker.hide()
            self.markers.append(marker)
        layout.addWidget(self.response)
        self.preview_note = QLabel('Respuesta teórica del diseño seleccionado (no FFT de la señal).')
        self.preview_note.setWordWrap(True)
        layout.addWidget(self.preview_note)
        self.validation = QLabel('')
        self.validation.setWordWrap(True)
        layout.addWidget(self.validation)
        buttons = QHBoxLayout()
        self.apply_button = QPushButton('Aplicar configuración')
        self.reset_button = QPushButton('Restablecer')
        buttons.addWidget(self.apply_button, 2)
        buttons.addWidget(self.reset_button, 1)
        layout.addLayout(buttons)
        self._timer = QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(120)
        self._timer.timeout.connect(self._preview)
        for combo in (self.family_combo, self.kind_combo, self.channel_combo, self.taps_combo):
            combo.currentIndexChanged.connect(self._edited)
        for control in (self.low_input, self.high_input):
            control.valueChanged.connect(self._edited)
        self.enabled_checkbox.toggled.connect(self._toggle)
        self.response_toggle.toggled.connect(self.response.setVisible)
        self.response_toggle.toggled.connect(self.preview_note.setVisible)
        self.apply_button.clicked.connect(self._emit)
        self.reset_button.clicked.connect(self.reset)
        self._edited()

    @staticmethod
    def _frequency_input(value):
        control = QDoubleSpinBox()
        control.setRange(0.1, 1e9)
        control.setDecimals(1)
        control.setSingleStep(100.0)
        control.setValue(value)
        control.setSuffix(' Hz')
        control.setKeyboardTracking(False)
        return control

    @staticmethod
    def _hz(value):
        return f'{value/1000:.5g} kHz' if value >= 1000 else f'{value:.5g} Hz'

    def _candidate(self, enabled=True):
        kind = self.kind_combo.currentData()
        low = self.low_input.value()
        high = self.high_input.value() if kind in ('bandpass', 'bandstop') else low
        return FilterConfig(enabled=enabled, kind=kind, channel=self.channel_combo.currentData(),
            cutoff_low=low, cutoff_high=high, family=self.family_combo.currentData(),
            numtaps=self.taps_combo.currentData())

    def sync_context(self, rate, config):
        """Called by the controller; never emits or resets acquisition."""
        rate = float(rate)
        if rate == self._rate and config == self._applied:
            return
        self._rate, self._applied = rate, config
        self.rate_label.setText(f'Fs: {self._hz(rate)}  ·  Nyquist: {self._hz(rate/2)}')
        self._edited()

    def _edited(self, *_):
        band = self.kind_combo.currentData() in ('bandpass', 'bandstop')
        fir = self.family_combo.currentData() == 'fir'
        self.high_label.setVisible(band)
        self.high_input.setVisible(band)
        self.low_label.setText('Corte inferior' if band else 'Frecuencia de corte')
        self.taps_label.setVisible(fir)
        self.taps_combo.setVisible(fir)
        self.order_label.setVisible(True)
        self._valid = False
        self.apply_button.setEnabled(False)
        self._timer.start()

    def _preview(self):
        cfg = self._candidate()
        band = cfg.kind in ('bandpass', 'bandstop')
        cutoffs = [cfg.cutoff_low, cfg.cutoff_high] if band else [cfg.cutoff_low]
        self.summary.setText(f'{self.family_combo.currentText()} · {self.kind_combo.currentText()} · ' + ' – '.join(self._hz(v) for v in cutoffs))
        if cfg.family == 'fir':
            n = (cfg.numtaps - 1) / 2
            delay = f' · {1000*n/self._rate:.4g} ms' if self._rate and self._rate > 0 else ''
            self.order_label.setText(f'FIR Hamming · Orden {cfg.numtaps-1} · {cfg.numtaps} coeficientes')
            self.detail.setText(f'Fase lineal · Retardo de grupo: {n:g} muestras{delay}')
            self.cutoff_note.setText('Corte nominal FIR: aproximadamente −6 dB (amplitud mitad).')
        else:
            total = cfg.order * (2 if band else 1)
            self.order_label.setText(f'IIR Butterworth · Orden total {total} · {total//2} secciones SOS')
            self.detail.setText(f'Orden de diseño {cfg.order} · Fase no lineal · retardo variable.')
            self.cutoff_note.setText('Corte Butterworth: −3 dB respecto de la ganancia en banda pasante.')
        try:
            if self._rate is None:
                raise ValueError('Esperando frecuencia de muestreo')
            coeff = design_filter(self._rate, cfg)
            if cfg.family == 'fir':
                f, h = freqz(coeff, worN=2048, fs=self._rate)
            else:
                f, h = sosfreqz(coeff, worN=2048, fs=self._rate)
            self.curve.setData(f, 20*np.log10(np.maximum(np.abs(h), 1e-9)))
            self.response.setXRange(0, self._rate/2, padding=0)
            for i, marker in enumerate(self.markers):
                marker.setVisible(i < len(cutoffs))
                if i < len(cutoffs):
                    marker.setValue(cutoffs[i])
            self._valid = True
            wanted = self._candidate(self.enabled_checkbox.isChecked())
            applied = self._applied
            matches = applied is not None and all(getattr(wanted, k) == getattr(applied, k) for k in
                ('enabled', 'kind', 'channel', 'family', 'numtaps', 'order', 'cutoff_low'))
            if band:
                matches = matches and wanted.cutoff_high == applied.cutoff_high
            self.validation.setText('Configuración aplicada.' if matches else
                'Vista previa · pulsá Aplicar configuración para confirmar. El filtro anterior sigue vigente hasta aplicar.')
        except (ValueError, TypeError) as exc:
            self._valid = False
            self.curve.setData([], [])
            for marker in self.markers:
                marker.hide()
            self.validation.setText(f'Configuración inválida: {exc}')
        self.apply_button.setEnabled(self._valid)

    def _toggle(self, checked):
        if not checked:
            self._send(False)
        self._edited()

    def _send(self, enabled):
        cfg = self._candidate(enabled)
        self.configuration_changed.emit(cfg.enabled, cfg.kind, cfg.channel,
            cfg.cutoff_low, cfg.cutoff_high, cfg.family, cfg.numtaps)

    def _emit(self, *_):
        self._timer.stop()
        self._preview()
        if self._valid:
            self._send(self.enabled_checkbox.isChecked())
            self._preview()

    def reset(self):
        controls = (self.enabled_checkbox, self.family_combo, self.kind_combo,
            self.channel_combo, self.taps_combo, self.low_input, self.high_input)
        blockers = [QSignalBlocker(c) for c in controls]
        self.enabled_checkbox.setChecked(False)
        self.family_combo.setCurrentIndex(0)
        self.kind_combo.setCurrentIndex(0)
        self.channel_combo.setCurrentIndex(0)
        self.taps_combo.setCurrentIndex(self.taps_combo.findData(129))
        self.low_input.setValue(1000.0)
        self.high_input.setValue(5000.0)
        del blockers
        self._send(False)
        self._edited()
