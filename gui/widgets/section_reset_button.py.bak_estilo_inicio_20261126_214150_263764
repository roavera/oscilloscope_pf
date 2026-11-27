"""Reset de 24 px integrado en la cabecera interior de cada sección."""
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QHBoxLayout, QLabel, QToolButton


class SectionResetButton(QToolButton):
    def __init__(self, section, description):
        super().__init__(section)
        self.setText("↺")
        self.setFixedSize(24, 24)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setToolTip(description)
        self.setAccessibleName(description)
        self.setStyleSheet("""
            QToolButton {
                color:#aeb9c8;background:rgba(105,120,140,25);
                border:1px solid rgba(135,150,170,85);border-radius:5px;
                padding:0;font-size:19px;font-weight:normal;
            }
            QToolButton:hover {background:rgba(128,144,168,65);color:palette(text);}
            QToolButton:pressed {background:rgba(128,144,168,100);}
            QToolButton:focus {border:1px solid #8098b8;}
        """)
        self.header_label = QLabel(section.title(), section)
        self.header_label.setStyleSheet("font-weight:600;")
        section.setTitle("")
        section.setProperty("compactResetHeader", True)
        section.setStyleSheet(section.styleSheet() + """
            QGroupBox[compactResetHeader="true"] {margin-top:0px;padding-top:4px;}
        """)
        header = QHBoxLayout()
        header.setContentsMargins(0, 0, 0, 0)
        header.setSpacing(4)
        header.addWidget(self.header_label)
        header.addStretch(1)
        header.addWidget(self)
        section.layout().insertLayout(0, header)
