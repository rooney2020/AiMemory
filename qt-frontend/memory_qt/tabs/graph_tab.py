# -*- coding: utf-8 -*-
"""Entity graph tab with interactive nodes, zoom, and related memory panel"""

import random
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QGraphicsView, QSplitter,
    QScrollArea, QFrame, QDialog, QLineEdit, QComboBox,
    QFormLayout, QMessageBox, QSizePolicy,
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPainter, QPalette

from ..constants import C
from ..theme import secondary_btn_style
from ..data_bridge import DataBridge
from ..components.memory_card import MemoryCard
from ..components.detail_panel import DetailPanel

from .graph_canvas import (
    ZoomableGraphicsView, EntityNode,
    draw_graph, simulate_step, layout_initial, center_view,
)


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


class GraphTab(QWidget):
    RELATION_LABELS = {
        "co_occurs": "共现",
        "depends_on": "依赖",
        "contains": "包含",
        "fixes": "修复",
        "causes": "导致",
    }

    def __init__(self, bridge: DataBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self.nodes: dict[str, EntityNode] = {}
        self.edges: list[tuple[str, str, str]] = []
        self._selected_entity: str | None = None
        self._related_memories = []
        self._entity_types: dict[str, str] = {}
        self._metric_values = {}
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        hero = QFrame()
        self._hero_frame = hero
        hero.setStyleSheet("QFrame { background: transparent; border: none; }")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(4, 2, 4, 0)
        hero_layout.setSpacing(16)

        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(6)

        self._hero_kicker = QLabel("GRAPH / RELATIONS")
        self._hero_kicker.setVisible(False)
        hero_text.addWidget(self._hero_kicker, 0, Qt.AlignLeft)

        self._header = QLabel("实体关系图谱")
        hero_text.addWidget(self._header)

        self._hero_desc = QLabel("把实体、关系和关联记忆放在同一工作台里观察，左侧看网络结构，右侧读节点上下文。")
        self._hero_desc.setWordWrap(True)
        self._hero_desc.setVisible(False)
        hero_text.addWidget(self._hero_desc)
        hero_text.addStretch(1)
        hero_layout.addLayout(hero_text, 1)

        hero_side = QVBoxLayout()
        hero_side.setContentsMargins(0, 0, 0, 0)
        hero_side.setSpacing(10)

        self.entity_count_label = QLabel("等待加载图谱")
        hero_side.addWidget(self.entity_count_label, 0, Qt.AlignRight)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        self._add_entity_btn = QPushButton("+ 实体")
        self._add_entity_btn.clicked.connect(self._add_entity_dialog)
        action_row.addWidget(self._add_entity_btn)

        self._add_rel_btn = QPushButton("+ 关系")
        self._add_rel_btn.clicked.connect(self._add_relation_dialog)
        action_row.addWidget(self._add_rel_btn)

        self._del_entity_btn = QPushButton("删除实体")
        self._del_entity_btn.setEnabled(False)
        self._del_entity_btn.clicked.connect(self._delete_selected_entity)
        action_row.addWidget(self._del_entity_btn)

        self._zoom_reset_btn = QPushButton("适应窗口")
        self._zoom_reset_btn.clicked.connect(self._center_view)
        action_row.addWidget(self._zoom_reset_btn)

        self._refresh_btn = QPushButton("重新布局")
        self._refresh_btn.clicked.connect(self._relayout)
        action_row.addWidget(self._refresh_btn)
        hero_side.addLayout(action_row)

        metrics_row = QHBoxLayout()
        metrics_row.setContentsMargins(0, 0, 0, 0)
        metrics_row.setSpacing(10)
        metrics_row.addWidget(self._build_metric_card("entities", "实体数", "blue"))
        metrics_row.addWidget(self._build_metric_card("relations", "关系数", "teal"))
        metrics_row.addWidget(self._build_metric_card("related", "关联记忆", "yellow"))
        hero_side.addLayout(metrics_row)
        hero_layout.addLayout(hero_side)

        layout.addWidget(hero)
        hero.hide()

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        graph_panel = QFrame()
        self._graph_panel = graph_panel
        graph_layout = QVBoxLayout(graph_panel)
        graph_layout.setContentsMargins(16, 16, 16, 16)
        graph_layout.setSpacing(12)

        self._graph_kicker = QLabel("GRAPH CANVAS")
        self._graph_kicker.setVisible(False)
        graph_layout.addWidget(self._graph_kicker)

        self._graph_title = QLabel("关系网络画布")
        graph_layout.addWidget(self._graph_title)

        self._graph_hint = QLabel("支持拖拽、滚轮缩放和节点点击。重新布局只影响画布，不改动实体关系本身。")
        self._graph_hint.setWordWrap(True)
        graph_layout.addWidget(self._graph_hint)

        canvas_shell = QFrame()
        self._canvas_shell = canvas_shell
        canvas_layout = QVBoxLayout(canvas_shell)
        canvas_layout.setContentsMargins(12, 12, 12, 12)
        canvas_layout.setSpacing(0)

        from PyQt5.QtWidgets import QGraphicsScene
        self.scene = QGraphicsScene()
        self.view = ZoomableGraphicsView(self.scene)
        self.view.setRenderHint(QPainter.Antialiasing, True)
        self.view.setRenderHint(QPainter.TextAntialiasing, True)
        self.view.setDragMode(QGraphicsView.ScrollHandDrag)
        self._apply_view_palette()
        self.view.setAutoFillBackground(True)
        self.view.setFrameShape(0)
        canvas_layout.addWidget(self.view)
        graph_layout.addWidget(canvas_shell, 1)
        splitter.addWidget(graph_panel)

        right_panel = QFrame()
        self._right_panel = right_panel
        right_layout = QVBoxLayout(right_panel)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        reader_header = QFrame()
        self._reader_header = reader_header
        reader_header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        reader_layout = QVBoxLayout(reader_header)
        reader_layout.setContentsMargins(16, 14, 16, 14)
        reader_layout.setSpacing(8)

        self._reader_badge = QLabel("IDLE")
        self._reader_badge.setVisible(False)
        reader_layout.addWidget(self._reader_badge, 0, Qt.AlignLeft)

        self._reader_title = QLabel("节点阅读区")
        reader_layout.addWidget(self._reader_title)

        self._reader_subtitle = QLabel("选择左侧节点后，这里会展开实体信息、关联记忆列表和具体记忆详情。")
        self._reader_subtitle.setWordWrap(True)
        reader_layout.addWidget(self._reader_subtitle)
        right_layout.addWidget(reader_header)

        self.entity_info = QLabel("点击图谱中的节点查看详情")
        self.entity_info.setObjectName("entity_info")
        self.entity_info.setWordWrap(True)
        right_layout.addWidget(self.entity_info)

        self.related_label = QLabel("关联记忆")
        self.related_label.setObjectName("related_label")
        self.related_label.setStyleSheet(
            f"color: {C['text']}; font-size: 14px; font-weight: bold;"
        )
        self.related_label.setVisible(False)
        right_layout.addWidget(self.related_label)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        self.memory_container = QWidget()
        self.memory_layout = QVBoxLayout(self.memory_container)
        self.memory_layout.setContentsMargins(0, 0, 0, 0)
        self.memory_layout.setSpacing(10)
        scroll.setWidget(self.memory_container)
        right_layout.addWidget(scroll, 1)

        self.detail = DetailPanel()
        self.detail.setVisible(False)
        right_layout.addWidget(self.detail, 2)

        splitter.addWidget(right_panel)
        splitter.setSizes([760, 420])
        layout.addWidget(splitter, 1)

        self.timer = QTimer()
        self.timer.timeout.connect(self._simulate_step)
        self._iteration = 0
        self._apply_shell_styles()

    def topbar_context_widgets(self):
        summary_widgets = [self.entity_count_label]
        summary_widgets.extend(frame for frame, *_ in self._metric_values.values())
        return summary_widgets, [
            self._add_entity_btn,
            self._add_rel_btn,
            self._del_entity_btn,
            self._zoom_reset_btn,
            self._refresh_btn,
        ]

    def _build_metric_card(self, key: str, title: str, color_key: str) -> QFrame:
        frame = QFrame()
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        label = QLabel(title)
        layout.addWidget(label)

        value = QLabel("0")
        layout.addWidget(value)

        self._metric_values[key] = (frame, label, value, color_key)
        return frame

    def _panel_style(self) -> str:
        return (
            f"QFrame {{ background: {_rgba(C['base'], 0.96)}; border: 1px solid {_rgba(C['surface2'], 0.42)}; border-radius: 22px; }}"
        )

    def _sub_panel_style(self) -> str:
        return (
            f"QFrame {{ background: {_rgba(C['surface0'], 0.72)}; border: 1px solid {_rgba(C['surface2'], 0.28)}; border-radius: 18px; }}"
        )

    def _set_reader_state(self, badge: str, title: str, subtitle: str):
        self._reader_badge.setText(badge)
        self._reader_title.setText(title)
        self._reader_subtitle.setText(subtitle)

    def _update_summary(self, entity_count: int | None = None, relation_count: int | None = None):
        if entity_count is None:
            entity_count = len(self.nodes)
        if relation_count is None:
            relation_count = len(self.edges)
        self._metric_values["entities"][2].setText(str(entity_count))
        self._metric_values["relations"][2].setText(str(relation_count))
        self._metric_values["related"][2].setText(str(len(self._related_memories)))

    def _apply_shell_styles(self):
        self._hero_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        self._hero_kicker.setStyleSheet(
            f"color: {C['blue']}; font-size: 11px; font-weight: 800; background: {_rgba(C['blue'], 0.14)}; border: 1px solid {_rgba(C['blue'], 0.22)}; border-radius: 999px; padding: 5px 10px;"
        )
        self._header.setStyleSheet(f"color: {C['text']}; font-size: 24px; font-weight: 800;")
        self._hero_desc.setStyleSheet(f"color: {C['subtext0']}; font-size: 13px;")
        self.entity_count_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; font-weight: 700;")
        for frame, label, value, color_key in self._metric_values.values():
            frame.setStyleSheet(self._sub_panel_style())
            label.setStyleSheet(f"color: {C['subtext0']}; font-size: 11px; font-weight: 700; background: transparent; border: none;")
            value.setStyleSheet(f"color: {C[color_key]}; font-size: 22px; font-weight: 800; background: transparent; border: none;")
        self._add_entity_btn.setStyleSheet(secondary_btn_style())
        self._add_rel_btn.setStyleSheet(secondary_btn_style())
        self._zoom_reset_btn.setStyleSheet(secondary_btn_style())
        self._refresh_btn.setStyleSheet(secondary_btn_style())
        self._del_entity_btn.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['red']}, stop:1 {C['maroon']}); color: white; border: 1px solid transparent; border-radius: 14px; padding: 8px 16px; font-size: 13px; font-weight: 800; }}"
            f"QPushButton:hover {{ border-color: {_rgba(C['red'], 0.35)}; }}"
        )
        self._graph_panel.setStyleSheet(self._panel_style())
        self._graph_kicker.setStyleSheet(f"color: {C['teal']}; font-size: 11px; font-weight: 800; background: transparent; border: none;")
        self._graph_title.setStyleSheet(f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;")
        self._graph_hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        self._canvas_shell.setStyleSheet(self._sub_panel_style())
        self._right_panel.setStyleSheet(self._panel_style())
        self._reader_header.setStyleSheet(self._sub_panel_style())
        self._reader_badge.setStyleSheet(
            f"color: {C['lavender']}; font-size: 11px; font-weight: 800; background: {_rgba(C['lavender'], 0.12)}; border: 1px solid {_rgba(C['lavender'], 0.2)}; border-radius: 999px; padding: 4px 10px;"
        )
        self._reader_title.setStyleSheet(f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;")
        self._reader_subtitle.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        self.entity_info.setStyleSheet(
            f"color: {C['text']}; font-size: 13px; padding: 14px 16px; background: {_rgba(C['surface0'], 0.72)}; border: 1px solid {_rgba(C['surface2'], 0.28)}; border-radius: 18px;"
        )
        self.related_label.setStyleSheet(f"color: {C['text']}; font-size: 14px; font-weight: 800; background: transparent; border: none;")
        self.detail.refresh_style()

    def _apply_view_palette(self):
        pal = self.view.palette()
        dark = QColor(C["mantle"])
        pal.setColor(QPalette.Window, dark)
        pal.setColor(QPalette.Base, dark)
        self.view.setPalette(pal)

    def refresh_style(self):
        from PyQt5.QtGui import QBrush
        self._apply_shell_styles()
        self._apply_view_palette()
        self.scene.setBackgroundBrush(QBrush(QColor(C["mantle"])))

    def refresh(self):
        self.scene.clear()
        self.nodes.clear()
        self.edges.clear()
        self._related_memories = []

        entities = self.bridge.list_entities()
        relations = self.bridge.get_relations()

        self.entity_count_label.setText(
            f"{len(entities)} 个实体, {len(relations)} 条关系"
        )
        self._update_summary(len(entities), len(relations))

        if not entities:
            text = self.scene.addText("暂无实体数据")
            text.setDefaultTextColor(QColor(C["overlay0"]))
            self._set_reader_state("IDLE", "节点阅读区", "当前没有实体数据，可先创建实体或关系。")
            self.entity_info.setText("点击左侧图谱中的节点查看详情")
            return

        self._entity_types = {}
        for entity in entities:
            self.nodes[entity.id] = EntityNode(
                name=entity.name,
                entity_id=entity.id,
                x=random.uniform(-300, 300),
                y=random.uniform(-300, 300),
            )
            self._entity_types[entity.id] = entity.type or "technology"

        for rel in relations:
            src_id = rel["source_id"]
            tgt_id = rel["target_id"]
            if src_id in self.nodes and tgt_id in self.nodes:
                label = self._format_relation_label(rel["relation"], rel.get("weight"))
                self.edges.append((src_id, tgt_id, label))

        layout_initial(self.nodes, self.edges)
        self._draw_graph()
        self._fit_graph_initial_view()
        self._iteration = 0
        if self.nodes:
            self.timer.start(30)
            QTimer.singleShot(300, self._fit_graph_initial_view)

    def _draw_graph(self):
        draw_graph(self.scene, self.nodes, self.edges,
                   self._selected_entity, self._entity_types, self)

    def _format_relation_label(self, relation: str, weight: float | None) -> str:
        label = self.RELATION_LABELS.get(relation, relation)
        if weight and weight > 1:
            return f"{label} x{int(weight)}"
        return label

    def _simulate_step(self):
        self._iteration += 1
        if not simulate_step(self.nodes, self.edges, self._iteration):
            self.timer.stop()
            return
        self._draw_graph()
        if self._iteration >= 149:
            self._center_view()

    def _center_view(self):
        center_view(self.view, self.scene)

    def _fit_graph_initial_view(self):
        rect = self.scene.itemsBoundingRect().adjusted(-24, -24, 24, 24)
        if rect.isEmpty():
            return
        self.scene.setSceneRect(rect.adjusted(-36, -36, 36, 36))
        self.view.resetTransform()
        if hasattr(self.view, "_zoom_factor"):
            self.view._zoom_factor = 1.0
        self.view.fitInView(rect, Qt.KeepAspectRatio)

    def _relayout(self):
        for node in self.nodes.values():
            node.x = random.uniform(-200, 200)
            node.y = random.uniform(-200, 200)
        self._iteration = 0
        self.timer.start(30)

    def _on_memory_card_click(self, mem_id: str):
        for mem in self._related_memories:
            if mem.id == mem_id:
                self.detail.setVisible(True)
                self.detail.show_memory(mem)
                self._set_reader_state("MEM", mem.summary or mem.id[:12], f"关联项目: {mem.project or '(通用)'} · 强度: {mem.strength:.1f}")
                break

    def _highlight_node(self, entity_id: str):
        from PyQt5.QtGui import QPen
        for nid, node in self.nodes.items():
            if node.ellipse:
                if nid == entity_id:
                    node.ellipse.setPen(QPen(QColor(C["lavender"]), 3))
                else:
                    node.ellipse.setPen(QPen(QColor(C["surface2"]), 2))

    def on_node_clicked(self, entity_id: str, entity_name: str):
        self._selected_entity = entity_id
        self._set_reader_state("NODE", entity_name, f"实体 ID: {entity_id[:12]} · 正在收集关联记忆")

        self.entity_info.setText(
            f'<span style="color:{C["blue"]};font-size:16px;font-weight:bold;">'
            f'{entity_name}</span><br>'
            f'<span style="color:{C["subtext0"]};font-size:12px;">ID: {entity_id[:12]}</span>'
        )
        self._del_entity_btn.setEnabled(True)

        while self.memory_layout.count():
            child = self.memory_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        mem_ids = self.bridge.get_related_memories(entity_name)
        self._related_memories = []

        for mid in mem_ids:
            mem = self.bridge.get_memory(mid)
            if mem:
                self._related_memories.append(mem)

        self.related_label.setVisible(True)
        self.related_label.setText(f"关联记忆 ({len(self._related_memories)})")
        self._update_summary()

        if self._related_memories:
            self.detail.setVisible(True)
            self.detail.show_memory(self._related_memories[0])
            first = self._related_memories[0]
            self._set_reader_state("NODE", entity_name, f"{len(self._related_memories)} 条关联记忆 · 首条来自 {first.project or '(通用)'}")

            for mem in self._related_memories:
                card = MemoryCard(mem)
                card.clicked.connect(self._on_memory_card_click)
                self.memory_layout.addWidget(card)
            self.memory_layout.addStretch()
        else:
            self.detail.setVisible(False)
            no_mem = QLabel("暂无关联记忆")
            no_mem.setStyleSheet(f"color: {C['overlay0']}; font-size: 12px; padding: 8px;")
            self.memory_layout.addWidget(no_mem)
            self._set_reader_state("NODE", entity_name, "当前节点暂无关联记忆")

        self._highlight_node(entity_id)

    def _add_entity_dialog(self):
        from ..theme import lineedit_style, primary_btn_style as _p_btn
        dialog = QDialog(self)
        dialog.setWindowTitle("添加实体")
        dialog.setMinimumWidth(400)
        dialog.setStyleSheet(f"background: {C['base']}; color: {C['text']};")

        form = QFormLayout(dialog)
        form.setSpacing(12)

        name_edit = QLineEdit()
        name_edit.setStyleSheet(lineedit_style())
        name_edit.setPlaceholderText("输入实体名称")
        form.addRow("名称:", name_edit)

        type_combo = QComboBox()
        type_combo.addItems(["technology", "project", "component", "issue", "tool", "workflow", "person", "concept"])
        form.addRow("类型:", type_combo)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(secondary_btn_style())
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("添加")
        ok_btn.setStyleSheet(_p_btn())
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)
        form.addRow(btn_layout)

        if dialog.exec_() == QDialog.Accepted:
            name = name_edit.text().strip()
            if not name:
                return
            entity_type = type_combo.currentText()
            self.bridge.add_entity(name, entity_type)
            self.refresh()

    def _add_relation_dialog(self):
        from ..theme import lineedit_style, primary_btn_style as _p_btn
        entities = self.bridge.list_entities()
        if len(entities) < 2:
            QMessageBox.information(self, "提示", "至少需要 2 个实体才能创建关系")
            return

        dialog = QDialog(self)
        dialog.setWindowTitle("添加关系")
        dialog.setMinimumWidth(450)
        dialog.setStyleSheet(f"background: {C['base']}; color: {C['text']};")

        form = QFormLayout(dialog)
        form.setSpacing(12)

        source_combo = QComboBox()
        target_combo = QComboBox()
        for e in entities:
            source_combo.addItem(e.name, e.id)
            target_combo.addItem(e.name, e.id)

        if self._selected_entity:
            for i in range(source_combo.count()):
                if source_combo.itemData(i) == self._selected_entity:
                    source_combo.setCurrentIndex(i)
                    break

        form.addRow("源实体:", source_combo)
        form.addRow("目标实体:", target_combo)

        rel_edit = QLineEdit()
        rel_edit.setStyleSheet(lineedit_style())
        rel_edit.setPlaceholderText("例如: uses, depends_on, part_of")
        form.addRow("关系:", rel_edit)

        btn_layout = QHBoxLayout()
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(secondary_btn_style())
        cancel_btn.clicked.connect(dialog.reject)
        btn_layout.addWidget(cancel_btn)

        ok_btn = QPushButton("添加")
        ok_btn.setStyleSheet(_p_btn())
        ok_btn.clicked.connect(dialog.accept)
        btn_layout.addWidget(ok_btn)
        form.addRow(btn_layout)

        if dialog.exec_() == QDialog.Accepted:
            src_id = source_combo.currentData()
            tgt_id = target_combo.currentData()
            rel = rel_edit.text().strip()
            if not rel:
                return
            if src_id == tgt_id:
                QMessageBox.warning(self, "错误", "源实体和目标实体不能相同")
                return
            self.bridge.add_relation(src_id, tgt_id, rel)
            self.refresh()

    def _delete_selected_entity(self):
        if not self._selected_entity:
            return
        node = self.nodes.get(self._selected_entity)
        name = node.name if node else self._selected_entity[:12]
        reply = QMessageBox.question(
            self, "确认删除",
            f"确定要删除实体「{name}」及其所有关系吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.bridge.delete_entity(self._selected_entity)
            self._selected_entity = None
            self._del_entity_btn.setEnabled(False)
            self.refresh()
