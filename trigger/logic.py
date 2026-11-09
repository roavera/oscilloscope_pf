"""Logic Trigger de dos canales: estados lógicos AND/OR/XOR y flancos.

Los umbrales se expresan en VOLTIOS calibrados para cada entrada. El detector
recibe obligatoriamente un array estéreo (N,2) alineado y no altera muestras.
La posición del flanco lógico tiene resolución de una muestra.
"""
from __future__ import annotations

import math
import numpy as np

from trigger.edge_trigger import Edge_Trigger, EdgeEvent


class LogicTrigger(Edge_Trigger):
    uses_both_channels = True

    def __init__(self, level=0.0, slope="Rising", position=0.5, *,
                 ch1_level=0.0, ch2_level=0.0, ch1_state="high",
                 ch2_state="high", operator="and", edge="rising"):
        super().__init__(level=level, slope=slope, position=position,
                         smoothing_samples=1, hysteresis_fraction=0.0)
        self.set_logic_settings(ch1_level=ch1_level, ch2_level=ch2_level,
                                ch1_state=ch1_state, ch2_state=ch2_state,
                                operator=operator, edge=edge)

    def set_logic_settings(self, *, ch1_level, ch2_level, ch1_state,
                           ch2_state, operator, edge):
        if ch1_state not in ("high", "low") or ch2_state not in ("high", "low"):
            raise ValueError("Los estados deben ser high/low")
        if operator not in ("and", "or", "xor"):
            raise ValueError("Operador lógico inválido")
        if edge not in ("rising", "falling"):
            raise ValueError("Flanco lógico inválido")
        one, two = float(ch1_level), float(ch2_level)
        if not (math.isfinite(one) and math.isfinite(two)):
            raise ValueError("Los umbrales lógicos deben ser finitos")
        self.ch1_level, self.ch2_level = one, two
        self.ch1_state, self.ch2_state = ch1_state, ch2_state
        self.operator, self.edge = operator, edge

    def crossings(self, samples):
        data = np.asarray(samples, dtype=np.float64)
        if data.ndim != 2 or data.shape[1] != 2:
            raise ValueError("Logic requiere dos canales sincronizados (N,2)")
        if len(data) < 2 or not np.isfinite(data).all():
            return []
        one = data[:, 0] >= self.ch1_level
        two = data[:, 1] >= self.ch2_level
        if self.ch1_state == "low":
            one = ~one
        if self.ch2_state == "low":
            two = ~two
        if self.operator == "and":
            combined = one & two
        elif self.operator == "or":
            combined = one | two
        else:
            combined = one ^ two
        if self.edge == "rising":
            indexes = np.flatnonzero(~combined[:-1] & combined[1:])
        else:
            indexes = np.flatnonzero(combined[:-1] & ~combined[1:])
        # Evento al adquirir la primera muestra del nuevo estado lógico.
        return [EdgeEvent(int(i), 1.0) for i in indexes]
