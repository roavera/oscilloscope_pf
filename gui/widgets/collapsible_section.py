
"""Sección plegable reutilizable para los controles del osciloscopio."""

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QPalette
from PySide6.QtWidgets import (
    QFrame,
    QToolButton,
    QVBoxLayout,
    QWidget,
    QSizePolicy,
)


class CollapsibleSection(QWidget):
    toggled = Signal(bool)

    def __init__(
        self,
        title: str,
        content: QWidget,
        expanded: bool = True,
        parent=None,
    ):
        super().__init__(parent)

        self.content = content

        self.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Maximum,
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # ============================================================
        # ENCABEZADO
        # ============================================================

        self.header = QToolButton(self)
        self.header.setObjectName("collapsibleHeader")
        self.header.setText(title)
        self.header.setCheckable(True)
        self.header.setChecked(bool(expanded))

        self.header.setToolButtonStyle(
            Qt.ToolButtonStyle.ToolButtonTextBesideIcon
        )

        self.header.setArrowType(
            Qt.ArrowType.DownArrow
            if expanded
            else Qt.ArrowType.RightArrow
        )

        self.header.setSizePolicy(
            QSizePolicy.Policy.Expanding,
            QSizePolicy.Policy.Fixed,
        )

        self.header.setCursor(
            Qt.CursorShape.PointingHandCursor
        )

        self.header.setMinimumHeight(42)

        layout.addWidget(self.header)

        # ============================================================
        # CONTENIDO PLEGABLE
        # ============================================================

        self.body = QFrame(self)

        body_layout = QVBoxLayout(self.body)
        body_layout.setContentsMargins(4, 8, 4, 8)
        body_layout.setSpacing(0)

        content.setParent(self.body)
        body_layout.addWidget(content)

        layout.addWidget(self.body)

        # ============================================================
        # CONEXIONES
        # ============================================================

        self.header.toggled.connect(self.set_expanded)

        self.update_theme()
        self.set_expanded(expanded)

    # ================================================================
    # TEMA VISUAL
    # ================================================================

    def update_theme(self):
        """Adapta los colores al tema activo de Qt."""

        palette = self.palette()

        background = palette.color(
            QPalette.ColorRole.Window
        )

        text = palette.color(
            QPalette.ColorRole.WindowText
        )

        # Detectar si el tema actual es oscuro.
        is_dark = background.lightness() < 128

        if is_dark:
            bg = "#222D3D"
            bg_hover = "#304159"
            bg_checked = "#29394F"
            border = "#3A4A60"
            foreground = "#E8EDF5"
        else:
            bg = "#E8EDF5"
            bg_hover = "#D8E2EF"
            bg_checked = "#D1DDEB"
            border = "#AAB8C8"
            foreground = "#202B3A"

        # Respetar el color de texto de la paleta cuando sea válido.
        if text.isValid():
            foreground = text.name()

        self.header.setStyleSheet(f"""
            QToolButton#collapsibleHeader {{
                background-color: {bg};
                color: {foreground};
                border: 1px solid {border};
                border-radius: 6px;
                padding: 10px 14px;
                text-align: left;
                font-size: 13px;
                font-weight: 600;
            }}

            QToolButton#collapsibleHeader:hover {{
                background-color: {bg_hover};
            }}

            QToolButton#collapsibleHeader:checked {{
                background-color: {bg_checked};
                color: {foreground};
            }}

            QToolButton#collapsibleHeader:pressed {{
                background-color: {bg_hover};
            }}
        """)

    def changeEvent(self, event):
        """Actualiza el encabezado cuando cambia la paleta."""

        if event.type() in (
            event.Type.PaletteChange,
            event.Type.ApplicationPaletteChange,
        ):
            self.update_theme()

        super().changeEvent(event)

    # ================================================================
    # EXPANDIR / CONTRAER
    # ============================================================

    def set_expanded(self, expanded: bool):
        expanded = bool(expanded)

        if self.header.isChecked() != expanded:
            self.header.setChecked(expanded)

        self.header.setArrowType(
            Qt.ArrowType.DownArrow
            if expanded
            else Qt.ArrowType.RightArrow
        )

        self.body.setVisible(expanded)

        self.toggled.emit(expanded)

    def is_expanded(self) -> bool:
        return self.header.isChecked()
