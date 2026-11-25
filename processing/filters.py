"""Diseño de filtros digitales y filtrado de capturas independientes."""
from dataclasses import dataclass
from functools import lru_cache
import numpy as np
from scipy.signal import butter, firwin, sosfilt, sosfilt_zi


@dataclass(frozen=True)
class FilterConfig:
    enabled: bool = False
    kind: str = "lowpass"
    channel: str = "both"
    cutoff_low: float = 1000.0
    cutoff_high: float = 5000.0
    order: int = 4
    family: str = "iir"
    numtaps: int = 129


FILTER_KINDS = ("lowpass", "highpass", "bandpass", "bandstop")
CHANNELS = ("both", "ch1", "ch2")


def _parameters(rate, config, max_iir_order):
    """Valida parámetros físicos sin recortar silenciosamente frecuencias."""
    rate = float(rate)
    if not np.isfinite(rate) or rate <= 0:
        raise ValueError("Frecuencia de muestreo inválida")
    if config.kind not in FILTER_KINDS:
        raise ValueError("Tipo de filtro no disponible")
    if config.channel not in CHANNELS:
        raise ValueError("Canal de filtrado inválido")
    if config.family == "fir":
        size = int(config.numtaps)
        if size != config.numtaps or size < 3 or size > 1025 or size % 2 == 0:
            raise ValueError("La cantidad de coeficientes FIR debe ser impar, entre 3 y 1025")
    elif config.family == "iir":
        size = int(config.order)
        if size != config.order or not 1 <= size <= max_iir_order:
            raise ValueError(f"El orden IIR debe ser entero entre 1 y {max_iir_order}")
    else:
        raise ValueError("Familia de filtro no disponible")
    low, high = float(config.cutoff_low), float(config.cutoff_high)
    if not np.isfinite(low) or not np.isfinite(high):
        raise ValueError("Frecuencias de corte no finitas")
    nyquist = rate / 2.0
    if config.kind == "lowpass":
        cutoff = low
    elif config.kind == "highpass":
        cutoff = high
    else:
        if high <= low:
            raise ValueError("La frecuencia superior debe ser mayor que la inferior")
        cutoff = (low, high)
    values = (cutoff,) if isinstance(cutoff, float) else cutoff
    if not all(0 < value < nyquist for value in values):
        raise ValueError(f"Los cortes deben estar entre 0 y Nyquist ({nyquist:g} Hz), sin incluir los extremos")
    return rate, size, cutoff


@lru_cache(maxsize=64)
def _design(rate, family, kind, size, cutoff):
    if family == "fir":
        return firwin(size, cutoff, pass_zero=kind, fs=rate, window="hamming")
    return butter(size, cutoff, btype=kind, fs=rate, output="sos")


def design_filter(sample_rate, config, *, max_iir_order=16):
    """Devuelve secciones SOS para IIR o el vector de coeficientes para FIR."""
    rate, size, cutoff = _parameters(sample_rate, config, max_iir_order)
    return _design(rate, config.family, config.kind, size, cutoff).copy()


def filter_block(coefficients, family, samples, state):
    if family == "fir":
        # FIR simétrico de longitud 2M+1. El estado contiene las 2M
        # entradas anteriores en orden cronológico, por separado para cada canal.
        middle = len(coefficients) // 2
        data = np.concatenate((state, samples))
        if len(samples) == 0:
            return np.empty(0, dtype=data.dtype), state.copy()
        windows = np.lib.stride_tricks.sliding_window_view(data, len(coefficients))
        output = coefficients[middle] * windows[:, middle]
        # Limitar la memoria temporal al sumar los pares de muestras.
        for start in range(0, len(output), 256):
            block = windows[start:start + 256]
            pairs = block[:, :middle] + block[:, :middle:-1]
            output[start:start + len(block)] += np.einsum("ij,j->i", pairs, coefficients[:middle])
        return output, data[-(2 * middle):].copy()
    return sosfilt(coefficients, samples, zi=state)


def apply_filter(samples, sample_rate, config):
    """Filtra cada captura independientemente; entrada/salida (N, 2)."""
    data = np.asarray(samples, dtype=np.float32)
    if data.ndim != 2 or data.shape[1] != 2:
        raise ValueError("El filtro requiere una captura con forma (N, 2)")
    if not np.isfinite(data).all():
        raise ValueError("La captura contiene muestras no finitas")
    if not np.isfinite(float(sample_rate)) or float(sample_rate) <= 0:
        raise ValueError("Frecuencia de muestreo inválida")
    if not config.enabled or len(data) == 0:
        return data.copy()
    coefficients = design_filter(sample_rate, config)
    result = data.astype(np.float64, copy=True)
    selected = (0, 1) if config.channel == "both" else (0,) if config.channel == "ch1" else (1,)
    # Inicialización estacionaria para reducir el transitorio inicial en
    # capturas recortadas. No reemplaza un estado entre bloques continuos.
    zi = (np.ones(len(coefficients) - 1) if config.family == "fir"
          else sosfilt_zi(coefficients))
    for index in selected:
        initial_state = zi * result[0, index]
        result[:, index], _ = filter_block(
            coefficients, config.family, result[:, index], initial_state)
    return result.astype(np.float32)
