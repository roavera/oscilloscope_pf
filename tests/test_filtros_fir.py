"""Respuesta en frecuencia, continuidad entre bloques y captura FIR."""
from dataclasses import replace
import unittest

import numpy as np
from scipy.signal import freqz
from processing.filters import FilterConfig, apply_filter, design_filter
from processing.stream_filter import ContinuousFilter


class TestFIR(unittest.TestCase):
    config = FilterConfig(enabled=True, family="fir", cutoff_low=4000, cutoff_high=10000)
    rate = 48000

    def test_respuesta(self):
        for kind, gains in (("lowpass", [1, 0, 0]), ("highpass", [0, 0, 1]),
                            ("bandpass", [0, 1, 0]), ("bandstop", [1, 0, 1])):
            with self.subTest(kind=kind):
                coeff = design_filter(self.rate, replace(self.config, kind=kind))
                np.testing.assert_allclose(coeff, coeff[::-1], atol=1e-14)
                _, h = freqz(coeff, worN=[500, 7000, 17000], fs=self.rate)
                np.testing.assert_allclose(abs(h), gains, atol=.005)

    def test_bloques_y_cambio_de_configuracion(self):
        data = np.random.default_rng(17).normal(size=(800, 2)).astype(np.float32)
        stream = ContinuousFilter()
        stream.process(data, self.rate, replace(self.config, family="iir"))
        for channel, index in (("ch1", 0), ("ch2", 1)):
            cfg = replace(self.config, channel=channel)
            coeff = design_filter(self.rate, cfg)
            pieces = [stream.process(part, self.rate, cfg) for part in np.array_split(data, 31)]
            out = np.concatenate(pieces)
            expected = np.convolve(data[:, index], coeff)[:len(data)]
            np.testing.assert_allclose(out[:, index], expected, atol=1e-7)
            np.testing.assert_array_equal(out[:, 1-index], data[:, 1-index])

    def test_captura_independiente(self):
        data = np.random.default_rng(2).normal(size=(350, 2)).astype(np.float32)
        coeff = design_filter(self.rate, self.config)
        out = apply_filter(data, self.rate, self.config)
        for i in range(2):
            padded = np.pad(data[:, i], (len(coeff)-1, 0), mode="edge")
            np.testing.assert_allclose(out[:, i], np.convolve(padded, coeff, "valid"), atol=1e-7)
