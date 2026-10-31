"""Ventana principal con conexión Blackpill USB asíncrona.

Requiere las versiones actualizadas de acquisition_manager.py y
oscilloscope_widget.py entregadas junto con esta integración.
Adquisición > Fuente > Blackpill USB COM abre el selector de puerto.
STOP congela la pantalla; Desconectar detiene la fuente y cierra el COM.
"""

from PySide6.QtCore import QTimer, Slot
from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QComboBox, QDialog, QDialogButtonBox, QHBoxLayout, QLabel,
    QMainWindow, QMessageBox, QPushButton, QVBoxLayout, QWidget,
)

from acquisition.acquisition_manager import AcquisitionManager
from .oscilloscope_widget import OscilloscopeWidget
from .theme.theme_manager import ThemeManager

class PortDialog(QDialog):
    """Selector actualizable. También admite escribir COM5 o /dev/ttyACM0."""

    AUTO = "Detección automática"

    def __init__(self, current_port=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Conectar Blackpill")
        self.resize(480, 180)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("Puerto USB de la Blackpill:"))

        row = QHBoxLayout()
        self.ports = QComboBox(self)
        self.ports.setEditable(True)
        self.ports.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        row.addWidget(self.ports, 1)
        refresh = QPushButton("Actualizar", self)
        refresh.clicked.connect(self.refresh_ports)
        row.addWidget(refresh)
        layout.addLayout(row)

        self.info = QLabel(self)
        self.info.setWordWrap(True)
        layout.addWidget(self.info)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok |
            QDialogButtonBox.StandardButton.Cancel, parent=self
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText("Conectar")
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        self.ports.addItem(self.AUTO, None)
        if current_port:
            self.ports.setEditText(str(current_port))
        self.refresh_ports()

    def selected_port(self):
        text = self.ports.currentText().strip()
        if not text or text == self.AUTO:
            return None
        index = self.ports.currentIndex()
        if index >= 0 and text == self.ports.itemText(index):
            return self.ports.itemData(index)
        return text

    @Slot()
    def refresh_ports(self):
        selected = self.selected_port()
        self.ports.clear()
        self.ports.addItem(self.AUTO, None)
        try:
            # Importación local: audio/simulador no dependen de pyserial.
            from communication.transport import list_serial_ports
            ports = list_serial_ports()
        except Exception as exc:
            ports = []
            self.info.setText(str(exc))
        else:
            self.info.setText(
                "Elegí el COM de la placa. Cerrá otros programas que lo usen."
                if ports else
                "No se detectaron puertos. Conectá la placa y pulsá Actualizar."
            )
        for port in ports:
            self.ports.addItem(str(port), port.device)
        if selected:
            index = self.ports.findData(selected)
            if index >= 0:
                self.ports.setCurrentIndex(index)
            else:
                self.ports.setEditText(selected)


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Osciloscopio de Audio")
        self.resize(1200, 700)
        self._closing = False
        self._last_error = None
        self._error_box = None
        
        self.theme_manager = ThemeManager(self)
        self.theme_manager.apply_theme(self.theme_manager.current_theme)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        title = QLabel("Osciloscopio de Audio")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        layout.addWidget(title)
        self.oscilloscope = OscilloscopeWidget()
        layout.addWidget(self.oscilloscope)

        self._create_acquisition_menu()
        self.oscilloscope.acquisition_state_changed.connect(
            self._on_acquisition_state
        )
        self.oscilloscope.acquisition_error.connect(self._show_error)
        
        self._create_appearance_menu()
        
        self._create_display_menu()

        # También refleja RUN/STOP, que no cambia el estado del enlace.
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(250)
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start()
        self._update_status()
        
    
    def _create_appearance_menu(self):
        menu = self.menuBar().addMenu("Apariencia")

        self.theme_group = QActionGroup(self)
        self.theme_group.setExclusive(True)

        self.dark_action = QAction("Modo noche", self)
        self.dark_action.setCheckable(True)

        self.light_action = QAction("Modo día", self)
        self.light_action.setCheckable(True)

        self.theme_group.addAction(self.dark_action)
        self.theme_group.addAction(self.light_action)

        menu.addAction(self.dark_action)
        menu.addAction(self.light_action)

        self.dark_action.triggered.connect(
            lambda: self.theme_manager.apply_theme("dark")
        )
        self.light_action.triggered.connect(
            lambda: self.theme_manager.apply_theme("light")
        )

        self.theme_manager.theme_changed.connect(
            self._update_theme_actions
        )

        self._update_theme_actions(
            self.theme_manager.current_theme
        )


    def _update_theme_actions(self, theme):
        self.dark_action.setChecked(theme == "dark")
        self.light_action.setChecked(theme == "light")


    def _create_acquisition_menu(self):
        menu = self.menuBar().addMenu("Adquisición")
        sources_menu = menu.addMenu("Fuente")
        self.source_group = QActionGroup(self)
        self.source_group.setExclusive(True)
        self.source_actions = {}
        for source, label in (
            (AcquisitionManager.AUDIO, "Audio (sounddevice)"),
            (AcquisitionManager.SIMULATOR, "Blackpill simulada (tramas USB)"),
            (AcquisitionManager.BLACKPILL_USB, "Blackpill USB COM"),
        ):
            action = QAction(label, self)
            action.setCheckable(True)
            action.setData(source)
            self.source_group.addAction(action)
            sources_menu.addAction(action)
            self.source_actions[source] = action
        self.source_group.triggered.connect(self._on_source_selected)

        menu.addSeparator()
        self.port_action = QAction("Elegir puerto y conectar Blackpill…", self)
        self.port_action.triggered.connect(self._choose_usb_port)
        menu.addAction(self.port_action)

        self.connect_action = QAction("Conectar / reintentar fuente actual", self)
        self.connect_action.triggered.connect(self._connect_current)
        menu.addAction(self.connect_action)

        self.disconnect_action = QAction("Desconectar fuente actual", self)
        self.disconnect_action.triggered.connect(self._disconnect_current)
        menu.addAction(self.disconnect_action)

    def _perform(self, operation):
        try:
            operation()
        except Exception as exc:
            self._show_error(str(exc))
        finally:
            self._update_status()
            
    
    def _create_display_menu(self):
        """Selector independiente de apariencia del gráfico."""

        menu = self.menuBar().addMenu("Pantalla")

        self.display_theme_group = QActionGroup(self)
        self.display_theme_group.setExclusive(True)

        self.display_dark_action = QAction(
            "Fondo oscuro", self
        )
        self.display_light_action = QAction(
            "Fondo claro", self
        )

        for action in (
            self.display_dark_action,
            self.display_light_action,
        ):
            action.setCheckable(True)
            self.display_theme_group.addAction(action)
            menu.addAction(action)

        self.display_dark_action.triggered.connect(
            lambda: self._set_display_theme("dark")
        )
        self.display_light_action.triggered.connect(
            lambda: self._set_display_theme("light")
        )

        saved = self.theme_manager.settings.value(
            "appearance/display_theme",
            "dark",
            type=str,
        )

        if saved not in ("dark", "light"):
            saved = "dark"

        self._set_display_theme(saved)


    def _set_display_theme(self, theme):
        self.oscilloscope.plot.set_display_theme(theme)

        self.theme_manager.settings.setValue(
            "appearance/display_theme", theme
        )

        self.display_dark_action.setChecked(
            theme == "dark"
        )
        self.display_light_action.setChecked(
            theme == "light"
        )


    @Slot(QAction)
    def _on_source_selected(self, action):
        source = action.data()
        if source == AcquisitionManager.BLACKPILL_USB:
            self._choose_usb_port()
            return
        manager = self.oscilloscope.acquisition
        if source == manager.source and (manager.is_running or manager.is_connecting):
            self._update_status()
            return
        # Un fallo permanece visible; no volver a audio silenciosamente.
        self._perform(lambda: self.oscilloscope.change_acquisition_source(source))

    @Slot()
    def _choose_usb_port(self):
        manager = self.oscilloscope.acquisition
        dialog = PortDialog(manager.usb_port, self)
        if dialog.exec() != QDialog.DialogCode.Accepted:
            self._update_status()  # restaurar selección si se canceló
            return
        port = dialog.selected_port()
        self._perform(
            lambda: self.oscilloscope.connect_blackpill(port, simulated=False)
        )

    @Slot()
    def _connect_current(self):
        manager = self.oscilloscope.acquisition
        if manager.is_connecting or manager.is_running:
            return
        self._perform(self.oscilloscope.start_acquisition)

    @Slot()
    def _disconnect_current(self):
        self._perform(self.oscilloscope.disconnect_acquisition)

    @Slot(str)
    def _on_acquisition_state(self, state):
        if state in ("connecting", "connected", "stopped"):
            self._last_error = None
        self._update_status()

    @Slot(str)
    def _show_error(self, message):
        if self._closing:
            return
        self._update_status()
        if message == self._last_error:
            return
        self._last_error = message
        if self._error_box is not None:
            self._error_box.close()
        self._error_box = QMessageBox(self)
        self._error_box.setIcon(QMessageBox.Icon.Warning)
        self._error_box.setWindowTitle("Error de adquisición")
        self._error_box.setText(message)
        self._error_box.setInformativeText(
            "Revisá la conexión y el puerto. Después podés usar "
            "Adquisición > Conectar / reintentar fuente actual."
        )
        self._error_box.setStandardButtons(QMessageBox.StandardButton.Ok)
        # No bloquear el procesamiento de estados con un exec() anidado.
        self._error_box.open()

    @Slot()
    def _update_status(self):
        manager = self.oscilloscope.acquisition
        labels = {
            manager.AUDIO: "Audio (sounddevice)",
            manager.SIMULATOR: "Blackpill simulada (tramas USB)",
            manager.BLACKPILL_USB: "Blackpill USB COM",
        }
        states = {
            "connecting": "conectando",
            "connected": "conectada",
            "stopped": "detenida",
            "error": "error",
        }
        source = manager.source
        state = manager.state
        for key, action in self.source_actions.items():
            action.setChecked(key == source)

        self.connect_action.setEnabled(state in ("stopped", "error"))
        self.disconnect_action.setEnabled(state != "stopped")
        self.port_action.setEnabled(not self._closing)
        view = "RUN" if self.oscilloscope.running else "STOP"
        text = (
            f"Fuente: {labels.get(source, source)} | "
            f"Adquisición: {states.get(state, state)} | Vista: {view} | "
            f"Fs: {manager.sample_rate:,.2f} Hz"
        )
        if source == manager.SIMULATOR:
            text += " | Transporte simulado · PCM24 · CH1 · amplitud sin calibrar"
        if source == manager.BLACKPILL_USB:
            port = manager.usb_port or "automático"
            text += f" | Puerto configurado: {port} | CH1 · amplitud sin calibrar"
        self.statusBar().showMessage(text)

    def closeEvent(self, event):
        # Cerrar primero permite cancelar el cierre si el hilo no termina.
        try:
            self.oscilloscope.disconnect_acquisition()
            self.oscilloscope.shutdown()
        except Exception as exc:
            self._show_error(str(exc))
            event.ignore()
            return
        self._closing = True
        self.status_timer.stop()
        if self._error_box is not None:
            self._error_box.close()
        event.accept()
