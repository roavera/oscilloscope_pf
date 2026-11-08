"""Panel para configurar y habilitar la entrada simulada de un canal."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QHBoxLayout,
    QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox, QLabel,
    QVBoxLayout,
)


class SimulatorControls(QGroupBox):
    settings_changed = Signal(dict)

    def __init__(self, parent=None, channel="CH1"):
        super().__init__(f"Generador Blackpill — {channel}", parent)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.waveform = QComboBox()
        for label, value in (("Senoidal", "sine"), ("Cuadrada", "square"),
                             ("Triangular", "triangle")):
            self.waveform.addItem(label, value)
        source_row = QHBoxLayout()
        self.channel_enabled = QCheckBox(f"{channel} activo")
        self.channel_enabled.setChecked(True)
        self.channel_enabled.setToolTip("Apaga o enciende la entrada de este canal en la simulación")
        source_row.addWidget(self.channel_enabled)
        source_row.addWidget(self.waveform, 1)
        form.addRow("Entrada:", source_row)

        self.frequency = self._spin(1.0, 20000.0, 1000.0, 10.0, " Hz", 2)
        self.amplitude = self._spin(0.0, 3.0, 1.5, 0.05, " V", 3)
        self.offset = self._spin(-3.0, 3.0, 0.0, 0.05, " V", 3)
        self.noise = self._spin(0.0, 3.0, 0.0, 0.005, " V RMS", 3)
        form.addRow("Frecuencia:", self.frequency)
        form.addRow("Amplitud pico:", self.amplitude)
        form.addRow("Offset:", self.offset)
        form.addRow("Ruido (σ):", self.noise)
        layout.addLayout(form)
        info = QLabel(
            "Amplitud, offset y ruido en voltios simulados. ADC virtual ±3 V: "
            "la señal se recorta al exceder ese rango."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        self.channel_enabled.toggled.connect(self._emit_settings)
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
        enabled = self.channel_enabled.isChecked()
        for control in (self.waveform, self.frequency, self.amplitude, self.offset, self.noise):
            control.setEnabled(enabled)
        self.settings_changed.emit(self.get_settings())

    def get_settings(self):
        return {
            "enabled": self.channel_enabled.isChecked(),
            "waveform": self.waveform.currentData(),
            "frequency": self.frequency.value(),
            "amplitude": self.amplitude.value(),
            "offset": self.offset.value(),
            "noise": self.noise.value(),
        }


