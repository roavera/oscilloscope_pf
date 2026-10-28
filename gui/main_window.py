"""Ventana principal y selector de fuente de adquisición."""

from PySide6.QtGui import QAction, QActionGroup
from PySide6.QtWidgets import (
    QLabel,
    QMainWindow,
    QMessageBox,
    QVBoxLayout,
    QWidget,
)

from acquisition.acquisition_manager import AcquisitionManager
from .oscilloscope_widget import OscilloscopeWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Osciloscopio de Audio")
        self.resize(1200, 700)

        central_widget = QWidget(self)
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)

        title = QLabel("Osciloscopio de Audio")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        main_layout.addWidget(title)

        self.oscilloscope = OscilloscopeWidget()
        main_layout.addWidget(self.oscilloscope)

        self._create_acquisition_menu()
        self._update_status()

    def _create_acquisition_menu(self):
        """Crea el menú Adquisición > Fuente."""
        acquisition_menu = self.menuBar().addMenu("Adquisición")
        source_menu = acquisition_menu.addMenu("Fuente")

        self.source_group = QActionGroup(self)
        self.source_group.setExclusive(True)
        self.source_actions = {}

        sources = (
            (AcquisitionManager.AUDIO, "Audio (sounddevice)", True),
            (AcquisitionManager.SIMULATOR, "Simulador Blackpill", True),
            (AcquisitionManager.BLACKPILL_USB, "Blackpill USB COM (próximamente)", False),
        )

        for source_id, label, enabled in sources:
            action = QAction(label, self)
            action.setCheckable(True)
            action.setEnabled(enabled)
            action.setData(source_id)
            self.source_group.addAction(action)
            source_menu.addAction(action)
            self.source_actions[source_id] = action

        current_source = self.oscilloscope.acquisition.source
        self.source_actions[current_source].setChecked(True)
        self.source_group.triggered.connect(self._on_source_selected)

    def _on_source_selected(self, action):
        """Cambia la fuente y recupera la anterior si el cambio falla."""
        source = action.data()
        previous_source = self.oscilloscope.acquisition.source

        if source == previous_source:
            return

        try:
            self.oscilloscope.change_acquisition_source(source)

            if not self.oscilloscope.acquisition.is_running:
                raise RuntimeError(
                    "La fuente seleccionada no pudo iniciarse."
                )

        except Exception as exc:
            try:
                self.oscilloscope.change_acquisition_source(previous_source)
            except Exception:
                pass

            current_source = self.oscilloscope.acquisition.source
            if current_source in self.source_actions:
                self.source_actions[current_source].setChecked(True)

            self._update_status()
            QMessageBox.warning(self, "Error de adquisición", str(exc))
            return

        self._update_status()

    def _update_status(self):
        """Actualiza la fuente activa y la frecuencia de muestreo."""
        labels = {
            AcquisitionManager.AUDIO: "Audio (sounddevice)",
            AcquisitionManager.SIMULATOR: "Simulador Blackpill",
            AcquisitionManager.BLACKPILL_USB: "Blackpill USB COM",
        }

        source = self.oscilloscope.acquisition.source
        label = labels.get(source, source)
        state = (
            "activa" if self.oscilloscope.acquisition.is_running else "detenida"
        )
        sample_rate = self.oscilloscope.acquisition.sample_rate

        self.statusBar().showMessage(
            f"Fuente: {label} | Estado: {state} | Fs: {sample_rate:,.2f} Hz"
        )
