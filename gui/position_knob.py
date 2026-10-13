"""Perilla circular de posición con arrastre vertical."""

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QDial


class PositionKnob(QDial):
    UNITS_PER_DIVISION = 100

    def __init__(self, parent=None):
        super().__init__(parent)

        self.setRange(-400, 400)
        self.setValue(0)

        self.setSingleStep(10)
        self.setPageStep(100)

        self.setWrapping(False)
        self.setNotchesVisible(True)
        self.setFixedSize(90, 90)

        self.setCursor(Qt.CursorShape.SizeVerCursor)

        self.setToolTip(
            "Mantené presionado y arrastrá hacia arriba o abajo.\n"
            "Doble clic para centrar."
        )

        self._dragging = False
        self._start_y = 0.0
        self._start_value = 0

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.setFocus()

            self._dragging = True
            self._start_y = event.globalPosition().y()
            self._start_value = self.value()

            event.accept()
            return

        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._dragging:
            displacement = (
                self._start_y - event.globalPosition().y()
            )

            # 50 píxeles de arrastre equivalen a una división.
            new_value = self._start_value + round(displacement * 2)

            self.setValue(new_value)

            event.accept()
            return

        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            event.accept()
            return

        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self.setValue(0)

            event.accept()
            return

        super().mouseDoubleClickEvent(event)

    def wheelEvent(self, event):
        # Permite desplazar el panel sin modificar la posición
        # accidentalmente al pasar la rueda sobre la perilla.
        event.ignore()