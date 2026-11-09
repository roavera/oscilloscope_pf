"""Pruebas de integración de UI horizontal integrada (requiere PySide6)."""
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
class HorizontalInlineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        self.panel = HorizontalControls()
        self.panel.show()
        self.app.processEvents()

    def tearDown(self):
        self.panel.close()

    def test_no_dialog_and_default_compact(self):
        self.assertFalse(hasattr(self.panel, 'navigation_dialog'))
        self.assertFalse(self.panel.inspection_area.isVisible())
        self.assertFalse(self.panel.fine_row.isVisible())
        self.assertEqual(self.panel.reference_combo.currentData(), 'Center')

    def test_inspection_inline_toggle(self):
        self.panel.navigation_button.click()
        self.app.processEvents()
        self.assertTrue(self.panel.inspection_area.isVisible())
        self.panel.navigation_button.click()
        self.assertFalse(self.panel.inspection_area.isVisible())

    def test_delay_zoom_and_reset(self):
        self.panel.navigation_button.click()
        delays = []
        zooms = []
        self.panel.delay_changed.connect(delays.append)
        self.panel.zoom_changed.connect(zooms.append)
        self.panel.delay_spin.setValue(3.25)
        self.panel.zoom_spin.setValue(4.0)
        self.assertAlmostEqual(delays[-1], 0.00325)
        self.assertAlmostEqual(zooms[-1], 4.0)
        self.panel.reset_inspection_button.click()
        self.assertEqual(self.panel.delay_spin.value(), 0.0)
        self.assertEqual(self.panel.zoom_spin.value(), 1.0)

    def test_reference_presets_and_custom(self):
        self.panel.reference_combo.setCurrentIndex(
            self.panel.reference_combo.findData('Right')
        )
        self.assertAlmostEqual(self.panel._position_divisions, 6.0)
        self.panel._on_position_changed(1.25)
        self.assertEqual(self.panel.reference_combo.currentData(), 'Custom')

    def test_vernier_show_and_scale(self):
        vals = []
        self.panel.time_per_division_changed.connect(vals.append)
        self.panel.vernier_checkbox.setChecked(True)
        self.assertTrue(self.panel.fine_row.isVisible())
        self.panel.fine_time_spin.setValue(875.25)
        self.assertAlmostEqual(vals[-1], 0.00087525)
        self.panel.time_combo.setCurrentIndex(self.panel.time_combo.findData(0.0005))
        self.assertFalse(self.panel.vernier_checkbox.isChecked())
        self.assertFalse(self.panel.fine_row.isVisible())

    def test_stop_state_restricts_inspection(self):
        self.panel.navigation_button.click()
        self.panel.set_navigation_enabled(False)
        self.assertFalse(self.panel.delay_spin.isEnabled())
        self.assertFalse(self.panel.zoom_spin.isEnabled())
        self.assertTrue(self.panel.reference_combo.isEnabled())
        self.assertTrue(self.panel.time_combo.isEnabled())
        self.panel.set_navigation_enabled(True)
        self.assertTrue(self.panel.delay_spin.isEnabled())
        self.assertTrue(self.panel.zoom_spin.isEnabled())


if __name__ == '__main__':
    unittest.main()
