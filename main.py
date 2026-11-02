"""Inicio en pantalla completa, con botón visible y atajos F11 / Esc."""
import sys

from PySide6.QtCore import QEvent, QObject, Qt
from PySide6.QtGui import QAction, QKeySequence, QShortcut
from PySide6.QtWidgets import QApplication, QStyle, QToolButton

from gui.main_window import MainWindow


class FullScreenControls(QObject):
    """Sincroniza el botón con el estado real de la ventana."""

    def __init__(self, window):
        super().__init__(window)
        self.window = window
        self.action = QAction(window)
        self.action.setShortcut(QKeySequence("F11"))
        self.action.triggered.connect(self.toggle)
        window.addAction(self.action)

        self.button = QToolButton(window)
        self.button.setDefaultAction(self.action)
        self.button.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        self.button.setAutoRaise(True)
        self.button.setMinimumHeight(28)
        window.menuBar().setCornerWidget(self.button, Qt.Corner.TopRightCorner)

        self.escape = QShortcut(QKeySequence("Escape"), window)
        self.escape.activated.connect(self.leave)
        window.installEventFilter(self)
        self.sync()

    def toggle(self):
        if self.window.isFullScreen():
            self.window.showMaximized()
        else:
            self.window.showFullScreen()
        self.sync()

    def leave(self):
        if self.window.isFullScreen():
            self.window.showMaximized()
        self.sync()

    def sync(self):
        fullscreen = self.window.isFullScreen()
        text = "Salir de pantalla completa" if fullscreen else "Pantalla completa"
        icon = (QStyle.StandardPixmap.SP_TitleBarNormalButton if fullscreen
                else QStyle.StandardPixmap.SP_TitleBarMaxButton)
        self.action.setText(text)
        self.action.setIcon(self.window.style().standardIcon(icon))
        self.action.setToolTip(text + " (F11) · Esc para salir")
        self.button.setAccessibleName(text)

    def eventFilter(self, watched, event):
        if watched is self.window and event.type() == QEvent.Type.WindowStateChange:
            self.sync()
        return super().eventFilter(watched, event)


def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.fullscreen_controls = FullScreenControls(window)
    window.showFullScreen()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
