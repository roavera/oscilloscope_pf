"""Botones de adquisición e indicador de estado."""

from PySide6.QtCore import Signal, Qt

from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QVBoxLayout,
    QPushButton,
    QLabel,
)


class AcquisitionControls(QGroupBox):

    run_stop_clicked = Signal()
    single_clicked = Signal()

    def __init__(self, parent=None):
        super().__init__("Adquisición", parent)

        self.create_interface()
        self.connect_signals()

    def create_interface(self):
        layout = QHBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(12)

        # ------------------------------------------------------------
        # ESTADO
        # ------------------------------------------------------------

        status_layout = QVBoxLayout()
        status_layout.setSpacing(6)

        title = QLabel("Estado")

        self.status_label = QLabel("STOP")
        self.status_label.setWordWrap(True)

        status_layout.addWidget(title)
        status_layout.addWidget(self.status_label)
        status_layout.addStretch()

        layout.addLayout(status_layout, 1)

        # ------------------------------------------------------------
        # BOTONES DE OPERACIÓN
        # ------------------------------------------------------------

        buttons_layout = QVBoxLayout()
        buttons_layout.setSpacing(8)

        self.single_button = QPushButton("SINGLE")
        self.run_button = QPushButton("RUN")

        for button in (self.single_button, self.run_button):
            button.setFixedWidth(110)
            button.setMinimumHeight(36)

        buttons_layout.addWidget(self.single_button)
        buttons_layout.addWidget(self.run_button)

        layout.addLayout(buttons_layout)
        layout.setAlignment(
            buttons_layout,
            Qt.AlignmentFlag.AlignTop,
        )

    def connect_signals(self):
        self.run_button.clicked.connect(
            lambda _checked=False: self.run_stop_clicked.emit()
        )

        self.single_button.clicked.connect(
            lambda _checked=False: self.single_clicked.emit()
        )

    def show_state(self, running, status, error=None):
        self.run_button.setText("STOP" if running else "RUN")

        self.status_label.setText(
            f"{status}: {error}" if error else status
        )

        self.status_label.setToolTip(error or "")

    def set_actions_enabled(self, enabled):
        self.run_button.setEnabled(enabled)
        self.single_button.setEnabled(enabled)