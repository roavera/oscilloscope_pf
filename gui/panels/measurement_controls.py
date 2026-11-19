"""Lecturas de amplitud de la última captura presentada."""
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QCheckBox,
)


class MeasurementControls(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self._results = (None, None)
        self._timing = (None, None)
        self._units = ("u.a.", "u.a.")
        self._notes = ("Sin captura", "Sin captura")
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        title = QLabel("Mediciones automáticas")
        title.setStyleSheet("font-weight: bold;")
        layout.addWidget(title)
        source = QHBoxLayout()
        source.addWidget(QLabel("Canal"))
        self.channel = QComboBox()
        self.channel.addItems(["CH1", "CH2"])
        source.addWidget(self.channel)
        source.addStretch(1)
        layout.addLayout(source)
        self.status = QLabel("Sin captura")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        grid = QGridLayout()
        self.value_labels = {}
        self.checkboxes = {}
        for row, (key, label, tooltip) in enumerate((
            ("maximum", "Máximo", "Mayor valor de la captura."),
            ("minimum", "Mínimo", "Menor valor de la captura."),
            ("peak_to_peak", "Pico a pico", "Máximo menos mínimo."),
            ("mean", "Valor medio", "Promedio de todas las muestras de la captura."),
            ("rms", "RMS", "Valor eficaz total, incluyendo la componente continua."),
            ("frequency", "Frecuencia", "Inversa del período estimado por cruces ascendentes."),
            ("period", "Período", "Promedio de los intervalos entre cruces ascendentes válidos."),
        )):
            check = QCheckBox(label)
            check.setChecked(True)
            check.setToolTip(tooltip)
            value = QLabel("—")
            value.setStyleSheet("font-size: 18px; font-weight: 600;")
            grid.addWidget(check, row, 0)
            grid.addWidget(value, row, 1)
            self.checkboxes[key] = check
            self.value_labels[key] = value
            check.toggled.connect(self._render)
        layout.addLayout(grid)
        self.timing_status = QLabel()
        self.timing_status.setWordWrap(True)
        layout.addWidget(self.timing_status)
        self.scope = QLabel("Se mide la captura completa, antes de la interpolación.\n"
                            "El zoom y el delay de inspección no delimitan la medición.")
        self.scope.setWordWrap(True)
        layout.addWidget(self.scope)
        layout.addStretch(1)
        self.channel.currentIndexChanged.connect(self._render)

    def set_readings(self, results, units, notes, timing=(None, None)):
        self._timing = tuple(timing)
        self._results, self._units, self._notes = tuple(results), tuple(units), tuple(notes)
        self._render()

    def _render(self, *_):
        ch = self.channel.currentIndex()
        result = self._results[ch]
        note = self._notes[ch]
        if result is not None:
            note += f" · {result.sample_count} muestras"
        self.status.setText(note)
        timing = self._timing[ch]
        timing_enabled = any(self.checkboxes[key].isChecked() for key in ("frequency", "period"))
        timing_note = ""
        if result is not None and timing is not None:
            timing_note = (timing.reason if timing.frequency is None else
                           f"Frecuencia estimada con {timing.periods_used} períodos")
        self.timing_status.setText(timing_note)
        self.timing_status.setVisible(timing_enabled and bool(timing_note))
        for key, value in self.value_labels.items():
            enabled = self.checkboxes[key].isChecked()
            value.setVisible(enabled)
            if key in ("frequency", "period"):
                number = getattr(timing, key) if timing is not None and result is not None else None
                value.setText(self._format(number, "Hz" if key == "frequency" else "s"))
            else:
                number = getattr(result, key) if result is not None else None
                value.setText(self._format(number, self._units[ch]))

    @staticmethod
    def _format(number, unit):
        if number is None:
            return "—"
        if number == 0:
            number = 0.0
        if unit in ("Hz", "s"):
            number = float(f"{number:.5g}")  # Elegir unidad tras redondear evita 1000 µs.
        if unit == "Hz":
            if abs(number) >= 1e6:
                return f"{number / 1e6:.5g} MHz"
            if abs(number) >= 1e3:
                return f"{number / 1e3:.5g} kHz"
        if unit == "s" and 0 < abs(number) < 1:
            if abs(number) < 1e-3:
                return f"{number * 1e6:.5g} µs"
            return f"{number * 1000:.5g} ms"
        if unit == "V" and 0 < abs(number) < 1:
            return f"{number * 1000:.5g} mV"
        return f"{number:.5g} {unit}"
