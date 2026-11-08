"""Pruebas de calibración: python -m unittest discover -s tests -p test_voltage_calibration.py -v"""
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
import tempfile
from pathlib import Path
import unittest
from unittest.mock import patch

import numpy as np
from acquisition.voltage_calibration import (VoltageCalibration, ChannelCalibration,
    simulator_volts_to_normalized, SOURCE_SIMULATOR, SOURCE_BLACKPILL, SOURCE_AUDIO)


class VoltageCalibrationTests(unittest.TestCase):
    def test_virtual_range_and_independent_stereo(self):
        with tempfile.TemporaryDirectory() as d:
            cal = VoltageCalibration(Path(d)/'calibration.json')
            raw = np.array([[-1.0, 0.5], [0.0, -0.25], [0.8, 0.0]], dtype=np.float32)
            original = raw.copy()
            converted = cal.apply(raw, SOURCE_SIMULATOR)
            np.testing.assert_allclose(converted, [[-3.0,1.5],[0,-0.75],[2.4,0]],atol=1e-6)
            np.testing.assert_array_equal(original, raw)
            self.assertFalse(np.shares_memory(raw, converted))
            self.assertTrue(cal.has_volts(SOURCE_SIMULATOR))

    def test_physical_coefficients_are_channel_independent_and_persist(self):
        with tempfile.TemporaryDirectory() as d:
            path = Path(d)/'calibration.json'
            cal = VoltageCalibration(path)
            self.assertFalse(cal.has_volts(SOURCE_BLACKPILL))
            cal.set_physical(1, 2.98, 0.025, verified=True)
            cal.set_physical(2, 3.04, -0.05, verified=True)
            raw = np.array([[0.5, -0.25]], dtype=np.float32)
            expected = np.array([[1.515, -0.81]], dtype=np.float32)
            np.testing.assert_allclose(cal.apply(raw, SOURCE_BLACKPILL), expected, atol=1e-6)
            cal2 = VoltageCalibration(path)
            np.testing.assert_allclose(cal2.apply(raw, SOURCE_BLACKPILL), expected, atol=1e-6)
            self.assertTrue(cal2.has_volts(SOURCE_BLACKPILL))

    def test_audio_does_not_claim_volts(self):
        with tempfile.TemporaryDirectory() as d:
            cal = VoltageCalibration(Path(d)/'calibration.json')
            arr = np.array([[0.1, -0.2]], dtype=np.float32)
            np.testing.assert_allclose(cal.apply(arr, SOURCE_AUDIO), arr)
            self.assertFalse(cal.has_volts(SOURCE_AUDIO))
            self.assertFalse(cal.has_volts(SOURCE_BLACKPILL))

    def test_simulator_controls_convert_to_normalized(self):
        controls = dict(enabled=True, waveform='sine', frequency=200,
                        amplitude=1.8, offset=0.3, noise=0.3)
        converted = simulator_volts_to_normalized(controls)
        self.assertEqual(converted['frequency'], 200)
        self.assertAlmostEqual(converted['amplitude'], .6)
        self.assertAlmostEqual(converted['offset'], .1)
        self.assertAlmostEqual(converted['noise'], .1)
        self.assertEqual(controls['amplitude'], 1.8)

    def test_invalid_settings_rejected(self):
        for gain in (0, np.nan, np.inf):
            with self.assertRaises(ValueError):
                ChannelCalibration(gain, 0)
        with self.assertRaises(ValueError):
            ChannelCalibration(3, float('nan'))
        with self.assertRaises(ValueError):
            simulator_volts_to_normalized({'noise': float('inf')})
        with tempfile.TemporaryDirectory() as d:
            cal = VoltageCalibration(Path(d)/'calibration.json')
            with self.assertRaises(ValueError):
                cal.apply(np.zeros((5,1)), SOURCE_SIMULATOR)

    def test_pcm24_round_trip_virtual_volts_without_clipping(self):
        try:
            from communication.protocol import encode_audio, decode_audio
        except ModuleNotFoundError:
            self.skipTest("El protocolo PCM24 se prueba dentro del repositorio original")
        raw = np.array([[.5, -.4], [-.25, .2]], dtype=np.float32)
        result = decode_audio(encode_audio(raw))
        with tempfile.TemporaryDirectory() as d:
            volts = VoltageCalibration(Path(d)/'calibration.json').apply(result, SOURCE_SIMULATOR)
        np.testing.assert_allclose(volts, 3*raw, atol=5e-7)


try:
    from PySide6.QtWidgets import QApplication
    from gui.oscilloscope_widget import OscilloscopeWidget
    HAS_QT = True
except ImportError:
    HAS_QT = False


@unittest.skipUnless(HAS_QT, 'Prueba Qt disponible al instalar PySide6')
class VoltageCalibrationWidgetTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def widget(self):
        with patch.object(OscilloscopeWidget, 'start_acquisition'):
            w = OscilloscopeWidget()
        self.addCleanup(w.shutdown)
        w.acquisition.source = SOURCE_SIMULATOR
        w.reset_acquisition(97656.25)
        w.set_time_per_division(.001)
        w.set_trigger_mode('Normal')
        return w

    def test_sampling_trigger_display_and_raw_archive(self):
        w = self.widget()
        t = np.arange(8000)
        raw = np.column_stack((.5*np.sin(2*np.pi*t/400),
                              -.2*np.sin(2*np.pi*t/400))).astype(np.float32)
        w.on_samples_received(raw)
        w.process_data()
        self.assertTrue(w.trigger_found)
        self.assertIsNotNone(w.last_acquisition)
        self.assertGreater(np.max(w.last_acquisition[:,0]),1.45)
        self.assertLess(np.min(w.last_acquisition[:,0]),-1.45)
        self.assertTrue('Simulación' in w.plot.calibration_label)
        archived = w.capture_archive.snapshot()[-1].samples
        exact = w._latest_raw_recut()
        np.testing.assert_array_equal(archived, exact)
        self.assertLess(np.max(abs(archived[:,0])), .51)
        # La fuente RAW es normalizada y NO vuelve a multiplicarse.
        w.stop()
        w._redraw_last_acquisition()
        np.testing.assert_array_equal(w.capture_archive.snapshot()[-1].samples, exact)

    def test_average_uses_volts_but_preserves_normalized_archive(self):
        w = self.widget()
        w.set_acquisition_mode('average')
        w.set_average_count(4)
        t = np.arange(8000)
        raw = np.column_stack((.4*np.sin(2*np.pi*t/200),
                              -.1*np.sin(2*np.pi*t/200))).astype(np.float32)
        w.on_samples_received(raw)
        w.process_data()
        self.assertGreaterEqual(w.acquisition_processor.get_progress()[0],1)
        self.assertGreater(np.max(w.last_acquisition[:,0]), 1.0)
        for capture in w.capture_archive.snapshot():
            self.assertLess(np.max(abs(capture.samples[:,0])),.41)


if __name__=='__main__':
    unittest.main()
