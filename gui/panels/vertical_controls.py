"""Panel vertical compacto, reutilizable para CH1 y CH2."""

from math import isfinite

from PySide6.QtCore import Signal, QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QWidget,
    QLabel,
    QComboBox,
    QPushButton,
    QSizePolicy,
)

from gui.widgets.drag_knob import DragKnob


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
        self.set_volts_per_division(0.1)
        self.set_position(0.0)

    def create_interface(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(5)

        columns = QHBoxLayout()
        columns.setContentsMargins(0, 0, 0, 0)
        columns.setSpacing(8)

        # Izquierda: escala vertical, perilla y selector sincronizados.
        voltage_panel = QWidget(self)
        voltage_layout = QVBoxLayout(voltage_panel)
        voltage_layout.setContentsMargins(0, 0, 0, 0)
        voltage_layout.setSpacing(3)

        voltage_title = QLabel("Volt/div")
        voltage_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        voltage_layout.addWidget(voltage_title)

        self.voltage_knob = DragKnob(
            minimum=0,
            maximum=len(self.voltage_options) - 1,
            step=1,
            initial=5,
            reset_value=5,
            pixels_per_step=12.0,
            size=52,
        )
        self.voltage_knob.setToolTip(
            "Arrastrá para cambiar Volt/div. Doble clic: 100 mV/div."
        )
        voltage_layout.addWidget(
            self.voltage_knob, 0, Qt.AlignmentFlag.AlignHCenter
        )

        self.voltage_combo = QComboBox()
        self.voltage_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        for text, value in self.voltage_options.items():
            self.voltage_combo.addItem(text, value)
        voltage_layout.addWidget(self.voltage_combo)
        columns.addWidget(voltage_panel, 1)

        # Derecha: posición vertical y centrado.
        position_panel = QWidget(self)
        position_layout = QVBoxLayout(position_panel)
        position_layout.setContentsMargins(0, 0, 0, 0)
        position_layout.setSpacing(3)

        position_title = QLabel("Posición")
        position_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        position_layout.addWidget(position_title)

        self.position_knob = DragKnob(
            minimum=-4.0,
            maximum=4.0,
            step=0.01,
            initial=0.0,
            reset_value=0.0,
            pixels_per_step=1.0,
            size=52,
        )
        self.position_knob.setToolTip(
            "Arrastrá para desplazar la señal. Doble clic: centrar."
        )
        position_layout.addWidget(
            self.position_knob, 0, Qt.AlignmentFlag.AlignHCenter
        )

        position_bottom = QHBoxLayout()
        position_bottom.setContentsMargins(0, 0, 0, 0)
        position_bottom.setSpacing(4)
        self.position_label = QLabel("+0.00 div")
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.center_button = QPushButton("0")
        self.center_button.setFixedWidth(28)
        self.center_button.setToolTip("Centrar posición vertical")
        position_bottom.addWidget(self.position_label, 1)
        position_bottom.addWidget(self.center_button)
        position_layout.addLayout(position_bottom)
        columns.addWidget(position_panel, 1)

        layout.addLayout(columns)

    def connect_signals(self):
        self.voltage_combo.currentIndexChanged.connect(
            self._emit_voltage_change
        )
        self.voltage_knob.value_changed.connect(
            self._on_voltage_knob_changed
        )
        self.position_knob.value_changed.connect(
            self._emit_position_change
        )
        self.center_button.clicked.connect(self._center_position)

    def _emit_voltage_change(self, _index):
        value = self.voltage_combo.currentData()
        if value is None:
            return
        self.set_volts_per_division(value)
        self.volts_per_division_changed.emit(float(value))

    def _on_voltage_knob_changed(self, value):
        index = int(round(value))
        if not 0 <= index < self.voltage_combo.count():
            return
        voltage = self.voltage_combo.itemData(index)
        if voltage is None:
            return
        self.set_volts_per_division(voltage)
        self.volts_per_division_changed.emit(float(voltage))

    def _emit_position_change(self, divisions):
        self.set_position(divisions)
        self.position_changed.emit(self.position_knob.numeric_value())

    def _center_position(self, _checked=False):
        self.set_position(0.0)
        self.position_changed.emit(0.0)

    def set_volts_per_division(self, value):
        """Sincroniza selector y perilla sin emitir señales de usuario."""
        value = float(value)
        if not isfinite(value) or value <= 0:
            raise ValueError("Volt/div debe ser positivo y finito.")

        blocker = QSignalBlocker(self.voltage_combo)
        try:
            index = self.voltage_combo.findData(value)
            if index < 0:
                self.voltage_combo.addItem(f"{value:g} V/div", value)
                index = self.voltage_combo.count() - 1
            self.voltage_combo.setCurrentIndex(index)
            self.voltage_knob.configure_range(
                minimum=0,
                maximum=self.voltage_combo.count() - 1,
                step=1,
                value=index,
            )
        finally:
            del blocker

    def set_position(self, divisions):
        """Actualiza la posición sin emitir position_changed."""
        divisions = float(divisions)
        if not isfinite(divisions):
            raise ValueError("La posición vertical debe ser finita.")
        self.position_knob.set_value(divisions)
        actual_position = self.position_knob.numeric_value()
        self.position_label.setText(f"{actual_position:+.2f} div")
