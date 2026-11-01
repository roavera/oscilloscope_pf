"""Pruebas sin hardware: python -m unittest discover -s tests -p test_average.py -v"""

import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

import unittest
from unittest.mock import patch, PropertyMock

import numpy as np
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QEventLoop, QTimer

from acquisition.acquisition_processor import AcquisitionProcessor
from acquisition.capture_sequence import CaptureSequence
from acquisition.stereo_buffer import StereoBuffer
from gui.oscilloscope_widget import OscilloscopeWidget
from trigger.edge_trigger import Edge_Trigger


def stereo_signal(count=1500, period=64, start=0):
    t = np.arange(start, start + count, dtype=np.float64)
    y = np.sin(2 * np.pi * (t - 0.37) / period).astype(np.float32)
    return np.column_stack((y, 2 * y + 0.25)).astype(np.float32)


class AverageAlgorithmTests(unittest.TestCase):
    def make_processor(self):
        p = AcquisitionProcessor()
        p.configure(mode="average", average_count=4)
        return p

    def test_exact_arithmetic_mean_and_rolling_window(self):
        p = self.make_processor()
        for index in range(7):
            result = p.process(np.full(8, index, dtype=np.float32))
            expected = np.mean(np.arange(max(0, index - 3), index + 1))
            np.testing.assert_allclose(result, expected)
        self.assertEqual(p.get_progress(), (4, 4))
        self.assertEqual(p.get_state()["acquisitions"], 7)

    def test_channels_input_output_and_diagnostic_are_independent(self):
        p = self.make_processor()
        data = np.arange(10, dtype=np.float32)
        original = data.copy()
        result = p.process(data, channel=1)
        p.process(-data, channel=2)
        data[:] = 999
        result[:] = 999
        diagnostic = p.get_state(1)
        diagnostic["captures"][0][:] = 999
        np.testing.assert_allclose(p.process(original, channel=1), original)
        np.testing.assert_allclose(p.process(-original, channel=2), -original)
        self.assertEqual(p.get_progress(1), (2, 4))
        self.assertEqual(p.get_progress(2), (2, 4))

    def test_reset_shape_and_configuration(self):
        p = self.make_processor()
        p.process(np.ones(8))
        p.set_average_count(16)
        self.assertEqual(p.get_progress(), (0, 16))
        p.process(np.ones(8))
        np.testing.assert_array_equal(p.process(np.full(4, 3)), np.full(4, 3))
        self.assertEqual(p.get_progress(), (1, 16))
        p.reset()
        self.assertEqual(p.get_progress(), (0, 16))
        with self.assertRaises(ValueError):
            p.set_average_count(True)
        with self.assertRaises(ValueError):
            p.set_average_count(3)

    def test_invalid_and_empty_samples_do_not_accumulate(self):
        p = self.make_processor()
        for data in ([1, np.nan], [np.inf], np.zeros((3, 2))):
            with self.assertRaises(ValueError):
                p.process(data)
        self.assertEqual(p.process([]).size, 0)
        self.assertEqual(p.get_progress(), (0, 4))

    def test_repeatable_signal_noise_reduction(self):
        p = self.make_processor()
        p.set_average_count(64)
        rng = np.random.default_rng(32)
        clean = np.sin(np.linspace(0, 2*np.pi, 2048))
        for _ in range(64):
            output = p.process(clean + rng.normal(0, 0.2, len(clean)))
        self.assertLess(np.std(output - clean), 0.035)


