"""图谱画布组件 — 可缩放视图、可点击节点、力导向布局"""

import math
import random

from PyQt5.QtWidgets import (
    QGraphicsScene, QGraphicsView, QGraphicsEllipseItem,
    QGraphicsTextItem,
)
from PyQt5.QtCore import Qt, QTimer, QRectF
from PyQt5.QtGui import QPen, QColor, QBrush, QFont, QPainter, QPalette

from ..constants import C


class ZoomableGraphicsView(QGraphicsView):
    """QGraphicsView with mouse wheel zoom"""

    def __init__(self, scene, parent=None):
        super().__init__(scene, parent)
        self._zoom_factor = 1.0

    def wheelEvent(self, event):
        factor = 1.15
        if event.angleDelta().y() > 0:
            self._zoom_factor *= factor
            self.scale(factor, factor)
        else:
            self._zoom_factor /= factor
            self.scale(1 / factor, 1 / factor)


class ClickableNode(QGraphicsEllipseItem):
    """Ellipse node that emits click via parent tab"""

    def __init__(self, entity_id, entity_name, rect, pen, brush, tab):
        super().__init__(rect)
        self.setPen(pen)
        self.setBrush(brush)
        self.entity_id = entity_id
        self.entity_name = entity_name
        self._tab = tab
        self.setCursor(Qt.PointingHandCursor)
        self.setAcceptHoverEvents(True)
        self._original_pen = pen

    def mousePressEvent(self, event):
        self._tab.on_node_clicked(self.entity_id, self.entity_name)
        super().mousePressEvent(event)

    def hoverEnterEvent(self, event):
        self.setPen(QPen(QColor(C["lavender"]), 3))
        super().hoverEnterEvent(event)

    def hoverLeaveEvent(self, event):
        self.setPen(self._original_pen)
        super().hoverLeaveEvent(event)


class EntityNode:
    def __init__(self, name: str, entity_id: str, x: float, y: float):
        self.name = name
        self.entity_id = entity_id
        self.x = x
        self.y = y
        self.vx = 0.0
        self.vy = 0.0
        self.ellipse: ClickableNode | None = None
        self.label: QGraphicsTextItem | None = None


TYPE_COLORS = {
    "technology": "blue", "project": "green",
    "component": "peach", "issue": "red",
    "tool": "lavender", "workflow": "yellow",
}


def draw_graph(scene: QGraphicsScene, nodes: dict, edges: list,
               selected_entity: str | None, entity_types: dict, tab):
    """绘制图谱（节点 + 边 + 标签）"""
    scene.clear()
    scene.setBackgroundBrush(QBrush(QColor(C["crust"])))
    node_radius = 22
    edge_color = QColor(C["surface2"])

    for src_id, tgt_id, label in edges:
        src = nodes[src_id]
        tgt = nodes[tgt_id]
        scene.addLine(
            src.x, src.y, tgt.x, tgt.y,
            QPen(edge_color, 1.5),
        )
        if label:
            mid_x = (src.x + tgt.x) / 2
            mid_y = (src.y + tgt.y) / 2
            edge_label = scene.addText(label, QFont("sans-serif", 7))
            edge_label.setDefaultTextColor(QColor(C["overlay0"]))
            br = edge_label.boundingRect()
            edge_label.setPos(mid_x - br.width() / 2, mid_y - br.height() / 2)

    for node in nodes.values():
        pen = QPen(QColor(C["surface2"]), 2)
        if selected_entity and node.entity_id == selected_entity:
            pen = QPen(QColor(C["lavender"]), 3)

        etype = entity_types.get(node.entity_id, "technology")
        nc = QColor(C.get(TYPE_COLORS.get(etype, "blue"), C["blue"]))

        rect = QRectF(
            node.x - node_radius, node.y - node_radius,
            node_radius * 2, node_radius * 2,
        )
        ellipse = ClickableNode(
            node.entity_id, node.name,
            rect, pen, QBrush(nc), tab,
        )
        scene.addItem(ellipse)
        node.ellipse = ellipse

        text = scene.addText(node.name, QFont("sans-serif", 9))
        text.setDefaultTextColor(QColor(C["text"]))
        br = text.boundingRect()
        text.setPos(node.x - br.width() / 2, node.y + node_radius + 2)
        node.label = text


