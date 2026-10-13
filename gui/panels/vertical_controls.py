"""Panel vertical reutilizable para un canal del osciloscopio."""

from PySide6.QtCore import Signal, QSignalBlocker, Qt

from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
)

from gui.position_knob import PositionKnob


class VerticalControls(QGroupBox):

    volts_per_division_changed = Signal(float)
    position_changed = Signal(float)

    def __init__(self, channel="CH1", parent=None):
        super().__init__(f"Vertical — {channel}", parent)

        self.channel = channel

        self.voltage_options = {
            "5 V/div": 5.0,
            "2 V/div": 2.0,
            "1 V/div": 1.0,
            "500 mV/div": 0.5,
            "200 mV/div": 0.2,
            "100 mV/div": 0.1,
            "50 mV/div": 0.05,
            "20 mV/div": 0.02,
            "10 mV/div": 0.01,
            "5 mV/div": 0.005,
            "2 mV/div": 0.002,
            "1 mV/div": 0.001,
        }

        self.create_interface()
        self.connect_signals()

    def create_interface(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ------------------------------------------------------------
        # ESCALA VERTICAL
        # ------------------------------------------------------------

        layout.addWidget(QLabel("Volt/div:"))

        self.voltage_combo = QComboBox()

        for text, value in self.voltage_options.items():
            self.voltage_combo.addItem(text, value)

        layout.addWidget(self.voltage_combo)

        # ------------------------------------------------------------
        # POSICIÓN
        # ------------------------------------------------------------

        position_title = QLabel("Posición")
        position_title.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.position_knob = PositionKnob()

        self.position_label = QLabel("0.00 div")
        self.position_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.center_button = QPushButton("Centrar")

        layout.addSpacing(8)
        layout.addWidget(position_title)

        layout.addWidget(
            self.position_knob,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        layout.addWidget(self.position_label)
        layout.addWidget(self.center_button)

    def connect_signals(self):
        self.voltage_combo.currentIndexChanged.connect(
            self._emit_voltage_change
        )

        self.position_knob.valueChanged.connect(
            self._emit_position_change
        )

        self.center_button.clicked.connect(
            lambda _checked=False: self.position_changed.emit(0.0)
        )

    def _emit_voltage_change(self, _index):
        value = self.voltage_combo.currentData()

        if value is not None:
            self.volts_per_division_changed.emit(float(value))

    def _emit_position_change(self, units):
        divisions = units / PositionKnob.UNITS_PER_DIVISION
        self.position_changed.emit(divisions)

    # ================================================================
    # ACTUALIZACIÓN DESDE EL CONTROLADOR
    # ================================================================

    def set_volts_per_division(self, value):
        value = float(value)
        blocker = QSignalBlocker(self.voltage_combo)

        try:
            index = self.voltage_combo.findData(value)

            if index < 0:
                self.voltage_combo.addItem(
                    f"{value:g} V/div",
                    value,
                )
                index = self.voltage_combo.count() - 1

            self.voltage_combo.setCurrentIndex(index)

        finally:
            del blocker

    def set_position(self, divisions):
        units = round(
            float(divisions) * PositionKnob.UNITS_PER_DIVISION
        )

        units = max(
            self.position_knob.minimum(),
            min(self.position_knob.maximum(), units),
        )

        blocker = QSignalBlocker(self.position_knob)

        try:
            self.position_knob.setValue(units)
        finally:
            del blocker

        actual_position = (
            units / PositionKnob.UNITS_PER_DIVISION
        )

        self.position_label.setText(
            f"{actual_position:+.2f} div"
        )