"""Ejecutar con: python -m unittest discover -s tests -p test_high_resolution.py -v"""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from unittest.mock import patch

import numpy as np
from acquisition.acquisition_processor import AcquisitionProcessor
from acquisition.modes.high_resolution import effective_high_resolution_factor


class HiResAlgorithmTests(unittest.TestCase):
    def test_exact_block_averaging(self):
        p = AcquisitionProcessor()
        p.configure(mode="high_resolution", high_resolution_factor=4)
        original = np.arange(16, dtype=np.float32)
        out = p.process(original)
        np.testing.assert_allclose(out, [1.5, 5.5, 9.5, 13.5])
        np.testing.assert_array_equal(original, np.arange(16))

    def test_two_channels_independent(self):
        p = AcquisitionProcessor()
        p.configure(mode="high_resolution", high_resolution_factor=4)
        x = np.arange(32, dtype=np.float32)
        a = p.process(x, channel=1)
        b = p.process(2*x+3, channel=2)
        np.testing.assert_allclose(b, 2*a+3)
        self.assertEqual(p.get_progress(1), (0, 1))

    def test_short_windows_do_not_collapse_to_one_point(self):
        self.assertEqual(effective_high_resolution_factor(6, 16), 2)
        self.assertEqual(effective_high_resolution_factor(1, 16), 1)
        p = AcquisitionProcessor()
        p.configure(mode="high_resolution", high_resolution_factor=16)
        self.assertEqual(len(p.process(np.arange(6, dtype=np.float32))), 3)

    def test_reject_invalid_data(self):
        p = AcquisitionProcessor()
        p.set_mode("high_resolution")
        for sample in ([0., np.nan], [np.inf], np.ones((4, 2))):
            with self.assertRaises(ValueError):
                p.process(sample)
        for factor in (0, 3, True, 4.0):
            with self.assertRaises(ValueError):
                p.set_high_resolution_factor(factor)

    def test_noise_reduction(self):
        p = AcquisitionProcessor()
        p.configure(mode="high_resolution", high_resolution_factor=16)
        rng = np.random.default_rng(42)
        original = np.full(16000, 0.25, dtype=np.float32) + rng.normal(0, 0.2, 16000)
        filtered = p.process(original)
        self.assertLess(np.std(filtered-0.25), np.std(original-0.25)/3)


class HiResWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from PySide6.QtWidgets import QApplication
        cls.app = QApplication.instance() or QApplication([])

    def test_ui_factor_and_time_axis(self):
        from gui.oscilloscope_widget import OscilloscopeWidget
        with patch.object(OscilloscopeWidget, "start_acquisition"):
            w = OscilloscopeWidget()
        try:
            w.set_acquisition_mode("high_resolution")
            panel = w.controls.acquisition_controls
            self.assertTrue(panel.high_resolution_factor_combo.isEnabled())
            self.assertEqual(panel.mode_combo.currentData(), "high_resolution")
            w.set_high_resolution_factor(4)
            raw = np.column_stack((np.arange(32), 2*np.arange(32))).astype(np.float32)
            w._show_acquisition(raw, trigger_sample=16.25)
            self.assertEqual(w.last_acquisition.shape, (8, 2))
            np.testing.assert_allclose(w.last_acquisition[:, 1], 2*w.last_acquisition[:, 0])
            times = w.plot._cursor_signal_x
            np.testing.assert_allclose(np.diff(times), np.full(7, 4/w.sample_rate))
            expected_x0 = w.plot.horizontal_position + (1.5-16.25)/w.sample_rate + (w.plot.trigger_position*w.plot.time_per_division*w.plot.horizontal_divisions)
            self.assertAlmostEqual(times[0], expected_x0)
        finally:
            w.shutdown()


if __name__ == "__main__":
    unittest.main()
