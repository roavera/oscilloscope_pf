"""Controles de disparo con ajustes específicos por tipo y nivel editable."""

from math import isfinite

from PySide6.QtCore import Signal, QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDoubleSpinBox, QFormLayout, QGroupBox,
    QHBoxLayout, QLabel, QLayout, QPushButton, QSizePolicy, QVBoxLayout,
)

from gui.widgets.position_knob import LevelKnob
from gui.widgets.compact_level_input import CompactLevelInput


class TriggerControls(QGroupBox):
    source_changed = Signal(int)
    level_changed = Signal(float)
    slope_changed = Signal(str)
    mode_changed = Signal(str)
    single_clicked = Signal()
    type_changed = Signal(str)
    pulse_width_changed = Signal(dict)
    timeout_changed = Signal(dict)
    runt_changed = Signal(dict)
    logic_changed = Signal(dict)
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
        self._update_pulse_width_ui()

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
        self.settings_dialog.setWindowTitle("Trigger")
        self.settings_dialog.setModal(False)
        dialog_layout = QVBoxLayout(self.settings_dialog)
        dialog_layout.setContentsMargins(16, 16, 16, 16)
        dialog_layout.setSpacing(12)
        dialog_layout.setSizeConstraint(QLayout.SizeConstraint.SetFixedSize)
        type_group = QGroupBox("Tipo de disparo")
        type_group.setMinimumWidth(368)
        type_layout = QVBoxLayout(type_group)
        type_layout.setSpacing(12)
        self.type_form = QFormLayout()

        self.type_combo = QComboBox()
        self.type_combo.addItem("Flanco", "edge")
        self.type_combo.addItem("Ancho de pulso", "pulse_width")
        self.type_combo.addItem("Timeout", "timeout")
        self.type_combo.addItem("Runt", "runt")
        self.type_combo.addItem("Logic CH1/CH2", "logic")
        self.type_combo.setAccessibleName("Tipo de disparo")
        type_layout.addWidget(self.type_combo)
        type_layout.addLayout(self.type_form)
        dialog_layout.addWidget(type_group)

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

        self.slope_combo = QComboBox()
        self.slope_combo.addItem("Ascendente", "Rising")
        self.slope_combo.addItem("Descendente", "Falling")
        self.type_form.addRow("Flanco:", self.slope_combo)

        # Configuracion especifica de Pulse Width; no ocupa sitio en la
        # pantalla principal y no interfiere con el control Holdoff.
        self.pulse_group = QGroupBox("Ancho de pulso", self.settings_dialog)
        self.pulse_form = pulse_form = QFormLayout(self.pulse_group)
        self.pulse_polarity = QComboBox()
        self.pulse_polarity.addItem("Alto (HIGH)", "high")
        self.pulse_polarity.addItem("Bajo (LOW)", "low")
        pulse_form.addRow("Polaridad:", self.pulse_polarity)

        self.pulse_comparison = QComboBox()
        self.pulse_comparison.addItem("Mayor que (>)", "greater")
        self.pulse_comparison.addItem("Menor que (<)", "less")
        self.pulse_comparison.addItem("Dentro del rango", "within")
        self.pulse_comparison.addItem("Fuera del rango", "outside")
        pulse_form.addRow("Condición:", self.pulse_comparison)

        self.pulse_lower = QDoubleSpinBox()
        self.pulse_lower.setRange(0.0, 1_000_000.0)
        self.pulse_lower.setDecimals(2)
        self.pulse_lower.setSingleStep(10.0)
        self.pulse_lower.setValue(400.0)
        self.pulse_lower.setSuffix(" µs")
        self.pulse_lower.setKeyboardTracking(False)
        self.pulse_lower.setToolTip("Umbral o limite inferior, expresado en microsegundos")
        pulse_form.addRow("Duración:", self.pulse_lower)

        self.pulse_upper = QDoubleSpinBox()
        self.pulse_upper.setRange(0.0, 1_000_000.0)
        self.pulse_upper.setDecimals(2)
        self.pulse_upper.setSingleStep(10.0)
        self.pulse_upper.setValue(600.0)
        self.pulse_upper.setSuffix(" µs")
        self.pulse_upper.setKeyboardTracking(False)
        self.pulse_upper.setToolTip("Limite superior para Dentro/Fuera del rango")
        pulse_form.addRow("Máximo:", self.pulse_upper)

        self.pulse_group.setToolTip("El disparo se confirma al finalizar el pulso.")
        dialog_layout.addWidget(self.pulse_group)
        self.pulse_group.hide()

        self.timeout_group = QGroupBox("Timeout - ausencia de flancos", self.settings_dialog)
        timeout_form = QFormLayout(self.timeout_group)
        self.timeout_state = QComboBox()
        for label, value in (("Alto o bajo", "either"),
                             ("Alto", "high"), ("Bajo", "low")):
            self.timeout_state.addItem(label, value)
        timeout_form.addRow("Estado:", self.timeout_state)
        self.timeout_duration = QDoubleSpinBox()
        self.timeout_duration.setRange(0.0, 10_000_000.0)
        self.timeout_duration.setDecimals(2)
        self.timeout_duration.setSingleStep(100.0)
        self.timeout_duration.setValue(1000.0)
        self.timeout_duration.setSuffix(" µs")
        self.timeout_duration.setKeyboardTracking(False)
        timeout_form.addRow("Sin transición:", self.timeout_duration)
        self.timeout_hysteresis = QDoubleSpinBox()
        self.timeout_hysteresis.setRange(0.0, 100.0)
        self.timeout_hysteresis.setDecimals(4)
        self.timeout_hysteresis.setValue(0.0)
        self.timeout_hysteresis.setSuffix(" V")
        self.timeout_hysteresis.setKeyboardTracking(False)
        timeout_form.addRow("Histéresis:", self.timeout_hysteresis)
        self.timeout_duration.setToolTip("Tiempo sin transiciones respecto del nivel principal.")
        dialog_layout.addWidget(self.timeout_group)
        self.timeout_group.hide()

        self.runt_group = QGroupBox("Runt - pulso incompleto", self.settings_dialog)
        runt_form = QFormLayout(self.runt_group)
        self.runt_polarity = QComboBox()
        self.runt_polarity.addItem("Pulso alto incompleto", "high")
        self.runt_polarity.addItem("Pulso bajo incompleto", "low")
        runt_form.addRow("Polaridad:", self.runt_polarity)
        self.runt_lower = QDoubleSpinBox()
        self.runt_lower.setRange(-100000.0, 100000.0)
        self.runt_lower.setDecimals(4)
        self.runt_lower.setValue(-0.2)
        self.runt_lower.setSuffix(" V")
        self.runt_lower.setKeyboardTracking(False)
        runt_form.addRow("Umbral inferior:", self.runt_lower)
        self.runt_upper = QDoubleSpinBox()
        self.runt_upper.setRange(-100000.0, 100000.0)
        self.runt_upper.setDecimals(4)
        self.runt_upper.setValue(0.2)
        self.runt_upper.setSuffix(" V")
        self.runt_upper.setKeyboardTracking(False)
        runt_form.addRow("Umbral superior:", self.runt_upper)
        self.runt_min_width = QDoubleSpinBox()
        self.runt_min_width.setRange(0.0, 10_000_000.0)
        self.runt_min_width.setDecimals(2)
        self.runt_min_width.setValue(0.0)
        self.runt_min_width.setSuffix(" µs")
        self.runt_min_width.setKeyboardTracking(False)
        runt_form.addRow("Duración mínima:", self.runt_min_width)
        self.runt_group.setToolTip("Cruza el primer umbral y regresa sin alcanzar el segundo.")
        dialog_layout.addWidget(self.runt_group)
        self.runt_group.hide()

        self.logic_group = QGroupBox("Logic - dos canales", self.settings_dialog)
        logic_form = QFormLayout(self.logic_group)
        self.logic_operator = QComboBox()
        for label, value in (("AND (Y)", "and"), ("OR (O)", "or"),
                             ("XOR (O excluyente)", "xor")):
            self.logic_operator.addItem(label, value)
        logic_form.addRow("Operación:", self.logic_operator)
        self.logic_ch1_state = QComboBox()
        self.logic_ch1_state.addItem("HIGH", "high")
        self.logic_ch1_state.addItem("LOW", "low")
        self.logic_ch2_state = QComboBox()
        self.logic_ch2_state.addItem("HIGH", "high")
        self.logic_ch2_state.addItem("LOW", "low")
        self.logic_ch1_level = QDoubleSpinBox()
        self.logic_ch1_level.setRange(-100000.0, 100000.0)
        self.logic_ch1_level.setDecimals(4)
        self.logic_ch1_level.setSuffix(" V")
        self.logic_ch1_level.setKeyboardTracking(False)
        self.logic_ch2_level = QDoubleSpinBox()
        self.logic_ch2_level.setRange(-100000.0, 100000.0)
        self.logic_ch2_level.setDecimals(4)
        self.logic_ch2_level.setSuffix(" V")
        self.logic_ch2_level.setKeyboardTracking(False)
        logic_form.addRow("Estado CH1:", self.logic_ch1_state)
        logic_form.addRow("Nivel CH1:", self.logic_ch1_level)
        logic_form.addRow("Estado CH2:", self.logic_ch2_state)
        logic_form.addRow("Nivel CH2:", self.logic_ch2_level)
        self.logic_edge = QComboBox()
        self.logic_edge.addItem("Cuando se cumple", "rising")
        self.logic_edge.addItem("Cuando deja de cumplirse", "falling")
        logic_form.addRow("Disparar:", self.logic_edge)
        self.logic_group.setToolTip("Requiere dos canales activos y sincronizados.")
        dialog_layout.addWidget(self.logic_group)
        self.logic_group.hide()

        timing_group = QGroupBox("Entre disparos")
        timing_form = QFormLayout(timing_group)
        timing_form.addRow("Holdoff:", self.holdoff_spin)
        dialog_layout.addWidget(timing_group)
        for form in (self.type_form, pulse_form, timeout_form, runt_form, logic_form, timing_form):
            form.setFieldGrowthPolicy(QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow)
            form.setVerticalSpacing(10)

        footer = QHBoxLayout()
        footer.addStretch()
        close_button = QPushButton("Cerrar")
        close_button.setDefault(True)
        close_button.clicked.connect(self.settings_dialog.hide)
        footer.addWidget(close_button)
        dialog_layout.addLayout(footer)

    def connect_signals(self):
        self.settings_button.clicked.connect(self._show_settings)
        self.source_combo.currentIndexChanged.connect(self._emit_source_change)
        self.level_knob.value_changed.connect(self._emit_level_change)
        self.level_input.valueChanged.connect(self._emit_level_change)
        self.zero_button.clicked.connect(self._zero_level)
        self.slope_combo.currentIndexChanged.connect(self._emit_slope_change)
        self.type_combo.currentIndexChanged.connect(self._emit_trigger_type_change)
        self.pulse_polarity.currentIndexChanged.connect(self._emit_pulse_width_change)
        self.pulse_comparison.currentIndexChanged.connect(self._emit_pulse_width_change)
        self.pulse_lower.valueChanged.connect(self._emit_pulse_width_change)
        self.pulse_upper.valueChanged.connect(self._emit_pulse_width_change)
        for ctrl in (self.timeout_state, self.timeout_duration, self.timeout_hysteresis):
            (ctrl.currentIndexChanged if isinstance(ctrl, QComboBox)
             else ctrl.valueChanged).connect(self._emit_timeout_change)
        for ctrl in (self.runt_polarity, self.runt_lower,
                     self.runt_upper, self.runt_min_width):
            (ctrl.currentIndexChanged if isinstance(ctrl, QComboBox)
             else ctrl.valueChanged).connect(self._emit_runt_change)
        for ctrl in (self.logic_operator, self.logic_ch1_state,
                     self.logic_ch2_state, self.logic_ch1_level,
                     self.logic_ch2_level, self.logic_edge):
            (ctrl.currentIndexChanged if isinstance(ctrl, QComboBox)
             else ctrl.valueChanged).connect(self._emit_logic_change)
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

    def timeout_settings(self):
        return dict(state=self.timeout_state.currentData(),
                    timeout_us=self.timeout_duration.value(),
                    hysteresis_volts=self.timeout_hysteresis.value())

    def runt_settings(self):
        return dict(polarity=self.runt_polarity.currentData(),
                    lower_volts=self.runt_lower.value(),
                    upper_volts=self.runt_upper.value(),
                    min_width_us=self.runt_min_width.value())

    def logic_settings(self):
        return dict(operator=self.logic_operator.currentData(),
                    ch1_state=self.logic_ch1_state.currentData(),
                    ch2_state=self.logic_ch2_state.currentData(),
                    ch1_level=self.logic_ch1_level.value(),
                    ch2_level=self.logic_ch2_level.value(),
                    edge=self.logic_edge.currentData())

    def _emit_timeout_change(self, *_):
        self.timeout_changed.emit(self.timeout_settings())

    def _emit_runt_change(self, *_):
        if self.runt_lower.value() >= self.runt_upper.value():
            # Garantizar umbrales separados antes de actualizar el detector.
            blocker = QSignalBlocker(self.runt_upper)
            try:
                self.runt_upper.setValue(min(self.runt_upper.maximum(),
                                              self.runt_lower.value() + 0.01))
            finally:
                del blocker
            if self.runt_lower.value() >= self.runt_upper.value():
                return
        self.runt_changed.emit(self.runt_settings())

    def _emit_logic_change(self, *_):
        self.logic_changed.emit(self.logic_settings())

    def reset_advanced_settings(self):
        defaults = (
            (self.timeout_state,0), (self.timeout_duration,1000.0),
            (self.timeout_hysteresis,0.0), (self.runt_polarity,0),
            (self.runt_lower,-0.2), (self.runt_upper,0.2),
            (self.runt_min_width,0.0), (self.logic_operator,0),
            (self.logic_ch1_state,0), (self.logic_ch2_state,0),
            (self.logic_ch1_level,0.0), (self.logic_ch2_level,0.0),
            (self.logic_edge,0),
        )
        for ctrl, value in defaults:
            blocker = QSignalBlocker(ctrl)
            try:
                if isinstance(ctrl, QComboBox):
                    ctrl.setCurrentIndex(value)
                else:
                    ctrl.setValue(value)
            finally:
                del blocker
        self._update_pulse_width_ui()

    def set_available_channels(self, channels):
        two = int(channels) == 2
        index = self.type_combo.findData("logic")
        self.type_combo.model().item(index).setEnabled(two)
        self.source_combo.model().item(1).setEnabled(two)
        if not two and self.source_combo.currentData() == 2:
            blocker = QSignalBlocker(self.source_combo)
            try:
                self.source_combo.setCurrentIndex(0)
            finally:
                del blocker
        if not two and self.type_combo.currentData() == "logic":
            self.set_trigger_type("edge")

    def _update_pulse_width_ui(self):
        kind = self.type_combo.currentData()
        pulse = kind == "pulse_width"
        self.pulse_group.setVisible(pulse)
        self.timeout_group.setVisible(kind == "timeout")
        self.runt_group.setVisible(kind == "runt")
        self.logic_group.setVisible(kind == "logic")
        self.type_form.setRowVisible(self.slope_combo, kind == "edge")
        self.slope_combo.setEnabled(kind == "edge")
        self.level_knob.setEnabled(kind in ("edge", "pulse_width", "timeout"))
        self.level_input.setEnabled(kind in ("edge", "pulse_width", "timeout"))
        self.auto_level_button.setEnabled(kind in ("edge", "pulse_width", "timeout"))
        interval = self.pulse_comparison.currentData() in ("within", "outside")
        self.pulse_form.setRowVisible(self.pulse_upper, interval)
        self.pulse_upper.setEnabled(interval)
        self.pulse_form.labelForField(self.pulse_lower).setText(
            "Mínimo:" if interval else "Duración:"
        )

    def _emit_trigger_type_change(self, _index):
        self._update_pulse_width_ui()
        selected = self.type_combo.currentData()
        if selected is not None:
            self.type_changed.emit(selected)

    def _emit_pulse_width_change(self, *_):
        # Impedir un rango invertido antes de notificar al detector.
        minimum = self.pulse_lower.value()
        if self.pulse_upper.value() < minimum:
            blocker = QSignalBlocker(self.pulse_upper)
            try:
                self.pulse_upper.setValue(minimum)
            finally:
                del blocker
        self._update_pulse_width_ui()
        self.pulse_width_changed.emit(self.pulse_width_settings())

    def pulse_width_settings(self):
        return {
            "polarity": self.pulse_polarity.currentData(),
            "comparison": self.pulse_comparison.currentData(),
            "lower_us": self.pulse_lower.value(),
            "upper_us": self.pulse_upper.value(),
        }

    def set_trigger_type(self, kind):
        self._select(self.type_combo, kind, kind)
        self._update_pulse_width_ui()

    def reset_pulse_width_settings(self):
        controls = (
            (self.pulse_polarity, 0),
            (self.pulse_comparison, 0),
            (self.pulse_lower, 400.0),
            (self.pulse_upper, 600.0),
        )
        for control, value in controls:
            blocker = QSignalBlocker(control)
            try:
                if isinstance(control, QComboBox):
                    control.setCurrentIndex(value)
                else:
                    control.setValue(value)
            finally:
                del blocker
        self._update_pulse_width_ui()

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




