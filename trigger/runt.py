"""Runt Trigger: detecta pulsos que no alcanzan el segundo umbral.

HIGH runt: desde debajo de `lower` se supera `lower` pero NO se alcanza
`upper`, antes de volver debajo de `lower`.
LOW runt: desde encima de `upper` se cruza `upper` hacia abajo pero NO
se llega a `lower`, antes de volver encima de `upper`.

Se dispara en el flanco de retorno (pulso confirmado). No crea muestras.
"""
from __future__ import annotations

import math
import numpy as np

from trigger.edge_trigger import Edge_Trigger, EdgeEvent


class RuntTrigger(Edge_Trigger):
    def __init__(self, level=0.0, slope="Rising", position=0.5, *,
                 sample_rate=97656.25, polarity="high", lower_volts=-0.2,
                 upper_volts=0.2, min_width_us=0.0):
        super().__init__(level=level, slope=slope, position=position,
                         smoothing_samples=1, hysteresis_fraction=0.0)
        self.set_sample_rate(sample_rate)
        self.set_runt_settings(polarity=polarity, lower_volts=lower_volts,
                               upper_volts=upper_volts,
                               min_width_us=min_width_us)

    def set_sample_rate(self, sample_rate):
        rate = float(sample_rate)
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("Fs debe ser finita y positiva")
        self.sample_rate = rate

    def set_runt_settings(self, *, polarity, lower_volts, upper_volts, min_width_us):
        if polarity not in ("high", "low"):
            raise ValueError("Polaridad debe ser high o low")
        lo, hi, width = float(lower_volts), float(upper_volts), float(min_width_us)
        if (not all(math.isfinite(v) for v in (lo, hi, width))
                or lo >= hi or width < 0 or width > 10_000_000):
            raise ValueError("Runt requiere lower < upper y ancho >= 0")
        self.polarity, self.lower_volts = polarity, lo
        self.upper_volts, self.min_width_us = hi, width

    @staticmethod
    def _fraction(a, b, level):
        if a == b:
            return 0.0
        return float(np.clip((level - a) / (b - a), 0.0, 1.0))

    def crossings(self, samples):
        data = np.asarray(samples, dtype=np.float64)
        if data.ndim != 1:
            raise ValueError("Runt necesita un canal mono")
        if len(data) < 3 or not np.isfinite(data).all():
            return []
        lo, hi = self.lower_volts, self.upper_volts
        high = self.polarity == "high"
        # Armado solo en un nivel inequívocamente exterior al pulso.
        armed = (data[0] < lo if high else data[0] > hi)
        opening = None
        out = []
        for i in range(1, len(data)):
            a, b = data[i - 1], data[i]
            if opening is None:
                if high and a < lo <= b < hi and armed:
                    opening = i - 1 + self._fraction(a, b, lo)
                elif not high and a > hi >= b > lo and armed:
                    opening = i - 1 + self._fraction(a, b, hi)
                if (high and b < lo) or (not high and b > hi):
                    armed = True
                continue
            # Si alcanzó el umbral 'bueno', ya NO es un pulso Runt.
            if (high and b >= hi) or (not high and b <= lo):
                opening = None
                armed = False
                continue
            closed = (high and a >= lo > b) or (not high and a <= hi < b)
            if closed:
                threshold = lo if high else hi
                fraction = self._fraction(a, b, threshold)
                end = i - 1 + fraction
                duration_us = (end - opening) / self.sample_rate * 1e6
                if duration_us >= self.min_width_us:
                    out.append(EdgeEvent(i - 1, fraction))
                opening = None
                armed = True
        return out
