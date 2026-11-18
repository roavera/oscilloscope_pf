"""Filtros Butterworth IIR digitales para capturas del osciloscopio.

Etapa 1: cada captura se filtra de manera independiente con SOS. No se
mantiene estado entre capturas; para filtrado continuo real se debe filtrar
el flujo ANTES de construir capturas solapadas.
"""
from dataclasses import dataclass
from functools import lru_cache
import numpy as np
from scipy.signal import butter, sosfilt, sosfilt_zi


@dataclass(frozen=True)
class FilterConfig:
    enabled: bool = False
    kind: str = "lowpass"
    channel: str = "both"
    cutoff_low: float = 1000.0
    cutoff_high: float = 5000.0
    order: int = 4


FILTER_KINDS = ("lowpass", "highpass", "bandpass", "bandstop")
CHANNELS = ("both", "ch1", "ch2")


def _parameters(rate, config):
    """Valida parámetros físicos sin recortar silenciosamente frecuencias."""
    rate = float(rate)
    if not np.isfinite(rate) or rate <= 0:
        raise ValueError("Frecuencia de muestreo inválida")
    if config.kind not in FILTER_KINDS:
        raise ValueError("Tipo de filtro no disponible")
    if config.channel not in CHANNELS:
        raise ValueError("Canal de filtrado inválido")
    order = int(config.order)
    if order != config.order or not 1 <= order <= 16:
        raise ValueError("El orden del filtro debe ser entero entre 1 y 16")
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
    return rate, order, cutoff


@lru_cache(maxsize=64)
def _design(rate, kind, order, cutoff):
    """SciPy diseña el IIR digital (transformación bilineal) en secciones SOS."""
    return butter(order, cutoff, btype=kind, fs=rate, output="sos")


def design_filter(sample_rate, config):
    """Expone coeficientes SOS para graficar o verificar la respuesta."""
    rate, order, cutoff = _parameters(sample_rate, config)
    return _design(rate, config.kind, order, cutoff).copy()


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
    sos = design_filter(sample_rate, config)
    result = data.astype(np.float64, copy=True)
    selected = (0, 1) if config.channel == "both" else (0,) if config.channel == "ch1" else (1,)
    # Inicialización estacionaria para reducir el transitorio inicial en
    # capturas recortadas. No reemplaza un estado entre bloques continuos.
    zi = sosfilt_zi(sos)
    for index in selected:
        initial_state = zi * result[0, index]
        result[:, index], _ = sosfilt(sos, result[:, index], zi=initial_state)
    return result.astype(np.float32)
