"""Capturas estéreo nuevas, completas y alineadas con un disparo común."""

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
    """Usa índices absolutos; el wrap del búfer no repite adquisiciones.

    Se eligen ventanas sin superposición. Cada muestra de ruido pertenece a
    una sola captura del promedio. La interpolación lineal aplica el mismo
    desplazamiento fraccional a CH1 y CH2 y requiere una muestra adicional.
    """

    def __init__(self):
        self.reset()

    def reset(self, minimum_trigger=0):
        self._minimum_trigger = int(minimum_trigger)
        self._minimum_start = 0

    def captures(self, data, first_sample, display_samples, trigger, channel):
        data = np.asarray(data, dtype=np.float32)
        if data.ndim != 2 or data.shape[1] != 2:
            raise ValueError("Se requieren pares sincronizados (N, 2)")
        if channel not in (1, 2):
            raise ValueError("La fuente debe ser CH1 o CH2")
        count = int(display_samples)
        if count < 2 or len(data) < count + 1:
            return
        before = int(count * trigger.position)
        signal = data[:, channel - 1]
        if trigger.slope == "Rising":
            mask = (signal[:-1] < trigger.level) & (signal[1:] >= trigger.level)
        else:
            mask = (signal[:-1] > trigger.level) & (signal[1:] <= trigger.level)
        low = max(before, self._minimum_trigger - first_sample,
                  self._minimum_start - first_sample + before)
        high = min(len(data) - count + before - 1, len(data) - 2)
        crossings = np.flatnonzero(mask)
        for index in crossings[(crossings >= low) & (crossings <= high)]:
            index = int(index)
            start = index - before
            absolute_start = int(first_sample + start)
            if absolute_start < self._minimum_start:
                continue
            segment = data[start:start + count + 1]
            if not np.isfinite(segment).all():
                continue
            fraction = float((trigger.level - float(signal[index])) /
                             (float(signal[index + 1]) - float(signal[index])))
            fraction = float(np.clip(fraction, 0, 1))
            aligned = ((1.0 - fraction) * segment[:-1] +
                       fraction * segment[1:]).astype(np.float32)
            trigger_id = int(first_sample + index)
            # Avanzar antes del yield: detener SINGLE no permite repetirlo.
            self._minimum_trigger = trigger_id + 1
            self._minimum_start = absolute_start + count + 1
            yield TriggeredCapture(aligned, before, trigger_id, segment.copy(), before + fraction)


