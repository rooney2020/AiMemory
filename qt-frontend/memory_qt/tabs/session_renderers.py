"""会话渲染工具 — Markdown、搜索高亮、自适应浏览器、列表 Delegate"""

from PyQt5.QtWidgets import (
    QTextBrowser, QSizePolicy, QStyledItemDelegate, QStyle,
)
from PyQt5.QtCore import Qt, QTimer, QSize, QRect
from PyQt5.QtGui import (
    QFont, QColor, QIcon, QPixmap, QPainter, QPen, QFontMetrics,
)

try:
    import markdown as _md
    _MD_AVAILABLE = True
except ImportError:
    _MD_AVAILABLE = False

from ..constants import C, FONT_MONO

MESSAGES_PER_PAGE = 10
RENDER_BATCH_SIZE = 3


class AutoHeightBrowser(QTextBrowser):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        self._height_timer = QTimer(self)
        self._height_timer.setSingleShot(True)
        self._height_timer.setInterval(0)
        self._height_timer.timeout.connect(self._do_adjust_height)
        self.document().contentsChanged.connect(self._schedule_height)

    def _schedule_height(self):
        if not self._height_timer.isActive():
            self._height_timer.start()

    def _do_adjust_height(self):
        doc = self.document()
        w = self.viewport().width() if self.viewport().width() > 0 else 600
        doc.setTextWidth(w)
        h = int(doc.size().height()) + 8
        if self.minimumHeight() != h:
            self.setMinimumHeight(h)
            self.setMaximumHeight(h)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._schedule_height()

    def showEvent(self, event):
        super().showEvent(event)
        self._schedule_height()


def split_thinking(text: str) -> tuple[str, str]:
    parts = text.split("\n\n", 1)
    if len(parts) < 2:
        return text, ""

    visible = parts[0].strip()
    rest = parts[1].strip()

    _THINKING_MARKERS = [
        "让我", "用户想", "用户要求", "用户说", "用户提到",
        "我需要", "现在我", "首先", "好的，",
        "The user", "Let me", "I need", "Now I",
        "Looking at", "Based on", "From the",
    ]

    if any(rest.startswith(m) for m in _THINKING_MARKERS):
        return visible, rest

    return text, ""


def render_markdown(text: str, bg: str, is_user: bool) -> str:
    if _MD_AVAILABLE and not is_user:
        try:
            body = _md.markdown(
                text,
                extensions=["fenced_code", "tables", "nl2br"],
            )
        except Exception:
            body = f"<pre>{text}</pre>"
    else:
        import html
        body = f"<p>{html.escape(text).replace(chr(10), '<br>')}</p>"

    return f"""<html><body style="
        color: {C['text']}; font-size: 13px; font-family: sans-serif;
        line-height: 1.6; margin: 0; padding: 0; word-wrap: break-word;
        overflow-wrap: break-word;
    ">
    <style>
        * {{ word-wrap: break-word; overflow-wrap: break-word; }}
        code {{ background: {C['mantle']}; padding: 2px 6px; border-radius: 4px;
               font-family: {FONT_MONO}; font-size: 12px;
               word-break: break-all; }}
        pre {{ background: {C['mantle']}; padding: 10px 12px; border-radius: 8px;
              font-family: {FONT_MONO}; font-size: 12px;
              line-height: 1.4; white-space: pre-wrap; word-break: break-all; }}
        pre code {{ background: transparent; padding: 0; }}
        table {{ border-collapse: collapse; margin: 8px 0; width: 100%; }}
        th, td {{ border: 1px solid {C['surface1']}; padding: 6px 10px; text-align: left; }}
        th {{ background: {C['mantle']}; font-weight: bold; }}
        a {{ color: {C['blue']}; }}
        h1, h2, h3 {{ color: {C['text']}; margin: 8px 0 4px 0; }}
        ul, ol {{ padding-left: 20px; margin: 4px 0; }}
        p {{ margin: 4px 0; }}
        strong {{ color: {C['text']}; }}
        blockquote {{ border-left: 3px solid {C['blue']}; padding-left: 12px;
                     color: {C['subtext0']}; margin: 8px 0; }}
    </style>
    {body}
    </body></html>"""


def highlight_search(html_content: str, term: str) -> str:
    """在 HTML 中高亮搜索关键词（跳过 HTML 标签内部）"""
    if not term or len(term) < 2:
        return html_content
    import re
    tag_pattern = re.compile(r'(<[^>]+>)')
    parts = tag_pattern.split(html_content)
    result = []
    escaped_term = re.escape(term)
    for part in parts:
        if part.startswith('<'):
            result.append(part)
        else:
            part = re.sub(
                escaped_term,
                lambda m: f'<span style="background: #f9e2af; color: #1e1e2e; padding: 1px 2px; '
                          f'border-radius: 2px; font-weight: bold;">{m.group(0)}</span>',
                part,
                flags=re.IGNORECASE,
            )
            result.append(part)
    return ''.join(result)


