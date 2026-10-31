"""Grilla de 12 × 8 divisiones para el osciloscopio PySide6/pyqtgraph."""

from PySide6.QtCore import QPointF, QRectF
from PySide6.QtGui import QColor, QPen
from PySide6.QtWidgets import QGraphicsObject


class OscilloscopeGrid(QGraphicsObject):
    """Dibuja una grilla con tema, visibilidad e intensidad configurables."""

    def __init__(self, horizontal_divisions=12, vertical_divisions=8, subdivisions=5):
        super().__init__()
        if horizontal_divisions < 1 or vertical_divisions < 1:
            raise ValueError("La cantidad de divisiones debe ser positiva")

        if subdivisions < 1:
            raise ValueError("La cantidad de subdivisiones debe ser positiva")
        self.subdivisions = int(subdivisions)
        self.subgrid_intensity_ratio = 0.25
        self.horizontal_divisions = int(horizontal_divisions)
        self.vertical_divisions = int(vertical_divisions)
        self.grid_color = "#526B88"
        self.center_color = "#8DA7C5"
        self.subgrid_color = "#526B88"
        self.grid_enabled = True
        self.grid_intensity = 0.5
        self._rect = QRectF(0, 0, 1, 1)

        # Positiva respecto del fondo; la traza se coloca en Z=5.
        self.setZValue(1)

    def boundingRect(self):
        return self._rect

    def set_rect(self, rect):
        rect = QRectF(rect).normalized()
        if rect == self._rect:
            return
        self.prepareGeometryChange()
        self._rect = rect
        self.update()

    def set_theme(self, theme):
        if theme == "dark":
            self.grid_color = "#526B88"
            self.center_color = "#8DA7C5"
            self.subgrid_color = "#526B88"
        elif theme == "light":
            self.grid_color = "#B4C2D3"
            self.center_color = "#7C91A9"
            self.subgrid_color = "#8FA3BA"
        else:
            raise ValueError(f"Tema de grilla desconocido: {theme}")
        self.update()

    def set_grid_enabled(self, enabled: bool):
        self.grid_enabled = bool(enabled)
        self.update()

    def set_grid_intensity(self, intensity: float):
        self.grid_intensity = max(0.0, min(1.0, float(intensity)))
        self.update()

    def paint(self, painter, option, widget=None):
        """Dibuja primero la subgrilla tenue y luego las divisiones principales."""
        if not self.grid_enabled or self.grid_intensity <= 0:
            return
        rect = self._rect
        if rect.width() <= 0 or rect.height() <= 0:
            return

        painter.save()
        try:
            painter.setRenderHint(painter.RenderHint.Antialiasing, False)

            # Subgrilla: líneas entre las divisiones principales.
            painter.setOpacity(self.grid_intensity * self.subgrid_intensity_ratio)
            minor_pen = QPen(QColor(self.subgrid_color))
            minor_pen.setWidthF(1.0)
            minor_pen.setCosmetic(True)
            painter.setPen(minor_pen)

            for i in range(1, self.horizontal_divisions * self.subdivisions):
                if i % self.subdivisions == 0:
                    continue
                x = rect.left() + rect.width() * i / (self.horizontal_divisions * self.subdivisions)
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

            for j in range(1, self.vertical_divisions * self.subdivisions):
                if j % self.subdivisions == 0:
                    continue
                y = rect.top() + rect.height() * j / (self.vertical_divisions * self.subdivisions)
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))

            # Grilla principal y ejes centrales más destacados.
            painter.setOpacity(self.grid_intensity)
            for i in range(1, self.horizontal_divisions):
                x = rect.left() + rect.width() * i / self.horizontal_divisions
                center = i == self.horizontal_divisions // 2
                pen = QPen(QColor(self.center_color if center else self.grid_color))
                pen.setWidthF(1.5 if center else 1.0)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.drawLine(QPointF(x, rect.top()), QPointF(x, rect.bottom()))

            for j in range(1, self.vertical_divisions):
                y = rect.top() + rect.height() * j / self.vertical_divisions
                center = j == self.vertical_divisions // 2
                pen = QPen(QColor(self.center_color if center else self.grid_color))
                pen.setWidthF(1.5 if center else 1.0)
                pen.setCosmetic(True)
                painter.setPen(pen)
                painter.drawLine(QPointF(rect.left(), y), QPointF(rect.right(), y))
        finally:
            painter.restore()
