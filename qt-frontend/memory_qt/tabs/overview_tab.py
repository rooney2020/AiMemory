"""总览仪表盘 — 统计卡片 + 图表分析 + 最近活动 + 详情面板"""

from collections import Counter
from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSplitter, QMessageBox, QTabWidget, QSizePolicy,
)
from PyQt5.QtCore import Qt

from ..constants import C
from ..data_bridge import DataBridge
from ..components.stat_card import StatCard
from ..components.memory_card import MemoryCard
from ..components.detail_panel import DetailPanel
from ..components.charts import (
    BarChart, TimelineChart, StrengthDistribution, EntityFrequencyChart,
)


class OverviewTab(QWidget):
    def __init__(self, bridge: DataBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._memories = []
        self._all_memories = []
        self._selected_memory_id: str | None = None
        self._build_ui()
        self.refresh()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        hero = QFrame()
        hero.setObjectName("overview_title_block")
        hero.setStyleSheet("QFrame { background: transparent; border: none; }")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(4, 2, 4, 0)
        hero_layout.setSpacing(0)

        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(0)

        self.hero_title = QLabel("AI Memory 工作台总览")
        self.hero_title.setObjectName("hero_title")
        hero_text.addWidget(self.hero_title)
        hero_layout.addLayout(hero_text, 1)

        layout.addWidget(hero)

        self.cards_layout = QHBoxLayout()
        self.cards_layout.setContentsMargins(0, 0, 0, 0)
        self.cards_layout.setSpacing(10)

        self.card_active = StatCard("活跃记忆", "0", "green")
        self.card_episodic = StatCard("会话摘要", "0", "teal")
        self.card_semantic = StatCard("笔记", "0", "blue")
        self.card_procedural = StatCard("偏好", "0", "mauve")
        self.card_core = StatCard("核心记忆", "0", "yellow")
        self.card_entities = StatCard("实体", "0", "peach")
        self.card_assets = StatCard("有效资产", "0", "green")

        cards = [
            self.card_active, self.card_episodic, self.card_semantic,
            self.card_procedural, self.card_core, self.card_entities,
            self.card_assets,
        ]
        for card in cards:
            card.setMinimumWidth(0)
            card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.cards_layout.addWidget(card, 1)

        layout.addLayout(self.cards_layout)

        self._sub_tabs = QTabWidget()
        self._sub_tabs.setTabPosition(QTabWidget.North)
        self._sub_tabs.setDocumentMode(True)
        self._sub_tabs.setStyleSheet(
            "QTabWidget::pane { border: none; top: 0px; }"
            "QTabBar { border: none; qproperty-drawBase: 0; }"
        )

        self._build_recent_tab()
        self._build_analytics_tab()

        layout.addWidget(self._sub_tabs, 1)

    def _build_recent_tab(self):
        widget = QWidget()
        main_layout = QVBoxLayout(widget)
        main_layout.setContentsMargins(0, 4, 0, 0)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_layout.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        self.recent_container = QWidget()
        self.recent_layout = QVBoxLayout(self.recent_container)
        self.recent_layout.setContentsMargins(0, 0, 0, 0)
        self.recent_layout.setSpacing(8)
        scroll.setWidget(self.recent_container)
        left_layout.addWidget(scroll)

        self.detail = DetailPanel(show_actions=True)
        self.detail.show_placeholder("点击左侧记忆卡片查看详情")
        self.detail.edit_requested.connect(self._on_edit)
        self.detail.delete_requested.connect(self._on_delete)

        splitter.addWidget(left_widget)
        splitter.addWidget(self.detail)
        splitter.setSizes([360, 920])
        main_layout.addWidget(splitter, 1)

        self._sub_tabs.addTab(widget, "最近活动")

    def _build_analytics_tab(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 4, 0, 0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        container = QWidget()
        self._analytics_layout = QVBoxLayout(container)
        self._analytics_layout.setContentsMargins(0, 0, 0, 0)
        self._analytics_layout.setSpacing(10)

        row1 = QHBoxLayout()
        row1.setSpacing(12)
        row1.setAlignment(Qt.AlignTop)
        self._timeline_chart = TimelineChart("记忆创建时间线")
        self._strength_chart = StrengthDistribution("强度 × 时间分布")
        row1.addWidget(self._timeline_chart)
        row1.addWidget(self._strength_chart)
        self._analytics_layout.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(12)
        row2.setAlignment(Qt.AlignTop)
        self._project_chart = BarChart("项目活跃度")
        self._entity_chart = EntityFrequencyChart("实体关联频率 TOP 15")
        row2.addWidget(self._project_chart)
        row2.addWidget(self._entity_chart)
        self._analytics_layout.addLayout(row2)

        self._analytics_layout.addStretch()
        scroll.setWidget(container)
        layout.addWidget(scroll)

        self._sub_tabs.addTab(widget, "数据分析")

    def refresh_style(self):
        for card in [
            self.card_active, self.card_episodic, self.card_semantic,
            self.card_procedural, self.card_core, self.card_entities,
            self.card_assets,
        ]:
            card.refresh_style()
        self.detail.refresh_style()

    def refresh(self):
        stats = self.bridge.get_stats()
        self.card_active.set_value(stats["active"])
        self.card_episodic.set_value(stats["episodic"])
        self.card_semantic.set_value(stats["semantic"])
        self.card_procedural.set_value(stats["procedural"])
        self.card_core.set_value(stats["core"])
        self.card_entities.set_value(stats["entities"])
        self.card_assets.set_value(stats["assets_valid"])

        while self.recent_layout.count():
            child = self.recent_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self._memories = self.bridge.list_memories(limit=15)
        for mem in self._memories:
            card = MemoryCard(mem)
            card.clicked.connect(self._on_card_click)
            self.recent_layout.addWidget(card)
            card.set_selected(mem.id == self._selected_memory_id)
        self.recent_layout.addStretch()

        self._refresh_analytics()

    def _refresh_analytics(self):
        self._all_memories = self.bridge.list_memories()

        self._timeline_chart.set_data_from_memories(self._all_memories, group_by="month")
        self._strength_chart.set_data_from_memories(self._all_memories)
        row1_height = max(self._timeline_chart.height(), self._strength_chart.height())
        self._timeline_chart.setFixedHeight(row1_height)
        self._strength_chart.setFixedHeight(row1_height)

        project_counts = Counter(m.project or "(通用)" for m in self._all_memories)
        proj_data = [
            (proj, count, "green") for proj, count in project_counts.most_common(15)
        ]
        self._project_chart.set_data(proj_data)

        self._entity_chart.set_data_from_memories(self._all_memories)
        row2_height = max(self._project_chart.height(), self._entity_chart.height())
        self._project_chart.setFixedHeight(row2_height)
        self._entity_chart.setFixedHeight(row2_height)

    def _on_card_click(self, mem_id: str):
        self._selected_memory_id = mem_id
        for index in range(self.recent_layout.count()):
            item = self.recent_layout.itemAt(index)
            widget = item.widget() if item else None
            if isinstance(widget, MemoryCard):
                widget.set_selected(widget.memory_id == mem_id)
        for mem in self._memories:
            if mem.id == mem_id:
                self.detail.show_memory(mem)
                break

    def _on_edit(self, mem_id: str):
        from .procedural_tab import EditDialog
        from PyQt5.QtWidgets import QDialog
        mem = self.bridge.get_memory(mem_id)
        if not mem:
            return
        dialog = EditDialog(mem, self)
        if dialog.exec_() == QDialog.Accepted:
            new_summary = dialog.summary_edit.text().strip()
            new_content = dialog.content_edit.toPlainText().strip()
            new_strength = dialog.strength_slider.value() / 10.0
            if new_content:
                self.bridge.update_memory(mem_id, content=new_content, summary=new_summary or None, strength=new_strength)
                self.refresh()

    def _on_delete(self, mem_id: str):
        reply = QMessageBox.question(
            self, "确认归档",
            "确定要归档这条记忆吗？\n（归档后不会出现在列表和搜索中，但数据保留）",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.bridge.update_memory(mem_id, status="archived")
            self.detail.show_placeholder("记忆已归档")
            self.refresh()
