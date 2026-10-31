"""Panel horizontal compacto para el diseño de osciloscopio estilo LeCroy."""

from math import isfinite

from PySide6.QtCore import QSignalBlocker, Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.drag_knob import DragKnob


class HorizontalControls(QGroupBox):
    time_per_division_changed = Signal(float)
    position_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__("Horizontal", parent)
        self._time_per_division = 0.001
        self._position_divisions = 0.0
        self.time_options = {
            "10 ms/div": 0.010,
            "5 ms/div": 0.005,
            "2 ms/div": 0.002,
            "1 ms/div": 0.001,
            "500 µs/div": 0.0005,
            "200 µs/div": 0.0002,
            "100 µs/div": 0.0001,
            "50 µs/div": 0.00005,
            "20 µs/div": 0.00002,
            "10 µs/div": 0.00001,
        }
        self.create_interface()
        self.connect_signals()
        self.set_time_per_division(self._time_per_division)
        self.set_position(0.0)

    def create_interface(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(5)

        knobs_row = QHBoxLayout()
        knobs_row.setSpacing(8)

        time_column = QVBoxLayout()
        time_column.setSpacing(3)
        time_title = QLabel("Time/div")
        time_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.time_knob = DragKnob(
            minimum=0,
            maximum=len(self.time_options) - 1,
            step=1,
            initial=3,
            reset_value=3,
            pixels_per_step=12.0,
            size=52,
        )
        self.time_knob.setToolTip(
            "Arrastrá hacia arriba para reducir Tiempo/div.\n"
            "Doble clic para volver a 1 ms/div."
        )
        self.time_combo = QComboBox()
        for label, value in self.time_options.items():
            self.time_combo.addItem(label, value)
        self.time_combo.setMinimumWidth(0)
        self.time_combo.setSizePolicy(
            QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed
        )
        time_column.addWidget(time_title)
        time_column.addWidget(self.time_knob, 0, Qt.AlignmentFlag.AlignHCenter)
        time_column.addWidget(self.time_combo)

        position_column = QVBoxLayout()
        position_column.setSpacing(3)
        position_title = QLabel("Posición")
        position_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.position_knob = DragKnob(
            minimum=-6.0,
            maximum=6.0,
            step=0.01,
            initial=0.0,
            reset_value=0.0,
            pixels_per_step=1.0,
            size=52,
        )
        self.position_knob.setToolTip(
            "Ajuste horizontal en divisiones.\nDoble clic para centrar."
        )
        self.position_label = QLabel()
        self.position_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.position_label.setToolTip("Desplazamiento horizontal en divisiones y tiempo")
        self.center_button = QPushButton("0")
        self.center_button.setToolTip("Centrar posición horizontal")
        self.center_button.setFixedWidth(30)
        self.center_button.setFixedHeight(24)
        position_column.addWidget(position_title)
        position_column.addWidget(self.position_knob, 0, Qt.AlignmentFlag.AlignHCenter)
        position_column.addWidget(self.position_label)
        position_column.addWidget(self.center_button, 0, Qt.AlignmentFlag.AlignHCenter)

        knobs_row.addLayout(time_column, 1)
        knobs_row.addLayout(position_column, 1)
        layout.addLayout(knobs_row)
        layout.addStretch(1)

    def connect_signals(self):
        self.time_combo.currentIndexChanged.connect(self._on_time_combo_changed)
        self.time_knob.value_changed.connect(self._on_time_knob_changed)
        self.position_knob.value_changed.connect(self._on_position_changed)
        self.center_button.clicked.connect(self._center_position)

    def _on_time_combo_changed(self, index):
        if index < 0:
            return
        value = self.time_combo.itemData(index)
        if value is None:
            return
        self.set_time_per_division(value)
        self.time_per_division_changed.emit(float(value))

    def _on_time_knob_changed(self, value):
        index = int(round(value))
        if not 0 <= index < self.time_combo.count():
            return
        time_per_division = float(self.time_combo.itemData(index))
        self.set_time_per_division(time_per_division)
        self.time_per_division_changed.emit(time_per_division)

    def _on_position_changed(self, divisions):
        self.set_position(divisions)
        self.position_changed.emit(self._position_divisions)

    def _center_position(self, _checked=False):
        self.set_position(0.0)
        self.position_changed.emit(0.0)

    def set_time_per_division(self, value):
        """Sincroniza los controles sin emitir una orden al controlador."""
        value = float(value)
        if not isfinite(value) or value <= 0:
            raise ValueError("Tiempo/div debe ser positivo y finito.")

        blocker = QSignalBlocker(self.time_combo)
        try:
            index = self.time_combo.findData(value)
            if index < 0:
                self.time_combo.addItem(
                    f"{self._format_time(value)}/div", value
                )
                index = self.time_combo.count() - 1
            self.time_combo.setCurrentIndex(index)
            self.time_knob.configure_range(
                minimum=0,
                maximum=self.time_combo.count() - 1,
                step=1,
                value=index,
            )
        finally:
            del blocker
        self._time_per_division = value
        self._update_position_label()

    def set_position(self, divisions):
        """Actualiza la posición sin emitir position_changed."""
        divisions = float(divisions)
        if not isfinite(divisions):
            raise ValueError("La posición debe ser finita.")
        self.position_knob.set_value(divisions)
        self._position_divisions = self.position_knob.numeric_value()
        self._update_position_label()

    def _update_position_label(self):
        displacement = self._position_divisions * self._time_per_division
        self.position_label.setText(
            f"{self._position_divisions:+.2f} div\n"
            f"{self._format_time(displacement, signed=True)}"
        )

    @staticmethod
    def _format_time(seconds, signed=False):
        magnitude = abs(seconds)
        if magnitude == 0:
            value, unit = 0.0, "s"
        elif magnitude < 0.001:
            value, unit = seconds * 1_000_000, "µs"
        elif magnitude < 1.0:
            value, unit = seconds * 1_000, "ms"
        else:
            value, unit = seconds, "s"
        text = f"{value:+.4g}" if signed else f"{value:.4g}"
        return f"{text} {unit}"
