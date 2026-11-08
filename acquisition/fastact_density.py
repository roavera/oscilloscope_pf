"""Mapa de intensidad FastAct: detección visual de adquisiciones poco frecuentes.

Esta capa trabaja SOLO con capturas ya alineadas y calibradas. No promedia
adquisiciones entre sí, no altera el trigger ni la entrada PCM24.
"""
from __future__ import annotations

import math
import numpy as np


class FastActDensity:
    """Acumulador acotado por píxeles (CH1, CH2), independiente del muestreo.

    Las celdas retienen densidad, no promedios: una traza anómala puede seguir
    siendo visible brevemente aunque el disparo siguiente sea normal.
    """

    def __init__(self, columns=512, rows=256, half_life=2.0, strength=0.20):
        self.columns = int(columns)
        self.rows = int(rows)
        self.half_life = float(half_life)
        self.strength = float(strength)
        if self.columns < 8 or self.rows < 8:
            raise ValueError("La grilla FastAct debe tener al menos 8 celdas por eje")
        if not (math.isfinite(self.half_life) and self.half_life > 0):
            raise ValueError("La persistencia debe ser positiva y finita")
        if not (math.isfinite(self.strength) and self.strength > 0):
            raise ValueError("La intensidad debe ser positiva y finita")
        self.clear()

    def clear(self):
        self._density = np.zeros((2, self.rows, self.columns), dtype=np.float32)
        self.captures = 0

    def fade(self, elapsed_seconds):
        """Persistencia temporal: media intensidad después de half_life segundos."""
        elapsed = float(elapsed_seconds)
        if not math.isfinite(elapsed) or elapsed < 0:
            raise ValueError("El intervalo temporal debe ser finito y >= 0")
        if elapsed:
            self._density *= np.float32(2.0 ** (-elapsed / self.half_life))

    def add_capture(self, samples, scales, positions):
        data = np.asarray(samples, dtype=np.float32)
        if data.ndim != 2 or data.shape[1] != 2 or len(data) < 2:
            raise ValueError("FastAct necesita una captura estéreo (N, 2), N >= 2")
        if not np.isfinite(data).all():
            raise ValueError("La captura contiene valores no finitos")
        scale = np.asarray(scales, dtype=np.float64)
        position = np.asarray(positions, dtype=np.float64)
        if scale.shape != (2,) or not np.isfinite(scale).all() or np.any(scale <= 0):
            raise ValueError("Las escalas de ambos canales deben ser positivas")
        if position.shape != (2,) or not np.isfinite(position).all():
            raise ValueError("Las posiciones de ambos canales deben ser finitas")

        # Cada columna conserva los extremos de TODAS las muestras crudas
        # de la captura. Así no desaparecen glitches estrechos al reducir el
        # raster: una interpolación simple podría saltearse un pico aislado.
        columns = np.minimum(
            (np.arange(len(data), dtype=np.int64) * self.columns) // len(data),
            self.columns - 1,
        ).astype(np.intp)
        x_pixel = np.arange(self.columns)
        for ch in range(2):
            y_div = data[:, ch].astype(np.float64) / scale[ch] + position[ch]
            low = np.full(self.columns, np.inf, dtype=np.float64)
            high = np.full(self.columns, -np.inf, dtype=np.float64)
            np.minimum.at(low, columns, y_div)
            np.maximum.at(high, columns, y_div)

            # Cuando hay menos muestras que píxeles, conectar los intervalos
            # faltantes sin inventar nuevos extremos fuera de las muestras.
            known = np.flatnonzero(np.isfinite(low))
            if len(known) < 2:
                continue
            if len(known) < self.columns:
                between = (x_pixel >= known[0]) & (x_pixel <= known[-1])
                low[between] = np.interp(x_pixel[between], known, low[known])
                high[between] = np.interp(x_pixel[between], known, high[known])

            # Solo dibujamos los intervalos que tocan la ventana vertical.
            valid = np.isfinite(low) & np.isfinite(high) & (high >= -4) & (low <= 4)
            if not valid.any():
                continue
            y_low = np.clip(np.rint((low[valid] + 4.0) / 8.0 * (self.rows - 1)),
                            0, self.rows - 1).astype(np.intp)
            y_high = np.clip(np.rint((high[valid] + 4.0) / 8.0 * (self.rows - 1)),
                             0, self.rows - 1).astype(np.intp)
            density = self._density[ch]
            # Rango mínimo-máximo por columna: preserva los transitorios.
            for x, lo, hi in zip(x_pixel[valid], y_low, y_high):
                density[lo:hi + 1, x] += self.strength
            np.minimum(density, 6.0, out=density)

        self.captures += 1

    def image(self, visible=(True, True)):
        """Imagen RGBA en orientación Y ascendente (ImageItem row-major)."""
        if len(visible) != 2:
            raise ValueError("Visibilidad requiere CH1 y CH2")
        # 0..1 sin introducir datos imaginarios en la traza.
        a = (1.0 - np.exp(-self._density[0])) if visible[0] else np.zeros_like(self._density[0])
        b = (1.0 - np.exp(-self._density[1])) if visible[1] else np.zeros_like(self._density[1])
        image = np.empty((self.rows, self.columns, 4), dtype=np.uint8)
        image[:, :, 0] = np.clip(255 * a + 35 * b, 0, 255).astype(np.uint8)
        image[:, :, 1] = np.clip(222 * a + 205 * b, 0, 255).astype(np.uint8)
        image[:, :, 2] = np.clip(50 * a + 255 * b, 0, 255).astype(np.uint8)
        image[:, :, 3] = np.clip(210 * (a + b), 0, 220).astype(np.uint8)
        return image

    def peak(self):
        return float(np.max(self._density))
