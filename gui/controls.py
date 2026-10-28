"""Organiza los paneles con una disposición de osciloscopio."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QWidget,
    QGridLayout,
    QSizePolicy,
)

from gui.panels.vertical_controls import VerticalControls
from gui.panels.horizontal_controls import HorizontalControls
from gui.panels.trigger_controls import TriggerControls
from gui.panels.acquisition_controls import AcquisitionControls
from gui.panels.simulator_controls import SimulatorControls


class OscilloscopeControls(QWidget):

    # ================================================================
    # SEÑALES HACIA EL CONTROLADOR
    # ================================================================

    time_per_division_changed = Signal(float)
    horizontal_position_changed = Signal(float)

    volts_per_division_changed = Signal(float)
    vertical_position_changed = Signal(float)

    trigger_level_changed = Signal(float)
    trigger_slope_changed = Signal(str)
    trigger_mode_changed = Signal(str)

    run_stop_clicked = Signal()
    single_clicked = Signal()
    simulator_settings_changed = Signal(dict)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setMinimumWidth(450)

        self.create_interface()
        self.connect_signals()

    # ================================================================
    # ORGANIZACIÓN DE PANELES
    # ================================================================

    def create_interface(self):
        layout = QGridLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setHorizontalSpacing(8)
        layout.setVerticalSpacing(12)

        self.ch1_controls = VerticalControls(channel="CH1")
        self.horizontal_controls = HorizontalControls()
        self.trigger_controls = TriggerControls()
        self.acquisition_controls = AcquisitionControls()
        self.simulator_controls = SimulatorControls()
        self.simulator_controls.setVisible(False)

        # Fila superior: adquisición.
        layout.addWidget(
            self.acquisition_controls,
            0, 0, 1, 3,
        )

        # Segunda fila: vertical, horizontal y trigger.
        layout.addWidget(self.ch1_controls, 1, 0)
        layout.addWidget(self.horizontal_controls, 1, 1)
        layout.addWidget(self.trigger_controls, 1, 2)

        panels = (
            self.ch1_controls,
            self.horizontal_controls,
            self.trigger_controls,
        )

        for panel in panels:
            panel.setMinimumWidth(135)

            panel.setSizePolicy(
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.Preferred,
            )

            # Mantiene los controles arriba en cada sección.
            panel.layout().addStretch()

        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)

        # El espacio adicional queda debajo del conjunto.
        layout.addWidget(self.simulator_controls, 2, 0, 1, 3)
        layout.setRowStretch(3, 1)

    # ================================================================
    # REENVÍO DE SEÑALES
    # ================================================================

    def connect_signals(self):
        self.simulator_controls.settings_changed.connect(
            self.simulator_settings_changed.emit
        )

        # Control vertical.
        self.ch1_controls.volts_per_division_changed.connect(
            self.volts_per_division_changed.emit
        )

        self.ch1_controls.position_changed.connect(
            self.vertical_position_changed.emit
        )

        # Control horizontal.
        self.horizontal_controls.time_per_division_changed.connect(
            self.time_per_division_changed.emit
        )

        self.horizontal_controls.position_changed.connect(
            self.horizontal_position_changed.emit
        )

        # Trigger.
        self.trigger_controls.level_changed.connect(
            self.trigger_level_changed.emit
        )

        self.trigger_controls.slope_changed.connect(
            self.trigger_slope_changed.emit
        )

        self.trigger_controls.mode_changed.connect(
            self.trigger_mode_changed.emit
        )

        # Adquisición.
        self.acquisition_controls.run_stop_clicked.connect(
            self.run_stop_clicked.emit
        )

        self.acquisition_controls.single_clicked.connect(
            self.single_clicked.emit
        )

    # ================================================================
    # ACTUALIZACIÓN DESDE EL CONTROLADOR
    # ================================================================

    def set_time_per_division(self, value):
        self.horizontal_controls.set_time_per_division(value)

    def set_horizontal_position(self, divisions):
        self.horizontal_controls.set_position(divisions)

    def set_volts_per_division(self, value):
        self.ch1_controls.set_volts_per_division(value)

    def set_vertical_position(self, divisions):
        self.ch1_controls.set_position(divisions)

    def set_trigger_level(self, value):
        self.trigger_controls.set_level(value)

    def set_trigger_slope(self, value):
        self.trigger_controls.set_slope(value)

    def set_trigger_mode(self, value):
        self.trigger_controls.set_mode(value)

    def set_trigger_range(self, minimum, maximum):
        self.trigger_controls.set_level_range(
            minimum,
            maximum,
        )

    def sync_settings(self, settings):
        """Refleja el estado del controlador en todos los paneles."""

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

        self.set_trigger_level(settings.trigger_level)
        self.set_trigger_slope(settings.trigger_slope)
        self.set_trigger_mode(settings.trigger_mode)

    # ================================================================
    # ESTADO DE ADQUISICIÓN
    # ================================================================

    def show_state(self, running, status, error=None):
        self.acquisition_controls.show_state(
            running,
            status,
            error,
        )

    def set_acquisition_enabled(self, enabled):
        self.acquisition_controls.set_actions_enabled(enabled)

    # ================================================================
    # ACCESO A BOTONES DESDE EL WIDGET
    # ================================================================

    @property
    def run_button(self):
        return self.acquisition_controls.run_button

    @property
    def single_button(self):
        return self.acquisition_controls.single_button