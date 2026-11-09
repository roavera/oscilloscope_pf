"""Navegación temporal: zoom y delay sin alterar la adquisición/trigger.

Sólo en STOP se explora el historial RAW del modo Sampling. Para Average,
Envelope, Peak Detect y Hi-Res el zoom actúa sobre la captura procesada
actual, sin recalcular ni inventar muestras. En RUN se muestra x1, delay 0.
"""
import numpy as np

from horizontal_navigation import HorizontalView


class HorizontalMixin:
    def _apply_horizontal_view(self):
        self.plot.set_horizontal_view(
            self.time_per_division,
            self.trigger_position,
            self.horizontal_delay_seconds,
            self.horizontal_zoom_factor,
        )
        if not self.running:
            self._redraw_frozen_horizontal()

    def set_horizontal_reference(self, reference):
        if reference not in ("Left", "Center", "Right", "Custom"):
            return
        self.horizontal_reference = reference
        self.controls.horizontal_controls.set_reference(reference)
        positions = {"Left": -6.0, "Center": 0.0, "Right": 6.0}
        if reference in positions:
            self.set_horizontal_position(positions[reference])
        else:
            self._apply_horizontal_view()

    def set_horizontal_delay(self, seconds):
        value = float(seconds)
        if not np.isfinite(value) or self.running or self.acquisition_processor.get_mode() in ("roll", "fastact"):
            self.controls.horizontal_controls.set_delay_seconds(self.horizontal_delay_seconds)
            return
        self.horizontal_delay_seconds = float(np.clip(value, -0.5, 0.5))
        self.controls.horizontal_controls.set_delay_seconds(self.horizontal_delay_seconds)
        self._apply_horizontal_view()

    def set_horizontal_zoom(self, factor):
        value = float(factor)
        if not np.isfinite(value) or self.running or self.acquisition_processor.get_mode() in ("roll", "fastact"):
            self.controls.horizontal_controls.set_zoom_factor(self.horizontal_zoom_factor)
            return
        self.horizontal_zoom_factor = float(np.clip(value, 1.0, 20.0))
        self.controls.horizontal_controls.set_zoom_factor(self.horizontal_zoom_factor)
        self._apply_horizontal_view()

    def _clear_frozen_horizontal(self):
        self._frozen_horizontal_data = None
        self._frozen_horizontal_anchor = None

    def _resume_horizontal_view(self):
        """Vuelve a la visualización LIVE, sin alterar Time/div ni referencia."""
        self._clear_frozen_horizontal()
        self.horizontal_zoom_factor = 1.0
        self.horizontal_delay_seconds = 0.0
        self.controls.horizontal_controls.set_zoom_factor(1.0)
        self.controls.horizontal_controls.set_delay_seconds(0.0)
        self._apply_horizontal_view()

    def _freeze_horizontal_history(self):
        """Copia hasta 1 segundo de muestras *sin procesar* para Sampling en STOP.

        La copia se hace una sola vez. Se preserva la captura/CSV originales;
        sólo el gráfico usa estos datos calibrados para la inspección.
        """
        self._clear_frozen_horizontal()
        if (self.running or self.acquisition_processor.get_mode() != "sampling"
                or self.last_acquisition is None or self._last_display_buffer is None):
            return
        with self._buffer_lock:
            raw = self.buffer.get_data()
            total = int(self.buffer.total_samples)
        if len(raw) < 2:
            return
        first_absolute = total - len(raw)
        if self._last_trigger_index is not None and self._last_sampling_trigger_id >= 0:
            anchor = (float(self._last_sampling_trigger_id) +
                      float(self._last_fractional_offset) - first_absolute)
        else:
            # Trigger Auto sin cruce: t=0 es referencia visual, no un trigger.
            anchor = (len(raw) - 1 - (1.0 - self.trigger_position) * self.display_samples)
        if not 0 <= anchor < len(raw):
            return  # No hay contexto histórico suficiente; queda la captura actual.
        self._frozen_horizontal_data = self.voltage_calibration.apply(raw, self.acquisition.source)
        self._frozen_horizontal_anchor = anchor
        self._redraw_frozen_horizontal()

    def _redraw_frozen_horizontal(self):
        samples = self._frozen_horizontal_data
        anchor = self._frozen_horizontal_anchor
        if samples is None or anchor is None:
            return
        view = HorizontalView(
            self.time_per_division,
            self.horizontal_divisions,
            self.trigger_position,
            self.horizontal_delay_seconds,
            self.horizontal_zoom_factor,
        )
        section = view.sample_interval(len(samples), self.sample_rate, anchor)
        if section is None:
            self.plot.clear_signal()
            self.plot.clear_math()
            return
        begin, end, local_anchor = section
        self.plot.set_signal(samples[begin:end], self.sample_rate, trigger_sample=local_anchor)
        # No superponer MATH calculada con otra ventana de adquisición.
        self.plot.clear_math()
