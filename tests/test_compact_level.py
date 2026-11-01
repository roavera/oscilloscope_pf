"""Formato compacto del trigger sin perder precisión al editar o enfocar."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import unittest

from PySide6.QtCore import Qt, QLocale
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QPushButton, QVBoxLayout, QWidget
from gui.panels.trigger_controls import TriggerControls


class CompactLevelTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def controls(self):
        window = QWidget()
        layout = QVBoxLayout(window)
        panel = TriggerControls()
        other = QPushButton("Otro control")
        layout.addWidget(panel)
        layout.addWidget(other)
        self.addCleanup(window.close)
        window.show()
        self.app.processEvents()
        other.setFocus()
        self.app.processEvents()
        return window, panel, other

    def test_compact_zero_and_preserved_nine_decimals(self):
        window, panel, other = self.controls()
        self.assertEqual(panel.level_input.text(), "0 V")
        for value in (.123456789, -.000123456, 1e-9):
            with self.subTest(value=value):
                panel.set_level(value)
                panel.level_input.setFocus()
                self.app.processEvents()
                other.setFocus()
                self.app.processEvents()
                self.assertAlmostEqual(panel.level_input.value(), value, places=12)
                self.assertAlmostEqual(panel._level, value, places=12)

    def test_keyboard_edit_updates_model_and_keeps_precision(self):
        window, panel, other = self.controls()
        panel.level_input.setLocale(QLocale("en_US"))
        values = []
        panel.level_changed.connect(values.append)
        panel.level_input.setFocus()
        panel.level_input.lineEdit().selectAll()
        QTest.keyClicks(panel.level_input, "0.123456789")
        QTest.keyClick(panel.level_input, Qt.Key.Key_Return)
        other.setFocus()
        self.app.processEvents()
        self.assertAlmostEqual(panel._level, .123456789, places=12)
        self.assertAlmostEqual(values[-1], .123456789, places=12)
        self.assertLess(len(panel.level_input.text()), len("0.123456789 V"))

    def test_spanish_decimal_and_scientific_input(self):
        window, panel, other = self.controls()
        panel.level_input.setLocale(QLocale("es_AR"))
        for text, expected in (("0,012345678", .012345678), ("1e-6", 1e-6)):
            panel.level_input.setFocus()
            panel.level_input.lineEdit().selectAll()
            QTest.keyClicks(panel.level_input, text)
            QTest.keyClick(panel.level_input, Qt.Key.Key_Return)
            other.setFocus()
            self.app.processEvents()
            self.assertAlmostEqual(panel._level, expected, places=12)

    def test_step_uses_full_internal_value_after_compact_display(self):
        window, panel, other = self.controls()
        panel.set_level(.123456789)
        step = panel.level_input.singleStep()
        panel.level_input.stepUp()
        self.assertAlmostEqual(panel.level_input.value(), .123456789+step, places=9)


if __name__ == "__main__":
    unittest.main()
