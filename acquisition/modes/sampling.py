
"""
===============================================================================
MODO DE ADQUISICIÓN: SAMPLING
===============================================================================
Proyecto: Osciloscopio de Audio en Python

Descripción:
    Modo normal de adquisición.

    Utiliza directamente las muestras adquiridas,
    sin aplicar promediado, filtrado ni reducción
    de resolución.

Características:
    - Conserva todas las muestras.
    - No modifica los valores adquiridos.
    - No requiere acumular adquisiciones anteriores.
    - Funciona independientemente para CH1 y CH2.
    - No modifica el buffer original.
===============================================================================
"""

import numpy as np


def process_sampling(samples, channel, config, state):
    """
    Procesa una adquisición en modo Sampling.

    Parameters
    ----------
    samples : np.ndarray
        Vector unidimensional de muestras adquiridas.

    channel : int
        Canal de adquisición (1 o 2).

    config : AcquisitionConfig
        Configuración actual del procesador.

    state : dict
        Estado interno del canal. Sampling no lo utiliza.

    Returns
    -------
    np.ndarray
        Copia de las muestras originales.
    """

    data = np.asarray(samples, dtype=np.float32)

    if data.ndim != 1:
        raise ValueError(
            "Sampling requiere un vector de muestras 1D"
        )

    return data.copy()
