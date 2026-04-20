"""全局搜索栏组件"""

from PyQt5.QtWidgets import QLineEdit
from PyQt5.QtCore import pyqtSignal, Qt

from ..constants import C
from ..theme import lineedit_style


class GlobalSearchBar(QLineEdit):
    search_triggered = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setPlaceholderText("搜索记忆... (回车执行)")
        self.setMinimumWidth(300)
        self.setMaximumWidth(500)
        self.setStyleSheet(lineedit_style())
        self.returnPressed.connect(self._on_enter)

    def _on_enter(self):
        text = self.text().strip()
        if text:
            self.search_triggered.emit(text)
