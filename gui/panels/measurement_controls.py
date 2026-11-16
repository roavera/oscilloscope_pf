"""Lecturas de amplitud de la última captura presentada."""
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QComboBox, QCheckBox,
    QToolButton, QPushButton, QFrame,
)


class MeasurementControls(QWidget):
    overlay_changed = Signal(str, bool)
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
        self.value_labels = {}
        self.checkboxes = {}
        definitions = (
            ("maximum", "Máximo", "Mayor valor de la captura."),
            ("minimum", "Mínimo", "Menor valor de la captura."),
            ("peak_to_peak", "Pico a pico", "Máximo menos mínimo."),
            ("top", "Vtop / superior", "Nivel superior estable; reduce la influencia de picos y ruido."),
            ("base", "Vbase / inferior", "Nivel inferior estable; reduce la influencia de picos y ruido."),
            ("amplitude", "Vamp / amplitud", "Diferencia entre Vtop y Vbase."),
            ("area", "Área integral", "Integral de la tensión respecto del tiempo, en V·s."),
            ("mean", "Valor medio", "Promedio de todas las muestras de la captura."),
            ("rms", "RMS", "Valor eficaz total, incluyendo la componente continua."),
            ("frequency", "Frecuencia", "Inversa del período estimado por cruces ascendentes."),
            ("period", "Período", "Promedio de los intervalos entre cruces ascendentes válidos."),
            ("duty_cycle", "Ciclo de trabajo", "Porcentaje del período en nivel alto."),
            ("high_time", "Ancho alto", "Tiempo que la señal permanece por encima del nivel central."),
            ("low_time", "Ancho bajo", "Tiempo que la señal permanece por debajo del nivel central."),
            ("rise_time", "Subida 10–90 %", "Tiempo de subida entre 10 % y 90 % de la amplitud."),
            ("fall_time", "Bajada 90–10 %", "Tiempo de bajada entre 90 % y 10 % de la amplitud."),
            ("rovshoot", "ROVShoot", "Overshoot positivo después del flanco ascendente."),
            ("fovshoot", "FOVShoot", "Overshoot negativo después del flanco descendente."),
            ("rpreshoot", "RPREShoot", "Excursión positiva antes del flanco ascendente."),
            ("fpreshoot", "FPREShoot", "Excursión negativa antes del flanco descendente."),
            ("phase", "Fase CH1–CH2", "Desfase entre los primeros flancos ascendentes."),
            ("frr", "FRR", "Primer ascendente CH1 a primer ascendente CH2."),
            ("frf", "FRF", "Primer ascendente CH1 a primer descendente CH2."),
            ("ffr", "FFR", "Primer descendente CH1 a primer ascendente CH2."),
            ("fff", "FFF", "Primer descendente CH1 a primer descendente CH2."),
            ("lrr", "LRR", "Último ascendente CH1 a último ascendente CH2."),
            ("lrf", "LRF", "Último ascendente CH1 a último descendente CH2."),
            ("lfr", "LFR", "Último descendente CH1 a último ascendente CH2."),
            ("lff", "LFF", "Último descendente CH1 a último descendente CH2."),
        )
        groups = {
            "Amplitud": {"maximum", "minimum", "peak_to_peak", "top", "base", "amplitude", "area", "mean", "rms"},
            "Tiempo y frecuencia": {"frequency", "period", "duty_cycle", "high_time", "low_time"},
            "Transitorios": {"rise_time", "fall_time", "rovshoot", "fovshoot", "rpreshoot", "fpreshoot"},
            "Entre canales": {"phase", "frr", "frf", "ffr", "fff", "lrr", "lrf", "lfr", "lff"},
        }
        by_key = {key: (label, tooltip) for key, label, tooltip in definitions}
        self.group_buttons = {}
        self.group_widgets = {}
        for group_name, keys in groups.items():
            header = QToolButton()
            header.setText(f"▾  {group_name}")
            header.setCheckable(True)
            header.setChecked(True)
            header.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextOnly)
            header.setStyleSheet("QToolButton { text-align: left; font-weight: 600; padding: 5px; }")
            body = QWidget()
            grid = QGridLayout(body)
            grid.setContentsMargins(8, 0, 2, 4)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(1)
            for row, key in enumerate(definitions_key for definitions_key in by_key if definitions_key in keys):
                label, tooltip = by_key[key]
                check = QCheckBox(label)
                check.setChecked(key in {"maximum", "minimum", "peak_to_peak", "mean", "rms", "frequency", "period"})
                check.setToolTip(tooltip)
                value = QLabel("—")
                value.setStyleSheet("font-size: 16px; font-weight: 600;")
                grid.addWidget(check, row, 0)
                grid.addWidget(value, row, 1)
                self.checkboxes[key] = check
                self.value_labels[key] = value
                check.toggled.connect(self._render)
            layout.addWidget(header)
            layout.addWidget(body)
            self.group_buttons[group_name] = header
            self.group_widgets[group_name] = body
            header.toggled.connect(lambda checked, b=body, h=header, name=group_name: self._toggle_group(b, h, name, checked))
        buttons = QHBoxLayout()
        for text, preset in (("Básicas", "basic"), ("PWM", "pwm"), ("Transitorios", "transient"), ("Dos canales", "channels")):
            button = QPushButton(text)
            button.clicked.connect(lambda _checked=False, p=preset: self._apply_preset(p))
            buttons.addWidget(button)
        layout.addLayout(buttons)
        self.show_overlay = QCheckBox("Mostrar seleccionadas sobre el gráfico")
        self.show_overlay.setToolTip("Muestra las mediciones seleccionadas como una lectura dentro del display.")
        self.show_overlay.toggled.connect(self._render)
        layout.addWidget(self.show_overlay)
        self.timing_status = QLabel()
        self.timing_status.setWordWrap(True)
        layout.addWidget(self.timing_status)
        self.scope = QLabel("Se mide la captura completa, antes de la interpolación.\n"
                            "El zoom y el delay de inspección no delimitan la medición.")
        self.scope.setWordWrap(True)
        layout.addWidget(self.scope)
        layout.addStretch(1)
        self.channel.currentIndexChanged.connect(self._render)

    def _toggle_group(self, body, header, name, checked):
        body.setVisible(checked)
        header.setText(f"{'▾' if checked else '▸'}  {name}")

    def _apply_preset(self, preset):
        presets = {
            "basic": {"maximum", "minimum", "peak_to_peak", "mean", "rms", "frequency", "period"},
            "pwm": {"frequency", "period", "duty_cycle", "high_time", "low_time", "rise_time", "fall_time"},
            "transient": {"rise_time", "fall_time", "rovshoot", "fovshoot", "rpreshoot", "fpreshoot"},
            "channels": {"phase", "frr", "frf", "ffr", "fff", "lrr", "lrf", "lfr", "lff"},
        }
        selected = presets[preset]
        for key, check in self.checkboxes.items():
            check.setChecked(key in selected)

    def set_readings(self, results, units, notes, timing=(None, None), transients=(None, None), interchannel=None):
        self._timing = tuple(timing)
        self._transients = tuple(transients)
        self._interchannel = interchannel
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
        transient = getattr(self, "_transients", (None, None))[ch]
        interchannel = getattr(self, "_interchannel", None)
        timing_enabled = any(self.checkboxes[key].isChecked() for key in (
            "frequency", "period", "duty_cycle", "high_time", "low_time", "rise_time", "fall_time"
        ))
        timing_note = ""
        if result is not None and timing is not None:
            timing_note = (timing.reason if timing.frequency is None else
                           f"Frecuencia estimada con {timing.periods_used} períodos")
        self.timing_status.setText(timing_note)
        self.timing_status.setVisible(timing_enabled and bool(timing_note))
        for key, value in self.value_labels.items():
            enabled = self.checkboxes[key].isChecked()
            value.setVisible(enabled)
            if key in ("frequency", "period", "duty_cycle", "high_time", "low_time", "rise_time", "fall_time"):
                number = getattr(timing, key) if timing is not None and result is not None else None
                unit = "Hz" if key == "frequency" else ("%" if key == "duty_cycle" else "s")
                value.setText(self._format(number, unit))
            elif key in ("rovshoot", "fovshoot", "rpreshoot", "fpreshoot"):
                number = getattr(transient, key) if transient is not None and result is not None else None
                value.setText(self._format(number, "%"))
            elif key in ("phase", "frr", "frf", "ffr", "fff", "lrr", "lrf", "lfr", "lff"):
                number = getattr(interchannel, key) if interchannel is not None and result is not None else None
                value.setText(self._format(number, "°" if key == "phase" else "s"))
            elif key == "area":
                number = getattr(result, key) if result is not None else None
                value.setText(self._format(number, "V·s"))
            else:
                number = getattr(result, key) if result is not None else None
                value.setText(self._format(number, self._units[ch]))
        selected_lines = []
        if result is not None:
            for key, value in self.value_labels.items():
                if self.checkboxes[key].isChecked() and value.text() != "—":
                    selected_lines.append(f"{self._label_for(key)} = {value.text()}")
        self.overlay_changed.emit("\n".join(selected_lines), self.show_overlay.isChecked() and bool(selected_lines))

    @staticmethod
    def _label_for(key):
        return {
            "peak_to_peak": "Vpp", "top": "Vtop", "base": "Vbase",
            "amplitude": "Vamp", "duty_cycle": "Duty", "rise_time": "Rise",
            "fall_time": "Fall", "phase": "Phase",
        }.get(key, key)

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
        if unit == "%":
            return f"{number:.5g} %"
        if unit == "V" and 0 < abs(number) < 1:
            return f"{number * 1000:.5g} mV"
        return f"{number:.5g} {unit}"
