"""Ícono original del osciloscopio. Dibujado con Qt, sin archivos externos."""
from __future__ import annotations

import math

from PySide6.QtCore import QRectF, Qt
from PySide6.QtGui import QColor, QIcon, QPainter, QPainterPath, QPen, QPixmap


def create_oscilloscope_icon() -> QIcon:
    """Pantalla oscura con cuadrícula y onda cian, en tamaños de Windows/Qt."""
    icon = QIcon()
    for size in (16, 24, 32, 48, 64, 96, 128, 256):
        pixmap = QPixmap(size, size)
        pixmap.fill(Qt.GlobalColor.transparent)
        p = QPainter(pixmap)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        p.scale(size / 128.0, size / 128.0)

        p.setPen(QPen(QColor("#4B7193"), 3))
        p.setBrush(QColor("#101D30"))
        p.drawRoundedRect(QRectF(5, 5, 118, 118), 22, 22)

        p.save()
        p.setClipRect(QRectF(13, 13, 102, 102))
        p.setPen(QPen(QColor(53, 93, 125, 130), 1.3))
        for coordinate in (32, 64, 96):
            p.drawLine(coordinate, 14, coordinate, 114)
            p.drawLine(14, coordinate, 114, coordinate)
        p.setPen(QPen(QColor("#58778E"), 1.7))
        p.drawLine(14, 64, 114, 64)

        wave = QPainterPath()
        for x in range(14, 115):
            y = 64 - 31 * math.sin((x - 14) * math.pi / 41.0)
            if x == 14:
                wave.moveTo(x, y)
            else:
                wave.lineTo(x, y)
        p.setPen(QPen(QColor(17, 173, 204, 85), 11, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(wave)
        p.setPen(QPen(QColor("#5CF9FF"), 5, Qt.PenStyle.SolidLine,
                      Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
        p.drawPath(wave)
        p.restore()
        p.end()
        icon.addPixmap(pixmap)
    return icon
