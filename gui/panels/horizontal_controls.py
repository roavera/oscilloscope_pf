"""Controles de escala y posición horizontal del osciloscopio."""

from math import isfinite

from PySide6.QtCore import Signal, QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QLabel,
    QComboBox,
    QPushButton,
)

from gui.widgets.drag_knob import DragKnob


class HorizontalControls(QGroupBox):

    time_per_division_changed = Signal(float)

    # Posición visual expresada en divisiones.
    position_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__("Horizontal", parent)

        self._time_per_division = 0.001
        self._position_divisions = 0.0

        # La perilla recorre estos valores discretos.
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

    # ================================================================
    # INTERFAZ
    # ================================================================

    def create_interface(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ------------------------------------------------------------
        # TIEMPO / DIV
        # ------------------------------------------------------------

        time_title = QLabel("Tiempo/div")
        time_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(time_title)

        self.time_combo = QComboBox()

        for text, value in self.time_options.items():
            self.time_combo.addItem(text, value)

        self.time_knob = DragKnob(
            minimum=0,
            maximum=len(self.time_options) - 1,
            step=1,
            initial=3,
            reset_value=3,
            pixels_per_step=12.0,
            size=76,
        )

        self.time_knob.setToolTip(
            "Arrastrá hacia arriba para reducir Tiempo/div.\n"
            "Doble clic para volver a 1 ms/div."
        )

        layout.addWidget(
            self.time_knob,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )
        layout.addWidget(self.time_combo)

        # ------------------------------------------------------------
        # POSICIÓN HORIZONTAL
        # ------------------------------------------------------------

        position_title = QLabel("Posición")
        position_title.setAlignment(Qt.AlignmentFlag.AlignCenter)

        self.position_knob = DragKnob(
            minimum=-6.0,
            maximum=6.0,
            step=0.01,
            initial=0.0,
            reset_value=0.0,
            pixels_per_step=1.0,
            size=76,
        )

        self.position_knob.setToolTip(
            "Ajuste de posición horizontal en divisiones.\n"
            "Doble clic para centrar."
        )

        self.position_label = QLabel()
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

    # ================================================================
    # CONEXIONES
    # ================================================================

    def connect_signals(self):
        self.time_combo.currentIndexChanged.connect(
            self._on_time_combo_changed
        )

        self.time_knob.value_changed.connect(
            self._on_time_knob_changed
        )

        self.position_knob.value_changed.connect(
            self._on_position_changed
        )

        self.center_button.clicked.connect(
            self._center_position
        )

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

        time_per_division = float(
            self.time_combo.itemData(index)
        )

        self.set_time_per_division(time_per_division)
        self.time_per_division_changed.emit(time_per_division)

    def _on_position_changed(self, divisions):
        self.set_position(divisions)
        self.position_changed.emit(self._position_divisions)

    def _center_position(self, _checked=False):
        self.set_position(0.0)
        self.position_changed.emit(0.0)

    # ================================================================
    # ACTUALIZACIÓN DESDE EL CONTROLADOR
    # ================================================================

    def set_time_per_division(self, value):
        """Actualiza los controles sin emitir una nueva orden."""

        value = float(value)

        if not isfinite(value) or value <= 0:
            raise ValueError("Tiempo/div debe ser positivo y finito.")

        blocker = QSignalBlocker(self.time_combo)

        try:
            index = self.time_combo.findData(value)

            # Conserva la posibilidad de recibir una escala adicional
            # desde el controlador.
            if index < 0:
                self.time_combo.addItem(
                    f"{self._format_time(value)}/div",
                    value,
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
        self._position_divisions = (
            self.position_knob.numeric_value()
        )

        self._update_position_label()

    # ================================================================
    # INDICADORES
    # ================================================================

    def _update_position_label(self):
        displacement = (
            self._position_divisions * self._time_per_division
        )

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