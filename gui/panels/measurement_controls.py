
from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QCheckBox, QPushButton, QDialog, QDialogButtonBox,
    QListWidget, QListWidgetItem, QLineEdit, QTabWidget, QGridLayout,
    QFrame, QScrollArea, QSizePolicy, QButtonGroup)
import math

class MeasurementControls(QWidget):
    overlay_changed = Signal(str, bool)
    CARD_LAYOUT_V2 = True
    DEFINITIONS = (('maximum', 'Máximo', 'Mayor valor de la captura.'), ('minimum', 'Mínimo', 'Menor valor de la captura.'), ('peak_to_peak', 'Pico a pico', 'Máximo menos mínimo.'), ('top', 'Vtop / superior', 'Nivel superior estable; reduce la influencia de picos y ruido.'), ('base', 'Vbase / inferior', 'Nivel inferior estable; reduce la influencia de picos y ruido.'), ('amplitude', 'Vamp / amplitud', 'Diferencia entre Vtop y Vbase.'), ('area', 'Área integral', 'Integral de la tensión respecto del tiempo, en V·s.'), ('mean', 'Valor medio', 'Promedio de todas las muestras de la captura.'), ('rms', 'RMS', 'Valor eficaz total, incluyendo la componente continua.'), ('frequency', 'Frecuencia', 'Inversa del período estimado por cruces ascendentes.'), ('period', 'Período', 'Promedio de los intervalos entre cruces ascendentes válidos.'), ('duty_cycle', 'Ciclo de trabajo', 'Porcentaje del período en nivel alto.'), ('high_time', 'Ancho alto', 'Tiempo que la señal permanece por encima del nivel central.'), ('low_time', 'Ancho bajo', 'Tiempo que la señal permanece por debajo del nivel central.'), ('rise_time', 'Subida 10–90 %', 'Tiempo de subida entre 10 % y 90 % de la amplitud.'), ('fall_time', 'Bajada 90–10 %', 'Tiempo de bajada entre 90 % y 10 % de la amplitud.'), ('rovshoot', 'ROVShoot', 'Overshoot positivo después del flanco ascendente.'), ('fovshoot', 'FOVShoot', 'Overshoot negativo después del flanco descendente.'), ('rpreshoot', 'RPREShoot', 'Excursión positiva antes del flanco ascendente.'), ('fpreshoot', 'FPREShoot', 'Excursión negativa antes del flanco descendente.'), ('phase', 'Fase CH1–CH2', 'Desfase entre los primeros flancos ascendentes.'), ('frr', 'FRR', 'Primer ascendente CH1 a primer ascendente CH2.'), ('frf', 'FRF', 'Primer ascendente CH1 a primer descendente CH2.'), ('ffr', 'FFR', 'Primer descendente CH1 a primer ascendente CH2.'), ('fff', 'FFF', 'Primer descendente CH1 a primer descendente CH2.'), ('lrr', 'LRR', 'Último ascendente CH1 a último ascendente CH2.'), ('lrf', 'LRF', 'Último ascendente CH1 a último descendente CH2.'), ('lfr', 'LFR', 'Último descendente CH1 a último ascendente CH2.'), ('lff', 'LFF', 'Último descendente CH1 a último descendente CH2.'))
    GROUPS = {'Amplitud': {'minimum', 'mean', 'top', 'maximum', 'amplitude', 'area', 'rms', 'peak_to_peak', 'base'}, 'Tiempo y frecuencia': {'period', 'frequency', 'high_time', 'low_time', 'duty_cycle'}, 'Transitorios': {'rise_time', 'fovshoot', 'fall_time', 'rpreshoot', 'rovshoot', 'fpreshoot'}, 'Entre canales': {'fff', 'lff', 'frr', 'frf', 'ffr', 'lrr', 'lrf', 'lfr', 'phase'}}
    PRESETS = {'basic': {'minimum', 'mean', 'period', 'maximum', 'frequency', 'rms', 'peak_to_peak'}, 'pwm': {'period', 'rise_time', 'fall_time', 'frequency', 'high_time', 'low_time', 'duty_cycle'}, 'transient': {'rise_time', 'fovshoot', 'fall_time', 'rpreshoot', 'rovshoot', 'fpreshoot'}, 'channels': {'fff', 'lff', 'frr', 'frf', 'ffr', 'lrr', 'lrf', 'lfr', 'phase'}}
    PAIR = frozenset(GROUPS["Entre canales"])
    TIME = frozenset(("frequency", "period", "duty_cycle", "high_time", "low_time", "rise_time", "fall_time"))
    TRANSIENT = frozenset(("rovshoot", "fovshoot", "rpreshoot", "fpreshoot"))

    def __init__(self, parent=None):
        super().__init__(parent)
        self._results = self._timing = self._transients = (None, None)
        self._units = ("u.a.", "u.a.")
        self._notes = ("Sin captura", "Sin captura")
        self._interchannel = None
        self._selected = set(self.PRESETS["basic"])
        self._rows = []
        self._labels = {k: (label, tip) for k, label, tip in self.DEFINITIONS}
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        header = QHBoxLayout()
        title = QLabel("Mediciones automáticas")
        title.setStyleSheet("font-weight: bold;")
        header.addWidget(title, 1)
        add = QPushButton("+ Mediciones")
        add.clicked.connect(self._catalog)
        header.addWidget(add)
        layout.addLayout(header)
        options = QHBoxLayout()
        self.channel = QButtonGroup(self)
        self.channel.setExclusive(True)
        for idx, label in enumerate(("Ambos", "CH1", "CH2")):
            button = QPushButton(label)
            button.setCheckable(True)
            self.channel.addButton(button, idx)
            options.addWidget(button)
        self.channel.button(0).setChecked(True)
        self.channel.button(0).setToolTip("Mostrar ambos canales sin modificar la adquisición.")
        layout.addLayout(options)
        options = QHBoxLayout()
        self.profile = QComboBox()
        for label, key in (("Personalizado", "custom"), ("Básicas", "basic"), ("PWM", "pwm"), ("Transitorios", "transient"), ("Dos canales", "channels")):
            self.profile.addItem(label, key)
        self.profile.setCurrentIndex(1)
        options.addWidget(self.profile, 1)
        clear = QPushButton("Limpiar")
        clear.clicked.connect(self._clear_selection)
        options.addWidget(clear)
        layout.addLayout(options)
        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.content = QWidget()
        self.cards_layout = QVBoxLayout(self.content)
        self.cards_layout.setContentsMargins(0, 0, 4, 0)
        self.cards_layout.setSpacing(7)
        self.scroll.setWidget(self.content)
        layout.addWidget(self.scroll, 1)
        self.show_overlay = QCheckBox("Mostrar resultados sobre el gráfico")
        layout.addWidget(self.show_overlay)
        self.status = QLabel()
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.status.setToolTip("Se mide la captura completa antes de interpolar. El zoom y el delay de inspección no delimitan la medición.")
        self.channel.idClicked.connect(self._render)
        self.profile.currentIndexChanged.connect(self._profile_changed)
        self.show_overlay.toggled.connect(self._render)
        self._rebuild()

    def _remove(self, key):
        self._selected.discard(key)
        self._custom()

    def _make_card(self, key, pair):
        label, tip = self._labels[key]
        card = QFrame()
        card.setObjectName("measurementCard")
        card.setStyleSheet("""
            QFrame#measurementCard { background: #202936; border: 1px solid #354356; border-radius: 7px; }
            QFrame#measurementCard QLabel { background: transparent; border: none; color: #e2eaf4; }
            QFrame#measurementCard QPushButton { background: transparent; color: #aab8ca; border: none; padding: 0; }
            QFrame#measurementCard QPushButton:hover { color: white; background: #46566b; }
        """)
        card.setToolTip(tip)
        v = QVBoxLayout(card)
        v.setContentsMargins(9, 6, 9, 6)
        v.setSpacing(3)
        top = QHBoxLayout()
        name = QLabel(label)
        name.setWordWrap(True)
        top.addWidget(name, 1)
        remove = QPushButton("×")
        remove.setFixedSize(23, 23)
        remove.setToolTip("Quitar " + label)
        remove.clicked.connect(lambda checked=False, k=key: self._remove(k))
        top.addWidget(remove)
        v.addLayout(top)
        rows = {}
        for ch in ((0,) if pair else (0, 1)):
            row = QWidget()
            h = QHBoxLayout(row)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(4)
            color = "#e2eaf4" if pair else ("#f3d34e" if ch == 0 else "#63c7ef")
            tag = QLabel("CH1 → CH2" if pair else f"CH{ch+1}")
            tag.setStyleSheet(f"color: {color}; font-size: 11px;")
            value = QLabel("—")
            value.setStyleSheet(f"color: {color}; font-size: 15px; font-weight: 600;")
            value.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
            h.addWidget(tag)
            h.addWidget(value, 1)
            v.addWidget(row)
            rows[ch] = (row, value)
        if pair:
            desc = QLabel(tip)
            desc.setWordWrap(True)
            desc.setStyleSheet("color: #aab8ca; font-size: 10px;")
            v.addWidget(desc)
        self._rows.append((key, rows))
        return card

    def _profile_changed(self, *_):
        key = self.profile.currentData()
        if key != "custom":
            self._selected = set(self.PRESETS[key])
            self._rebuild()

    def _custom(self):
        self.profile.blockSignals(True)
        self.profile.setCurrentIndex(0)
        self.profile.blockSignals(False)
        self._rebuild()

    def _clear_selection(self):
        self._selected.clear()
        self._custom()

    def _catalog(self):
        dialog = QDialog(self)
        dialog.setWindowTitle("Seleccionar mediciones")
        dialog.resize(440, 430)
        layout = QVBoxLayout(dialog)
        search = QLineEdit()
        search.setPlaceholderText("Buscar medición…")
        layout.addWidget(search)
        tabs = QTabWidget()
        layout.addWidget(tabs)
        items = {}
        for group, keys in self.GROUPS.items():
            listing = QListWidget()
            tabs.addTab(listing, group)
            for key, label, tip in self.DEFINITIONS:
                if key not in keys:
                    continue
                item = QListWidgetItem(label, listing)
                item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
                item.setCheckState(Qt.CheckState.Checked if key in self._selected else Qt.CheckState.Unchecked)
                item.setToolTip(tip)
                items[key] = item
        def filter_items(text):
            matches = []
            for key, item in items.items():
                visible = text.casefold() in (item.text() + " " + key + " " + item.toolTip()).casefold()
                item.setHidden(not visible)
                if visible:
                    matches.append(item.listWidget())
            if text and matches and tabs.currentWidget() not in matches:
                tabs.setCurrentWidget(matches[0])
        search.textChanged.connect(filter_items)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._selected = {key for key, item in items.items() if item.checkState() == Qt.CheckState.Checked}
            self._custom()

    def _rebuild(self):
        while self.cards_layout.count():
            item = self.cards_layout.takeAt(0)
            if item.widget() is not None:
                item.widget().hide()
                item.widget().deleteLater()
        self._rows = []
        for group, keys in self.GROUPS.items():
            chosen = [k for k, _, _ in self.DEFINITIONS if k in self._selected and k in keys]
            if not chosen:
                continue
            section = QLabel(group if group != "Entre canales" else "Entre canales · CH1 → CH2")
            section.setStyleSheet("font-weight: 600;")
            self.cards_layout.addWidget(section)
            holder = QWidget()
            grid = QGridLayout(holder)
            grid.setContentsMargins(0, 0, 0, 0)
            grid.setSpacing(6)
            grid.setColumnStretch(0, 1)
            grid.setColumnStretch(1, 1)
            for i, key in enumerate(chosen):
                grid.addWidget(self._make_card(key, key in self.PAIR), i // 2, i % 2)
            self.cards_layout.addWidget(holder)
        if not self._selected:
            empty = QLabel("Agregá mediciones o elegí un perfil.")
            empty.setWordWrap(True)
            self.cards_layout.addWidget(empty)
        self.cards_layout.addStretch(1)
        self._render()

    def set_readings(self, results, units, notes, timing=(None, None), transients=(None, None), interchannel=None):
        self._results, self._units, self._notes = tuple(results), tuple(units), tuple(notes)
        self._timing, self._transients = tuple(timing), tuple(transients)
        self._interchannel = interchannel
        self._render()

    def _reading(self, key, ch):
        if key in self.PAIR:
            obj = self._interchannel if all(r is not None for r in self._results) else None
            unit = "°" if key == "phase" else "s"
        elif self._results[ch] is None:
            return "—", self._notes[ch]
        elif key in self.TIME:
            obj = self._timing[ch]
            unit = "Hz" if key == "frequency" else "%" if key == "duty_cycle" else "s"
        elif key in self.TRANSIENT:
            obj, unit = self._transients[ch], "%"
        else:
            obj = self._results[ch]
            unit = self._units[ch] + "·s" if key == "area" else self._units[ch]
        number = getattr(obj, key, None)
        reason = getattr(obj, "reason", "") or "Sin resultado válido"
        if number is None or not math.isfinite(number):
            return "—", reason
        return self._format(number, unit), ""

    def _render(self, *_):
        idx = self.channel.checkedId()
        channels = (0, 1) if idx <= 0 else (idx - 1,)
        lines = []
        for key, rows in self._rows:
            pair = key in self.PAIR
            for ch, (row, label) in rows.items():
                visible = pair or ch in channels
                row.setVisible(visible)
                if not visible:
                    continue
                value, reason = self._reading(key, ch)
                if label.text() != value:
                    label.setText(value)
                label.setToolTip(reason or self._labels[key][1])
                if value != "—":
                    prefix = "CH1→CH2" if pair else f"CH{ch+1}"
                    lines.append(f"{prefix} {self._label_for(key)} = {value}")
        notes = []
        for ch in channels:
            result = self._results[ch]
            note = self._notes[ch]
            if result is not None:
                note += f" · {result.sample_count} muestras"
            timing = self._timing[ch]
            if self._selected & self.TIME and timing is not None:
                if timing.frequency is None:
                    note += " · " + (timing.reason or "Sin frecuencia válida")
                else:
                    note += f" · {timing.periods_used} períodos"
            notes.append(f"CH{ch+1}: {note}")
        if self._selected & self.PAIR:
            reason = getattr(self._interchannel, "reason", "")
            if not all(r is not None for r in self._results):
                reason = "Se requieren ambos canales con datos"
            elif self._interchannel is None:
                reason = "Sin medición entre canales válida"
            if reason:
                notes.append("CH1→CH2: " + reason)
        if not self._selected:
            notes.insert(0, "Agregá mediciones o elegí un perfil.")
        self.status.setText("\n".join(notes))
        # Limitar la superposición para no cubrir todo el display.
        shown = lines[:8]
        if len(lines) > 8:
            shown.append(f"+ {len(lines)-8} mediciones en el panel")
        self.overlay_changed.emit("\n".join(shown), self.show_overlay.isChecked() and bool(shown))

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

