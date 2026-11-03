"""Ventana de control del generador Blackpill.

No abre el puerto serie: emite objetos Command para que la ventana principal
los entregue al proceso/hilo que ya posee la conexión USB CDC.
"""
from __future__ import annotations

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDoubleSpinBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QMessageBox, QPushButton,
    QTabWidget, QVBoxLayout, QWidget,
)

from communication import commands
from communication.errors import CommandError


class _ChannelPanel(QWidget):
    """Controles para una salida del generador (L o R)."""

    command_requested = Signal(object)

    def __init__(self, channel: str, parent=None):
        super().__init__(parent)
        self.channel = channel

        self.waveform = QComboBox()
        self.waveform.addItem("Senoidal", commands.Waveform.SINE)
        self.waveform.addItem("Cuadrada", commands.Waveform.SQUARE)
        self.waveform.addItem("Triangular", commands.Waveform.TRIANGLE)
        self.waveform.addItem("Chirp", commands.Waveform.CHIRP)

        self.frequency = QDoubleSpinBox()
        self.frequency.setRange(0.001, 1_000_000.0)
        self.frequency.setDecimals(3)
        self.frequency.setSingleStep(100.0)
        self.frequency.setValue(1000.0)
        self.frequency.setSuffix(" Hz")

        self.amplitude = QDoubleSpinBox()
        self.amplitude.setRange(0, 100)
        self.amplitude.setDecimals(0)
        self.amplitude.setSingleStep(5)
        self.amplitude.setValue(50)
        self.amplitude.setSuffix(" % FS")

        self.enabled = QCheckBox("Salida habilitada")
        self.enabled.setChecked(False)

        form = QFormLayout()
        form.addRow("Forma de onda:", self.waveform)
        form.addRow("Frecuencia:", self.frequency)
        form.addRow("Amplitud:", self.amplitude)

        group = QGroupBox(f"Generador {'CH1 / L' if channel == 'L' else 'CH2 / R'}")
        group_layout = QVBoxLayout(group)
        group_layout.addLayout(form)
        group_layout.addWidget(self.enabled)

        self.apply_button = QPushButton("Aplicar configuración")
        self.apply_button.clicked.connect(self.apply)

        self.off_button = QPushButton("Apagar salida")
        self.off_button.clicked.connect(self.turn_off)

        buttons = QHBoxLayout()
        buttons.addWidget(self.apply_button)
        buttons.addWidget(self.off_button)

        layout = QVBoxLayout(self)
        layout.addWidget(group)
        layout.addLayout(buttons)
        layout.addStretch()

        self.waveform.currentIndexChanged.connect(self._update_waveform_ui)
        self._update_waveform_ui()

    def _update_waveform_ui(self, *_):
        # Chirp requiere f0, f1 y duración; no enviar un chirp incompleto.
        is_chirp = self.waveform.currentData() == commands.Waveform.CHIRP
        self.frequency.setEnabled(not is_chirp)
        self.apply_button.setEnabled(not is_chirp)
        if is_chirp:
            self.apply_button.setToolTip(
                "La configuración de chirp requiere frecuencia inicial, final y duración."
            )
        else:
            self.apply_button.setToolTip("")

    def apply(self):
        """Prepara los comandos en orden; la conexión USB se gestiona afuera."""
        try:
            prepared = [
                commands.set_waveform(self.channel, self.waveform.currentData()),
                commands.set_frequency(self.channel, self.frequency.value()),
                commands.set_amplitude(self.channel, self.amplitude.value()),
                commands.output_on(self.channel)
                if self.enabled.isChecked()
                else commands.output_off(self.channel),
            ]
        except (CommandError, ValueError) as exc:
            QMessageBox.warning(self, "Configuración inválida", str(exc))
            return
        for command in prepared:
            self.command_requested.emit(command)

    def turn_off(self):
        self.enabled.setChecked(False)
        self.command_requested.emit(commands.output_off(self.channel))


class BlackpillGeneratorDialog(QDialog):
    """Diálogo que emite Command mediante command_requested.

    Ejemplo de integración:
        dialog = BlackpillGeneratorDialog(self)
        dialog.command_requested.connect(self._send_blackpill_command)
        dialog.show()

    El slot receptor debe encolar los comandos al lector USB activo, no abrir
    una segunda conexión serie.
    """

    command_requested = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Blackpill — Generador de señales")
        self.setMinimumWidth(440)
        self.setModal(False)

        description = QLabel(
            "Configurá las salidas del generador. Los cambios se envían "
            "al pulsar «Aplicar configuración»."
        )
        description.setWordWrap(True)

        tabs = QTabWidget()
        self.left_panel = _ChannelPanel("L", self)
        self.right_panel = _ChannelPanel("R", self)
        tabs.addTab(self.left_panel, "CH1 · L")
        tabs.addTab(self.right_panel, "CH2 · R")

        self.left_panel.command_requested.connect(self.command_requested.emit)
        self.right_panel.command_requested.connect(self.command_requested.emit)

        self.status_label = QLabel(
            "Sin confirmar conexión. Los comandos requieren una sesión USB activa."
        )
        self.status_label.setWordWrap(True)

        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.close)

        layout = QVBoxLayout(self)
        layout.addWidget(description)
        layout.addWidget(tabs)
        layout.addWidget(self.status_label)
        layout.addWidget(close_button)

    def set_connection_status(self, connected: bool, message: str = ""):
        """Actualiza el estado visible y habilita/deshabilita los controles."""
        self.left_panel.setEnabled(connected)
        self.right_panel.setEnabled(connected)
        self.status_label.setText(
            message or ("Blackpill conectada" if connected else "Blackpill desconectada")
        )
