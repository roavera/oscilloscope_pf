
"""
Buffer circular de adquisición para osciloscopio digital.

- Almacenamiento continuo de muestras float32.
- Capacidad independiente de Time/div.
- Conserva las muestras más recientes.
- Compatible con CH1 mono del decodificador Blackpill.
- Lectura cronológica mediante get_data().
"""

import numpy as np


class AcquisitionBuffer:

    def __init__(self, size=1_048_576):
        self.size = int(size)

        if self.size <= 0:
            raise ValueError("El tamaño debe ser positivo")

        self.buffer = np.zeros(
            self.size,
            dtype=np.float32
        )

        self.valid_samples = 0
        self.write_index = 0

    def clear(self):
        """Reinicia el buffer."""
        self.buffer.fill(0)
        self.valid_samples = 0
        self.write_index = 0

    def add_samples(self, samples):
        """Agrega muestras sin desplazar el historial."""

        samples = np.asarray(
            samples,
            dtype=np.float32
        ).reshape(-1)

        n = samples.size

        if n == 0:
            return

        # Bloque mayor o igual a la capacidad
        if n >= self.size:
            self.buffer[:] = samples[-self.size:]
            self.valid_samples = self.size
            self.write_index = 0
            return

        # Cantidad disponible hasta el final
        first = min(n, self.size - self.write_index)

        self.buffer[
            self.write_index:self.write_index + first
        ] = samples[:first]

        # Si el bloque cruza el final del buffer
        remaining = n - first

        if remaining > 0:
            self.buffer[:remaining] = samples[first:]

        # Actualizar índice circular
        self.write_index = (
            self.write_index + n
        ) % self.size

        self.valid_samples = min(
            self.size,
            self.valid_samples + n
        )

    def get_data(self, count=None):
        """
        Devuelve muestras en orden cronológico.

        count=None: devuelve todo el historial válido.
        count=N: devuelve las últimas N muestras.
        """

        n = self.valid_samples

        if count is not None:
            n = min(n, max(0, int(count)))

        if n == 0:
            return np.empty(0, dtype=np.float32)

        start = (self.write_index - n) % self.size
        end = start + n

        if end <= self.size:
            return self.buffer[start:end].copy()

        first = self.buffer[start:]
        second = self.buffer[:end - self.size]

        return np.concatenate((first, second))

    def is_full(self):
        """Indica si el buffer alcanzó su capacidad."""
        return self.valid_samples == self.size
