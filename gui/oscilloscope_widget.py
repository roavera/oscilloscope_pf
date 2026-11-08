"""Punto de entrada público del osciloscopio de dos canales."""

from threading import Lock
from time import monotonic

from PySide6.QtCore import QTimer, Slot, Signal, Qt
from PySide6.QtWidgets import QApplication, QWidget

from acquisition.acquisition_manager import AcquisitionManager
from acquisition.stereo_buffer import StereoBuffer
from acquisition.voltage_calibration import VoltageCalibration
from acquisition.acquisition_processor import AcquisitionProcessor
from acquisition.capture_sequence import CaptureSequence
from exporting.capture_export import CaptureArchive
from processing.math_processor import MathTraceProcessor
from trigger.edge_trigger import Edge_Trigger
from gui.controls import OscilloscopeControls
from gui.oscilloscope_plot import OscilloscopePlot
from gui.widgets.export_controls import ExportControls
from gui.oscilloscope.interface import InterfaceMixin
from gui.oscilloscope.acquisition import AcquisitionMixin
from gui.oscilloscope.processing import ProcessingMixin
from gui.oscilloscope.display import DisplayMixin
from gui.oscilloscope.math_trace import MathTraceMixin
from gui.oscilloscope.roll import RollMixin
from gui.oscilloscope.controls import ControlsMixin


class OscilloscopeWidget(
    InterfaceMixin,
    AcquisitionMixin,
    ProcessingMixin,
    DisplayMixin,
    MathTraceMixin,
    RollMixin,
    ControlsMixin,
    QWidget,
):
    acquisition_state_changed = Signal(str)
    acquisition_error = Signal(str)
    _reader_state = Signal(int, str)
    _reader_error = Signal(int, object)

    def __init__(self, parent=None):
        super().__init__(parent)

        # ============================================================
        # ADQUISICIÓN
        # ============================================================

        self.capture_archive = CaptureArchive()
        self.sample_rate = 48000
        self.blocksize = 2048
        self.channels = 2
        self.trigger_channel = 1
        self.ch2_volts_per_division = 0.02
        self.ch2_position_divisions = 0.0

        # ============================================================
        # PANTALLA Y ESCALAS
        # ============================================================

        self.horizontal_divisions = 12
        self.vertical_divisions = 8

        self.time_per_division = 0.001
        self.volts_per_division = 0.02

        # Origen del eje temporal, en segundos.
        self.horizontal_position = 0.0

        # Posición del disparo respecto del centro, en divisiones.
        self.horizontal_position_divisions = 0.0

        # Posición vertical de la traza, en divisiones.
        self.vertical_position_divisions = 0.0

        # Desplazamiento del rango visible del eje Y, en voltios.
        self.vertical_offset = 0.0

        self.display_samples = max(
            2,
            int(
                self.sample_rate
                * self.time_per_division
                * self.horizontal_divisions
            ),
        )

        # ============================================================
        # TRIGGER
        # ============================================================

        self.trigger_level = 0.0
        self.trigger_slope = "Rising"
        self.trigger_position = 0.5
        self.trigger_mode = "Auto"

        # ============================================================
        # ESTADO
        # ============================================================

        self.running = True
        self.single_mode = False
        self.trigger_found = False
        self.last_acquisition = None
        self.last_envelope = None
        self._last_high_resolution_factor = 1
        self._last_peak_capture = None
        self._last_peak_config = None
        self._last_render_trigger_sample = None

        self._closed = False
        self._audio_error = None
        self._new_data = False
        self._source_generation = 0
        self._connection_state = "stopped"
        self._pending_discontinuity = False

        self._buffer_lock = Lock()

        # Pares estéreo de la última adquisición para cambiar el recorte
        # horizontal incluso en STOP.
        self._last_display_buffer = None
        self._last_trigger_index = None
        self._last_fractional_offset = 0.0

        # ============================================================
        # COMPONENTES
        # ============================================================

        self.buffer = StereoBuffer(self.sample_rate)  # Muestras PCM24 normalizadas
        self.voltage_calibration = VoltageCalibration()
        self._last_raw_display_buffer = None
        self._roll_history = None
        
        # Procesador de modos de adquisición
        self.acquisition_processor = AcquisitionProcessor()
        self.acquisition_processor.set_mode("sampling")
        self.math_processor = MathTraceProcessor(self.acquisition_processor.get_config())
        self.last_math = None
        self._pending_math_result = None
        self._last_math_reference = None
        self._math_error = None
        self.capture_sequence = CaptureSequence()
        self._last_sampling_trigger_id = -1
        self._last_snapshot_end = 0
        self._pending_captures = None
        self.max_captures_per_tick = 32
        self.auto_timeout = 0.15
        self._last_trigger_time = monotonic()
        self._auto_free_running = False

        self.acquisition = AcquisitionManager(
            source=AcquisitionManager.AUDIO,
            sample_rate=self.sample_rate,
            channels=self.channels,
            blocksize=self.blocksize,
        )

        self.trigger = Edge_Trigger(
            level=self.trigger_level,
            slope=self.trigger_slope,
            position=self.trigger_position,
        )

        self.controls = OscilloscopeControls()

        self.plot = OscilloscopePlot(
            horizontal_divisions=self.horizontal_divisions,
            vertical_divisions=self.vertical_divisions,
            time_per_division=self.time_per_division,
            volts_per_division=self.volts_per_division,
            trigger_level=self.trigger_level,
            trigger_position=self.trigger_position,
            horizontal_position=self.horizontal_position,
            vertical_offset=self.vertical_offset,
        )

        self.controls.ch2_controls.set_volts_per_division(self.ch2_volts_per_division)
        self.controls.ch2_controls.set_position(self.ch2_position_divisions)
        self.plot.set_channel_settings(2, scale=self.ch2_volts_per_division)
        self.plot.set_calibration_label(
            self.voltage_calibration.status(self.acquisition.source),
            in_volts=self.voltage_calibration.has_volts(self.acquisition.source),
        )
        self.cursor_controls = self.controls.cursor_controls
        self.create_interface()
        self.export_controls = ExportControls(self)
        self.controls.layout().insertWidget(0, self.export_controls)
        self.connect_signals()

        # La interfaz se actualiza desde el hilo de Qt.
        self.display_timer = QTimer(self)
        self.display_timer.setInterval(40)
        self.display_timer.timeout.connect(self.process_data)

        self.controls.sync_settings(self)
        self.controls.set_simulator_visible(False)
        self.set_vertical_position(
            self.vertical_position_divisions
        )

        self.set_horizontal_position(
            self.horizontal_position_divisions
        )

        self.update_controls_state()

        app = QApplication.instance()

        if app is not None:
            app.aboutToQuit.connect(self.shutdown)

        self._reader_state.connect(
            self._on_reader_state, Qt.ConnectionType.QueuedConnection
        )
        self._reader_error.connect(
            self._on_reader_error, Qt.ConnectionType.QueuedConnection
        )
        self.start_acquisition()


    @Slot(int, str)
    def _on_reader_state(self, generation, state):
        AcquisitionMixin._on_reader_state(self, generation, state)

    @Slot(int, object)
    def _on_reader_error(self, generation, error):
        AcquisitionMixin._on_reader_error(self, generation, error)

    @Slot()
    def process_data(self):
        ProcessingMixin.process_data(self)

    @Slot()
    def shutdown(self):
        AcquisitionMixin.shutdown(self)

    def closeEvent(self, event):
        self.shutdown()
        event.accept()

