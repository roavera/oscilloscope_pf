"""FastAct: capturas disparadas + mapa de persistencia del display."""
from time import monotonic
import numpy as np

from acquisition.fastact_density import FastActDensity


class FastActMixin:
    def _reset_fastact(self):
        self._fastact_density = FastActDensity()
        self._fastact_last_refresh = monotonic()
        self._fastact_last_trigger_time = None
        self._auto_free_running = False
        self._last_high_resolution_factor = 1
        self.plot.clear_fastact()

    def _process_fastact_captures(self, data, first_sample, raw_data=None):
        """Procesa un lote limitado; los eventos se deduplican por ID absoluto."""
        if self._fastact_density is None:
            self._reset_fastact()
        if self._pending_captures is None and data is not None:
            self._pending_captures = self.capture_sequence.captures(
                data, first_sample, self.display_samples, self.trigger,
                self.trigger_channel, raw_data=raw_data,
                holdoff=self.trigger_holdoff, sample_rate=self.sample_rate,
            )

        now = monotonic()
        self._fastact_density.fade(max(0.0, now - self._fastact_last_refresh))
        self._fastact_last_refresh = now
        captured = 0
        self.trigger_found = False
        # Evita saturar el hilo GUI con miles de capturas por segundo.
        for _ in range(min(8, self.max_captures_per_tick)):
            capture = next(self._pending_captures, None) if self._pending_captures is not None else None
            if capture is None:
                self._pending_captures = None
                break
            # Solo llegan capturas con cruces reales del trigger. Auto no
            # introduce ventanas de fase arbitraria en el mapa de densidad.
            self._auto_free_running = False
            self.trigger_found = True
            self._last_trigger_time = now
            self._fastact_last_trigger_time = now
            self._accept_fastact_capture(
                capture.samples, capture.trigger_sample,
                capture.raw_samples, capture.raw_trigger_sample,
            )
            captured += 1
            if self.trigger_mode == "Single":
                self.running = False
                self.single_mode = True
                self.display_timer.stop()
                self._pending_captures = None
                break

        # En FastAct, Auto y Normal solo acumulan capturas DISPARADAS.
        # Si no existe un cruce válido, no inventamos un barrido libre:
        # conservamos el último disparo y dejamos desvanecer la densidad.
        # Esto no altera el comportamiento Auto de Sampling/Peak/Hi-Res.

        # Redibujar también cuando no hay disparos: la persistencia debe
        # desvanecerse con el tiempo mientras la adquisición esté en RUN.
        if captured or self._fastact_density.captures:
            visible = tuple(bool(self.plot.channel_visible[ch]) for ch in (1, 2))
            self.plot.set_fastact_image(self._fastact_density.image(visible))
        if captured:
            self.capture_archive.publish()
            self.export_controls.refresh()
        self.update_controls_state()

    def _accept_fastact_capture(self, acquisition, trigger_sample,
                                raw_acquisition, raw_trigger_sample):
        # Las muestras ya vienen calibradas; el mapa usa exactamente las
        # mismas escalas/posiciones que OscilloscopePlot.
        scales = tuple(self.plot.channel_scales[ch] for ch in (1, 2))
        positions = tuple(self.plot.channel_positions[ch] for ch in (1, 2))
        self._fastact_density.add_capture(acquisition, scales, positions)
        self._last_high_resolution_factor = 1
        self._last_render_trigger_sample = trigger_sample
        self._last_display_buffer = None
        self._last_raw_display_buffer = None
        self._last_trigger_index = None
        self._render_acquisition(acquisition, trigger_sample)
        if raw_acquisition is not None:
            self._archive_raw(raw_acquisition, raw_trigger_sample)
        # En este modo MATH es la operación instantánea, sin filtros de Avg.
        try:
            math = self.math_processor.math.evaluate(acquisition, self.sample_rate)
            self._math_error = None
            self._render_math(math.values, trigger_sample)
        except ValueError as exc:
            self._math_error = str(exc)
            self._render_math(None)

    def _redraw_fastact(self):
        # Reposiciona la traza al cambiar el origen temporal o al congelar.
        if self.last_acquisition is not None:
            self.plot.set_signal(self.last_acquisition, self.sample_rate,
                                 trigger_sample=self._last_render_trigger_sample)
            self._redraw_math()
        if self._fastact_density is not None:
            visible = tuple(bool(self.plot.channel_visible[ch]) for ch in (1, 2))
            self.plot.set_fastact_image(self._fastact_density.image(visible))

    def _clear_fastact_for_vertical_change(self):
        # La imagen está rasterizada en divisiones: cambiar Volt/div/Pos
        # invalida las coordenadas anteriores, pero no la captura congelada.
        if self.acquisition_processor.get_mode() == "fastact":
            self._reset_fastact()
