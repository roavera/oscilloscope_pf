"""Filtrado IIR con estado, aplicado solamente a las muestras nuevas."""
import numpy as np
from scipy.signal import butter, sosfilt


class ContinuousButterworth:
    """Conserva los estados SOS por canal; cada bloque se procesa una vez."""

    def __init__(self):
        self.reset()

    def reset(self):
        self._key = None
        self._sos = None
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
            if config.kind not in ("lowpass", "highpass", "bandpass", "bandstop"):
                raise ValueError("Tipo de filtro no disponible")
            if config.channel not in ("ch1", "ch2", "both"):
                raise ValueError("Canal de filtrado no disponible")
            if int(config.order) != config.order or not 1 <= config.order <= 20:
                raise ValueError("Orden de filtro invalido")
            nyquist = float(rate) / 2.0
            if not np.isfinite(nyquist) or nyquist <= 0:
                raise ValueError("Frecuencia de muestreo invalida")
            if config.kind == "lowpass":
                cut = float(config.cutoff_low)
            elif config.kind == "highpass":
                cut = float(config.cutoff_high)
            else:
                cut = [float(config.cutoff_low), float(config.cutoff_high)]
            values = np.atleast_1d(cut)
            if not np.isfinite(values).all() or np.any(values <= 0) or np.any(values >= nyquist):
                raise ValueError("Los cortes deben estar entre 0 y Nyquist (sin incluir extremos)")
            if len(values) == 2 and values[0] >= values[1]:
                raise ValueError("El corte inferior debe ser menor que el superior")
            self._sos = butter(int(config.order), cut, btype=config.kind,
                               fs=float(rate), output="sos")
            self._selected = ((0, 1) if config.channel == "both" else
                              (0,) if config.channel == "ch1" else (1,))
            self._state = {ch: np.zeros((len(self._sos), 2), dtype=np.float64)
                           for ch in self._selected}
            self._key = key
        result = data.astype(np.float64, copy=True)
        for ch in self._selected:
            result[:, ch], self._state[ch] = sosfilt(
                self._sos, result[:, ch], zi=self._state[ch])
        return result.astype(np.float32)
