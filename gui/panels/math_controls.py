"""Controles de una traza MATH con escala y posición independientes."""

from PySide6.QtCore import Signal, QSignalBlocker
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDoubleSpinBox, QFormLayout, QGroupBox,
    QLabel, QPushButton, QVBoxLayout,
)


class MathControls(QGroupBox):
    configuration_changed = Signal(str, int, int)
    visibility_changed = Signal(bool)
    scale_changed = Signal(float)
    scale_mode_changed = Signal(bool)
    position_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__("Matemática — MATH", parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        self.visible_checkbox = QCheckBox("Mostrar MATH")
        self.visible_checkbox.setChecked(False)
        layout.addWidget(self.visible_checkbox)
        form = QFormLayout()
        self.operation_combo = QComboBox()
        self.category_combo = QComboBox()
        self._operation_groups = {
            "Aritméticas": (("Suma: A + B", "add"), ("Resta: A − B", "subtract"), ("Multiplicación: A × B", "multiply"), ("División: A ÷ B", "divide")),
            "Cálculo": (("Integración: ∫ A dt", "integrate"), ("Derivación: dA/dt", "derivative")),
            "Funciones": (("Valor absoluto: |A|", "abs"), ("Raíz cuadrada: √A", "sqrt"), ("Logaritmo decimal: log10(A)", "log10"), ("Logaritmo natural: ln(A)", "ln"), ("Exponencial: exp(A)", "exp")),
            "Comparaciones": (("Mayor que: A > B", "greater"), ("Menor que: A < B", "less"), ("Mayor o igual: A ≥ B", "greater_equal"), ("Menor o igual: A ≤ B", "less_equal"), ("Igual: A = B", "equal")),
            "Lógicas": (("AND", "and"), ("OR", "or"), ("XOR", "xor")),
        }
        self.category_combo.addItems(self._operation_groups)
        self.source_a_combo = QComboBox()
        self.source_b_combo = QComboBox()
        for combo in (self.source_a_combo, self.source_b_combo):
            combo.addItem("CH1", 1)
            combo.addItem("CH2", 2)
        self.source_b_combo.setCurrentIndex(1)
        form.addRow("Grupo:", self.category_combo)
        form.addRow("Operación:", self.operation_combo)
        form.addRow("Fuente A:", self.source_a_combo)
        form.addRow("Fuente B:", self.source_b_combo)
        self._unit_suffix = "u.a."
        self.scale_mode_combo = QComboBox()
        self.scale_mode_combo.addItem("Auto", True)
        self.scale_mode_combo.addItem("Manual", False)
        form.addRow("Ajuste escala:", self.scale_mode_combo)
        self.scale_combo = QComboBox()
        # Escalas normalizadas 1-2-5, desde nano hasta giga.
        for exponent in range(-9, 10):
            for mantissa in (1, 2, 5):
                value = float(mantissa * 10.0 ** exponent)
                self.scale_combo.addItem(f"{value:g} u.a./div", value)
        self.scale_combo.setCurrentIndex(self.scale_combo.findData(.02))
        self.scale_combo.setEnabled(False)
        form.addRow("Escala MATH:", self.scale_combo)
        self.position_input = QDoubleSpinBox()
        self.position_input.setRange(-4, 4)
        self.position_input.setDecimals(2)
        self.position_input.setSingleStep(.01)
        self.position_input.setSuffix(" div")
        self.position_input.setKeyboardTracking(False)
        form.addRow("Posición MATH:", self.position_input)
        layout.addLayout(form)
        self.center_button = QPushButton("Centrar MATH")
        self.center_button.clicked.connect(lambda: self.position_input.setValue(0))
        layout.addWidget(self.center_button)
        self.formula_label = QLabel("MATH = CH1 + CH2")
        self.formula_label.setStyleSheet("color:#c993ff;font-weight:600;")
        layout.addWidget(self.formula_label)
        self.units_label = QLabel("Escala: unidades de entrada")
        self.units_label.setStyleSheet("color:#a8b5c8;font-weight:600;")
        layout.addWidget(self.units_label)
        note = QLabel("A/B son canales de entrada. Las funciones unarias utilizan solamente A.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status_label = QLabel("MATH oculta")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.visible_checkbox.toggled.connect(self.visibility_changed.emit)
        self.category_combo.currentIndexChanged.connect(self._on_category_changed)
        self.scale_mode_combo.currentIndexChanged.connect(self._on_scale_mode_changed)
        self.scale_combo.currentIndexChanged.connect(
            lambda _index: self.scale_changed.emit(float(self.scale_combo.currentData())))
        self.position_input.valueChanged.connect(self.position_changed.emit)
        for combo in (self.operation_combo, self.source_a_combo, self.source_b_combo):
            combo.currentIndexChanged.connect(self._emit_configuration)
        self._reload_operations()

    def _reload_operations(self, *_):
        current = self.operation_combo.currentData()
        self.operation_combo.blockSignals(True)
        self.operation_combo.clear()
        for label, value in self._operation_groups[self.category_combo.currentText()]:
            self.operation_combo.addItem(label, value)
        index = self.operation_combo.findData(current)
        self.operation_combo.setCurrentIndex(index if index >= 0 else 0)
        self.operation_combo.blockSignals(False)

    def _on_category_changed(self, *_):
        self._reload_operations()
        self._emit_configuration()

    @property
    def auto_scale(self):
        return bool(self.scale_mode_combo.currentData())

    def set_auto_scale(self, enabled):
        blocker = QSignalBlocker(self.scale_mode_combo)
        self.scale_mode_combo.setCurrentIndex(self.scale_mode_combo.findData(bool(enabled)))
        del blocker
        self.scale_combo.setEnabled(not enabled)

    def _on_scale_mode_changed(self, _index):
        automatic = self.auto_scale
        self.scale_combo.setEnabled(not automatic)
        self.scale_mode_changed.emit(automatic)

    @staticmethod
    def result_unit(operation, calibrated):
        unit = "V" if calibrated else "u.a."
        if operation in {"greater", "less", "greater_equal", "less_equal", "equal",
                         "and", "or", "xor", "divide", "log10", "ln", "exp"}:
            return "1"
        if operation == "multiply":
            return f"{unit}²"
        if operation == "derivative":
            return f"{unit}/s"
        if operation == "integrate":
            return f"{unit}·s"
        if operation == "sqrt":
            return f"√({unit})"
        return unit

    def set_units(self, label, calibrated, operation="add"):
        self._unit_suffix = self.result_unit(operation, calibrated)
        if operation in {"greater", "less", "greater_equal", "less_equal", "equal",
                         "and", "or", "xor"}:
            self.units_label.setText("Resultado lógico: 0 = bajo · 1 = alto")
        else:
            self.units_label.setText(f"Escala MATH: {label} · {self._unit_suffix}/div")
        for index in range(self.scale_combo.count()):
            value = float(self.scale_combo.itemData(index))
            self.scale_combo.setItemText(index, f"{value:g} {self._unit_suffix}/div")

    def set_digital_mode(self, digital):
        # Se conserva por compatibilidad con el controlador.
        self._digital_mode = bool(digital)

    def set_scale_value(self, value):
        value = float(value)
        for index in range(self.scale_combo.count()):
            item_value = float(self.scale_combo.itemData(index))
            if abs(item_value - value) <= max(1e-9, abs(value) * 1e-6):
                blocker = QSignalBlocker(self.scale_combo)
                self.scale_combo.setCurrentIndex(index)
                del blocker
                return
        unit = getattr(self, "_unit_suffix", "u.a.")
        blocker = QSignalBlocker(self.scale_combo)
        self.scale_combo.addItem(f"{value:g} {unit}/div", value)
        self.scale_combo.setCurrentIndex(self.scale_combo.count() - 1)
        del blocker

    def _emit_configuration(self, _index=None):
        self.configuration_changed.emit(
            self.operation_combo.currentData(), self.source_a_combo.currentData(),
            self.source_b_combo.currentData(),
        )

    def set_configuration(self, config):
        combos = ((self.operation_combo, config.operation),
                  (self.source_a_combo, config.source_a),
                  (self.source_b_combo, config.source_b))
        blockers = [QSignalBlocker(combo) for combo, _ in combos]
        try:
            for combo, value in combos:
                combo.setCurrentIndex(combo.findData(value))
        finally:
            del blockers
        self.formula_label.setText(f"MATH = {self._expression(config)}")
        category = next((name for name, values in self._operation_groups.items()
                         if any(value == config.operation for _, value in values)), None)
        if category:
            self.category_combo.blockSignals(True)
            self.category_combo.setCurrentText(category)
            self.category_combo.blockSignals(False)
            self._reload_operations()
            blocker = QSignalBlocker(self.operation_combo)
            self.operation_combo.setCurrentIndex(self.operation_combo.findData(config.operation))
            del blocker

    @staticmethod
    def _expression(config):
        labels = {"add": "+", "subtract": "−", "multiply": "×", "divide": "÷",
                  "greater": ">", "less": "<", "greater_equal": "≥",
                  "less_equal": "≤", "equal": "=", "and": "AND", "or": "OR", "xor": "XOR"}
        if config.operation in labels:
            return f"CH{config.source_a} {labels[config.operation]} CH{config.source_b}"
        names = {"integrate": "∫(CH%d) dt", "derivative": "d(CH%d)/dt", "abs": "abs(CH%d)",
                 "sqrt": "√CH%d", "log10": "log10(CH%d)", "ln": "ln(CH%d)", "exp": "exp(CH%d)"}
        return names[config.operation] % config.source_a
