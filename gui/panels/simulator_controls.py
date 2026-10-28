"""Panel para configurar la señal simulada de CH1."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QLabel,
    QVBoxLayout,
)


class SimulatorControls(QGroupBox):
    settings_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__("Generador Blackpill — CH1", parent)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.waveform = QComboBox()
        for label, value in (("Senoidal", "sine"), ("Cuadrada", "square"),
                             ("Triangular", "triangle")):
            self.waveform.addItem(label, value)
        form.addRow("Señal:", self.waveform)

        self.frequency = self._spin(1.0, 20000.0, 1000.0, 10.0, " Hz", 2)
        self.amplitude = self._spin(0.0, 1.0, 0.5, 0.05, "", 3)
        self.offset = self._spin(-1.0, 1.0, 0.0, 0.05, "", 3)
        self.noise = self._spin(0.0, 0.5, 0.0, 0.005, " RMS", 3)
        form.addRow("Frecuencia:", self.frequency)
        form.addRow("Amplitud pico:", self.amplitude)
        form.addRow("Offset:", self.offset)
        form.addRow("Ruido (σ):", self.noise)
        layout.addLayout(form)
        info = QLabel("Amplitud, offset y ruido en unidades normalizadas (no V calibrados).")
        info.setWordWrap(True)
        layout.addWidget(info)
        self.waveform.currentIndexChanged.connect(self._emit_settings)
        for spin in (self.frequency, self.amplitude, self.offset, self.noise):
            spin.valueChanged.connect(self._emit_settings)

    @staticmethod
    def _spin(minimum, maximum, initial, step, suffix, decimals):
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.setValue(initial)
        return spin

    def _emit_settings(self, *_):
        self.settings_changed.emit({
            "waveform": self.waveform.currentData(),
            "frequency": self.frequency.value(),
            "amplitude": self.amplitude.value(),
            "offset": self.offset.value(),
            "noise": self.noise.value(),
        })
