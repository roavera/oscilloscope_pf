"""Bienvenida neón animada. Compatible con MainWindow: start_requested.

No requiere imágenes ni bibliotecas adicionales fuera de PySide6.
Las ondas son decorativas; no representan datos adquiridos.
"""
from __future__ import annotations

import math
from PySide6.QtCore import Qt, QTimer, Signal, QRectF, QElapsedTimer
from PySide6.QtGui import (QColor, QFont, QFontMetricsF, QPainter, QPainterPath,
                          QPen, QLinearGradient)
from PySide6.QtWidgets import QWidget, QPushButton


class WelcomePage(QWidget):
    start_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName('welcomePage')
        self.setMinimumSize(540, 360)
        self.setAttribute(Qt.WidgetAttribute.WA_OpaquePaintEvent)
        self.phase = 0.0
        self.speed = 5.2  # radianes por segundo; independiente de los FPS
        self._clock = QElapsedTimer()
        self._clock.start()
        self._last_ns = self._clock.nsecsElapsed()
        self.timer = QTimer(self)
        self.timer.setTimerType(Qt.TimerType.PreciseTimer)
        self.timer.setInterval(16)  # objetivo aproximado: 60 FPS
        self.timer.timeout.connect(self._animate)
        self.timer.start()

        # Botón real sobre el dibujo, centrado en la zona inferior.
        self.start_button = QPushButton('▶   INICIAR OSCILOSCOPIO', self)
        self.start_button.setObjectName('startButton')
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.clicked.connect(self.start_requested.emit)
        self.start_button.setStyleSheet('''
            QPushButton#startButton {
                color: #F2FBFF; background: rgba(3, 27, 57, 235);
                border: 3px solid #00F0FF; border-radius: 28px;
                font-family: 'Segoe UI'; font-size: 19px; font-weight: 800;
            }
            QPushButton#startButton:hover {
                background: rgba(5, 78, 119, 240); border-color: #A9FFFF;
            }
            QPushButton#startButton:pressed { background: #08618D; }
        ''')
        self._font_cache_width = None
        self._title_font = None
        self._subtitle_font = None
        self._layout_button()

    def _animate(self):
        now_ns = self._clock.nsecsElapsed()
        dt = min((now_ns - self._last_ns) / 1_000_000_000, 0.05)
        self._last_ns = now_ns
        if self.isVisible():
            self.phase = (self.phase + self.speed * dt) % (2 * math.pi)
            self.update()

    def _layout_button(self):
        w, h = self.width(), self.height()
        bw = min(510, max(300, int(w * .37)))
        bh = max(52, min(78, int(h * .105)))
        self.start_button.setGeometry((w - bw) // 2, int(h * .78) - bh // 2, bw, bh)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._layout_button()
        self._font_cache_width = None

    def _fonts_for_width(self, w):
        if self._font_cache_width == w:
            return self._title_font, self._subtitle_font
        title = 'OSCILOSCOPIO'
        title_font = QFont('Arial', 100, QFont.Weight.Black)
        title_font.setLetterSpacing(QFont.SpacingType.PercentageSpacing, 100)
        while (QFontMetricsF(title_font).horizontalAdvance(title) > w * .78
               and title_font.pointSize() > 20):
            title_font.setPointSize(title_font.pointSize() - 1)
        subtitle = 'SISTEMA DE ADQUISICIÓN Y VISUALIZACIÓN DE SEÑALES'
        sub_font = QFont('Segoe UI', max(8, min(16, int(w / 95))), QFont.Weight.DemiBold)
        sub_font.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 2)
        while (QFontMetricsF(sub_font).horizontalAdvance(subtitle) > w * .90
               and sub_font.pointSize() > 7):
            sub_font.setPointSize(sub_font.pointSize() - 1)
        self._font_cache_width = w
        self._title_font = title_font
        self._subtitle_font = sub_font
        return title_font, sub_font

    @staticmethod
    def _glow_path(p, path, rgb, core=2.8):
        color = QColor(rgb)
        for width, alpha in ((15, 18), (7, 65), (core, 255)):
            c = QColor(color)
            c.setAlpha(alpha)
            p.setPen(QPen(c, width, Qt.PenStyle.SolidLine,
                          Qt.PenCapStyle.RoundCap, Qt.PenJoinStyle.RoundJoin))
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawPath(path)

    def _wave(self, p, kind, y, amp, period, color, offset=0.0):
        w = self.width()
        path = QPainterPath()
        dx = 5
        for x in range(-dx, w + dx + 1, dx):
            theta = 2 * math.pi * x / period - self.phase + offset
            if kind == 'sine':
                value = math.sin(theta)
            elif kind == 'square':
                value = 1 if math.sin(theta) >= 0 else -1
            else:
                value = (2 / math.pi) * math.asin(math.sin(theta))
            py = y - amp * value
            if x == -dx:
                path.moveTo(x, py)
            else:
                # Para onda cuadrada, salto vertical limpio (sin diagonales).
                if kind == 'square' and x > -dx:
                    prev = math.sin(2 * math.pi * (x-dx) / period - self.phase + offset)
                    prev_val = 1 if prev >= 0 else -1
                    if prev_val != value:
                        path.lineTo(x, y - amp * prev_val)
                path.lineTo(x, py)
        self._glow_path(p, path, color)

    @staticmethod
    def _centered_text(p, text, cx, baseline, font, color, glow=None):
        p.setFont(font)
        fm = QFontMetricsF(font)
        x = cx - fm.horizontalAdvance(text) / 2
        if glow:
            for shift, alpha in ((4, 30), (2, 65)):
                c = QColor(glow)
                c.setAlpha(alpha)
                p.setPen(c)
                for ox, oy in ((-shift, 0), (shift, 0), (0, -shift), (0, shift)):
                    p.drawText(int(x + ox), int(baseline + oy), text)
        p.setPen(QColor(color))
        p.drawText(int(x), int(baseline), text)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing, True)
        w, h = self.width(), self.height()
        p.fillRect(self.rect(), QColor('#030C1C'))
        if w < 2 or h < 2:
            p.end()
            return

        # Grilla de pantalla completa, con divisiones mayores.
        step = max(34, int(w / 30))
        p.setPen(QPen(QColor(14, 73, 112, 105), 1))
        for x in range(0, w + step, step):
            p.drawLine(x, 0, x, h)
        for y in range(0, h + step, step):
            p.drawLine(0, y, w, y)
        p.setPen(QPen(QColor(23, 93, 139, 45), 1))
        for x in range(0, w + step, step * 5):
            p.drawLine(x, 0, x, h)
        for y in range(0, h + step, step * 5):
            p.drawLine(0, y, w, y)

        # Tres ondas animadas a lo ancho de la pantalla.
        period = max(220, w * .275)
        self._wave(p, 'sine', h * .18, h * .075, period, '#1DF5FF', .5)
        self._wave(p, 'square', h * .58, h * .06, period * .79, '#FF31CE', .8)
        self._wave(p, 'triangle', h * .87, h * .095, period * .87, '#B46CFF', .4)

        # Velo oscuro central: legibilidad sin tapar las ondas del fondo.
        gradient = QLinearGradient(0, h * .25, 0, h * .80)
        gradient.setColorAt(0, QColor(3, 10, 26, 0))
        gradient.setColorAt(.25, QColor(3, 10, 26, 170))
        gradient.setColorAt(.68, QColor(3, 10, 26, 150))
        gradient.setColorAt(1, QColor(3, 10, 26, 0))
        p.fillRect(QRectF(0, h * .25, w, h * .55), gradient)

        # Ornamentos y trazo de pulso sobre el título.
        cx = w / 2
        title_y = h * .48
        pulse = QPainterPath()
        px, py = cx - 100, h * .30
        pulse.moveTo(px, py)
        for dx, dy in ((65, 0), (75, -15), (90, 20), (107, -52),
                       (126, 28), (142, 0), (200, 0)):
            pulse.lineTo(px + dx, py + dy)
        self._glow_path(p, pulse, '#24F6FF', 2.5)

        # Título ajustado al ancho real con métricas de fuente (no tamaño fijo).
        title = 'OSCILOSCOPIO'
        title_font, sub_font = self._fonts_for_width(w)
        self._centered_text(p, title, cx, title_y, title_font, '#A9FCFF', '#00EFFF')

        # Esquinas violetas que enmarcan el título.
        tw = QFontMetricsF(title_font).horizontalAdvance(title)
        left = cx - tw / 2 - 28
        right = cx + tw / 2 + 28
        top = title_y - QFontMetricsF(title_font).ascent() * .9
        bottom = title_y + 6
        for x, direction in ((left, 1), (right, -1)):
            corner = QPainterPath()
            corner.moveTo(x + 55 * direction, top)
            corner.lineTo(x + 12 * direction, top)
            corner.quadTo(x, top, x, top + 12)
            corner.lineTo(x, bottom - 10)
            self._glow_path(p, corner, '#A16BFF', 2)

        subtitle = 'SISTEMA DE ADQUISICIÓN Y VISUALIZACIÓN DE SEÑALES'
        self._centered_text(p, subtitle, cx, h * .55, sub_font, '#E5F3FF')
        underline = QPainterPath()
        underline.moveTo(cx - min(155, w * .13), h * .585)
        underline.lineTo(cx + min(155, w * .13), h * .585)
        self._glow_path(p, underline, '#24F6FF', 2)

        # Autor con nombre fucsia.
        author_font = QFont('Segoe UI', max(11, min(22, int(w / 70))))
        p.setFont(author_font)
        fm = QFontMetricsF(author_font)
        first, second = 'Desarrollado por ', 'Rocío'
        tx = cx - (fm.horizontalAdvance(first) + fm.horizontalAdvance(second)) / 2
        ay = h * .70
        p.setPen(QColor('#ECF4FF'))
        p.drawText(int(tx), int(ay), first)
        p.setPen(QColor('#FF39D5'))
        p.drawText(int(tx + fm.horizontalAdvance(first)), int(ay), second)

        # Halo bajo el botón real, sin bloquear sus clics.
        br = self.start_button.geometry()
        halo = QPainterPath()
        halo.addRoundedRect(QRectF(br.adjusted(-2, -2, 2, 2)), 30, 30)
        self._glow_path(p, halo, '#00F0FF', 2)
        p.end()
