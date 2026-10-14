"""Visualización de señales y ajuste gráfico del nivel de trigger."""

import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout


class OscilloscopePlot(QWidget):

    # Se emite solo cuando el usuario arrastra el trigger.
    trigger_level_changed = Signal(float)

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
        parent=None,
    ):
        super().__init__(parent)

        self.horizontal_divisions = horizontal_divisions
        self.vertical_divisions = vertical_divisions

        self.time_per_division = float(time_per_division)
        self.volts_per_division = float(volts_per_division)

        self.horizontal_position = float(horizontal_position)
        self.vertical_offset = float(vertical_offset)

        self.trigger_level = float(trigger_level)
        self.trigger_position = float(trigger_position)

        self.create_interface()

    # ================================================================
    # INTERFAZ
    # ================================================================

    def create_interface(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget)

        self.plot_widget.setLabel(
            "left",
            "Tensión",
            units="V",
        )

        self.plot_widget.setLabel(
            "bottom",
            "Tiempo",
            units="s",
        )

        self.plot_widget.showGrid(
            x=True,
            y=True,
            alpha=0.3,
        )

        self.plot_widget.enableAutoRange(
            x=False,
            y=False,
        )

        # Las escalas se manejan desde los controles.
        self.plot_widget.setMouseEnabled(x=False, y=False)
        self.plot_widget.setMenuEnabled(False)

        self.curve = self.plot_widget.plot(
            pen=pg.mkPen("#e3c84b", width=1),
        )

        # ------------------------------------------------------------
        # NIVEL DE TRIGGER
        # ------------------------------------------------------------

        self.trigger_line = pg.InfiniteLine(
            pos=self.trigger_level,
            angle=0,
            movable=True,
            pen=pg.mkPen("#ff40c8", width=1.5),
            hoverPen=pg.mkPen("#ff8de0", width=2.5),
        )

        self.trigger_line.addMarker(
            "v",
            position=0.985,
            size=18,
        )

        self.trigger_line.setZValue(20)

        self.trigger_line.setToolTip(
            "Arrastrá el triángulo o la línea para ajustar el trigger."
        )

        self.plot_widget.addItem(
            self.trigger_line,
            ignoreBounds=True,
        )

        # Los cambios programáticos con setValue() no emiten
        # esta señal de arrastre.
        self.trigger_line.sigDragged.connect(
            self._on_trigger_dragged
        )

        # ------------------------------------------------------------
        # REFERENCIA TEMPORAL DEL TRIGGER
        # ------------------------------------------------------------

        self.trigger_vertical_line = pg.InfiniteLine(
            pos=0.0,
            angle=90,
            movable=False,
            pen=pg.mkPen("#808080", width=1),
        )

        self.plot_widget.addItem(
            self.trigger_vertical_line,
            ignoreBounds=True,
        )

        # ------------------------------------------------------------
        # AVISO DE NIVEL FUERA DE PANTALLA
        # ------------------------------------------------------------

        self.trigger_notice = pg.TextItem(
            color="#ff40c8",
            anchor=(1, 0),
        )

        self.trigger_notice.setZValue(30)

        self.plot_widget.addItem(
            self.trigger_notice,
            ignoreBounds=True,
        )

        self.update_scales()

    # ================================================================
    # RANGOS VISIBLES
    # ================================================================

    def vertical_range(self):
        half_range = (
            self.volts_per_division
            * self.vertical_divisions
            / 2
        )

        return (
            self.vertical_offset - half_range,
            self.vertical_offset + half_range,
        )

    def update_scales(self):
        total_time = (
            self.time_per_division * self.horizontal_divisions
        )

        self.plot_widget.setXRange(
            self.horizontal_position,
            self.horizontal_position + total_time,
            padding=0,
        )

        y_min, y_max = self.vertical_range()

        self.plot_widget.setYRange(
            y_min,
            y_max,
            padding=0,
        )

        # Cambiar la escala no modifica el umbral.
        self.trigger_line.setValue(self.trigger_level)

        self._update_time_reference()
        self._update_trigger_notice()

    def _update_time_reference(self):
        total_time = (
            self.time_per_division * self.horizontal_divisions
        )

        trigger_time = (
            self.horizontal_position
            + self.trigger_position * total_time
        )

        self.trigger_vertical_line.setValue(trigger_time)

    def _update_trigger_notice(self):
        y_min, y_max = self.vertical_range()

        total_time = (
            self.time_per_division * self.horizontal_divisions
        )

        self.trigger_notice.setPos(
            self.horizontal_position + total_time * 0.98,
            y_max,
        )

        outside = not y_min <= self.trigger_level <= y_max

        if outside:
            self.trigger_notice.setText(
                "Trigger fuera de vista: "
                f"{self.trigger_level:+.6g} V"
            )

        self.trigger_notice.setVisible(outside)

    # ================================================================
    # ARRASTRE DEL TRIGGER
    # ================================================================

    def _on_trigger_dragged(self, line):
        y_min, y_max = self.vertical_range()

        level = float(
            np.clip(line.value(), y_min, y_max)
        )

        self.set_trigger_level(level)
        self.trigger_level_changed.emit(level)

    # ================================================================
    # MOSTRAR SEÑAL
    # ================================================================

    def set_signal(self, signal, sample_rate, trigger_sample=None):
        """
        Muestra una ventana de muestras.

        trigger_sample es la posición del cruce dentro de esa ventana,
        expresada en muestras. Puede incluir una fracción de muestra.
        """
        if signal is None or len(signal) == 0:
            self.clear_signal()
            return

        sample_rate = float(sample_rate)

        if not np.isfinite(sample_rate) or sample_rate <= 0:
            raise ValueError(
                "La frecuencia de muestreo debe ser positiva y finita."
            )

        time_axis = (
            np.arange(len(signal), dtype=float) / sample_rate
        )

        total_time = (
            self.time_per_division * self.horizontal_divisions
        )

        if trigger_sample is not None:
            trigger_sample = float(trigger_sample)

            if not np.isfinite(trigger_sample):
                raise ValueError(
                    "La posición del disparo debe ser finita."
                )

            # Posición del disparo en las coordenadas de pantalla.
            trigger_time = (
                self.horizontal_position
                + self.trigger_position * total_time
            )

            # Alinea el cruce interpolado con la línea vertical.
            time_axis += (
                trigger_time - trigger_sample / sample_rate
            )

        else:
            # Auto sin disparo: ubica la ventana desde el borde izquierdo.
            time_axis += self.horizontal_position

        self.curve.setData(time_axis, signal)

    def clear_signal(self):
        """Limpia la traza conservando escalas y referencias."""
        self.curve.setData([], [])

    # ================================================================
    # ACTUALIZACIÓN DESDE EL CONTROLADOR
    # ================================================================

    def set_time_per_division(self, value):
        value = float(value)

        if not np.isfinite(value) or value <= 0:
            raise ValueError(
                "Tiempo/div debe ser positivo y finito."
            )

        self.time_per_division = value
        self.update_scales()

    def set_volts_per_division(self, value):
        value = float(value)

        if not np.isfinite(value) or value <= 0:
            raise ValueError(
                "Volt/div debe ser positivo y finito."
            )

        self.volts_per_division = value
        self.update_scales()

    def set_trigger_level(self, level):
        """Actualiza el nivel sin emitir trigger_level_changed."""
        level = float(level)

        if not np.isfinite(level):
            raise ValueError("El nivel de trigger debe ser finito.")

        self.trigger_level = level
        self.trigger_line.setValue(level)

        self.trigger_line.setToolTip(
            f"Trigger: {level:+.6g} V\n"
            "Arrastrá para ajustar el nivel."
        )

        self._update_trigger_notice()

    def set_trigger_position(self, position):
        """Ubica la referencia temporal entre los bordes de pantalla."""
        position = float(position)

        if not np.isfinite(position):
            raise ValueError(
                "La posición del trigger debe ser finita."
            )

        self.trigger_position = float(
            np.clip(position, 0.0, 1.0)
        )

        self._update_time_reference()

    def set_vertical_offset(self, offset):
        offset = float(offset)

        if not np.isfinite(offset):
            raise ValueError("El offset vertical debe ser finito.")

        self.vertical_offset = offset
        self.update_scales()

    def set_horizontal_position(self, position):
        """Cambia el origen del eje X, expresado en segundos."""
        position = float(position)

        if not np.isfinite(position):
            raise ValueError(
                "El origen del eje temporal debe ser finito."
            )

        self.horizontal_position = position
        self.update_scales()