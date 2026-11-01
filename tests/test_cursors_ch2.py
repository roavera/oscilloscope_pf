"""Cursores de ambos canales y etiquetas opcionales."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from unittest.mock import patch

import numpy as np
from PySide6.QtWidgets import QApplication
from gui.oscilloscope_widget import OscilloscopeWidget


class CursorChannelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def widget(self):
        with patch.object(OscilloscopeWidget, "start_acquisition"):
            w = OscilloscopeWidget()
        self.addCleanup(w.shutdown)
        data = np.column_stack((np.arange(13)*.001, .2+np.arange(13)*.01))
        w.plot.set_signal(data, 1000)
        w.plot.set_channel_settings(2, scale=.1, position=-1)
        w.cursor_controls.channel.setCurrentIndex(1)
        return w

    def test_track_uses_ch2_values_and_its_scale_and_position(self):
        w = self.widget()
        w.cursor_controls.mode.setCurrentText("Track")
        w.plot.cursor_lines[0].setValue(.003)
        w.plot.cursor_lines[1].setValue(.007)
        self.assertEqual(w.plot.cursor_channel, 2)
        x, y = w.plot.cursor_points[0].getData()
        np.testing.assert_allclose(x, [.003])
        np.testing.assert_allclose(y, [1.3])
        self.assertIn("CH2", w.cursor_controls.readout.text())
        self.assertIn("V=+0.23 V", w.cursor_controls.readout.text())
        self.assertIn("ΔV=+0.04 V", w.cursor_controls.readout.text())
        self.assertIn("CH2", w.plot.cursor_labels[0].toPlainText())
        self.assertIn("0.23", w.plot.cursor_labels[0].toPlainText())
        self.assertEqual(w.trigger_channel, 1)

    def test_manual_voltage_uses_selected_channel_conversion(self):
        w = self.widget()
        w.cursor_controls.mode.setCurrentText("Manual")
        w.cursor_controls.orientation.setCurrentText("Tensión")
        w.plot.cursor_lines[0].setValue(1)
        w.plot.cursor_lines[1].setValue(2)
        self.assertIn("CH2 · C1: +0.2 V", w.cursor_controls.readout.text())
        self.assertIn("C2: +0.3 V", w.cursor_controls.readout.text())
        self.assertIn("0.2 V", w.plot.cursor_labels[0].toPlainText())
        w.cursor_controls.channel.setCurrentIndex(0)
        self.assertIn("CH1 · C1: +0.02 V", w.cursor_controls.readout.text())

    def test_hide_labels_keeps_lines_points_and_panel_readout(self):
        w = self.widget()
        w.cursor_controls.mode.setCurrentText("Track")
        before = w.cursor_controls.readout.text()
        self.assertTrue(all(label.isVisible() for label in w.plot.cursor_labels))
        w.cursor_controls.show_values.setChecked(False)
        self.assertFalse(any(label.isVisible() for label in w.plot.cursor_labels))
        self.assertTrue(all(line.isVisible() for line in w.plot.cursor_lines))
        self.assertTrue(all(point.isVisible() for point in w.plot.cursor_points))
        self.assertEqual(w.cursor_controls.readout.text(), before)
        w.cursor_controls.show_values.setChecked(True)
        self.assertTrue(all(label.isVisible() for label in w.plot.cursor_labels))

    def test_off_hides_labels_and_lines_but_keeps_visibility_preference(self):
        w = self.widget()
        w.cursor_controls.mode.setCurrentText("Manual")
        w.cursor_controls.mode.setCurrentText("Off")
        self.assertFalse(any(label.isVisible() for label in w.plot.cursor_labels))
        self.assertFalse(any(line.isVisible() for line in w.plot.cursor_lines))
        w.cursor_controls.show_values.setChecked(False)
        w.cursor_controls.mode.setCurrentText("Manual")
        self.assertFalse(any(label.isVisible() for label in w.plot.cursor_labels))
        self.assertTrue(all(line.isVisible() for line in w.plot.cursor_lines))

    def test_time_voltage_switch_reinitializes_positions_in_correct_units(self):
        w = self.widget()
        w.cursor_controls.mode.setCurrentText("Manual")
        w.cursor_controls.orientation.setCurrentText("Tensión")
        self.assertAlmostEqual(w.plot.cursor_lines[0].value(), -1.6)
        w.cursor_controls.orientation.setCurrentText("Tiempo")
        self.assertAlmostEqual(w.plot.cursor_lines[0].value(), .0036)
        self.assertIn("t=", w.plot.cursor_labels[0].toPlainText())

    def test_clear_and_envelope_never_track_stale_ch2_values(self):
        w = self.widget()
        w.cursor_controls.mode.setCurrentText("Track")
        w.plot.clear_signal()
        self.assertIn("esperando muestras de CH2", w.cursor_controls.readout.text())
        self.assertEqual(len(w.plot.cursor_points[0].data), 0)
        w.plot.set_envelope(np.zeros((13, 2)), np.ones((13, 2)), 1000)
        self.assertIn("no disponible en Envolvente", w.cursor_controls.readout.text())
        self.assertEqual(len(w.plot.cursor_points[0].data), 0)
        w.cursor_controls.mode.setCurrentText("Manual")
        w.cursor_controls.orientation.setCurrentText("Tensión")
        self.assertIn("CH2", w.cursor_controls.readout.text())

    def test_cursor_movement_in_stop_does_not_acquire_or_process(self):
        w = self.widget()
        w.stop()
        w.cursor_controls.mode.setCurrentText("Track")
        original = w.plot._raw_channels.copy()
        with patch.object(w.acquisition_processor, "process") as process:
            w.plot.cursor_lines[0].setValue(.004)
            w.plot.cursor_lines[1].setValue(.008)
            process.assert_not_called()
        np.testing.assert_array_equal(w.plot._raw_channels, original)
        self.assertIn("V=+0.24 V", w.cursor_controls.readout.text())

    def test_outside_capture_has_no_fabricated_voltage(self):
        w = self.widget()
        w.plot.set_signal(np.ones((2, 2)), 1000)
        w.cursor_controls.mode.setCurrentText("Track")
        self.assertIn("fuera del tramo adquirido", w.cursor_controls.readout.text())
        self.assertIn("Fuera de captura", w.plot.cursor_labels[0].toPlainText())
        self.assertEqual(len(w.plot.cursor_points[0].data), 0)


if __name__ == "__main__":
    unittest.main()
