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
        self.statusBar().showMessage("Fuente: Audio (sounddevice)")

    def _create_acquisition_menu(self):
        acquisition_menu = self.menuBar().addMenu("Adquisición")
        source_menu = acquisition_menu.addMenu("Fuente")

        self.source_group = QActionGroup(self)
        self.source_group.setExclusive(True)
        self.source_actions = {}

        sources = (
            (AcquisitionManager.AUDIO, "Audio (sounddevice)", True),
            (AcquisitionManager.SIMULATOR, "Simulador Blackpill (próximamente)", False),
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
        source = action.data()
        previous_source = self.oscilloscope.acquisition.source
        if source == previous_source:
            return

        try:
            self.oscilloscope.change_acquisition_source(source)
        except Exception as exc:
            self.source_actions[previous_source].setChecked(True)
            QMessageBox.warning(self, "Adquisición", str(exc))
            return

        self.statusBar().showMessage(f"Fuente: {action.text()}")