"""Perilla reutilizable con arrastre vertical y rango configurable."""

from math import isfinite

from PySide6.QtCore import Qt, Signal, QSignalBlocker
from PySide6.QtWidgets import QDial


class DragKnob(QDial):

    # Valor expresado en las unidades configuradas.
    value_changed = Signal(float)

    def __init__(
        self,
        minimum=0.0,
        maximum=100.0,
        step=1.0,
        initial=0.0,
        reset_value=None,
        pixels_per_step=5.0,
        size=90,
        parent=None,
    ):
        super().__init__(parent)

        pixels_per_step = float(pixels_per_step)

        if not isfinite(pixels_per_step) or pixels_per_step <= 0:
            raise ValueError(
                "pixels_per_step debe ser un número positivo."
            )

        self._pixels_per_step = pixels_per_step

        self._reset_value = float(
            initial if reset_value is None else reset_value
        )

        if not isfinite(self._reset_value):
            raise ValueError("El valor de reinicio debe ser finito.")

        self._dragging = False
        self._start_y = 0.0
        self._start_tick = 0

        self.setSingleStep(1)
        self.setPageStep(1)

        self.setWrapping(False)
        self.setNotchesVisible(True)
        self.setFixedSize(size, size)

        self.setCursor(Qt.CursorShape.SizeVerCursor)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)

        self.setToolTip(
            "Arrastrá hacia arriba o abajo para ajustar.\n"
            "Doble clic para restablecer el valor."
        )

        self.configure_range(
            minimum=minimum,
            maximum=maximum,
            step=step,
            value=initial,
        )

        self.valueChanged.connect(self._emit_value)

    # ================================================================
    # CONVERSIÓN ENTRE PASOS INTERNOS Y VALOR NUMÉRICO
    # ================================================================

    def numeric_value(self):
        """Devuelve el valor en las unidades configuradas."""

        return (
            self._minimum_value
            + self.value() * self._step
        )

    def _value_to_tick(self, value):
        value = float(value)

        if not isfinite(value):
            raise ValueError("El valor debe ser finito.")

        tick = round(
            (value - self._minimum_value) / self._step
        )

        return max(
            self.minimum(),
            min(self.maximum(), tick),
        )

    def _emit_value(self, _tick):
        self.value_changed.emit(self.numeric_value())

    # ================================================================
    # ACTUALIZACIÓN DESDE EL CONTROLADOR
    # ================================================================

    def set_value(self, value):
        """Actualiza la perilla sin emitir una nueva orden."""

        blocker = QSignalBlocker(self)

        try:
            self.setValue(self._value_to_tick(value))
        finally:
            del blocker

    def configure_range(self, minimum, maximum, step, value):
        """Cambia el rango y la resolución sin emitir señales.

        El paso solicitado se ajusta ligeramente, si es necesario,
        para que los extremos del rango sean representables.
        """

        minimum = float(minimum)
        maximum = float(maximum)
        step = float(step)
        value = float(value)

        if not all(
            isfinite(number)
            for number in (minimum, maximum, step, value)
        ):
            raise ValueError("Los parámetros deben ser finitos.")

        if maximum <= minimum:
            raise ValueError(
                "El máximo debe ser mayor que el mínimo."
            )

        if step <= 0:
            raise ValueError("El paso debe ser mayor que cero.")

        tick_count = (maximum - minimum) / step

        if not isfinite(tick_count):
            raise ValueError("El rango requiere demasiados pasos.")

        ticks = max(1, round(tick_count))

        # QDial representa sus posiciones mediante enteros de Qt.
        if ticks > 2_147_483_647:
            raise ValueError("El rango requiere demasiados pasos.")

        blocker = QSignalBlocker(self)

        try:
            self._minimum_value = minimum
            self._step = (maximum - minimum) / ticks

            self.setRange(0, ticks)
            self.setValue(self._value_to_tick(value))

        finally:
            del blocker

    # ================================================================
    # ARRASTRE VERTICAL
    # ================================================================

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()

            self._dragging = True
            self._start_y = event.globalPosition().y()
            self._start_tick = self.value()

            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            movement = (
                self._start_y - event.globalPosition().y()
            )

            steps = round(
                movement / self._pixels_per_step
            )

            self.setValue(self._start_tick + steps)

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

            event.accept()
            return

        super().mouseReleaseEvent(event)

    # ================================================================
    # DOBLE CLIC PARA RESTABLECER
    # ================================================================

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False

            # Aquí sí se emite el cambio porque es una acción
            # del usuario. Si el valor queda fuera del rango,
            # se utiliza el extremo más cercano.
            self.setValue(
                self._value_to_tick(self._reset_value)
            )

            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    # ================================================================
    # RUEDA DEL MOUSE
    # ================================================================

    def wheelEvent(self, event):

        delta = event.angleDelta().y()

        if delta == 0:
            event.ignore()
            return

        # Cantidad de pasos de la rueda.
        steps = delta / 120.0

        # Acumular desplazamientos de ruedas de alta resolución.
        self._wheel_remainder = (
            getattr(self, "_wheel_remainder", 0.0) + steps
        )

        whole_steps = int(self._wheel_remainder)
        self._wheel_remainder -= whole_steps

        if whole_steps:
            self.setValue(
                self.value() + whole_steps
            )

        event.accept()