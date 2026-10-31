"""Visualización de señales y ajuste gráfico del nivel de trigger."""

import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import Signal, QRectF, Qt, QPointF
from PySide6.QtGui import QColor, QBrush, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsObject, QWidget, QVBoxLayout

from .theme.colors import PLOT_COLORS
from .oscilloscope_grid import OscilloscopeGrid

class ChannelMarker(QGraphicsObject):
    """Triángulo CH1 de tamaño fijo, arrastrable sobre el eje izquierdo."""

    def __init__(self, plot):
        super().__init__()
        self.plot = plot
        self.setZValue(40)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip("CH1 · Posición de 0 V. Arrastrá para mover el canal.")

    def boundingRect(self):
        return QRectF(-2, -13, 32, 26)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        
        color = PLOT_COLORS[
            self.plot.display_theme
        ]["ch1"]

        painter.setPen(QPen(QColor(color).darker(130), 1))
        painter.setBrush(QBrush(QColor(color)))
        
        painter.drawPolygon(QPolygonF([
            QPointF(0, -11), QPointF(28, 0), QPointF(0, 11)
        ]))
        painter.setPen(QColor("#171717"))
        painter.drawText(QRectF(1, -10, 16, 20),
                         Qt.AlignmentFlag.AlignCenter, "1")

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return

        # Guardamos la referencia al inicio del arrastre. No usamos la
        # posición actual del marcador porque se mueve junto con el rango Y.
        self._drag_start_scene_y = event.scenePos().y()
        self._drag_start_divisions = (
            -self.plot.vertical_offset / self.plot.volts_per_division
        )
        event.accept()

    def mouseMoveEvent(self, event):
        if not hasattr(self, "_drag_start_scene_y"):
            event.ignore()
            return

        view = self.plot.plot_widget.getViewBox()
        height = view.sceneBoundingRect().height()
        if height <= 0:
            event.accept()
            return

        delta_pixels = self._drag_start_scene_y - event.scenePos().y()
        delta_divisions = (
            delta_pixels * self.plot.vertical_divisions / height
        )
        half = self.plot.vertical_divisions / 2.0
        divisions = float(np.clip(
            self._drag_start_divisions + delta_divisions, -half, half
        ))

        # El controlador es el único que cambia el offset y actualiza
        # el gráfico. Así evitamos actualizaciones duplicadas.
        self.plot.vertical_position_changed.emit(divisions)
        event.accept()

    def mouseReleaseEvent(self, event):
        if hasattr(self, "_drag_start_scene_y"):
            del self._drag_start_scene_y
        event.accept()


