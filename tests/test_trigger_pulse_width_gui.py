"""Pruebas Qt opcionales: usa QT_QPA_PLATFORM=offscreen para entornos sin pantalla."""
import os
import unittest

try:
    os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
    from PySide6.QtWidgets import QApplication
    from gui.panels.trigger_controls import TriggerControls
except ImportError:
    QApplication = None


@unittest.skipUnless(QApplication is not None, 'Requiere PySide6 en el entorno')
class TriggerPulseWidthGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def test_default_edge_and_type_signal(self):
        control = TriggerControls()
        captured = []
        control.type_changed.connect(captured.append)
        self.assertEqual(control.type_combo.currentData(), 'edge')
        control.type_combo.setCurrentIndex(control.type_combo.findData('pulse_width'))
        self.assertEqual(captured, ['pulse_width'])
        self.assertTrue(control.pulse_group.isVisibleTo(control.settings_dialog))
        self.assertFalse(control.slope_combo.isEnabled())
        control.deleteLater()

    def test_settings_change_and_reset(self):
        control = TriggerControls()
        changes = []
        control.pulse_width_changed.connect(changes.append)
        control.pulse_lower.setValue(450)
        control.pulse_comparison.setCurrentIndex(control.pulse_comparison.findData('within'))
        self.assertTrue(changes)
        self.assertEqual(changes[-1]['lower_us'], 450)
        control.reset_pulse_width_settings()
        self.assertEqual(control.pulse_width_settings()['lower_us'], 400)
        control.deleteLater()


if __name__ == '__main__':
    unittest.main()
