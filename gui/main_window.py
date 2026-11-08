"""Ventana principal """

from PySide6.QtCore import Qt, QTimer, Slot, QPropertyAnimation, QEasingCurve
from PySide6.QtGui import QAction, QActionGroup

from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QHBoxLayout,
    QLabel,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QSlider,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
    QWidgetAction,
    QStackedWidget,
    QGraphicsOpacityEffect,
)

from acquisition.acquisition_manager import AcquisitionManager
from .blackpill_generator_dialog import BlackpillGeneratorDialog
from .oscilloscope_widget import OscilloscopeWidget
from .theme.theme_manager import ThemeManager
from .widgets.welcome_page import WelcomePage
from .theme.app_icon import create_oscilloscope_icon
from .widgets.acquisition_source_dialog import AcquisitionSourceDialog

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
        self.setWindowIcon(create_oscilloscope_icon())
        self.setWindowTitle("Osciloscopio de Audio")
        self.resize(1200, 700)
        self._closing = False
        self._last_error = None
        self._error_box = None
        self._pending_physical_generator = None
        
        self.theme_manager = ThemeManager(self)
        self.theme_manager.apply_theme(self.theme_manager.current_theme)

        # La bienvenida y el osciloscopio comparten una sola ventana.
        self.pages = QStackedWidget(self)
        self.setCentralWidget(self.pages)
        self.welcome_page = WelcomePage(self)
        self.pages.addWidget(self.welcome_page)

        self.scope_page = QWidget(self)
        layout = QVBoxLayout(self.scope_page)
        layout.setContentsMargins(8, 8, 8, 6)
        layout.setSpacing(8)

        self.oscilloscope = OscilloscopeWidget()
        self.oscilloscope.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Expanding,
        )
        layout.addWidget(self.oscilloscope, 1)
        self.pages.addWidget(self.scope_page)
        self.pages.setCurrentWidget(self.welcome_page)

        self.welcome_page.start_requested.connect(self._open_oscilloscope)
        self._page_animation = None

        # Inicio comparte la barra superior con los menús.
        self.home_action = QAction("⌂ Inicio", self)
        self.home_action.setToolTip("Volver a la pantalla de bienvenida")
        self.home_action.triggered.connect(self._show_welcome)
        self.menuBar().addAction(self.home_action)
        self.oscilloscope_logo = QLabel(self)
        self.oscilloscope_logo.setPixmap(create_oscilloscope_icon().pixmap(24, 24))
        self.oscilloscope_logo.setContentsMargins(5, 0, 5, 0)
        self.oscilloscope_logo.setToolTip("Osciloscopio de Audio")
        self.oscilloscope_logo.setStyleSheet("background: transparent; border: none;")
        self.menuBar().setCornerWidget(
            self.oscilloscope_logo, Qt.Corner.TopLeftCorner
        )

        self._create_acquisition_menu()
        self.oscilloscope.acquisition_state_changed.connect(
            self._on_acquisition_state
        )
        self.oscilloscope.acquisition_error.connect(self._show_error)
        
        self._create_appearance_menu()
        self._create_display_menu()
        # Los cursores siguen disponibles en la pestaña CURSORES.
        self._generator_dialog = None
        self._create_blackpill_menu()

        # También refleja RUN/STOP, que no cambia el estado del enlace.
        self.status_timer = QTimer(self)
        self.status_timer.setInterval(250)
        self.status_timer.timeout.connect(self._update_status)
        self.status_timer.start()
        self._update_status()
        
    
    def _transition_to(self, page):
        """Transición suave al cambiar de página."""
        if self.pages.currentWidget() is page:
            return
        if self._page_animation is not None:
            self._page_animation.stop()
        # El efecto se aplica a la página de destino y se retira al finalizar.
        effect = QGraphicsOpacityEffect(page)
        page.setGraphicsEffect(effect)
        effect.setOpacity(0.0)
        self.pages.setCurrentWidget(page)
        animation = QPropertyAnimation(effect, b"opacity", self)
        animation.setDuration(300)
        animation.setStartValue(0.0)
        animation.setEndValue(1.0)
        animation.setEasingCurve(QEasingCurve.Type.InOutCubic)
        animation.finished.connect(lambda: page.setGraphicsEffect(None))
        self._page_animation = animation
        animation.start()

    @Slot()
    def _open_oscilloscope(self):
        manager = self.oscilloscope.acquisition
        dialog = AcquisitionSourceDialog(
            current_source=manager.source,
            current_channels=manager.channels,
            current_usb_port=manager.usb_port,
            parent=self,
        )
        # Al reabrir desde el menú, mostrar la configuración ACTUAL de cada
        # canal. Cancelar deja intacta la adquisición en curso.
        for form, live_panel in (
            (dialog.sim_ch1, self.oscilloscope.controls.simulator_controls),
            (dialog.sim_ch2, self.oscilloscope.controls.simulator_controls_ch2),
        ):
            settings = live_panel.get_settings()
            waveform_index = form.waveform.findData(settings["waveform"])
            if waveform_index >= 0:
                form.waveform.setCurrentIndex(waveform_index)
            form.frequency.setValue(settings["frequency"])
            form.amplitude.setValue(settings["amplitude"])
            form.offset.setValue(settings["offset"])
            form.noise.setValue(settings["noise"])
            form.enabled.setChecked(settings["enabled"])
            form._update_enabled(form.enabled.isChecked())
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        try:
            self._apply_start_configuration(dialog.configuration())
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._transition_to(self.scope_page)
        self._update_status()

    def _apply_start_configuration(self, config):
        scope = self.oscilloscope
        source = config["source"]
        count = int(config["channels"])
        if source not in AcquisitionManager.SAMPLE_RATES or count not in (1, 2):
            raise ValueError("Configuración inicial inválida")

        # No puede haber dos streams usando el mismo dispositivo o puerto.
        scope.disconnect_acquisition()
        scope.channels = count
        scope.acquisition.channels = count
        scope.acquisition.device = None  # sounddevice elige la entrada predeterminada
        scope.acquisition.usb_simulated = False
        self._pending_physical_generator = (
            config["physical_generator"]
            if source == AcquisitionManager.BLACKPILL_USB else None
        )
        if source == AcquisitionManager.BLACKPILL_USB:
            scope.acquisition.usb_port = config["usb_port"]

        # Preparar el panel ANTES de conectar: el callback de conexión
        # aplica estos valores al backend simulado recién iniciado.
        for panel, settings in zip(
            (scope.controls.simulator_controls,
             scope.controls.simulator_controls_ch2),
            config["simulator"],
        ):
            index = panel.waveform.findData(settings["waveform"])
            if index < 0:
                raise ValueError("Forma de onda no disponible")
            panel.waveform.setCurrentIndex(index)
            panel.frequency.setValue(settings["frequency"])
            panel.amplitude.setValue(settings["amplitude"])
            panel.offset.setValue(settings["offset"])
            panel.noise.setValue(settings["noise"])
            panel.channel_enabled.setChecked(settings["enabled"])

        # Un canal centrado; dos canales en 25 % y 75 % de la altura.
        scope.controls.ch2_controls.visible_checkbox.setChecked(count == 2)
        scope.controls.ch2_controls.setEnabled(count == 2)
        if count == 1:
            scope.set_trigger_channel(1)
        scope.set_vertical_position(0.0 if count == 1 else 2.0)
        scope.set_ch2_position(0.0 if count == 1 else -2.0)

        # Incluye arranque y actualización de controles/display.
        scope.change_acquisition_source(source)

    @Slot()
    def _show_welcome(self):
        try:
            self.oscilloscope.disconnect_acquisition()
        except Exception as exc:
            self._show_error(str(exc))
            return
        self._transition_to(self.welcome_page)

    @Slot()
    def _toggle_cursors(self):
        """Alterna entre cursores apagados y manuales, sin cambiar el eje."""
        cursor = self.oscilloscope.controls.cursor_controls
        cursor.mode.setCurrentText(
            "Off" if cursor.mode.currentText() != "Off" else "Manual"
        )

    def _create_blackpill_menu(self):
        menu = self.menuBar().addMenu("Generador Blackpill")
        action = QAction("Generador de señales...", self)
        action.triggered.connect(self._open_generator_dialog)
        menu.addAction(action)

    @Slot()
    def _open_generator_dialog(self):
        if self._generator_dialog is None:
            self._generator_dialog = BlackpillGeneratorDialog(self)
            self._generator_dialog.command_requested.connect(
                self._send_blackpill_command
            )
        self._refresh_generator_status()
        self._generator_dialog.show()
        self._generator_dialog.raise_()
        self._generator_dialog.activateWindow()

    @Slot(object)
    def _send_blackpill_command(self, command):
        try:
            self.oscilloscope.acquisition.send_command(command)
        except Exception as exc:
            self._show_error(str(exc))
        else:
            if self._generator_dialog is not None:
                self._generator_dialog.status_label.setText(
                    f"Comando encolado: {command.text} (sin confirmación del firmware)"
                )

    def _refresh_generator_status(self):
        if self._generator_dialog is None:
            return
        manager = self.oscilloscope.acquisition
        active = (
            manager.source in (manager.SIMULATOR, manager.BLACKPILL_USB)
            and manager.state == manager.CONNECTED
        )
        self._generator_dialog.set_connection_status(
            active,
            "Blackpill conectada: comandos habilitados" if active
            else "Conectá una fuente Blackpill para habilitar los comandos",
        )

    def _create_cursors_menu(self):
        """Acceso a cursores sin ocupar espacio sobre el display."""
        menu = self.menuBar().addMenu("Cursores")
        toggle_action = QAction("Activar / desactivar cursores", self)
        toggle_action.triggered.connect(self._toggle_cursors)
        menu.addAction(toggle_action)

    def _create_appearance_menu(self):
        self.configuration_menu = self.menuBar().addMenu("Configuración")
        menu = self.configuration_menu.addMenu("Apariencia")

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
        # OSCILLOSCOPE_MENU_LAYOUT_V2
        # Menú único: la configuración inicial y los controles de conexión.
        menu = self.menuBar().addMenu("Fuente de entrada")
        self.acquisition_setup_action = QAction("Seleccionar fuente y canales...", self)
        self.acquisition_setup_action.setToolTip(
            "Abrir la misma ventana de selección que aparece al iniciar"
        )
        self.acquisition_setup_action.triggered.connect(self._open_oscilloscope)
        menu.addAction(self.acquisition_setup_action)
        menu.addSeparator()
        # Acceso avanzado opcional; no se pierden las acciones existentes.
        sources_menu = menu.addMenu("Cambio rápido de fuente")
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
    
    def _set_grid_enabled(self, enabled):
        self.oscilloscope.plot.set_grid_enabled(enabled)

        self.theme_manager.settings.setValue(
            "display/grid_enabled",
            enabled,
        )


    def _set_grid_intensity(self, value):
        self.oscilloscope.plot.set_grid_intensity(value)

        self.grid_intensity_label.setText(
            f"Intensidad de grilla: {value} %"
        )

        self.theme_manager.settings.setValue(
            "display/grid_intensity",
            value,
        )
    
    def _create_display_menu(self):
        """Selector independiente de apariencia del gráfico."""

        menu = self.configuration_menu.addMenu("Pantalla")

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
        
        
        # --------------------------------------------------
        # CONTROLES DE GRILLA
        # --------------------------------------------------

        menu.addSeparator()

        self.grid_action = QAction(
            "Mostrar grilla", self
        )
        self.grid_action.setCheckable(True)

        grid_enabled = self.theme_manager.settings.value(
            "display/grid_enabled",
            True,
            type=bool,
        )

        self.grid_action.setChecked(grid_enabled)
        menu.addAction(self.grid_action)

        self.grid_action.toggled.connect(
            self._set_grid_enabled
        )

        self._set_grid_enabled(grid_enabled)

        # Control de intensidad
        grid_widget = QWidget(menu)
        grid_layout = QVBoxLayout(grid_widget)
        grid_layout.setContentsMargins(12, 6, 12, 8)

        self.grid_intensity_label = QLabel(
            "Intensidad de grilla: 50 %"
        )
        grid_layout.addWidget(self.grid_intensity_label)

        self.grid_intensity_slider = QSlider(
            Qt.Orientation.Horizontal
        )
        self.grid_intensity_slider.setRange(0, 100)
        self.grid_intensity_slider.setSingleStep(5)

        saved_intensity = self.theme_manager.settings.value(
            "display/grid_intensity",
            50,
            type=int,
        )

        saved_intensity = max(0, min(100, saved_intensity))

        self.grid_intensity_slider.setValue(saved_intensity)
        grid_layout.addWidget(self.grid_intensity_slider)

        slider_action = QWidgetAction(menu)
        slider_action.setDefaultWidget(grid_widget)
        menu.addAction(slider_action)

        self.grid_intensity_slider.valueChanged.connect(
            self._set_grid_intensity
        )

        self._set_grid_intensity(saved_intensity)

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
        if (state == "connected" and
                self.oscilloscope.acquisition.source == AcquisitionManager.BLACKPILL_USB):
            self._apply_pending_physical_generator()

    def _apply_pending_physical_generator(self):
        settings = self._pending_physical_generator
        self._pending_physical_generator = None
        if settings is None:
            return
        from communication import commands
        count = self.oscilloscope.acquisition.channels
        try:
            for index, parameters in enumerate(settings[:count]):
                name = "L" if index == 0 else "R"
                for command in (
                    commands.set_waveform(name, parameters["waveform"]),
                    commands.set_frequency(name, parameters["frequency"]),
                    commands.set_amplitude(name, parameters["amplitude_percent"]),
                    commands.output_on(name) if parameters["enabled"]
                    else commands.output_off(name),
                ):
                    self.oscilloscope.acquisition.send_command(command)
            # Una sesión mono que configure el generador también apaga R.
            if count == 1:
                self.oscilloscope.acquisition.send_command(commands.output_off("R"))
        except Exception as exc:
            self._show_error("No se pudo configurar el generador físico: " + str(exc))

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
            channels = "CH1/CH2" if manager.channels == 2 else "CH1"
            text += f" | Transporte simulado · PCM24 · {channels} · amplitud sin calibrar"
        if source == manager.BLACKPILL_USB:
            port = manager.usb_port or "automático"
            channels = "CH1/CH2" if manager.channels == 2 else "CH1"
            text += f" | Puerto configurado: {port} | {channels} · amplitud sin calibrar"
        self.statusBar().showMessage(text)
        self._refresh_generator_status()

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