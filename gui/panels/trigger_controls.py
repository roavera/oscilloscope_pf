"""Controles de nivel, pendiente y modo de trigger."""

from PySide6.QtCore import Signal, QSignalBlocker
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QLabel,
    QComboBox,
)


class TriggerControls(QGroupBox):

    level_changed = Signal(float)
    slope_changed = Signal(str)
    mode_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Trigger", parent)

        self.create_interface()
        self.connect_signals()

    def create_interface(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ------------------------------------------------------------
        # NIVEL
        # ------------------------------------------------------------

        levels = (
            -2.0, -1.0, -0.5, -0.2, -0.1, -0.05, -0.02,
            0.0,
            0.02, 0.05, 0.1, 0.2, 0.5, 1.0, 2.0,
        )

        self.level_combo = self._combo(
            layout,
            "Nivel:",
            ((f"{value:g} V", value) for value in levels),
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
        # MODO
        # ------------------------------------------------------------

        self.mode_combo = self._combo(
            layout,
            "Modo:",
            ((mode, mode) for mode in ("Auto", "Normal", "Single")),
        )

    def connect_signals(self):
        self.level_combo.currentIndexChanged.connect(
            self._emit_level_change
        )

        self.slope_combo.currentIndexChanged.connect(
            self._emit_slope_change
        )

        self.mode_combo.currentIndexChanged.connect(
            self._emit_mode_change
        )

    def _emit_level_change(self, _index):
        value = self.level_combo.currentData()

        if value is not None:
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
        value = float(value)

        self._select(
            self.level_combo,
            value,
            f"{value:g} V",
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