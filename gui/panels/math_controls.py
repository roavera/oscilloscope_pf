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
        self.operation_combo.addItem("Suma: A + B", "add")
        self.operation_combo.addItem("Resta: A − B", "subtract")
        self.source_a_combo = QComboBox()
        self.source_b_combo = QComboBox()
        for combo in (self.source_a_combo, self.source_b_combo):
            combo.addItem("CH1", 1)
            combo.addItem("CH2", 2)
        self.source_b_combo.setCurrentIndex(1)
        form.addRow("Operación:", self.operation_combo)
        form.addRow("Fuente A:", self.source_a_combo)
        form.addRow("Fuente B:", self.source_b_combo)
        self.scale_combo = QComboBox()
        for value in (5, 2, 1, .5, .2, .1, .05, .02, .01, .005, .002, .001):
            self.scale_combo.addItem(f"{value:g} u.a./div", float(value))
        self.scale_combo.setCurrentIndex(self.scale_combo.findData(.02))
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
        note = QLabel("Salida en unidades de entrada (u.a.). Las muestras USB todavía no están calibradas en voltios.")
        note.setWordWrap(True)
        layout.addWidget(note)
        self.status_label = QLabel("MATH oculta")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)
        self.visible_checkbox.toggled.connect(self.visibility_changed.emit)
        self.scale_combo.currentIndexChanged.connect(
            lambda _index: self.scale_changed.emit(float(self.scale_combo.currentData())))
        self.position_input.valueChanged.connect(self.position_changed.emit)
        for combo in (self.operation_combo, self.source_a_combo, self.source_b_combo):
            combo.currentIndexChanged.connect(self._emit_configuration)

    def _emit_configuration(self, _index):
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
        sign = "+" if config.operation == "add" else "−"
        self.formula_label.setText(f"MATH = CH{config.source_a} {sign} CH{config.source_b}")
