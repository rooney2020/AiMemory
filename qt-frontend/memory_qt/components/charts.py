"""可视化图表组件 — 纯 QPainter 实现"""

from datetime import datetime, timedelta
from collections import Counter, defaultdict
import math

from PyQt5.QtWidgets import QWidget, QVBoxLayout, QLabel, QFrame, QSizePolicy
from PyQt5.QtCore import Qt, QRectF, QPointF
from PyQt5.QtGui import QPainter, QColor, QPen, QBrush, QFont, QFontMetrics, QPainterPath

from ..constants import C


class _ChartBase(QWidget):
    def __init__(self, title: str, parent=None):
        super().__init__(parent)
        self._title = title
        self.setMinimumHeight(200)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)

    def _draw_title(self, painter: QPainter, rect: QRectF):
        painter.setPen(QColor(C["text"]))
        painter.setFont(QFont("sans-serif", 13, QFont.Bold))
        painter.drawText(QPointF(rect.x() + 8, rect.y() + 22), self._title)


class BarChart(_ChartBase):
    """通用柱状图"""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self._data: list[tuple[str, int, str]] = []  # (label, value, color_key)

    def set_data(self, data: list[tuple[str, int, str]]):
        self._data = data
        h = max(200, 40 + len(data) * 28 + 16)
        self.setFixedHeight(h)
        self.update()

    def paintEvent(self, event):
        if not self._data:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        rect = QRectF(0, 0, w, h)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(C["base"]))
        painter.drawRoundedRect(rect, 10, 10)

        self._draw_title(painter, rect)

        max_val = max((v for _, v, _ in self._data), default=1) or 1
        label_font = QFont("sans-serif", 10)
        fm = QFontMetrics(label_font)
        max_label_w = max((fm.horizontalAdvance(label) for label, _, _ in self._data), default=60)
        max_label_w = min(max_label_w, w * 0.3)

        y_start = 40
        bar_h = 20
        gap = 8
        bar_area_w = w - max_label_w - 80

        for i, (label, value, color_key) in enumerate(self._data):
            y = y_start + i * (bar_h + gap)

            painter.setFont(label_font)
            painter.setPen(QColor(C["subtext0"]))
            elided = fm.elidedText(label, Qt.ElideRight, int(max_label_w))
            painter.drawText(
                QRectF(8, y, max_label_w, bar_h),
                Qt.AlignRight | Qt.AlignVCenter, elided,
            )

            bar_w = max(4, (value / max_val) * bar_area_w)
            bar_x = max_label_w + 16

            color = QColor(C.get(color_key, C["blue"]))
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(bar_x, y + 2, bar_w, bar_h - 4), 4, 4)

            painter.setPen(QColor(C["text"]))
            painter.setFont(QFont("sans-serif", 9))
            painter.drawText(
                QRectF(bar_x + bar_w + 6, y, 60, bar_h),
                Qt.AlignLeft | Qt.AlignVCenter, str(value),
            )

        painter.end()


