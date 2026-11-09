"""Modelo temporal sin dependencias gráficas para inspección de capturas.

Convenciones:
  t=0 es el evento de disparo (o referencia virtual de un barrido libre).
  delay>0 desplaza la ventana hacia muestras posteriores al evento.
  reference es la fracción horizontal donde cae t=0 cuando delay=0.
  zoom aumenta la magnificación sin modificar Time/div de adquisición.
"""

from dataclasses import dataclass
from math import ceil, floor, isfinite


@dataclass(frozen=True)
class HorizontalView:
    time_per_division: float
    divisions: int = 12
    reference: float = 0.5
    delay_seconds: float = 0.0
    zoom: float = 1.0

    def __post_init__(self):
        values = (self.time_per_division, self.reference, self.delay_seconds, self.zoom)
        if not all(isfinite(float(x)) for x in values):
            raise ValueError("Parámetros temporales no finitos")
        if self.time_per_division <= 0 or self.divisions <= 0 or self.zoom < 1:
            raise ValueError("Escala/divisiones/zoom inválidos")
        if not 0 <= self.reference <= 1:
            raise ValueError("La referencia debe estar entre 0 y 1")

    @property
    def span_seconds(self):
        return self.time_per_division * self.divisions / self.zoom

    @property
    def x_range(self):
        duration = self.span_seconds
        left = self.delay_seconds - self.reference * duration
        return (left, left + duration)

    def sample_interval(self, length, sample_rate, trigger_sample, margin_fraction=0.05):
        """Índices [start,end) dentro del historial para el viewport.

        Nunca inventa muestras ni cambia el instante de trigger; proporciona
        5 % extra de contexto para interpolación cerca de los bordes.
        """
        length = int(length)
        rate = float(sample_rate)
        anchor = float(trigger_sample)
        if length <= 0 or not isfinite(rate) or rate <= 0 or not isfinite(anchor):
            raise ValueError("Historial o muestreo inválido")
        if not isfinite(margin_fraction) or margin_fraction < 0:
            raise ValueError("Margen inválido")
        left, right = self.x_range
        pad = (right - left) * margin_fraction
        start = max(0, int(floor(anchor + (left - pad) * rate)))
        end = min(length, int(ceil(anchor + (right + pad) * rate)) + 1)
        if start >= end:
            return None
        return (start, end, anchor - start)


def reference_fraction(mode, custom_fraction=0.5):
    """Referencia de pantalla. Custom utiliza la perilla actual."""
    presets = {"Left": 0.0, "Center": 0.5, "Right": 1.0}
    if mode == "Custom":
        value = float(custom_fraction)
        if not isfinite(value) or not 0 <= value <= 1:
            raise ValueError("Referencia personalizada inválida")
        return value
    try:
        return presets[mode]
    except (KeyError, TypeError):
        raise ValueError(f"Referencia desconocida: {mode}") from None
