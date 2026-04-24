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

    PADDING_H = 14
    PADDING_V = 8
    SUB_H = 18
    LH = 16
    MAX_LINES = 1
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
        return QSize(option.rect.width(), 88)

    def paint(self, painter: QPainter, option, index):
        painter.save()
        painter.setRenderHint(QPainter.Antialiasing)
        rect = option.rect.adjusted(4, 3, -4, -3)

        data = index.data(Qt.UserRole + 1)
        if not data:
            painter.restore(); return

        is_sel = bool(option.state & QStyle.State_Selected)
        is_hov = bool(option.state & QStyle.State_MouseOver)
        fw_color = C["blue"]

        bg = QColor(C["base"])
        bg.setAlpha(245)
        border = QColor(C["surface2"])
        border.setAlpha(90)
        if is_sel:
            bg = QColor(C["surface0"])
            bg.setAlpha(230)
            border = QColor(fw_color)
        elif is_hov:
            bg = QColor(C["surface0"])
            bg.setAlpha(180)
            border = QColor(fw_color)
            border.setAlpha(120)

        painter.setBrush(bg)
        painter.setPen(QPen(border, 1.2))
        painter.drawRoundedRect(rect, 14, 14)

        accent = QColor(fw_color)
        accent.setAlpha(255 if is_sel else 190)
        painter.setBrush(accent)
        painter.setPen(Qt.NoPen)
        painter.drawRoundedRect(QRect(rect.x() + 4, rect.y() + 8, 4, rect.height() - 16), 2, 2)

        title = data.get("title", "")
        framework = data.get("framework", "会话记录")
        time_str = data.get("time", "")
        msg_count = data.get("msg_count", 0)
        workspace = data.get("workspace", "")
        archived = data.get("archived", False)

        x = rect.x() + self.PADDING_H
        y = rect.y() + self.PADDING_V
        w = rect.width() - 2 * self.PADDING_H
        tx, tw = x, w

        badge_font = QFont("sans-serif", 8)
        badge_metrics = QFontMetrics(badge_font)
        badge_text = framework
        badge_w = badge_metrics.horizontalAdvance(badge_text) + 14
        badge_h = 18

        badge_bg = QColor(C["blue"])
        badge_bg.setAlpha(42)
        badge_border = QColor(C["blue"])
        badge_border.setAlpha(120)
        painter.setBrush(badge_bg)
        painter.setPen(QPen(badge_border, 1))
        painter.drawRoundedRect(QRect(x, y, badge_w, badge_h), 6, 6)
        painter.setFont(badge_font)
        painter.setPen(QColor(C["blue"]))
        painter.drawText(QRect(x, y, badge_w, badge_h), Qt.AlignCenter, badge_text)

        if time_str:
            painter.setFont(QFont("sans-serif", 9))
            painter.setPen(QColor(C["overlay0"]))
            painter.drawText(
                QRect(x + badge_w + 10, y, w - badge_w - 10, badge_h),
                Qt.AlignRight | Qt.AlignVCenter,
                time_str,
            )

        y += badge_h + 8
        meta_y = rect.bottom() - self.PADDING_V - 14

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

        painter.setFont(self._sf)
        sfm = QFontMetrics(self._sf)
        painter.setPen(QColor(C["overlay0"]))
        sx = rect.x() + self.PADDING_H
        if msg_count:
            msg_text = f"{msg_count} 条"
            msg_w = sfm.horizontalAdvance(msg_text)
            painter.drawText(QRect(sx, meta_y, msg_w + 4, 14), Qt.AlignLeft | Qt.AlignVCenter, msg_text)
            sx += sfm.horizontalAdvance(f"{msg_count} 条") + 10
        if workspace:
            painter.setPen(QColor(C["subtext0"]))
            painter.drawText(QRect(sx, meta_y, w - (sx - x), 14), Qt.AlignLeft | Qt.AlignVCenter, workspace)

        painter.restore()
