"""Selección de capturas, modos de adquisición y archivo de muestras originales."""

from time import monotonic
import numpy as np
from acquisition.modes.envelope import EnvelopeResult
from acquisition.modes.peak_detect import PeakDetectResult
from acquisition.modes.high_resolution import effective_high_resolution_factor
from exporting.capture_export import raw_capture


class ProcessingMixin:
    """Colabora sobre el estado único inicializado por OscilloscopeWidget."""

    def _reset_processing(self, *, use_buffered=False):
        """Reinicia acumulación e IDs sin borrar la captura visible."""
        self.capture_archive.reset()
        self.acquisition_processor.reset()
        self.math_processor.configure_acquisition(self.acquisition_processor.get_config())
        self.math_processor.reset()
        self._pending_math_result = None
        with self._buffer_lock:
            minimum = self.buffer.total_samples
            if use_buffered:
                minimum -= self.buffer.valid_samples
        self.capture_sequence.reset(minimum_trigger=minimum)
        self._last_sampling_trigger_id = minimum - 1
        self._last_snapshot_end = minimum
        self._pending_captures = None
        self._last_trigger_time = monotonic()
        self._auto_free_running = False


    def reset_accumulation(self, _checked=False):
        """Reinicia los historiales, manteniendo modo, N, conexión y RUN/STOP."""
        if self._closed:
            return
        with self._buffer_lock:
            self._new_data = False
            # El reinicio siguiente ya atiende cualquier corte recibido.
            self._pending_discontinuity = False
        self._reset_processing()
        self.trigger_found = False
        self.update_controls_state()


    def _clear_trigger_history(self, *, preserve_display=False):
        """Reinicia el procesamiento; puede conservar la última captura visible."""
        self.trigger_found = False
        self.trigger.fractional_offset = 0.0
        if not preserve_display:
            self.last_acquisition = None
            self.last_envelope = None
            self._last_display_buffer = None
            self._last_raw_display_buffer = None
            self._last_trigger_index = None
            self._last_fractional_offset = 0.0
            self.plot.clear_signal()
            self.last_math = None
            self.capture_archive.clear()
        self._reset_processing(use_buffered=True)


    def set_acquisition_mode(self, mode):
        if mode not in ("sampling", "peak_detect", "average", "envelope", "high_resolution"):
            raise ValueError(f"Modo no disponible: {mode}")
        if mode != self.acquisition_processor.get_mode():
            self.acquisition_processor.set_mode(mode)
            self._reset_processing()
            self.trigger_found = False
        self.controls.set_acquisition_mode(mode)
        self.update_controls_state()


    def set_high_resolution_factor(self, factor):
        if factor != self.acquisition_processor.get_high_resolution_factor():
            self.acquisition_processor.set_high_resolution_factor(factor)
            self._reset_processing()
            self.trigger_found = False
            if self.acquisition_processor.get_mode() == "high_resolution":
                self._redraw_last_acquisition()
        if factor != 1:
            self.controls.acquisition_controls.set_high_resolution_factor(factor)
        self.update_controls_state()

    def set_peak_bucket_size(self, count):
        self.acquisition_processor.configure(peak_bucket_size=count)
        self._reset_processing()
        self.trigger_found = False
        self.controls.acquisition_controls.set_peak_bucket_size(count)
        self.update_controls_state()


    def set_average_count(self, count):
        if count != self.acquisition_processor.get_average_count():
            self.acquisition_processor.set_average_count(count)
            self._reset_processing()
            self.trigger_found = False
        self.controls.acquisition_controls.set_average_count(count)
        self.update_controls_state()


    def set_envelope_count(self, count):
        if count != self.acquisition_processor.get_envelope_count():
            self.acquisition_processor.set_envelope_count(count)
            self._reset_processing()
            self.trigger_found = False
        self.controls.acquisition_controls.set_envelope_count(count)
        self.update_controls_state()


    def process_data(self):
        # Incluso una señal timeout ya encolada debe respetar STOP.
        if self._closed or not self.running:
            return

        # Una discontinuidad invalida también las capturas pendientes.
        with self._buffer_lock:
            discontinuity = self._pending_discontinuity
            self._pending_discontinuity = False
        if discontinuity:
            self._clear_trigger_history(preserve_display=True)
            self.update_controls_state()

        # Distribuir un lote grande en varios ticks, sin repetir capturas.
        if self._pending_captures is not None:
            self._process_triggered_captures(None, None)
            return

        with self._buffer_lock:
            if not self._new_data:
                return
            total = self.buffer.total_samples
            # Conservar el solapamiento necesario para pre/post-trigger y
            # cruces entre bloques, sin copiar un segundo entero en cada tick.
            count = max(0, total - self._last_snapshot_end) + self.display_samples + 2
            raw_data = self.buffer.get_data(count)
            first_sample = total - len(raw_data)
            self._last_snapshot_end = total
            self._new_data = False

        # Una sola conversión RAW -> V antes de trigger, modos y MATH.
        # El búfer retiene siempre los float32 PCM24 originales.
        data = self.voltage_calibration.apply(raw_data, self.acquisition.source)

        if len(data) < self.display_samples:
            return

        if self.acquisition_processor.get_mode() in ("average", "envelope"):
            self._process_triggered_captures(data, first_sample, raw_data=raw_data)
            return

        # Detector compartido por Sampling, Peak Detect y High Resolution.
        # Average/Envelope usan el mismo trigger a través de CaptureSequence.
        # La captura y sus datos originales NO se filtran aquí.
        trigger_index = self.trigger.find(
            data[:, self.trigger_channel - 1],
            self.display_samples,
        )

        acquisition = None
        raw_acquisition = None
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
            raw_acquisition = self.trigger.capture(
                raw_data, trigger_index, self.display_samples,
            )

        self.trigger_found = acquisition is not None

        if not self.trigger_found:
            # Normal y Single conservan la última traza
            # mientras esperan un disparo válido.
            if self.trigger_mode in ("Normal", "Single"):
                self.update_controls_state()
                return

            # Auto espera brevemente un disparo nuevo antes del barrido libre.
            # Una vez vencida la espera, cada bloque nuevo actualiza la pantalla.
            if monotonic() - self._last_trigger_time < self.auto_timeout:
                self._auto_free_running = False
                self.update_controls_state()
                return
            self._auto_free_running = True
            # Auto sin disparo.
            self._last_display_buffer = data
            self._last_raw_display_buffer = raw_data
            self._last_trigger_index = None
            self._last_fractional_offset = 0.0

            acquisition = data[-self.display_samples:].copy()
            self._show_acquisition(
                acquisition, raw_acquisition=raw_data[-self.display_samples:].copy()
            )

        else:
            self._last_trigger_time = monotonic()
            self._auto_free_running = False
            self._last_sampling_trigger_id = first_sample + trigger_index
            # Guarda el contexto del disparo para poder volver
            # a recortar esta adquisición sin buscar otro cruce.
            self._last_display_buffer = data
            self._last_raw_display_buffer = raw_data
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
                raw_acquisition=raw_acquisition,
            )

            if self.trigger_mode == "Single":
                self.running = False
                self.display_timer.stop()

        self.update_controls_state()


    def _process_triggered_captures(self, data, first_sample, raw_data=None):
        """Acumula un lote acotado por tick; Auto no mezcla barridos libres."""
        if self._pending_captures is None:
            self._pending_captures = self.capture_sequence.captures(
                data, first_sample, self.display_samples, self.trigger, self.trigger_channel,
                raw_data=raw_data,
            )
        result = None
        reference = None
        self.trigger_found = False
        for _ in range(self.max_captures_per_tick):
            capture = next(self._pending_captures, None)
            if capture is None:
                self._pending_captures = None
                break
            result = self._process_acquisition(capture.samples)
            self._archive_raw(capture.raw_samples, capture.raw_trigger_sample)
            reference = capture.trigger_sample
            self.trigger_found = True
            count, target = self.acquisition_processor.get_progress()
            if self.trigger_mode == "Single" and count >= target:
                self.running = False
                self.display_timer.stop()
                self._pending_captures = None
                break
        if result is not None:
            self._render_processed(result, reference)
        self.update_controls_state()


    def _archive_raw(self, samples, trigger_sample):
        config = self.acquisition_processor.get_config()
        target = {"average": config.average_count, "envelope": config.envelope_count}.get(config.mode, 1)
        capture = raw_capture(samples, self.sample_rate, trigger_sample, self.acquisition.source, config)
        self.capture_archive.add(capture, target)


    def _process_acquisition(self, acquisition):
        self._last_high_resolution_factor = (
            effective_high_resolution_factor(
                len(acquisition), self.acquisition_processor.get_high_resolution_factor()
            )
            if self.acquisition_processor.get_mode() == "high_resolution" else 1
        )
        results = [
            self.acquisition_processor.process(acquisition[:, ch - 1], channel=ch)
            for ch in (1, 2)
        ]
        try:
            self.math_processor.configure_acquisition(self.acquisition_processor.get_config())
            self._pending_math_result = self.math_processor.process(acquisition, self.sample_rate)
            self._math_error = None
        except ValueError as exc:
            self._pending_math_result = None
            self._math_error = str(exc)
        if self.acquisition_processor.get_mode() == "peak_detect":
            self._last_peak_capture = acquisition.copy()
            self._last_peak_config = self.acquisition_processor.get_config()
            return PeakDetectResult(
                np.column_stack([result.minimum for result in results]),
                np.column_stack([result.maximum for result in results]),
                results[0].sample_positions.copy(), results[0].original_count,
            )
        if self.acquisition_processor.get_mode() == "envelope":
            return EnvelopeResult(
                np.column_stack([result.minimum for result in results]),
                np.column_stack([result.maximum for result in results]),
            )
        return np.column_stack(results)


    def _show_acquisition(self, acquisition, trigger_sample=None, *, raw_acquisition=None):
        """
        Procesa y representa una captura del osciloscopio.

        El trigger ya seleccionó la ventana temporal.
        El procesador aplica el modo de adquisición activo.
        """

        processed = self._process_acquisition(acquisition)
        self._archive_raw(
            acquisition if raw_acquisition is None else raw_acquisition,
            trigger_sample,
        )
        self._render_processed(processed, trigger_sample)