def make_dot_icon(color: str, size: int = 12) -> QIcon:
    px = QPixmap(size, size)
    px.fill(Qt.transparent)
    p = QPainter(px)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(color))
    p.setPen(Qt.NoPen)
    p.drawEllipse(1, 1, size - 2, size - 2)
    p.end()
    return QIcon(px)


class SessionDelegate(QStyledItemDelegate):
    """自定义会话列表项渲染：标题自动换行 + 下方元信息"""

    PADDING_H = 10
    PADDING_V = 6
    SUB_H = 18
    LH = 17
    MAX_LINES = 3
    _tf = QFont("sans-serif", 11)
    _sf = QFont("sans-serif", 9)

    @staticmethod
    def _wrap(title: str, max_w: int, fm: QFontMetrics, max_lines: int = 3) -> list[str]:
        if fm.horizontalAdvance(title) <= max_w:
            return [title]
        lines: list[str] = []
        rest = title
        while rest and len(lines) < max_lines:
            cur = ""
            for ch in rest:
                if fm.horizontalAdvance(cur + ch) > max_w:
                    break
                cur += ch
            if not cur:
                cur = rest[0]
            rest = rest[len(cur):]
            if rest and len(lines) == max_lines - 1:
                cur = fm.elidedText(cur + rest, Qt.ElideRight, max_w)
                rest = ""
            lines.append(cur)
        return lines

    def sizeHint(self, option, index):
        data = index.data(Qt.UserRole + 1)
        if not data:
            return QSize(option.rect.width(), 50)
        title = data.get("title", "")
        avail = max(200, (option.rect.width() or 300) - 2 * self.PADDING_H - 4)
        n = len(self._wrap(title, avail, QFontMetrics(self._tf), self.MAX_LINES))
        return QSize(option.rect.width(), self.PADDING_V * 2 + n * self.LH + self.SUB_H + 2)

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(2, 1, -2, -1)

        is_sel = bool(option.state & QStyle.State_Selected)
        is_hov = bool(option.state & QStyle.State_MouseOver)
        if is_sel:
            bg = QColor(C["surface0"]); bg.setAlpha(180)
            painter.setBrush(bg); painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 6, 6)
        elif is_hov:
            bg = QColor(C["surface0"]); bg.setAlpha(100)
            painter.setBrush(bg); painter.setPen(Qt.NoPen)
            painter.drawRoundedRect(rect, 6, 6)

        data = index.data(Qt.UserRole + 1)
        if not data:
            painter.restore(); return

        title = data.get("title", "")
        time_str = data.get("time", "")
        msg_count = data.get("msg_count", 0)
        workspace = data.get("workspace", "")
        archived = data.get("archived", False)
        fw_color = data.get("fw_color", C["blue"])

        x = rect.x() + self.PADDING_H
        y = rect.y() + self.PADDING_V
        w = rect.width() - 2 * self.PADDING_H
        tx, tw = x, w

        if archived:
            painter.setBrush(QColor(C["surface1"])); painter.setPen(Qt.NoPen)
            tfm = QFontMetrics(QFont("sans-serif", 8))
            tw2 = tfm.horizontalAdvance("归档") + 8
            painter.drawRoundedRect(QRect(x, y + 1, tw2, 14), 3, 3)
            painter.setPen(QColor(C["overlay0"]))
            painter.setFont(QFont("sans-serif", 8))
            painter.drawText(QRect(x, y + 1, tw2, 14), Qt.AlignCenter, "归档")
            tx += tw2 + 4; tw -= tw2 + 4

        painter.setFont(self._tf)
        painter.setPen(QColor(C["text"] if not archived else C["overlay0"]))
        lines = self._wrap(title, tw, QFontMetrics(self._tf), self.MAX_LINES)
        for i, ln in enumerate(lines):
            painter.drawText(QRect(tx, y + i * self.LH, tw, self.LH),
                             Qt.AlignLeft | Qt.AlignVCenter, ln)

        sy = y + len(lines) * self.LH + 2
        painter.setFont(self._sf)
        sfm = QFontMetrics(self._sf)
        painter.setPen(QColor(C["overlay0"]))
        sx = rect.x() + self.PADDING_H
        if time_str:
            painter.drawText(sx, sy + 12, time_str)
            sx += sfm.horizontalAdvance(time_str) + 10
        if msg_count:
            painter.drawText(sx, sy + 12, f"{msg_count} 条")
            sx += sfm.horizontalAdvance(f"{msg_count} 条") + 10
        if workspace:
            painter.setPen(QColor(fw_color))
            painter.drawText(sx, sy + 12, workspace)

        painter.restore()
