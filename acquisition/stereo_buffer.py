"""Buffer circular de pares CH1/CH2; nunca separa instantes de muestreo."""
import numpy as np


class StereoBuffer:
    def __init__(self, size):
        self.size = int(size)
        if self.size < 1:
            raise ValueError('El tamaño debe ser positivo')
        self.buffer = np.zeros((self.size, 2), dtype=np.float32)
        self.total_samples = 0
        self.clear()

    def clear(self):
        # El contador absoluto no retrocede al vaciar el historial.
        self.write_index = 0
        self.valid_samples = 0

    def add_samples(self, samples):
        x = np.asarray(samples, dtype=np.float32)
        if x.ndim != 2 or x.shape[1] != 2:
            raise ValueError('Se requieren muestras estéreo (N, 2)')
        if not len(x):
            return
        self.total_samples += len(x)
        if len(x) >= self.size:
            self.buffer[:] = x[-self.size:]
            self.write_index = 0
            self.valid_samples = self.size
            return
        count = len(x)
        first = min(count, self.size - self.write_index)
        self.buffer[self.write_index:self.write_index + first] = x[:first]
        if first < count:
            self.buffer[:count-first] = x[first:]
        self.write_index = (self.write_index + count) % self.size
        self.valid_samples = min(self.size, self.valid_samples + count)

    def get_data(self, count=None):
        n = self.valid_samples if count is None else min(self.valid_samples, max(0, int(count)))
        start = (self.write_index - n) % self.size
        if start + n <= self.size:
            return self.buffer[start:start+n].copy()
        return np.concatenate((self.buffer[start:], self.buffer[:(start+n) % self.size]))

