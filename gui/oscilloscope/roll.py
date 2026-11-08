"""Estrategia de visualización Roll, independiente de los disparos."""
import numpy as np
from acquisition.roll_history import RollHistory


class RollMixin:
    def _reset_roll_history(self):
        self._roll_history = RollHistory(
            self.sample_rate,
            self.time_per_division * self.horizontal_divisions,
            max_points=2048,
        )
        # En Roll no fabricamos CSV a partir de bins promediados.
        self.capture_archive.clear()
        self.last_acquisition = None
        self.last_envelope = None
        self.last_math = None
        self._last_display_buffer = None
        self._last_raw_display_buffer = None
        self._last_trigger_index = None
        self._last_render_trigger_sample = None
        self._last_high_resolution_factor = 1
        self.plot.clear_signal()

    def _process_roll_data(self, calibrated_samples):
        if self._roll_history is None:
            self._reset_roll_history()
        self._roll_history.append(calibrated_samples)
        self.trigger_found = False
        self._auto_free_running = False
        self._redraw_roll()
        # SINGLE en Roll significa congelar una actualización, sin trigger.
        if self.trigger_mode == 'Single':
            self.running = False
            self.display_timer.stop()
        self.update_controls_state()

    def _redraw_roll(self):
        if self._roll_history is None:
            return
        points, offsets = self._roll_history.view()
        if not len(points):
            self.last_acquisition = None
            self.last_math = None
            self.plot.clear_signal()
            return
        self.last_acquisition = points.copy()
        self.last_envelope = None
        self._last_render_trigger_sample = None
        self.plot.set_roll_signal(points, offsets)
        self._redraw_roll_math(points, offsets)

    def _redraw_roll_math(self, points, offsets):
        try:
            result = self.math_processor.math.evaluate(points, self.sample_rate)
        except ValueError as exc:
            self._math_error = str(exc)
            self.last_math = None
            self.plot.clear_math()
        else:
            self._math_error = None
            self.last_math = np.asarray(result.values, dtype=np.float32).copy()
            self.plot.set_roll_math_signal(self.last_math, offsets)
        self._update_math_status()
