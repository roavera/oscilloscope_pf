"""Panel de cursores Manual y Track para CH1."""
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QLabel, QComboBox, QGroupBox

class CursorControls(QGroupBox):
    settings_changed = Signal(str, str)

    def __init__(self, parent=None):
        super().__init__('CURSORES · CH1', parent)
        layout = QVBoxLayout(self)
        row = QHBoxLayout()
        self.mode = QComboBox()
        self.mode.addItems(['Off', 'Manual', 'Track'])
        self.orientation = QComboBox()
        self.orientation.addItems(['Tiempo', 'Tensión'])
        row.addWidget(QLabel('Modo'))
        row.addWidget(self.mode)
        row.addWidget(QLabel('Eje'))
        row.addWidget(self.orientation)
        layout.addLayout(row)
        self.readout = QLabel('Cursores desactivados')
        self.readout.setWordWrap(True)
        self.readout.setMinimumHeight(65)
        self.readout.setStyleSheet('font-family: monospace;')
        layout.addWidget(self.readout)
        self.mode.currentTextChanged.connect(self._changed)
        self.orientation.currentTextChanged.connect(self._changed)
        self._changed()

    def _changed(self, *_):
        mode = self.mode.currentText()
        self.orientation.setEnabled(mode == 'Manual')
        self.settings_changed.emit(mode, self.orientation.currentText())

    def set_readout(self, text):
        self.readout.setText(text)
