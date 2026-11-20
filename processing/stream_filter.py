"""Filtrado digital con estado, aplicado solamente a las muestras nuevas."""
import numpy as np
from processing.filters import design_filter, filter_block


class ContinuousFilter:
    """Conserva los estados por canal; cada bloque se procesa una vez."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._key = None
        self._coefficients = None
        self._state = None
        self._selected = ()

    def process(self, samples, rate, config):
        data = np.asarray(samples, dtype=np.float32)
        if data.ndim != 2 or data.shape[1] != 2:
            raise ValueError("Se requieren muestras (N, 2)")
        if not len(data):
            return data.copy()
        key = (float(rate), config)
        if not config.enabled:
            self.reset()
            return data.copy()
        if self._key != key:
            self._coefficients = design_filter(rate, config, max_iir_order=20)
            size = len(self._coefficients)
            state_shape = (size - 1,) if config.family == "fir" else (size, 2)
            self._selected = ((0, 1) if config.channel == "both" else
                              (0,) if config.channel == "ch1" else (1,))
            self._state = {ch: np.zeros(state_shape, dtype=np.float64)
                           for ch in self._selected}
            self._key = key
        result = data.astype(np.float64, copy=True)
        for ch in self._selected:
            result[:, ch], self._state[ch] = filter_block(
                self._coefficients, config.family, result[:, ch], self._state[ch])
        return result.astype(np.float32)


ContinuousButterworth = ContinuousFilter
