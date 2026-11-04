"""Representación y recorte de capturas; estado mostrado en los controles."""

from copy import deepcopy
import numpy as np
from acquisition.modes.envelope import EnvelopeResult


class DisplayMixin:
    """Colabora sobre el estado único inicializado por OscilloscopeWidget."""

    def _render_processed(self, result, trigger_sample=None):
        if isinstance(result, EnvelopeResult):
            self.last_envelope = deepcopy(result)
            self.last_acquisition = None
            self._last_render_trigger_sample = trigger_sample
            self._last_display_buffer = None
            self.plot.set_envelope(
                self.last_envelope.minimum, self.last_envelope.maximum,
                self.sample_rate, trigger_sample=trigger_sample,
                sample_positions=getattr(result, "sample_positions", None),
            )
        else:
            self._render_acquisition(result, trigger_sample)
        self._render_math(self._pending_math_result, trigger_sample)
        self.capture_archive.publish()
        self.export_controls.refresh()


    def _render_acquisition(self, samples, trigger_sample=None):
        """Representa muestras sin ejecutar ni acumular el algoritmo."""
        self.last_envelope = None
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

        if self.last_envelope is not None:
            self.plot.set_envelope(
                self.last_envelope.minimum, self.last_envelope.maximum,
                self.sample_rate, trigger_sample=self._last_render_trigger_sample,
                sample_positions=getattr(self.last_envelope, "sample_positions", None),
            )
            self._redraw_math()
            return

        # Un promedio congelado conserva sus valores y su origen temporal.
        # Nunca sustituirlo por una captura cruda ni acumular al redibujar.
        if self.acquisition_processor.get_mode() == "average":
            if self.last_acquisition is not None:
                self.plot.set_signal(
                    self.last_acquisition, self.sample_rate,
                    trigger_sample=self._last_render_trigger_sample,
                )
            self._redraw_math()
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
                self.last_envelope = None
                self.plot.clear_signal()
                self.last_math = None
                self.capture_archive.clear()
                self.export_controls.refresh()
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
            self._recut_sampling_math(acquisition, trigger_sample)

        else:
            # Sin disparo no existe una referencia temporal
            # para desplazar el recorte alrededor de un cruce.
            if len(data) < self.display_samples:
                self.last_acquisition = None
                self.last_envelope = None
                self.plot.clear_signal()
                self.last_math = None
                self.capture_archive.clear()
                self.export_controls.refresh()
                return

            acquisition = data[-self.display_samples:].copy()
            self._render_acquisition(acquisition)
            self._recut_sampling_math(acquisition)


    def update_controls_state(self):
        self.export_controls.refresh()
        self._update_math_status()
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
            status = "STOP · SINGLE completo" if self.single_mode else "STOP"
        elif self.trigger_mode == "Single":
            status = "SINGLE: esperando disparo"
        elif self.trigger_mode == "Normal":
            status = "NORMAL: disparado" if self.trigger_found else "NORMAL: esperando disparo"
        elif self.trigger_found:
            status = "AUTO: disparado"
        elif self._auto_free_running:
            status = "AUTO: barrido libre"
        else:
            status = "AUTO: esperando disparo"

        mode = self.acquisition_processor.get_mode()
        accumulating = mode in ("average", "envelope")
        count, target = self.acquisition_processor.get_progress()
        self.controls.acquisition_controls.show_capture_progress(count, target)
        if accumulating:
            if self.running and not self.trigger_found:
                status += ": esperando disparo" if "esperando" not in status else ""
            label = "AVG" if mode == "average" else "ENV"
            status += f" · {label} {count}/{target}"
        if mode == "peak_detect":
            status += f" · PEAK {self.acquisition_processor.get_config().peak_bucket_size} muestras/intervalo"
        self.controls.show_state(self.running, status)
