"""Pruebas numéricas de Pulse Width: python -m unittest discover -s tests -p test_trigger_pulse_width.py -v"""
import unittest
import numpy as np

from trigger.edge_trigger import Edge_Trigger
from trigger.pulse_width import PulseWidthTrigger
from trigger.holdoff import TriggerHoldoff
from acquisition.capture_sequence import CaptureSequence

FS = 97656.25


def square(frequency=1000, duration=0.15, duty=0.5, offset=0.0):
    t = np.arange(int(round(duration * FS)), dtype=np.float64) / FS
    return np.where((t * frequency) % 1.0 < duty, 1.0, -1.0) + offset


def stereo(x):
    return np.column_stack((x, np.roll(x, 12))).astype(np.float32)


class PulseWidthUnitTests(unittest.TestCase):
    def test_high_greater_400_us_matches_500_us(self):
        x = square()
        detector = PulseWidthTrigger(sample_rate=FS, lower_us=400)
        events = detector.crossings(x)
        self.assertGreater(len(events), 100)
        for ev in events[:12]:
            self.assertAlmostEqual(ev.width_seconds, .0005, delta=2 / FS)
            self.assertGreater(x[ev.index - 1], x[ev.index + 2])

    def test_less_than_300_never_triggers_500_us(self):
        ev = PulseWidthTrigger(sample_rate=FS, comparison='less', lower_us=300).crossings(square())
        self.assertEqual(len(ev), 0)

    def test_less_than_300_detects_200_us_high_pulse(self):
        ev = PulseWidthTrigger(sample_rate=FS, comparison='less', lower_us=300).crossings(
            square(duty=.2))
        self.assertGreater(len(ev), 100)
        self.assertLess(abs(ev[3].width_seconds - .0002), 2/FS)

    def test_within_range_and_outside(self):
        x = square()
        accepted = PulseWidthTrigger(sample_rate=FS, comparison='within',
                                     lower_us=450, upper_us=550).crossings(x)
        rejected = PulseWidthTrigger(sample_rate=FS, comparison='outside',
                                     lower_us=450, upper_us=550).crossings(x)
        self.assertGreater(len(accepted), 100)
        self.assertEqual(rejected, [])
        rejected_inside = PulseWidthTrigger(sample_rate=FS, comparison='within',
                                            lower_us=300, upper_us=400).crossings(x)
        accepted_outside = PulseWidthTrigger(sample_rate=FS, comparison='outside',
                                             lower_us=300, upper_us=400).crossings(x)
        self.assertEqual(rejected_inside, [])
        self.assertGreater(len(accepted_outside), 100)

    def test_low_polarity_closes_on_rising_edge(self):
        x = square()
        events = PulseWidthTrigger(sample_rate=FS, polarity='low', lower_us=400).crossings(x)
        self.assertGreater(len(events), 100)
        for e in events[1:10]:
            self.assertLess(x[e.index - 1], x[e.index + 2])

    def test_offset_and_level_are_in_calibrated_volts(self):
        x = square(offset=0.75)
        t = PulseWidthTrigger(level=0.75, sample_rate=FS)
        self.assertGreater(len(t.crossings(x)), 100)
        t.set_level(2.5)
        self.assertEqual(t.crossings(x), [])

    def test_invalid_input_no_signal_and_not_finite(self):
        t = PulseWidthTrigger(sample_rate=FS)
        self.assertEqual(t.crossings(np.ones(400)), [])
        self.assertEqual(t.crossings(np.zeros(400)), [])
        self.assertEqual(t.crossings(np.array([1.0, np.nan, -1, 1])), [])
        with self.assertRaises(ValueError):
            t.crossings(np.zeros((12, 2)))
        for params in (
            {'polarity': 'unknown', 'comparison': 'less', 'lower_us': 100, 'upper_us': 200},
            {'polarity': 'high', 'comparison': 'none', 'lower_us': 100, 'upper_us': 200},
            {'polarity': 'high', 'comparison': 'within', 'lower_us': 300, 'upper_us': 100},
            {'polarity': 'high', 'comparison': 'less', 'lower_us': float('nan'), 'upper_us': 100},
        ):
            with self.subTest(params=params), self.assertRaises(ValueError):
                t.set_width_settings(**params)
        with self.assertRaises(ValueError):
            t.set_sample_rate(0)

    def test_capture_api_and_subsample_offset(self):
        data = square()
        trigger = PulseWidthTrigger(sample_rate=FS, position=.25)
        index = trigger.find(data, 600)
        self.assertIsNotNone(index)
        capture = trigger.capture(stereo(data), index, 600)
        self.assertEqual(capture.shape, (600, 2))
        self.assertTrue(0 <= trigger.fractional_offset <= 1)
        candidates = [e for e in trigger.crossings(data)
                      if 150 <= e.index <= len(data) - (600 - 150)]
        self.assertEqual(index, candidates[-1].index)

    def test_minimum_index_filters_older_events_with_holdoff(self):
        data = square(duration=.08)
        trigger = PulseWidthTrigger(sample_rate=FS)
        eligible = [e for e in trigger.crossings(data)
                    if 75 <= e.index <= len(data) - 75]
        self.assertGreater(len(eligible), 2)
        threshold = eligible[-2].index + eligible[-2].fraction + .25
        idx = trigger.find(data, 150, minimum_index=threshold)
        self.assertEqual(idx, eligible[-1].index)
        self.assertIsNone(trigger.find(data, 150,
                      minimum_index=eligible[-1].index + eligible[-1].fraction + .25))

    def test_raw_samples_not_changed(self):
        x = square()
        original = x.copy()
        PulseWidthTrigger(sample_rate=FS).crossings(x)
        np.testing.assert_array_equal(x, original)

    def test_edge_unmodified_by_pulse_width(self):
        x = square()
        edge = Edge_Trigger(level=0, slope='Rising')
        before = edge.crossings(x)
        PulseWidthTrigger(sample_rate=FS).crossings(x)
        after = edge.crossings(x)
        self.assertEqual(before, after)

    def test_capture_sequence_ch1_and_ch2_with_holdoff(self):
        data = square(duration=.26)
        samples = stereo(data)
        pulse = PulseWidthTrigger(sample_rate=FS, lower_us=400)
        base = list(CaptureSequence().captures(samples, 0, 180, pulse, 1))
        holdoff = TriggerHoldoff(.02)
        selected = list(CaptureSequence().captures(
            samples, 0, 180, pulse, 2, holdoff=holdoff, sample_rate=FS))
        self.assertGreater(len(base), 50)
        self.assertGreater(len(selected), 4)
        self.assertLess(len(selected), len(base)/5)
        ids = np.array([c.trigger_id for c in selected])
        self.assertTrue(np.all(np.diff(ids) >= .02*FS-1))
        self.assertTrue(all(c.samples.shape == (180,2) for c in selected))

    def test_contiguous_snapshots_do_not_duplicate_events(self):
        d = stereo(square(duration=.25))
        pulse = PulseWidthTrigger(sample_rate=FS)
        seq, h, ids = CaptureSequence(), TriggerHoldoff(.01), []
        for end in range(3500, len(d), 1400):
            start = max(0,end-4500)
            selected = list(seq.captures(d[start:end],start,250,pulse,1,
                                         holdoff=h,sample_rate=FS))
            ids += [c.trigger_id for c in selected]
        self.assertGreater(len(ids), 3)
        self.assertEqual(len(ids),len(set(ids)))

    def test_changing_sample_rate_updates_microseconds_not_samples(self):
        t = PulseWidthTrigger(sample_rate=FS, lower_us=400)
        t.set_sample_rate(48000)
        fs = 48000
        i = np.arange(int(fs*.07))
        signal = np.where((i / fs % .001) < .0005,1.0,-1.0)
        e = t.crossings(signal)
        self.assertGreater(len(e), 30)
        self.assertAlmostEqual(e[3].width_seconds, .0005, delta=2/fs)


if __name__ == '__main__':
    unittest.main()
