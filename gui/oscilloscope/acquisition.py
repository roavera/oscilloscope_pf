"""Ciclo de vida de las fuentes, recepción estéreo y RUN/STOP/SINGLE."""

import numpy as np
from acquisition.acquisition_manager import AcquisitionManager
from acquisition.stereo_buffer import StereoBuffer


class AcquisitionMixin:
    """Colabora sobre el estado único inicializado por OscilloscopeWidget."""

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
        self.capture_archive.clear()
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
        self.last_envelope = None
        self._last_display_buffer = None
        self._last_trigger_index = None
        self._last_fractional_offset = 0.0
        self.plot.clear_signal()
        self.last_math = None
        self._last_math_reference = None
        self._last_peak_capture = None
        self._last_peak_config = None


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
        self.single_mode = False
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


    def shutdown(self):
        if self._closed:
            return

        self.display_timer.stop()
        self.running = False

        with self._buffer_lock:
            self._closed = True

        # Fuera del lock para no bloquear el callback al cerrar.
        self.acquisition.stop()
