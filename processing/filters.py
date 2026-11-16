"""Filtros digitales sencillos para las capturas del osciloscopio."""

from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class FilterConfig:
    enabled: bool = False
    kind: str = "lowpass"
    channel: str = "both"
    cutoff_low: float = 1000.0
    cutoff_high: float = 5000.0
    order: int = 4


FILTER_KINDS = ("lowpass", "highpass", "bandpass", "bandstop")


def _response(frequencies, config):
    order = max(1, int(config.order))
    eps = np.finfo(float).eps
    low = max(float(config.cutoff_low), eps)
    high = max(float(config.cutoff_high), eps)
    low_ratio = frequencies / low
    high_ratio = high / np.maximum(frequencies, eps)
    lowpass = 1.0 / np.sqrt(1.0 + low_ratio ** (2 * order))
    if config.kind == "lowpass":
        return lowpass
    highpass = 1.0 / np.sqrt(1.0 + high_ratio ** (2 * order))
    if config.kind == "highpass":
        highpass[0] = 0.0
        return highpass
    bandpass = lowpass * highpass
    return bandpass if config.kind == "bandpass" else 1.0 - bandpass


def apply_filter(samples, sample_rate, config):
    """Filtra cada canal por separado mediante una respuesta Butterworth FFT."""
    data = np.asarray(samples, dtype=np.float32)
    if data.ndim != 2 or data.shape[1] != 2:
        raise ValueError("El filtro requiere una captura con forma (N, 2)")
    rate = float(sample_rate)
    if not np.isfinite(rate) or rate <= 0:
        raise ValueError("Frecuencia de muestreo inválida")
    if not config.enabled or len(data) < 4:
        return data.copy()
    if config.kind not in FILTER_KINDS:
        raise ValueError("Tipo de filtro no disponible")
    nyquist = rate / 2.0
    low = float(np.clip(config.cutoff_low, 1e-6, nyquist))
    high = float(np.clip(config.cutoff_high, 1e-6, nyquist))
    if config.kind in ("bandpass", "bandstop") and high <= low:
        raise ValueError("La frecuencia superior debe ser mayor que la inferior")
    safe = FilterConfig(True, config.kind, config.channel, low, high, config.order)
    response = _response(np.fft.rfftfreq(len(data), d=1.0 / rate), safe)
    result = data.astype(np.float64, copy=True)
    channels = (0, 1) if config.channel == "both" else ((0,) if config.channel == "ch1" else (1,))
    for index in channels:
        spectrum = np.fft.rfft(result[:, index])
        result[:, index] = np.fft.irfft(spectrum * response, n=len(data))
    return np.asarray(result, dtype=np.float32)