class TimelineChart(_ChartBase):
    """时间线柱状图 — 按月/周聚合"""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self._buckets: list[tuple[str, int, str]] = []  # (label, count, color_key)
        self.setFixedHeight(220)

    def set_data_from_memories(self, memories, group_by: str = "month"):
        buckets = defaultdict(int)
        type_colors = {"episodic": "teal", "semantic": "blue", "procedural": "mauve"}

        for mem in memories:
            dt = mem.created_at
            if group_by == "month":
                key = dt.strftime("%Y-%m")
            else:
                iso_year, iso_week, _ = dt.isocalendar()
                key = f"{iso_year}-W{iso_week:02d}"
            buckets[key] += 1

        sorted_keys = sorted(buckets.keys())[-24:]
        self._buckets = [(k, buckets[k], "blue") for k in sorted_keys]
        self.update()

    def paintEvent(self, event):
        if not self._buckets:
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        rect = QRectF(0, 0, w, h)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(C["base"]))
        painter.drawRoundedRect(rect, 10, 10)

        self._draw_title(painter, rect)

        margin_left = 40
        margin_right = 16
        margin_top = 44
        margin_bottom = 40
        chart_w = w - margin_left - margin_right
        chart_h = h - margin_top - margin_bottom

        n = len(self._buckets)
        if n == 0:
            painter.end()
            return

        max_val = max(v for _, v, _ in self._buckets) or 1
        bar_w = max(4, min(30, (chart_w - n * 2) / n))
        total_bars_w = n * (bar_w + 2)
        offset_x = margin_left + (chart_w - total_bars_w) / 2

        painter.setPen(QPen(QColor(C["surface1"]), 1))
        for i in range(5):
            y = margin_top + chart_h * i / 4
            painter.drawLine(QPointF(margin_left, y), QPointF(w - margin_right, y))
            val = int(max_val * (4 - i) / 4)
            painter.setFont(QFont("sans-serif", 8))
            painter.setPen(QColor(C["overlay0"]))
            painter.drawText(QRectF(0, y - 8, margin_left - 4, 16),
                             Qt.AlignRight | Qt.AlignVCenter, str(val))
            painter.setPen(QPen(QColor(C["surface1"]), 1))

        for i, (label, value, color_key) in enumerate(self._buckets):
            x = offset_x + i * (bar_w + 2)
            bar_h = (value / max_val) * chart_h if max_val else 0
            y = margin_top + chart_h - bar_h

            color = QColor(C.get(color_key, C["blue"]))
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawRoundedRect(QRectF(x, y, bar_w, bar_h), 2, 2)

            if n <= 12 or i % max(1, n // 8) == 0:
                painter.setPen(QColor(C["overlay0"]))
                painter.setFont(QFont("sans-serif", 7))
                short_label = label.split("-")[-1] if "-" in label else label
                painter.drawText(
                    QRectF(x - 10, margin_top + chart_h + 4, bar_w + 20, 20),
                    Qt.AlignCenter, short_label,
                )

        painter.end()


class StrengthDistribution(_ChartBase):
    """强度分布散点图 — 横轴为强度，纵轴为创建时间，点大小为访问次数"""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self._points: list[tuple[float, float, float, str]] = []
        self.setFixedHeight(240)

    def set_data_from_memories(self, memories):
        if not memories:
            self._points = []
            self.update()
            return

        now = datetime.now()
        max_days = 1
        for m in memories:
            age = (now - m.created_at).days
            if age > max_days:
                max_days = age

        self._points = []
        for m in memories:
            x_norm = m.strength / 10.0
            age = (now - m.created_at).days
            y_norm = age / max(max_days, 1)
            size = min(1.0, 0.3 + (m.access_count or 0) * 0.1)
            color_key = {"episodic": "teal", "semantic": "blue", "procedural": "mauve"}.get(
                m.type.value, "blue"
            )
            self._points.append((x_norm, y_norm, size, color_key))
        self.update()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        w, h = self.width(), self.height()
        rect = QRectF(0, 0, w, h)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(C["base"]))
        painter.drawRoundedRect(rect, 10, 10)
        self._draw_title(painter, rect)

        margin_l, margin_r, margin_t, margin_b = 50, 20, 44, 36
        cw = w - margin_l - margin_r
        ch = h - margin_t - margin_b

        painter.setPen(QPen(QColor(C["surface1"]), 1))
        painter.drawLine(
            QPointF(margin_l, margin_t + ch),
            QPointF(margin_l + cw, margin_t + ch),
        )
        painter.drawLine(
            QPointF(margin_l, margin_t),
            QPointF(margin_l, margin_t + ch),
        )

        painter.setFont(QFont("sans-serif", 8))
        painter.setPen(QColor(C["overlay0"]))
        for i in range(6):
            x = margin_l + cw * i / 5
            val = i * 2
            painter.drawText(QRectF(x - 10, margin_t + ch + 4, 20, 16),
                             Qt.AlignCenter, str(val))

        painter.drawText(
            QRectF(margin_l, margin_t + ch + 18, cw, 16),
            Qt.AlignCenter, "强度",
        )

        painter.save()
        painter.translate(10, margin_t + ch / 2)
        painter.rotate(-90)
        painter.drawText(QRectF(-30, 0, 60, 16), Qt.AlignCenter, "天数")
        painter.restore()

        for x_norm, y_norm, size, color_key in self._points:
            px = margin_l + x_norm * cw
            py = margin_t + (1 - y_norm) * ch
            radius = 3 + size * 6

            color = QColor(C.get(color_key, C["blue"]))
            color.setAlpha(160)
            painter.setPen(Qt.NoPen)
            painter.setBrush(color)
            painter.drawEllipse(QPointF(px, py), radius, radius)

        painter.end()


