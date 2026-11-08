"""Tiempo mínimo entre eventos de trigger, en la escala de las muestras.

Un único estado compartido por Sampling/Peak/HiRes y por los capturadores
Average/Envelope/FastAct. No se mide en tiempo de GUI ni en ticks USB.
"""
from __future__ import annotations

import math


class TriggerHoldoff:
    """Filtro de eventos basado en índices ABSOLUTOS de muestra.

    El holdoff se aplica al instante del cruce (con fracción de muestra).
    Al resetear el procesamiento se rearma el primer disparo.
    """

    MAX_SECONDS = 10.0

    def __init__(self, seconds: float = 0.0):
        self.seconds = 0.0
        self.last_sample: float | None = None
        self.set_seconds(seconds)

    def set_seconds(self, seconds: float) -> None:
        value = float(seconds)
        if not math.isfinite(value) or not 0.0 <= value <= self.MAX_SECONDS:
            raise ValueError("Holdoff debe estar entre 0 y 10 segundos")
        if value != self.seconds:
            self.seconds = value
            self.reset()

    def reset(self) -> None:
        self.last_sample = None

    def earliest_sample(self, sample_rate: float) -> float | None:
        rate = float(sample_rate)
        if not math.isfinite(rate) or rate <= 0.0:
            raise ValueError("Frecuencia de muestreo inválida")
        if self.last_sample is None:
            return None
        return self.last_sample + self.seconds * rate

    def allows(self, sample_position: float, sample_rate: float) -> bool:
        position = float(sample_position)
        if not math.isfinite(position):
            raise ValueError("Posición del disparo inválida")
        earliest = self.earliest_sample(sample_rate)
        return earliest is None or position + 1e-9 >= earliest

    def accept(self, sample_position: float) -> None:
        position = float(sample_position)
        if not math.isfinite(position) or position < 0.0:
            raise ValueError("Posición absoluta del disparo inválida")
        if self.last_sample is not None and position < self.last_sample:
            raise ValueError("Los disparos deben llegar en orden temporal")
        self.last_sample = position
