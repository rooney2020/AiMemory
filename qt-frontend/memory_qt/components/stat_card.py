"""统计卡片组件"""

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QLabel
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGraphicsDropShadowEffect
from PyQt5.QtGui import QColor

from ..constants import C


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


class StatCard(QFrame):
    def __init__(self, title: str, value: str | int, color_key: str = "blue", parent=None):
        super().__init__(parent)
        self._color_key = color_key
        self.setProperty("card", True)
        self.setFixedHeight(108)
        self.setMinimumWidth(160)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 12, 16, 12)

        self.title_label = QLabel(title)
        layout.addWidget(self.title_label)

        self.value_label = QLabel(str(value))
        layout.addWidget(self.value_label)

        layout.addStretch()

        self._apply_style()

    def set_value(self, value: str | int):
        self.value_label.setText(str(value))

    def _apply_style(self):
        self.title_label.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 12px; border: none; background: transparent;"
        )
        self.value_label.setStyleSheet(
            f"color: {C[self._color_key]}; font-size: 28px; font-weight: bold; border: none; background: transparent;"
        )
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {_rgba(C['base'], 0.98)}, stop:1 {_rgba(C['surface0'], 0.92)});
                border: 1px solid {_rgba(C['surface2'], 0.4)};
                border-radius: 18px;
            }}
            QFrame:hover {{ border-color: {_rgba(C[self._color_key], 0.52)}; }}
        """)
        shadow = QGraphicsDropShadowEffect()
        shadow.setBlurRadius(20)
        shadow.setOffset(0, 4)
        shadow.setColor(QColor(0, 0, 0, 48))
        self.setGraphicsEffect(shadow)

    def refresh_style(self):
        self._apply_style()
