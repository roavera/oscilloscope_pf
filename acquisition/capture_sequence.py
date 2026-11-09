"""Capturas estéreo nuevas y alineadas por el detector Edge compartido."""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class TriggeredCapture:
    samples: np.ndarray
    trigger_sample: int
    trigger_id: int
    raw_samples: np.ndarray | None = None
    raw_trigger_sample: float | None = None


class CaptureSequence:
    """Ventanas sin superposición, deduplicadas mediante índices absolutos.

    ``trigger.crossings`` es el mismo detector que usa Sampling/Peak/Hi-Res.
    La interpolación temporal se aplica sobre ambos canales originales; no
    sobre los datos suavizados que se usan para detectar el disparo.
    """

    def __init__(self):
        self.reset()

    def reset(self, minimum_trigger=0):
        self._minimum_trigger = int(minimum_trigger)
        self._minimum_start = 0

    def captures(self, data, first_sample, display_samples, trigger, channel,
                 *, raw_data=None, holdoff=None, sample_rate=None):
        data = np.asarray(data, dtype=np.float32)
        # Calibrated data is used for trigger and processing. These are
        # the exact native PCM24-decoded samples retained for CSV export.
        raw_data = data if raw_data is None else np.asarray(raw_data, dtype=np.float32)
        if raw_data.shape != data.shape or not np.isfinite(raw_data).all():
            raise ValueError("Las muestras RAW deben ser pares sincronizados finitos")
        if data.ndim != 2 or data.shape[1] != 2:
            raise ValueError("Se requieren pares sincronizados (N, 2)")
        if channel not in (1, 2):
            raise ValueError("La fuente debe ser CH1 o CH2")
        if holdoff is not None and sample_rate is None:
            raise ValueError("El Holdoff requiere frecuencia de muestreo")
        count = int(display_samples)
        if count < 2 or len(data) < count + 1:
            return
        before = int(count * trigger.position)
        # La misma referencia y banda de histéresis para los cinco modos.
        # Logic procesa los dos canales; Timeout usa indices absolutos para
        # conservar estado entre bloques USB y ventanas solapadas.
        if hasattr(trigger, "set_window_start"):
            trigger.set_window_start(first_sample)
        source = data if getattr(trigger, "uses_both_channels", False) else data[:, channel - 1]
        events = trigger.crossings(source)
        low = max(before, self._minimum_trigger - first_sample,
                  self._minimum_start - first_sample + before)
        high = min(len(data) - count + before - 1, len(data) - 2)
        for event in events:
            index = event.index
            if not low <= index <= high:
                continue
            absolute_event = float(first_sample + index) + event.fraction
            if holdoff is not None and not holdoff.allows(absolute_event, sample_rate):
                continue
            start = index - before
            absolute_start = int(first_sample + start)
            if absolute_start < self._minimum_start:
                continue
            segment = data[start:start + count + 1]
            if not np.isfinite(segment).all():
                continue
            fraction = event.fraction
            aligned = ((1.0 - fraction) * segment[:-1] +
                       fraction * segment[1:]).astype(np.float32)
            trigger_id = int(first_sample + index)
            self._minimum_trigger = trigger_id + 1
            self._minimum_start = absolute_start + count + 1
            if holdoff is not None:
                holdoff.accept(absolute_event)
            yield TriggeredCapture(aligned, before, trigger_id,
                                   raw_data[start:start + count + 1].copy(), before + fraction)
