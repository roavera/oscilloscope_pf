"""Resets por sección sin hardware."""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch, PropertyMock

import numpy as np
from PySide6.QtWidgets import QApplication

from acquisition.modes.envelope import EnvelopeResult
from gui.oscilloscope_widget import OscilloscopeWidget


def signal(count=1500, start=0):
    t = np.arange(start, start+count, dtype=float)
    ch1 = (.012*np.sin(2*np.pi*(t-.37)/64)).astype(np.float32)
    return np.column_stack((ch1, .5*ch1+.002)).astype(np.float32)


class SectionResetTests(unittest.TestCase):
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

    def test_vertical_buttons_restore_only_corresponding_channel(self):
        for channel in (1, 2):
            with self.subTest(channel=channel):
                w = self.widget()
                self.fill(w)
                original = w.last_acquisition.copy()
                math = w.last_math.copy()
                w.set_volts_per_division(.1)
                w.set_ch2_volts_per_division(.2)
                w.set_vertical_position(1)
                w.set_ch2_position(-1)
                panel = w.controls.ch1_controls if channel == 1 else w.controls.ch2_controls
                panel.visible_checkbox.setChecked(False)
                w.controls.reset_buttons[f"ch{channel}"].click()
                self.assertEqual(w.plot.channel_scales[channel], .02)
                self.assertEqual(w.plot.channel_positions[channel], 0)
                self.assertTrue(w.plot.channel_visible[channel])
                self.assertEqual(w.plot.channel_scales[3-channel], .2 if channel == 1 else .1)
                np.testing.assert_array_equal(w.last_acquisition, original)
                np.testing.assert_array_equal(w.last_math, math)

    def test_trigger_reset_restores_defaults_and_keeps_stop(self):
        w = self.widget("average")
        w.set_trigger_channel(2)
        w.set_trigger_level(.003)
        w.set_trigger_slope("Falling")
        w.set_trigger_mode("Normal")
        self.fill(w)
        w.stop()
        before = w.last_acquisition.copy()
        w.controls.reset_buttons["trigger"].click()
        self.assertEqual((w.trigger_channel, w.trigger_level, w.trigger_slope, w.trigger_mode),
                         (1, 0, "Rising", "Auto"))
        self.assertEqual(w.controls.trigger_controls.source_combo.currentData(), 1)
        self.assertEqual(w.controls.trigger_controls.slope_combo.currentData(), "Rising")
        self.assertEqual(w.controls.trigger_controls.mode_combo.currentData(), "Auto")
        self.assertFalse(w.running)
        self.assertFalse(w.display_timer.isActive())
        np.testing.assert_array_equal(w.last_acquisition, before)

    def test_horizontal_reset_keeps_envelope_values_and_stop(self):
        w = self.widget("envelope")
        self.fill(w)
        w.stop()
        minimum = w.last_envelope.minimum.copy()
        math = w.last_math.minimum.copy()
        w.set_horizontal_position(2)
        w.controls.reset_buttons["horizontal"].click()
        self.assertEqual(w.time_per_division, .001)
        self.assertEqual(w.horizontal_position_divisions, 0)
        self.assertEqual(w.trigger.position, .5)
        self.assertFalse(w.running)
        np.testing.assert_array_equal(w.last_envelope.minimum, minimum)
        np.testing.assert_array_equal(w.last_math.minimum, math)
        np.testing.assert_array_equal(w.plot.math_lower.xData, w.plot.envelope_curves[1][0].xData)

    def test_math_reset_preserves_primary_data_and_progress(self):
        for mode in ("sampling", "average", "envelope"):
            with self.subTest(mode=mode):
                w = self.widget(mode)
                self.fill(w)
                w.stop()
                before = (w.last_envelope.minimum.copy() if mode == "envelope"
                          else w.last_acquisition.copy())
                count = w.acquisition_processor.get_progress()
                w.set_math_configuration("subtract", 2, 1)
                panel = w.controls.math_controls
                panel.scale_combo.setCurrentIndex(panel.scale_combo.findData(.1))
                panel.position_input.setValue(1)
                w.controls.reset_buttons["math"].click()
                config = w.math_processor.math.config
                self.assertEqual((config.operation, config.source_a, config.source_b), ("add", 1, 2))
                self.assertEqual(w.plot.math_scale, .02)
                self.assertEqual(w.plot.math_position, 0)
                self.assertFalse(w.plot.math_visible)
                self.assertFalse(panel.visible_checkbox.isChecked())
                self.assertEqual(panel.formula_label.text(), "MATH = CH1 + CH2")
                self.assertEqual(w.acquisition_processor.get_progress(), count)
                actual = w.last_envelope.minimum if mode == "envelope" else w.last_acquisition
                np.testing.assert_array_equal(actual, before)
                self.assertFalse(w.running)
                panel.visible_checkbox.setChecked(True)
                if mode == "envelope":
                    self.assertIsInstance(w.last_math, EnvelopeResult)
                    self.assertTrue(w.plot.math_fill.isVisible())
                else:
                    np.testing.assert_allclose(w.last_math, before.sum(axis=1), atol=1e-8)
                    self.assertTrue(w.plot.math_curve.isVisible())

    def test_accumulation_reset_keeps_mode_count_state_connection_and_capture(self):
        for mode in ("average", "envelope"):
            for running in (True, False):
                with self.subTest(mode=mode, running=running):
                    w = self.widget(mode)
                    self.fill(w)
                    if running:
                        w.display_timer.start()
                    else:
                        w.stop()
                    config = w.acquisition_processor.get_config()
                    before = (w.last_envelope.minimum.copy() if mode == "envelope"
                              else w.last_acquisition.copy())
                    before_math = (w.last_math.minimum.copy() if mode == "envelope"
                                   else w.last_math.copy())
                    source = w.acquisition.source
                    generation = w._source_generation
                    with patch.object(w.acquisition, "stop") as stop, \
                         patch.object(w.acquisition, "start") as start:
                        w.controls.reset_buttons["acquisition"].click()
                        stop.assert_not_called()
                        start.assert_not_called()
                    self.assertEqual(w.acquisition_processor.get_config(), config)
                    self.assertEqual(w.acquisition_processor.get_progress(), (0, 4))
                    self.assertEqual(len(w.math_processor.history), 0)
                    self.assertEqual(w.running, running)
                    self.assertEqual(w.display_timer.isActive(), running)
                    self.assertEqual(w.acquisition.source, source)
                    self.assertEqual(w._source_generation, generation)
                    actual = w.last_envelope.minimum if mode == "envelope" else w.last_acquisition
                    actual_math = w.last_math.minimum if mode == "envelope" else w.last_math
                    np.testing.assert_array_equal(actual, before)
                    np.testing.assert_array_equal(actual_math, before_math)
                    # Un timeout sin muestras nuevas no vuelve a acumular historial.
                    w.process_data()
                    self.assertEqual(w.acquisition_processor.get_progress(), (0, 4))

    def test_single_reset_requires_n_new_captures_after_click(self):
        w = self.widget("average")
        self.enterContext(patch.object(type(w.acquisition), "is_running",
                                      new_callable=PropertyMock, return_value=True))
        w.single()
        w.on_samples_received(signal(100))
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (1, 4))
        w.controls.reset_buttons["acquisition"].click()
        self.assertTrue(w.running)
        self.assertEqual(w.trigger_mode, "Single")
        self.assertEqual(w.acquisition_processor.get_progress(), (0, 4))
        w.on_samples_received(signal(80, start=100))
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (1, 4))
        self.assertTrue(w.running)
        w.on_samples_received(signal(1000, start=180))
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (4, 4))
        self.assertFalse(w.running)
        self.assertEqual(len(w.math_processor.history), 4)

    def test_buttons_remain_inside_group_titles_after_resize(self):
        w = self.widget()
        w.resize(1340, 680)
        w.show()
        self.app.processEvents()
        for button in w.controls.reset_buttons.values():
            section = button.parentWidget()
            self.assertGreaterEqual(button.x(), 0)
            self.assertLessEqual(button.x()+button.width(), section.width())
            self.assertGreaterEqual(button.y(), 0)
            self.assertLess(button.y()+button.height(), section.height())
            self.assertEqual((button.width(), button.height()), (24, 24))
            self.assertTrue(button.toolTip())
            self.assertTrue(button.accessibleName())

    def test_reset_buttons_safe_before_first_capture(self):
        w = self.widget()
        w.stop()
        for button in w.controls.reset_buttons.values():
            button.click()
        self.assertFalse(w.running)
        self.assertIsNone(w.last_acquisition)
        self.assertIsNone(w.last_math)


if __name__ == "__main__":
    unittest.main()