def simulate_step(nodes: dict, edges: list, iteration: int) -> bool:
    """执行一步力导向模拟，返回是否应继续"""
    if iteration > 150:
        return False

    n_nodes = len(nodes)
    k = max(150.0, n_nodes * 10.0)
    ideal_edge = k * 1.5
    damping = 0.75
    gravity = 0.02
    node_list = list(nodes.values())

    for n in node_list:
        n.vx = 0
        n.vy = 0

    for i, a in enumerate(node_list):
        for b in node_list[i + 1:]:
            dx = a.x - b.x
            dy = a.y - b.y
            dist = max(math.sqrt(dx * dx + dy * dy), 10.0)
            force = k * k / (dist * dist) * 2.0
            fx = force * dx / dist
            fy = force * dy / dist
            a.vx += fx
            a.vy += fy
            b.vx -= fx
            b.vy -= fy

    for src_id, tgt_id, _ in edges:
        a = nodes[src_id]
        b = nodes[tgt_id]
        dx = a.x - b.x
        dy = a.y - b.y
        dist = max(math.sqrt(dx * dx + dy * dy), 1.0)
        force = (dist - ideal_edge) * 0.1
        fx = force * dx / dist
        fy = force * dy / dist
        a.vx -= fx
        a.vy -= fy
        b.vx += fx
        b.vy += fy

    for n in node_list:
        n.vx -= n.x * gravity
        n.vy -= n.y * gravity

    temperature = max(0.1, 1.0 - iteration / 150.0) * 4.0
    bound = max(800, n_nodes * 40)
    for n in node_list:
        n.x = max(-bound, min(bound, n.x + n.vx * damping * temperature))
        n.y = max(-bound, min(bound, n.y + n.vy * damping * temperature))

    return True


def layout_initial(nodes: dict, edges: list):
    """初始化节点布局：连通节点环形排列，孤立节点网格排列"""
    connected = set()
    for src_id, tgt_id, _ in edges:
        if src_id in nodes and tgt_id in nodes:
            connected.add(src_id)
            connected.add(tgt_id)

    n = len(nodes)
    radius = max(300, n * 25)
    conn_list = [eid for eid in nodes if eid in connected]
    iso_list = [eid for eid in nodes if eid not in connected]

    for idx, eid in enumerate(conn_list):
        angle = 2 * math.pi * idx / max(len(conn_list), 1)
        r = radius * 0.6
        nodes[eid].x = r * math.cos(angle)
        nodes[eid].y = r * math.sin(angle)

    cols = max(1, int(math.ceil(math.sqrt(len(iso_list)))))
    spacing = 120
    offset_x = -cols * spacing / 2
    offset_y = radius * 0.8
    for idx, eid in enumerate(iso_list):
        col = idx % cols
        row = idx // cols
        nodes[eid].x = offset_x + col * spacing
        nodes[eid].y = offset_y + row * spacing


def center_view(view: QGraphicsView, scene: QGraphicsScene, min_size: int = 600):
    """自适应居中视图"""
    rect = scene.itemsBoundingRect().adjusted(-80, -80, 80, 80)
    if not rect.isEmpty():
        if min_size and rect.width() < min_size:
            cx = rect.center().x()
            rect.setLeft(cx - min_size / 2)
            rect.setRight(cx + min_size / 2)
        if min_size and rect.height() < min_size:
            cy = rect.center().y()
            rect.setTop(cy - min_size / 2)
            rect.setBottom(cy + min_size / 2)
        scene.setSceneRect(rect.adjusted(-100, -100, 100, 100))
        view.resetTransform()
        if hasattr(view, "_zoom_factor"):
            view._zoom_factor = 1.0
        view.fitInView(rect, Qt.KeepAspectRatio)
