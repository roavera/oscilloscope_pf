"""Pruebas deterministas de Timeout, Runt y Logic. No requieren PySide6.

python -m unittest discover -s tests -p test_trigger_advanced.py -v
"""
import unittest
import numpy as np

from trigger.timeout import TimeoutTrigger
from trigger.runt import RuntTrigger
from trigger.logic import LogicTrigger
from trigger.holdoff import TriggerHoldoff
from acquisition.capture_sequence import CaptureSequence

FS = 97656.25


class TimeoutTests(unittest.TestCase):
    def test_constant_high_and_low_after_threshold(self):
        for state, signal in [('high', 1.), ('low', -1.), ('either', 1.)]:
            with self.subTest(state=state):
                t = TimeoutTrigger(sample_rate=FS, timeout_us=2000, state=state)
                out = t.crossings(np.full(500, signal))
                self.assertEqual(len(out), 1)
                self.assertEqual(out[0].index, 196)

    def test_constant_equal_to_threshold_still_times_out(self):
        t = TimeoutTrigger(sample_rate=FS, timeout_us=1000, state="either")
        events = t.crossings(np.zeros(500))
        self.assertEqual(len(events), 1)

    def test_excludes_wrong_state(self):
        t = TimeoutTrigger(sample_rate=FS, timeout_us=1000, state='high')
        self.assertEqual(t.crossings(np.full(700, -1.0)), [])

    def test_short_segments_never_trigger(self):
        t = TimeoutTrigger(sample_rate=FS, timeout_us=1000)
        x = np.where((np.arange(1000) // 20) % 2, -1.0, 1.0)
        self.assertEqual(t.crossings(x), [])

    def test_ends_when_new_edge_appears_and_rearms(self):
        t = TimeoutTrigger(sample_rate=FS, timeout_us=500, state='high')
        x = np.r_[np.full(100, 1.), np.full(100, -1.), np.full(100, 1.)]
        events = t.crossings(x)
        self.assertEqual([e.index for e in events], [49, 249])

    def test_absolute_cross_block_windows_do_not_reset_or_repeat(self):
        t = TimeoutTrigger(sample_rate=FS, timeout_us=3000)
        x = np.full(1200, 1.)
        events = []
        for start, end in [(0,120), (80,200), (150,300), (245,400), (350,600), (550,800), (750,1200)]:
            t.set_window_start(start)
            events.extend(start+e.index for e in t.crossings(x[start:end]))
        self.assertIn(293, events)
        self.assertEqual(len(set(events)), 1)

    def test_delayed_end_of_buffer_event_reappears_with_post_samples(self):
        t = TimeoutTrigger(sample_rate=FS, timeout_us=500)
        x = np.ones(200)
        t.set_window_start(0)
        first = t.crossings(x[:50])
        self.assertEqual(first, [])  # Evento justo en el borde, falta posttrigger.
        t.set_window_start(10)
        second = t.crossings(x[10:70])
        self.assertEqual(len(second), 1)
        self.assertEqual(second[0].index + 10, 49)

    def test_capture_sequence_with_holdoff_and_state(self):
        x = np.r_[np.ones(250), -np.ones(250), np.ones(250), -np.ones(250)].astype(np.float32)
        stereo = np.column_stack((x,x))
        t = TimeoutTrigger(sample_rate=FS, timeout_us=1000)
        seq = CaptureSequence()
        h = TriggerHoldoff(.002)
        frames = list(seq.captures(stereo, 0, 100, t, 1, holdoff=h, sample_rate=FS))
        self.assertGreaterEqual(len(frames), 2)
        self.assertTrue(all(f.samples.shape == (100,2) for f in frames))
        self.assertTrue(all(b.trigger_id-a.trigger_id >= 195 for a,b in zip(frames, frames[1:])))

    def test_timeout_parameter_validation_and_input(self):
        t = TimeoutTrigger()
        for kwargs in [dict(state='bad', timeout_us=10), dict(state='either', timeout_us=-10),
                       dict(state='high', timeout_us=float('nan'))]:
            with self.assertRaises(ValueError):
                t.set_timeout_settings(**kwargs)
        self.assertEqual(t.crossings(np.array([1.,np.nan,2.])), [])
        with self.assertRaises(ValueError):
            t.crossings(np.zeros((20,2)))


class RuntTests(unittest.TestCase):
    def test_high_runt_amplitude_insufficient(self):
        x = np.r_[np.full(40, -1.), np.full(20, .0), np.full(40,-1.)]
        t = RuntTrigger(polarity='high', lower_volts=-.2, upper_volts=.2)
        events=t.crossings(x)
        self.assertEqual(len(events), 1)
        self.assertTrue(59 <= events[0].index <= 61)

    def test_normal_high_pulse_is_not_runt(self):
        x = np.r_[np.full(40, -1.), np.full(20, 1.), np.full(40,-1.)]
        self.assertEqual(RuntTrigger(polarity='high').crossings(x), [])

    def test_single_sample_full_step_no_false_runt(self):
        x = np.r_[np.full(30,-1.), np.full(30,1.), np.full(30,-1.)]
        self.assertEqual(RuntTrigger(polarity='high').crossings(x), [])

    def test_low_runt_and_full_pulse(self):
        runt = np.r_[np.full(40, 1.), np.full(20, 0.), np.full(40,1.)]
        full = np.r_[np.full(40, 1.), np.full(20, -1.), np.full(40,1.)]
        t = RuntTrigger(polarity='low')
        self.assertEqual(len(t.crossings(runt)), 1)
        self.assertEqual(t.crossings(full), [])

    def test_minimum_width_rejects_short_runt(self):
        x = np.r_[np.full(40,-1.), np.full(2,0.), np.full(40,-1.)]
        t=RuntTrigger(min_width_us=100.)
        self.assertEqual(t.crossings(x), [])
        t.set_runt_settings(polarity='high', lower_volts=-.2,
                            upper_volts=.2, min_width_us=0.)
        self.assertEqual(len(t.crossings(x)), 1)

    def test_runt_invalid_settings(self):
        t = RuntTrigger()
        for kw in (dict(polarity='x',lower_volts=-.2,upper_volts=.2,min_width_us=0),
                   dict(polarity='high',lower_volts=.3,upper_volts=.2,min_width_us=0),
                   dict(polarity='high',lower_volts=-.3,upper_volts=.2,min_width_us=-2)):
            with self.assertRaises(ValueError):
                t.set_runt_settings(**kw)


class LogicTests(unittest.TestCase):
    def test_and_ch1_high_ch2_low_rising(self):
        a = np.r_[-np.ones(30), np.ones(30), np.ones(30)]
        b = np.r_[np.ones(30), np.ones(30), -np.ones(30)]
        t = LogicTrigger(ch1_state='high', ch2_state='low', operator='and')
        events = t.crossings(np.column_stack((a,b)))
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].index, 59)

    def test_or_xor_and_falling(self):
        a = np.r_[-np.ones(20), np.ones(20), np.ones(20), -np.ones(20)]
        b = np.r_[-np.ones(20), -np.ones(20), np.ones(20), np.ones(20)]
        data=np.column_stack((a,b))
        self.assertEqual(len(LogicTrigger(operator='or').crossings(data)), 1)
        self.assertEqual(len(LogicTrigger(operator='xor').crossings(data)), 2)
        self.assertEqual(len(LogicTrigger(operator='and',edge='falling').crossings(data)), 1)

    def test_ch2_level_in_volts_and_input_validation(self):
        a = np.r_[np.full(30,-1.),np.full(30,1.)]
        b = np.r_[np.full(30,-1.),np.full(30,0.4)]
        data=np.column_stack((a,b))
        t=LogicTrigger(ch2_level=.6)
        self.assertEqual(t.crossings(data), [])
        t.set_logic_settings(ch1_level=0,ch2_level=.1,ch1_state='high',ch2_state='high',operator='and',edge='rising')
        self.assertEqual(len(t.crossings(data)), 1)
        with self.assertRaises(ValueError): t.crossings(a)
        with self.assertRaises(ValueError): t.set_logic_settings(ch1_level=0,ch2_level=0,ch1_state='bad',ch2_state='low',operator='and',edge='rising')

    def test_capture_sequence_stereo_logic_and_holdoff(self):
        indices=np.arange(3000)
        one=np.where(indices%400 < 200,1.,-1.)
        two=np.where(indices%400 >=100, -1.,1.)
        data=np.column_stack((one,two)).astype(np.float32)
        t=LogicTrigger(ch1_state='high',ch2_state='low')
        h=TriggerHoldoff(.003)
        frames=list(CaptureSequence().captures(data,0,60,t,1,holdoff=h,sample_rate=FS))
        self.assertGreater(len(frames),3)
        self.assertTrue(all(f.samples.shape==(60,2) for f in frames))


if __name__=='__main__':
    unittest.main()
