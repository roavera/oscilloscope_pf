"""Detección Edge compartida por todos los modos de adquisición.

El acondicionamiento solamente se utiliza para ubicar el disparo. Las
muestras que recibe el procesador de adquisición siguen siendo las originales.

No implementa holdoff; eso corresponde a una etapa posterior.
"""
from __future__ import annotations

from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class EdgeEvent:
    """Cruce en índice ``index + fraction`` sobre el eje de muestras crudas."""
    index: int
    fraction: float


class Edge_Trigger:
    """Detector Edge de nivel, pendiente, histéresis y acondicionamiento.

    La misma instancia se usa en Sampling/Peak/Hi-Res y en CaptureSequence.
    ``smoothing_samples`` y ``hysteresis_fraction`` quedan disponibles para
    una futura configuración de Trigger, sin introducir nuevos controles hoy.
    """

    def __init__(self, level=0.0, slope="Rising", position=0.5,
                 *, smoothing_samples=7, hysteresis_fraction=0.10):
        self.level = 0.0
        self.slope = "Rising"
        self.position = 0.5
        self.fractional_offset = 0.0
        self.smoothing_samples = 7
        self.hysteresis_fraction = 0.10
        self.set_level(level)
        self.set_slope(slope)
        self.set_position(position)
        self.set_conditioning(smoothing_samples=smoothing_samples,
                              hysteresis_fraction=hysteresis_fraction)

    def set_level(self, level):
        level = float(level)
        if not np.isfinite(level):
            raise ValueError("Nivel de trigger no finito")
        self.level = level

    def set_slope(self, slope):
        if slope not in ("Rising", "Falling"):
            raise ValueError("Slope must be 'Rising' or 'Falling'")
        self.slope = slope

    def set_position(self, position):
        position = float(position)
        if not np.isfinite(position):
            raise ValueError("Posición de trigger no finita")
        self.position = float(np.clip(position, 0, 1))

    def set_conditioning(self, *, smoothing_samples=None, hysteresis_fraction=None):
        if smoothing_samples is not None:
            if (isinstance(smoothing_samples, (bool, np.bool_))
                    or not isinstance(smoothing_samples, (int, np.integer))
                    or smoothing_samples < 1 or smoothing_samples % 2 != 1
                    or smoothing_samples > 51):
                raise ValueError("smoothing_samples debe ser impar entre 1 y 51")
            self.smoothing_samples = int(smoothing_samples)
        if hysteresis_fraction is not None:
            h = float(hysteresis_fraction)
            if not np.isfinite(h) or not 0 <= h < 0.5:
                raise ValueError("hysteresis_fraction debe estar entre 0 y 0.5")
            self.hysteresis_fraction = h

    def _condition(self, data):
        """Suaviza solo la referencia de disparo, con padding constante.

        Mantiene índices y longitud. No modifica el vector de entrada.
        """
        n = len(data)
        window = min(self.smoothing_samples, n if n % 2 else n - 1)
        # Estimar cuántas muestras hay por medio período. Con señales rápidas,
        # un suavizado largo suprimiría el flanco y produciría disparos falsos.
        # El parámetro smoothing_samples actúa como longitud máxima.
        if window >= 3 and n >= 96:
            center = float(np.median(data))
            signs = data >= center
            flips = int(np.count_nonzero(signs[:-1] != signs[1:]))
            if flips >= 6:
                samples_per_half_period = (n - 1) / flips
                if samples_per_half_period < 6:
                    window = 1
                elif samples_per_half_period < 14:
                    window = min(window, 3)
                elif samples_per_half_period < 25:
                    window = min(window, 5)
        if window < 3:
            return data.astype(np.float64, copy=True)
        half = window // 2
        padded = np.pad(data.astype(np.float64), (half, half), mode="edge")
        return np.convolve(padded, np.ones(window) / window, mode="valid")

    def crossings(self, samples):
        """Devuelve eventos ascendentes o descendentes, con referencia submuestra.

        Un cruce se confirma solamente tras atravesar la banda de histéresis.
        Se devuelve la posición del cruce por el nivel central, NO por el borde
        de la banda. El evento se retrasa al confirmarse, sin alterar su índice.
        """
        data = np.asarray(samples, dtype=np.float64)
        if data.ndim != 1:
            raise ValueError("Trigger requiere señal unidimensional")
        if len(data) < 2 or not np.all(np.isfinite(data)):
            return []
        signal = self._condition(data)
        q05, q95 = np.percentile(signal, [5, 95])
        amplitude = max(0.0, (q95 - q05) * 0.5)
        # Histéresis relativa a la señal, no en unidades de display.
        h = self.hysteresis_fraction * amplitude
        # Si el nivel está próximo a un extremo, no exigir un umbral
        # inalcanzable. Una histéresis nula conserva modo Edge clásico.
        headroom = min(float(q95 - self.level), float(self.level - q05))
        h = max(0.0, min(h, 0.49 * headroom))
        if h == 0.0:
            # No se puede establecer una banda estable; devolver el cruce
            # directo para no anular disparos sobre amplitudes pequeñas.
            if self.slope == "Rising":
                ix = np.flatnonzero((signal[:-1] < self.level) & (signal[1:] >= self.level))
            else:
                ix = np.flatnonzero((signal[:-1] > self.level) & (signal[1:] <= self.level))
            out = []
            for i in ix:
                delta = signal[i + 1] - signal[i]
                mu = 0.0 if delta == 0 else (self.level - signal[i]) / delta
                out.append(EdgeEvent(int(i), float(np.clip(mu, 0.0, 1.0))))
            return out

        rising = self.slope == "Rising"
        low = self.level - h
        high = self.level + h
        armed = False
        pending = None
        events = []
        for i, value in enumerate(signal):
            if (rising and value <= low) or ((not rising) and value >= high):
                armed = True
                pending = None
            if not armed:
                continue
            if i == 0:
                continue
            prev = signal[i - 1]
            crossed = ((prev < self.level <= value) if rising
                       else (prev > self.level >= value))
            if pending is None and crossed:
                delta = value - prev
                mu = 0.0 if delta == 0 else (self.level - prev) / delta
                pending = EdgeEvent(i - 1, float(np.clip(mu, 0.0, 1.0)))
            confirmed = (value >= high) if rising else (value <= low)
            if pending is not None and confirmed:
                events.append(pending)
                pending = None
                armed = False
        return events

    def find(self, data, display_samples, *, minimum_index=None):
        """Elige el evento completo más reciente dentro de la ventana."""
        data = np.asarray(data)
        n = len(data)
        count = int(display_samples)
        if n < count or count < 2:
            return None
        before = int(count * self.position)
        after = count - before
        low = before
        # Se necesita una muestra a la derecha del cruce para la interpolación.
        high = min(n - after, n - 2)
        choices = [
            e for e in self.crossings(data)
            if low <= e.index <= high and
            (minimum_index is None or e.index + e.fraction >= minimum_index)
        ]
        if not choices:
            self.fractional_offset = 0.0
            return None
        last = choices[-1]
        self.fractional_offset = last.fraction
        return last.index

    def capture(self, data, trigger_index, display_samples):
        """Extrae una ventana de los datos originales, sin filtrarlos."""
        if trigger_index is None:
            return None
        before = int(display_samples * self.position)
        start = int(trigger_index) - before
        end = start + int(display_samples)
        if start < 0 or end > len(data):
            return None
        return data[start:end].copy()
