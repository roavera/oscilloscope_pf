"""Mediciones de amplitud sobre una captura, sin dependencias de la GUI."""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class AmplitudeMeasurements:
    maximum: float
    minimum: float
    peak_to_peak: float
    mean: float
    rms: float
    sample_count: int


def measure_amplitude(samples):
    """Mide todas las muestras; RMS incluye DC. No interpola ni elimina NaN.

    Devuelve None para captura vacía/no finita. La unidad es la de entrada.
    Una muestra es válida para amplitud (Vpp=0); no implica periodicidad.
    """
    values = np.asarray(samples, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("Las mediciones requieren una señal de un solo canal")
    if values.size == 0 or not np.isfinite(values).all():
        return None
    maximum, minimum = float(values.max()), float(values.min())
    # Escalado previo evita overflow al elevar al cuadrado.
    scale = float(np.max(np.abs(values)))
    rms = float(scale * np.sqrt(np.mean((values / scale) ** 2))) if scale else 0.0
    mean = float(scale * np.mean(values / scale)) if scale else 0.0
    span = maximum - minimum
    if not np.isfinite([maximum, minimum, span, mean, rms]).all():
        return None
    return AmplitudeMeasurements(maximum, minimum, span, mean, rms, len(values))


@dataclass(frozen=True)
class TimingMeasurements:
    frequency: float | None = None
    period: float | None = None
    periods_used: int = 0
    reason: str = ""


def measure_timing(samples, sample_rate):
    """Estima f y T de señales periódicas mediante cruces ascendentes.

    Nivel central entre percentiles 5/95; histéresis de +/-10% de ese rango.
    Un cruce solo se acepta tras recorrer ambos umbrales. Se interpola el
    cruce por el nivel central (independiente de la interpolación del display).
    Requiere >=3 cruces, >=8 muestras por período, dispersión <=15% respecto
    de la mediana y correlación a un período >=0.6. No corrige aliasing ni
    estima la fundamental de señales complejas o pulsos muy estrechos.
    """
    values = np.asarray(samples, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("La medición temporal requiere un solo canal")
    if not np.isfinite(sample_rate) or sample_rate <= 0:
        return TimingMeasurements(reason="Frecuencia de muestreo inválida")
    if not len(values) or not np.isfinite(values).all():
        return TimingMeasurements(reason="Sin captura válida")
    scale = float(np.max(np.abs(values)))
    if not scale:
        return TimingMeasurements(reason="Señal constante o sin variación suficiente")
    normalized = values / scale
    lower, upper = np.percentile(normalized, [5, 95])
    span = float(upper - lower)
    if span <= 64 * np.finfo(float).eps:
        return TimingMeasurements(reason="Señal constante o sin variación suficiente")
    centered = normalized - (lower + upper) / 2
    hysteresis = .1 * span

    # Ignorar las muestras dentro de la banda. Cada transición -/+ implica
    # un recorrido completo de la banda y evita contar oscilaciones pequeñas.
    outside = np.flatnonzero(np.abs(centered) >= hysteresis)
    if len(outside) < 2:
        return TimingMeasurements(reason="Faltan ciclos: aumentá Time/div")
    rising = (centered[outside[:-1]] < 0) & (centered[outside[1:]] > 0)
    low_indices, high_indices = outside[:-1][rising], outside[1:][rising]
    middle_indices = np.flatnonzero((centered[:-1] < 0) & (centered[1:] >= 0)) + 1
    if not len(high_indices) or not len(middle_indices):
        return TimingMeasurements(reason="Faltan ciclos: aumentá Time/div")
    # Último cruce del nivel central antes de confirmar el umbral superior.
    selected = np.searchsorted(middle_indices, high_indices, side="right") - 1
    valid = selected >= 0
    ends = middle_indices[selected[valid]]
    valid_band = ends > low_indices[valid]
    ends = ends[valid_band]
    before, after = centered[ends - 1], centered[ends]
    crossings = ends - 1 + (-before) / (after - before)
    if len(crossings) < 3:
        return TimingMeasurements(reason="Faltan ciclos: se necesitan al menos 3 cruces ascendentes")

    periods = np.diff(crossings)
    median = float(np.median(periods))
    if float(periods.min()) < 8:
        return TimingMeasurements(reason="Menos de 8 muestras por período; reducí la frecuencia o Hi-Res")
    if np.max(np.abs(periods - median)) / median > .15:
        return TimingMeasurements(reason="Cruces irregulares: señal ruidosa o no periódica")
    period_samples = float(np.mean(periods))

    # Comprobar repetición de la forma de onda, además de intervalos similares.
    # Evita interpretar ruido aleatorio como señal periódica por coincidencia.
    positions = np.arange(int(np.ceil(period_samples)), len(centered))
    first = np.interp(positions - period_samples, np.arange(len(centered)), centered)
    second = centered[positions]
    first = first - first.mean()
    second = second - second.mean()
    norm = np.linalg.norm(first) * np.linalg.norm(second)
    correlation = float(np.dot(first, second) / norm) if norm else 0.0
    if correlation < .6:
        return TimingMeasurements(reason="No se detecta una repetición estable de la señal")

    period = period_samples / float(sample_rate)
    frequency = 1.0 / period
    if not np.isfinite([period, frequency]).all() or period <= 0:
        return TimingMeasurements(reason="Resultado temporal fuera de rango")
    return TimingMeasurements(frequency, period, len(periods))
