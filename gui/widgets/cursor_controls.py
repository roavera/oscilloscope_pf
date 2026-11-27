"""Panel compacto de cursores, sin dependencia del tema de la aplicación."""
from PySide6.QtCore import Signal, QSignalBlocker, Qt
from PySide6.QtWidgets import (QGroupBox, QVBoxLayout, QHBoxLayout, QLabel,
    QComboBox, QCheckBox, QPushButton, QButtonGroup, QDoubleSpinBox, QFrame)


class CursorControls(QGroupBox):
    settings_changed = Signal(str, str)
    channel_changed = Signal(int)
    labels_visible_changed = Signal(bool)
    second_channel_changed = Signal(int)
    linked_changed = Signal(bool)
    snap_changed = Signal(bool)
    reset_requested = Signal()
    position_changed = Signal(int, float)

    def __init__(self, parent=None):
        super().__init__("Cursores", parent)
        layout = QVBoxLayout(self)
        layout.setSpacing(8)
        self.mode = QComboBox(self)
        self.mode.addItems(["Off", "Manual", "Track"])
        self.mode.hide()
        self.orientation = QComboBox(self)
        self.orientation.addItems(["Tiempo", "Tensión"])
        self.orientation.hide()
        modes = QHBoxLayout()
        self.buttons = QButtonGroup(self)
        for i, name in enumerate(("OFF", "Tiempo", "Amplitud", "Track")):
            b = QPushButton(name)
            b.setCheckable(True)
            self.buttons.addButton(b, i)
            modes.addWidget(b)
        self.buttons.button(0).setChecked(True)
        self.buttons.idClicked.connect(self._choose)
        layout.addLayout(modes)
        self.source_row = QFrame()
        sources = QHBoxLayout(self.source_row)
        sources.setContentsMargins(0, 0, 0, 0)
        sources.addWidget(QLabel("Fuente C1"))
        self.channel = QComboBox()
        for n, name in enumerate(("CH1", "CH2", "MATH"), 1):
            self.channel.addItem(name, n)
        sources.addWidget(self.channel, 1)
        self.second_label = QLabel("C2")
        self.second = QComboBox()
        self.second.addItem("Misma", 0)
        for n, name in enumerate(("CH1", "CH2", "MATH"), 1):
            self.second.addItem(name, n)
        sources.addWidget(self.second_label)
        sources.addWidget(self.second, 1)
        layout.addWidget(self.source_row)
        self.details = QFrame()
        detail = QVBoxLayout(self.details)
        detail.setContentsMargins(0, 0, 0, 0)
        self.cards = []
        self.positions = []
        row = QHBoxLayout()
        for i, color in enumerate(("#33d6e8", "#ffad4d")):
            card = QGroupBox(f"Cursor {i+1}")
            card.setStyleSheet("QGroupBox { border: 1px solid palette(mid); border-radius: 6px; margin-top: 10px; padding-top: 8px; } QGroupBox::title { subcontrol-origin: margin; left: 8px; }")
            col = QVBoxLayout(card)
            label = QLabel("—")
            label.setWordWrap(True)
            label.setStyleSheet("font-size: 15px; font-weight: 600;")
            col.addWidget(label)
            spin = QDoubleSpinBox()
            spin.setRange(0, 100)
            spin.setDecimals(2)
            spin.setSuffix(" %")
            spin.setKeyboardTracking(False)
            spin.setToolTip("Posición dentro del área visible (0–100 %). También podés arrastrar el cursor.")
            spin.valueChanged.connect(lambda v, j=i: self.position_changed.emit(j, v/100))
            col.addWidget(spin)
            self.cards.append(label)
            self.positions.append(spin)
            row.addWidget(card, 1)
        detail.addLayout(row)
        self.readout = QLabel("—")
        self.readout.setWordWrap(True)
        self.readout.setStyleSheet("font-size: 16px; font-weight: 600; padding: 8px; border: 1px solid palette(mid); border-radius: 6px;")
        detail.addWidget(self.readout)
        options = QHBoxLayout()
        self.linked = QCheckBox("Vincular")
        self.snap = QCheckBox("Ajustar a muestras")
        reset = QPushButton("Restablecer")
        options.addWidget(self.linked)
        options.addWidget(self.snap)
        options.addWidget(reset)
        detail.addLayout(options)
        self.show_values = QCheckBox("Mostrar etiquetas en el gráfico")
        self.show_values.setChecked(True)
        detail.addWidget(self.show_values)
        layout.addWidget(self.details)
        self.status = QLabel("Arrastrá los cursores sobre el gráfico.")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)
        self.mode.currentTextChanged.connect(self._changed)
        self.orientation.currentTextChanged.connect(self._changed)
        self.channel.currentIndexChanged.connect(lambda _: self.channel_changed.emit(int(self.channel.currentData())))
        self.second.currentIndexChanged.connect(lambda _: self.second_channel_changed.emit(int(self.second.currentData())))
        self.show_values.toggled.connect(self.labels_visible_changed.emit)
        self.linked.toggled.connect(self.linked_changed.emit)
        self.snap.toggled.connect(self.snap_changed.emit)
        reset.clicked.connect(self.reset_requested.emit)
        self._changed()

    def _choose(self, i):
        with QSignalBlocker(self.mode), QSignalBlocker(self.orientation):
            self.mode.setCurrentText(("Off", "Manual", "Manual", "Track")[i])
            self.orientation.setCurrentText("Tensión" if i == 2 else "Tiempo")
        self._changed()

    def _changed(self, *_):
        mode, orientation = self.mode.currentText(), self.orientation.currentText()
        if mode == "Track":
            with QSignalBlocker(self.orientation):
                self.orientation.setCurrentText("Tiempo")
            orientation = "Tiempo"
        i = 0 if mode == "Off" else 3 if mode == "Track" else 2 if orientation == "Tensión" else 1
        self.buttons.button(i).setChecked(True)
        self.details.setVisible(i != 0)
        self.source_row.setVisible(i in (2, 3))
        self.second.setVisible(i == 3)
        self.second_label.setVisible(i == 3)
        self.snap.setVisible(i == 3)
        self.status.setText("Cursores desactivados" if i == 0 else "Arrastrá los cursores o ajustá su posición en % del área visible.")
        self.settings_changed.emit(mode, orientation)

    def set_readout(self, text):
        # Compatibilidad con la señal de texto anterior.
        if self.mode.currentText() == "Off":
            self.readout.setText(text)

    def set_cursor_data(self, data):
        for i in range(2):
            self.cards[i].setText(data["cards"][i])
            with QSignalBlocker(self.positions[i]):
                self.positions[i].setValue(data["positions"][i]*100)
        self.readout.setText(data["result"])
        self.status.setText(data["status"])
