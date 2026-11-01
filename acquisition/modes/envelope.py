"""Envolvente móvil de mínimos y máximos entre N capturas alineadas."""

from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class EnvelopeResult:
    """Límites por muestra; nunca se sustituyen por una señal promedio."""

    minimum: np.ndarray
    maximum: np.ndarray


def process_envelope(samples, channel, config, state):
    """Retiene las últimas N capturas; un extremo desaparece al salir de ellas."""
    data = np.asarray(samples, dtype=np.float32)
    if data.ndim != 1 or not np.isfinite(data).all():
        raise ValueError("Envelope requiere muestras 1D finitas")
    if not len(data):
        return EnvelopeResult(data.copy(), data.copy())
    target = config.envelope_count
    if state.get("shape") != data.shape or state.get("target") != target:
        state.clear()
        state.update(shape=data.shape, target=target, captures=deque(),
                     count=0, acquisitions=0)
    captures = state["captures"]
    if len(captures) == target:
        captures.popleft()
    captures.append(data.copy())
    # Reducir por posición temporal, no a un mínimo y máximo globales.
    stack = np.stack(captures, axis=0)
    state["count"] = len(captures)
    state["acquisitions"] += 1
    return EnvelopeResult(stack.min(axis=0), stack.max(axis=0))
