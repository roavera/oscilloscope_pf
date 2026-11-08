"""Trigger por flanco con configuración no modal y nivel editable."""

from math import isfinite

from PySide6.QtCore import Signal, QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QPushButton, QSizePolicy, QVBoxLayout,
)

from gui.widgets.position_knob import LevelKnob
from gui.widgets.compact_level_input import CompactLevelInput


class TriggerControls(QGroupBox):
    source_changed = Signal(int)
    level_changed = Signal(float)
    slope_changed = Signal(str)
    mode_changed = Signal(str)
    single_clicked = Signal()
    auto_level_clicked = Signal()
    holdoff_changed = Signal(float)  # segundos

    def __init__(self, parent=None):
        super().__init__("Trigger", parent)
        self._level = 0.0
        self._visible_min = -0.08
        self._visible_max = 0.08
        self.create_interface()
        self.connect_signals()
        self._refresh_level_knob()

    def create_interface(self):
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(5)

        self.settings_button = QPushButton("CONFIGURACIÓN")
        self.settings_button.setMinimumHeight(30)
        self.settings_button.setToolTip("Configurar tipo, modo y flanco del disparo")
        self.settings_button.setStyleSheet("""
            QPushButton {background:#34465a;color:#f0f4f8;
                border:1px solid #60758b;border-radius:5px;
                font-weight:bold;padding:5px 6px;}
            QPushButton:hover:enabled {background:#465d76;}
        """)
        self.settings_button.setText("Config.")
        self.settings_button.setToolTip("Configuración de trigger: tipo, modo y flanco")

        self.single_button = QPushButton("SINGLE")
        self.single_button.setMinimumHeight(28)
        self.single_button.setToolTip(
            "Espera un disparo válido, captura una vez y congela la pantalla."
        )
        self.single_button.setStyleSheet("""
            QPushButton {background-color:#805ad5;color:white;border:none;
                border-radius:5px;font-weight:bold;padding:4px 6px;}
            QPushButton:hover:enabled {background-color:#6b46c1;}
            QPushButton:pressed:enabled {background-color:#553c9a;}
            QPushButton:disabled {background-color:#454052;color:#9992a8;}
        """)
        actions = QHBoxLayout()
        actions.setContentsMargins(0, 0, 0, 0)
        actions.setSpacing(4)
        actions.addWidget(self.settings_button, 1)
        actions.addWidget(self.single_button, 1)
        self.auto_level_button = QPushButton("AUTO LEVEL")
        self.auto_level_button.setMinimumHeight(28)
        self.auto_level_button.setToolTip(
            "Calcula un umbral de disparo desde el canal seleccionado. "
            "No modifica las muestras ni las escalas."
        )
        self.auto_level_button.setStyleSheet("""
            QPushButton {background:#205c68;color:#f2fcff;border:1px solid #4e8b9a;
                border-radius:5px;font-weight:bold;padding:4px 6px;}
            QPushButton:hover:enabled {background:#28788a;}
            QPushButton:disabled {background:#374650;color:#9caeb7;}
        """)
        actions.addWidget(self.auto_level_button, 1)
        layout.addLayout(actions)

        # Perilla a la izquierda; fuente y entrada numérica a la derecha.
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(5)
        knob_column = QVBoxLayout()
        knob_column.setContentsMargins(0, 0, 0, 0)
        knob_column.setSpacing(3)
        self.level_knob = LevelKnob(
            minimum=self._visible_min, maximum=self._visible_max,
            initial=self._level, accent_color="#e478c4", size=64,
        )
        knob_column.addWidget(self.level_knob, 0, Qt.AlignmentFlag.AlignHCenter)
        self.zero_button = QPushButton("0 V", self)
        self.zero_button.hide()
        self.zero_button.setToolTip("Restablecer nivel de disparo a 0 V")
        self.zero_button.setFixedWidth(44)
        self.zero_button.setMinimumHeight(24)
        
        body.addLayout(knob_column)

        fields = QVBoxLayout()
        fields.setContentsMargins(0, 0, 0, 0)
        fields.setSpacing(3)
        source_row = QHBoxLayout()
        source_row.setContentsMargins(0, 0, 0, 0)
        source_row.setSpacing(3)
        source_row.addWidget(QLabel("Fuente:"))
        self.source_combo = QComboBox()
        self.source_combo.addItem("CH1", 1)
        self.source_combo.addItem("CH2", 2)
        source_row.addWidget(self.source_combo, 1)
        fields.addLayout(source_row)

        level_title = QLabel("Nivel (V)")
        level_title.setWordWrap(True)
        fields.addWidget(level_title)
        self.level_input = CompactLevelInput()
        self.level_input.setDecimals(9)
        self.level_input.setRange(-1e6, 1e6)
        self.level_input.setSuffix(" V")
        self.level_input.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.level_input.setKeyboardTracking(False)
        self.level_input.setAccelerated(True)
        self.level_input.setMinimumHeight(28)
        self.level_input.setButtonSymbols(QDoubleSpinBox.ButtonSymbols.NoButtons)
        # El rango numérico amplio no debe ensanchar el panel lateral.
        self.level_input.setMinimumWidth(0)
        self.level_input.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        self.level_input.setStyleSheet("color:#e478c4;font-weight:normal;padding-left:3px;padding-right:3px;")
        self.level_input.setToolTip(
            "Ingresá el nivel de tensión del disparo en voltios.\n"
            "Confirmá con Enter o saliendo del campo."
        )
        fields.addWidget(self.level_input)
        body.addLayout(fields, 1)
        layout.addLayout(body)

        self.range_label = QLabel("")
        self.range_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.range_label.setWordWrap(True)
        self.range_label.setStyleSheet("color:#e9a4bd;font-size:10px;")
        self.range_label.setVisible(False)
        layout.addWidget(self.range_label)
        layout.addStretch(1)

        # Se reutiliza el diálogo: cerrar y reabrir conserva la selección.
        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle("Configuración de trigger")
        self.settings_dialog.setModal(False)
        self.settings_dialog.setMinimumWidth(330)
        dialog_layout = QVBoxLayout(self.settings_dialog)
        form = QFormLayout()

        self.type_combo = QComboBox()
        self.type_combo.addItem("Flanco", "edge")
        form.addRow("Tipo de disparo:", self.type_combo)

        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Auto", "Auto")
        self.mode_combo.addItem("Normal", "Normal")
        self.mode_combo.addItem("Single", "Single")
        self.mode_combo.model().item(2).setEnabled(False)
        self.mode_combo.setToolTip(
            "Auto: dispara si hay un cruce; sin cruces pasa a barrido libre.\n"
            "Normal: conserva la última captura hasta un disparo nuevo.\n"
            "Promediado y Envolvente siempre requieren disparos válidos."
        )
        layout.insertWidget(0, self.mode_combo)

        self.holdoff_spin = QDoubleSpinBox()
        self.holdoff_spin.setRange(0.0, 10000.0)  # ms
        self.holdoff_spin.setDecimals(3)
        self.holdoff_spin.setSingleStep(1.0)
        self.holdoff_spin.setSuffix(" ms")
        self.holdoff_spin.setKeyboardTracking(False)
        self.holdoff_spin.setToolTip(
            "Tiempo minimo entre disparos aceptados. 0 ms = desactivado. "
            "No depende del tiempo de actualizacion de pantalla."
        )
        form.addRow("Holdoff:", self.holdoff_spin)

        self.slope_combo = QComboBox()
        self.slope_combo.addItem("Ascendente", "Rising")
        self.slope_combo.addItem("Descendente", "Falling")
        form.addRow("Flanco:", self.slope_combo)
        dialog_layout.addLayout(form)

        note = QLabel(
            "Tipo disponible: disparo por flanco. "
            "Holdoff evita aceptar nuevos eventos durante el intervalo configurado."
        )
        note.setWordWrap(True)
        dialog_layout.addWidget(note)
        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.settings_dialog.hide)
        dialog_layout.addWidget(close_button)

    def connect_signals(self):
        self.settings_button.clicked.connect(self._show_settings)
        self.source_combo.currentIndexChanged.connect(self._emit_source_change)
        self.level_knob.value_changed.connect(self._emit_level_change)
        self.level_input.valueChanged.connect(self._emit_level_change)
        self.zero_button.clicked.connect(self._zero_level)
        self.slope_combo.currentIndexChanged.connect(self._emit_slope_change)
        self.holdoff_spin.valueChanged.connect(self._emit_holdoff_change)
        self.mode_combo.currentIndexChanged.connect(self._emit_mode_change)
        self.single_button.clicked.connect(self.single_clicked.emit)
        self.auto_level_button.clicked.connect(self.auto_level_clicked.emit)

    def _show_settings(self, _checked=False):
        self.settings_dialog.show()
        self.settings_dialog.raise_()
        self.settings_dialog.activateWindow()

    def _emit_source_change(self, _index):
        channel = self.source_combo.currentData()
        if channel in (1, 2):
            self.source_changed.emit(channel)

    def _zero_level(self, _checked=False):
        self._emit_level_change(0.0)

    def _emit_level_change(self, value):
        value = float(value)
        if not isfinite(value) or value == self._level:
            return
        # Actualizar los dos controles antes de notificar al controlador.
        self.set_level(value)
        self.level_changed.emit(value)

    def _emit_holdoff_change(self, milliseconds):
        self.holdoff_changed.emit(float(milliseconds) / 1000.0)

    def set_holdoff(self, seconds):
        blocker = QSignalBlocker(self.holdoff_spin)
        try:
            self.holdoff_spin.setValue(float(seconds) * 1000.0)
        finally:
            del blocker

    def _emit_slope_change(self, _index):
        value = self.slope_combo.currentData()
        if value is not None:
            self.slope_changed.emit(value)

    def _emit_mode_change(self, _index):
        value = self.mode_combo.currentData()
        if value is not None:
            self.mode_changed.emit(value)

    @staticmethod
    def _select(combo, value, fallback):
        blocker = QSignalBlocker(combo)
        try:
            index = combo.findData(value)
            if index < 0:
                combo.addItem(fallback, value)
                index = combo.count() - 1
            combo.setCurrentIndex(index)
        finally:
            del blocker

    def set_level(self, value):
        value = float(value)
        if not isfinite(value):
            raise ValueError("El nivel de trigger debe ser finito.")
        self._level = value
        self._refresh_level_knob()

    def set_level_range(self, minimum, maximum):
        minimum, maximum = float(minimum), float(maximum)
        if not isfinite(minimum) or not isfinite(maximum):
            raise ValueError("Los límites deben ser finitos.")
        if maximum <= minimum:
            raise ValueError("El límite superior debe ser mayor que el inferior.")
        self._visible_min, self._visible_max = minimum, maximum
        self._refresh_level_knob()

    def _refresh_level_knob(self):
        minimum = min(self._visible_min, self._level, 0.0)
        maximum = max(self._visible_max, self._level, 0.0)
        span = maximum - minimum
        knob_blocker = QSignalBlocker(self.level_knob)
        input_blocker = QSignalBlocker(self.level_input)
        try:
            self.level_knob.configure_range(
                minimum=minimum, maximum=maximum,
                step=span / 2000, value=self._level,
            )
            self.level_input.setRange(min(-1e6, minimum), max(1e6, maximum))
            self.level_input.setSingleStep(max(span / 2000, 1e-9))
            self.level_input.setValue(self._level)
            self.level_input.setToolTip(
                f"Nivel de disparo: {self._level:+.9g} V\n"
                "Ingresá el valor y confirmá con Enter o saliendo del campo."
            )
        finally:
            del input_blocker
            del knob_blocker
        outside = not (self._visible_min <= self._level <= self._visible_max)
        self.range_label.setText("Fuera de pantalla" if outside else "")
        self.range_label.setVisible(outside)
        self.range_label.setToolTip(
            f"Rango visible: {self._visible_min:+.6g} a {self._visible_max:+.6g} V"
        )

    def set_slope(self, value):
        self._select(self.slope_combo, value, value)

    def set_mode(self, value):
        # SINGLE se arma con su botón, pero el selector refleja su estado.
        self._select(self.mode_combo, value, value)

    def set_source(self, channel):
        if channel not in (1, 2):
            raise ValueError("La fuente de disparo debe ser CH1 o CH2.")
        blocker = QSignalBlocker(self.source_combo)
        try:
            self.source_combo.setCurrentIndex(self.source_combo.findData(channel))
        finally:
            del blocker



