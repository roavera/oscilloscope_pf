"""Paneles de control organizados en secciones plegables."""

from PySide6.QtCore import Signal, QSettings
from PySide6.QtWidgets import QWidget, QVBoxLayout, QSizePolicy

from gui.panels.vertical_controls import VerticalControls
from gui.panels.horizontal_controls import HorizontalControls
from gui.panels.trigger_controls import TriggerControls
from gui.panels.acquisition_controls import AcquisitionControls
from gui.panels.simulator_controls import SimulatorControls
from gui.widgets.cursor_controls import CursorControls
from gui.widgets.collapsible_section import CollapsibleSection


class OscilloscopeControls(QWidget):
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
        self.settings = QSettings("OsciloscopioAudio", "OsciloscopioPF")
        self.sections = {}
        self.create_interface()
        self.connect_signals()

    def _add_section(self, layout, key, title, widget, default=True):
        expanded = self.settings.value(f"controls/expanded/{key}", default, type=bool)
        section = CollapsibleSection(title, widget, expanded=expanded, parent=self)
        section.toggled.connect(
            lambda value, section_key=key: self.settings.setValue(
                f"controls/expanded/{section_key}", value
            )
        )
        layout.addWidget(section)
        self.sections[key] = section
        return section

    def create_interface(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(8)

        self.acquisition_controls = AcquisitionControls()
        self.ch1_controls = VerticalControls(channel="CH1")
        self.horizontal_controls = HorizontalControls()
        self.trigger_controls = TriggerControls()
        self.cursor_controls = CursorControls()
        self.simulator_controls = SimulatorControls()

        for panel in (
            self.acquisition_controls,
            self.ch1_controls,
            self.horizontal_controls,
            self.trigger_controls,
            self.cursor_controls,
            self.simulator_controls,
        ):
            panel.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)

        self._add_section(layout, "acquisition", "Adquisición", self.acquisition_controls)
        self._add_section(layout, "vertical", "Vertical — CH1", self.ch1_controls)
        self._add_section(layout, "horizontal", "Horizontal", self.horizontal_controls)
        self._add_section(layout, "trigger", "Trigger", self.trigger_controls)
        self.cursor_section = self._add_section(
            layout, "cursors", "Cursores — CH1", self.cursor_controls, default=False
        )
        self.simulator_section = self._add_section(
            layout, "simulator", "Generador simulado", self.simulator_controls, default=False
        )
        self.simulator_section.setVisible(False)
        layout.addStretch(1)

    def set_simulator_visible(self, visible):
        self.simulator_section.setVisible(bool(visible))

    def connect_signals(self):
        self.simulator_controls.settings_changed.connect(self.simulator_settings_changed.emit)
        self.ch1_controls.volts_per_division_changed.connect(self.volts_per_division_changed.emit)
        self.ch1_controls.position_changed.connect(self.vertical_position_changed.emit)
        self.horizontal_controls.time_per_division_changed.connect(self.time_per_division_changed.emit)
        self.horizontal_controls.position_changed.connect(self.horizontal_position_changed.emit)
        self.trigger_controls.level_changed.connect(self.trigger_level_changed.emit)
        self.trigger_controls.slope_changed.connect(self.trigger_slope_changed.emit)
        self.trigger_controls.mode_changed.connect(self.trigger_mode_changed.emit)
        self.acquisition_controls.run_stop_clicked.connect(self.run_stop_clicked.emit)
        self.acquisition_controls.single_clicked.connect(self.single_clicked.emit)

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
        self.trigger_controls.set_level_range(minimum, maximum)

    def sync_settings(self, settings):
        self.set_time_per_division(settings.time_per_division)
        self.set_horizontal_position(settings.horizontal_position_divisions)
        self.set_volts_per_division(settings.volts_per_division)
        self.set_vertical_position(settings.vertical_position_divisions)
        self.set_trigger_level(settings.trigger_level)
        self.set_trigger_slope(settings.trigger_slope)
        self.set_trigger_mode(settings.trigger_mode)

    def show_state(self, running, status, error=None):
        self.acquisition_controls.show_state(running, status, error)

    def set_acquisition_enabled(self, enabled):
        self.acquisition_controls.set_actions_enabled(enabled)

    @property
    def run_button(self):
        return self.acquisition_controls.run_button

    @property
    def single_button(self):
        return self.acquisition_controls.single_button
