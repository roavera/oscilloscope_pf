"""Panel compacto para los filtros digitales."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QLabel, QPushButton, QVBoxLayout


class FilterControls(QGroupBox):
    configuration_changed = Signal(bool, str, str, float, float)

    def __init__(self, parent=None):
        super().__init__("Filtros digitales", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        self.enabled_checkbox = QCheckBox("Activar filtro")
        layout.addWidget(self.enabled_checkbox)
        form = QFormLayout()
        self.kind_combo = QComboBox()
        for label, value in (("Pasa bajos", "lowpass"), ("Pasa altos", "highpass"), ("Pasa banda", "bandpass"), ("Rechaza banda", "bandstop")):
            self.kind_combo.addItem(label, value)
        self.channel_combo = QComboBox()
        for label, value in (("CH1 + CH2", "both"), ("CH1", "ch1"), ("CH2", "ch2")):
            self.channel_combo.addItem(label, value)
        self.low_input = self._frequency_input(1000.0)
        self.high_input = self._frequency_input(5000.0)
        form.addRow("Tipo:", self.kind_combo)
        form.addRow("Canal:", self.channel_combo)
        form.addRow("Corte inferior:", self.low_input)
        form.addRow("Corte superior:", self.high_input)
        layout.addLayout(form)
        self.reset_button = QPushButton("Restablecer filtro")
        layout.addWidget(self.reset_button)
        self.status_label = QLabel("Filtro desactivado")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.enabled_checkbox.toggled.connect(self._emit)
        self.kind_combo.currentIndexChanged.connect(self._emit)
        self.channel_combo.currentIndexChanged.connect(self._emit)
        self.low_input.valueChanged.connect(self._emit)
        self.high_input.valueChanged.connect(self._emit)
        self.reset_button.clicked.connect(self.reset)
        self.kind_combo.currentIndexChanged.connect(self._update_cutoff_visibility)
        self._update_cutoff_visibility()

    @staticmethod
    def _frequency_input(value):
        control = QDoubleSpinBox()
        control.setRange(1.0, 48000.0)
        control.setDecimals(1)
        control.setSingleStep(100.0)
        control.setValue(value)
        control.setSuffix(" Hz")
        control.setKeyboardTracking(False)
        return control

    def _update_cutoff_visibility(self, *_):
        self.high_input.setEnabled(self.kind_combo.currentData() in ("bandpass", "bandstop"))

    def _emit(self, *_):
        kind = self.kind_combo.currentData()
        band = kind in ("bandpass", "bandstop")
        self.status_label.setText("Filtro activo" if self.enabled_checkbox.isChecked() else "Filtro desactivado")
        self.configuration_changed.emit(self.enabled_checkbox.isChecked(), str(kind), str(self.channel_combo.currentData()), float(self.low_input.value()), float(self.high_input.value() if band else self.low_input.value()))

    def reset(self):
        self.enabled_checkbox.setChecked(False)
        self.kind_combo.setCurrentIndex(0)
        self.channel_combo.setCurrentIndex(0)
        self.low_input.setValue(1000.0)
        self.high_input.setValue(5000.0)
