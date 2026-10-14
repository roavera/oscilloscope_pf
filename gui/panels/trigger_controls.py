"""Controles de modo, pendiente y nivel de trigger."""

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


class TriggerControls(QGroupBox):

    # ================================================================
    # SEÑALES HACIA EL CONTROLADOR
    # ================================================================

    level_changed = Signal(float)
    slope_changed = Signal(str)
    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Trigger", parent)

        self._level = 0.0

        # Rango inicial: 8 divisiones a 20 mV/div.
        # El controlador lo actualiza según la escala del gráfico.
        self._visible_min = -0.08
        self._visible_max = 0.08

        self.create_interface()
        self.connect_signals()
        self._refresh_level_knob()

    # ================================================================
    # INTERFAZ
    # ================================================================

    def create_interface(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ------------------------------------------------------------
        # MODO
        # ------------------------------------------------------------

        self.mode_combo = self._combo(
            layout,
            "Modo:",
            (
                ("Auto", "Auto"),
                ("Normal", "Normal"),
                ("Single", "Single"),
            ),
        )

        # ------------------------------------------------------------
        # PENDIENTE
        # ------------------------------------------------------------

        self.slope_combo = self._combo(
            layout,
            "Flanco:",
            (
                ("Ascendente", "Rising"),
                ("Descendente", "Falling"),
            ),
        )

        # ------------------------------------------------------------
        # NIVEL DE TRIGGER
        # ------------------------------------------------------------

        layout.addSpacing(12)

        level_title = QLabel("Nivel")
        level_title.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )

        self.level_knob = DragKnob(
            minimum=self._visible_min,
            maximum=self._visible_max,
            step=(
                self._visible_max - self._visible_min
            ) / 2000,
            initial=self._level,
            reset_value=0.0,
            pixels_per_step=0.2,
            size=76,
        )

        self.level_knob.setToolTip(
            "Arrastrá hacia arriba o abajo para ajustar el trigger.\n"
            "El rango se adapta a la escala vertical.\n"
            "Doble clic: nivel de 0 V."
        )

        self.level_label = QLabel()
        self.level_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.level_label.setStyleSheet(
            "color: #c2188b; font-weight: bold;"
        )

        self.zero_button = QPushButton("Nivel 0 V")

        self.range_label = QLabel()
        self.range_label.setAlignment(
            Qt.AlignmentFlag.AlignCenter
        )
        self.range_label.setWordWrap(True)

        layout.addWidget(level_title)

        layout.addWidget(
            self.level_knob,
            0,
            Qt.AlignmentFlag.AlignHCenter,
        )

        layout.addWidget(self.level_label)
        layout.addWidget(self.zero_button)
        layout.addWidget(self.range_label)

    # ================================================================
    # CONEXIÓN DE SEÑALES
    # ================================================================

    def connect_signals(self):
        self.level_knob.value_changed.connect(
            self._emit_level_change
        )

        self.zero_button.clicked.connect(
            lambda _checked=False: self.level_changed.emit(0.0)
        )

        self.slope_combo.currentIndexChanged.connect(
            self._emit_slope_change
        )

        self.mode_combo.currentIndexChanged.connect(
            self._emit_mode_change
        )

    def _emit_level_change(self, value):
        # El controlador recibe el valor y lo devuelve mediante
        # set_level(), sincronizando perilla, lectura y gráfico.
        self.level_changed.emit(float(value))

    def _emit_slope_change(self, _index):
        value = self.slope_combo.currentData()

        if value is not None:
            self.slope_changed.emit(value)

    def _emit_mode_change(self, _index):
        value = self.mode_combo.currentData()

        if value is not None:
            self.mode_changed.emit(value)

    # ================================================================
    # SELECTORES
    # ================================================================

    @staticmethod
    def _combo(layout, label, options):
        layout.addWidget(QLabel(label))

        combo = QComboBox()

        for text, value in options:
            combo.addItem(text, value)

        layout.addWidget(combo)

        return combo

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

    # ================================================================
    # ACTUALIZACIÓN DESDE EL CONTROLADOR
    # ================================================================

    def set_level(self, value):
        """Muestra el nivel recibido del controlador o del gráfico."""

        value = float(value)

        if not isfinite(value):
            raise ValueError("El nivel de trigger debe ser finito.")

        self._level = value
        self._refresh_level_knob()

    def set_level_range(self, minimum, maximum):
        """Actualiza el rango visible sin cambiar el nivel elegido."""

        minimum = float(minimum)
        maximum = float(maximum)

        if not isfinite(minimum) or not isfinite(maximum):
            raise ValueError("Los límites deben ser finitos.")

        if maximum <= minimum:
            raise ValueError(
                "El límite superior debe ser mayor que el inferior."
            )

        self._visible_min = minimum
        self._visible_max = maximum

        self._refresh_level_knob()

    def _refresh_level_knob(self):
        # Conservar el nivel actual aunque quede fuera de pantalla.
        # Incluir cero permite utilizar el botón Nivel 0 V.
        minimum = min(
            self._visible_min,
            self._level,
            0.0,
        )

        maximum = max(
            self._visible_max,
            self._level,
            0.0,
        )

        span = maximum - minimum

        self.level_knob.configure_range(
            minimum=minimum,
            maximum=maximum,
            step=span / 2000,
            value=self._level,
        )

        # La lectura muestra el nivel real del controlador.
        # No reemplaza ese nivel por el valor discretizado del dial.
        self.level_label.setText(
            f"{self._level:+.6g} V"
        )

        self.level_label.setToolTip(
            f"Nivel de trigger: {self._level:+.9g} V"
        )

        outside = not (
            self._visible_min
            <= self._level
            <= self._visible_max
        )

        self.range_label.setText(
            "Fuera de pantalla" if outside else ""
        )

        self.range_label.setToolTip(
            "Rango visible: "
            f"{self._visible_min:+.6g} a "
            f"{self._visible_max:+.6g} V"
        )

    def set_slope(self, value):
        self._select(
            self.slope_combo,
            value,
            value,
        )

    def set_mode(self, value):
        self._select(
            self.mode_combo,
            value,
            value,
        )