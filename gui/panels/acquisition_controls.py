
"""Panel de adquisición: modos, interpolación y RUN/STOP."""

from PySide6.QtCore import Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QVBoxLayout,
    QFormLayout,
    QPushButton,
    QLabel,
    QComboBox,
    QFrame,
)


class AcquisitionControls(QGroupBox):
    """Panel de configuración y operación de adquisición."""

    # Señales de operación
    run_clicked = Signal()
    stop_clicked = Signal()

    # Señales de configuración
    mode_changed = Signal(str)
    interpolation_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__("Adquisición", parent)

        self._running = False
        self._actions_enabled = True

        self.create_interface()
        self.connect_signals()

        self._update_buttons()

    # ============================================================
    # INTERFAZ
    # ============================================================

    def create_interface(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 16, 12, 12)
        layout.setSpacing(12)

        # ========================================================
        # CONFIGURACIÓN DE ADQUISICIÓN
        # ========================================================

        settings_layout = QFormLayout()
        settings_layout.setSpacing(10)

        # --------------------------------------------------------
        # MODO DE ADQUISICIÓN
        # --------------------------------------------------------

        self.mode_combo = QComboBox()

        modes = [
            ("Sampling", "sampling"),
            ("Peak Detect", "peak_detect"),
            ("Average", "average"),
            ("High Resolution", "high_resolution"),
            ("Envelope", "envelope"),
        ]

        for label, value in modes:
            self.mode_combo.addItem(label, value)

        # Solo Sampling está disponible inicialmente.
        for index in range(1, self.mode_combo.count()):
            self.mode_combo.model().item(index).setEnabled(False)

        self.mode_combo.setCurrentIndex(0)

        self.mode_combo.setToolTip(
            "Selecciona cómo se procesan las muestras adquiridas."
        )

        settings_layout.addRow(
            "Modo:",
            self.mode_combo,
        )

        # --------------------------------------------------------
        # INTERPOLACIÓN VISUAL
        # --------------------------------------------------------

        self.interpolation_combo = QComboBox()

        interpolation_methods = [
            ("Puntos", "none"),
            ("Lineal", "linear"),
            ("Cúbica", "cubic"),
            ("Sinc (sin x/x)", "sinc"),
        ]

        for label, value in interpolation_methods:
            self.interpolation_combo.addItem(label, value)

        # La visualización actual utiliza segmentos lineales.
        # Las demás opciones se habilitarán al implementar
        # los algoritmos correspondientes.
        for index in (0, 2, 3):
            self.interpolation_combo.model().item(index).setEnabled(False)

        self.interpolation_combo.setCurrentIndex(1)

        self.interpolation_combo.setToolTip(
            "Selecciona cómo se representa la señal entre muestras."
        )

        settings_layout.addRow(
            "Interpolación:",
            self.interpolation_combo,
        )

        layout.addLayout(settings_layout)

        # ========================================================
        # SEPARADOR
        # ========================================================

        separator = QFrame()
        separator.setFrameShape(QFrame.Shape.HLine)
        separator.setFrameShadow(QFrame.Shadow.Sunken)

        layout.addWidget(separator)

        # ========================================================
        # ESTADO DE ADQUISICIÓN
        # ========================================================

        status_layout = QHBoxLayout()

        status_title = QLabel("Estado:")
        self.status_label = QLabel("STOP")
        self.status_label.setWordWrap(True)

        status_layout.addWidget(status_title)
        status_layout.addWidget(self.status_label, 1)

        layout.addLayout(status_layout)

        # ========================================================
        # BOTONES RUN Y STOP
        # ========================================================

        buttons_layout = QHBoxLayout()
        buttons_layout.setSpacing(8)

        self.run_button = QPushButton("▶ RUN")
        self.stop_button = QPushButton("■ STOP")

        for button in (
            self.run_button,
            self.stop_button,
        ):
            button.setMinimumHeight(40)
            button.setMinimumWidth(100)

        # --------------------------------------------------------
        # ESTILO RUN - VERDE
        # --------------------------------------------------------

        self.run_button.setStyleSheet("""
            QPushButton {
                background-color: #198754;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 8px 14px;
            }

            QPushButton:hover:enabled {
                background-color: #157347;
            }

            QPushButton:pressed:enabled {
                background-color: #0f5132;
            }

            QPushButton:disabled {
                background-color: #344d40;
                color: #8fa99a;
            }
        """)

        # --------------------------------------------------------
        # ESTILO STOP - ROJO
        # --------------------------------------------------------

        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                color: white;
                border: none;
                border-radius: 6px;
                font-weight: bold;
                padding: 8px 14px;
            }

            QPushButton:hover:enabled {
                background-color: #bb2d3b;
            }

            QPushButton:pressed:enabled {
                background-color: #842029;
            }

            QPushButton:disabled {
                background-color: #57383d;
                color: #b09a9d;
            }
        """)

        buttons_layout.addWidget(self.run_button)
        buttons_layout.addWidget(self.stop_button)

        layout.addLayout(buttons_layout)

    # ============================================================
    # CONEXIÓN DE SEÑALES
    # ============================================================

    def connect_signals(self):
        # RUN
        self.run_button.clicked.connect(
            self.run_clicked.emit
        )

        # STOP
        self.stop_button.clicked.connect(
            self.stop_clicked.emit
        )

        # Modo de adquisición
        self.mode_combo.currentIndexChanged.connect(
            lambda _: self.mode_changed.emit(
                self.mode_combo.currentData()
            )
        )

        # Interpolación visual
        self.interpolation_combo.currentIndexChanged.connect(
            lambda _: self.interpolation_changed.emit(
                self.interpolation_combo.currentData()
            )
        )

    # ============================================================
    # ESTADO DE ADQUISICIÓN
    # ============================================================

    def show_state(self, running, status, error=None):
        """Actualiza el indicador y los botones."""

        self._running = bool(running)

        self.status_label.setText(
            f"{status}: {error}" if error else status
        )

        self.status_label.setToolTip(error or "")

        self._update_buttons()

    def set_actions_enabled(self, enabled):
        """Habilita o deshabilita los controles de operación."""

        self._actions_enabled = bool(enabled)
        self._update_buttons()

    def _update_buttons(self):
        """Sincroniza RUN y STOP con el estado de adquisición."""

        enabled = self._actions_enabled

        self.run_button.setEnabled(
            enabled and not self._running
        )

        self.stop_button.setEnabled(
            enabled and self._running
        )

    # ============================================================
    # MODOS DE ADQUISICIÓN
    # ============================================================

    def set_mode(self, mode):
        """Selecciona un modo de adquisición habilitado."""

        index = self.mode_combo.findData(mode)

        if index < 0:
            raise ValueError(
                f"Modo de adquisición desconocido: {mode}"
            )

        if not self.mode_combo.model().item(index).isEnabled():
            raise ValueError(
                f"Modo de adquisición no disponible: {mode}"
            )

        self.mode_combo.setCurrentIndex(index)

    def enable_mode(self, mode, enabled=True):
        """Habilita un modo cuando su algoritmo esté implementado."""

        index = self.mode_combo.findData(mode)

        if index < 0:
            raise ValueError(
                f"Modo de adquisición desconocido: {mode}"
            )

        if not enabled and self.mode_combo.currentIndex() == index:
            raise ValueError(
                "No se puede deshabilitar el modo seleccionado."
            )

        self.mode_combo.model().item(index).setEnabled(
            bool(enabled)
        )

    # ============================================================
    # INTERPOLACIÓN
    # ============================================================

    def set_interpolation(self, interpolation):
        """Selecciona un método de interpolación habilitado."""

        index = self.interpolation_combo.findData(interpolation)

        if index < 0:
            raise ValueError(
                f"Interpolación desconocida: {interpolation}"
            )

        if not self.interpolation_combo.model().item(index).isEnabled():
            raise ValueError(
                f"Interpolación no disponible: {interpolation}"
            )

        self.interpolation_combo.setCurrentIndex(index)

    def enable_interpolation(self, interpolation, enabled=True):
        """Habilita una interpolación implementada."""

        index = self.interpolation_combo.findData(interpolation)

        if index < 0:
            raise ValueError(
                f"Interpolación desconocida: {interpolation}"
            )

        if not enabled and self.interpolation_combo.currentIndex() == index:
            raise ValueError(
                "No se puede deshabilitar la interpolación seleccionada."
            )

        self.interpolation_combo.model().item(index).setEnabled(
            bool(enabled)
        )