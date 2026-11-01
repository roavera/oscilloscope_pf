"""MATH sin hardware: python -m unittest discover -s tests -p test_math_processor.py -v"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch, PropertyMock

import numpy as np
from PySide6.QtCore import QEventLoop, QTimer
from PySide6.QtWidgets import QApplication

from acquisition.acquisition_processor import AcquisitionConfig
from acquisition.modes.envelope import EnvelopeResult
from gui.oscilloscope_widget import OscilloscopeWidget
from processing.math_processor import MathProcessor, MathTraceProcessor


def signal(count=1500, start=0):
    t = np.arange(start, start+count, dtype=float)
    y = (.012*np.sin(2*np.pi*(t-.37)/64)).astype(np.float32)
    return np.column_stack((y, .5*y+.002)).astype(np.float32)


class MathProcessorTests(unittest.TestCase):
    def test_sum_subtraction_sources_time_and_units(self):
        p = MathProcessor()
        data = np.array([[1, 4], [2, 6], [-3, 1]], dtype=np.float32)
        result = p.evaluate(data, 1000)
        np.testing.assert_array_equal(result.values, [5, 8, -2])
        np.testing.assert_allclose(result.time, [0, .001, .002])
        self.assertEqual(result.unit, "u.a.")
        p.configure(operation="subtract")
        np.testing.assert_array_equal(p.evaluate(data, 1000).values, [-3, -4, -4])
        p.configure(source_a=2, source_b=1)
        np.testing.assert_array_equal(p.evaluate(data, 1000).values, [3, 4, 4])
        self.assertEqual(p.expression, "CH2 − CH1")

    def test_same_channel_cancel_or_double_and_no_mutation(self):
        p = MathProcessor()
        data = signal(20)
        original = data.copy()
        p.configure(operation="subtract", source_a=1, source_b=1)
        np.testing.assert_array_equal(p.evaluate(data, 48000).values, np.zeros(20))
        p.configure(operation="add")
        output = p.evaluate(data, 48000)
        np.testing.assert_array_equal(output.values, 2*data[:, 0])
        output.values[:] = 999
        np.testing.assert_array_equal(data, original)

    def test_invalid_inputs_configurations_and_overflow(self):
        p = MathProcessor()
        for samples in (np.zeros(3), np.zeros((3, 3)), [[np.nan, 0]], [[0, np.inf]]):
            with self.assertRaises(ValueError):
                p.evaluate(samples, 1000)
        for rate in (0, -1, np.inf, np.nan):
            with self.assertRaises(ValueError):
                p.evaluate(np.zeros((3, 2)), rate)
        for changes in ({"operation": "multiply"}, {"source_a": 3},
                        {"source_a": True}, {"source_b": 1.0}):
            before = p.config
            with self.assertRaises(ValueError):
                p.configure(**changes)
            self.assertEqual(p.config, before)
        with self.assertRaises(ValueError):
            p.evaluate([[np.finfo(np.float32).max, np.finfo(np.float32).max]], 1000)

    def test_empty_capture(self):
        result = MathProcessor().evaluate(np.empty((0, 2)), 48000)
        self.assertEqual(result.time.size, 0)
        self.assertEqual(result.values.size, 0)


class MathTraceTests(unittest.TestCase):
    def test_rolling_average_of_math_values_and_replay(self):
        config = AcquisitionConfig(mode="average", average_count=4)
        trace = MathTraceProcessor(config)
        captures = []
        for k in range(7):
            capture = np.column_stack((np.full(5, k), np.full(5, 2*k+1))).astype(np.float32)
            captures.append(capture)
            output = trace.process(capture, 48000)
        expected = np.stack(captures[-4:])
        np.testing.assert_allclose(output, (expected[:, :, 0]+expected[:, :, 1]).mean(axis=0))
        output = trace.configure_math(operation="subtract")
        np.testing.assert_allclose(output, (expected[:, :, 0]-expected[:, :, 1]).mean(axis=0))
        self.assertEqual(len(trace.history), 4)
        self.assertEqual(trace.acquisition.get_progress(), (4, 4))

    def test_envelope_of_difference_preserves_correlation(self):
        trace = MathTraceProcessor(AcquisitionConfig(mode="envelope", envelope_count=4))
        trace.configure_math(operation="subtract")
        for k in (1, 3, -2, 8):
            output = trace.process(np.full((5, 2), k, dtype=np.float32), 48000)
        self.assertIsInstance(output, EnvelopeResult)
        np.testing.assert_array_equal(output.minimum, np.zeros(5))
        np.testing.assert_array_equal(output.maximum, np.zeros(5))
        # Restar límites independientes produciría aquí un intervalo falso.
        output = trace.configure_math(operation="add")
        np.testing.assert_array_equal(output.minimum, np.full(5, -4))
        np.testing.assert_array_equal(output.maximum, np.full(5, 16))

    def test_history_copies_inputs_and_resets_on_shape_rate_or_config_change(self):
        trace = MathTraceProcessor(AcquisitionConfig(mode="average", average_count=4))
        data = signal(20)
        expected = data[:, 0]+data[:, 1]
        trace.process(data, 48000)
        data[:] = 999
        np.testing.assert_array_equal(trace.configure_math(operation="add"), expected)
        trace.process(signal(10), 48000)
        self.assertEqual(trace.acquisition.get_progress(), (1, 4))
        trace.process(signal(10), 97656.25)
        self.assertEqual(trace.acquisition.get_progress(), (1, 4))
        trace.configure_acquisition(AcquisitionConfig(mode="envelope", envelope_count=16))
        self.assertEqual(trace.acquisition.get_progress(), (0, 16))
        self.assertEqual(len(trace.history), 0)


class MathWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def widget(self, mode="sampling"):
        with patch.object(OscilloscopeWidget, "start_acquisition"):
            w = OscilloscopeWidget()
        self.addCleanup(w.shutdown)
        w.set_time_per_division(24/(48000*12))
        w.set_acquisition_mode(mode)
        w.set_average_count(4)
        w.set_envelope_count(4)
        w.controls.math_controls.visible_checkbox.setChecked(True)
        return w

    def fill(self, w):
        w.on_samples_received(signal())
        w.process_data()
        self.assertIsNotNone(w.last_math)

    def test_sampling_sum_and_subtraction_share_input_time_axis(self):
        w = self.widget()
        self.fill(w)
        np.testing.assert_allclose(w.last_math, w.last_acquisition.sum(axis=1))
        np.testing.assert_array_equal(w.plot.math_curve.xData, w.plot.curve.xData)
        w.stop()
        primary = w.last_acquisition.copy()
        w.set_math_configuration("subtract", 2, 1)
        np.testing.assert_allclose(w.last_math, primary[:, 1]-primary[:, 0])
        np.testing.assert_array_equal(w.last_acquisition, primary)

    def test_scale_position_and_visibility_are_independent(self):
        w = self.widget()
        self.fill(w)
        result = w.last_math.copy()
        primary = w.last_acquisition.copy()
        w.set_volts_per_division(.1)
        w.set_vertical_position(2)
        w.set_ch2_volts_per_division(.05)
        w.set_ch2_position(-2)
        np.testing.assert_array_equal(w.last_math, result)
        panel = w.controls.math_controls
        panel.scale_combo.setCurrentIndex(panel.scale_combo.findData(.1))
        panel.position_input.setValue(1)
        np.testing.assert_allclose(w.plot.math_curve.yData, result/.1+1, atol=1e-7)
        np.testing.assert_array_equal(w.last_acquisition, primary)
        w.controls.ch1_controls.visible_checkbox.setChecked(False)
        w.controls.ch2_controls.visible_checkbox.setChecked(False)
        self.assertTrue(w.plot.math_curve.isVisible())
        panel.visible_checkbox.setChecked(False)
        self.assertFalse(w.plot.math_curve.isVisible())
        panel.visible_checkbox.setChecked(True)
        np.testing.assert_array_equal(w.last_math, result)

    def test_navigation_preserves_simulator_mapping(self):
        w = self.widget()
        w.controls.navigation_buttons["math"].click()
        self.assertEqual(w.controls.pages.currentIndex(), 4)
        w.controls.set_simulator_visible(False)
        self.assertEqual(w.controls.pages.currentIndex(), 4)
        w.controls.set_simulator_visible(True)
        w.controls.navigation_buttons["simulator"].click()
        self.assertEqual(w.controls.pages.currentIndex(), 3)
        w.controls.set_simulator_visible(False)
        self.assertEqual(w.controls.pages.currentIndex(), 0)

    def test_panel_operation_and_sources_are_connected(self):
        w = self.widget()
        self.fill(w)
        w.stop()
        panel = w.controls.math_controls
        panel.operation_combo.setCurrentIndex(1)
        panel.source_b_combo.setCurrentIndex(0)
        np.testing.assert_array_equal(w.last_math, np.zeros(len(w.last_math)))
        self.assertEqual(panel.formula_label.text(), "MATH = CH1 − CH1")
        self.assertEqual(w.math_processor.math.config.operation, "subtract")

    def test_average_and_reconfiguration_in_stop_do_not_touch_channels(self):
        w = self.widget("average")
        self.fill(w)
        w.stop()
        primary = w.last_acquisition.copy()
        count = w.acquisition_processor.get_progress()
        w.set_math_configuration("subtract", 1, 2)
        np.testing.assert_allclose(w.last_math, primary[:, 0]-primary[:, 1], atol=1e-8)
        self.assertEqual(w.acquisition_processor.get_progress(), count)
        np.testing.assert_array_equal(w.last_acquisition, primary)

    def test_envelope_difference_of_identical_channels_is_zero(self):
        w = self.widget("envelope")
        w.set_math_configuration("subtract", 1, 2)
        data = signal()
        data[:, 1] = data[:, 0]
        w.on_samples_received(data)
        w.process_data()
        self.assertIsInstance(w.last_math, EnvelopeResult)
        np.testing.assert_array_equal(w.last_math.minimum, np.zeros(len(w.last_math.minimum)))
        np.testing.assert_array_equal(w.last_math.maximum, np.zeros(len(w.last_math.maximum)))
        self.assertTrue(w.plot.math_fill.isVisible())
        self.assertFalse(w.plot.math_curve.isVisible())
        np.testing.assert_array_equal(w.plot.math_lower.xData, w.plot.envelope_curves[1][0].xData)

    def test_stop_and_redraw_preserve_math_without_accumulating(self):
        for mode in ("average", "envelope"):
            with self.subTest(mode=mode):
                w = self.widget(mode)
                self.fill(w)
                w.stop()
                result = w.last_math.minimum.copy() if mode == "envelope" else w.last_math.copy()
                w.on_samples_received(signal(600, start=1500))
                w.process_data()
                with patch.object(w.math_processor, "process") as process:
                    w.set_horizontal_position(1)
                    w.set_time_per_division(w.time_per_division*2)
                    w._redraw_last_acquisition()
                    process.assert_not_called()
                actual = w.last_math.minimum if mode == "envelope" else w.last_math
                np.testing.assert_array_equal(actual, result)

    def test_sampling_recut_uses_corresponding_raw_window(self):
        w = self.widget()
        self.fill(w)
        w.stop()
        w.set_horizontal_position(1)
        w.set_time_per_division(w.time_per_division*2)
        np.testing.assert_allclose(w.last_math, w.last_acquisition.sum(axis=1), atol=1e-8)
        np.testing.assert_array_equal(w.plot.math_curve.xData, w.plot.curve.xData)

    def test_single_freezes_math_with_both_input_channels(self):
        for mode in ("sampling", "average", "envelope"):
            with self.subTest(mode=mode):
                w = self.widget(mode)
                self.enterContext(patch.object(type(w.acquisition), "is_running",
                                              new_callable=PropertyMock, return_value=True))
                w.single()
                w.on_samples_received(signal())
                w.process_data()
                self.assertFalse(w.running)
                target = 1 if mode == "sampling" else 4
                self.assertEqual(len(w.math_processor.history), target)
                result = w.last_math.minimum.copy() if mode == "envelope" else w.last_math.copy()
                w.on_samples_received(signal(600, start=1500))
                w.process_data()
                actual = w.last_math.minimum if mode == "envelope" else w.last_math
                np.testing.assert_array_equal(actual, result)

    def test_source_reset_clears_math_and_formula_without_history_waits(self):
        w = self.widget("envelope")
        self.fill(w)
        w.reset_acquisition(97656.25)
        self.assertIsNone(w.last_math)
        self.assertIsNone(w.plot._math_bounds)
        self.assertFalse(w.plot.math_fill.isVisible())
        w.set_math_configuration("subtract", 1, 2)
        self.assertIsNone(w.last_math)
        self.assertIn("esperando", w.controls.math_controls.status_label.text())

    def test_math_theme_and_validation(self):
        w = self.widget()
        self.fill(w)
        original = w.last_math.copy()
        w.plot.set_display_theme("light")
        np.testing.assert_array_equal(w.last_math, original)
        for kwargs in ({"scale": 0}, {"scale": np.nan}, {"position": np.inf}):
            with self.assertRaises(ValueError):
                w.plot.set_math_settings(**kwargs)
        with self.assertRaises(ValueError):
            w.plot.set_math_envelope([2], [1], w.sample_rate)

    def test_simulator_math_end_to_end(self):
        w = self.widget("average")
        w.change_acquisition_source(w.acquisition.SIMULATOR)
        loop = QEventLoop()
        timer = QTimer()
        timer.setInterval(10)
        timer.timeout.connect(lambda: loop.quit() if w.last_math is not None else None)
        timeout = QTimer()
        timeout.setSingleShot(True)
        timeout.timeout.connect(loop.quit)
        timer.start()
        timeout.start(4000)
        loop.exec()
        timer.stop()
        timeout.stop()
        self.assertIsNone(w._audio_error)
        self.assertIsNotNone(w.last_math)
        np.testing.assert_allclose(w.last_math, w.last_acquisition.sum(axis=1), atol=1e-7)
        self.assertTrue(w.plot.math_curve.isVisible())


if __name__ == "__main__":
    unittest.main()
