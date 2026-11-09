"""Tests Qt. Requiere PySide6 instalado en el entorno de usuario."""
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtWidgets import QApplication
    from gui.panels.horizontal_controls import HorizontalControls
except ImportError:
    QApplication = None
    HorizontalControls = None


@unittest.skipIf(QApplication is None, 'PySide6 no instalado')
class HorizontalPanelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = HorizontalControls()

    def tearDown(self):
        self.panel.close()
        # La inspección ahora está dentro del panel Horizontal.

    def test_reference_preset(self):
        values = []
        self.panel.position_changed.connect(values.append)
        self.panel.reference_combo.setCurrentIndex(self.panel.reference_combo.findData('Left'))
        self.assertEqual(values[-1], -6.0)
        self.assertAlmostEqual(self.panel._position_divisions, -6.0)

    def test_custom_when_moving_position(self):
        self.panel.position_knob.set_value(1.25)
        self.panel._on_position_changed(1.25)
        self.assertEqual(self.panel.reference_combo.currentData(), 'Custom')

    def test_delay_in_seconds(self):
        values = []
        self.panel.delay_changed.connect(values.append)
        self.panel.delay_spin.setValue(2.0)
        self.assertAlmostEqual(values[-1], 0.002)

    def test_zoom_in_stop(self):
        values = []
        self.panel.zoom_changed.connect(values.append)
        self.panel.zoom_spin.setValue(4)
        self.assertAlmostEqual(values[-1], 4.0)
        self.panel.set_navigation_enabled(False)
        self.assertFalse(self.panel.zoom_spin.isEnabled())

    def test_vernier_fine_scale(self):
        values = []
        self.panel.time_per_division_changed.connect(values.append)
        self.panel.vernier_checkbox.setChecked(True)
        self.panel.fine_time_spin.setValue(875.25)
        self.assertAlmostEqual(values[-1], 0.00087525)
        self.assertAlmostEqual(self.panel._time_per_division, 0.00087525)
        self.assertFalse(self.panel._fine_item_index is None)

    def test_standard_scale_clears_vernier(self):
        self.panel.vernier_checkbox.setChecked(True)
        self.panel.time_combo.setCurrentIndex(self.panel.time_combo.findData(0.0005))
        self.assertFalse(self.panel.vernier_checkbox.isChecked())


if __name__ == '__main__':
    unittest.main()
