"""Frecuencia/período y su integración; ejecutar con unittest discover."""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
import numpy as np
from PySide6.QtWidgets import QApplication
from processing.measurements import (measure_timing, measure_amplitude,
                                     measure_transients, measure_interchannel)
from acquisition.voltage_calibration import VoltageCalibration
from gui.oscilloscope_widget import OscilloscopeWidget


def wave(fs, frequency, cycles=12, phase=.37):
    time = np.arange(int(np.ceil(cycles * fs / frequency))) / fs
    return np.sin(2 * np.pi * frequency * time + phase)


class TimingMathTests(unittest.TestCase):
    def assertFrequency(self, values, fs, expected, tolerance=.005):
        result = measure_timing(values, fs)
        self.assertIsNotNone(result.frequency, result.reason)
        self.assertLess(abs(result.frequency / expected - 1), tolerance)
        self.assertAlmostEqual(result.frequency * result.period, 1)
        self.assertGreaterEqual(result.periods_used, 2)
        return result

    def test_sines_at_audio_and_blackpill_rates(self):
        for fs in (48000., 97656.25):
            for frequency in (20., 200., 1000., 3000.):
                with self.subTest(fs=fs, f=frequency):
                    self.assertFrequency(wave(fs, frequency), fs, frequency, .001)

    def test_offset_amplitude_and_inversion(self):
        for gain, offset in ((1.5, .5), (-2., 3.), (.0001, .1)):
            self.assertFrequency(offset + gain * wave(97656.25, 734), 97656.25, 734, .001)

    def test_duty_cycle_and_pulse_width_for_square_waves(self):
        fs, f = 97656.25, 1000.
        time = np.arange(4096) / fs
        for duty in (.25, .5, .75):
            values = np.where((time * f) % 1 < duty, 1., -1.)
            result = self.assertFrequency(values, fs, f, .001)
            self.assertAlmostEqual(result.duty_cycle, duty * 100, delta=.5)
            self.assertAlmostEqual(result.high_time, duty / f, delta=1 / fs)
            self.assertAlmostEqual(result.low_time, (1 - duty) / f, delta=1 / fs)

    def test_sine_has_half_duty_cycle(self):
        result = self.assertFrequency(wave(97656.25, 1000), 97656.25, 1000, .001)
        self.assertAlmostEqual(result.duty_cycle, 50, delta=.1)
        self.assertAlmostEqual(result.high_time, result.period / 2, delta=2 / 97656.25)

    def test_square_and_triangle(self):
        fs, f = 97656.25, 1000
        sine = wave(fs, f)
        self.assertFrequency(np.sign(sine), fs, f)
        self.assertFrequency(2 / np.pi * np.arcsin(sine), fs, f, .001)

    def test_moderate_noise_and_crossing_chatter(self):
        fs, f = 97656.25, 1000
        sine = wave(fs, f, cycles=30)
        noise = np.random.default_rng(7).normal(0, .03, len(sine))
        result = self.assertFrequency(sine + noise, fs, f, .005)
        self.assertLess(result.periods_used, 31)
        self.assertGreater(result.periods_used, 26)

    def test_constant_short_invalid_and_invalid_rate(self):
        for values in ([], [np.nan], [np.inf], np.zeros(256), np.ones(256)):
            self.assertIsNone(measure_timing(values, 48000).frequency)
        for fs in (0, -1, np.nan, np.inf):
            self.assertIsNone(measure_timing(wave(48000, 1000), fs).frequency)
        with self.assertRaises(ValueError):
            measure_timing([[1, 2]], 48000)
        result = measure_timing(wave(48000, 1000, cycles=1.5), 48000)
        self.assertIsNone(result.frequency)
        self.assertIn('ciclos', result.reason)

    def test_white_noise_does_not_get_a_frequency(self):
        for seed in range(20):
            values = np.random.default_rng(seed).normal(size=2048)
            self.assertIsNone(measure_timing(values, 48000).frequency)

    def test_irregular_periods_and_single_pulse(self):
        signal = np.concatenate((wave(48000, 1000, cycles=5), wave(48000, 500, cycles=5)))
        self.assertIsNone(measure_timing(signal, 48000).frequency)
        pulse = np.zeros(1024)
        pulse[300:500] = 1
        self.assertIsNone(measure_timing(pulse, 48000).frequency)

    def test_too_few_samples_per_period(self):
        result = measure_timing(wave(48000, 10000), 48000)
        self.assertIsNone(result.frequency)
        self.assertIn('8 muestras', result.reason)

    def test_input_is_not_modified(self):
        data = wave(48000, 1000)
        before = data.copy()
        self.assertFrequency(data, 48000, 1000)
        np.testing.assert_array_equal(data, before)

    def test_robust_top_base_amplitude_rejects_spikes(self):
        values = np.repeat((-1.5, 1.5), 1000).astype(float)
        values[[10, 20]] = 20.0
        values[[30, 40]] = -20.0
        result = measure_amplitude(values)
        self.assertAlmostEqual(result.top, 1.5, delta=.02)
        self.assertAlmostEqual(result.base, -1.5, delta=.02)
        self.assertAlmostEqual(result.amplitude, 3.0, delta=.04)

    def test_overshoot_and_preshoot_percentages(self):
        fs, period = 10_000.0, 100
        values = np.where((np.arange(5000) % period) < period // 2, 1.0, -1.0)
        for start in range(0, len(values), period):
            if start >= 2:
                values[start - 2] = -.8   # preshoot: 10 % de Vamp
                values[start] = values[start + 1] = 1.5  # ROVShoot: 25 %
            if start + period // 2 + 1 < len(values):
                values[start + period // 2] = values[start + period // 2 + 1] = -1.4
        result = measure_transients(values, fs)
        self.assertAlmostEqual(result.rovshoot, 25, delta=1)
        self.assertAlmostEqual(result.fovshoot, 20, delta=1)
        self.assertAlmostEqual(result.rpreshoot, 10, delta=1)
        self.assertAlmostEqual(result.fpreshoot, 0, delta=1)

    def test_area_integral_uses_sample_period(self):
        values = np.ones(1000)
        result = measure_amplitude(values, 1000.0)
        self.assertAlmostEqual(result.area, .999, places=6)

    def test_interchannel_phase_and_first_last_edges(self):
        fs, period = 10_000.0, 100
        ch1 = np.where((np.arange(5000) % period) < period // 2, 1.0, -1.0)
        shift = 10
        ch2 = np.roll(ch1, shift)
        result = measure_interchannel(ch1, ch2, fs)
        self.assertAlmostEqual(result.lrr, shift / fs, delta=1 / fs)
        self.assertAlmostEqual(result.fff, 1 / fs, delta=1 / fs)
        self.assertAlmostEqual(result.phase, 36.0, delta=4.0)


class TimingIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.w = OscilloscopeWidget()
        self.temp = TemporaryDirectory()
        self.w.voltage_calibration = VoltageCalibration(Path(self.temp.name) / 'cal.json')
        self.w.acquisition.source = 'simulator'
        self.w.acquisition.channels = 2
        self.w.acquisition._active_channels = (True, True)
        self.w._connection_state = 'connected'
        self.w.running = True
        self.w.sample_rate = 97656.25
        n = 4096
        t = np.arange(n) / self.w.sample_rate
        self.data = np.column_stack((np.sin(2*np.pi*1000*t + .3), .5 + np.sin(2*np.pi*500*t + .7)))
        self.panel = self.w.controls.measurement_controls

    def tearDown(self):
        self.w.shutdown()
        self.w.close()
        self.w.deleteLater()
        self.app.processEvents()
        self.temp.cleanup()

    def test_channels_units_and_labels(self):
        self.w._show_acquisition(self.data)
        self.assertAlmostEqual(self.w._measurement_timing[0].frequency, 1000, delta=.1)
        self.assertAlmostEqual(self.w._measurement_timing[1].frequency, 500, delta=.1)
        self.assertIn('Hz', self.panel.value_labels['frequency'].text())
        self.assertIn('%', self.panel.value_labels['duty_cycle'].text())
        self.panel.channel.setCurrentIndex(1)
        self.assertIn('ms', self.panel.value_labels['period'].text())
        self.assertIn('períodos', self.panel.timing_status.text())
        self.assertEqual(self.panel._format(.00099999987, 's'), '1 ms')
        self.panel.checkboxes['frequency'].setChecked(False)
        self.panel.checkboxes['period'].setChecked(False)
        self.assertTrue(self.panel.timing_status.isHidden())

    def test_high_resolution_uses_effective_sample_rate(self):
        self.w.set_acquisition_mode('high_resolution')
        self.w.set_high_resolution_factor(4)
        self.w._show_acquisition(self.data)
        self.assertAlmostEqual(self.w._measurement_timing[0].frequency, 1000, delta=1)
        self.assertAlmostEqual(self.w._measurement_timing[1].frequency, 500, delta=1)

    def test_peak_detect_uses_original_samples_and_rate(self):
        self.w.set_acquisition_mode('peak_detect')
        self.w._show_acquisition(self.data)
        self.assertAlmostEqual(self.w._measurement_timing[0].frequency, 1000, delta=.1)

    def test_average_processed_signal_and_stop(self):
        self.w.set_acquisition_mode('average')
        self.w._show_acquisition(self.data)
        self.assertAlmostEqual(self.w._measurement_timing[0].frequency, 1000, delta=.1)
        self.w._show_acquisition(-self.data)
        self.assertIsNone(self.w._measurement_timing[0].frequency)
        self.assertEqual(self.panel.value_labels['frequency'].text(), '—')
        self.assertIn('constante', self.panel.timing_status.text())
        self.assertEqual(self.w._measurement_results[0].rms, 0)
        before = list(self.w._measurement_timing)
        self.w.stop()
        self.w.plot.set_interpolation_mode('linear')
        self.assertEqual(self.w._measurement_timing, before)

    def test_invalid_timing_keeps_amplitude(self):
        self.w._show_acquisition(np.ones((512,2)))
        self.assertEqual(self.panel.value_labels['frequency'].text(), '—')
        self.assertEqual(self.panel.value_labels['rms'].text(), '1 V')
        self.assertIn('constante', self.panel.timing_status.text())

    def test_clears_on_mode_source_channel_changes(self):
        self.w._show_acquisition(self.data)
        self.w.acquisition._active_channels = (False, True)
        self.w.update_controls_state()
        self.assertIsNone(self.w._measurement_timing[0])
        self.w.acquisition._active_channels = (True,True)
        self.w._show_acquisition(self.data)
        self.w.set_acquisition_mode('envelope')
        self.assertEqual(self.w._measurement_timing, [None, None])
        self.w.set_acquisition_mode('sampling')
        self.w._show_acquisition(self.data)
        self.w.reset_acquisition(48000)
        self.assertEqual(self.w._measurement_timing, [None, None])


if __name__ == '__main__':
    unittest.main()
