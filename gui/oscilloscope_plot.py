# CONTROL_HORIZONTAL_COMPLETO_V1
"""Visualización de señales y ajuste gráfico del nivel de trigger."""

import numpy as np
import pyqtgraph as pg

from PySide6.QtCore import Signal, QRectF, Qt, QPointF
from PySide6.QtGui import QColor, QBrush, QPen, QPolygonF
from PySide6.QtWidgets import QGraphicsObject, QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSizePolicy

from .theme.colors import PLOT_COLORS
from .oscilloscope_grid import OscilloscopeGrid
from .display_interpolation import MODES, interpolate_display
from .timebase_readout import format_timebase_readout

class ChannelMarker(QGraphicsObject):
    """Marcador de cero de cada canal, arrastrable en divisiones."""

    def __init__(self, plot, channel=1):
        super().__init__()
        self.plot = plot
        self.channel = channel
        self.setZValue(40)
        self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton)
        self.setAcceptHoverEvents(True)
        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setToolTip(f"CH{channel} · Posición de cero. Arrastrá para mover el canal.")

    def boundingRect(self):
        return QRectF(-2, -13, 32, 26)

    def paint(self, painter, option, widget=None):
        painter.setRenderHint(painter.RenderHint.Antialiasing)
        
        color = (PLOT_COLORS[self.plot.display_theme]["ch1"]
                 if self.channel == 1 else "#38cfff")

        painter.setPen(QPen(QColor(color).darker(130), 1))
        painter.setBrush(QBrush(QColor(color)))
        
        painter.drawPolygon(QPolygonF([
            QPointF(0, -11), QPointF(28, 0), QPointF(0, 11)
        ]))
        painter.setPen(QColor("#171717"))
        painter.drawText(QRectF(1, -10, 16, 20),
                         Qt.AlignmentFlag.AlignCenter, str(self.channel))

    def mousePressEvent(self, event):
        if event.button() != Qt.MouseButton.LeftButton:
            event.ignore()
            return

        # Guardamos la referencia al inicio del arrastre. No usamos la
        # posición actual del marcador porque se mueve junto con el rango Y.
        self._drag_start_scene_y = event.scenePos().y()
        self._drag_start_divisions = (
            self.plot.channel_positions[self.channel]
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
        if self.channel == 1:
            self.plot.vertical_position_changed.emit(divisions)
        else:
            self.plot.ch2_position_changed.emit(divisions)
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
    ch2_position_changed = Signal(float)

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
        # Time/div adquirido y Time/div visible con Zoom no son equivalentes.
        self._readout_base_seconds = self.time_per_division
        self._readout_zoom = 1.0
        self._readout_delay = 0.0
        self._readout_vernier = False
        self.volts_per_division = float(volts_per_division)

        self.horizontal_position = float(horizontal_position)
        self.vertical_offset = float(vertical_offset)

        self.trigger_level = float(trigger_level)
        self.trigger_position = float(trigger_position)

        self.cursor_mode = "Off"
        self.cursor_orientation = "Tiempo"
        self.cursor_channel = 1
        self.cursor_labels_visible = True
        self._cursor_updating = False
        self._cursor_signal_x = np.array([], dtype=float)
        self._cursor_signal_y = np.array([], dtype=float)
        self.channel_scales = {1: self.volts_per_division, 2: self.volts_per_division}
        self.channel_positions = {1: -self.vertical_offset / self.volts_per_division, 2: 0.0}
        self.channel_visible = {1: True, 2: True}
        self.trigger_channel = 1
        self.roll_active = False
        self._raw_channels = None
        self._raw_envelope = None
        self.math_visible = False
        self.math_scale = 0.02
        self.math_position = 0.0
        self.math_expression = "CH1 + CH2"
        self._math_values = None
        self._math_bounds = None
        self._math_x = np.array([], dtype=float)
        self.display_theme = "dark"
        self.calibration_label = "Sin calibrar"
        self.voltage_units = False
        self.interpolation_mode = "linear"
        self.create_interface()
        self._init_fastact_overlay()
            
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

        for channel in (1, 2):
            color = QColor(colors["ch1"] if channel == 1 else "#38cfff")
            for curve in self.envelope_curves[channel]:
                curve.setPen(pg.mkPen(color, width=1.3))
            color.setAlpha(55)
            self.envelope_fills[channel].setBrush(pg.mkBrush(color))

        math_color = QColor("#c993ff" if theme_name == "dark" else "#8b36c7")
        for curve in (self.math_curve, self.math_lower, self.math_upper):
            curve.setPen(pg.mkPen(math_color, width=1.6))
        self.math_legend.setColor(math_color)
        math_color.setAlpha(45)
        self.math_fill.setBrush(pg.mkBrush(math_color))

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
        self.channel_marker_ch2.update()

        # Repintar sin cambiar escalas ni muestras.
        self.plot_widget.update()
        
        self.grid.set_theme(theme_name)
        self._style_timebase_readout()
        self._refresh_channel_curves()
        self._refresh_math()

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
        layout.setSpacing(0)  # Barra de escala pegada a la base del display.

        self.plot_widget = pg.PlotWidget()
        layout.addWidget(self.plot_widget, 1)

        # TIMEBASE_READOUT_V1: Time/div siempre visible a la derecha.
        self.timebase_strip = QWidget(self)
        self.timebase_strip.setObjectName("timebase_strip")
        strip_layout = QHBoxLayout(self.timebase_strip)
        strip_layout.setContentsMargins(10, 0, 10, 0)
        strip_layout.setSpacing(10)
        self.timebase_details = QLabel(self.timebase_strip)
        self.timebase_details.setObjectName("timebase_details")
        self.timebase_details.setAlignment(Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft)
        self.timebase_details.setMinimumWidth(0)
        self.timebase_details.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        strip_layout.addWidget(self.timebase_details, 1)
        self.timebase_readout = QLabel(self.timebase_strip)
        self.timebase_readout.setObjectName("timebase_readout")
        self.timebase_readout.setAccessibleName("Escala de tiempo del osciloscopio")
        self.timebase_readout.setAlignment(Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter)
        self.timebase_readout.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.timebase_readout.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        strip_layout.addWidget(self.timebase_readout, 0)
        self.timebase_strip.setFixedHeight(27)
        layout.addWidget(self.timebase_strip, 0)
        self._style_timebase_readout()
        self._update_timebase_readout()

        self.plot_widget.setLabel(
            "left",
            "Posición vertical",
            units="div",
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
        self.curve_ch2 = self.plot_widget.plot(pen=pg.mkPen("#38cfff", width=2))
        self.curve_ch2.setZValue(5)
        self.envelope_curves = {}
        self.envelope_fills = {}
        for channel in (1, 2):
            lower = self.plot_widget.plot()
            upper = self.plot_widget.plot()
            lower.setZValue(5)
            upper.setZValue(5)
            fill = pg.FillBetweenItem(lower, upper)
            fill.setZValue(4)
            self.plot_widget.addItem(fill)
            self.envelope_curves[channel] = (lower, upper)
            self.envelope_fills[channel] = fill
            lower.hide()
            upper.hide()
            fill.hide()
        self.math_curve = self.plot_widget.plot()
        self.math_curve.setZValue(7)
        self.math_lower = self.plot_widget.plot()
        self.math_upper = self.plot_widget.plot()
        self.math_lower.setZValue(7)
        self.math_upper.setZValue(7)
        self.math_fill = pg.FillBetweenItem(self.math_lower, self.math_upper)
        self.math_fill.setZValue(6)
        self.plot_widget.addItem(self.math_fill)
        self.math_legend = pg.TextItem(anchor=(0, 0))
        self.math_legend.setZValue(30)
        self.plot_widget.addItem(self.math_legend, ignoreBounds=True)
        self._refresh_math()
        self.channel_legend = pg.TextItem(anchor=(0, 0), color="#a8b5c8")
        self.plot_widget.addItem(self.channel_legend, ignoreBounds=True)
        self.channel_legend.setZValue(30)

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
        self.channel_marker_ch2 = ChannelMarker(self, 2)
        self.plot_widget.scene().addItem(self.channel_marker_ch2)
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
        for ch, marker in ((1, self.channel_marker), (2, self.channel_marker_ch2)):
            y = view.mapViewToScene(QPointF(0.0, self.channel_positions[ch])).y()
            y = float(np.clip(y, scene_rect.top() + 12, scene_rect.bottom() - 12))
            marker.setPos(scene_rect.left() - 27, y)
            marker.setVisible(self.channel_visible[ch])

    # ================================================================
    # RANGOS VISIBLES
    # ================================================================

    def vertical_range(self):
        half = self.vertical_divisions / 2
        return -half, half

    def _to_display(self, value, channel):
        return np.asarray(value) / self.channel_scales[channel] + self.channel_positions[channel]

    def _from_display(self, value, channel):
        return (np.asarray(value) - self.channel_positions[channel]) * self.channel_scales[channel]

    def set_math_settings(self, *, scale=None, position=None, visible=None, expression=None):
        if scale is not None:
            if not np.isfinite(scale) or scale <= 0:
                raise ValueError("Escala MATH inválida")
            self.math_scale = float(scale)
        if position is not None:
            if not np.isfinite(position):
                raise ValueError("Posición MATH inválida")
            self.math_position = float(np.clip(position, -4, 4))
        if visible is not None:
            self.math_visible = bool(visible)
        if expression is not None:
            self.math_expression = str(expression)
        self._refresh_math()

    def set_math_signal(self, values, sample_rate, trigger_sample=None):
        values = np.asarray(values, dtype=np.float32)
        if values.ndim != 1 or not np.isfinite(values).all():
            raise ValueError("MATH requiere un vector finito")
        self._math_x = self._signal_time_axis(len(values), sample_rate, trigger_sample)
        self._math_values = values.copy()
        self._math_bounds = None
        self._refresh_math()

    def set_math_envelope(self, minimum, maximum, sample_rate, trigger_sample=None, *, sample_positions=None):
        minimum, maximum = np.asarray(minimum, dtype=np.float32), np.asarray(maximum, dtype=np.float32)
        if (minimum.ndim != 1 or maximum.shape != minimum.shape
                or not np.isfinite(minimum).all() or not np.isfinite(maximum).all()
                or np.any(minimum > maximum)):
            raise ValueError("Límites de MATH inválidos")
        self._math_x = self._bounds_time_axis(len(minimum), sample_rate, trigger_sample, sample_positions)
        self._math_values = None
        self._math_bounds = minimum.copy(), maximum.copy()
        self._refresh_math()

    def clear_math(self):
        self._math_values = None
        self._math_bounds = None
        self._math_x = np.array([], dtype=float)
        for curve in (self.math_curve, self.math_lower, self.math_upper):
            curve.setData([], [])
        self._refresh_math()

    def _refresh_math(self):
        convert = lambda values: values / self.math_scale + self.math_position
        signal = self._math_values is not None and self._math_values.size > 0
        envelope = self._math_bounds is not None and self._math_bounds[0].size > 0
        if signal:
            self._draw_interpolated_curve(
                self.math_curve, self._math_x, convert(self._math_values),
                channel=1, math_trace=True,
            )
        if envelope:
            self.math_lower.setData(self._math_x, convert(self._math_bounds[0]))
            self.math_upper.setData(self._math_x, convert(self._math_bounds[1]))
        self.math_curve.setVisible(self.math_visible and signal)
        for item in (self.math_lower, self.math_upper, self.math_fill):
            item.setVisible(self.math_visible and envelope)
        unit = "V" if self.voltage_units else "u.a."
        self.math_legend.setText(
            f"MATH = {self.math_expression} · {self.math_scale:g} {unit}/div"
        )
        self.math_legend.setPos(self.horizontal_position, self.vertical_divisions/2 - 0.35)
        self.math_legend.setVisible(self.math_visible and (signal or envelope))

    def set_channel_settings(self, channel, *, scale=None, position=None, visible=None):
        if channel not in (1, 2):
            raise ValueError("Canal inválido")
        if scale is not None:
            if not np.isfinite(scale) or scale <= 0:
                raise ValueError("Escala inválida")
            self.channel_scales[channel] = float(scale)
        if position is not None:
            self.channel_positions[channel] = float(np.clip(position, -4, 4))
        if visible is not None:
            self.channel_visible[channel] = bool(visible)
        self._refresh_channel_curves()
        self.update_scales()

    def set_trigger_channel(self, channel):
        if channel not in (1, 2):
            raise ValueError("Canal inválido")
        self.trigger_channel = channel
        self.update_scales()

    def _init_fastact_overlay(self):
        """Imagen de persistencia, debajo de las curvas, sobre la grilla."""
        self.fastact_active = False
        self.fastact_image = pg.ImageItem(axisOrder="row-major")
        self.fastact_image.setZValue(4.5)  # Curvas CH1/CH2: 5; MATH: 7.
        self.fastact_image.setOpacity(0.85)
        self.plot_widget.addItem(self.fastact_image, ignoreBounds=True)
        self.fastact_image.hide()

    def set_fastact_mode(self, active):
        self.fastact_active = bool(active)
        self.fastact_image.setVisible(self.fastact_active and self.fastact_image.image is not None)
        self._refresh_channel_curves()

    def clear_fastact(self):
        self.fastact_image.setImage(np.zeros((8, 8, 4), dtype=np.uint8), autoLevels=False)
        self.fastact_image.hide()

    def set_fastact_image(self, rgba):
        rgba = np.asarray(rgba, dtype=np.uint8)
        if rgba.ndim != 3 or rgba.shape[2] != 4:
            raise ValueError("La persistencia FastAct debe ser RGBA")
        self.fastact_image.setImage(rgba, autoLevels=False)
        span = self.time_per_division * self.horizontal_divisions
        self.fastact_image.setRect(QRectF(self.horizontal_position, -4, span, 8))
        self.fastact_image.setVisible(self.fastact_active)

    def set_roll_mode(self, active):
        """Oculta los marcadores de disparo en Roll."""
        self.roll_active = bool(active)
        self.trigger_line.setVisible(not self.roll_active)
        self.trigger_vertical_line.setVisible(not self.roll_active)
        self._update_trigger_notice()
        self._refresh_channel_curves()

    def set_calibration_label(self, label, *, in_volts=False):
        self.calibration_label = str(label)
        self.voltage_units = bool(in_volts)
        self._refresh_channel_curves()
        self._refresh_math()

    def set_interpolation_mode(self, mode):
        """Selecciona el método VISUAL sin modificar las capturas ni la fs."""
        mode = str(mode)
        if mode not in MODES:
            raise ValueError(f"Interpolación desconocida: {mode}")
        if mode == self.interpolation_mode:
            return
        self.interpolation_mode = mode
        self._refresh_channel_curves()
        self._refresh_math()

    def _draw_interpolated_curve(self, curve, x, y, channel=1, *, math_trace=False):
        """Solo pyqtgraph ve estos vectores; cursores y mediciones usan RAW."""
        if math_trace:
            color = "#c993ff" if self.display_theme == "dark" else "#8b36c7"
            width = 1.6
        else:
            color = PLOT_COLORS[self.display_theme]["ch1"] if channel == 1 else "#38cfff"
            width = 2.0
        if self.interpolation_mode == "none":
            # Evita miles de objetos gráficos en escalas de tiempo grandes.
            count = len(x)
            stride = max(1, (count + 1499) // 1500)
            curve.setData(
                np.asarray(x)[::stride], np.asarray(y)[::stride],
                pen=None, symbol="o", symbolSize=4,
                symbolPen=None, symbolBrush=pg.mkBrush(color),
            )
        else:
            px, py = interpolate_display(x, y, self.interpolation_mode)
            curve.setData(
                px, py, pen=pg.mkPen(color, width=width), symbol=None,
            )

    def _refresh_channel_curves(self):
        envelope = self._raw_envelope is not None
        for ch, curve in ((1, self.curve), (2, self.curve_ch2)):
            visible = self.channel_visible[ch]
            curve.setVisible(visible and not envelope)
            if self._raw_channels is not None:
                self._draw_interpolated_curve(
                    curve, self._cursor_signal_x,
                    self._to_display(self._raw_channels[:, ch-1], ch), channel=ch,
                )
            lower, upper = self.envelope_curves[ch]
            if envelope:
                minimum, maximum = self._raw_envelope
                lower.setData(self._cursor_signal_x, self._to_display(minimum[:, ch-1], ch))
                upper.setData(self._cursor_signal_x, self._to_display(maximum[:, ch-1], ch))
            lower.setVisible(visible and envelope)
            upper.setVisible(visible and envelope)
            self.envelope_fills[ch].setVisible(visible and envelope)
        text = "   ".join(f"CH{ch}: {self.channel_scales[ch]:g}/div" +
                           ("" if self.channel_visible[ch] else " (oculto)") for ch in (1, 2))
        mode = " · " + getattr(self, "_bounds_label", "Envolvente") if envelope else ""
        self.channel_legend.setText(
            text + (" · FASTACT (persistencia)" if getattr(self, "fastact_active", False) else
                    (" · ROLL (sin trigger)" if self.roll_active else
                     f" · Trigger CH{self.trigger_channel}")) +
            f" · {self.calibration_label}" + mode
        )
        self.channel_legend.setPos(self.horizontal_position, self.vertical_divisions / 2)
        self._refresh_cursors()

    def _style_timebase_readout(self):
        """Mantiene contraste correcto en los temas día/noche."""
        if self.display_theme == "light":
            background, foreground, border = "#EAF0F7", "#243448", "#CAD5E3"
        else:
            background, foreground, border = "#111C2B", "#E5EEF9", "#34475D"
        self.timebase_strip.setStyleSheet(
            f"QWidget#timebase_strip {{ background: {background}; "
            f"border-top: 1px solid {border}; }} "
            f"QLabel#timebase_readout {{ color: {foreground}; "
            "font-family: Consolas, 'DejaVu Sans Mono', monospace; "
            "font-size: 11px; font-weight: 700; }} "
            f"QLabel#timebase_details {{ color: {foreground}; "
            "font-family: Consolas, 'DejaVu Sans Mono', monospace; "
            "font-size: 10px; }}"
        )

    def _update_timebase_readout(self):
        """Siempre informa Time/div REAL y, si hay Zoom, Time/div visible."""
        full = format_timebase_readout(
            self._readout_base_seconds,
            self._readout_zoom,
            self._readout_delay,
            vernier=self._readout_vernier,
        )
        parts = full.split("   ·   ", 1)
        # La escala adquirida queda anclada a la derecha aun con poco ancho.
        self.timebase_readout.setText(parts[0])
        self.timebase_details.setText(parts[1] if len(parts) == 2 else "")
        self.timebase_strip.setToolTip(full)

    def set_timebase_vernier_enabled(self, enabled):
        self._readout_vernier = bool(enabled)
        self._update_timebase_readout()

    def update_scales(self):
        total_time = (
            self.time_per_division * self.horizontal_divisions
        )

        self.plot_widget.setXRange(
            self.horizontal_position,
            self.horizontal_position + total_time,
            padding=0,
        )
        if hasattr(self, "fastact_image"):
            self.fastact_image.setRect(QRectF(self.horizontal_position, -4, total_time, 8))

        y_min, y_max = self.vertical_range()

        self.plot_widget.setYRange(
            y_min,
            y_max,
            padding=0,
        )

        # Cambiar la escala no modifica el umbral.
        self.trigger_line.setValue(float(self._to_display(self.trigger_level, self.trigger_channel)))

        self._update_time_reference()
        self._update_trigger_notice()
        self._refresh_channel_curves()
        self._refresh_math()
        if hasattr(self, "channel_marker"):
            self._update_channel_marker()
        if hasattr(self, "cursor_lines"):
            self._refresh_cursors()

    def _update_time_reference(self):
        total_time = (
            self.time_per_division * self.horizontal_divisions
        )

        # t=0 representa el evento. Delay mueve la ventana, no el evento.
        self.trigger_vertical_line.setValue(0.0)

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
        self.trigger_vertical_line.setValue(0.0)
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

        outside = not y_min <= self._to_display(self.trigger_level, self.trigger_channel) <= y_max

        if outside:
            self.trigger_notice.setText(
                "Trigger fuera de vista: "
                f"{self.trigger_level:+.6g} V"
            )

        self.trigger_notice.setVisible(outside and not self.roll_active)

    # ================================================================
    # ARRASTRE DEL TRIGGER
    # ================================================================

    def _on_trigger_dragged(self, line):
        y_min, y_max = self.vertical_range()

        level = float(
            np.clip(line.value(), y_min, y_max)
        )

        level = float(self._from_display(level, self.trigger_channel))
        self.set_trigger_level(level)
        self.trigger_level_changed.emit(level)

    # ================================================================
    # MOSTRAR SEÑAL
    # ================================================================

    def _signal_time_axis(self, length, sample_rate, trigger_sample=None):
        sample_rate = float(sample_rate)

        if not np.isfinite(sample_rate) or sample_rate <= 0:
            raise ValueError(
                "La frecuencia de muestreo debe ser positiva y finita."
            )

        time_axis = (
            np.arange(length, dtype=float) / sample_rate
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

            # El tiempo físico de disparo se mantiene en t=0, aun con Delay.
            time_axis -= trigger_sample / sample_rate

        else:
            # Auto sin disparo: ubica la ventana desde el borde izquierdo.
            time_axis += self.horizontal_position

        return time_axis

    def _bounds_time_axis(self, count, sample_rate, trigger_sample, positions):
        if positions is None:
            return self._signal_time_axis(count, sample_rate, trigger_sample)
        positions = np.asarray(positions, dtype=float)
        if (positions.shape != (count,) or not np.isfinite(positions).all()
                or np.any(positions < 0) or np.any(np.diff(positions) < 0)):
            raise ValueError("Posiciones temporales inválidas")
        rate = float(sample_rate)
        if not np.isfinite(rate) or rate <= 0:
            raise ValueError("Frecuencia de muestreo inválida")
        origin = self._signal_time_axis(1, rate, trigger_sample)[0]
        return origin + positions / rate

    def set_envelope(self, minimum, maximum, sample_rate, trigger_sample=None, *, sample_positions=None):
        """Representa dos límites por canal, sin inventar una traza central."""
        minimum = np.asarray(minimum, dtype=np.float32)
        maximum = np.asarray(maximum, dtype=np.float32)
        if (minimum.ndim != 2 or minimum.shape[1] != 2
                or maximum.shape != minimum.shape):
            raise ValueError("La envolvente requiere dos matrices (N, 2) iguales")
        if (not np.isfinite(minimum).all() or not np.isfinite(maximum).all()
                or np.any(minimum > maximum)):
            raise ValueError("Límites de envolvente inválidos")
        if not len(minimum):
            self.clear_signal()
            return
        time_axis = self._bounds_time_axis(len(minimum), sample_rate, trigger_sample, sample_positions)
        self._bounds_label = "Peak Detect" if sample_positions is not None else "Envolvente"
        self._raw_channels = None
        self._raw_envelope = (minimum.copy(), maximum.copy())
        self._cursor_signal_x = time_axis
        self._cursor_signal_y = np.array([], dtype=float)
        # Vaciar la traza previa: Track no puede tomar muestras de otro modo.
        self.curve.setData([], [])
        self.curve_ch2.setData([], [])
        self._refresh_channel_curves()

    def set_signal(self, signal, sample_rate, trigger_sample=None):
        """
        Muestra una ventana de muestras.

        trigger_sample es la posición del cruce dentro de esa ventana,
        expresada en muestras. Puede incluir una fracción de muestra.
        """
        if signal is None or len(signal) == 0:
            self.clear_signal()
            return

        time_axis = self._signal_time_axis(len(signal), sample_rate, trigger_sample)

        self._cursor_signal_x = time_axis.copy()
        data = np.asarray(signal, dtype=float)
        if data.ndim != 2 or data.shape[1] != 2:
            raise ValueError("Se requieren muestras (N, 2)")
        self._raw_envelope = None
        self._raw_channels = data.copy()
        self._cursor_signal_y = data[:, 0].copy()
        self._refresh_channel_curves()
        self._refresh_cursors()

    def set_roll_signal(self, samples, relative_seconds):
        """Coloca el dato nuevo a la derecha, sin trigger."""
        data = np.asarray(samples, dtype=np.float32)
        offsets = np.asarray(relative_seconds, dtype=np.float64)
        if (data.ndim != 2 or data.shape[1] != 2 or
            offsets.shape != (len(data),) or
            not np.isfinite(data).all() or not np.isfinite(offsets).all() or
            np.any(np.diff(offsets) < 0)):
            raise ValueError("Datos temporales Roll inválidos")
        if not len(data):
            self.clear_signal()
            return
        span = self.time_per_division * self.horizontal_divisions
        self._cursor_signal_x = self.horizontal_position + span + offsets
        self._cursor_signal_y = data[:, 0].copy()
        self._raw_envelope = None
        self._raw_channels = data.copy()
        self._refresh_channel_curves()
        self._refresh_cursors()

    def set_roll_math_signal(self, values, relative_seconds):
        values = np.asarray(values, dtype=np.float32)
        offsets = np.asarray(relative_seconds, dtype=np.float64)
        if (values.ndim != 1 or offsets.shape != values.shape or
            not np.isfinite(values).all() or not np.isfinite(offsets).all()):
            raise ValueError("MATH Roll inválida")
        span = self.time_per_division * self.horizontal_divisions
        self._math_x = self.horizontal_position + span + offsets
        self._math_values = values.copy()
        self._math_bounds = None
        self._refresh_math()

    def clear_signal(self):
        """Limpia las trazas conservando escalas y referencias."""
        self.clear_math()
        self._cursor_signal_x = np.array([], dtype=float)
        self._cursor_signal_y = np.array([], dtype=float)
        self._raw_channels = None
        self._raw_envelope = None
        for channel in (1, 2):
            for curve in self.envelope_curves[channel]:
                curve.setData([], [])
                curve.hide()
            self.envelope_fills[channel].hide()
        self.curve.setData([], [])
        self.curve_ch2.setData([], [])
        self._refresh_cursors()

    # ================================================================
    # ACTUALIZACIÓN DESDE EL CONTROLADOR
    # ================================================================

    def set_horizontal_view(self, acquisition_time_division, reference, delay, zoom):
        """Cambia únicamente el viewport sin reactivar el procesador/trigger."""
        base = float(acquisition_time_division)
        zoom = float(zoom)
        fraction = float(reference)
        delay = float(delay)
        if (not np.isfinite([base, zoom, fraction, delay]).all()
                or base <= 0 or zoom < 1 or not 0 <= fraction <= 1):
            raise ValueError("Vista horizontal inválida")
        self.time_per_division = base / zoom
        self.trigger_position = fraction
        span = self.time_per_division * self.horizontal_divisions
        self.horizontal_position = delay - fraction * span
        self._readout_base_seconds = base
        self._readout_zoom = zoom
        self._readout_delay = delay
        self._update_timebase_readout()
        self.update_scales()

    def set_time_per_division(self, value):
        value = float(value)

        if not np.isfinite(value) or value <= 0:
            raise ValueError(
                "Tiempo/div debe ser positivo y finito."
            )

        self.time_per_division = value
        self._readout_base_seconds = value
        self._update_timebase_readout()
        self.update_scales()

    def set_volts_per_division(self, value):
        value = float(value)

        if not np.isfinite(value) or value <= 0:
            raise ValueError(
                "Volt/div debe ser positivo y finito."
            )

        self.volts_per_division = value
        self.set_channel_settings(1, scale=value)

    def set_trigger_level(self, level):
        """Actualiza el nivel sin emitir trigger_level_changed."""
        level = float(level)

        if not np.isfinite(level):
            raise ValueError("El nivel de trigger debe ser finito.")

        self.trigger_level = level
        self.trigger_line.setValue(float(self._to_display(level, self.trigger_channel)))

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
        self.set_channel_settings(1, position=-offset / self.volts_per_division)

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
    # CURSORES: MANUAL Y TRACK SOBRE CH1 O CH2
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
        self.cursor_labels = []
        for color in colors:
            label = pg.TextItem(color=color, anchor=(0, 0),
                                fill=pg.mkBrush(21, 26, 34, 235),
                                border=pg.mkPen(color, width=0.6))
            label.setZValue(31)
            self.plot_widget.addItem(label, ignoreBounds=True)
            label.hide()
            self.cursor_labels.append(label)
        self._cursor_positions = [0.3, 0.7]
        self._cursor_initialized = False
        self._refresh_cursors()

    def set_cursor_channel(self, channel):
        if channel not in (1, 2):
            raise ValueError("La referencia de cursores debe ser CH1 o CH2")
        self.cursor_channel = int(channel)
        self._refresh_cursors()

    def set_cursor_labels_visible(self, visible):
        self.cursor_labels_visible = bool(visible)
        self._refresh_cursors()

    def set_cursor_mode(self, mode, orientation='Tiempo'):
        if mode not in ('Off', 'Manual', 'Track'):
            return
        if orientation not in ('Tiempo', 'Tensión'):
            return
        was_off = self.cursor_mode == 'Off'
        old_voltage = self.cursor_mode == 'Manual' and self.cursor_orientation == 'Tensión'
        new_voltage = mode == 'Manual' and orientation == 'Tensión'
        self.cursor_mode = mode
        self.cursor_orientation = orientation
        if (was_off and mode != 'Off') or old_voltage != new_voltage:
            self._cursor_initialized = False
        self._refresh_cursors()

    def _refresh_cursors(self, *args):
        if self._cursor_updating or not hasattr(self, 'cursor_lines'):
            return
        self._cursor_updating = True
        try:
            mode = self.cursor_mode
            channel = self.cursor_channel
            is_voltage = mode == 'Manual' and self.cursor_orientation == 'Tensión'
            xmin, xmax = self.plot_widget.getViewBox().viewRange()[0]
            ymin, ymax = self.plot_widget.getViewBox().viewRange()[1]
            # Rotar antes de ubicar: InfiniteLine cambia su coordenada activa.
            for line in self.cursor_lines:
                line.setAngle(0 if is_voltage else 90)
            if not self._cursor_initialized and mode != 'Off':
                for i, line in enumerate(self.cursor_lines):
                    fraction = self._cursor_positions[i]
                    line.setValue(ymin + fraction * (ymax-ymin) if is_voltage
                                  else xmin + fraction * (xmax-xmin))
                self._cursor_initialized = True
            values = []
            track_samples = [None, None]
            texts = []
            for i, line in enumerate(self.cursor_lines):
                line.setVisible(mode != 'Off')
                lo, hi = (ymin, ymax) if is_voltage else (xmin, xmax)
                value = float(np.clip(line.value(), lo, hi))
                if abs(value - float(line.value())) > 1e-12:
                    line.setValue(value)
                values.append(value)
                self.cursor_points[i].setVisible(mode == 'Track')
                texts.append(f'C{i+1} · t={value:.6g} s')
            if mode == 'Off':
                result = 'Cursores desactivados'
            elif is_voltage:
                a, b = [float(self._from_display(v, channel)) for v in values]
                result = (f'CH{channel} · C1: {a:+.6g} V    C2: {b:+.6g} V\n'
                          f'ΔV: {b-a:+.6g} V  |ΔV|: {abs(b-a):.6g} V')
                texts = [f'C{i+1} · CH{channel}: {v:+.6g} V' for i, v in enumerate((a, b))]
            elif mode == 'Manual':
                a, b = values
                dt = b-a
                result = (f'C1: {a:.6g} s    C2: {b:.6g} s\n'
                          f'Δt: {dt:+.6g} s  |Δt|: {abs(dt):.6g} s')
                if abs(dt) > 1e-15:
                    result += f'    1/|Δt|: {1/abs(dt):.6g} Hz'
            else:
                x = self._cursor_signal_x
                y = (self._raw_channels[:, channel-1] if self._raw_channels is not None
                     else np.array([], dtype=float))
                if x.size < 2 or y.size != x.size:
                    result = (f'Track no disponible en {getattr(self, "_bounds_label", "Envolvente")}: hay dos límites por intervalo'
                              if self._raw_envelope is not None
                              else f'Track: esperando muestras de CH{channel}')
                    for point in self.cursor_points:
                        point.setData([], [])
                else:
                    for i, t in enumerate(values):
                        if x[0] <= t <= x[-1]:
                            v = float(np.interp(t, x, y))
                            self.cursor_points[i].setData([t], [float(self._to_display(v, channel))])
                            track_samples[i] = v
                            texts[i] = f'C{i+1} · CH{channel}\nt={t:.6g} s\nV={v:+.6g} V'
                        else:
                            self.cursor_points[i].setData([], [])
                            texts[i] = f'C{i+1} · CH{channel}\nt={t:.6g} s\nFuera de captura'
                    if all(v is not None for v in track_samples):
                        a, b = values
                        va, vb = track_samples
                        result = (f'CH{channel} · C1: t={a:.6g} s, V={va:+.6g} V\n'
                                  f'C2: t={b:.6g} s, V={vb:+.6g} V\n'
                                  f'Δt={b-a:+.6g} s   ΔV={vb-va:+.6g} V')
                    else:
                        result = 'Track: cursor fuera del tramo adquirido'
            for i, label in enumerate(self.cursor_labels):
                label.setVisible(mode != 'Off' and self.cursor_labels_visible)
                label.setText(texts[i])
                if is_voltage:
                    label.setAnchor((0, 1 if values[i] < ymax-.5 else 0))
                    label.setPos(xmin+.025*(xmax-xmin), values[i])
                else:
                    right = values[i] > (xmin+xmax)/2
                    label.setAnchor((1 if right else 0, 0))
                    x_label = values[i] + (-.012 if right else .012)*(xmax-xmin)
                    if mode == 'Track' and track_samples[i] is not None:
                        y_display = float(self._to_display(track_samples[i], channel))
                        y_label = float(np.clip(y_display+.65, ymin+.9, ymax-.65))
                    else:
                        y_label = ymax-.7-.45*i
                    label.setPos(x_label, y_label)
            self.cursor_readout_changed.emit(result)
        finally:
            self._cursor_updating = False

