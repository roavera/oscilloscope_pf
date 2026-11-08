"""Estimación robusta de un nivel Edge a partir de muestras ya calibradas.

Auto Level NO modifica la captura ni aplica filtrado al canal: únicamente
propone un nivel de trigger. No es Autoset ni seguimiento automático.
"""
from __future__ import annotations

import numpy as np


def estimate_auto_level(samples, *, minimum_samples=32):
    """Devuelve el nivel en las unidades de ``samples`` o None si no hay señal.

    Usa percentiles 5/95 para ignorar picos aislados. En señales asimétricas
    (o con ciclo de trabajo muy estrecho) el nivel es una estimación, no una
    medida de amplitud certificada.
    """
    data = np.asarray(samples, dtype=np.float64)
    if data.ndim != 1:
        raise ValueError("Auto Level necesita muestras de un solo canal")
    if data.size < minimum_samples:
        return None
    data = data[np.isfinite(data)]
    if data.size < minimum_samples:
        return None
    low, high = (float(x) for x in np.percentile(data, [5, 95]))
    span = high - low
    # Rechazar DC o una señal prácticamente constante, sin depender de Volt/div.
    minimum_span = max(1e-7, 1e-5 * max(abs(low), abs(high)))
    if not np.isfinite(span) or span <= minimum_span:
        return None
    return (low + high) / 2.0
