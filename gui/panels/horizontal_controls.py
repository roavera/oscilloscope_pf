"""Controles de escala temporal del osciloscopio."""

from PySide6.QtCore import Signal, QSignalBlocker
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QLabel,
    QComboBox,
)


class HorizontalControls(QGroupBox):

    time_per_division_changed = Signal(float)

    def __init__(self, parent=None):
        super().__init__("Horizontal", parent)

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

    def create_interface(self):
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        layout.addWidget(QLabel("Tiempo/div:"))

        self.time_combo = QComboBox()

        for text, value in self.time_options.items():
            self.time_combo.addItem(text, value)

        layout.addWidget(self.time_combo)

    def connect_signals(self):
        self.time_combo.currentIndexChanged.connect(
            self._emit_time_change
        )

    def _emit_time_change(self, _index):
        value = self.time_combo.currentData()

        if value is not None:
            self.time_per_division_changed.emit(float(value))

    def set_time_per_division(self, value):
        """Muestra la escala elegida sin emitir una nueva orden."""

        value = float(value)
        blocker = QSignalBlocker(self.time_combo)

        try:
            index = self.time_combo.findData(value)

            if index < 0:
                self.time_combo.addItem(
                    f"{value:g} s/div",
                    value,
                )
                index = self.time_combo.count() - 1

            self.time_combo.setCurrentIndex(index)

        finally:
            del blocker