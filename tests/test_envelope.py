"""Envolvente sin hardware: python -m unittest discover -s tests -p test_envelope.py -v"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from collections import deque
import unittest
from unittest.mock import patch, PropertyMock

import numpy as np
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from acquisition.acquisition_processor import AcquisitionProcessor
from acquisition.modes.envelope import EnvelopeResult
from gui.oscilloscope_widget import OscilloscopeWidget


def signal(count=1500, start=0):
    t = np.arange(start, start + count, dtype=float)
    phase = 2*np.pi*(t - 0.37)/64
    # Amplitudes diferentes entre ciclos; CH2 conserva una relación conocida.
    amplitude = 0.01 + 0.002 * (np.floor(t / 64) % 4)
    ch1 = (amplitude * np.sin(phase)).astype(np.float32)
    return np.column_stack((ch1, -2*ch1 + 0.005)).astype(np.float32)


class EnvelopeAlgorithmTests(unittest.TestCase):
    def processor(self, count=4):
        p = AcquisitionProcessor()
        p.configure(mode="envelope", envelope_count=count)
        return p

    def test_minimum_and_maximum_at_each_time_position(self):
        p = self.processor()
        rows = np.array([[4, -5, 1], [-2, 3, 8], [1, 0, -6], [0, 1, 2]], dtype=np.float32)
        for row in rows:
            result = p.process(row)
        self.assertIsInstance(result, EnvelopeResult)
        np.testing.assert_array_equal(result.minimum, [-2, -5, -6])
        np.testing.assert_array_equal(result.maximum, [4, 3, 8])
        self.assertEqual(p.get_progress(), (4, 4))

    def test_single_capture_both_bounds_equal_original(self):
        p = self.processor()
        data = np.arange(8, dtype=np.float32)
        result = p.process(data)
        np.testing.assert_array_equal(result.minimum, data)
        np.testing.assert_array_equal(result.maximum, data)
        self.assertEqual(p.get_progress(), (1, 4))

    def test_old_extremes_expire_when_their_capture_leaves_window(self):
        p = self.processor()
        p.process(np.array([-20, 20], dtype=np.float32))
        for _ in range(3):
            result = p.process(np.array([1, 2], dtype=np.float32))
        np.testing.assert_array_equal(result.minimum, [-20, 2])
        np.testing.assert_array_equal(result.maximum, [1, 20])
        result = p.process(np.array([1, 2], dtype=np.float32))
        np.testing.assert_array_equal(result.minimum, [1, 2])
        np.testing.assert_array_equal(result.maximum, [1, 2])

    def test_random_rolling_result_matches_brute_force(self):
        p = self.processor(16)
        reference = deque(maxlen=16)
        rng = np.random.default_rng(81)
        for _ in range(40):
            data = rng.normal(size=127).astype(np.float32)
            reference.append(data)
            result = p.process(data)
            np.testing.assert_array_equal(result.minimum, np.min(reference, axis=0))
            np.testing.assert_array_equal(result.maximum, np.max(reference, axis=0))

    def test_channels_inputs_outputs_and_diagnostics_are_independent(self):
        p = self.processor()
        data = np.arange(8, dtype=np.float32)
        p.process(data, channel=1)
        p.process(-data, channel=2)
        data[:] = 999
        state = p.get_state(1)
        state["captures"][0][:] = 999
        result = p.process(np.arange(8), channel=1)
        np.testing.assert_array_equal(result.minimum, np.arange(8))
        result.minimum[:] = 999
        np.testing.assert_array_equal(p.process(np.arange(8)).minimum, np.arange(8))
        np.testing.assert_array_equal(p.process(-np.arange(8), channel=2).maximum, -np.arange(8))

    def test_empty_invalid_shape_count_and_nonfinite_do_not_accumulate(self):
        p = self.processor()
        result = p.process([])
        self.assertEqual(result.minimum.size, 0)
        self.assertEqual(result.maximum.size, 0)
        for data in ([np.nan], [np.inf], np.zeros((8, 2))):
            with self.assertRaises(ValueError):
                p.process(data)
        for count in (0, -1, 8, True, 4.0):
            with self.assertRaises(ValueError):
                p.set_envelope_count(count)
        self.assertEqual(p.get_progress(), (0, 4))

    def test_resets_on_shape_configuration_and_mode_changes(self):
        p = self.processor()
        p.process(np.ones(8))
        result = p.process(np.full(4, 3))
        self.assertEqual(p.get_progress(), (1, 4))
        np.testing.assert_array_equal(result.minimum, np.full(4, 3))
        p.set_envelope_count(16)
        self.assertEqual(p.get_progress(), (0, 16))
        p.process(np.ones(4))
        p.set_mode("average")
        p.set_mode("envelope")
        self.assertEqual(p.get_progress(), (0, 16))


class EnvelopeWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def widget(self):
        with patch.object(OscilloscopeWidget, "start_acquisition"):
            w = OscilloscopeWidget()
        self.addCleanup(w.shutdown)
        w.set_time_per_division(24 / (w.sample_rate*12))
        w.set_acquisition_mode("envelope")
        w.set_envelope_count(4)
        return w

    def fill(self, w):
        w.on_samples_received(signal())
        w.process_data()
        self.assertIsNotNone(w.last_envelope)
        self.assertEqual(w.acquisition_processor.get_progress(), (4, 4))

    def test_dialog_selectors_have_independent_counts_and_progress(self):
        w = self.widget()
        panel = w.controls.acquisition_controls
        self.assertEqual(panel.mode_combo.currentData(), "envelope")
        self.assertTrue(panel.envelope_count_combo.isEnabled())
        self.assertFalse(panel.average_count_combo.isEnabled())
        panel.envelope_count_combo.setCurrentIndex(2)
        self.assertEqual(w.acquisition_processor.get_envelope_count(), 32)
        self.assertEqual(w.acquisition_processor.get_average_count(), 16)
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("average"))
        self.assertEqual(w.acquisition_processor.get_mode(), "average")
        self.assertFalse(panel.envelope_count_combo.isEnabled())
        self.assertTrue(panel.average_count_combo.isEnabled())

    def test_bands_for_both_channels_preserve_common_time_and_inverse_relationship(self):
        w = self.widget()
        self.fill(w)
        env = w.last_envelope
        self.assertIsNone(w.last_acquisition)
        np.testing.assert_allclose(env.minimum[:, 1], -2*env.maximum[:, 0]+0.005, atol=1e-7)
        np.testing.assert_allclose(env.maximum[:, 1], -2*env.minimum[:, 0]+0.005, atol=1e-7)
        self.assertTrue(np.any(env.maximum > env.minimum))
        plot = w.plot
        self.assertFalse(plot.curve.isVisible())
        self.assertFalse(plot.curve_ch2.isVisible())
        for ch in (1, 2):
            lower, upper = plot.envelope_curves[ch]
            self.assertTrue(lower.isVisible())
            self.assertTrue(upper.isVisible())
            self.assertTrue(plot.envelope_fills[ch].isVisible())
            np.testing.assert_array_equal(lower.xData, upper.xData)
            np.testing.assert_array_equal(lower.xData, plot.envelope_curves[1][0].xData)

    def test_stop_scaling_visibility_and_redraw_preserve_bounds(self):
        w = self.widget()
        self.fill(w)
        low, high = w.last_envelope.minimum.copy(), w.last_envelope.maximum.copy()
        w.stop()
        w.on_samples_received(signal(600, start=1500))
        w.process_data()
        with patch.object(w.acquisition_processor, "process") as process:
            w.set_ch2_volts_per_division(0.04)
            w.set_ch2_position(1)
            w.set_horizontal_position(1)
            w.set_time_per_division(w.time_per_division*2)
            w._redraw_last_acquisition()
            process.assert_not_called()
        np.testing.assert_array_equal(w.last_envelope.minimum, low)
        np.testing.assert_array_equal(w.last_envelope.maximum, high)
        np.testing.assert_allclose(w.plot.envelope_curves[2][0].yData, low[:, 1]/0.04+1)
        w.controls.ch2_controls.visible_checkbox.setChecked(False)
        for item in (*w.plot.envelope_curves[2], w.plot.envelope_fills[2]):
            self.assertFalse(item.isVisible())
        self.assertTrue(w.plot.envelope_curves[1][0].isVisible())

    def test_single_needs_n_distinct_captures_and_freezes_both_bounds(self):
        w = self.widget()
        self.enterContext(patch.object(type(w.acquisition), "is_running",
                                      new_callable=PropertyMock, return_value=True))
        w.single()
        w.on_samples_received(signal(100))
        w.process_data()
        self.assertTrue(w.running)
        self.assertEqual(w.acquisition_processor.get_progress(), (1, 4))
        w.on_samples_received(signal(1400, start=100))
        w.process_data()
        self.assertFalse(w.running)
        self.assertFalse(w.display_timer.isActive())
        for ch in (1, 2):
            self.assertEqual(w.acquisition_processor.get_state(ch)["acquisitions"], 4)
        low, high = w.last_envelope.minimum.copy(), w.last_envelope.maximum.copy()
        w.on_samples_received(signal(600, start=1500))
        w.process_data()
        np.testing.assert_array_equal(w.last_envelope.minimum, low)
        np.testing.assert_array_equal(w.last_envelope.maximum, high)

    def test_no_trigger_and_no_duplicate_when_new_tail_arrives(self):
        w = self.widget()
        w.on_samples_received(np.ones((300, 2), dtype=np.float32))
        w.process_data()
        self.assertIsNone(w.last_envelope)
        data = np.full((200, 2), -1, dtype=np.float32)
        data[64:] = 1
        w.on_samples_received(data)
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (1, 4))
        w.on_samples_received(np.ones((200, 2), dtype=np.float32))
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (1, 4))

    def test_switch_to_sampling_or_average_hides_all_bands_after_next_capture(self):
        for mode in ("sampling", "average"):
            with self.subTest(mode=mode):
                w = self.widget()
                self.fill(w)
                w.set_acquisition_mode(mode)
                w.on_samples_received(signal(1500, start=1500))
                w.process_data()
                self.assertIsNone(w.last_envelope)
                self.assertIsNotNone(w.last_acquisition)
                self.assertTrue(w.plot.curve.isVisible())
                self.assertIsNone(w.plot._raw_envelope)
                for ch in (1, 2):
                    self.assertFalse(w.plot.envelope_fills[ch].isVisible())
                    for curve in w.plot.envelope_curves[ch]:
                        self.assertFalse(curve.isVisible())

    def test_source_ch2_reset_and_discontinuity_preserve_display(self):
        w = self.widget()
        self.fill(w)
        w.set_trigger_channel(2)
        self.assertEqual(w.acquisition_processor.get_progress(), (0, 4))
        w.on_samples_received(signal(1500, start=1500))
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (4, 4))
        previous = w.last_envelope.minimum.copy()
        w.stop()
        w._on_discontinuity(w._source_generation)
        w.process_data()
        np.testing.assert_array_equal(w.last_envelope.minimum, previous)
        w.running = True
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (0, 4))
        np.testing.assert_array_equal(w.last_envelope.minimum, previous)

    def test_track_does_not_invent_a_central_waveform_and_manual_still_works(self):
        w = self.widget()
        w.plot.set_signal(signal(100), w.sample_rate)
        self.fill(w)
        readouts = []
        w.plot.cursor_readout_changed.connect(readouts.append)
        w.plot.set_cursor_mode("Track")
        self.assertIn("no disponible en Envolvente", readouts[-1])
        for point in w.plot.cursor_points:
            self.assertEqual(len(point.data), 0)
        w.plot.set_cursor_mode("Manual", "Tiempo")
        self.assertIn("Δt", readouts[-1])
        w.plot.set_cursor_mode("Manual", "Tensión")
        self.assertIn("ΔV", readouts[-1])

    def test_plot_validation_theme_and_clear(self):
        w = self.widget()
        self.fill(w)
        plot = w.plot
        previous = w.last_envelope.minimum.copy()
        plot.set_display_theme("light")
        np.testing.assert_array_equal(plot._raw_envelope[0], previous)
        valid = np.ones((10, 2), dtype=np.float32)
        for low, high in ((valid[:, 0], valid), (valid, valid[:5]),
                          (valid*2, valid), (valid*np.nan, valid)):
            with self.assertRaises(ValueError):
                plot.set_envelope(low, high, w.sample_rate)
        plot.clear_signal()
        self.assertIsNone(plot._raw_envelope)
        for ch in (1, 2):
            self.assertFalse(plot.envelope_fills[ch].isVisible())
            self.assertIsNone(plot.envelope_curves[ch][0].xData)

    def test_run_resets_progress_and_does_not_use_stopped_history(self):
        w = self.widget()
        self.fill(w)
        self.enterContext(patch.object(type(w.acquisition), "is_running",
                                      new_callable=PropertyMock, return_value=True))
        previous = w.last_envelope.minimum.copy()
        w.stop()
        w.on_samples_received(signal(600, start=1500))
        w.run()
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (0, 4))
        np.testing.assert_array_equal(w.last_envelope.minimum, previous)
        w.on_samples_received(signal(600, start=2100))
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (4, 4))

    def test_parameter_changes_reset_counts_and_source_reset_clears_bands(self):
        actions = (
            lambda w: w.set_envelope_count(16),
            lambda w: w.set_trigger_level(0.001),
            lambda w: w.set_trigger_slope("Falling"),
            lambda w: w.set_time_per_division(w.time_per_division*2),
            lambda w: w.set_horizontal_position(1),
        )
        for action in actions:
            with self.subTest(action=action):
                w = self.widget()
                self.fill(w)
                previous = w.last_envelope.minimum.copy()
                action(w)
                self.assertEqual(w.acquisition_processor.get_progress()[0], 0)
                np.testing.assert_array_equal(w.last_envelope.minimum, previous)
        w = self.widget()
        self.fill(w)
        w.reset_acquisition(97656.25)
        self.assertEqual(w.acquisition_processor.get_progress(), (0, 4))
        self.assertIsNone(w.last_envelope)
        self.assertIsNone(w.plot._raw_envelope)
        self.assertFalse(w.plot.envelope_fills[1].isVisible())

    def test_simulated_usb_envelope_and_single_end_to_end(self):
        w = self.widget()
        w.set_envelope_count(16)

        def wait_for(predicate):
            loop = QEventLoop()
            poll = QTimer()
            poll.setInterval(10)
            poll.timeout.connect(lambda: loop.quit() if predicate() else None)
            timeout = QTimer()
            timeout.setSingleShot(True)
            timeout.timeout.connect(loop.quit)
            poll.start()
            timeout.start(4000)
            loop.exec()
            poll.stop()
            timeout.stop()
            self.assertTrue(predicate(), w._audio_error)

        w.change_acquisition_source(w.acquisition.SIMULATOR)
        wait_for(lambda: w.acquisition_processor.get_progress()[0] == 16)
        self.assertIsNone(w._audio_error)
        self.assertEqual(w.last_envelope.minimum.shape[1], 2)
        w.single()
        wait_for(lambda: not w.running)
        self.assertTrue(w.trigger_found)
        self.assertEqual(w.acquisition_processor.get_progress(1), (16, 16))
        self.assertEqual(w.acquisition_processor.get_progress(2), (16, 16))
        self.assertEqual(w.acquisition_processor.get_state()["acquisitions"], 16)


if __name__ == "__main__":
    unittest.main()
