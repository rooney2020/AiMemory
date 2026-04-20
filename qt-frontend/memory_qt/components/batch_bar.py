"""批量操作工具栏 — 选择模式下的操作按钮"""

from PyQt5.QtWidgets import (
    QWidget, QHBoxLayout, QLabel, QPushButton,
    QInputDialog, QMessageBox,
)
from PyQt5.QtCore import pyqtSignal, Qt

from ..constants import C
from ..theme import secondary_btn_style, danger_btn_style


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


class BatchActionBar(QWidget):
    archive_requested = pyqtSignal(list)
    tag_requested = pyqtSignal(list, str)
    select_all_requested = pyqtSignal()
    deselect_all_requested = pyqtSignal()
    exit_requested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._selected_ids: set[str] = set()
        self.setFixedHeight(44)
        self._build_ui()
        self.setVisible(False)

    def _build_ui(self):
        self.setStyleSheet(
            f"background: {_rgba(C['base'], 0.96)}; border: 1px solid {_rgba(C['surface2'], 0.35)}; border-radius: 18px;"
        )
        layout = QHBoxLayout(self)
        layout.setContentsMargins(14, 8, 14, 8)
        layout.setSpacing(8)

        self._count_label = QLabel("已选择 0 条")
        self._count_label.setStyleSheet(
            f"color: {C['blue']}; font-size: 13px; font-weight: 800;"
        )
        layout.addWidget(self._count_label)

        layout.addSpacing(8)

        self._select_all_btn = QPushButton("全选")
        self._select_all_btn.setStyleSheet(secondary_btn_style())
        self._select_all_btn.setFixedHeight(34)
        self._select_all_btn.clicked.connect(self.select_all_requested)
        layout.addWidget(self._select_all_btn)

        self._deselect_btn = QPushButton("取消全选")
        self._deselect_btn.setStyleSheet(secondary_btn_style())
        self._deselect_btn.setFixedHeight(34)
        self._deselect_btn.clicked.connect(self.deselect_all_requested)
        layout.addWidget(self._deselect_btn)

        layout.addStretch()

        self._tag_btn = QPushButton("打标签")
        self._tag_btn.setStyleSheet(secondary_btn_style())
        self._tag_btn.setFixedHeight(34)
        self._tag_btn.clicked.connect(self._on_tag)
        layout.addWidget(self._tag_btn)

        self._archive_btn = QPushButton("归档")
        self._archive_btn.setStyleSheet(danger_btn_style())
        self._archive_btn.setFixedHeight(34)
        self._archive_btn.clicked.connect(self._on_archive)
        layout.addWidget(self._archive_btn)

        layout.addSpacing(8)

        self._exit_btn = QPushButton("退出")
        self._exit_btn.setStyleSheet(secondary_btn_style())
        self._exit_btn.setFixedHeight(34)
        self._exit_btn.clicked.connect(self.exit_requested)
        layout.addWidget(self._exit_btn)

    def update_selection(self, selected_ids: set[str]):
        self._selected_ids = selected_ids
        count = len(selected_ids)
        self._count_label.setText(f"已选择 {count} 条")
        enabled = count > 0
        self._archive_btn.setEnabled(enabled)
        self._tag_btn.setEnabled(enabled)

    def _on_archive(self):
        ids = list(self._selected_ids)
        if not ids:
            return
        reply = QMessageBox.question(
            self, "确认归档",
            f"确定要归档选中的 {len(ids)} 条记忆吗？\n（不会永久删除）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.archive_requested.emit(ids)

    def _on_tag(self):
        ids = list(self._selected_ids)
        if not ids:
            return
        tag, ok = QInputDialog.getText(
            self, "打标签", f"为选中的 {len(ids)} 条记忆添加标签：",
        )
        if ok and tag.strip():
            self.tag_requested.emit(ids, tag.strip())

    def refresh_style(self):
        self.setStyleSheet(
            f"background: {_rgba(C['base'], 0.96)}; border: 1px solid {_rgba(C['surface2'], 0.35)}; border-radius: 18px;"
        )
        self._count_label.setStyleSheet(
            f"color: {C['blue']}; font-size: 13px; font-weight: 800;"
        )
        self._select_all_btn.setStyleSheet(secondary_btn_style())
        self._deselect_btn.setStyleSheet(secondary_btn_style())
        self._tag_btn.setStyleSheet(secondary_btn_style())
        self._exit_btn.setStyleSheet(secondary_btn_style())
        self._archive_btn.setStyleSheet(danger_btn_style())
