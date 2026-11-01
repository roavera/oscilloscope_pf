"""Panel frontal del osciloscopio, inspirado en LeCroy."""

from PySide6.QtCore import Signal, QSettings
from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QSizePolicy, QPushButton,
    QButtonGroup, QStackedWidget, QLabel, QFrame,
)
from PySide6.QtCore import Qt

from gui.panels.vertical_controls import VerticalControls
from gui.panels.horizontal_controls import HorizontalControls
from gui.panels.trigger_controls import TriggerControls
from gui.panels.acquisition_controls import AcquisitionControls
from gui.panels.simulator_controls import SimulatorControls
from gui.widgets.cursor_controls import CursorControls


class OscilloscopeControls(QWidget):
    """Contenedor de los paneles de control del osciloscopio."""

    # ============================================================
    # SEÑALES HORIZONTALES
    # ============================================================

    time_per_division_changed = Signal(float)
    horizontal_position_changed = Signal(float)

    # ============================================================
    # SEÑALES VERTICALES
    # ============================================================

    volts_per_division_changed = Signal(float)
    vertical_position_changed = Signal(float)

    # ============================================================
    # SEÑALES DE TRIGGER
    # ============================================================

    trigger_level_changed = Signal(float)
    trigger_slope_changed = Signal(str)
    trigger_mode_changed = Signal(str)
    single_clicked = Signal()

    # ============================================================
    # SEÑALES DE ADQUISICIÓN
    # ============================================================

    run_clicked = Signal()
    stop_clicked = Signal()

    acquisition_mode_changed = Signal(str)
    interpolation_changed = Signal(str)

    # ============================================================
    # SEÑALES DEL SIMULADOR
    # ============================================================

    simulator_settings_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.settings = QSettings(
            "OsciloscopioAudio",
            "OsciloscopioPF",
        )

        self.sections = {}

        self.create_interface()
        self.connect_signals()

    # ============================================================
    # INTERFAZ TIPO OSCILOSCOPIO FÍSICO
    # ============================================================

    def create_interface(self):
        """Navegación lateral sin cambiar el ancho del display."""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(7)

        self.acquisition_controls = AcquisitionControls()
        self.ch1_controls = VerticalControls(channel="CH1")
        self.ch2_controls = VerticalControls(channel="CH2")
        self.horizontal_controls = HorizontalControls()
        self.trigger_controls = TriggerControls()
        self.cursor_controls = CursorControls()
        self.cursor_controls.setToolTip("Los cursores de tensión y Track se refieren a CH1.")
        self.simulator_controls = SimulatorControls()
        self.simulator_controls_ch2 = SimulatorControls(channel="CH2")
        self.simulator_controls_ch2.waveform.setCurrentIndex(1)
        self.simulator_controls_ch2.frequency.setValue(500.0)

        for panel in (
            self.acquisition_controls,
            self.ch1_controls,
            self.horizontal_controls,
            self.trigger_controls,
            self.cursor_controls,
            self.simulator_controls,
        ):
            panel.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )

        # Barra de navegación, siempre por encima de Adquisición.
        nav = QHBoxLayout()
        nav.setContentsMargins(0, 0, 0, 0)
        nav.setSpacing(4)
        self.navigation_group = QButtonGroup(self)
        self.navigation_group.setExclusive(True)
        self.navigation_buttons = {}

        for key, title in (
            ("controls", "CONTROLES"),
            ("measurements", "MEDICIONES"),
            ("cursors", "CURSORES"),
            ("simulator", "SIMULADOR"),
        ):
            button = QPushButton(title, self)
            button.setCheckable(True)
            button.setMinimumHeight(30)
            button.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Fixed,
            )
            button.setStyleSheet("""
                QPushButton {
                    background: #283648;
                    color: #e5edf7;
                    border: 1px solid #3e5066;
                    border-radius: 4px;
                    padding: 5px 2px;
                    font-size: 10px;
                    font-weight: 600;
                }
                QPushButton:checked { background: #496488; }
                QPushButton:hover { background: #3b506b; }
            """)
            self.navigation_group.addButton(button)
            self.navigation_buttons[key] = button
            nav.addWidget(button, 1)

        layout.addLayout(nav)

        # RUN/STOP y el acceso a configuración siempre visibles.
        layout.addWidget(self.acquisition_controls)

        self.pages = QStackedWidget(self)
        self.pages.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Preferred,
        )

        # Página 0: controles físicos existentes.
        controls_page = QWidget()
        controls_layout = QVBoxLayout(controls_page)
        controls_layout.setContentsMargins(0, 0, 0, 0)
        controls_layout.setSpacing(7)
        upper_row = QHBoxLayout()
        upper_row.setSpacing(7)
        upper_row.addWidget(self.horizontal_controls, 1)
        upper_row.addWidget(self.trigger_controls, 1)
        controls_layout.addLayout(upper_row)
        controls_layout.addWidget(self.ch1_controls)
        controls_layout.addWidget(self.ch2_controls)
        controls_layout.addStretch(1)
        self.pages.addWidget(controls_page)

        # Página 1: espacio reservado para mediciones automáticas.
        measurements_page = QWidget()
        measurements_layout = QVBoxLayout(measurements_page)
        measurements_layout.setContentsMargins(8, 12, 8, 8)
        measurements_title = QLabel("Mediciones automáticas · CH1")
        measurements_title.setStyleSheet("font-weight: bold;")
        measurements_layout.addWidget(measurements_title)
        measurements_note = QLabel(
            "Próximamente: frecuencia, período, RMS y Vpp.\n"
            "Todavía no se calculan ni se muestran valores ficticios."
        )
        measurements_note.setWordWrap(True)
        measurements_layout.addWidget(measurements_note)
        measurements_layout.addStretch(1)
        self.pages.addWidget(measurements_page)

        # Página 2: reutiliza el panel de cursores original.
        cursors_page = QWidget()
        cursors_layout = QVBoxLayout(cursors_page)
        cursors_layout.setContentsMargins(0, 0, 0, 0)
        self.cursor_section = self.cursor_controls
        cursors_layout.addWidget(self.cursor_section)
        cursors_layout.addStretch(1)
        self.pages.addWidget(cursors_page)

        # Página 3: se habilita solo al seleccionar la fuente simulador.
        simulator_page = QWidget()
        simulator_layout = QVBoxLayout(simulator_page)
        simulator_layout.setContentsMargins(0, 0, 0, 0)
        self.simulator_section = self.simulator_controls
        simulator_layout.addWidget(self.simulator_section)
        simulator_layout.addWidget(self.simulator_controls_ch2)
        simulator_layout.addStretch(1)
        self.pages.addWidget(simulator_page)

        for index, key in enumerate(
            ("controls", "measurements", "cursors", "simulator")
        ):
            self.navigation_buttons[key].clicked.connect(
                lambda _checked=False, i=index: self.pages.setCurrentIndex(i)
            )

        self.navigation_buttons["controls"].setChecked(True)
        self.navigation_buttons["simulator"].setVisible(False)
        self.pages.setCurrentIndex(0)
        layout.addWidget(self.pages)

    # ============================================================
    # VISIBILIDAD DEL SIMULADOR
    # ============================================================

    def set_simulator_visible(self, visible):
        """Habilita la pestaña del simulador sin destruir sus controles."""
        visible = bool(visible)
        self.navigation_buttons["simulator"].setVisible(visible)
        if not visible and self.pages.currentIndex() == 3:
            self.navigation_buttons["controls"].setChecked(True)
            self.pages.setCurrentIndex(0)

    # ============================================================
    # CONEXIONES DE SEÑALES
    # ============================================================

    def connect_signals(self):

        # --------------------------------------------------------
        # SIMULADOR
        # --------------------------------------------------------

        self.simulator_controls.settings_changed.connect(
            self.simulator_settings_changed.emit
        )

        # --------------------------------------------------------
        # CONTROL VERTICAL
        # --------------------------------------------------------

        self.ch1_controls.volts_per_division_changed.connect(
            self.volts_per_division_changed.emit
        )

        self.ch1_controls.position_changed.connect(
            self.vertical_position_changed.emit
        )

        # --------------------------------------------------------
        # CONTROL HORIZONTAL
        # --------------------------------------------------------

        self.horizontal_controls.time_per_division_changed.connect(
            self.time_per_division_changed.emit
        )

        self.horizontal_controls.position_changed.connect(
            self.horizontal_position_changed.emit
        )

        # --------------------------------------------------------
        # TRIGGER
        # --------------------------------------------------------

        self.trigger_controls.level_changed.connect(
            self.trigger_level_changed.emit
        )

        self.trigger_controls.slope_changed.connect(
            self.trigger_slope_changed.emit
        )

        self.trigger_controls.mode_changed.connect(
            self.trigger_mode_changed.emit
        )

        # SINGLE ahora pertenece al panel Trigger.
        self.trigger_controls.single_clicked.connect(
            self.single_clicked.emit
        )

        # --------------------------------------------------------
        # RUN / STOP
        # --------------------------------------------------------

        self.acquisition_controls.run_clicked.connect(
            self.run_clicked.emit
        )

        self.acquisition_controls.stop_clicked.connect(
            self.stop_clicked.emit
        )

        # --------------------------------------------------------
        # MODOS DE ADQUISICIÓN
        # --------------------------------------------------------

        self.acquisition_controls.mode_changed.connect(
            self.acquisition_mode_changed.emit
        )

        # --------------------------------------------------------
        # INTERPOLACIÓN
        # --------------------------------------------------------

        self.acquisition_controls.interpolation_changed.connect(
            self.interpolation_changed.emit
        )

    # ============================================================
    # CONFIGURACIÓN HORIZONTAL
    # ============================================================

    def set_time_per_division(self, value):
        self.horizontal_controls.set_time_per_division(
            value
        )

    def set_horizontal_position(self, divisions):
        self.horizontal_controls.set_position(
            divisions
        )

    # ============================================================
    # CONFIGURACIÓN VERTICAL
    # ============================================================

    def set_volts_per_division(self, value):
        self.ch1_controls.set_volts_per_division(
            value
        )

    def set_vertical_position(self, divisions):
        self.ch1_controls.set_position(
            divisions
        )

    # ============================================================
    # CONFIGURACIÓN TRIGGER
    # ============================================================

    def set_trigger_level(self, value):
        self.trigger_controls.set_level(
            value
        )

    def set_trigger_slope(self, value):
        self.trigger_controls.set_slope(
            value
        )

    def set_trigger_mode(self, value):
        self.trigger_controls.set_mode(
            value
        )

    def set_trigger_range(self, minimum, maximum):
        self.trigger_controls.set_level_range(
            minimum,
            maximum,
        )

    # ============================================================
    # CONFIGURACIÓN ADQUISICIÓN
    # ============================================================

    def set_acquisition_mode(self, mode):
        self.acquisition_controls.set_mode(
            mode
        )

    def set_interpolation(self, interpolation):
        self.acquisition_controls.set_interpolation(
            interpolation
        )

    def enable_acquisition_mode(self, mode, enabled=True):
        self.acquisition_controls.enable_mode(
            mode,
            enabled,
        )

    def enable_interpolation(self, interpolation, enabled=True):
        self.acquisition_controls.enable_interpolation(
            interpolation,
            enabled,
        )

    # ============================================================
    # SINCRONIZACIÓN DE CONFIGURACIÓN
    # ============================================================

    def sync_settings(self, settings):
        """Sincroniza los controles con el estado del osciloscopio."""

        self.set_time_per_division(
            settings.time_per_division
        )

        self.set_horizontal_position(
            settings.horizontal_position_divisions
        )

        self.set_volts_per_division(
            settings.volts_per_division
        )

        self.set_vertical_position(
            settings.vertical_position_divisions
        )

        self.set_trigger_level(
            settings.trigger_level
        )

        self.set_trigger_slope(
            settings.trigger_slope
        )

        self.set_trigger_mode(
            settings.trigger_mode
        )

    # ============================================================
    # ESTADO DE ADQUISICIÓN
    # ============================================================

    def show_state(self, running, status, error=None):
        """Actualiza el estado y los botones RUN/STOP."""

        self.acquisition_controls.show_state(
            running,
            status,
            error,
        )

    def set_acquisition_enabled(self, enabled):
        """Habilita o deshabilita RUN/STOP."""

        self.acquisition_controls.set_actions_enabled(
            enabled
        )

        # SINGLE requiere una fuente conectada.
        # El controlador decide cuándo está disponible.
        self.trigger_controls.single_button.setEnabled(
            bool(enabled)
        )

    # ============================================================
    # ACCESO A BOTONES
    # ============================================================

    @property
    def run_button(self):
        return self.acquisition_controls.run_button

    @property
    def stop_button(self):
        return self.acquisition_controls.stop_button

    @property
    def single_button(self):
        return self.trigger_controls.single_button
