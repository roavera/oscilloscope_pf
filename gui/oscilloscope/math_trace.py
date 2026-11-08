"""Configuración, representación y recorte de la traza MATH."""

from copy import deepcopy
import numpy as np
from PySide6.QtCore import QSignalBlocker
from acquisition.modes.envelope import EnvelopeResult
from acquisition.modes.peak_detect import PeakDetectResult
from processing.math_processor import MathTraceProcessor


class MathTraceMixin:
    """Colabora sobre el estado único inicializado por OscilloscopeWidget."""

    def reset_math_controls(self, _checked=False):
        """Defaults de MATH; los canales y sus acumulaciones se conservan."""
        panel = self.controls.math_controls
        widgets = (panel.scale_combo, panel.position_input, panel.visible_checkbox)
        blockers = [QSignalBlocker(widget) for widget in widgets]
        try:
            panel.scale_combo.setCurrentIndex(panel.scale_combo.findData(0.02))
            panel.position_input.setValue(0.0)
            panel.visible_checkbox.setChecked(False)
        finally:
            del blockers
        self.plot.set_math_settings(scale=0.02, position=0.0)
        self.set_math_configuration("add", 1, 2)
        self.set_math_visible(False)


    def set_math_visible(self, visible):
        self.plot.set_math_settings(visible=visible)
        self._update_math_status()


    def set_math_configuration(self, operation, source_a, source_b):
        result = self.math_processor.configure_math(
            operation=operation, source_a=source_a, source_b=source_b,
        )
        # Una captura Peak congelada conserva sus datos originales incluso
        # después de cambiar la base temporal (que reinicia la adquisición).
        if (not self.running and isinstance(self.last_envelope, PeakDetectResult)
                and self._last_peak_capture is not None):
            frozen = MathTraceProcessor(self._last_peak_config)
            frozen.math.configure(operation=operation, source_a=source_a, source_b=source_b)
            result = frozen.process(self._last_peak_capture, self.sample_rate)
        self.controls.math_controls.set_configuration(self.math_processor.math.config)
        self.plot.set_math_settings(expression=self.math_processor.math.expression)
        self._math_error = None
        if self.acquisition_processor.get_mode() == "roll":
            self._redraw_roll()
        else:
            self._render_math(result, self._last_math_reference)


    def _update_math_status(self):
        if self._math_error:
            status = f"MATH: {self._math_error}"
        elif not self.plot.math_visible:
            status = "MATH oculta"
        elif self.last_math is None:
            status = "MATH: esperando captura válida"
        else:
            status = "MATH: " + ("captura congelada" if not self.running else "actualizando")
        self.controls.math_controls.status_label.setText(status)


    def _render_math(self, result, trigger_sample=None):
        self._last_math_reference = trigger_sample
        factor = self._last_high_resolution_factor
        display_rate = self.sample_rate / factor
        display_reference = (
            None if trigger_sample is None else
            (trigger_sample - (factor - 1) / 2) / factor
        )
        if result is None:
            self.last_math = None
            self.plot.clear_math()
        elif isinstance(result, EnvelopeResult):
            self.last_math = deepcopy(result)
            self.plot.set_math_envelope(result.minimum, result.maximum, display_rate, display_reference,
                                        sample_positions=getattr(result, "sample_positions", None))
        else:
            self.last_math = np.asarray(result, dtype=np.float32).copy()
            self.plot.set_math_signal(self.last_math, display_rate, display_reference)
        self._update_math_status()


    def _redraw_math(self):
        self._render_math(self.last_math, self._last_math_reference)


    def _recut_sampling_math(self, acquisition, trigger_sample=None, *, raw_acquisition=None):
        # El histórico CSV guarda las muestras normalizadas originales.
        self._archive_raw(
            acquisition if raw_acquisition is None else raw_acquisition,
            trigger_sample,
        )
        self.capture_archive.publish()
        self.export_controls.refresh()
        self.math_processor.configure_acquisition(self.acquisition_processor.get_config())
        result = self.math_processor.replace_sampling_capture(acquisition, self.sample_rate)
        self._render_math(result, trigger_sample)
