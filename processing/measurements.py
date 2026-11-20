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
    top: float
    base: float
    amplitude: float
    area: float | None = None


def measure_amplitude(samples, sample_rate=None):
    
    values = np.asarray(samples, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("Las mediciones requieren una señal de un solo canal")
    if values.size == 0 or not np.isfinite(values).all():
        return None
    maximum, minimum = float(values.max()), float(values.min())
    # Percentiles robustos: descartan picos aislados y ruido impulsivo.
    base, top = (float(value) for value in np.percentile(values, [5, 95]))
    amplitude = top - base
    # Escalado previo evita overflow al elevar al cuadrado.
    scale = float(np.max(np.abs(values)))
    rms = float(scale * np.sqrt(np.mean((values / scale) ** 2))) if scale else 0.0
    mean = float(scale * np.mean(values / scale)) if scale else 0.0
    span = maximum - minimum
    if not np.isfinite([maximum, minimum, span, mean, rms, top, base, amplitude]).all():
        return None
    area = None
    if sample_rate is not None and np.isfinite(sample_rate) and sample_rate > 0:
        area = float(np.trapezoid(values, dx=1.0 / float(sample_rate)))
    return AmplitudeMeasurements(maximum, minimum, span, mean, rms, len(values),
                                 top, base, amplitude, area)


@dataclass(frozen=True)
class TimingMeasurements:
    frequency: float | None = None
    period: float | None = None
    periods_used: int = 0
    reason: str = ""
    duty_cycle: float | None = None
    high_time: float | None = None
    low_time: float | None = None
    rise_time: float | None = None
    fall_time: float | None = None


@dataclass(frozen=True)
class TransientMeasurements:
    """Sobreimpulsos y preshoot expresados como porcentaje de Vamp."""
    rovshoot: float | None = None
    fovshoot: float | None = None
    rpreshoot: float | None = None
    fpreshoot: float | None = None
    reason: str = ""


@dataclass(frozen=True)
class InterchannelMeasurements:
    phase: float | None = None
    frr: float | None = None
    frf: float | None = None
    ffr: float | None = None
    fff: float | None = None
    lrr: float | None = None
    lrf: float | None = None
    lfr: float | None = None
    lff: float | None = None
    reason: str = ""


def _hysteretic_crossings(values, hysteresis):
    """Devuelve cruces centrales validados por dos umbrales de histéresis."""
    state = 0
    crossings = []
    for index, current in enumerate(values):
        if state == 0:
            if current <= -hysteresis:
                state = -1
            elif current >= hysteresis:
                state = 1
            continue
        if state == -1 and current >= hysteresis:
            previous = float(values[index - 1])
            denominator = current - previous
            crossing = index - 1 + (-previous / denominator) if denominator else float(index)
            crossings.append((crossing, "rising"))
            state = 1
        elif state == 1 and current <= -hysteresis:
            previous = float(values[index - 1])
            denominator = current - previous
            crossing = index - 1 + (-previous / denominator) if denominator else float(index)
            crossings.append((crossing, "falling"))
            state = -1
    return crossings


def _slew_times(values, lower, upper):
    """Mide 10-90 % y 90-10 % en transiciones completas."""
    def crossing(previous, current, level, index):
        delta = current - previous
        return index - 1 + ((level - previous) / delta if delta else 0.0)

    rising, falling = [], []
    rise_start = fall_start = None
    rising_armed = float(values[0]) < lower
    falling_armed = float(values[0]) > upper
    for index in range(1, len(values)):
        previous, current = float(values[index - 1]), float(values[index])
        if current <= lower:
            rising_armed = True
            rise_start = None
        if current >= upper:
            falling_armed = True
            fall_start = None
        if rising_armed and rise_start is None and previous < lower <= current:
            rise_start = crossing(previous, current, lower, index)
        if rising_armed and rise_start is not None and previous < upper <= current:
            rising.append(crossing(previous, current, upper, index) - rise_start)
            rising_armed = False
            rise_start = None
        if falling_armed and fall_start is None and previous > upper >= current:
            fall_start = crossing(previous, current, upper, index)
        if falling_armed and fall_start is not None and previous > lower >= current:
            falling.append(crossing(previous, current, lower, index) - fall_start)
            falling_armed = False
            fall_start = None
    return rising, falling


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
    transitions = _hysteretic_crossings(centered, hysteresis)
    rising_crossings = np.array([x for x, direction in transitions if direction == "rising"])
    falling_crossings = np.array([x for x, direction in transitions if direction == "falling"])
    high_intervals = []
    low_intervals = []
    for rising_crossing in rising_crossings:
        next_falling = falling_crossings[falling_crossings > rising_crossing]
        if len(next_falling):
            high_intervals.append(float(next_falling[0] - rising_crossing))
    for falling_crossing in falling_crossings:
        next_rising = rising_crossings[rising_crossings > falling_crossing]
        if len(next_rising):
            low_intervals.append(float(next_rising[0] - falling_crossing))
    if not high_intervals or not low_intervals:
        return TimingMeasurements(frequency, period, len(periods),
                                   reason="No se pudo medir el pulso completo")
    high = float(np.median(high_intervals)) / float(sample_rate)
    low = float(np.median(low_intervals)) / float(sample_rate)
    duty = 100.0 * high / (high + low) if high + low else None
    if duty is None or not np.isfinite([duty, high, low]).all():
        return TimingMeasurements(frequency, period, len(periods),
                                   reason="Ancho de pulso fuera de rango")
    low_threshold = lower + .1 * span
    high_threshold = lower + .9 * span
    rise_times, fall_times = _slew_times(normalized, low_threshold, high_threshold)
    rise = float(np.median(rise_times)) / float(sample_rate) if rise_times else None
    fall = float(np.median(fall_times)) / float(sample_rate) if fall_times else None
    return TimingMeasurements(frequency, period, len(periods), "", duty, high, low, rise, fall)


def measure_transients(samples, sample_rate):
    """Mide ROVShoot, FOVShoot y RPREShoot en flancos repetidos.

    Usa Vbase/Vtop (percentiles 5/95) como niveles estables. Se examina una
    ventana de media época después del flanco para overshoot y un cuarto de
    época antes del flanco ascendente para preshoot.
    """
    values = np.asarray(samples, dtype=np.float64)
    if values.ndim != 1:
        raise ValueError("La medición transitoria requiere un solo canal")
    if not np.isfinite(sample_rate) or sample_rate <= 0:
        return TransientMeasurements(reason="Frecuencia de muestreo inválida")
    if len(values) < 3 or not np.isfinite(values).all():
        return TransientMeasurements(reason="Sin captura válida")
    timing = measure_timing(values, sample_rate)
    if timing.period is None:
        return TransientMeasurements(reason=timing.reason or "Sin período válido")
    base, top = (float(value) for value in np.percentile(values, [5, 95]))
    span = top - base
    if span <= 64 * np.finfo(float).eps:
        return TransientMeasurements(reason="Amplitud estable insuficiente")
    center = (base + top) / 2.0
    rising = np.flatnonzero((values[:-1] < center) & (values[1:] >= center))
    falling = np.flatnonzero((values[:-1] >= center) & (values[1:] < center))
    period_samples = timing.period * float(sample_rate)
    if period_samples <= 0 or (not len(rising) and not len(falling)):
        return TransientMeasurements(reason="No se detectaron flancos")

    def crossing(index):
        a, b = values[index], values[index + 1]
        return index + ((center - a) / (b - a) if b != a else 0.0)

    rises = np.asarray([crossing(i) for i in rising])
    falls = np.asarray([crossing(i) for i in falling])
    positive_overshoot, negative_overshoot, preshoot, falling_preshoot = [], [], [], []
    for edge in rises:
        start, stop = int(np.ceil(edge)), min(len(values), int(np.floor(edge + .5 * period_samples)) + 1)
        if stop > start:
            positive_overshoot.append(max(0.0, (float(np.max(values[start:stop])) - top) / span * 100.0))
        pre_start, pre_stop = max(0, int(np.floor(edge - .25 * period_samples))), int(np.floor(edge)) + 1
        if pre_stop > pre_start:
            preshoot.append(max(0.0, (float(np.max(values[pre_start:pre_stop])) - base) / span * 100.0))
    for edge in falls:
        start, stop = int(np.ceil(edge)), min(len(values), int(np.floor(edge + .5 * period_samples)) + 1)
        if stop > start:
            negative_overshoot.append(max(0.0, (base - float(np.min(values[start:stop]))) / span * 100.0))
        pre_start, pre_stop = max(0, int(np.floor(edge - .25 * period_samples))), int(np.floor(edge)) + 1
        if pre_stop > pre_start:
            falling_preshoot.append(max(0.0, (top - float(np.min(values[pre_start:pre_stop]))) / span * 100.0))

    def median_or_none(items):
        return float(np.median(items)) if items else None

    return TransientMeasurements(
        median_or_none(positive_overshoot),
        median_or_none(negative_overshoot),
        median_or_none(preshoot),
        median_or_none(falling_preshoot),
        "",
    )


def _edge_positions(values):
    base, top = (float(value) for value in np.percentile(values, [5, 95]))
    center = (base + top) / 2.0

    def crossing(index):
        a, b = values[index], values[index + 1]
        return index + ((center - a) / (b - a) if b != a else 0.0)

    rising = np.flatnonzero((values[:-1] < center) & (values[1:] >= center))
    falling = np.flatnonzero((values[:-1] >= center) & (values[1:] < center))
    return (np.asarray([crossing(i) for i in rising], dtype=float),
            np.asarray([crossing(i) for i in falling], dtype=float))


def measure_interchannel(channel1, channel2, sample_rate):
    """Mide fase y retardos entre flancos de CH1 y CH2.

    Los retardos son positivos cuando el flanco correspondiente de CH2 ocurre
    después que el de CH1. La fase se normaliza al intervalo [-180, 180].
    """
    first = np.asarray(channel1, dtype=np.float64)
    second = np.asarray(channel2, dtype=np.float64)
    if first.ndim != 1 or second.ndim != 1:
        raise ValueError("La medición entre canales requiere señales de un solo canal")
    if not np.isfinite(sample_rate) or sample_rate <= 0:
        return InterchannelMeasurements(reason="Frecuencia de muestreo inválida")
    if len(first) < 3 or len(second) < 3 or not np.isfinite(first).all() or not np.isfinite(second).all():
        return InterchannelMeasurements(reason="Captura inválida")
    timing1 = measure_timing(first, sample_rate)
    timing2 = measure_timing(second, sample_rate)
    if timing1.period is None or timing2.period is None:
        return InterchannelMeasurements(reason="Se necesitan señales periódicas válidas en ambos canales")
    period = float((timing1.period + timing2.period) / 2.0)
    if abs(timing1.frequency - timing2.frequency) / max(timing1.frequency, timing2.frequency) > .02:
        return InterchannelMeasurements(reason="Las frecuencias de CH1 y CH2 no coinciden")
    r1, f1 = _edge_positions(first)
    r2, f2 = _edge_positions(second)
    if not len(r1) or not len(f1) or not len(r2) or not len(f2):
        return InterchannelMeasurements(reason="No se detectaron flancos suficientes")

    def delay(a, b):
        return float((b - a) / float(sample_rate))

    first_values = (delay(r1[0], r2[0]), delay(r1[0], f2[0]),
                    delay(f1[0], r2[0]), delay(f1[0], f2[0]))
    last_values = (delay(r1[-1], r2[-1]), delay(r1[-1], f2[-1]),
                   delay(f1[-1], r2[-1]), delay(f1[-1], f2[-1]))
    phase_delay = first_values[0]
    phase = ((phase_delay / period + .5) % 1.0 - .5) * 360.0
    values = (*first_values, *last_values, float(phase))
    if not np.isfinite(values).all():
        return InterchannelMeasurements(reason="Resultado entre canales inválido")
    return InterchannelMeasurements(
        float(phase), *first_values, *last_values, ""
    )
