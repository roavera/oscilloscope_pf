"""Promedio aritmético móvil de las últimas N capturas alineadas."""

from collections import deque

import numpy as np

def process_average(samples, channel, config, state):
    """Acumula una captura por llamada; cada canal tiene su propio estado.

    La cola conserva float32 y la suma usa float64 para reducir el error al
    agregar y retirar capturas. Durante el llenado se promedian las disponibles.
    """
    data = np.asarray(samples, dtype=np.float32)
    if data.ndim != 1 or not np.isfinite(data).all():
        raise ValueError("Average requiere muestras 1D finitas")
    if not len(data):
        return data.copy()
    count = config.average_count
    if state.get("shape") != data.shape or state.get("target") != count:
        state.clear()
        state.update(shape=data.shape, target=count, captures=deque(),
                     total=np.zeros(data.shape, dtype=np.float64),
                     count=0, acquisitions=0)
    captures = state["captures"]
    if len(captures) == count:
        state["total"] -= captures.popleft()
    current = data.copy()
    captures.append(current)
    state["total"] += current
    state["count"] = len(captures)
    state["acquisitions"] += 1
    return (state["total"] / len(captures)).astype(np.float32)
