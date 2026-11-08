"""High Resolution: promediado espacial (en tiempo) dentro de una captura.

Cada bloque de N muestras produce un promedio. Las muestras resultantes
corresponden al centro temporal de cada bloque; la frecuencia efectiva es
fs/N. No acumula capturas distintas ni modifica la entrada.
"""

import numpy as np

HIGH_RESOLUTION_FACTORS = (1, 2, 4, 8, 16)


def effective_high_resolution_factor(length, requested):
    """Evita que una ventana demasiado corta produzca menos de dos puntos."""
    if (isinstance(requested, (bool, np.bool_))
            or not isinstance(requested, (int, np.integer))
            or requested not in HIGH_RESOLUTION_FACTORS):
        raise ValueError("El factor Hi-Res debe ser 1, 2, 4, 8 o 16")
    factor = int(requested)
    while factor > 1 and length < 2 * factor:
        factor //= 2
    return factor


def process_high_resolution(samples, channel, config, state):
    """Media por bloques consecutivos, con acumulación float64.

    Descarta el último bloque si está incompleto. 
    La firma es compatible con AcquisitionProcessor.
    """
    data = np.asarray(samples, dtype=np.float32)
    if data.ndim != 1 or not np.isfinite(data).all():
        raise ValueError("Hi-Res requiere muestras 1D finitas")
    factor = effective_high_resolution_factor(
        len(data), config.high_resolution_factor
    )
    count = len(data) // factor
    if factor == 1 or count == 0:
        return data.copy()
    return (
        data[:count * factor].reshape(count, factor)
        .mean(axis=1, dtype=np.float64)
        .astype(np.float32)
    )
