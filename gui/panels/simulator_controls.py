"""Panel para configurar y habilitar la entrada simulada de un canal."""
from gui.theme.day_style import is_day, day_color
from math import pi, sin

from PySide6.QtCore import QPointF, QSize, Qt, Signal
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PySide6.QtWidgets import (
    QButtonGroup, QCheckBox, QGridLayout, QToolButton, QSizePolicy,
    QDoubleSpinBox, QFormLayout, QGroupBox, QLabel,
    QVBoxLayout, QWidget,
)


WAVES = (
    ("Senoidal", "sine"), ("Cuadrada", "square"), ("Triangular", "triangle"),
    ("Pulso / PWM", "pulse"), ("Continua", "dc"), ("Dos tonos", "two_tone"),
)


def wave_icon(kind):
    pixmap = QPixmap(136, 48)
    pixmap.setDevicePixelRatio(2)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(QPen(QColor(day_color("#61dbbb", "#007D65")), 1.8))
    path = QPainterPath()
    previous = None
    for index in range(125):
        phase = index / 64
        angle = 2 * pi * phase
        if kind == "sine":
            level = sin(angle)
        elif kind in ("square", "pulse"):
            duty = 0.5 if kind == "square" else 0.25
            level = 1 if phase % 1 < duty else -1
        elif kind == "triangle":
            level = 1 - 4 * abs(phase % 1 - 0.5)
        elif kind == "dc":
            level = 0.55
        else:
            level = (sin(angle) + 0.45 * sin(3 * angle)) / 1.45
        x = 3 + index / 2
        point = QPointF(x, 12 - 8 * level)
        if previous is None:
            path.moveTo(point)
        else:
            if kind in ("square", "pulse") and level != previous:
                path.lineTo(x, 12 - 8 * previous)
            path.lineTo(point)
        previous = level
    painter.drawPath(path)
    painter.end()
    return QIcon(pixmap)


class SimulatorControls(QGroupBox):
    settings_changed = Signal(dict)

    def __init__(self, parent=None, channel="CH1"):
        super().__init__(channel, parent)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self.form = form
        self.channel_enabled = QCheckBox(f"{channel} activo")
        self.channel_enabled.setChecked(True)
        layout.addWidget(self.channel_enabled)
        self.wave_buttons = QButtonGroup(self)
        self.wave_selector = QWidget()
        grid = QGridLayout(self.wave_selector)
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setSpacing(4)
        for index, (label, kind) in enumerate(WAVES):
            button = QToolButton()
            button.setCheckable(True)
            button.setText(label)
            button.setAccessibleName(f"{channel}: {label}")
            button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextUnderIcon)
            button.setIcon(wave_icon(kind))
            button.setIconSize(QSize(68, 24))
            button.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            button.setObjectName("waveButton")
            self.wave_buttons.addButton(button, index)
            grid.addWidget(button, index // 3, index % 3)
        self.wave_buttons.button(0).setChecked(True)
        layout.addWidget(self.wave_selector)

        self.frequency = self._spin(1.0, 20000.0, 1000.0, 10.0, " Hz", 2)
        self.amplitude = self._spin(0.0, 1000.0, 1.5, 0.05, " V", 3)
        self.frequency_2 = self._spin(1.0, 20000.0, 3000.0, 10.0, " Hz", 2)
        self.amplitude_2 = self._spin(0.0, 1000.0, 0.75, 0.05, " V", 3)
        self.offset = self._spin(-1000.0, 1000.0, 0.0, 0.05, " V", 3)
        self.noise = self._spin(0.0, 3.0, 0.0, 0.005, " V RMS", 3)
        self.duty = self._spin(1.0, 99.0, 50.0, 1.0, " %", 1)
        form.addRow("Frecuencia:", self.frequency)
        form.addRow("Amplitud pico:", self.amplitude)
        form.addRow("Frecuencia 2:", self.frequency_2)
        form.addRow("Amplitud 2:", self.amplitude_2)
        form.addRow("Offset:", self.offset)
        form.addRow("Ruido (σ):", self.noise)
        form.addRow("Duty PWM:", self.duty)
        layout.addLayout(form)
        info = QLabel(
            "Amplitud pico y offset en voltios. Rango automático por canal."
        )
        info.setWordWrap(True)
        layout.addWidget(info)
        self.channel_enabled.toggled.connect(self._emit_settings)
        self.wave_buttons.idToggled.connect(self._wave_toggled)
        for spin in (self.frequency, self.amplitude, self.frequency_2, self.amplitude_2, self.offset, self.noise, self.duty):
            spin.valueChanged.connect(self._emit_settings)
        self._emit_settings()

    def _scope_v4_refresh(self):
        for index, (_, kind) in enumerate(WAVES):
            self.wave_buttons.button(index).setIcon(wave_icon(kind))

    @staticmethod
    def _spin(minimum, maximum, initial, step, suffix, decimals):
        spin = QDoubleSpinBox()
        spin.setRange(minimum, maximum)
        spin.setDecimals(decimals)
        spin.setSingleStep(step)
        spin.setSuffix(suffix)
        spin.setValue(initial)
        return spin

    def set_waveform(self, kind):
        for index, (_, value) in enumerate(WAVES):
            if kind == value:
                self.wave_buttons.button(index).setChecked(True)
                return
        raise ValueError(f"Forma de onda desconocida: {kind}")

    def _wave_toggled(self, index, checked):
        if checked:
            self._emit_settings()

    def _emit_settings(self, *_):
        enabled = self.channel_enabled.isChecked()
        for control in (self.wave_selector, self.frequency, self.amplitude, self.frequency_2, self.amplitude_2, self.offset, self.noise, self.duty):
            control.setEnabled(enabled)
        kind = WAVES[self.wave_buttons.checkedId()][1]
        self.form.setRowVisible(self.frequency, kind != "dc")
        self.form.setRowVisible(self.frequency_2, kind == "two_tone")
        self.form.setRowVisible(self.amplitude_2, kind == "two_tone")
        self.form.setRowVisible(self.duty, kind == "pulse")
        self.settings_changed.emit(self.get_settings())

    def set_settings(self, settings):
        """Carga todos los parámetros del canal, incluido el duty normalizado."""
        self.set_waveform(settings["waveform"])
        for name in ("frequency", "amplitude", "frequency_2", "amplitude_2", "offset", "noise"):
            getattr(self, name).setValue(settings[name])
        self.duty.setValue(settings["duty"] * 100)
        self.channel_enabled.setChecked(settings["enabled"])

    def get_settings(self):
        return {
            "enabled": self.channel_enabled.isChecked(),
            "waveform": WAVES[self.wave_buttons.checkedId()][1],
            "frequency": self.frequency.value(),
            "amplitude": self.amplitude.value(),
            "frequency_2": self.frequency_2.value(),
            "amplitude_2": self.amplitude_2.value(),
            "offset": self.offset.value(),
            "noise": self.noise.value(),
            "duty": self.duty.value() / 100.0,
        }


