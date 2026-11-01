
"""Panel de cursores Manual y Track para CH1 o CH2."""

from PySide6.QtCore import Signal, QSignalBlocker
from PySide6.QtWidgets import (
    QGroupBox,
    QVBoxLayout,
    QHBoxLayout,
    QLabel,
    QComboBox, QCheckBox,
)


class CursorControls(QGroupBox):
    settings_changed = Signal(str, str)
    channel_changed = Signal(int)
    labels_visible_changed = Signal(bool)

    def __init__(self, parent=None):
        super().__init__("CURSORES", parent)

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
        channel_row = QHBoxLayout()
        channel_row.addWidget(QLabel("Canal"))
        self.channel = QComboBox()
        self.channel.addItem("CH1", 1)
        self.channel.addItem("CH2", 2)
        channel_row.addWidget(self.channel, 1)
        layout.addLayout(channel_row)
        self.show_values = QCheckBox("Mostrar valores en gráfico")
        self.show_values.setChecked(True)
        self.show_values.setToolTip("Muestra u oculta las etiquetas junto a los cursores. La lectura del panel sigue disponible.")
        layout.addWidget(self.show_values)

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

        self.channel.currentIndexChanged.connect(
            lambda _index: self.channel_changed.emit(int(self.channel.currentData())))
        self.show_values.toggled.connect(self.labels_visible_changed.emit)

        # Estado inicial
        self._changed()

    # ================================================================
    # ACTUALIZACIÓN DE CONFIGURACIÓN
    # ================================================================

    def _changed(self, *_):
        mode = self.mode.currentText()
        orientation = self.orientation.currentText()

        # Track sigue la señal en tiempos elegidos; Manual admite ambos ejes.
        if mode == "Track":
            blocker = QSignalBlocker(self.orientation)
            self.orientation.setCurrentText("Tiempo")
            del blocker
            orientation = "Tiempo"
        self.orientation.setEnabled(mode == "Manual")

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

