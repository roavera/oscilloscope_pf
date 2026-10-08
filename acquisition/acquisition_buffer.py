"""
===============================================================================
MÓDULO DE BUFFER DE ADQUISICIÓN TEMPORAL (SLIDING ACQUISITION BUFFER)
===============================================================================
Proyecto:       Osciloscopio y Analizador de Audio por Software (DSO)
Institución:    Facultad de Ingeniería
Descripción:
    Estructura de almacenamiento continuo FIFO basada en un buffer lineal con
    desplazamiento temporal (Sliding Window) implementado sobre NumPy.
    
    Características principales:
      - Almacenamiento continuo de muestras en punto flotante (np.float32).
      - Manejo dinámico de régimen transitorio (llenado) y estacionario (shift).
      - Retención de ventana histórica continua para análisis de Pre-trigger.
      - Desacoplamiento de memoria mediante copia segura para consumo en GUI.

Entrada:        Bloques de muestras discretas (NumPy array 1D / listas).
Salida:         Arreglo NumPy continuo de las últimas N muestras válidas.
===============================================================================
"""
import numpy as np

class AcquisitionBuffer:

    def __init__(self, size):
        self.size = size

        self.buffer = np.zeros(
            self.size,
            dtype=np.float32
        )

        self.valid_samples = 0

    def clear(self):
        self.buffer[:] = 0
        self.valid_samples = 0

    def add_samples(self, samples):
        samples = np.asarray(
            samples,
            dtype=np.float32
        ).flatten()

        if len(samples) == 0:
            return

        n = len(samples)

        # Si entran más muestras que el tamaño del buffer
        if n >= self.size:
            self.buffer[:] = samples[-self.size:]
            self.valid_samples = self.size
            return

        # --------------------------------------------------
        # BUFFER TODAVÍA NO LLENO
        # --------------------------------------------------
        if self.valid_samples < self.size:
            available = self.size - self.valid_samples

            amount = min(n, available)

            self.buffer[
                self.valid_samples:
                self.valid_samples + amount
            ] = samples[:amount]

            self.valid_samples += amount

            # Si sobraron muestras
            if amount < n:
                remaining = samples[amount:]
                nr = len(remaining)
                self.buffer[:-nr] = self.buffer[nr:]
                self.buffer[-nr:] = remaining
                self.valid_samples = self.size
            return

        # --------------------------------------------------
        # BUFFER LLENO
        # --------------------------------------------------
        self.buffer[:-n] = self.buffer[n:]
        self.buffer[-n:] = samples


    def get_data(self):
        return self.buffer[:self.valid_samples].copy()

    def is_full(self):
        return self.valid_samples >= self.size