"""Panel Trigger compacto para el diseño inspirado en LeCroy."""

from math import isfinite

from PySide6.QtCore import Signal, QSignalBlocker, Qt
from PySide6.QtWidgets import (
    QComboBox,
    QGridLayout,
    QGroupBox,
    QLabel,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from gui.widgets.drag_knob import DragKnob


class TriggerControls(QGroupBox):
    source_changed = Signal(int)
    level_changed = Signal(float)
    slope_changed = Signal(str)
    mode_changed = Signal(str)
    single_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__("Trigger", parent)
        self._level = 0.0
        self._visible_min = -0.08
        self._visible_max = 0.08
        self.create_interface()
        self.connect_signals()
        self._refresh_level_knob()

    def create_interface(self):
        layout = QVBoxLayout(self)
        self.source_combo = QComboBox()
        self.source_combo.addItem("Trigger: CH1", 1)
        self.source_combo.addItem("Trigger: CH2", 2)
        self.source_combo.currentIndexChanged.connect(
            lambda _index: self.source_changed.emit(self.source_combo.currentData()))
        layout.addWidget(self.source_combo)

        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(5)

        grid = QGridLayout()
        grid.setContentsMargins(0, 0, 0, 0)
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(4)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)

        # Columna izquierda: ajuste del nivel.
        level_container = QWidget(self)
        level_layout = QVBoxLayout(level_container)
        level_layout.setContentsMargins(0, 0, 0, 0)
        level_layout.setSpacing(3)

        level_title = QLabel("Nivel")
        level_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        level_layout.addWidget(level_title)

        self.level_knob = DragKnob(
            minimum=self._visible_min,
            maximum=self._visible_max,
            step=(self._visible_max - self._visible_min) / 2000,
            initial=self._level,
            reset_value=0.0,
            pixels_per_step=0.2,
            size=52,
        )
        self.level_knob.setToolTip(
            "Arrastrá para ajustar el nivel de disparo.\n"
            "Doble clic: restablecer a 0 V."
        )
        level_layout.addWidget(
            self.level_knob, 0, Qt.AlignmentFlag.AlignHCenter
        )

        self.level_label = QLabel("+0 V")
        self.level_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.level_label.setStyleSheet(
            "color: #e478c4; font-weight: 600;"
        )
        level_layout.addWidget(self.level_label)

        self.zero_button = QPushButton("0 V")
        self.zero_button.setToolTip("Restablecer nivel de disparo a 0 V")
        self.zero_button.setMaximumWidth(72)
        self.zero_button.setMinimumHeight(25)
        level_layout.addWidget(
            self.zero_button, 0, Qt.AlignmentFlag.AlignHCenter
        )
        grid.addWidget(level_container, 0, 0)

        # Columna derecha: modo y flanco.
        settings_container = QWidget(self)
        settings_layout = QVBoxLayout(settings_container)
        settings_layout.setContentsMargins(0, 0, 0, 0)
        settings_layout.setSpacing(3)

        settings_layout.addWidget(QLabel("Modo"))
        self.mode_combo = QComboBox()
        self.mode_combo.addItem("Auto", "Auto")
        self.mode_combo.addItem("Normal", "Normal")
        self.mode_combo.setSizePolicy(
            QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed
        )
        settings_layout.addWidget(self.mode_combo)

        settings_layout.addWidget(QLabel("Flanco"))
        self.slope_combo = QComboBox()
        self.slope_combo.addItem("Ascendente", "Rising")
        self.slope_combo.addItem("Descendente", "Falling")
        settings_layout.addWidget(self.slope_combo)
        settings_layout.addStretch(1)
        grid.addWidget(settings_container, 0, 1)

        layout.addLayout(grid)

        self.range_label = QLabel("")
        self.range_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.range_label.setWordWrap(True)
        self.range_label.setStyleSheet("color: #e9a4bd; font-size: 10px;")
        self.range_label.setVisible(False)
        layout.addWidget(self.range_label)

        self.single_button = QPushButton("SINGLE")
        self.single_button.setMinimumHeight(30)
        self.single_button.setToolTip(
            "Espera un disparo válido, captura una vez y congela la pantalla."
        )
        self.single_button.setStyleSheet("""
            QPushButton {
                background-color: #805ad5;
                color: white;
                border: none;
                border-radius: 5px;
                font-weight: bold;
                padding: 4px 8px;
            }
            QPushButton:hover:enabled { background-color: #6b46c1; }
            QPushButton:pressed:enabled { background-color: #553c9a; }
            QPushButton:disabled {
                background-color: #454052;
                color: #9992a8;
            }
        """)
        layout.addWidget(self.single_button)

    def connect_signals(self):
        self.level_knob.value_changed.connect(self._emit_level_change)
        self.zero_button.clicked.connect(self._zero_level)
        self.slope_combo.currentIndexChanged.connect(self._emit_slope_change)
        self.mode_combo.currentIndexChanged.connect(self._emit_mode_change)
        self.single_button.clicked.connect(self.single_clicked.emit)

    def _zero_level(self, _checked=False):
        self.level_changed.emit(0.0)

    def _emit_level_change(self, value):
        self.level_changed.emit(float(value))

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
        minimum = min(self._visible_min, self._level, 0.0)
        maximum = max(self._visible_max, self._level, 0.0)
        span = maximum - minimum
        self.level_knob.configure_range(
            minimum=minimum,
            maximum=maximum,
            step=span / 2000,
            value=self._level,
        )
        self.level_label.setText(f"{self._level:+.6g} V")
        self.level_label.setToolTip(
            f"Nivel de trigger: {self._level:+.9g} V"
        )
        outside = not (self._visible_min <= self._level <= self._visible_max)
        self.range_label.setText("Fuera de pantalla" if outside else "")
        self.range_label.setVisible(outside)
        self.range_label.setToolTip(
            "Rango visible: "
            f"{self._visible_min:+.6g} a {self._visible_max:+.6g} V"
        )

    def set_slope(self, value):
        self._select(self.slope_combo, value, value)

    def set_mode(self, value):
        # SINGLE es una acción, no un modo permanente del selector.
        if value == "Single":
            return
        self._select(self.mode_combo, value, value)


    def set_source(self, channel):
        blocker = QSignalBlocker(self.source_combo)
        self.source_combo.setCurrentIndex(self.source_combo.findData(channel))
        del blocker
