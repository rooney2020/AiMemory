"""导出 UI 组件 — 按钮、菜单、文件对话框"""

from pathlib import Path
from typing import Optional

from PyQt5.QtWidgets import QWidget, QFileDialog, QToolButton, QMenu, QAction
from PyQt5.QtCore import Qt

from ...constants import C
from ...theme import secondary_btn_style
from .formatters import FORMATS, _EXT_MAP


def load_session_messages(sessions: list, scanner, parent: QWidget = None) -> list:
    """为所有会话加载完整消息，带进度条"""
    from PyQt5.QtWidgets import QProgressDialog, QApplication

    if not sessions or not scanner:
        return sessions

    progress = QProgressDialog("加载会话消息...", "取消", 0, len(sessions), parent)
    progress.setWindowTitle("加载中")
    progress.setMinimumDuration(500)

    loaded = []
    for i, session in enumerate(sessions):
        if progress.wasCanceled():
            loaded.extend(sessions[i:])
            break
        progress.setValue(i)
        title_short = (session.display_title or "")[:40]
        progress.setLabelText(f"({i+1}/{len(sessions)}) {title_short}")
        QApplication.processEvents()

        if not session.messages:
            try:
                session = scanner.load_messages(session)
            except Exception:
                pass
        loaded.append(session)

    progress.close()
    return loaded


def save_with_dialog(content: str, default_name: str, fmt: str, parent: QWidget = None) -> Optional[str]:
    ext = _EXT_MAP.get(fmt, ".txt")
    path, _ = QFileDialog.getSaveFileName(
        parent, "导出", f"{default_name}{ext}", f"{fmt} (*{ext})"
    )
    if not path:
        return None
    Path(path).write_text(content, encoding="utf-8")
    return path


def make_export_button(parent=None) -> QToolButton:
    btn = QToolButton(parent)
    btn.setText("导出 ▾")
    btn.setPopupMode(QToolButton.InstantPopup)
    btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
    btn.setStyleSheet(
        f"QToolButton {{ background: {C['surface0']}; color: {C['text']}; "
        f"border: none; border-radius: 8px; padding: 8px 16px; font-size: 13px; }}"
        f"QToolButton:hover {{ background: {C['surface1']}; }}"
        f"QToolButton::menu-indicator {{ image: none; }}"
    )
    btn.setFixedHeight(30)
    return btn


def build_format_menu(btn: QToolButton, callback) -> QMenu:
    menu = QMenu(btn)
    menu.setStyleSheet(
        f"QMenu {{ background: {C['surface0']}; color: {C['text']}; border: 1px solid {C['surface1']}; border-radius: 6px; padding: 4px; }}"
        f"QMenu::item {{ padding: 6px 20px; border-radius: 4px; }}"
        f"QMenu::item:selected {{ background: {C['surface1']}; }}"
    )
    for fmt in FORMATS:
        action = QAction(f"导出为 {fmt} ({_EXT_MAP[fmt]})", menu)
        action.triggered.connect(lambda checked=False, f=fmt: callback(f))
        menu.addAction(action)
    btn.setMenu(menu)
    return menu
