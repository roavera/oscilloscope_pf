"""Extremos por intervalo dentro de una captura; no acumula capturas."""
from dataclasses import dataclass
import numpy as np
from acquisition.modes.envelope import EnvelopeResult


@dataclass(frozen=True)
class PeakDetectResult(EnvelopeResult):
    # Dos bordes por intervalo en coordenadas de muestra ORIGINAL.
    sample_positions: np.ndarray
    original_count: int


def process_peak_detect(samples, channel, config, state):
    data = np.asarray(samples, dtype=np.float32)
    if data.ndim != 1 or not np.isfinite(data).all():
        raise ValueError('Peak Detect requiere muestras 1D finitas')
    size = config.peak_bucket_size
    if isinstance(size, (bool, np.bool_)) or not isinstance(size, (int, np.integer)) or size not in (2, 4, 8, 16):
        raise ValueError('El intervalo debe contener 2, 4, 8 o 16 muestras')
    if not len(data):
        return PeakDetectResult(data.copy(), data.copy(), np.array([], dtype=float), 0)
    starts = np.arange(0, len(data), size)
    ends = np.minimum(starts + size - 1, len(data) - 1)
    minimum = np.minimum.reduceat(data, starts)
    maximum = np.maximum.reduceat(data, starts)
    positions = np.column_stack((starts, ends)).ravel().astype(float)
    return PeakDetectResult(np.repeat(minimum, 2), np.repeat(maximum, 2), positions, len(data))