class CaptureSequenceTests(unittest.TestCase):
    def test_fractional_alignment_and_common_time_for_both_channels(self):
        data = stereo_signal()
        trigger = Edge_Trigger(position=0.5)
        frames = list(CaptureSequence().captures(data, 0, 24, trigger, 1))
        self.assertGreater(len(frames), 10)
        for frame in frames:
            self.assertAlmostEqual(float(frame.samples[12, 0]), 0.0, places=6)
            np.testing.assert_allclose(frame.samples[:, 1],
                                       2*frame.samples[:, 0]+0.25, atol=1e-6)

    def test_no_duplicate_after_snapshot_overlap_or_wrap(self):
        sequence = CaptureSequence()
        buf = StereoBuffer(200)
        trigger = Edge_Trigger()
        ids = []
        for start in range(0, 1200, 80):
            buf.add_samples(stereo_signal(80, start=start))
            data = buf.get_data()
            first = buf.total_samples - len(data)
            frames = list(sequence.captures(data, first, 24, trigger, 1))
            ids.extend(f.trigger_id for f in frames)
            self.assertEqual(list(sequence.captures(data, first, 24, trigger, 1)), [])
        self.assertGreater(len(ids), 10)
        self.assertEqual(ids, sorted(set(ids)))

    def test_incomplete_capture_waits_for_posttrigger_sample(self):
        data = stereo_signal(160)
        sequence = CaptureSequence()
        trigger = Edge_Trigger()
        self.assertEqual(list(sequence.captures(data[:70], 0, 24, trigger, 1)), [])
        frames = list(sequence.captures(data[:90], 0, 24, trigger, 1))
        self.assertEqual(len(frames), 1)
        self.assertEqual(frames[0].trigger_id, 64)

    def test_source_ch2_and_falling_edge(self):
        data = stereo_signal()
        data[:, 0] = np.arange(len(data))
        data[:, 1] = stereo_signal()[:, 0]
        trigger = Edge_Trigger(slope="Falling")
        frames = list(CaptureSequence().captures(data, 0, 24, trigger, 2))
        self.assertGreater(len(frames), 10)
        for frame in frames:
            self.assertAlmostEqual(float(frame.samples[12, 1]), 0.0, places=6)
            # La rampa de CH1 recibe exactamente la misma corrección fraccional.
            self.assertGreater(float(frame.samples[12, 0]), frame.trigger_id)
            self.assertLess(float(frame.samples[12, 0]), frame.trigger_id + 1)

    def test_no_trigger_or_nonfinite_data_never_creates_capture(self):
        sequence = CaptureSequence()
        trigger = Edge_Trigger()
        self.assertEqual(list(sequence.captures(np.ones((100, 2)), 0, 24, trigger, 1)), [])
        data = stereo_signal()
        data[:, 1] = np.nan
        self.assertEqual(list(sequence.captures(data, 0, 24, trigger, 1)), [])

    def test_extreme_trigger_positions_and_clear_keep_ids_monotonic(self):
        buf = StereoBuffer(200)
        buf.add_samples(stereo_signal(300))
        self.assertEqual(buf.total_samples, 300)
        buf.clear()
        self.assertEqual(buf.total_samples, 300)
        buf.add_samples(stereo_signal(100, start=300))
        self.assertEqual(buf.total_samples, 400)
        for position in (0, 1):
            frames = list(CaptureSequence().captures(stereo_signal(), 0, 24,
                         Edge_Trigger(position=position), 1))
            self.assertGreater(len(frames), 0)
            self.assertTrue(all(f.samples.shape == (24, 2) for f in frames))


class AverageWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def make_widget(self):
        with patch.object(OscilloscopeWidget, "start_acquisition"):
            w = OscilloscopeWidget()
        self.addCleanup(w.shutdown)
        w.set_time_per_division(24 / (w.sample_rate * 12))
        w.set_acquisition_mode("average")
        w.set_average_count(4)
        return w

    def test_gui_selector_and_progress(self):
        w = self.make_widget()
        controls = w.controls.acquisition_controls
        self.assertEqual(controls.mode_combo.currentData(), "average")
        self.assertTrue(controls.average_count_combo.isEnabled())
        controls.average_count_combo.setCurrentIndex(2)
        self.assertEqual(w.acquisition_processor.get_average_count(), 32)
        w.on_samples_received(stereo_signal())
        w.process_data()
        self.assertIn("/ 32 capturas", controls.average_progress_label.text())
        w.set_acquisition_mode("sampling")
        self.assertFalse(controls.average_count_combo.isEnabled())

    def test_average_requires_valid_trigger_even_in_auto(self):
        w = self.make_widget()
        w.on_samples_received(np.ones((600, 2), dtype=np.float32))
        w.process_data()
        self.assertIsNone(w.last_acquisition)
        self.assertEqual(w.acquisition_processor.get_progress(), (0, 4))
        self.assertIn("esperando disparo", w.controls.acquisition_controls.status_label.text())

    def test_repeated_trigger_with_new_tail_is_not_counted_twice(self):
        w = self.make_widget()
        # Un solo disparo completo seguido de una cola constante.
        data = np.full((250, 2), -1, dtype=np.float32)
        data[64:] = 1
        w.on_samples_received(data)
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (1, 4))
        w.on_samples_received(np.ones((250, 2), dtype=np.float32))
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (1, 4))

    def test_stop_and_horizontal_redraw_preserve_processed_result(self):
        w = self.make_widget()
        w.on_samples_received(stereo_signal())
        w.process_data()
        frozen = w.last_acquisition.copy()
        self.assertEqual(w.acquisition_processor.get_progress(), (4, 4))
        w.stop()
        w.on_samples_received(stereo_signal(600, start=1500))
        w.process_data()
        np.testing.assert_array_equal(w.last_acquisition, frozen)
        self.assertFalse(w.display_timer.isActive())
        with patch.object(w.acquisition_processor, "process") as process:
            w.set_horizontal_position(1)
            w.set_time_per_division(w.time_per_division * 2)
            w._redraw_last_acquisition()
            process.assert_not_called()
        np.testing.assert_array_equal(w.last_acquisition, frozen)
        np.testing.assert_allclose(w.plot._raw_channels, frozen)

    def test_single_waits_for_n_new_captures_and_freezes_both_channels(self):
        w = self.make_widget()
        self.enterContext(patch.object(type(w.acquisition), "is_running",
                                      new_callable=PropertyMock, return_value=True))
        w.single()
        w.on_samples_received(stereo_signal(100))
        w.process_data()
        self.assertTrue(w.running)
        self.assertEqual(w.acquisition_processor.get_progress(), (1, 4))
        w.on_samples_received(stereo_signal(1400, start=100))
        w.process_data()
        self.assertFalse(w.running)
        self.assertEqual(w.acquisition_processor.get_progress(1), (4, 4))
        self.assertEqual(w.acquisition_processor.get_progress(2), (4, 4))
        self.assertEqual(w.acquisition_processor.get_state()["acquisitions"], 4)
        frozen = w.last_acquisition.copy()
        w.on_samples_received(stereo_signal(600, start=1500))
        w.process_data()
        np.testing.assert_array_equal(w.last_acquisition, frozen)
        self.assertFalse(w.display_timer.isActive())

    def test_run_resets_average_and_does_not_reuse_stopped_history(self):
        w = self.make_widget()
        self.enterContext(patch.object(type(w.acquisition), "is_running",
                                      new_callable=PropertyMock, return_value=True))
        w.on_samples_received(stereo_signal())
        w.process_data()
        frozen = w.last_acquisition.copy()
        w.stop()
        w.on_samples_received(stereo_signal(600, start=1500))
        w.run()
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (0, 4))
        np.testing.assert_array_equal(w.last_acquisition, frozen)
        w.on_samples_received(stereo_signal(600, start=2100))
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (4, 4))

    def test_trigger_changes_reset_and_keep_stereo_relationship(self):
        w = self.make_widget()
        w.on_samples_received(stereo_signal())
        w.process_data()
        w.set_trigger_channel(2)
        self.assertEqual(w.acquisition_processor.get_progress(), (0, 4))
        w.on_samples_received(stereo_signal(1500, start=1500))
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (4, 4))
        np.testing.assert_allclose(w.last_acquisition[:, 1],
                                   2*w.last_acquisition[:, 0]+0.25, atol=1e-6)
        w.set_trigger_level(0.1)
        self.assertEqual(w.acquisition_processor.get_progress(), (0, 4))

    def test_discontinuity_resets_average_and_preserves_frozen_display(self):
        w = self.make_widget()
        w.on_samples_received(stereo_signal())
        w.process_data()
        frozen = w.last_acquisition.copy()
        w.stop()
        w._on_discontinuity(w._source_generation)
        w.process_data()
        np.testing.assert_array_equal(w.last_acquisition, frozen)
        w.running = True
        w.on_samples_received(stereo_signal(100))
        w.process_data()
        self.assertEqual(w.acquisition_processor.get_progress(), (1, 4))

    def test_sampling_single_still_needs_only_one_trigger(self):
        w = self.make_widget()
        w.set_acquisition_mode("sampling")
        self.enterContext(patch.object(type(w.acquisition), "is_running",
                                      new_callable=PropertyMock, return_value=True))
        w.single()
        w.on_samples_received(stereo_signal())
        w.process_data()
        self.assertFalse(w.running)
        self.assertTrue(w.trigger_found)
        self.assertEqual(w.last_acquisition.shape[1], 2)

    def test_mode_selection_through_actual_dialog_signals(self):
        w = self.make_widget()
        panel = w.controls.acquisition_controls
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("sampling"))
        self.assertEqual(w.acquisition_processor.get_mode(), "sampling")
        panel.mode_combo.setCurrentIndex(panel.mode_combo.findData("average"))
        self.assertEqual(w.acquisition_processor.get_mode(), "average")

    def test_source_rate_time_slope_and_count_reset_accumulation(self):
        actions = (
            lambda w: w.set_average_count(16),
            lambda w: w.set_trigger_slope("Falling"),
            lambda w: w.set_trigger_mode("Normal"),
            lambda w: w.set_time_per_division(w.time_per_division * 2),
            lambda w: w.set_horizontal_position(1),
            lambda w: w.reset_acquisition(97656.25),
        )
        for action in actions:
            with self.subTest(action=action):
                w = self.make_widget()
                w.on_samples_received(stereo_signal())
                w.process_data()
                self.assertEqual(w.acquisition_processor.get_progress()[0], 4)
                action(w)
                self.assertEqual(w.acquisition_processor.get_progress()[0], 0)

    def test_simulated_usb_average_and_single_end_to_end(self):
        w = self.make_widget()
        w.set_average_count(16)

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
        self.assertEqual(w.sample_rate, 97656.25)
        self.assertEqual(w.last_acquisition.shape[1], 2)
        w.single()
        wait_for(lambda: not w.running)
        self.assertTrue(w.trigger_found)
        self.assertEqual(w.acquisition_processor.get_progress(1), (16, 16))
        self.assertEqual(w.acquisition_processor.get_progress(2), (16, 16))
        self.assertEqual(w.acquisition_processor.get_state()["acquisitions"], 16)


if __name__ == "__main__":
    unittest.main()
