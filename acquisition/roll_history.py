"""Historial Roll: reducción temporal continua de pares CH1/CH2.

Cada bin contiene la media de un intervalo temporal. Se conservan también
los instantes centrales de los bins, para anclar el extremo derecho al dato
más reciente sin depender del disparo. Los bins se almacenan en un anillo.
"""
from math import ceil, isfinite
import numpy as np


class RollHistory:
    def __init__(self, sample_rate, window_seconds, max_points=2048):
        self.sample_rate = float(sample_rate)
        self.window_seconds = float(window_seconds)
        self.max_points = int(max_points)
        if (not isfinite(self.sample_rate) or self.sample_rate <= 0 or
            not isfinite(self.window_seconds) or self.window_seconds <= 0 or
            self.max_points < 16):
            raise ValueError('Parámetros inválidos de Roll')
        self.samples_per_bin = max(1, int(ceil(self.sample_rate * self.window_seconds / self.max_points)))
        self.capacity = max(16, int(ceil(self.sample_rate * self.window_seconds / self.samples_per_bin)) + 2)
        self._values = np.zeros((self.capacity, 2), dtype=np.float32)
        self._centers = np.zeros(self.capacity, dtype=np.float64)
        self.reset()

    def reset(self):
        self.total_samples = 0
        self._write = 0
        self._valid = 0
        self._partial_sum = np.zeros(2, dtype=np.float64)
        self._partial_count = 0
        self._partial_start = 0

    def _add(self, means, centers):
        n = len(means)
        if not n:
            return
        if n >= self.capacity:
            means, centers, n = means[-self.capacity:], centers[-self.capacity:], self.capacity
        first = min(n, self.capacity - self._write)
        self._values[self._write:self._write+first] = means[:first]
        self._centers[self._write:self._write+first] = centers[:first]
        if first < n:
            self._values[:n-first] = means[first:]
            self._centers[:n-first] = centers[first:]
        self._write = (self._write + n) % self.capacity
        self._valid = min(self.capacity, self._valid + n)

    def append(self, samples):
        data = np.asarray(samples, dtype=np.float32)
        if data.ndim != 2 or data.shape[1] != 2 or not np.isfinite(data).all():
            raise ValueError('Roll requiere muestras finitas de forma (N, 2)')
        n = len(data)
        if not n:
            return
        base = self.total_samples
        self.total_samples += n
        pos = 0
        width = self.samples_per_bin
        if self._partial_count:
            take = min(width - self._partial_count, n)
            self._partial_sum += data[:take].sum(axis=0, dtype=np.float64)
            self._partial_count += take
            pos = take
            if self._partial_count == width:
                center = self._partial_start + (width - 1) / 2.0
                self._add((self._partial_sum / width)[None,:], np.array([center]))
                self._partial_sum[:] = 0
                self._partial_count = 0
        complete = (n - pos) // width
        if complete:
            group = data[pos:pos + complete * width].reshape(complete, width, 2)
            means = group.mean(axis=1, dtype=np.float64).astype(np.float32)
            centers = base + pos + (width - 1)/2.0 + np.arange(complete) * width
            self._add(means, centers)
            pos += complete * width
        if pos < n:
            if not self._partial_count:
                self._partial_start = base + pos
            self._partial_sum += data[pos:].sum(axis=0, dtype=np.float64)
            self._partial_count += n - pos

    def view(self):
        """(valores, posiciones_s); posiciones relativas a la última muestra."""
        if self.total_samples == 0:
            return np.empty((0,2), dtype=np.float32), np.empty(0, dtype=np.float64)
        if self._valid:
            start = (self._write - self._valid) % self.capacity
            if start + self._valid <= self.capacity:
                values = self._values[start:start+self._valid].copy()
                centers = self._centers[start:start+self._valid].copy()
            else:
                end = (start + self._valid) % self.capacity
                values = np.concatenate((self._values[start:], self._values[:end]))
                centers = np.concatenate((self._centers[start:], self._centers[:end]))
        else:
            values = np.empty((0,2), dtype=np.float32)
            centers = np.empty(0, dtype=np.float64)
        if self._partial_count:
            center = self._partial_start + (self._partial_count - 1)/2.0
            values = np.vstack((values, (self._partial_sum / self._partial_count).astype(np.float32)))
            centers = np.append(centers, center)
        offsets = (centers - (self.total_samples - 1)) / self.sample_rate
        keep = offsets >= -self.window_seconds
        return values[keep], offsets[keep]
