
"""Panel de cursores Manual y Track para CH1."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox,
)


class CursorControls(QGroupBox):
    settings_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__("CURSORES · CH1", parent)

        # ============================================================
        # INTERFAZ
        # ============================================================

        layout = QVBoxLayout(self)

        row = QHBoxLayout()
        row.setSpacing(8)

        # Selector de modo
        self.mode = QComboBox()
        self.mode.addItems([
            "Off",
            "Manual",
            "Track",
        ])

        # Selector de eje
        self.orientation = QComboBox()
        self.orientation.addItems([
            "Tiempo",
            "Tensión",
        ])

        # Distribución horizontal
        row.addWidget(QLabel("Modo"))
        row.addWidget(self.mode)

        row.addWidget(QLabel("Eje"))
        row.addWidget(self.orientation)

        layout.addLayout(row)

        # ============================================================
        # LECTURAS DE CURSORES
        # ============================================================

        self.readout = QLabel("Cursores desactivados")
        self.readout.setWordWrap(True)
        self.readout.setMinimumHeight(65)

        self.readout.setStyleSheet(
            "font-family: monospace;"
        )

        layout.addWidget(self.readout)

        # ============================================================
        # CONEXIONES
        # ============================================================

        self.mode.currentTextChanged.connect(
            self._changed
        )

        self.orientation.currentTextChanged.connect(
            self._changed
        )

        # Estado inicial
        self._changed()

    # ================================================================
    # ACTUALIZACIÓN DE CONFIGURACIÓN
    # ================================================================

    def _changed(self, *_):
        mode = self.mode.currentText()
        orientation = self.orientation.currentText()

        # El eje puede modificarse en Manual y Track.
        # Solo se deshabilita cuando los cursores están apagados.
        self.orientation.setEnabled(
            mode != "Off"
        )

        # Informar los cambios al osciloscopio.
        self.settings_changed.emit(
            mode,
            orientation
        )

    # ================================================================
    # LECTURAS
    # ================================================================

    def set_readout(self, text):
        """Actualiza las mediciones mostradas."""
        self.readout.setText(text)
