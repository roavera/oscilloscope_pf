"""Disparo por ancho de pulso sobre muestras calibradas.

Se integra como sustituto de Edge_Trigger: mantiene la API crossings/find/capture,
la localización submuestra y la compatibilidad con CaptureSequence y Holdoff.

El evento se confirma al FINAL del pulso (flanco de cierre), nunca al inicio.
La muestra original no se modifica. No detecta pulsos abiertos antes del buffer.
"""
from __future__ import annotations

from dataclasses import dataclass
import math

import numpy as np

from trigger.edge_trigger import Edge_Trigger, EdgeEvent


@dataclass(frozen=True)
class PulseWidthEvent(EdgeEvent):
    """Índice/fracción del cierre y duración del pulso confirmado en segundos."""
    width_seconds: float


class PulseWidthTrigger(Edge_Trigger):
    """Detector de pulsos altos/bajos con comparación de duración en segundos.

    polarity: 'high' o 'low'.
    comparison: 'greater', 'less', 'within', 'outside'.
    lower_us: umbral simple o límite inferior en microsegundos.
    upper_us: límite superior usado en within/outside.

    Por defecto NO suaviza para preservar el ancho de los pulsos rápidos;
    se mantiene histéresis para reducir falsos flancos por ruido.
    """

    def __init__(self, level=0.0, slope="Rising", position=0.5, *,
                 sample_rate=97656.25, polarity="high", comparison="greater",
                 lower_us=400.0, upper_us=600.0, smoothing_samples=1,
                 hysteresis_fraction=0.10):
        super().__init__(level=level, slope=slope, position=position,
                         smoothing_samples=smoothing_samples,
                         hysteresis_fraction=hysteresis_fraction)
        self.set_sample_rate(sample_rate)
        self.set_width_settings(polarity=polarity, comparison=comparison,
                                lower_us=lower_us, upper_us=upper_us)

    def set_sample_rate(self, sample_rate):
        rate = float(sample_rate)
        if not math.isfinite(rate) or rate <= 0.0:
            raise ValueError("Frecuencia de muestreo inválida")
        self.sample_rate = rate

    def set_width_settings(self, *, polarity, comparison, lower_us, upper_us):
        if polarity not in ("high", "low"):
            raise ValueError("Polaridad inválida: high o low")
        if comparison not in ("greater", "less", "within", "outside"):
            raise ValueError("Comparación de ancho inválida")
        lower, upper = float(lower_us), float(upper_us)
        if (not math.isfinite(lower) or not math.isfinite(upper)
                or lower < 0.0 or upper < 0.0 or lower > 1_000_000.0
                or upper > 1_000_000.0):
            raise ValueError("Duraciones en microsegundos fuera de rango")
        if comparison in ("within", "outside") and upper < lower:
            raise ValueError("El límite superior debe ser mayor o igual al inferior")
        self.polarity = polarity
        self.comparison = comparison
        self.lower_us = lower
        self.upper_us = upper

    def _matches(self, width_seconds):
        us = width_seconds * 1_000_000.0
        if self.comparison == "greater":
            return us > self.lower_us
        if self.comparison == "less":
            return us < self.lower_us
        if self.comparison == "within":
            return self.lower_us <= us <= self.upper_us
        return us < self.lower_us or us > self.upper_us

    def crossings(self, samples):
        """Encuentra pulsos completos; devuelve eventos en el flanco de cierre.

        Un Schmitt digital permite confirmar una transición sin alterar la
        posición temporal calculada sobre el cruce por el nivel central.
        """
        data = np.asarray(samples, dtype=np.float64)
        if data.ndim != 1:
            raise ValueError("Trigger requiere señal unidimensional")
        if len(data) < 3 or not np.isfinite(data).all():
            return []

        signal = self._condition(data)
        p05, p95 = np.percentile(signal, (5.0, 95.0))
        amplitude = max(0.0, float(p95 - p05) / 2.0)
        headroom = min(float(p95 - self.level), float(self.level - p05))
        h = min(self.hysteresis_fraction * amplitude,
                0.49 * max(0.0, headroom))
        low, high = self.level - h, self.level + h

        # -1: nivel bajo; +1: alto; None: todavía sin estado estable.
        state = (-1 if signal[0] <= low else
                 +1 if signal[0] >= high else None)
        pending = None
        transitions = []
        for i in range(1, len(signal)):
            prev, current = signal[i - 1], signal[i]
            if state is None:
                if current <= low:
                    state = -1
                elif current >= high:
                    state = +1
                continue

            if state == -1:
                if pending is None and prev < self.level <= current:
                    delta = current - prev
                    fraction = 0.0 if delta == 0 else (self.level - prev) / delta
                    pending = EdgeEvent(i - 1, float(np.clip(fraction, 0.0, 1.0)))
                if pending is not None and current >= high:
                    transitions.append(("rising", pending))
                    state = +1
                    pending = None
                elif current <= low:
                    pending = None
            else:
                if pending is None and prev > self.level >= current:
                    delta = current - prev
                    fraction = 0.0 if delta == 0 else (self.level - prev) / delta
                    pending = EdgeEvent(i - 1, float(np.clip(fraction, 0.0, 1.0)))
                if pending is not None and current <= low:
                    transitions.append(("falling", pending))
                    state = -1
                    pending = None
                elif current >= high:
                    pending = None

        opening = "rising" if self.polarity == "high" else "falling"
        closing = "falling" if self.polarity == "high" else "rising"
        opened = None
        out = []
        for direction, event in transitions:
            if direction == opening:
                opened = event
            elif direction == closing and opened is not None:
                width_samples = (event.index + event.fraction
                                 - opened.index - opened.fraction)
                width_seconds = width_samples / self.sample_rate
                if width_samples > 0.0 and self._matches(width_seconds):
                    out.append(PulseWidthEvent(event.index, event.fraction,
                                               float(width_seconds)))
                opened = None
        return out
