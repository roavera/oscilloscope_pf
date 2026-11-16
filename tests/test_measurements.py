"""Pruebas reproducibles sin hardware: python -m unittest discover -s tests -v."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np
from PySide6.QtWidgets import QApplication
from acquisition.voltage_calibration import VoltageCalibration
from gui.oscilloscope_widget import OscilloscopeWidget
from processing.measurements import measure_amplitude


class MeasurementMathTests(unittest.TestCase):
    def test_sine_with_dc(self):
        signal = .5 + 2 * np.sin(2 * np.pi * np.arange(1000) / 100)
        original = signal.copy()
        result = measure_amplitude(signal)
        self.assertAlmostEqual(result.maximum, 2.5)
        self.assertAlmostEqual(result.minimum, -1.5)
        self.assertAlmostEqual(result.peak_to_peak, 4)
        self.assertAlmostEqual(result.mean, .5)
        self.assertAlmostEqual(result.rms, 1.5)
        np.testing.assert_array_equal(signal, original)

    def test_square_and_constant(self):
        result = measure_amplitude(np.tile([-2., 2.], 100))
        self.assertEqual(result.rms, 2)
        self.assertEqual(result.peak_to_peak, 4)
        self.assertEqual(result.mean, 0)
        for value in (-3., 0., 1.):
            result = measure_amplitude(np.full(32, value))
            self.assertEqual(result.mean, value)
            self.assertEqual(result.rms, abs(value))
            self.assertEqual(result.peak_to_peak, 0)

    def test_invalid_and_empty(self):
        for values in ([], [1, np.nan], [np.inf]):
            self.assertIsNone(measure_amplitude(values))
        with self.assertRaises(ValueError):
            measure_amplitude([[1, 2]])

    def test_float32_large_amplitudes(self):
        result = measure_amplitude(np.array([-1e20, 1e20], dtype=np.float32))
        self.assertTrue(np.isfinite(result.rms))
        self.assertAlmostEqual(result.rms / 1e20, 1., places=6)


class MeasurementIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.scope = OscilloscopeWidget()
        self.temp = TemporaryDirectory()
        self.scope.voltage_calibration = VoltageCalibration(Path(self.temp.name) / 'calibration.json')
        self.scope.acquisition.source = 'simulator'
        self.scope.acquisition.channels = 2
        # Entradas sintéticas controladas; no se abre USB ni audio.
        self.scope.acquisition._active_channels = (True, True)
        self.scope._connection_state = 'connected'
        self.scope.running = True
        self.panel = self.scope.controls.measurement_controls
        self.data = np.column_stack((np.tile([-1., 1.], 32), np.full(64, .5)))

    def tearDown(self):
        self.scope.shutdown()
        self.scope.close()
        self.scope.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def show_capture(self, data=None):
        self.scope._show_acquisition(self.data if data is None else data)

    def test_two_channels_and_selection(self):
        self.show_capture()
        self.assertEqual(self.panel.value_labels['peak_to_peak'].text(), '2 V')
        self.panel.channel.setCurrentIndex(1)
        self.assertEqual(self.panel.value_labels['rms'].text(), '500 mV')
        self.assertEqual(self.panel.value_labels['peak_to_peak'].text(), '0 V')
        self.panel.checkboxes['rms'].setChecked(False)
        self.assertTrue(self.panel.value_labels['rms'].isHidden())

    def test_calibration_applied_once_before_measurement(self):
        calibrated = self.scope.voltage_calibration.apply(self.data / 3, 'simulator')
        self.show_capture(calibrated)
        self.assertAlmostEqual(self.scope._measurement_results[0].peak_to_peak, 2)

    def test_stop_scale_interpolation_zoom_do_not_change_capture_readings(self):
        self.show_capture()
        before = list(self.scope._measurement_results)
        self.scope.stop()
        self.scope.set_volts_per_division(.5)
        self.scope.set_vertical_position(2)
        self.scope.plot.set_interpolation_mode('linear')
        self.scope.set_horizontal_zoom(4)
        self.scope.set_horizontal_delay(.001)
        self.assertEqual(before, self.scope._measurement_results)
        self.assertIn('STOP', self.panel.status.text())

    def test_average_measures_processed_signal(self):
        self.scope.set_acquisition_mode('average')
        self.show_capture(self.data)
        self.show_capture(-self.data)
        self.assertEqual(self.scope._measurement_results[0].rms, 0)
        self.assertIn('2/16', self.panel.status.text())
        self.scope.reset_accumulation()
        self.assertIn('2/16', self.panel.status.text())

    def test_high_resolution_measures_processed_signal(self):
        self.scope.set_acquisition_mode('high_resolution')
        self.show_capture()
        self.assertEqual(self.scope._measurement_results[0].rms, 0)
        self.assertEqual(self.scope._measurement_results[0].sample_count, 16)
        self.assertEqual(self.scope._measurement_results[1].rms, .5)

    def test_peak_detect_measures_original_samples_not_extrema_bins(self):
        self.scope.set_acquisition_mode('peak_detect')
        values = np.zeros((64, 2))
        values[0, 0] = 2
        self.show_capture(values)
        result = self.scope._measurement_results[0]
        self.assertEqual(result.mean, 2 / 64)
        self.assertEqual(result.rms, .25)
        self.assertEqual(result.sample_count, 64)

    def test_unsupported_modes_clear_previous_readings(self):
        for mode in ('envelope', 'roll', 'fastact'):
            self.scope.set_acquisition_mode('sampling')
            self.show_capture()
            self.scope.set_acquisition_mode(mode)
            self.assertEqual(self.panel.value_labels['rms'].text(), '—')
            self.assertIn('no disponibles', self.panel.status.text())

    def test_channel_disable_and_reenable_waits_for_new_capture(self):
        self.show_capture()
        self.panel.channel.setCurrentIndex(1)
        self.scope.acquisition._active_channels = (True, False)
        self.scope.update_controls_state()
        self.assertEqual(self.panel.value_labels['rms'].text(), '—')
        self.scope.acquisition._active_channels = (True, True)
        self.scope.update_controls_state()
        self.assertEqual(self.panel.value_labels['rms'].text(), '—')
        self.show_capture()
        self.assertEqual(self.panel.value_labels['rms'].text(), '500 mV')

    def test_source_reset_and_audio_units(self):
        self.show_capture()
        self.scope.acquisition.source = 'audio'
        self.scope.reset_acquisition(48000)
        self.assertEqual(self.panel.value_labels['rms'].text(), '—')
        self.scope.acquisition._active_channels = (True, False)
        self.show_capture()
        self.assertEqual(self.panel.value_labels['rms'].text(), '1 u.a.')
        self.assertIsNone(self.scope._measurement_results[1])

    def test_physical_calibration_is_per_channel(self):
        self.scope.acquisition.source = 'blackpill_usb'
        self.scope.voltage_calibration.set_physical(1, 3, 0, verified=True, save=False)
        self.show_capture()
        self.assertEqual(self.scope._measurement_units, ['V', 'u.a.'])
        self.panel.channel.setCurrentIndex(1)
        self.assertIn('sin calibración verificada', self.panel.status.text())

    def test_waiting_for_trigger_and_cleared_capture(self):
        self.show_capture()
        before = list(self.scope._measurement_results)
        self.scope.trigger_mode = 'Normal'
        self.scope.trigger_found = False
        self.scope.update_controls_state()
        self.assertEqual(before, self.scope._measurement_results)
        self.assertIn('esperando disparo', self.panel.status.text())
        self.scope._clear_trigger_history()
        self.assertEqual(self.panel.value_labels['rms'].text(), '—')


if __name__ == '__main__':
    unittest.main()
