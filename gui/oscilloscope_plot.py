import numpy as np
import pyqtgraph as pg

from PySide6.QtWidgets import QWidget, QVBoxLayout


class OscilloscopePlot(QWidget):

    def __init__(
        self,
        horizontal_divisions,
        vertical_divisions,
        time_per_division,
        volts_per_division,
        trigger_level,
        trigger_position,
        horizontal_position,
        vertical_offset,
        parent=None
    ):

        super().__init__(parent)

        # ============================================================
        # CONFIGURACIÓN DE PANTALLA
        # ============================================================

        self.horizontal_divisions = horizontal_divisions
        self.vertical_divisions = vertical_divisions

        self.time_per_division = time_per_division
        self.volts_per_division = volts_per_division

        # ============================================================
        # POSICIÓN
        # ============================================================

        self.trigger_position = trigger_position
        self.horizontal_position = horizontal_position
        self.vertical_offset = vertical_offset

        # ============================================================
        # TRIGGER
        # ============================================================

        self.trigger_level = trigger_level

        # ============================================================
        # INTERFAZ
        # ============================================================

        self.create_interface()

    # ==================================================================
    # INTERFAZ
    # ==================================================================

    def create_interface(self):

        layout = QVBoxLayout()

        self.setLayout(
            layout
        )

        # ============================================================
        # PLOT
        # ============================================================

        self.plot_widget = pg.PlotWidget()

        layout.addWidget(
            self.plot_widget
        )

        # ============================================================
        # ETIQUETAS
        # ============================================================

        self.plot_widget.setLabel(
            "left",
            "Tensión",
            units="V"
        )

        self.plot_widget.setLabel(
            "bottom",
            "Tiempo",
            units="s"
        )

        # ============================================================
        # GRID
        # ============================================================

        self.plot_widget.showGrid(
            x=True,
            y=True,
            alpha=0.3
        )

        # ============================================================
        # AUTORANGE
        # ============================================================

        self.plot_widget.enableAutoRange(
            x=False,
            y=False
        )

        # ============================================================
        # CURVA
        # ============================================================

        self.curve = self.plot_widget.plot()

        # ============================================================
        # LÍNEA HORIZONTAL DE TRIGGER
        # ============================================================

        self.trigger_line = pg.InfiniteLine(
            pos=self.trigger_level,
            angle=0,
            movable=False
        )

        self.plot_widget.addItem(
            self.trigger_line
        )

        # ============================================================
        # LÍNEA VERTICAL DE TRIGGER
        # ============================================================

        self.trigger_vertical_line = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=False
        )

        self.plot_widget.addItem(
            self.trigger_vertical_line
        )

        # ============================================================
        # ESCALAS INICIALES
        # ============================================================

        self.update_scales()

    # ==================================================================
    # ESCALAS
    # ==================================================================

    def update_scales(self):

        total_time = (
            self.time_per_division * self.horizontal_divisions
        )

        total_voltage = (
            self.volts_per_division * self.vertical_divisions
        )

        # ============================================================
        # EJE X
        # ============================================================

        self.plot_widget.setXRange(
            self.horizontal_position,
            self.horizontal_position + total_time,
            padding=0
        )

        # ============================================================
        # EJE Y
        # ============================================================

        self.plot_widget.setYRange(
            -total_voltage / 2 + self.vertical_offset,
            total_voltage / 2 + self.vertical_offset,
            padding=0
        )

        # ============================================================
        # TRIGGER HORIZONTAL
        # ============================================================

        self.trigger_line.setValue(
            self.trigger_level
        )

        # ============================================================
        # TRIGGER VERTICAL
        # ============================================================

        trigger_time = (
            self.horizontal_position + (self.trigger_position * total_time)
        )

        self.trigger_vertical_line.setValue(
            trigger_time
        )

    # ==================================================================
    # MOSTRAR SEÑAL
    # ==================================================================

    def set_signal(
        self,
        signal,
        sample_rate
    ):

        if signal is None:
            return

        if len(signal) == 0:
            return

        # ============================================================
        # EJE TEMPORAL
        # ============================================================

        time_axis = (
            np.arange(len(signal))/ sample_rate
        )

        # ============================================================
        # MOSTRAR
        # ============================================================

        self.curve.setData(
            time_axis,
            signal
        )

        # ============================================================
        # ESCALA X
        # ============================================================

        total_time = (
            self.time_per_division * self.horizontal_divisions
        )

        self.plot_widget.setXRange(
            self.horizontal_position,
            self.horizontal_position + total_time,
            padding=0
        )

        # ============================================================
        # TRIGGER VERTICAL
        # ============================================================

        trigger_time = (
            self.horizontal_position + (self.trigger_position * total_time)
        )

        self.trigger_vertical_line.setValue(
            trigger_time
        )

    # ==================================================================
    # CONFIGURACIÓN DE TIME/DIV
    # ==================================================================

    def set_time_per_division(
        self,
        time_per_division
    ):

        self.time_per_division = (
            float(time_per_division)
        )

        self.update_scales()

    # ==================================================================
    # CONFIGURACIÓN DE VOLT/DIV
    # ==================================================================

    def set_volts_per_division(
        self,
        volts_per_division
    ):

        self.volts_per_division = (
            float(volts_per_division)
        )

        self.update_scales()

    # ==================================================================
    # CONFIGURACIÓN DEL TRIGGER
    # ==================================================================

    def set_trigger_level(
        self,
        level
    ):

        self.trigger_level = float(level)

        self.trigger_line.setValue(
            self.trigger_level
        )

    # ==================================================================
    # POSICIÓN DEL TRIGGER
    # ==================================================================

    def set_trigger_position(
        self,
        position
    ):

        self.trigger_position = float(
            position
        )

        self.update_scales()

    # ==================================================================
    # OFFSET VERTICAL
    # ==================================================================

    def set_vertical_offset(
        self,
        offset
    ):

        self.vertical_offset = float(
            offset
        )

        self.update_scales()

    # ==================================================================
    # POSICIÓN HORIZONTAL
    # ==================================================================

    def set_horizontal_position(
        self,
        position
    ):

        self.horizontal_position = float(
            position
        )

        self.update_scales()