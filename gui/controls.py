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


class OscilloscopeControls(QWidget):

    # ================================================================
    # SEÑALES HACIA EL CONTROLADOR
    # ================================================================

    time_per_division_changed = Signal(float)
    volts_per_division_changed = Signal(float)
    vertical_position_changed = Signal(float)

    trigger_level_changed = Signal(float)
    trigger_slope_changed = Signal(str)
    trigger_mode_changed = Signal(str)

    run_stop_clicked = Signal()
    single_clicked = Signal()

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

        # ------------------------------------------------------------
        # FILA SUPERIOR: ADQUISICIÓN
        # Ocupa las tres columnas.
        # ------------------------------------------------------------

        layout.addWidget(
            self.acquisition_controls,
            0, 0, 1, 3,
        )

        # ------------------------------------------------------------
        # FILA INFERIOR: VERTICAL / HORIZONTAL / TRIGGER
        # ------------------------------------------------------------

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

            # Los controles quedan arriba dentro de cada sección.
            panel.layout().addStretch()

        # Las tres columnas comparten el ancho disponible.
        layout.setColumnStretch(0, 1)
        layout.setColumnStretch(1, 1)
        layout.setColumnStretch(2, 1)

        # El espacio adicional queda debajo del conjunto.
        layout.setRowStretch(2, 1)

    # ================================================================
    # REENVÍO DE SEÑALES
    # ================================================================

    def connect_signals(self):
        self.ch1_controls.volts_per_division_changed.connect(
            self.volts_per_division_changed.emit
        )

        self.ch1_controls.position_changed.connect(
            self.vertical_position_changed.emit
        )

        self.horizontal_controls.time_per_division_changed.connect(
            self.time_per_division_changed.emit
        )

        self.trigger_controls.level_changed.connect(
            self.trigger_level_changed.emit
        )

        self.trigger_controls.slope_changed.connect(
            self.trigger_slope_changed.emit
        )

        self.trigger_controls.mode_changed.connect(
            self.trigger_mode_changed.emit
        )

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

    def sync_settings(self, settings):
        self.set_time_per_division(settings.time_per_division)
        self.set_volts_per_division(settings.volts_per_division)

        self.set_vertical_position(
            settings.vertical_position_divisions
        )

        self.set_trigger_level(settings.trigger_level)
        self.set_trigger_slope(settings.trigger_slope)
        self.set_trigger_mode(settings.trigger_mode)

    def show_state(self, running, status, error=None):
        self.acquisition_controls.show_state(
            running,
            status,
            error,
        )

    def set_acquisition_enabled(self, enabled):
        self.acquisition_controls.set_actions_enabled(enabled)

    # ================================================================
    # COMPATIBILIDAD CON EL WIDGET ACTUAL
    # ================================================================

    @property
    def run_button(self):
        return self.acquisition_controls.run_button

    @property
    def single_button(self):
        return self.acquisition_controls.single_button