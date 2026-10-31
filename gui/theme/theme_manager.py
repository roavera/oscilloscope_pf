
"""Administración de temas visuales de OSCILOSCOPIO."""

from pathlib import Path

from PySide6.QtCore import QObject, QSettings, Signal
from PySide6.QtWidgets import QApplication

from .colors import THEMES


class ThemeManager(QObject):
    theme_changed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)

        self.settings = QSettings(
            "OsciloscopioPF",
            "Osciloscopio"
        )

        self.themes_path = Path(__file__).resolve().parent

        saved_theme = self.settings.value(
            "appearance/theme", "dark", type=str
        )

        self.current_theme = (
            saved_theme if saved_theme in THEMES else "dark"
        )

    def apply_theme(self, theme_name):
        if theme_name not in THEMES:
            raise ValueError(
                f"Tema no reconocido: {theme_name}"
            )

        app = QApplication.instance()
        if app is None:
            raise RuntimeError(
                "QApplication debe existir antes de aplicar el tema"
            )

        stylesheet_path = (
            self.themes_path / f"{theme_name}.qss"
        )

        stylesheet = stylesheet_path.read_text(
            encoding="utf-8"
        )

        app.setStyleSheet(stylesheet)

        self.current_theme = theme_name
        self.settings.setValue(
            "appearance/theme", theme_name
        )

        self.theme_changed.emit(theme_name)

    def toggle_theme(self):
        new_theme = (
            "light"
            if self.current_theme == "dark"
            else "dark"
        )
        self.apply_theme(new_theme)

    def get_colors(self):
        return THEMES[self.current_theme]
