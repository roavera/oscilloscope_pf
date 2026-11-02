"""Controles compactos de adquisición para el panel frontal LeCroy.

Mantiene la API y los identificadores internos utilizados por el controlador.
Los ajustes avanzados se muestran en un diálogo no modal.
"""

from PySide6.QtCore import Signal, QSignalBlocker
from PySide6.QtWidgets import (
    QComboBox, QDialog, QFormLayout, QGroupBox, QHBoxLayout,
    QLabel, QPushButton, QVBoxLayout, QWidget,
)


class AcquisitionControls(QGroupBox):
    run_clicked = Signal()
    stop_clicked = Signal()
    mode_changed = Signal(str)
    interpolation_changed = Signal(str)
    average_count_changed = Signal(int)
    envelope_count_changed = Signal(int)
    peak_bucket_size_changed = Signal(int)

    def __init__(self, parent=None):
        super().__init__("Adquisición", parent)
        self._running = False
        self._actions_enabled = True
        self.create_interface()
        self.connect_signals()
        self._update_buttons()

    def create_interface(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 10, 8, 8)
        layout.setSpacing(6)

        buttons = QHBoxLayout()
        buttons.setSpacing(6)
        self.run_button = QPushButton("▶ RUN")
        self.stop_button = QPushButton("■ STOP")
        self.settings_button = QPushButton("ADQUISICIÓN")
        self.settings_button.setToolTip("Configurar modo de adquisición e interpolación")

        self.run_button.setStyleSheet("""
            QPushButton {background:#198754;color:white;border:0;border-radius:5px;
                         font-weight:bold;padding:3px 6px;}
            QPushButton:hover:enabled {background:#157347;}
            QPushButton:disabled {background:#344d40;color:#8fa99a;}
        """)
        self.stop_button.setStyleSheet("""
            QPushButton {background:#dc3545;color:white;border:0;border-radius:5px;
                         font-weight:bold;padding:3px 6px;}
            QPushButton:hover:enabled {background:#bb2d3b;}
            QPushButton:disabled {background:#57383d;color:#b09a9d;}
        """)
        self.settings_button.setStyleSheet("""
            QPushButton {background:#34465a;color:#f0f4f8;border:1px solid #60758b;
                         border-radius:5px;font-weight:bold;padding:3px 6px;}
            QPushButton:hover:enabled {background:#465d76;}
        """)
        for button in (self.run_button, self.stop_button, self.settings_button):
            button.setMinimumHeight(26)
            buttons.addWidget(button, 1)
        layout.addLayout(buttons)

        self.status_label = QLabel("STOP")
        self.status_label.setWordWrap(True)
        self.status_label.hide()
        layout.addWidget(self.status_label)

        # Se crea una sola vez: los combos conservan estado y conexiones.
        self.settings_dialog = QDialog(self)
        self.settings_dialog.setWindowTitle("Configuración de adquisición")
        self.settings_dialog.setModal(False)
        self.settings_dialog.setMinimumWidth(330)
        dialog_layout = QVBoxLayout(self.settings_dialog)
        form = QFormLayout()

        self.mode_combo = QComboBox()
        modes = (
            ("Muestreo", "sampling"),
            ("Detección de picos", "peak_detect"),
            ("Promediado", "average"),
            ("Alta resolución", "high_resolution"),
            ("Envolvente", "envelope"),
        )
        for label, value in modes:
            self.mode_combo.addItem(label, value)
        for index in (3,):
            self.mode_combo.model().item(index).setEnabled(False)
        self.mode_combo.setCurrentIndex(0)
        self.mode_combo.setToolTip("Procesamiento de las muestras adquiridas")

        self.interpolation_combo = QComboBox()
        interpolations = (
            ("Puntos", "none"),
            ("Lineal", "linear"),
            ("Cúbica", "cubic"),
            ("Sinc (sin x/x)", "sinc"),
        )
        for label, value in interpolations:
            self.interpolation_combo.addItem(label, value)
        for index in (0, 2, 3):
            self.interpolation_combo.model().item(index).setEnabled(False)
        self.interpolation_combo.setCurrentIndex(1)
        self.interpolation_combo.setToolTip("Representación visual entre muestras")

        form.addRow("Modo:", self.mode_combo)
        self.peak_bucket_combo = QComboBox()
        for count in (2, 4, 8, 16):
            self.peak_bucket_combo.addItem(str(count), count)
        self.peak_bucket_combo.setCurrentIndex(1)
        self.peak_bucket_combo.setToolTip(
            "Mínimo y máximo por intervalo de una captura. No acumula capturas."
        )
        form.addRow("Muestras por intervalo:", self.peak_bucket_combo)
        self.average_count_combo = QComboBox()
        for count in (4, 16, 32, 64, 128, 256):
            self.average_count_combo.addItem(str(count), count)
        self.average_count_combo.setCurrentIndex(1)
        self.average_count_combo.setToolTip("Cantidad de capturas alineadas del promedio móvil")
        form.addRow("Capturas a promediar:", self.average_count_combo)
        self.envelope_count_combo = QComboBox()
        for count in (4, 16, 32, 64, 128, 256):
            self.envelope_count_combo.addItem(str(count), count)
        self.envelope_count_combo.setCurrentIndex(1)
        self.envelope_count_combo.setToolTip("Últimas N capturas que forman los mínimos y máximos")
        form.addRow("Capturas de envolvente:", self.envelope_count_combo)
        self.average_progress_label = QLabel("0 / 16 capturas")
        form.addRow("Progreso:", self.average_progress_label)
        form.addRow("Interpolación:", self.interpolation_combo)
        dialog_layout.addLayout(form)
        note = QLabel(
            "Promediado y Envolvente esperan disparos válidos, también en Auto. "
            "SINGLE completa N capturas y congela ambos canales.\n"
            "Las opciones no implementadas permanecen deshabilitadas."
        )
        note.setWordWrap(True)
        dialog_layout.addWidget(note)
        close_button = QPushButton("Cerrar")
        close_button.clicked.connect(self.settings_dialog.hide)
        dialog_layout.addWidget(close_button)

    def connect_signals(self):
        self.run_button.clicked.connect(self.run_clicked.emit)
        self.stop_button.clicked.connect(self.stop_clicked.emit)
        self.settings_button.clicked.connect(self.settings_dialog.show)
        self.mode_combo.currentIndexChanged.connect(self._emit_mode)
        self.peak_bucket_combo.currentIndexChanged.connect(
            lambda _: self.peak_bucket_size_changed.emit(int(self.peak_bucket_combo.currentData()))
        )
        self.average_count_combo.currentIndexChanged.connect(self._emit_average_count)
        self.envelope_count_combo.currentIndexChanged.connect(self._emit_envelope_count)
        self._update_accumulation_controls()
        self.interpolation_combo.currentIndexChanged.connect(self._emit_interpolation)

    def _emit_mode(self, _index):
        self._update_accumulation_controls()
        value = self.mode_combo.currentData()
        if value is not None:
            self.mode_changed.emit(str(value))

    def set_peak_bucket_size(self, count):
        index = self._index_for(self.peak_bucket_combo, count, "Intervalo Peak Detect")
        blocker = QSignalBlocker(self.peak_bucket_combo)
        self.peak_bucket_combo.setCurrentIndex(index)
        del blocker

    def _update_accumulation_controls(self):
        self.settings_button.setText(self.mode_combo.currentText())
        self.peak_bucket_combo.setEnabled(self.mode_combo.currentData() == "peak_detect")
        enabled = self.mode_combo.currentData() == "average"
        self.average_count_combo.setEnabled(enabled)
        envelope = self.mode_combo.currentData() == "envelope"
        self.envelope_count_combo.setEnabled(envelope)
        self.average_progress_label.setEnabled(enabled or envelope)

    def _emit_average_count(self, _index):
        self.average_count_changed.emit(int(self.average_count_combo.currentData()))

    def set_average_count(self, count):
        index = self._index_for(self.average_count_combo, count, "Cantidad de capturas")
        blocker = QSignalBlocker(self.average_count_combo)
        try:
            self.average_count_combo.setCurrentIndex(index)
        finally:
            del blocker

    def _emit_envelope_count(self, _index):
        self.envelope_count_changed.emit(int(self.envelope_count_combo.currentData()))

    def set_envelope_count(self, count):
        index = self._index_for(self.envelope_count_combo, count, "Cantidad de capturas")
        blocker = QSignalBlocker(self.envelope_count_combo)
        try:
            self.envelope_count_combo.setCurrentIndex(index)
        finally:
            del blocker

    def show_capture_progress(self, count, target):
        self.average_progress_label.setText(f"{count} / {target} capturas")

    def show_average_progress(self, count, target):
        """Alias para código que usaba la primera versión de Promediado."""
        self.show_capture_progress(count, target)

    def _emit_interpolation(self, _index):
        value = self.interpolation_combo.currentData()
        if value is not None:
            self.interpolation_changed.emit(str(value))

    def show_state(self, running, status, error=None):
        self._running = bool(running)
        self.status_label.setText(f"{status}: {error}" if error else str(status))
        self.status_label.setToolTip(error or "")
        self.status_label.setVisible(bool(error))
        self.setToolTip(f"{status}: {error}" if error else str(status))
        self._update_buttons()

    def set_actions_enabled(self, enabled):
        self._actions_enabled = bool(enabled)
        self._update_buttons()

    def _update_buttons(self):
        self.run_button.setEnabled(self._actions_enabled and not self._running)
        self.stop_button.setEnabled(self._actions_enabled and self._running)

    @staticmethod
    def _index_for(combo, value, category):
        index = combo.findData(value)
        if index < 0:
            raise ValueError(f"{category} desconocido: {value}")
        return index

    def set_mode(self, mode):
        index = self._index_for(self.mode_combo, mode, "Modo de adquisición")
        if not self.mode_combo.model().item(index).isEnabled():
            raise ValueError(f"Modo de adquisición no disponible: {mode}")
        blocker = QSignalBlocker(self.mode_combo)
        try:
            self.mode_combo.setCurrentIndex(index)
            self._update_accumulation_controls()
        finally:
            del blocker

    def enable_mode(self, mode, enabled=True):
        index = self._index_for(self.mode_combo, mode, "Modo de adquisición")
        if not enabled and self.mode_combo.currentIndex() == index:
            raise ValueError("No se puede deshabilitar el modo seleccionado.")
        self.mode_combo.model().item(index).setEnabled(bool(enabled))

    def set_interpolation(self, interpolation):
        index = self._index_for(self.interpolation_combo, interpolation, "Interpolación")
        if not self.interpolation_combo.model().item(index).isEnabled():
            raise ValueError(f"Interpolación no disponible: {interpolation}")
        blocker = QSignalBlocker(self.interpolation_combo)
        try:
            self.interpolation_combo.setCurrentIndex(index)
        finally:
            del blocker

    def enable_interpolation(self, interpolation, enabled=True):
        index = self._index_for(self.interpolation_combo, interpolation, "Interpolación")
        if not enabled and self.interpolation_combo.currentIndex() == index:
            raise ValueError("No se puede deshabilitar la interpolación seleccionada.")
        self.interpolation_combo.model().item(index).setEnabled(bool(enabled))



