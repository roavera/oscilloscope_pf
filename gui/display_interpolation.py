"""Interpolación exclusivamente VISUAL para las trazas del osciloscopio.

No reemplaza muestras adquiridas, no cambia fs ni altera el trigger, MATH,
cursores o las capturas exportadas. No necesita SciPy.

* none: puntos originales (la GUI decide cómo dibujarlos).
* linear: segmentos lineales originales.
* sinc: reconstrucción aproximada sinc-Lanczos con ventana de 8 muestras
        por lado; solo con muestreo temporal uniforme.
"""
from __future__ import annotations

import numpy as np

MODES = ("none", "linear", "sinc")
MAX_DISPLAY_POINTS = 4096
SINC_RADIUS = 8


def _uniform(x: np.ndarray) -> bool:
    intervals = np.diff(x)
    reference = float(intervals[0])
    return bool(np.max(np.abs(intervals - reference)) <= max(abs(reference)*1e-4, 1e-12))


def _lanczos_sinc(y: np.ndarray, factor: int) -> np.ndarray:
    """Núcleo sinc truncado (Lanczos) con corrección DC en los bordes."""
    t = np.arange((len(y)-1)*factor+1, dtype=np.float64)/factor
    centers = np.floor(t).astype(np.int64)
    offsets = np.arange(-SINC_RADIUS+1, SINC_RADIUS+1, dtype=np.int64)
    indices = centers[:, None]+offsets[None, :]
    distances = t[:, None] - indices
    inside = (indices>=0)&(indices<len(y))&(np.abs(distances)<SINC_RADIUS)
    weights = np.sinc(distances)*np.sinc(distances/SINC_RADIUS)
    weights *= inside
    numerator = np.sum(weights * y[np.clip(indices,0,len(y)-1)], axis=1)
    divisor = np.sum(weights, axis=1)
    result = np.divide(numerator, divisor, out=np.zeros_like(numerator), where=np.abs(divisor)>1e-12)
    # Conservación explícita de las muestras medidas.
    result[::factor] = y
    return result


def interpolate_display(x, y, mode: str, *, max_points: int = MAX_DISPLAY_POINTS,
                        max_factor: int = 8) -> tuple[np.ndarray, np.ndarray]:
    """Devuelve coordenadas para dibujar. Entrada jamás modificada.

    Si ya hay demasiados puntos, no interpola. Con tiempos no uniformes,
    la sinc (que requiere una fs fija) cae de forma explícita a interpolación
    lineal (p.ej. en un historial Roll parcial).
    """
    if mode not in MODES:
        raise ValueError(f"Interpolación no disponible: {mode}")
    times = np.asarray(x, dtype=np.float64)
    samples = np.asarray(y, dtype=np.float64)
    if times.ndim != 1 or samples.ndim != 1 or times.shape != samples.shape:
        raise ValueError("Tiempo y tensión deben ser vectores 1D de igual tamaño")
    if not (np.isfinite(times).all() and np.isfinite(samples).all()):
        raise ValueError("La señal contiene valores no finitos")
    if times.size > 1 and not np.all(np.diff(times)>0):
        raise ValueError("El eje temporal debe ser estrictamente creciente")
    if isinstance(max_points,bool) or max_points<2 or isinstance(max_factor,bool) or max_factor<1:
        raise ValueError("Límites gráficos inválidos")
    if mode in ("none", "linear") or len(times)<2:
        return times.copy(),samples.copy()

    factor = min(int(max_factor),(int(max_points)-1)//(len(times)-1))
    if factor < 2:
        return times.copy(),samples.copy()
    if mode == "sinc" and not _uniform(times):
        return times.copy(),samples.copy()  # Roll parcial no uniforme: trazo lineal.

    fractions = np.arange(factor, dtype=np.float64)/factor
    dense_times = np.append((times[:-1,None]+np.diff(times)[:,None]*fractions[None,:]).ravel(),times[-1])
    dense_values = _lanczos_sinc(samples,factor)
    return dense_times,dense_values