class EntityFrequencyChart(_ChartBase):
    """实体关联频率 — 显示最常出现的实体"""

    def __init__(self, title: str, parent=None):
        super().__init__(title, parent)
        self._data: list[tuple[str, int]] = []

    def set_data_from_memories(self, memories, top_n: int = 15):
        counter = Counter()
        for m in memories:
            if m.entities:
                for e in m.entities:
                    counter[e] += 1

        top = counter.most_common(top_n)
        if top:
            self._data = top
            h = max(200, 40 + len(top) * 28 + 16)
            self.setFixedHeight(h)
        else:
            self._data = []
            self.setFixedHeight(200)
        self.update()

    def paintEvent(self, event):
        if not self._data:
            painter = QPainter(self)
            painter.setRenderHint(QPainter.Antialiasing)
            w, h = self.width(), self.height()
            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(C["base"]))
            painter.drawRoundedRect(QRectF(0, 0, w, h), 10, 10)
            self._draw_title(painter, QRectF(0, 0, w, h))
            painter.setPen(QColor(C["overlay0"]))
            painter.setFont(QFont("sans-serif", 11))
            painter.drawText(QRectF(0, 40, w, h - 40), Qt.AlignCenter, "暂无实体数据")
            painter.end()
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        rect = QRectF(0, 0, w, h)

        painter.setPen(Qt.NoPen)
        painter.setBrush(QColor(C["base"]))
        painter.drawRoundedRect(rect, 10, 10)
        self._draw_title(painter, rect)

        max_val = max(c for _, c in self._data) or 1
        label_font = QFont("sans-serif", 10)
        fm = QFontMetrics(label_font)
        max_label_w = max(fm.horizontalAdvance(n) for n, _ in self._data)
        max_label_w = min(max_label_w, w * 0.3)

        y_start = 40
        bar_h = 20
        gap = 8
        bar_area_w = w - max_label_w - 80

        for i, (name, count) in enumerate(self._data):
            y = y_start + i * (bar_h + gap)

            painter.setFont(label_font)
            painter.setPen(QColor(C["subtext0"]))
            elided = fm.elidedText(name, Qt.ElideRight, int(max_label_w))
            painter.drawText(
                QRectF(8, y, max_label_w, bar_h),
                Qt.AlignRight | Qt.AlignVCenter, elided,
            )

            bar_w = max(4, (count / max_val) * bar_area_w)
            bar_x = max_label_w + 16

            painter.setPen(Qt.NoPen)
            painter.setBrush(QColor(C["peach"]))
            painter.drawRoundedRect(QRectF(bar_x, y + 2, bar_w, bar_h - 4), 4, 4)

            painter.setPen(QColor(C["text"]))
            painter.setFont(QFont("sans-serif", 9))
            painter.drawText(
                QRectF(bar_x + bar_w + 6, y, 60, bar_h),
                Qt.AlignLeft | Qt.AlignVCenter, str(count),
            )

        painter.end()
