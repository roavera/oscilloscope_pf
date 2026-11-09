"""Pruebas de integración Qt. Requiere PySide6 y pyqtgraph.

QT_QPA_PLATFORM=offscreen python -m unittest discover -s tests -p test_trigger_advanced_gui.py -v
"""
import os
import unittest

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')
try:
    from PySide6.QtWidgets import QApplication
    from gui.panels.trigger_controls import TriggerControls
    from gui.oscilloscope_widget import OscilloscopeWidget
    QT_AVAILABLE = True
except ImportError:
    QT_AVAILABLE = False


@unittest.skipUnless(QT_AVAILABLE,'Requiere PySide6 y pyqtgraph')
class AdvancedTriggerGuiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls._app = QApplication.instance() or QApplication([])

    def test_type_selector_and_groups(self):
        panel=TriggerControls()
        try:
            panel.set_available_channels(1)
            index=panel.type_combo.findData('logic')
            self.assertFalse(panel.type_combo.model().item(index).isEnabled())
            panel.set_available_channels(2)
            self.assertTrue(panel.type_combo.model().item(index).isEnabled())
            for kind, group in (('timeout',panel.timeout_group),
                                ('runt',panel.runt_group),('logic',panel.logic_group)):
                panel.set_trigger_type(kind)
                self.assertFalse(group.isHidden())
                self.assertFalse(panel.pulse_group.isVisible())
            panel.set_trigger_type('edge')
            self.assertTrue(panel.timeout_group.isHidden())
            self.assertTrue(panel.runt_group.isHidden())
            self.assertTrue(panel.logic_group.isHidden())
        finally:
            panel.close()

    def test_widget_selects_detectors_without_starting_usb(self):
        scope=OscilloscopeWidget()
        try:
            for kind in ('timeout','runt','pulse_width','edge'):
                scope.set_trigger_type(kind)
                self.assertEqual(scope.trigger_kind,kind)
                scope.set_trigger_level(0.25)
                self.assertEqual(scope.trigger.level,0.25)
            scope.acquisition.channels=2
            scope.controls.trigger_controls.set_available_channels(2)
            scope.set_trigger_type('logic')
            self.assertEqual(scope.trigger_kind,'logic')
            scope.acquisition.channels=1
            scope.set_trigger_type('edge')
            self.assertEqual(scope.trigger_kind,'edge')
        finally:
            scope.shutdown()
            scope.close()


if __name__=='__main__':
    unittest.main()
