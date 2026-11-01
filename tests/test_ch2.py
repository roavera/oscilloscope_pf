"""Ejecutar: python -m unittest discover -s tests -p test_ch2.py -v"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from unittest.mock import patch
import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QTimer, QEventLoop
from acquisition.stereo_buffer import StereoBuffer
from acquisition.audio_input import AudioInput
from acquisition.acquisition_manager import AcquisitionManager
from gui.oscilloscope_widget import OscilloscopeWidget


class StereoTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_widget(self):
        with patch.object(OscilloscopeWidget, 'start_acquisition'):
            widget = OscilloscopeWidget()
        self.addCleanup(widget.shutdown)
        return widget

    def test_buffer_wrap_preserves_pairs(self):
        buf = StereoBuffer(7)
        expected = np.column_stack((np.arange(30), -np.arange(30))).astype(np.float32)
        for start in range(0, 30, 3):
            buf.add_samples(expected[start:start+3])
        np.testing.assert_array_equal(buf.get_data(), expected[-7:])
        np.testing.assert_array_equal(buf.get_data(3), expected[-3:])
        self.assertEqual(buf.get_data(0).shape, (0, 2))
        buf.add_samples(expected)
        np.testing.assert_array_equal(buf.get_data(), expected[-7:])
        buf.clear()
        self.assertEqual(buf.get_data().shape, (0, 2))

    def test_audio_callback_keeps_both_channels(self):
        source = AudioInput(channels=2)
        received = []
        source.callback_function = received.append
        data = np.array([[1, -1], [2, -2]], dtype=np.float32)
        source._audio_callback(data, 2, None, None)
        np.testing.assert_array_equal(received[0], data)
        self.assertFalse(np.shares_memory(received[0], data))

    def test_trigger_ch2_and_common_capture(self):
        w = self.make_widget()
        w.set_trigger_channel(2)
        w.set_time_per_division(.0001)
        w.set_trigger_mode('Normal')
        x = np.arange(2048, dtype=np.float32)
        y = np.sin(2*np.pi*x/100).astype(np.float32)
        data = np.column_stack((x, y))
        w.on_samples_received(data)
        w.process_data()
        self.assertTrue(w.trigger_found)
        start = w._last_trigger_index - int(w.display_samples*w.trigger.position)
        np.testing.assert_array_equal(w.last_acquisition, data[start:start+w.display_samples])
        np.testing.assert_array_equal(w.plot.curve.xData, w.plot.curve_ch2.xData)

    def test_one_processing_call_per_channel_and_no_redraw_accumulation(self):
        w = self.make_widget()
        data = np.column_stack((np.arange(64), -np.arange(64))).astype(np.float32)
        with patch.object(w.acquisition_processor, 'process', wraps=w.acquisition_processor.process) as process:
            w._show_acquisition(data)
            self.assertEqual(process.call_count, 2)
            self.assertEqual([c.kwargs['channel'] for c in process.call_args_list], [1, 2])
            w._last_display_buffer = data
            w._last_trigger_index = None
            w.display_samples = 32
            w._redraw_last_acquisition()
            self.assertEqual(process.call_count, 2)

    def test_vertical_scales_visibility_trigger_conversion_and_stop(self):
        w = self.make_widget()
        w._show_acquisition(np.array([[.02, .04], [.04, .08]], dtype=np.float32))
        ch1 = w.plot.curve.yData.copy()
        w.set_ch2_volts_per_division(.04)
        w.set_ch2_position(1)
        np.testing.assert_allclose(w.plot.curve_ch2.yData, [2, 3])
        np.testing.assert_array_equal(w.plot.curve.yData, ch1)
        w.set_trigger_channel(2)
        w.set_trigger_level(.08)
        self.assertAlmostEqual(w.plot.trigger_line.value(), 3)
        w.plot.trigger_line.setValue(2)
        w.plot._on_trigger_dragged(w.plot.trigger_line)
        self.assertAlmostEqual(w.trigger_level, .04)
        w.controls.ch2_controls.visible_checkbox.setChecked(False)
        self.assertFalse(w.plot.curve_ch2.isVisible())
        w.stop()
        previous = w.last_acquisition.copy()
        w.on_samples_received(np.zeros((2048, 2), dtype=np.float32))
        w.process_data()
        np.testing.assert_array_equal(w.last_acquisition, previous)

    def test_discontinuity_clears_both_channels(self):
        w = self.make_widget()
        w.on_samples_received(np.ones((600, 2), dtype=np.float32))
        w._on_discontinuity(w._source_generation)
        w.process_data()
        self.assertEqual(w.buffer.get_data().shape, (0, 2))
        self.assertIsNone(w.last_acquisition)
        self.assertIsNone(w.plot.curve.xData)
        self.assertIsNone(w.plot.curve_ch2.xData)

    def test_simulator_usb_stereo_and_single(self):
        w = self.make_widget()
        w.change_acquisition_source(AcquisitionManager.SIMULATOR)
        loop = QEventLoop()
        QTimer.singleShot(1200, loop.quit)
        loop.exec()
        self.assertEqual(w.acquisition.state, 'connected')
        self.assertIsNone(w._audio_error)
        self.assertIsNotNone(w.last_acquisition)
        self.assertEqual(w.last_acquisition.shape[1], 2)
        self.assertFalse(np.array_equal(w.last_acquisition[:, 0], w.last_acquisition[:, 1]))
        w.set_trigger_channel(2)
        w.single()
        loop = QEventLoop()
        QTimer.singleShot(600, loop.quit)
        loop.exec()
        self.assertTrue(w.trigger_found)
        self.assertFalse(w.running)
        frozen = w.last_acquisition.copy()
        loop = QEventLoop()
        QTimer.singleShot(120, loop.quit)
        loop.exec()
        np.testing.assert_array_equal(w.last_acquisition, frozen)


if __name__ == '__main__':
    unittest.main()
