"""Timeout Trigger: dispara tras ausencia prolongada de cruces.

El evento ocurre cuando la señal lleva `timeout_us` en HIGH/LOW sin
cambiar de estado. Para conservar estado entre bloques USB, usar
`set_window_start(first_sample)` antes de `crossings` / `find`.

Esta clase comparte crossings/find/capture y Holdoff con Edge_Trigger.
"""
from __future__ import annotations

import math
import numpy as np

from trigger.edge_trigger import Edge_Trigger, EdgeEvent


class TimeoutTrigger(Edge_Trigger):
    """Disparo cuando la entrada permanece inmóvil durante cierto tiempo.

    state: 'either', 'high' o 'low', respecto de `level` (en voltios).
    El contador comienza al observar la primera muestra o un cambio de estado.
    Solo se genera UN evento por período estable, no un tren de eventos.
    """

    def __init__(self, level=0.0, slope="Rising", position=0.5, *,
                 sample_rate=97656.25, timeout_us=1000.0,
                 state="either", hysteresis_volts=0.0):
        super().__init__(level=level, slope=slope, position=position,
                         smoothing_samples=1, hysteresis_fraction=0.0)
        self.set_sample_rate(sample_rate)
        self.set_timeout_settings(state=state, timeout_us=timeout_us,
                                  hysteresis_volts=hysteresis_volts)

    def reset_stream(self):
        """Olvida el histórico al cambiar fuente, nivel, configuración o modo."""
        self._window_start = 0
        self._last_seen = None
        self._side = None
        self._side_started = None
        self._emitted_for_segment = False
        self._pending_absolute = []

    def set_window_start(self, first_sample):
        value = int(first_sample)
        if value < 0:
            raise ValueError("El primer índice absoluto debe ser >= 0")
        self._window_start = value
        if self._last_seen is not None and value > self._last_seen + 1:
            # Faltan muestras entre bloques: no unirlos artificialmente.
            self.reset_stream()
            self._window_start = value

    def set_sample_rate(self, sample_rate):
        rate = float(sample_rate)
        if not math.isfinite(rate) or rate <= 0:
            raise ValueError("Fs debe ser finita y positiva")
        self.sample_rate = rate
        self.reset_stream()

    def set_timeout_settings(self, *, state, timeout_us, hysteresis_volts=0.0):
        if state not in ("either", "high", "low"):
            raise ValueError("state debe ser either/high/low")
        timeout = float(timeout_us)
        hysteresis = float(hysteresis_volts)
        if (not math.isfinite(timeout) or timeout < 0 or timeout > 10_000_000
                or not math.isfinite(hysteresis) or hysteresis < 0
                or hysteresis > 1_000_000):
            raise ValueError("Parámetros de Timeout fuera de rango")
        self.state = state
        self.timeout_us = timeout
        self.hysteresis_volts = hysteresis
        self.reset_stream()

    def _emit_if_due(self, absolute_now):
        if self._side is None or self._emitted_for_segment:
            return
        if self.state != "either" and self.state != self._side:
            return
        # Ceil conservador: nunca disparar antes de completar la duración.
        wait = max(1, math.ceil(self.timeout_us * 1e-6 * self.sample_rate - 1e-12))
        target = self._side_started + wait
        if absolute_now >= target:
            self._pending_absolute.append(target)
            self._emitted_for_segment = True

    def crossings(self, samples):
        data = np.asarray(samples, dtype=np.float64)
        if data.ndim != 1:
            raise ValueError("Timeout necesita un canal mono")
        if not np.isfinite(data).all():
            self.reset_stream()
            return []
        n = len(data)
        if n < 2:
            return []
        start = self._window_start
        last_abs = start + n - 1
        # Reprocesar únicamente muestras nuevas; el lector entrega ventanas
        # superpuestas y la duración NO debe reiniciarse en cada ventana.
        begin = 0 if self._last_seen is None else max(0, self._last_seen + 1 - start)
        lo = self.level - self.hysteresis_volts
        hi = self.level + self.hysteresis_volts
        for i in range(begin, n):
            value = data[i]
            absolute = start + i
            if self.hysteresis_volts == 0.0:
                # En el umbral exacto la señal sigue siendo un estado estable.
                new_side = "high" if value >= self.level else "low"
            else:
                new_side = "high" if value >= hi else "low" if value <= lo else None
            if new_side is None:
                # Dentro de la banda muerta: conservar estado anterior.
                self._emit_if_due(absolute)
                continue
            if new_side != self._side:
                self._side = new_side
                self._side_started = absolute
                self._emitted_for_segment = False
            self._emit_if_due(absolute)
        self._last_seen = max(last_abs, self._last_seen if self._last_seen is not None else last_abs)
        # Conservar un evento al final del bloque para la próxima ventana:
        # es posible que aún falten muestras post-trigger para capturarlo.
        self._pending_absolute = [p for p in self._pending_absolute if p >= start]
        return [EdgeEvent(int(p - start), 0.0) for p in self._pending_absolute
                if 0 <= p - start < n - 1]
