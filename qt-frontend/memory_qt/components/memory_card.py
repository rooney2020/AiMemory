"""记忆卡片组件 — 用于列表中展示单条记忆"""

from PyQt5.QtWidgets import QFrame, QVBoxLayout, QHBoxLayout, QLabel, QCheckBox
from PyQt5.QtCore import pyqtSignal, Qt

from ..constants import C


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"

TYPE_COLORS = {
    "episodic": "teal",
    "semantic": "blue",
    "procedural": "mauve",
}

TYPE_LABELS = {
    "episodic": "会话摘要",
    "semantic": "笔记",
    "procedural": "偏好",
}


class MemoryCard(QFrame):
    clicked = pyqtSignal(str)
    selection_changed = pyqtSignal(str, bool)

    def __init__(self, memory, parent=None):
        super().__init__(parent)
        self.memory_id = memory.id
        self._selectable = False
        self.setCursor(Qt.PointingHandCursor)
        self.setProperty("card", True)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        top = QHBoxLayout()
        color = TYPE_COLORS.get(memory.type.value, "blue")

        self._checkbox = QCheckBox()
        self._checkbox.setVisible(False)
        self._checkbox.setStyleSheet(
            f"QCheckBox {{ spacing: 4px; }}"
            f"QCheckBox::indicator {{ width: 16px; height: 16px; border-radius: 4px; "
            f"border: 2px solid {C['surface2']}; background: {C['surface0']}; }}"
            f"QCheckBox::indicator:checked {{ background: {C['blue']}; border-color: {C['blue']}; }}"
        )
        self._checkbox.toggled.connect(
            lambda checked: self.selection_changed.emit(self.memory_id, checked)
        )
        top.addWidget(self._checkbox)

        type_text = TYPE_LABELS.get(memory.type.value, memory.type.value)
        type_badge = QLabel(type_text)
        type_badge.setFixedHeight(22)
        type_badge.setStyleSheet(
            f"background: {_rgba(C[color], 0.14)}; color: {C[color]}; border: 1px solid {_rgba(C[color], 0.22)}; "
            f"border-radius: 999px; font-size: 11px; font-weight: 800; padding: 2px 9px;"
        )
        top.addWidget(type_badge)

        strength_label = QLabel(f"强度:{memory.strength:.1f}")
        strength_label.setStyleSheet(
            f"color: {C['overlay0']}; font-size: 11px; border: none; background: transparent;"
        )
        top.addWidget(strength_label)

        top.addStretch()

        date_label = QLabel(memory.created_at.strftime("%Y-%m-%d"))
        date_label.setStyleSheet(
            f"color: {C['overlay0']}; font-size: 11px; border: none; background: transparent;"
        )
        top.addWidget(date_label)

        layout.addLayout(top)

        summary = memory.summary or memory.content[:80]
        summary_label = QLabel(summary)
        summary_label.setWordWrap(True)
        summary_label.setStyleSheet(
            f"color: {C['text']}; font-size: 13px; font-weight: 700; border: none; background: transparent;"
        )
        layout.addWidget(summary_label)

        if memory.project:
            proj_label = QLabel(f"@ {memory.project}")
            proj_label.setStyleSheet(
                f"color: {C['subtext0']}; font-size: 11px; border: none; background: transparent;"
            )
            layout.addWidget(proj_label)

        self._apply_style()

    def set_selectable(self, on: bool):
        self._selectable = on
        self._checkbox.setVisible(on)
        if not on:
            self._checkbox.setChecked(False)

    def is_checked(self) -> bool:
        return self._checkbox.isChecked()

    def set_checked(self, checked: bool):
        self._checkbox.setChecked(checked)

    def _apply_style(self):
        self.setStyleSheet(f"""
            QFrame {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {_rgba(C['base'], 0.98)}, stop:1 {_rgba(C['surface0'], 0.92)});
                border: 1px solid {_rgba(C['surface2'], 0.38)};
                border-radius: 18px;
            }}
            QFrame:hover {{ border-color: {_rgba(C['blue'], 0.62)}; }}
        """)

    def mousePressEvent(self, event):
        if self._selectable:
            self._checkbox.setChecked(not self._checkbox.isChecked())
        else:
            self.clicked.emit(self.memory_id)
        super().mousePressEvent(event)
