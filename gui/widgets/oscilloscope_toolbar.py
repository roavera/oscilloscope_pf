"""Barra superior de acceso rápido del osciloscopio."""
from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import QFrame, QHBoxLayout, QLabel, QPushButton, QSizePolicy


class OscilloscopeToolbar(QFrame):
    run_stop_clicked = Signal()
    single_clicked = Signal()
    cursors_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("oscilloscopeToolbar")
        layout = QHBoxLayout(self)
        layout.setContentsMargins(10, 6, 10, 6)
        layout.setSpacing(8)

        self.run_button = QPushButton("STOP")
        self.run_button.setToolTip("Congelar o reanudar la visualización")
        self.run_button.clicked.connect(self.run_stop_clicked.emit)
        layout.addWidget(self.run_button)

        self.single_button = QPushButton("SINGLE")
        self.single_button.setToolTip("Esperar una captura con disparo único")
        self.single_button.clicked.connect(self.single_clicked.emit)
        layout.addWidget(self.single_button)

        self.cursors_button = QPushButton("CURSORES")
        self.cursors_button.setToolTip("Activar o desactivar cursores manuales")
        self.cursors_button.clicked.connect(self.cursors_clicked.emit)
        layout.addWidget(self.cursors_button)

        layout.addStretch(1)
        self.source_label = QLabel("Fuente: —")
        self.source_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        self.source_label.setMinimumWidth(0)
        layout.addWidget(self.source_label)
        self.state_label = QLabel("STOP")
        self.state_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.state_label.setMinimumWidth(85)
        layout.addWidget(self.state_label)

    def update_state(self, *, running, state, source):
        self.run_button.setText("STOP" if running else "RUN")
        self.run_button.setEnabled(state not in ("connecting",))
        self.single_button.setEnabled(state == "connected")
        self.cursors_button.setEnabled(True)
        self.source_label.setText(f"Fuente: {source}")
        if state == "connecting":
            label = "CONECTANDO"
        elif state == "error":
            label = "ERROR"
        elif state == "stopped":
            label = "SIN FUENTE"
        else:
            label = "RUN" if running else "STOP"
        self.state_label.setText(label)
