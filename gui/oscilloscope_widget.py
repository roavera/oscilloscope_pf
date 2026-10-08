import numpy as np

from PySide6.QtCore import QTimer, Signal
from PySide6.QtWidgets import QWidget, QVBoxLayout

from acquisition.audio_input import AudioInput
from acquisition.acquisition_buffer import AcquisitionBuffer
from trigger.edge_trigger import Edge_Trigger

from gui.controls import OscilloscopeControls
from gui.oscilloscope_plot import OscilloscopePlot


class OscilloscopeWidget(QWidget):
    
    # Señal emitida desde el hilo de audio para notificar nuevos datos disponibles
    data_ready = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)

        # ============================================================
        # CONFIGURACIÓN DE ADQUISICIÓN
        # ============================================================

        self.sample_rate = 48000
        self.blocksize = 2048
        self.channels = 1

        # ============================================================
        # CONFIGURACIÓN DE PANTALLA
        # ============================================================

        self.horizontal_divisions = 12
        self.vertical_divisions = 8

        self.time_per_division = 0.001
        self.volts_per_division = 0.02

        # Parámetros geométricos y de posicionamiento faltantes
        self.horizontal_position = 0.0  # Desplazamiento temporal (delay)
        self.vertical_offset = 0.0      # Offset de tensión en CC

        self.display_samples = int(
            self.sample_rate * self.time_per_division * self.horizontal_divisions
        )

        # ============================================================
        # CONFIGURACIÓN DEL TRIGGER
        # ============================================================

        self.trigger_level = 0.0
        self.trigger_slope = "Rising"
        self.trigger_position = 0.5
        self.trigger_mode = "Auto"

        # ============================================================
        # ESTADO DEL OSCILOSCOPIO
        # ============================================================

        self.running = True
        self.single_mode = False

        self.last_acquisition = None
        self.trigger_found = False

        # ============================================================
        # BUFFER DE ADQUISICIÓN
        # ============================================================

        # 1 segundo de historial a 48 kHz (debe garantizar thread-safety internamente)
        buffer_size = self.sample_rate
        self.buffer = AcquisitionBuffer(buffer_size)

        # ============================================================
        # ENTRADA DE AUDIO
        # ============================================================

        self.audio = AudioInput(
            sample_rate=self.sample_rate,
            channels=self.channels,
            blocksize=self.blocksize
        )

        # ============================================================
        # TRIGGER
        # ============================================================

        self.trigger = Edge_Trigger(
            level=self.trigger_level,
            slope=self.trigger_slope,
            position=self.trigger_position
        )

        # ============================================================
        # CONTROLES Y PANTALLA
        # ============================================================

        self.controls = OscilloscopeControls()

        self.plot = OscilloscopePlot(
            horizontal_divisions=self.horizontal_divisions,
            vertical_divisions=self.vertical_divisions,
            time_per_division=self.time_per_division,
            volts_per_division=self.volts_per_division,
            horizontal_position=self.horizontal_position, 
            vertical_offset=self.vertical_offset,
            trigger_level=self.trigger_level,
            trigger_position=self.trigger_position
        )

        # ============================================================
        # LAYOUT
        # ============================================================

        layout = QVBoxLayout()
        layout.addWidget(self.controls)
        layout.addWidget(self.plot)
        self.setLayout(layout)

        # ============================================================
        # CONEXIONES DE SEÑALES Y CONTROLES
        # ============================================================

        self.controls.time_per_division_changed.connect(self.set_time_per_division)
        self.controls.volts_per_division_changed.connect(self.set_volts_per_division)
        self.controls.trigger_level_changed.connect(self.set_trigger_level)
        self.controls.trigger_slope_changed.connect(self.set_trigger_slope)
        self.controls.trigger_mode_changed.connect(self.set_trigger_mode)
        self.controls.run_stop_clicked.connect(self.toggle_run_stop)
        self.controls.single_clicked.connect(self.single)

        # Conexión basada en eventos (Reemplaza al QTimer de sondeo periódico)
        self.data_ready.connect(self.process_oscilloscope)

        # ============================================================
        # INICIAR ADQUISICIÓN
        # ============================================================

        self.audio.start_stream(self.audio_callback)

    # =================================================================
    # CALLBACK DE AUDIO (Ejecutado en hilo secundario)
    # =================================================================

    def audio_callback(self, data):
        """
        Recibe un bloque de muestras desde AudioInput, lo incorpora al buffer
        y emite una señal hacia el hilo principal de Qt de forma segura.
        """
        data_array = np.asarray(data, dtype=np.float32)

        if data_array.size == 0:
            return

        self.buffer.add_samples(data_array)
        
        # Notifica al hilo de GUI que hay nuevos datos listos para procesar
        self.data_ready.emit()

    # =================================================================
    # PROCESAMIENTO DEL OSCILOSCOPIO
    # =================================================================

    def process_oscilloscope(self):
        """
        Obtiene las muestras del buffer, busca el trigger y genera
        la ventana de adquisición de forma determinista ante cada bloque.
        """
        if not self.running:
            return

        data = self.buffer.get_data()

        if len(data) < self.display_samples:
            return

        # ============================================================
        # MODO NORMAL / SINGLE
        # ============================================================

        if self.trigger_mode in ("Normal", "Single"):
            trigger_index = self.trigger.find(data, self.display_samples)

            if trigger_index is None:
                return

            acquisition = self.trigger.capture(
                data,
                trigger_index,
                self.display_samples
            )

            if acquisition is None:
                return

            self.last_acquisition = acquisition
            self.trigger_found = True

            self.plot.set_signal(acquisition, self.sample_rate)

            if self.trigger_mode == "Single":
                self.running = False

            return

        # ============================================================
        # MODO AUTO
        # ============================================================

        trigger_index = self.trigger.find(data, self.display_samples)

        if trigger_index is not None:
            acquisition = self.trigger.capture(
                data,
                trigger_index,
                self.display_samples
            )

            if acquisition is not None:
                self.last_acquisition = acquisition
                self.trigger_found = True
                self.plot.set_signal(acquisition, self.sample_rate)
                return

        # Auto sin trigger (fallback a últimas muestras)
        self.trigger_found = False
        acquisition = data[-self.display_samples:].copy()
        self.last_acquisition = acquisition
        self.plot.set_signal(acquisition, self.sample_rate)

    # =================================================================
    # MÉTODOS DE CONFIGURACIÓN Y CONTROL
    # =================================================================

    def set_time_per_division(self, value):
        self.time_per_division = float(value)
        self.display_samples = int(
            self.sample_rate
            * self.time_per_division
            * self.horizontal_divisions
        )
        self.plot.set_time_per_division(self.time_per_division)

    def set_volts_per_division(self, value):
        self.volts_per_division = float(value)
        self.plot.set_volts_per_division(self.volts_per_division)

    def set_trigger_level(self, value):
        self.trigger_level = float(value)
        self.trigger.set_level(self.trigger_level)
        self.plot.set_trigger_level(self.trigger_level)

    def set_trigger_slope(self, value):
        self.trigger_slope = value
        self.trigger.set_slope(self.trigger_slope)

    def set_trigger_mode(self, value):
        self.trigger_mode = value
        self.single_mode = (value == "Single")

    def toggle_run_stop(self):
        self.running = not self.running

    def single(self):
        self.trigger_mode = "Single"
        self.single_mode = True
        self.running = True
        self.trigger_found = False
        self.last_acquisition = None
        self.buffer.clear()

    # =================================================================
    # CIERRE
    # =================================================================

    def closeEvent(self, event):
        self.audio.stop_stream()
        event.accept()