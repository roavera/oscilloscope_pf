"""Etapa 1 — pruebas NumPy: python -m unittest discover -s tests -p test_unified_trigger.py -v"""
import unittest
import numpy as np

from trigger.edge_trigger import Edge_Trigger
from acquisition.capture_sequence import CaptureSequence

FS = 97656.25


def simulated_stereo(frequency=200, noise=0.1, seconds=0.5, seed=11):
    rng = np.random.default_rng(seed)
    t = np.arange(int(seconds * FS), dtype=np.float64) / FS
    clean = np.sin(2 * np.pi * frequency * t)
    channel1 = clean + rng.normal(0.0, noise, len(t))
    channel2 = 0.5 * clean + rng.normal(0.0, noise, len(t))
    return np.column_stack((channel1, channel2)).astype(np.float32)


class UnifiedTriggerTests(unittest.TestCase):
    def test_both_paths_use_identical_events(self):
        data = simulated_stereo(seconds=0.20)
        trigger = Edge_Trigger(level=0, slope="Rising", position=0.5)
        count = 120
        index = trigger.find(data[:, 0], count)
        allowed = [e for e in trigger.crossings(data[:, 0])
                   if int(count * trigger.position) <= e.index <= len(data) - count + int(count * trigger.position)]
        self.assertIsNotNone(index)
        self.assertEqual(index, allowed[-1].index)
        self.assertAlmostEqual(trigger.fractional_offset, allowed[-1].fraction)

    def test_repeated_sine_noisy_200_hz_preserves_amplitude(self):
        data = simulated_stereo(frequency=200, noise=0.1, seconds=0.6)
        trigger = Edge_Trigger(level=0.0, slope="Rising")
        count = int(FS * 0.012)
        frames = list(CaptureSequence().captures(data, 0, count, trigger, 1))
        self.assertGreaterEqual(len(frames), 30)
        averaged = np.mean([f.samples[:, 0] for f in frames], axis=0)
        peak = (np.max(averaged) - np.min(averaged)) / 2
        self.assertGreater(peak, 0.88)
        self.assertLess(peak, 1.10)
        # A falta de Holdoff, la banda debe evitar los falsos cruces grandes.
        ids = np.array([f.trigger_id for f in frames])
        self.assertTrue(np.all(np.diff(ids) >= count))

    def test_higher_frequencies_still_detect_events(self):
        for frequency in (1000, 5000, 10000):
            with self.subTest(frequency=frequency):
                data = simulated_stereo(frequency, 0.05, 0.10)
                events = Edge_Trigger().crossings(data[:, 0])
                self.assertGreater(len(events), int(frequency * 0.08))
                self.assertLess(len(events), int(frequency * 0.12))

    def test_both_channels_share_time_reference_and_raw_noise(self):
        data = simulated_stereo(noise=0.05, seconds=0.12)
        trigger = Edge_Trigger(slope="Rising")
        frames = list(CaptureSequence().captures(data, 0, 200, trigger, 2))
        self.assertGreater(len(frames), 2)
        for frame in frames:
            self.assertEqual(frame.samples.shape, (200, 2))
            self.assertEqual(frame.raw_samples.shape, (201, 2))
            self.assertAlmostEqual(frame.raw_trigger_sample,
                                   frame.trigger_sample + (frame.raw_trigger_sample % 1), places=6)
            self.assertEqual(frame.trigger_sample, 100)
            self.assertGreater(np.std(frame.samples[:, 0]), 0.2)

    def test_missing_trigger_and_nonfinite_samples(self):
        trig = Edge_Trigger()
        self.assertIsNone(trig.find(np.ones(100), 24))
        self.assertEqual(trig.crossings(np.ones(100)), [])
        self.assertEqual(trig.crossings(np.array([0, np.nan, 1])), [])
        seq = CaptureSequence()
        data = np.ones((100, 2), dtype=np.float32)
        self.assertEqual(list(seq.captures(data, 0, 24, trig, 1)), [])
        data[20, 1] = np.nan
        self.assertEqual(list(seq.captures(data, 0, 24, trig, 1)), [])

    def test_trigger_direction(self):
        data = simulated_stereo(frequency=200, noise=0, seconds=0.1)
        rising = Edge_Trigger(slope="Rising").crossings(data[:, 0])
        falling = Edge_Trigger(slope="Falling").crossings(data[:, 0])
        self.assertGreater(len(rising), 10)
        self.assertGreater(len(falling), 10)
        for a, b in zip(rising[1:], falling[1:]):
            self.assertGreater(abs(a.index - b.index), FS / 200 * 0.3)

    def test_no_duplicate_with_overlapping_snapshots(self):
        data = simulated_stereo(seconds=0.4)
        seq = CaptureSequence()
        trigger = Edge_Trigger()
        ids = []
        for total in range(3000, len(data), 1100):
            first = max(0, total - 4000)
            snapshot = data[first:total]
            ids.extend(f.trigger_id for f in seq.captures(snapshot, first, 120, trigger, 1))
            self.assertEqual(list(seq.captures(snapshot, first, 120, trigger, 1)), [])
        self.assertEqual(ids, sorted(set(ids)))
        self.assertGreater(len(ids), 20)

    def test_state_changes_do_not_change_capture_samples(self):
        trig = Edge_Trigger()
        signal = simulated_stereo(noise=0, seconds=0.1)
        original = signal.copy()
        a = trig.find(signal[:, 0], 800)
        self.assertIsNotNone(a)
        np.testing.assert_array_equal(signal, original)
        trig.set_conditioning(smoothing_samples=1, hysteresis_fraction=0)
        b = trig.find(signal[:, 0], 800)
        self.assertIsNotNone(b)
        np.testing.assert_array_equal(signal, original)
        with self.assertRaises(ValueError):
            trig.set_conditioning(smoothing_samples=4)
        with self.assertRaises(ValueError):
            trig.set_conditioning(hysteresis_fraction=-0.1)


if __name__ == '__main__':
    unittest.main()
