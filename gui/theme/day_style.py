"""Colores diurnos; no altera la configuración del display temporal."""
from PySide6.QtWidgets import QApplication
from PySide6.QtGui import QColor, QPalette


def is_day():
    app = QApplication.instance()
    return app is not None and app.property('scope_ui_theme') == 'light'


def day_color(night, day):
    return day if is_day() else night


def apply_day_palette(app, theme):
    if not hasattr(app, '_scope_v4_original_palette'):
        app._scope_v4_original_palette = QPalette(app.palette())
    app.setProperty('scope_ui_theme', theme)
    p = QPalette(app._scope_v4_original_palette)
    if theme == 'light':
        roles = {'Window':'#E8EFF5', 'WindowText':'#40576D', 'Base':'#FFFFFF',
                 'AlternateBase':'#E8EFF5', 'Text':'#183149', 'Button':'#EDF3F8',
                 'ButtonText':'#183149', 'Highlight':'#007F9C', 'HighlightedText':'#FFFFFF',
                 'Mid':'#AEBFD0', 'Light':'#F8FAFC', 'Dark':'#637A90',
                 'ToolTipBase':'#FFFFFF', 'ToolTipText':'#183149'}
        for role, color in roles.items():
            p.setColor(getattr(QPalette.ColorRole, role), QColor(color))
        for role in ('Text','WindowText','ButtonText'):
            p.setColor(QPalette.ColorGroup.Disabled, getattr(QPalette.ColorRole, role), QColor('#657C91'))
    app.setPalette(p)


def refresh_day_widgets(app):
    for widget in app.allWidgets():
        callback = getattr(widget, '_scope_v4_refresh', None)
        if callable(callback):
            callback()