class OscilloscopePlot(QWidget):
    
    # Se emite solo cuando el usuario arrastra el trigger.
    trigger_level_changed = Signal(float)
    horizontal_position_changed = Signal(float)
    vertical_position_changed = Signal(float)
    cursor_readout_changed = Signal(str)

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

        self.cursor_mode = "Off"
        self.cursor_orientation = "Tiempo"
        self._cursor_updating = False
        self._cursor_signal_x = np.array([], dtype=float)
        self._cursor_signal_y = np.array([], dtype=float)
        self.display_theme = "dark"
        self.create_interface()
            
    def set_grid_enabled(self, enabled: bool):
        """Activa o desactiva la grilla del display."""
        self.grid.set_grid_enabled(enabled)


    def set_grid_intensity(self, percentage: int):
        """Ajusta la intensidad de la grilla entre 0 y 100 %."""
        percentage = max(0, min(100, int(percentage)))
        self.grid.set_grid_intensity(percentage / 100.0)

    
    def set_display_theme(self, theme_name: str):
        """Cambia la apariencia del gráfico sin modificar la adquisición."""

        if theme_name not in PLOT_COLORS:
            raise ValueError(
                f"Tema de pantalla desconocido: {theme_name}"
            )

        self.display_theme = theme_name
        colors = PLOT_COLORS[theme_name]

        # Fondo del área de visualización.
        self.plot_widget.setBackground(colors["background"])

        # Traza CH1.
        self.curve.setPen(
            pg.mkPen(colors["ch1"], width=2)
        )

        # Trigger horizontal.
        self.trigger_line.setPen(
            pg.mkPen(colors["trigger"], width=1.5)
        )
        self.trigger_line.setHoverPen(
            pg.mkPen(colors["trigger"], width=2.5)
        )

        # Referencia temporal vertical.
        reference_color = (
            "#A8B5C8"
            if theme_name == "dark"
            else "#68778A"
        )

        self.trigger_vertical_line.setPen(
            pg.mkPen(
                reference_color,
                width=1.2,
                style=Qt.PenStyle.DashLine,
            )
        )
        self.trigger_vertical_line.setHoverPen(
            pg.mkPen(reference_color, width=2)
        )

        # Aviso de trigger fuera de pantalla.
        self.trigger_notice.setColor(colors["trigger"])

        # Ejes y etiquetas.
        axis_color = (
            "#A8B5C8"
            if theme_name == "dark"
            else "#596A7D"
        )

        plot_item = self.plot_widget.getPlotItem()

        for axis_name in ("left", "bottom"):
            axis = plot_item.getAxis(axis_name)
            axis.setPen(pg.mkPen(axis_color))
            axis.setTextPen(pg.mkPen(axis_color))
            axis.setStyle(tickFont=None)

        # Contraste del marcador CH1.
        self.channel_marker.update()

        # Repintar sin cambiar escalas ni muestras.
        self.plot_widget.update()
        
        self.grid.set_theme(theme_name)

    def _update_grid(self, *args):
        view = self.plot_widget.getViewBox()
        x_range, y_range = view.viewRange()

        self.grid.set_rect(
            QRectF(
                x_range[0],
                y_range[0],
                x_range[1] - x_range[0],
                y_range[1] - y_range[0],
            )
        )
    
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

        self.plot_widget.showGrid(x=False, y=False)

        self.grid = OscilloscopeGrid(
            horizontal_divisions=self.horizontal_divisions,
            vertical_divisions=self.vertical_divisions,
        )

        self.plot_widget.addItem(self.grid, ignoreBounds=True)
        # Mantener la grilla por debajo de la traza y los indicadores.
        self.grid.setZValue(1)

        view = self.plot_widget.getViewBox()
        view.sigRangeChanged.connect(self._update_grid)
        view.sigResized.connect(self._update_grid)

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
        self.curve.setZValue(5)

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
            movable=True,
            pen=pg.mkPen("#808080", width=1.3),
            hoverPen=pg.mkPen("#b0b0b0", width=2),
        )
        self.trigger_vertical_line.addMarker("v", position=0.98, size=18)
        self.trigger_vertical_line.setZValue(15)
        self.trigger_vertical_line.setToolTip(
            "Arrastrá la línea o el triángulo gris para ajustar la posición horizontal."
        )

        self.plot_widget.addItem(
            self.trigger_vertical_line,
            ignoreBounds=True,
        )
        self.trigger_vertical_line.sigDragged.connect(
            self._on_horizontal_reference_dragged
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

        # Marcador independiente: no dibuja ninguna línea horizontal.
        self.channel_marker = ChannelMarker(self)
        self.plot_widget.scene().addItem(self.channel_marker)
        view = self.plot_widget.getViewBox()
        view.sigRangeChanged.connect(self._update_channel_marker)
        view.sigResized.connect(self._update_channel_marker)

        self._create_cursors()
        self.update_scales()
        self._update_grid()
        
        self.set_display_theme(self.display_theme)

    def _update_channel_marker(self, *args):
        """Fija el triángulo al borde izquierdo y a la altura de 0 V."""
        view = self.plot_widget.getViewBox()
        scene_rect = view.sceneBoundingRect()
        zero_scene_y = view.mapViewToScene(QPointF(0.0, 0.0)).y()
        # Posición siempre visible, aun en los extremos ±4 divisiones.
        y = float(np.clip(zero_scene_y, scene_rect.top() + 12,
                          scene_rect.bottom() - 12))
        self.channel_marker.setPos(scene_rect.left() - 27, y)

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
        if hasattr(self, "channel_marker"):
            self._update_channel_marker()
        if hasattr(self, "cursor_lines"):
            self._refresh_cursors()

    def _update_time_reference(self):
        total_time = (
            self.time_per_division * self.horizontal_divisions
        )

        trigger_time = (
            self.horizontal_position
            + self.trigger_position * total_time
        )

        self.trigger_vertical_line.setValue(trigger_time)

    def _on_horizontal_reference_dragged(self, line):
        """Convierte la posición temporal arrastrada a divisiones."""
        total_time = self.time_per_division * self.horizontal_divisions
        if total_time <= 0:
            return
        fraction = (float(line.value()) - self.horizontal_position) / total_time
        fraction = float(np.clip(fraction, 0.0, 1.0))
        divisions = round((fraction - 0.5) * self.horizontal_divisions, 2)
        # Se limita la línea inmediatamente y el controlador sincroniza
        # la perilla y el recorte de adquisición.
        self.trigger_vertical_line.setValue(
            self.horizontal_position + fraction * total_time
        )
        self.horizontal_position_changed.emit(divisions)

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

        self._cursor_signal_x = time_axis.copy()
        self._cursor_signal_y = np.asarray(signal, dtype=float).copy()
        self.curve.setData(time_axis, signal)
        self._refresh_cursors()

    def clear_signal(self):
        """Limpia la traza conservando escalas y referencias."""
        self._cursor_signal_x = np.array([], dtype=float)
        self._cursor_signal_y = np.array([], dtype=float)
        self.curve.setData([], [])
        self._refresh_cursors()

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

    # ================================================================
    # CURSORES: MANUAL (TIEMPO/TENSIÓN) Y TRACK (SOBRE CH1)
    # ================================================================

    def _create_cursors(self):
        self.cursor_lines = []
        colors = ('#33d6e8', '#ffad4d')
        for index, color in enumerate(colors):
            line = pg.InfiniteLine(
                pos=0.0, angle=90, movable=True,
                pen=pg.mkPen(color, width=1.5, style=Qt.PenStyle.DashLine),
                hoverPen=pg.mkPen(color, width=3),
            )
            line.setZValue(25)
            line.setToolTip(f'Cursor {index + 1}: arrastrá para medir')
            self.plot_widget.addItem(line, ignoreBounds=True)
            line.sigPositionChanged.connect(self._refresh_cursors)
            self.cursor_lines.append(line)
        self.cursor_points = []
        for color in colors:
            point = pg.ScatterPlotItem(size=12, brush=pg.mkBrush(color),
                                       pen=pg.mkPen('#181818', width=1.5))
            point.setZValue(29)
            self.plot_widget.addItem(point, ignoreBounds=True)
            self.cursor_points.append(point)
        self._cursor_positions = [0.3, 0.7]
        self._cursor_initialized = False
        self._refresh_cursors()

    def set_cursor_mode(self, mode, orientation='Tiempo'):
        if mode not in ('Off', 'Manual', 'Track'):
            return
        if orientation not in ('Tiempo', 'Tensión'):
            return
        was_off = self.cursor_mode == 'Off'
        self.cursor_mode = mode
        self.cursor_orientation = orientation
        if was_off and mode != 'Off':
            self._cursor_initialized = False
        self._refresh_cursors()

    def _refresh_cursors(self, *args):
        if self._cursor_updating or not hasattr(self, 'cursor_lines'):
            return
        self._cursor_updating = True
        try:
            mode = self.cursor_mode
            is_voltage = mode == 'Manual' and self.cursor_orientation == 'Tensión'
            xmin, xmax = self.plot_widget.getViewBox().viewRange()[0]
            ymin, ymax = self.plot_widget.getViewBox().viewRange()[1]
            if not self._cursor_initialized and mode != 'Off':
                for i, line in enumerate(self.cursor_lines):
                    fraction = self._cursor_positions[i]
                    line.setValue(ymin + fraction * (ymax-ymin) if is_voltage
                                  else xmin + fraction * (xmax-xmin))
                self._cursor_initialized = True
            values = []
            for i, line in enumerate(self.cursor_lines):
                line.setVisible(mode != 'Off')
                line.setAngle(0 if is_voltage else 90)
                lo, hi = (ymin, ymax) if is_voltage else (xmin, xmax)
                value = float(np.clip(line.value(), lo, hi))
                if abs(value - float(line.value())) > 1e-12:
                    line.setValue(value)
                values.append(value)
                self.cursor_points[i].setVisible(mode == 'Track')
            if mode == 'Off':
                result = 'Cursores desactivados'
            elif is_voltage:
                a, b = values
                result = (f'C1: {a:+.6g} V    C2: {b:+.6g} V\n'
                          f'ΔV: {b-a:+.6g} V  |ΔV|: {abs(b-a):.6g} V')
            elif mode == 'Manual':
                a, b = values
                dt = b-a
                result = (f'C1: {a:.6g} s    C2: {b:.6g} s\n'
                          f'Δt: {dt:+.6g} s  |Δt|: {abs(dt):.6g} s')
                if abs(dt) > 1e-15:
                    result += f'    1/|Δt|: {1/abs(dt):.6g} Hz'
            else:
                x = self._cursor_signal_x
                y = self._cursor_signal_y
                if x.size < 2 or y.size != x.size:
                    result = 'Track: esperando muestras de CH1'
                    for point in self.cursor_points:
                        point.setData([], [])
                else:
                    # Interpolación lineal: valores en coordenadas físicas.
                    samples = []
                    for i, t in enumerate(values):
                        if x[0] <= t <= x[-1]:
                            v = float(np.interp(t, x, y))
                            self.cursor_points[i].setData([t], [v])
                            samples.append(v)
                        else:
                            self.cursor_points[i].setData([], [])
                            samples.append(None)
                    if all(v is not None for v in samples):
                        a, b = values
                        va, vb = samples
                        result = (f'C1: t={a:.6g} s, V={va:+.6g} V\n'
                                  f'C2: t={b:.6g} s, V={vb:+.6g} V\n'
                                  f'Δt={b-a:+.6g} s   ΔV={vb-va:+.6g} V')
                    else:
                        result = 'Track: cursor fuera del tramo adquirido'
            self.cursor_readout_changed.emit(result)
        finally:
            self._cursor_updating = False