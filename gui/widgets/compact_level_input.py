"""Entrada compacta con nueve decimales disponibles al editar."""
from PySide6.QtCore import QSignalBlocker
from PySide6.QtGui import QDoubleValidator
from PySide6.QtWidgets import QDoubleSpinBox


class CompactLevelInput(QDoubleSpinBox):
    def __init__(self, parent=None):
        self._editing = False
        super().__init__(parent)

    def textFromValue(self, value):
        if self._editing:
            text = self.locale().toString(value, "f", self.decimals())
            point = self.locale().decimalPoint()
            if point in text:
                text = text.rstrip("0").rstrip(point)
            return text
        if value != 0 and (abs(value) < 1e-3 or abs(value) >= 1e5):
            mantissa, exponent = self.locale().toString(value, "e", 3).lower().split("e")
            point = self.locale().decimalPoint()
            if point in mantissa:
                mantissa = mantissa.rstrip("0").rstrip(point)
            return f"{mantissa}e{int(exponent)}"
        return self.locale().toString(value, "g", 6)

    def _number_text(self, text):
        text = text.strip()
        suffix = self.suffix().strip()
        if suffix and text.endswith(suffix):
            text = text[:-len(suffix)].strip()
        return text

    def valueFromText(self, text):
        value, valid = self.locale().toDouble(self._number_text(text))
        return value if valid else self.value()

    def validate(self, text, position):
        validator = QDoubleValidator(self.minimum(), self.maximum(), self.decimals())
        validator.setNotation(QDoubleValidator.Notation.ScientificNotation)
        validator.setLocale(self.locale())
        state, _, _ = validator.validate(self._number_text(text), position)
        return state, text, position

    def _refresh_text(self):
        blocker = QSignalBlocker(self.lineEdit())
        try:
            self.lineEdit().setText(self.textFromValue(self.value()) + self.suffix())
            self.lineEdit().setModified(False)
        finally:
            del blocker

    def focusInEvent(self, event):
        self._editing = True
        super().focusInEvent(event)
        self._refresh_text()

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        self._editing = False
        self._refresh_text()


    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.buttonSymbols() == QDoubleSpinBox.ButtonSymbols.NoButtons:
            # Algunos estilos Qt reservan todo el ancho para los botones ocultos.
            self.lineEdit().setGeometry(self.rect().adjusted(5, 3, -5, -3))
