"""Dos zonas concéntricas, un único valor de posición en divisiones."""
from math import cos, sin, radians, hypot
from PySide6.QtCore import Qt, QPointF, QRectF
from PySide6.QtGui import QColor, QPainter, QPen
from gui.widgets.drag_knob import DragKnob


class PositionKnob(DragKnob):
    def __init__(self, minimum=-4.0, maximum=4.0, initial=0.0,
                 accent_color='#FFD54A', size=64, parent=None):
        self._accent = QColor(accent_color)
        self._hover_zone = None
        self._active_zone = None
        self._motion_remainder = 0.0
        self._wheel_zone = None
        super().__init__(minimum=minimum, maximum=maximum, step=0.01,
                         initial=initial, reset_value=0.0, pixels_per_step=3.0,
                         size=size, parent=parent)
        self.setMouseTracking(True)
        self.setAccessibleName('Posición: ajuste grueso exterior y fino interior')
        self._update_hint()

    def _zone_at(self, point):
        r = hypot(point.x()-self.width()/2, point.y()-self.height()/2)
        if r > min(self.width(), self.height())/2-3:
            return None
        return 'fine' if r <= min(self.width(), self.height())*.29 else 'coarse'

    def _update_hint(self):
        zone = self._active_zone or self._hover_zone
        label = {'fine':'Ajuste fino: 0,01 div', 'coarse':'Ajuste grueso: 0,1 div'}.get(zone, 'Exterior: grueso · Interior: fino')
        self.setToolTip(label+'\nArrastrá arriba/abajo. Rueda con foco.\nFlechas: fino · RePág/AvPág: grueso · Inicio o doble clic: cero.')
        self.update()

    def _apply_steps(self, steps, zone):
        tick_step = 10 if zone == 'coarse' else 1
        requested = self.value()+steps*tick_step
        self.setValue(max(self.minimum(), min(self.maximum(), requested)))
        return requested <= self.minimum() or requested >= self.maximum()

    def mousePressEvent(self, event):
        zone = self._zone_at(event.position())
        if event.button() == Qt.MouseButton.LeftButton and zone and self.isEnabled():
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self._dragging = True
            self._active_zone = zone
            self._last_y = event.globalPosition().y()
            self._motion_remainder = 0.0
            self._update_hint()
            event.accept()
        else:
            event.ignore()

    def mouseMoveEvent(self, event):
        if self._dragging:
            dy = self._last_y-event.globalPosition().y()
            self._last_y = event.globalPosition().y()
            self._motion_remainder += dy/self._pixels_per_step
            steps = int(self._motion_remainder)
            if steps:
                self._motion_remainder -= steps
                if self._apply_steps(steps, self._active_zone):
                    self._motion_remainder = 0.0
            # El movimiento hacia fuera del límite no se acumula.
            if ((self.value()==self.maximum() and self._motion_remainder>0)
                    or (self.value()==self.minimum() and self._motion_remainder<0)):
                self._motion_remainder=0.0
            event.accept()
        else:
            self._hover_zone = self._zone_at(event.position())
            self._update_hint()
            event.accept()

    def mouseReleaseEvent(self, event):
        if event.button()==Qt.MouseButton.LeftButton:
            self._dragging=False
            self._active_zone=None
            self._hover_zone=self._zone_at(event.position())
            self._motion_remainder=0.0
            self._update_hint()
            event.accept()
        else:event.ignore()

    def mouseDoubleClickEvent(self, event):
        if event.button()==Qt.MouseButton.LeftButton and self._zone_at(event.position()):
            self._active_zone=None
            self._motion_remainder=0.0
            self._wheel_remainder=0.0
            super().mouseDoubleClickEvent(event)
            self._update_hint()
        else:event.ignore()

    def leaveEvent(self,event):
        self._hover_zone=None
        self._update_hint()
        super().leaveEvent(event)

    def wheelEvent(self,event):
        zone=self._zone_at(event.position())
        if not self.hasFocus() or not self.isEnabled() or zone is None:
            event.ignore()
            return
        if zone!=self._wheel_zone:
            self._wheel_remainder=0.0
            self._wheel_zone=zone
        self._wheel_remainder=getattr(self,'_wheel_remainder',0.0)+event.angleDelta().y()/120.0
        steps=int(self._wheel_remainder)
        self._wheel_remainder-=steps
        if steps and self._apply_steps(steps,zone):self._wheel_remainder=0.0
        event.accept()

    def keyPressEvent(self,event):
        key=event.key()
        if key==Qt.Key.Key_Home:self.setValue(self._value_to_tick(0.0))
        elif key in (Qt.Key.Key_Up,Qt.Key.Key_Right):self._apply_steps(1,'fine')
        elif key in (Qt.Key.Key_Down,Qt.Key.Key_Left):self._apply_steps(-1,'fine')
        elif key==Qt.Key.Key_PageUp:self._apply_steps(1,'coarse')
        elif key==Qt.Key.Key_PageDown:self._apply_steps(-1,'coarse')
        else:
            super().keyPressEvent(event)
            return
        event.accept()

    def paintEvent(self,event):
        p=QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        c=QPointF(self.width()/2,self.height()/2)
        radius=min(self.width(),self.height())/2-5
        dark=self.palette().window().color().lightness()<128
        accent=QColor(self._accent)
        if not dark:accent=accent.darker(160)
        if not self.isEnabled():p.setOpacity(.38)
        outer=QColor('#243246' if dark else '#d4dce7')
        inner=QColor('#41516a' if dark else '#f5f7fb')
        border=QColor('#718199' if dark else '#7f8da1')
        zone=self._active_zone or self._hover_zone
        p.setPen(QPen(accent if zone=='coarse' else border,2 if zone=='coarse' else 1))
        p.setBrush(outer)
        p.drawEllipse(c,radius,radius)
        # Arco del valor y una marca inequívoca de cero arriba.
        value=self.numeric_value()
        bound=(self._minimum_value+self.maximum()*self._step) if value>=0 else abs(self._minimum_value)
        angle=135*value/bound if bound else 0
        p.setPen(QPen(accent,2.5,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        arc=QRectF(c.x()-radius+3,c.y()-radius+3,2*radius-6,2*radius-6)
        p.drawArc(arc,90*16,round(-angle*16))
        p.drawLine(QPointF(c.x(),3),QPointF(c.x(),8))
        inner_radius=min(self.width(),self.height())*.29
        p.setPen(QPen(accent if zone=='fine' else border,2 if zone=='fine' else 1))
        p.setBrush(inner)
        p.drawEllipse(c,inner_radius,inner_radius)
        theta=radians(angle-90)
        p.setPen(QPen(accent,3,Qt.PenStyle.SolidLine,Qt.PenCapStyle.RoundCap))
        p.drawLine(QPointF(c.x()+cos(theta)*5,c.y()+sin(theta)*5),
                   QPointF(c.x()+cos(theta)*(inner_radius-4),c.y()+sin(theta)*(inner_radius-4)))
        p.setBrush(accent);p.setPen(Qt.PenStyle.NoPen)
        p.drawEllipse(c,2,2)
        if self.hasFocus():
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.setPen(QPen(accent,1,Qt.PenStyle.DotLine))
            p.drawRoundedRect(QRectF(1,1,self.width()-2,self.height()-2),6,6)


class LevelKnob(PositionKnob):
    """Nivel de trigger: aspecto común, resolución adaptada al rango visible."""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.setAccessibleName("Nivel de trigger: ajuste grueso exterior y fino interior")

    def _update_hint(self):
        zone = self._active_zone or self._hover_zone
        factor = 10 if zone == "coarse" else 1
        step = getattr(self, "_step", 0.0) * factor
        label = "Grueso" if zone == "coarse" else "Fino"
        self.setToolTip(
            f"Nivel: {self.numeric_value():+.6g} V\n"
            f"{label}: {step:.6g} V por paso\n"
            "Exterior: grueso · Interior: fino\n"
            "Arrastrá arriba/abajo. Rueda con foco. Doble clic: 0 V."
        )
        self.update()

    def configure_range(self, minimum, maximum, step, value):
        super().configure_range(minimum, maximum, step, value)
        self._update_hint()
