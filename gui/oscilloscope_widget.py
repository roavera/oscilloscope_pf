"""Widget compatible con el AcquisitionManager asíncrono.

USB: connect_blackpill(port=None, simulated=False); reconnect_acquisition();
disconnect_acquisition(). Señales públicas: acquisition_state_changed(str),
acquisition_error(str). La ventana principal debe aceptar is_connecting como
estado válido al cambiar de fuente y habilitar su menú USB.

STOP/SINGLE congelan la pantalla; disconnect_acquisition() detiene la fuente.
Se muestran CH1 y CH2 sincronizados. Las muestras USB siguen normalizadas, no calibradas en voltios.
"""

from threading import Lock

import numpy as np

from PySide6.QtCore import QSettings, QTimer, Slot, Signal, Qt
from PySide6.QtWidgets import (
    QApplication,
    QHBoxLayout,
    QSplitter,
    QLayout,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from acquisition.acquisition_manager import AcquisitionManager
from acquisition.stereo_buffer import StereoBuffer
from acquisition.acquisition_processor import AcquisitionProcessor
from acquisition.capture_sequence import CaptureSequence
from trigger.edge_trigger import Edge_Trigger

from gui.controls import OscilloscopeControls
from gui.oscilloscope_plot import OscilloscopePlot

class OscilloscopeWidget(QWidget):
    acquisition_state_changed = Signal(str)
    acquisition_error = Signal(str)
    _reader_state = Signal(int, str)
    _reader_error = Signal(int, object)


    def __init__(self, parent=None):
        super().__init__(parent)

        # ============================================================
        # ADQUISICIÓN
        # ============================================================

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

        self.buffer = StereoBuffer(self.sample_rate)
        
        # Procesador de modos de adquisición
        self.acquisition_processor = AcquisitionProcessor()
        self.acquisition_processor.set_mode("sampling")
        self.capture_sequence = CaptureSequence()
        self._last_sampling_trigger_id = -1

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
        self.cursor_controls = self.controls.cursor_controls
        self.create_interface()
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

    # ================================================================
    # INTERFAZ
    # ================================================================

    def create_interface(self):
        """Display y panel lateral fijo, sin área de desplazamiento."""
        self._layout_settings = QSettings("OsciloscopioPF", "Osciloscopio")

        layout = QHBoxLayout(self)
        layout.setContentsMargins(4, 4, 4, 4)
        layout.setSpacing(0)

        self.splitter = QSplitter(Qt.Orientation.Horizontal, self)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.setHandleWidth(5)

        self.plot.setMinimumWidth(320)
        self.splitter.addWidget(self.plot)

        # QWidget común: todos los controles de la página quedan en pantalla.
        # Se conserva el nombre del atributo por compatibilidad.
        self.controls_scroll = QWidget(self.splitter)
        self.controls_scroll.setMinimumWidth(400)
        self.controls_scroll.setSizePolicy(
            QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Expanding
        )
        right_layout = QVBoxLayout(self.controls_scroll)
        right_layout.setContentsMargins(2, 2, 2, 2)
        right_layout.setSpacing(0)
        right_layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)
        right_layout.addWidget(self.controls)
        self.splitter.addWidget(self.controls_scroll)

        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 0)
        layout.addWidget(self.splitter)
        # El mínimo natural impide reducir la ventana hasta recortar controles.
        layout.setSizeConstraint(QLayout.SizeConstraint.SetMinimumSize)

        self._restoring_splitter = True
        self.splitter.splitterMoved.connect(self._save_splitter_width)
        QTimer.singleShot(0, self._restore_splitter_width)

    def _restore_splitter_width(self):
        """Recupera el ancho lateral sin reducir demasiado el gráfico."""
        width = self._layout_settings.value(
            "layout/sidebar_width_v2", 460, type=int
        )
        width = max(400, min(600, width))
        available = max(0, self.splitter.width() - self.splitter.handleWidth())
        width = min(width, max(400, available - 320))
        self.splitter.setSizes([max(320, available - width), width])
        self._restoring_splitter = False

    def _save_splitter_width(self, position, index):
        """Guarda el ancho elegido arrastrando el separador."""
        if not self._restoring_splitter:
            self._layout_settings.setValue(
                "layout/sidebar_width_v2", self.splitter.sizes()[1]
            )

    # ================================================================
    # CONEXIONES
    # ================================================================

    def connect_signals(self):
        self.controls.simulator_settings_changed.connect(
            self._on_simulator_settings_changed
        )

        self.cursor_controls.settings_changed.connect(self.plot.set_cursor_mode)
        self.plot.cursor_readout_changed.connect(self.cursor_controls.set_readout)
        self.controls.ch2_controls.volts_per_division_changed.connect(self.set_ch2_volts_per_division)
        self.controls.ch2_controls.position_changed.connect(self.set_ch2_position)
        self.plot.ch2_position_changed.connect(self.set_ch2_position)
        for ch, panel in ((1, self.controls.ch1_controls), (2, self.controls.ch2_controls)):
            panel.visibility_changed.connect(lambda visible, c=ch: self.plot.set_channel_settings(c, visible=visible))
        self.controls.trigger_controls.source_changed.connect(self.set_trigger_channel)
        self.controls.simulator_controls_ch2.settings_changed.connect(self._on_simulator_ch2_settings_changed)
        # Control horizontal.
        self.controls.time_per_division_changed.connect(
            self.set_time_per_division
        )

        self.controls.horizontal_position_changed.connect(
            self.set_horizontal_position
        )

        self.plot.horizontal_position_changed.connect(
            self.set_horizontal_position
        )

        # Control vertical.
        self.controls.volts_per_division_changed.connect(
            self.set_volts_per_division
        )

        self.controls.vertical_position_changed.connect(
            self.set_vertical_position
        )

        self.plot.vertical_position_changed.connect(
            self.set_vertical_position
        )

        # Trigger desde el panel.
        self.controls.trigger_level_changed.connect(
            self.set_trigger_level
        )

        self.controls.trigger_slope_changed.connect(
            self.set_trigger_slope
        )

        self.controls.trigger_mode_changed.connect(
            self.set_trigger_mode
        )

        # Trigger desde el gráfico.
        self.plot.trigger_level_changed.connect(
            self.set_trigger_level
        )

        # Adquisición.
        self.controls.run_clicked.connect(self.run)
        self.controls.stop_clicked.connect(self.stop)

        self.controls.single_clicked.connect(
            self.single
        )
        
        # Selector de modos de adquisición
        self.controls.acquisition_mode_changed.connect(
            self.set_acquisition_mode
        )
        self.controls.acquisition_controls.average_count_changed.connect(
            self.set_average_count
        )


    # ================================================================
    # ADQUISICIÓN
    # ================================================================

    def _reset_processing(self, *, use_buffered=False):
        """Reinicia acumulación e IDs sin borrar la captura visible."""
        self.acquisition_processor.reset()
        with self._buffer_lock:
            minimum = self.buffer.total_samples
            if use_buffered:
                minimum -= self.buffer.valid_samples
        self.capture_sequence.reset(minimum_trigger=minimum)
        self._last_sampling_trigger_id = minimum - 1

    def set_acquisition_mode(self, mode):
        if mode not in ("sampling", "average"):
            raise ValueError(f"Modo no disponible: {mode}")
        if mode != self.acquisition_processor.get_mode():
            self.acquisition_processor.set_mode(mode)
            self._reset_processing()
            self.trigger_found = False
        self.controls.set_acquisition_mode(mode)
        self.update_controls_state()

    def set_average_count(self, count):
        if count != self.acquisition_processor.get_average_count():
            self.acquisition_processor.set_average_count(count)
            self._reset_processing()
            self.trigger_found = False
        self.controls.acquisition_controls.set_average_count(count)
        self.update_controls_state()

    def start_acquisition(self):
        """Solicita el arranque; USB confirma la conexión mediante señales."""
        if self._closed or self.acquisition.is_connecting or self.acquisition.is_running:
            return
        # Terminar el lector anterior ANTES de cambiar sus callbacks.
        try:
            self.acquisition.stop()
        except Exception as exc:
            self._on_reader_error(self._source_generation, exc)
            return
        with self._buffer_lock:
            self._source_generation += 1
            generation = self._source_generation
        self.reset_acquisition(self.acquisition.sample_rate)
        self.acquisition.on_state_changed = (
            lambda state: self._reader_state.emit(generation, state)
        )
        self.acquisition.on_error = (
            lambda error: self._reader_error.emit(generation, error)
        )
        self.acquisition.on_discontinuity = (
            lambda: self._on_discontinuity(generation)
        )
        self._audio_error = None
        self._connection_state = "connecting"
        self.running = False
        self.controls.set_acquisition_enabled(False)
        self.display_timer.start()
        self.update_controls_state()
        self.acquisition_state_changed.emit("connecting")
        try:
            self.acquisition.start(
                lambda data: self.on_samples_received(data, generation)
            )
        except Exception as exc:
            self._on_reader_error(generation, exc)
        else:
            # Fuentes síncronas y conexión USB que termine inmediatamente.
            self._on_reader_state(generation, self.acquisition.state)

    @Slot(int, str)
    def _on_reader_state(self, generation, state):
        if self._closed or generation != self._source_generation:
            return
        # Ignorar avisos encolados que ya fueron superados por otro estado.
        if state != self.acquisition.state or state == self._connection_state:
            return
        self._connection_state = state
        if state == "connected":
            self._audio_error = None
            self.running = True
            self.controls.set_acquisition_enabled(True)
            self.display_timer.start()
            if self.acquisition.source == AcquisitionManager.SIMULATOR:
                self._apply_simulator_panel()
        elif state == "connecting":
            self.running = False
            self.controls.set_acquisition_enabled(False)
        elif state == "error":
            self._on_reader_error(generation, self.acquisition.last_error)
            return
        else:
            self.running = False
            self.display_timer.stop()
            self.controls.set_acquisition_enabled(True)
        self.update_controls_state()
        self.acquisition_state_changed.emit(state)

    @Slot(int, object)
    def _on_reader_error(self, generation, error):
        if self._closed or generation != self._source_generation:
            return
        message = str(error) if error is not None else "Error de adquisición"
        duplicate = self._audio_error == message and self._connection_state == "error"
        self._connection_state = "error"
        self._audio_error = message
        self.running = False
        self.display_timer.stop()
        # RUN permite volver a intentar; SINGLE se valida en single().
        self.controls.set_acquisition_enabled(True)
        self.update_controls_state()
        if not duplicate:
            self.acquisition_state_changed.emit("error")
            self.acquisition_error.emit(message)

    def _on_discontinuity(self, generation):
        """Hilo lector: cortar el historial antes de agregar nuevas muestras."""
        with self._buffer_lock:
            if self._closed or generation != self._source_generation:
                return
            self.buffer.clear()
            self._new_data = False
            self._pending_discontinuity = True
        # Nunca modificar widgets ni el trigger desde este callback.

    def _clear_trigger_history(self, *, preserve_display=False):
        """Reinicia el procesamiento; puede conservar la última captura visible."""
        self.trigger_found = False
        self.trigger.fractional_offset = 0.0
        if not preserve_display:
            self.last_acquisition = None
            self._last_display_buffer = None
            self._last_trigger_index = None
            self._last_fractional_offset = 0.0
            self.plot.clear_signal()
        self._reset_processing(use_buffered=True)

    def disconnect_acquisition(self):
        """Cierra la fuente; invalida los avisos pendientes del lector anterior."""
        if self._closed:
            return
        with self._buffer_lock:
            self._source_generation += 1
        self.running = False
        self.display_timer.stop()
        try:
            self.acquisition.stop()
        except Exception as exc:
            self._on_reader_error(self._source_generation, exc)
            raise
        self._connection_state = "stopped"
        self._audio_error = None
        self.controls.set_acquisition_enabled(True)
        self.update_controls_state()
        self.acquisition_state_changed.emit("stopped")

    def reconnect_acquisition(self):
        """Reabre la fuente actual usando el puerto configurado."""
        if self._closed:
            return
        self.disconnect_acquisition()
        self.start_acquisition()

    def connect_blackpill(self, port=None, *, simulated=False):
        """port=None busca el COM automáticamente. Adquisición estéreo."""
        if self._closed:
            return
        self.disconnect_acquisition()
        self.acquisition.usb_port = port
        self.acquisition.usb_simulated = bool(simulated)
        self.change_acquisition_source(AcquisitionManager.BLACKPILL_USB)

    def change_acquisition_source(self, source, sample_rate=None):
        """Cambia la fuente. USB permanece conectando hasta recibir audio."""
        if self._closed:
            return
        if source not in self.acquisition.SAMPLE_RATES:
            raise ValueError(f"Fuente desconocida: {source}")
        rate = float(sample_rate if sample_rate is not None
                     else self.acquisition.SAMPLE_RATES[source])
        if not np.isfinite(rate) or rate <= 0:
            raise ValueError("Frecuencia de muestreo inválida")
        self.disconnect_acquisition()
        self.acquisition.change_source(source, rate)
        
        self.controls.set_simulator_visible(
            source == AcquisitionManager.SIMULATOR
        )
        self.start_acquisition()
    def _apply_simulator_panel(self):
        for channel, panel in ((0, self.controls.simulator_controls),
                               (1, self.controls.simulator_controls_ch2)):
            self._configure_simulator_channel(channel, panel.get_settings())

    def _configure_simulator_channel(self, channel, settings):
        if self.acquisition.source == AcquisitionManager.SIMULATOR and self.acquisition.is_running:
            try:
                self.configure_simulator(channel=channel, **settings)
            except (ValueError, RuntimeError) as exc:
                self.acquisition_error.emit(str(exc))

    def _on_simulator_settings_changed(self, settings):
        self._configure_simulator_channel(0, settings)

    def _on_simulator_ch2_settings_changed(self, settings):
        self._configure_simulator_channel(1, settings)

    def configure_simulator(self, channel=0, **kwargs):
        """Actualiza la señal simulada sin reiniciar la adquisición."""
        self.acquisition.configure_simulator(channel=channel, **kwargs)
        with self._buffer_lock:
            self.buffer.clear()
            self._new_data = False
        self._reset_processing()
        self.update_controls_state()

    def reset_acquisition(self, sample_rate):
        """Descarta muestras previas y actualiza la base temporal."""
        rate = float(sample_rate)
        if not np.isfinite(rate) or rate <= 0:
            raise ValueError("Frecuencia de muestreo inválida")
        with self._buffer_lock:
            self.sample_rate = rate
            self.buffer = StereoBuffer(max(1, int(np.ceil(rate))))
            self._pending_discontinuity = False
            self._new_data = False
        self._reset_processing()
        self.display_samples = max(
            2, int(self.sample_rate * self.time_per_division
                   * self.horizontal_divisions)
        )
        self.trigger_found = False
        self.single_mode = False
        self.last_acquisition = None
        self._last_display_buffer = None
        self._last_trigger_index = None
        self._last_fractional_offset = 0.0
        self.plot.clear_signal()

    def on_samples_received(self, data, generation=None):
        """Recibe pares estéreo sin descartar ni desalinear canales."""
        samples = np.asarray(data, dtype=np.float32)
        if samples.ndim != 2 or samples.shape[1] != 2:
            raise ValueError("La fuente debe entregar pares sincronizados (N, 2)")
        if samples.size == 0:
            return
        with self._buffer_lock:
            if self._closed or (generation is not None and
                                generation != self._source_generation):
                return
            self.buffer.add_samples(samples)
            self._new_data = True

    # ================================================================
    # PROCESAMIENTO
    # ================================================================

    @Slot()
    def process_data(self):
        # Incluso una señal timeout ya encolada debe respetar STOP.
        if self._closed or not self.running:
            return

        with self._buffer_lock:
            discontinuity = self._pending_discontinuity
            self._pending_discontinuity = False
            data = None
            if self.running and self._new_data:
                data = self.buffer.get_data()
                first_sample = self.buffer.total_samples - len(data)
                self._new_data = False

        if discontinuity:
            self._clear_trigger_history(preserve_display=True)
            self.update_controls_state()
        if data is None:
            return

        if len(data) < self.display_samples:
            return

        if self.acquisition_processor.get_mode() == "average":
            self._process_average_captures(data, first_sample)
            return

        trigger_index = self.trigger.find(
            data[:, self.trigger_channel - 1],
            self.display_samples,
        )

        acquisition = None
        if trigger_index is not None:
            trigger_id = first_sample + trigger_index
            if trigger_id <= self._last_sampling_trigger_id:
                trigger_index = None

        if trigger_index is not None:
            acquisition = self.trigger.capture(
                data,
                trigger_index,
                self.display_samples,
            )

        self.trigger_found = acquisition is not None

        if not self.trigger_found:
            # Normal y Single conservan la última traza
            # mientras esperan un disparo válido.
            if self.trigger_mode in ("Normal", "Single"):
                self.update_controls_state()
                return

            # Auto sin disparo.
            self._last_display_buffer = data
            self._last_trigger_index = None
            self._last_fractional_offset = 0.0

            acquisition = data[-self.display_samples:].copy()
            self._show_acquisition(acquisition)

        else:
            self._last_sampling_trigger_id = first_sample + trigger_index
            # Guarda el contexto del disparo para poder volver
            # a recortar esta adquisición sin buscar otro cruce.
            self._last_display_buffer = data
            self._last_trigger_index = trigger_index
            self._last_fractional_offset = (
                self.trigger.fractional_offset
            )

            samples_before = int(
                self.display_samples * self.trigger.position
            )

            trigger_sample = (
                samples_before + self._last_fractional_offset
            )

            self._show_acquisition(
                acquisition,
                trigger_sample=trigger_sample,
            )

            if self.trigger_mode == "Single":
                self.running = False
                self.display_timer.stop()

        self.update_controls_state()

    def _process_average_captures(self, data, first_sample):
        """Promedia ventanas nuevas con disparo; Auto no acumula barridos libres."""
        result = None
        reference = None
        self.trigger_found = False
        for capture in self.capture_sequence.captures(
            data, first_sample, self.display_samples, self.trigger, self.trigger_channel
        ):
            result = self._process_acquisition(capture.samples)
            reference = capture.trigger_sample
            self.trigger_found = True
            count, target = self.acquisition_processor.get_progress()
            if self.trigger_mode == "Single" and count >= target:
                self.running = False
                self.display_timer.stop()
                break
        if result is not None:
            self._render_acquisition(result, reference)
        self.update_controls_state()

    def _process_acquisition(self, acquisition):
        return np.column_stack([
            self.acquisition_processor.process(acquisition[:, ch - 1], channel=ch)
            for ch in (1, 2)
        ])

    def _show_acquisition(self, acquisition, trigger_sample=None):
        """
        Procesa y representa una captura del osciloscopio.

        El trigger ya seleccionó la ventana temporal.
        El procesador aplica el modo de adquisición activo.
        """

        processed = self._process_acquisition(acquisition)
        self._render_acquisition(processed, trigger_sample)

    def _render_acquisition(self, samples, trigger_sample=None):
        """Representa muestras sin ejecutar ni acumular el algoritmo."""
        self.last_acquisition = np.asarray(samples, dtype=np.float32).copy()
        self._last_render_trigger_sample = trigger_sample
        if self.acquisition_processor.get_mode() == "average":
            self._last_display_buffer = None
        self.plot.set_signal(
            self.last_acquisition,
            self.sample_rate,
            trigger_sample=trigger_sample,
        )

    def _redraw_last_acquisition(self):
        """Redibuja usando únicamente el buffer guardado."""

        # Un promedio congelado conserva sus valores y su origen temporal.
        # Nunca sustituirlo por una captura cruda ni acumular al redibujar.
        if self.acquisition_processor.get_mode() == "average":
            if self.last_acquisition is not None:
                self.plot.set_signal(
                    self.last_acquisition, self.sample_rate,
                    trigger_sample=self._last_render_trigger_sample,
                )
            return

        data = self._last_display_buffer

        if data is None:
            return

        if self._last_trigger_index is not None:
            acquisition = self.trigger.capture(
                data,
                self._last_trigger_index,
                self.display_samples,
            )

            if acquisition is None:
                self.last_acquisition = None
                self.plot.clear_signal()
                return

            samples_before = int(
                self.display_samples * self.trigger.position
            )

            trigger_sample = (
                samples_before + self._last_fractional_offset
            )

            self._render_acquisition(
                acquisition,
                trigger_sample=trigger_sample,
            )

        else:
            # Sin disparo no existe una referencia temporal
            # para desplazar el recorte alrededor de un cruce.
            if len(data) < self.display_samples:
                self.last_acquisition = None
                self.plot.clear_signal()
                return

            acquisition = data[-self.display_samples:].copy()
            self._render_acquisition(acquisition)

    # ================================================================
    # ESTADO
    # ================================================================

    def update_controls_state(self):
        if self._connection_state == "connecting":
            self.controls.show_state(False, "CONECTANDO...")
            return
        if self._audio_error is not None:
            self.controls.show_state(
                False,
                "ERROR DE ADQUISICIÓN",
                self._audio_error,
            )
            return

        if not self.running:
            status = "STOP"

        elif self.trigger_mode == "Single":
            status = "SINGLE: esperando disparo"

        elif (
            self.trigger_mode == "Normal"
            and not self.trigger_found
        ):
            status = "RUN: esperando disparo"

        else:
            status = "RUN"

        average = self.acquisition_processor.get_mode() == "average"
        count, target = self.acquisition_processor.get_progress()
        self.controls.acquisition_controls.show_average_progress(count, target)
        if average:
            if self.running and not self.trigger_found:
                status += ": esperando disparo" if "esperando" not in status else ""
            status += f" · AVG {count}/{target}"
        self.controls.show_state(self.running, status)

    # ================================================================
    # CONTROL HORIZONTAL
    # ================================================================

    def set_time_per_division(self, value):
        value = float(value)

        if not np.isfinite(value) or value <= 0:
            return

        if value != self.time_per_division:
            self._reset_processing()
        self.time_per_division = value

        self.display_samples = max(
            2,
            int(
                self.sample_rate
                * self.time_per_division
                * self.horizontal_divisions
            ),
        )

        self.plot.set_time_per_division(value)
        self.controls.set_time_per_division(value)

        self._redraw_last_acquisition()
        self.update_controls_state()

    def set_horizontal_position(self, divisions):
        divisions = float(divisions)

        if not np.isfinite(divisions):
            return

        half_screen = self.horizontal_divisions / 2.0

        # Misma resolución que la perilla: 0.01 div.
        divisions = round(divisions, 2)

        self.horizontal_position_divisions = float(
            np.clip(divisions, -half_screen, half_screen)
        )

        # Cero divisiones corresponde al centro de la pantalla.
        self.trigger_position = (
            0.5
            + self.horizontal_position_divisions
            / self.horizontal_divisions
        )

        if self.trigger.position != self.trigger_position:
            self._reset_processing()
        self.trigger.set_position(self.trigger_position)
        self.plot.set_trigger_position(self.trigger_position)

        self.controls.set_horizontal_position(
            self.horizontal_position_divisions
        )

        self._redraw_last_acquisition()
        self.update_controls_state()

    # ================================================================
    # CONTROL VERTICAL
    # ================================================================

    def set_ch2_volts_per_division(self, value):
        value = float(value)
        if not np.isfinite(value) or value <= 0:
            return
        self.ch2_volts_per_division = value
        self.controls.ch2_controls.set_volts_per_division(value)
        self.plot.set_channel_settings(2, scale=value)
        self.update_trigger_range()

    def set_ch2_position(self, divisions):
        if not np.isfinite(divisions):
            return
        self.ch2_position_divisions = float(np.clip(round(divisions, 2), -4, 4))
        self.controls.ch2_controls.set_position(self.ch2_position_divisions)
        self.plot.set_channel_settings(2, position=self.ch2_position_divisions)
        self.update_trigger_range()

    def set_trigger_channel(self, channel):
        if channel not in (1, 2) or channel == self.trigger_channel:
            return
        self.trigger_channel = channel
        self._reset_processing()
        self.trigger_found = False
        self.plot.set_trigger_channel(channel)
        self.controls.trigger_controls.set_source(channel)
        # La última captura conserva su referencia; la próxima usa la nueva fuente.
        self.update_trigger_range()
        self.update_controls_state()

    def set_volts_per_division(self, value):
        value = float(value)

        if not np.isfinite(value) or value <= 0:
            return

        self.volts_per_division = value

        self.plot.set_volts_per_division(value)
        self.controls.set_volts_per_division(value)

        self.set_vertical_position(
            self.vertical_position_divisions
        )

    def set_vertical_position(self, divisions):
        divisions = float(divisions)

        if not np.isfinite(divisions):
            return

        slider_value = max(
            -400,
            min(400, round(divisions * 100)),
        )

        self.vertical_position_divisions = slider_value / 100.0

        # Desplaza el rango visible, sin modificar las muestras.
        self.vertical_offset = (
            -self.vertical_position_divisions
            * self.volts_per_division
        )

        self.plot.set_vertical_offset(self.vertical_offset)

        self.controls.set_vertical_position(
            self.vertical_position_divisions
        )

        self.update_trigger_range()

    # ================================================================
    # TRIGGER
    # ================================================================

    def update_trigger_range(self):
        scale = self.volts_per_division if self.trigger_channel == 1 else self.ch2_volts_per_division
        position = self.vertical_position_divisions if self.trigger_channel == 1 else self.ch2_position_divisions
        minimum = (-self.vertical_divisions / 2 - position) * scale
        maximum = (self.vertical_divisions / 2 - position) * scale

        self.controls.set_trigger_range(
            minimum,
            maximum,
        )

    def set_trigger_level(self, value):
        value = float(value)

        if not np.isfinite(value):
            return

        if value != self.trigger_level:
            self._reset_processing()
        self.trigger_level = value

        self.trigger.set_level(value)
        self.plot.set_trigger_level(value)
        self.controls.set_trigger_level(value)

        self.trigger_found = False
        self.update_controls_state()

    def set_trigger_slope(self, value):
        if value not in ("Rising", "Falling"):
            return

        if value != self.trigger_slope:
            self._reset_processing()
        self.trigger_slope = value

        self.trigger.set_slope(value)
        self.controls.set_trigger_slope(value)

        self.trigger_found = False
        self.update_controls_state()

    def set_trigger_mode(self, value):
        if value not in ("Auto", "Normal", "Single"):
            return

        if value == "Single":
            self.single()
            return

        if self.trigger_mode != value:
            self._reset_processing()
        self.trigger_mode = value
        self.single_mode = False
        self.trigger_found = False

        self.controls.set_trigger_mode(value)
        self.update_controls_state()

    # ================================================================
    # RUN / STOP Y SINGLE
    # ================================================================
    
    def run(self):
        """Inicia o reanuda la visualización del osciloscopio."""

        if self._closed or self.acquisition.is_connecting:
            return

        # Si la fuente está detenida o hubo un error,
        # intenta iniciar nuevamente la adquisición.
        if self._audio_error is not None or not self.acquisition.is_running:
            self.start_acquisition()
            return

        # Si ya está ejecutándose, no hacemos nada.
        if self.running:
            return

        # Si está seleccionado Single, arma una nueva captura.
        if self.trigger_mode == "Single":
            self.single()
            return

        self._reset_processing()
        self.running = True
        self.trigger_found = False
        self.display_timer.start()

        self.update_controls_state()

    def stop(self):
        """Congela la pantalla sin desconectar la fuente de datos."""

        if self._closed:
            return

        self.running = False
        self.display_timer.stop()
        # No limpiar ni volver a recortar la captura mostrada.
        self.update_controls_state()


    def toggle_run_stop(self):
        if self.running:
            self.stop()
        else:
            self.run()

    def single(self):
        if (self._closed or self._audio_error is not None
                or not self.acquisition.is_running):
            return

        self._reset_processing()
        self.trigger_mode = "Single"
        self.single_mode = True
        self.trigger_found = False

        # La adquisición anterior permanece visible mientras
        # se espera el nuevo disparo.
        with self._buffer_lock:
            self.buffer.clear()
            self._new_data = False

        self.running = True
        self.display_timer.start()

        self.controls.set_trigger_mode("Single")
        self.update_controls_state()

    # ================================================================
    # CIERRE
    # ================================================================

    @Slot()
    def shutdown(self):
        if self._closed:
            return

        self.display_timer.stop()
        self.running = False

        with self._buffer_lock:
            self._closed = True

        # Fuera del lock para no bloquear el callback al cerrar.
        self.acquisition.stop()

    def closeEvent(self, event):
        self.shutdown()
        event.accept()


