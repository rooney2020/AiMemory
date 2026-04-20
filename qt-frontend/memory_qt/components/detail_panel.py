"""通用记忆详情面板 — 美化 Markdown 渲染 + 编辑/删除操作"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QTextBrowser, QFrame, QToolButton, QMenu,
)
from PyQt5.QtCore import pyqtSignal, Qt, QUrl
from PyQt5.QtGui import QColor, QDesktopServices

from ..constants import C
from ..theme import secondary_btn_style, danger_btn_style
from .detail_formatters import (
    _TYPE_LABELS_CN,
    detail_css as _detail_css,
    format_memory_html,
    highlight_html as _highlight_html,
)


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


class DetailPanel(QWidget):
    edit_requested = pyqtSignal(str)
    delete_requested = pyqtSignal(str)

    def __init__(self, show_actions: bool = False, embed_buttons: bool = True, parent=None):
        super().__init__(parent)
        self._current_id: str | None = None
        self._current_mem = None
        self._show_actions = show_actions
        self._embed_buttons = embed_buttons
        self._highlight_term: str = ""
        self._current_match: int = 0
        self._total_matches: int = 0
        self._build_ui()

    def _create_buttons(self):
        """Create action buttons (always called, regardless of embed mode)."""
        self._match_label = QLabel("")
        self._match_label.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 12px; font-weight: 700; "
            f"background: {_rgba(C['surface0'], 0.72)}; border: 1px solid {_rgba(C['surface2'], 0.35)}; "
            f"border-radius: 999px; padding: 6px 10px;"
        )
        self._match_label.setVisible(False)

        _BTN_H = 34

        self._prev_btn = QPushButton("◀ 上一个")
        self._prev_btn.setStyleSheet(secondary_btn_style())
        self._prev_btn.setFixedHeight(_BTN_H)
        self._prev_btn.clicked.connect(self._go_prev)
        self._prev_btn.setVisible(False)

        self._next_btn = QPushButton("下一个 >")
        self._next_btn.setStyleSheet(secondary_btn_style())
        self._next_btn.setFixedHeight(_BTN_H)
        self._next_btn.clicked.connect(self._go_next)
        self._next_btn.setVisible(False)

        from .exporter import make_export_button, build_format_menu
        self.export_btn = make_export_button(self)
        self.export_btn.setFixedHeight(_BTN_H)
        self.export_btn.setEnabled(False)
        build_format_menu(self.export_btn, self._on_export)

        if self._show_actions:
            self.edit_btn = QPushButton("编辑")
            self.edit_btn.setStyleSheet(secondary_btn_style())
            self.edit_btn.setFixedHeight(_BTN_H)
            self.edit_btn.setEnabled(False)
            self.edit_btn.clicked.connect(lambda: self._current_id and self.edit_requested.emit(self._current_id))

            self.delete_btn = QPushButton("删除")
            self.delete_btn.setStyleSheet(danger_btn_style())
            self.delete_btn.setFixedHeight(_BTN_H)
            self.delete_btn.setEnabled(False)
            self.delete_btn.clicked.connect(lambda: self._current_id and self.delete_requested.emit(self._current_id))

    def get_action_widgets(self) -> list[QWidget]:
        """Return action button widgets for external placement.
        Order: [match_label, prev, next, export, edit?, delete?]"""
        widgets = [self._match_label, self._prev_btn, self._next_btn, self.export_btn]
        if self._show_actions:
            widgets.extend([self.edit_btn, self.delete_btn])
        return widgets

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self._create_buttons()

        if self._embed_buttons:
            top_bar = QWidget()
            top_layout = QHBoxLayout(top_bar)
            top_layout.setContentsMargins(8, 4, 8, 8)
            top_layout.setSpacing(6)
            for w in self.get_action_widgets():
                top_layout.addWidget(w)
                if w is self._next_btn:
                    top_layout.addStretch()
            layout.addWidget(top_bar)

        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(False)
        self.browser.anchorClicked.connect(self._on_link_clicked)
        self._apply_browser_style()
        layout.addWidget(self.browser, 1)

    def show_memory(self, mem, highlight_term: str = ""):
        self._current_id = mem.id
        self._current_mem = mem
        self._highlight_term = highlight_term
        self._current_match = 0
        
        try:
            html, match_count = format_memory_html(mem, highlight_term=highlight_term)
        except ImportError:
            html = self._fallback_html(mem)
            match_count = 0
        
        self.browser.setHtml(html)
        self._total_matches = match_count
        
        if highlight_term and match_count > 0:
            self._match_label.setVisible(True)
            self._prev_btn.setVisible(True)
            self._next_btn.setVisible(True)
            self._current_match = 1
            self._update_nav_label()
            self.browser.scrollToAnchor("match-1")
        else:
            self._match_label.setVisible(False)
            self._prev_btn.setVisible(False)
            self._next_btn.setVisible(False)

        self.export_btn.setEnabled(True)
        if self._show_actions:
            self.edit_btn.setEnabled(True)
            self.delete_btn.setEnabled(True)

    def _update_nav_label(self):
        self._match_label.setText(f"{self._current_match}/{self._total_matches} 个匹配")

    def _go_prev(self):
        if self._total_matches == 0:
            return
        self._current_match -= 1
        if self._current_match < 1:
            self._current_match = self._total_matches
        self._update_nav_label()
        self.browser.scrollToAnchor(f"match-{self._current_match}")

    def _go_next(self):
        if self._total_matches == 0:
            return
        self._current_match += 1
        if self._current_match > self._total_matches:
            self._current_match = 1
        self._update_nav_label()
        self.browser.scrollToAnchor(f"match-{self._current_match}")

    def _fallback_html(self, mem) -> str:
        entities = ", ".join(mem.entities) if mem.entities else "无"
        raw_type = mem.type.value if hasattr(mem.type, 'value') else str(mem.type)
        type_val = _TYPE_LABELS_CN.get(raw_type, raw_type)
        content_escaped = mem.content.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace("\n", "<br>")
        return (
            f'<html><head><style>{_detail_css()}</style></head><body>'
            f'<h1>{mem.summary or "(无摘要)"}</h1>'
            f'<div class="meta-block">'
            f'<strong>类型:</strong> {type_val} &nbsp; '
            f'<strong>强度:</strong> {mem.strength:.1f} &nbsp; '
            f'<strong>创建:</strong> {mem.created_at.strftime("%Y-%m-%d %H:%M")}<br>'
            f'<strong>实体:</strong> {entities}'
            f'</div>'
            f'{content_escaped}'
            f'</body></html>'
        )

    def _apply_browser_style(self):
        self.browser.setStyleSheet(f"""
            QTextBrowser {{
                background: {_rgba(C['base'], 0.98)};
                border: 1px solid {_rgba(C['surface2'], 0.42)};
                border-radius: 20px;
                padding: 8px;
                color: {C['text']};
            }}
        """)

    def refresh_style(self):
        self._apply_browser_style()
        self._match_label.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 12px; font-weight: 700; "
            f"background: {_rgba(C['surface0'], 0.72)}; border: 1px solid {_rgba(C['surface2'], 0.35)}; "
            f"border-radius: 999px; padding: 6px 10px;"
        )
        self._prev_btn.setStyleSheet(secondary_btn_style())
        self._next_btn.setStyleSheet(secondary_btn_style())
        if self._show_actions:
            self.edit_btn.setStyleSheet(secondary_btn_style())
            self.delete_btn.setStyleSheet(danger_btn_style())
        if self._current_id is None:
            self.show_placeholder()

    def _on_link_clicked(self, url: QUrl):
        import subprocess, os
        url_str = url.toString()
        if url_str.startswith(("http://", "https://")):
            QDesktopServices.openUrl(url)
        elif url_str.startswith("file://") or os.path.exists(url_str):
            path = url.toLocalFile() if url_str.startswith("file://") else url_str
            if os.path.exists(path):
                subprocess.Popen(["xdg-open", path])

    def show_session(self, html: str, highlight_term: str = "", match_count: int = 0):
        """显示会话记录 HTML"""
        self._current_id = None
        self._current_mem = None
        self._highlight_term = highlight_term
        self._total_matches = match_count
        self._current_match = 0

        self.browser.setHtml(html)
        
        # 显示/隐藏导航栏
        if highlight_term and match_count > 0:
            self._match_label.setVisible(True)
            self._prev_btn.setVisible(True)
            self._next_btn.setVisible(True)
            self._current_match = 1
            self._update_nav_label()
            self.browser.scrollToAnchor("match-1")
        else:
            self._match_label.setVisible(False)
            self._prev_btn.setVisible(False)
            self._next_btn.setVisible(False)
        
        if self._show_actions:
            self.edit_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)

    def show_placeholder(self, text: str = "点击左侧列表查看详情"):
        self._current_id = None
        self._current_mem = None
        self.export_btn.setEnabled(False)
        self.browser.setHtml(
            f'<html><head><style>{_detail_css()}</style></head><body>'
            f'<p style="color: {C["overlay0"]}; text-align: center; margin-top: 40px; font-size: 14px;">'
            f'{text}</p></body></html>'
        )
        if self._show_actions:
            self.edit_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)

    def _on_export(self, fmt: str):
        if not self._current_mem:
            return
        from .exporter import format_memory, save_with_dialog
        content = format_memory(self._current_mem, fmt)
        safe_name = (self._current_mem.summary or self._current_mem.id[:12]).replace("/", "_")[:50]
        save_with_dialog(content, safe_name, fmt, self)
