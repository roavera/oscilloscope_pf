"""Configuración inicial de fuente, número de canales y simulación.

No inicia la captura: la selección se devuelve a MainWindow al aceptar.
"""
from __future__ import annotations

from PySide6.QtCore import Slot
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QDialog, QDialogButtonBox, QDoubleSpinBox,
    QFormLayout, QGroupBox, QHBoxLayout, QLabel, QPushButton,
    QStackedWidget, QTabWidget, QVBoxLayout, QWidget, QFrame,
)

from acquisition.acquisition_manager import AcquisitionManager


class SimulatorChannelForm(QGroupBox):
    """Parámetros de una entrada virtual, en voltios simulados."""

    def __init__(self, number: int, parent=None):
        super().__init__(f"Señal CH{number}", parent)
        self.number = number
        self.setObjectName("sourceChannelGroup")
        self.enabled = QCheckBox(f"Habilitar CH{number}")
        self.enabled.setChecked(True)

        self.waveform = QComboBox()
        self.waveform.addItem("Senoidal", "sine")
        self.waveform.addItem("Cuadrada", "square")
        self.waveform.addItem("Triangular", "triangle")

        self.frequency = self._spin(1.0, 20_000.0, 1000.0 if number == 1 else 500.0,
                                    10.0, " Hz", 2)
        self.amplitude = self._spin(0.0, 3.0, 1.5, 0.05, " V", 3)
        self.offset = self._spin(-3.0, 3.0, 0.0, 0.05, " V", 3)
        self.noise = self._spin(0.0, 3.0, 0.0, 0.005, " V RMS", 3)
        if number == 2:
            self.waveform.setCurrentIndex(1)

        form = QFormLayout(self)
        form.addRow(self.enabled)
        form.addRow("Forma de onda:", self.waveform)
        form.addRow("Frecuencia:", self.frequency)
        form.addRow("Amplitud pico:", self.amplitude)
        form.addRow("Offset:", self.offset)
        form.addRow("Ruido (σ):", self.noise)
        self.enabled.toggled.connect(self._update_enabled)

    @staticmethod
    def _spin(minimum, maximum, initial, step, suffix, decimals):
        control = QDoubleSpinBox()
        control.setRange(minimum, maximum)
        control.setDecimals(decimals)
        control.setSingleStep(step)
        control.setSuffix(suffix)
        control.setValue(initial)
        return control

    def _update_enabled(self, active: bool):
        for widget in (self.waveform, self.frequency, self.amplitude,
                       self.offset, self.noise):
            widget.setEnabled(active)

    def settings(self):
        return {
            "enabled": self.enabled.isChecked(),
            "waveform": self.waveform.currentData(),
            "frequency": self.frequency.value(),
            "amplitude": self.amplitude.value(),
            "offset": self.offset.value(),
            "noise": self.noise.value(),
        }


class PhysicalGeneratorChannelForm(QGroupBox):
    """Configuración opcional de las SALIDAS del generador físico (no ADC)."""

    def __init__(self, number: int, parent=None):
        super().__init__(f"Salida CH{number}", parent)
        self.setObjectName("sourceChannelGroup")
        self.enabled = QCheckBox(f"Encender salida CH{number}")
        self.enabled.setChecked(False)  # Nunca activar hardware por defecto.
        self.waveform = QComboBox()
        self.waveform.addItem("Senoidal", 0)
        self.waveform.addItem("Cuadrada", 1)
        self.waveform.addItem("Triangular", 2)
        if number == 2:
            self.waveform.setCurrentIndex(1)
        self.frequency = SimulatorChannelForm._spin(
            0.001, 1_000_000.0, 1000.0 if number == 1 else 500.0,
            100.0, " Hz", 3,
        )
        self.amplitude = SimulatorChannelForm._spin(
            0.0, 100.0, 50.0, 5.0, " % FS", 0,
        )
        form = QFormLayout(self)
        form.addRow(self.enabled)
        form.addRow("Forma de onda:", self.waveform)
        form.addRow("Frecuencia:", self.frequency)
        form.addRow("Amplitud:", self.amplitude)

    def settings(self):
        return {
            "enabled": self.enabled.isChecked(),
            "waveform": self.waveform.currentData(),
            "frequency": self.frequency.value(),
            "amplitude_percent": self.amplitude.value(),
        }


