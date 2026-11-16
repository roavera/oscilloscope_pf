import unittest

import numpy as np

from communication.commands import Waveform
from communication.simulator import FakeBlackPill


class SimulatorWaveformTests(unittest.TestCase):
    def test_pwm_duty_cycle(self):
        sim = FakeBlackPill(fs=10_000, frames_per_block=100)
        sim.freq[0] = 100.0
        sim.wave[0] = Waveform.PULSE
        sim.duty[0] = 0.25

        values = np.concatenate([sim._generator(0, 1000) for _ in range(2)])
        high_fraction = np.mean(values > 0)

        self.assertAlmostEqual(high_fraction, 0.25, delta=0.01)

    def test_dc_has_no_alternating_samples(self):
        sim = FakeBlackPill(fs=10_000, frames_per_block=100)
        sim.wave[0] = Waveform.DC

        values = sim._generator(0, 1000)

        self.assertTrue(np.all(values == 1.0))


if __name__ == "__main__":
    unittest.main()
