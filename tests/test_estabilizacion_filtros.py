"""Regresiones del filtrado continuo, sin interfaz grafica."""
import unittest
import numpy as np
from scipy.signal import butter, sosfilt
from processing.filters import FilterConfig, design_filter
from processing.stream_filter import ContinuousButterworth


class TestFiltroContinuo(unittest.TestCase):
    def setUp(self):
        self.fs = 48000.0
        t = np.arange(4800) / self.fs
        self.signal = np.column_stack((
            np.sin(2 * np.pi * 300 * t) + .3 * np.sin(2 * np.pi * 8000 * t),
            .7 * np.sin(2 * np.pi * 2000 * t),
        )).astype(np.float32)

    def test_bloques_equivalentes_a_senal_completa(self):
        cfg = FilterConfig(True, 'lowpass', 'both', 1000, 5000, 4)
        stream = ContinuousButterworth()
        pieces = [stream.process(x, self.fs, cfg)
                  for x in np.array_split(self.signal, 23)]
        full = ContinuousButterworth().process(self.signal, self.fs, cfg)
        np.testing.assert_allclose(np.concatenate(pieces), full, atol=4e-7)

    def test_canal_no_seleccionado(self):
        cfg = FilterConfig(True, 'highpass', 'ch1', 1000, 5000, 4)
        result = ContinuousButterworth().process(self.signal, self.fs, cfg)
        np.testing.assert_array_equal(result[:, 1], self.signal[:, 1])

    def test_reinicio_explicito(self):
        cfg = FilterConfig(True, 'lowpass', 'both', 1000, 5000, 4)
        f = ContinuousButterworth()
        f.process(self.signal[:400], self.fs, cfg)
        f.reset()
        actual = f.process(self.signal[400:], self.fs, cfg)
        fresh = ContinuousButterworth().process(self.signal[400:], self.fs, cfg)
        np.testing.assert_allclose(actual, fresh, atol=1e-7)

    def test_banda_rechazada(self):
        cfg = FilterConfig(True, 'bandstop', 'ch1', 1000, 5000, 4)
        sos = design_filter(self.fs, cfg)
        expected = sosfilt(sos, self.signal[:, 0].astype(float))
        actual = ContinuousButterworth().process(self.signal, self.fs, cfg)
        np.testing.assert_allclose(actual[:, 0], expected, atol=4e-7)

    def test_corte_fuera_de_nyquist(self):
        cfg = FilterConfig(True, 'lowpass', 'both', self.fs/2, 5000, 4)
        with self.assertRaises(ValueError):
            design_filter(self.fs, cfg)


if __name__ == '__main__':
    unittest.main()