class AcquisitionSourceDialog(QDialog):
    """Selector modal mostrado después de pulsar INICIAR OSCILOSCOPIO."""

    AUTOMATIC_PORT = "Detectar automáticamente"

    def __init__(self, current_source=AcquisitionManager.AUDIO,
                 current_channels=1, current_usb_port=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Fuente de adquisición")
        self.setObjectName("AcquisitionSourceDialog")
        self.setMinimumWidth(620)
        self.resize(650, 610)
        self.setModal(True)
        self._apply_dialog_theme(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 16, 18, 14)
        layout.setSpacing(12)

        heading = QLabel("Configuración de la adquisición")
        heading.setObjectName("sourceDialogTitle")
        layout.addWidget(heading)

        divider = QFrame(self)
        divider.setObjectName("sourceDialogDivider")
        divider.setFixedHeight(2)
        layout.addWidget(divider)

        form = QFormLayout()
        self.source = QComboBox()
        self.source.addItem("Audio de la computadora", AcquisitionManager.AUDIO)
        self.source.addItem("Generador de señales (simulador)", AcquisitionManager.SIMULATOR)
        self.source.addItem("Blackpill física (USB CDC)", AcquisitionManager.BLACKPILL_USB)
        form.addRow(self._field_label("Fuente de adquisición:"), self.source)

        self.channel_count = QComboBox()
        self.channel_count.addItem("1 canal · CH1 centrado", 1)
        self.channel_count.addItem("2 canales · CH1 arriba / CH2 abajo", 2)
        form.addRow(self._field_label("Canales de entrada:"), self.channel_count)
        layout.addLayout(form)

        self.pages = QStackedWidget()
        self.pages.addWidget(self._audio_page())
        self.pages.addWidget(self._simulator_page())
        self.pages.addWidget(self._blackpill_page(current_usb_port))
        layout.addWidget(self.pages)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel,
            parent=self,
        )
        start_button = buttons.button(QDialogButtonBox.StandardButton.Ok)
        start_button.setText("Iniciar osciloscopio")
        start_button.setObjectName("sourceStartButton")
        cancel_button = buttons.button(QDialogButtonBox.StandardButton.Cancel)
        cancel_button.setText("Cancelar")
        cancel_button.setObjectName("sourceCancelButton")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

        idx = self.source.findData(current_source)
        self.source.setCurrentIndex(max(0, idx))
        idx = self.channel_count.findData(current_channels)
        self.channel_count.setCurrentIndex(max(0, idx))
        self.source.currentIndexChanged.connect(self._update_page)
        self.channel_count.currentIndexChanged.connect(self._update_page)
        self._update_page()

    @staticmethod
    def _field_label(text):
        label = QLabel(text)
        label.setObjectName("sourceDialogFieldLabel")
        return label

    def _apply_dialog_theme(self, parent):
        """Contraste local en ambos temas; no modifica la apariencia del display."""
        theme_manager = getattr(parent, "theme_manager", None)
        dark = getattr(theme_manager, "current_theme", "dark") != "light"
        if dark:
            bg, title, text, soft, line = (
                "#151A22", "#F4F8FE", "#EDF2F8", "#C4D5E8", "#4398F7"
            )
            panel, panel_border = "#192332", "#4A6482"
            button_bg, button_hover, button_border = "#1A5AAB", "#2474D0", "#509CFF"
        else:
            bg, title, text, soft, line = (
                "#F1F4F8", "#192C46", "#202A38", "#445D78", "#3272C9"
            )
            panel, panel_border = "#F9FBFF", "#B4C8E1"
            button_bg, button_hover, button_border = "#2468BB", "#1F559B", "#205BA5"

        # El estilo del tab se define además en dark.qss y light.qss:
        # así se corrigen todas las pestañas de la aplicación.
        self.setStyleSheet(f"""
            QDialog#AcquisitionSourceDialog {{ background-color: {bg}; }}
            QLabel#sourceDialogTitle {{ color: {title}; font-size: 18px;
                                         font-weight: 700; background: transparent; }}
            QFrame#sourceDialogDivider {{ background-color: {line}; border: none; }}
            QLabel#sourceDialogFieldLabel {{ color: {text}; font-weight: 600;
                                              background: transparent; }}
            QLabel#sourceDialogHint {{ color: {soft}; background: transparent; }}
            QGroupBox#sourceChannelGroup {{ background-color: {panel};
                color: {text}; border: 1px solid {panel_border};
                border-radius: 7px; margin-top: 13px; padding: 10px 8px 8px 8px;
                font-weight: 600; }}
            QGroupBox#sourceChannelGroup::title {{ color: {title};
                subcontrol-origin: margin; left: 10px; padding: 0px 5px; }}
            QPushButton#sourceStartButton {{ color: #FFFFFF; background-color: {button_bg};
                border: 1px solid {button_border}; border-radius: 7px;
                padding: 8px 13px; font-weight: 600; min-height: 26px; }}
            QPushButton#sourceStartButton:hover {{ background-color: {button_hover}; }}
        """)

    @staticmethod
    def _note(text):
        label = QLabel(text)
        label.setWordWrap(True)
        return label

    def _audio_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(QLabel("Entrada de audio del equipo"))
        layout.addWidget(self._note(
            "Se utiliza automáticamente el dispositivo predeterminado de entrada "
            "del sistema mediante sounddevice. Para dos canales, el dispositivo "
            "debe permitir captura estéreo."
        ))
        layout.addStretch()
        return page

    def _simulator_page(self):
        page = QWidget()
        layout = QVBoxLayout(page)
        hint = self._note("Configurá una señal independiente para cada canal.")
        hint.setObjectName("sourceDialogHint")
        layout.addWidget(hint)
        self.sim_tabs = QTabWidget()
        self.sim_ch1 = SimulatorChannelForm(1)
        self.sim_ch2 = SimulatorChannelForm(2)
        self.sim_tabs.addTab(self.sim_ch1, "CH1")
        self.sim_tabs.addTab(self.sim_ch2, "CH2")
        layout.addWidget(self.sim_tabs)
        return page

    def _blackpill_page(self, selected_port):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(self._note(
            "Conectá la Blackpill por USB CDC. Se usa el mismo puerto para "
            "adquirir uno o dos canales; la placa debe transmitir el modo elegido."
        ))
        row = QHBoxLayout()
        self.port = QComboBox()
        self.port.setEditable(True)
        self.port.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        row.addWidget(self.port, 1)
        refresh = QPushButton("Actualizar puertos")
        refresh.clicked.connect(self.refresh_ports)
        row.addWidget(refresh)
        layout.addWidget(QLabel("Puerto serie:"))
        layout.addLayout(row)
        self.port_note = self._note("")
        layout.addWidget(self.port_note)

        # Esto controla SALIDAS del DAC, no define qué señal recibe el ADC.
        self.configure_hardware_generator = QCheckBox(
            "Configurar también el generador de salida de la Blackpill al conectar"
        )
        self.configure_hardware_generator.setChecked(False)
        layout.addWidget(self.configure_hardware_generator)
        layout.addWidget(self._note(
            "Opcional: envía comandos de forma, frecuencia y amplitud a las "
            "salidas físicas. No sustituye la conexión eléctrica de la señal "
            "a las entradas del ADC; ambas son independientes."
        ))
        self.physical_tabs = QTabWidget()
        self.physical_ch1 = PhysicalGeneratorChannelForm(1)
        self.physical_ch2 = PhysicalGeneratorChannelForm(2)
        self.physical_tabs.addTab(self.physical_ch1, "Salida L")
        self.physical_tabs.addTab(self.physical_ch2, "Salida R")
        self.physical_tabs.setEnabled(False)
        self.configure_hardware_generator.toggled.connect(self.physical_tabs.setEnabled)
        layout.addWidget(self.physical_tabs)
        layout.addStretch()
        self.refresh_ports()
        if selected_port:
            index = self.port.findData(selected_port)
            if index >= 0:
                self.port.setCurrentIndex(index)
            else:
                self.port.setEditText(str(selected_port))
        return page

    @Slot()
    def refresh_ports(self):
        old_port = self._selected_port() if self.port.count() else None
        self.port.clear()
        self.port.addItem(self.AUTOMATIC_PORT, None)
        try:
            from communication.transport import list_serial_ports
            ports = list_serial_ports()
        except Exception as exc:
            self.port_note.setText(f"No se pudieron consultar puertos: {exc}")
            ports = []
        else:
            self.port_note.setText(
                "Elegí el COM de la placa, o dejá la detección automática."
                if ports else
                "No se detectaron puertos. Podés escribir COM5 manualmente "
                "o conectar la placa y actualizar."
            )
        for port in ports:
            self.port.addItem(str(port), port.device)
        if old_port:
            index = self.port.findData(old_port)
            if index >= 0:
                self.port.setCurrentIndex(index)
            else:
                self.port.setEditText(old_port)

    def _selected_port(self):
        current = self.port.currentText().strip()
        if not current or current == self.AUTOMATIC_PORT:
            return None
        index = self.port.currentIndex()
        if index >= 0 and current == self.port.itemText(index):
            return self.port.itemData(index)
        return current

    @Slot()
    def _update_page(self, *_):
        selected = self.source.currentData()
        page = {AcquisitionManager.AUDIO: 0,
                AcquisitionManager.SIMULATOR: 1,
                AcquisitionManager.BLACKPILL_USB: 2}[selected]
        self.pages.setCurrentIndex(page)
        stereo = self.channel_count.currentData() == 2
        self.sim_tabs.setTabEnabled(1, stereo)
        self.physical_tabs.setTabEnabled(1, stereo)
        if not stereo:
            self.sim_tabs.setCurrentIndex(0)
            self.physical_tabs.setCurrentIndex(0)

    def configuration(self):
        return {
            "source": self.source.currentData(),
            "channels": self.channel_count.currentData(),
            "usb_port": self._selected_port(),
            "simulator": [self.sim_ch1.settings(), self.sim_ch2.settings()],
            "physical_generator": (
                [self.physical_ch1.settings(), self.physical_ch2.settings()]
                if self.configure_hardware_generator.isChecked() else None
            ),
        }
