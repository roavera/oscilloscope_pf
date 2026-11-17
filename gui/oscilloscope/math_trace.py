"""Configuración, representación y recorte de la traza MATH."""

from copy import deepcopy
import numpy as np
from PySide6.QtCore import QSignalBlocker
from acquisition.modes.envelope import EnvelopeResult
from acquisition.modes.peak_detect import PeakDetectResult
from processing.math_processor import MathTraceProcessor
from config.defaults import FACTORY_DEFAULTS


class MathTraceMixin:
    """Colabora sobre el estado único inicializado por OscilloscopeWidget."""

    def _math_reference_scale(self, source_a=1, source_b=2, operation="add"):
        """Obtiene una escala coherente con los canales que alimentan MATH."""
        scales = getattr(self.plot, "channel_scales", {})
        scale_a = float(scales.get(int(source_a), self.volts_per_division))
        scale_b = float(scales.get(int(source_b), self.ch2_volts_per_division))
        digital = {"greater", "less", "greater_equal", "less_equal", "equal", "and", "or", "xor"}
        if operation in digital:
            return 1.0
        if operation == "multiply":
            return scale_a * scale_b
        if operation == "divide":
            return scale_a / scale_b
        unary = {"abs", "sqrt", "log10", "ln", "exp", "integrate", "derivative"}
        if operation in unary:
            return scale_a
        # Para operaciones entre canales se usa la mayor escala: conserva la
        # legibilidad aun cuando CH1 y CH2 tengan sensibilidades distintas.
        return max(scale_a, scale_b)

    @staticmethod
    def _math_peak(result):
        if result is None:
            return 0.0
        arrays = (result.minimum, result.maximum) if isinstance(result, EnvelopeResult) else (result,)
        peak = 0.0
        for array in arrays:
            values = np.asarray(array, dtype=np.float64)
            finite = values[np.isfinite(values)]
            if finite.size:
                peak = max(peak, float(np.max(np.abs(finite))))
        return peak

    @staticmethod
    def _math_auto_scale(result):
        """Escala 1-2-5: el máximo absoluto ocupa hasta tres divisiones."""
        peak = MathTraceMixin._math_peak(result)
        if peak <= 0:
            return None
        required = peak / 3.0
        exponent = np.floor(np.log10(required))
        base = 10.0 ** exponent
        for multiplier in (1, 2, 5, 10):
            scale = float(multiplier * base)
            if scale >= required:
                return scale
        return float(10 * base)

    def _apply_math_scale(self, result=None):
        """Auto basado en las fuentes cuando la operación lo permite."""
        # MATH_AUTO_SCALE_RESTANTES_V1
        panel = self.controls.math_controls
        if not panel.auto_scale:
            return

        config = self.math_processor.math.config
        operation = config.operation
        scales = getattr(self.plot, "channel_scales", {})
        scale_a = float(scales.get(config.source_a, self.volts_per_division))

        # Estas operaciones conservan una relación directa con las escalas
        # elegidas en los canales, sin depender del pico de la captura.
        if operation in {"add", "subtract", "multiply", "divide", "abs"}:
            scale = self._math_reference_scale(
                config.source_a, config.source_b, operation
            )
        elif operation == "sqrt":
            scale = float(np.sqrt(scale_a))
        elif self.plot.math_digital:
            scale = 1.0
        else:
            # Derivada, integral, logaritmos y exponencial necesitan el rango
            # real de la operación, no las unidades/div de la fuente.
            scale = self._math_auto_scale(result)
            if scale is None:
                return
            # Histéresis exclusivamente dentro de la MISMA operación:
            # nunca heredar la escala de una función matemática anterior.
            last_operation = getattr(self, "_math_auto_last_operation", None)
            current = float(self.plot.math_scale)
            if last_operation == operation and current > 0:
                ratio = self._math_peak(result) / current
                if 1.5 <= ratio <= 3.3:
                    return

        if not np.isfinite(scale) or scale <= 0:
            return
        self._math_auto_last_operation = operation
        panel.set_scale_value(scale)
        self.plot.set_math_settings(scale=scale)

    def sync_math_scale(self):
        """No sobrescribir la escala elegida por el usuario en modo Manual."""
        if self.controls.math_controls.auto_scale:
            self._apply_math_scale(self.last_math)

    def reset_math_controls(self, _checked=False):
        """Defaults de MATH; los canales y sus acumulaciones se conservan."""
        panel = self.controls.math_controls
        widgets = (panel.scale_combo, panel.scale_mode_combo, panel.position_input, panel.visible_checkbox)
        blockers = [QSignalBlocker(widget) for widget in widgets]
        try:
            panel.set_auto_scale(True)
            panel.set_scale_value(self._math_reference_scale(1, 2, "add"))
            panel.position_input.setValue(FACTORY_DEFAULTS["math_position"])
            panel.visible_checkbox.setChecked(False)
        finally:
            del blockers
        self.plot.set_math_settings(
            scale=self._math_reference_scale(1, 2, "add"),
            position=FACTORY_DEFAULTS["math_position"],
            visible=FACTORY_DEFAULTS["math_visible"],
        )
        self.set_math_configuration("add", 1, 2)
        self.set_math_visible(False)


    def set_math_visible(self, visible):
        self.plot.set_math_settings(visible=visible)
        self._update_math_status()
        self.update_controls_state()


    def set_math_configuration(self, operation, source_a, source_b):
        source_label = self.voltage_calibration.status(self.acquisition.source)
        calibrated = self.voltage_calibration.has_volts(self.acquisition.source)
        self.controls.math_controls.set_units(source_label, calibrated, operation)
        result = self.math_processor.configure_math(
            operation=operation, source_a=source_a, source_b=source_b,
        )
        digital = operation in {
            "greater", "less", "greater_equal", "less_equal", "equal",
            "and", "or", "xor",
        }
        self.controls.math_controls.set_digital_mode(digital)
        self.plot.set_math_settings(digital=digital, unit=self.controls.math_controls._unit_suffix)
        self._math_auto_last_operation = None
        # Auto se actualiza luego, con el resultado de la nueva fórmula.

        if (self.acquisition_processor.get_mode() == "fastact" and
                self.last_acquisition is not None):
            result = self.math_processor.math.evaluate(
                self.last_acquisition, self.sample_rate
            ).values
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
            self._apply_math_scale(self.last_math)
            self.plot.set_math_envelope(result.minimum, result.maximum, display_rate, display_reference,
                                        sample_positions=getattr(result, "sample_positions", None))
        else:
            self.last_math = np.asarray(result, dtype=np.float64).copy()
            self._apply_math_scale(self.last_math)
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
