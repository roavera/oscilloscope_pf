"""
===============================================================================
CONTROLADOR DE VENTANA PRINCIPAL (MAIN WINDOW GUI CONTROLLER)
===============================================================================
Proyecto:       Osciloscopio y Analizador de Audio por Software (DSO)
Framework:      PySide6 (Qt for Python)
Descripción:
    Define la interfaz de usuario raíz (QMainWindow) y la jerarquía de layouts.
    Actúa como contenedor principal para el área de visualización del osciloscopio
    (OscilloscopeWidget) y los paneles de control de adquisición de hardware.
    
Componentes principales:
    - QVBoxLayout principal con distribución vertical de vistas.
    - Barra horizontal (QHBoxLayout) para configuración del backend de audio.
    - Instanciación y anclaje del widget central de procesamiento gráfico.
===============================================================================
"""

from PySide6.QtWidgets import QMainWindow, QWidget, QVBoxLayout,QHBoxLayout, QLabel, QComboBox
from .oscilloscope_widget import OscilloscopeWidget

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        
        # ============================================================
        # CONFIGURACIÓN DE LA VENTANA
        # ============================================================
        self.setWindowTitle("Osciloscopio de Audio")
        self.resize(1000, 600)
        
        # ============================================================
        # WIDGET CENTRAL - contenedor principal de la app
        # ============================================================
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # ============================================================
        # LAYOUT - organizador de widgets dentro del widget central
        # ============================================================
        main_layout = QVBoxLayout()
        central_widget.setLayout(main_layout)
        
        # ============================================================
        # TÍTULO
        # ============================================================
        title = QLabel("Osciloscopio de Audio")
        title.setStyleSheet("font-size: 24px; font-weight: bold;")
        main_layout.addWidget(title)
        
        # ============================================================
        # CONFIGURACIÓN DE AUDIO
        # ============================================================
        audio_layout = QHBoxLayout()
        """device_label = QLabel("Dispositivo de Entrada:")
        audio_layout.addWidget(device_label)"""
        main_layout.addLayout(audio_layout)
        
        # ============================================================
        # OSCILOSCOPIO WIDGET - área de visualización del osciloscopio
        # ============================================================
        self.oscilloscope = OscilloscopeWidget()
        main_layout.addWidget(self.oscilloscope)