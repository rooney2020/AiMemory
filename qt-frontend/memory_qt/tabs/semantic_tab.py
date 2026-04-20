"""语义知识 — 按项目 tab 切换的知识库（卡片列表 + 详情）"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
    QScrollArea, QFrame, QMessageBox, QPushButton, QButtonGroup, QSizePolicy,
)
from PyQt5.QtCore import Qt

from ..constants import C
from ..theme import secondary_btn_style
from ..data_bridge import DataBridge
from ..components.memory_card import MemoryCard
from ..components.detail_panel import DetailPanel
from ..components.batch_bar import BatchActionBar


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


class SemanticTab(QWidget):
    def __init__(self, bridge: DataBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._memories = []
        self._all_memories = []
        self._batch_mode = False
        self._selected_ids: set[str] = set()
        self._cards: list[MemoryCard] = []
        self._current_project: str | None = None
        self._proj_buttons: dict[str, QPushButton] = {}
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

        self._hero_kicker = QLabel("SEMANTIC / KNOWLEDGE")
        self._hero_kicker.setVisible(False)
        hero_text.addWidget(self._hero_kicker, 0, Qt.AlignLeft)

        self._header = QLabel("知识笔记库")
        hero_text.addWidget(self._header)

        self._hero_desc = QLabel("按项目切换可复用知识项，适合在同一工作台里横向扫读概念、说明和事实记录。")
        self._hero_desc.setWordWrap(True)
        self._hero_desc.setVisible(False)
        hero_text.addWidget(self._hero_desc)
        hero_text.addStretch(1)
        hero_layout.addLayout(hero_text, 1)

        hero_side = QVBoxLayout()
        hero_side.setContentsMargins(0, 0, 0, 0)
        hero_side.setSpacing(10)

        self._status_label = QLabel("等待加载知识项")
        hero_side.addWidget(self._status_label, 0, Qt.AlignRight)

        self._batch_btn = QPushButton("批量操作")
        self._batch_btn.setFixedHeight(38)
        self._batch_btn.clicked.connect(self._toggle_batch_mode)
        hero_side.addWidget(self._batch_btn, 0, Qt.AlignRight)

        metrics_row = QHBoxLayout()
        metrics_row.setContentsMargins(0, 0, 0, 0)
        metrics_row.setSpacing(10)
        metrics_row.addWidget(self._build_metric_card("items", "笔记数", "blue"))
        metrics_row.addWidget(self._build_metric_card("projects", "项目组", "teal"))
        metrics_row.addWidget(self._build_metric_card("selected", "已选中", "yellow"))
        hero_side.addLayout(metrics_row)
        hero_layout.addLayout(hero_side)

        layout.addWidget(hero)
        hero.hide()

        self.detail = DetailPanel(show_actions=True, embed_buttons=False)
        self.detail.show_placeholder("点击左侧知识项查看详情")
        self.detail.edit_requested.connect(self._on_edit)
        self.detail.delete_requested.connect(self._on_delete)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_widget = QFrame()
        self._left_panel = left_widget
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        self._queue_kicker = QLabel("KNOWLEDGE STREAM")
        self._queue_kicker.setVisible(False)
        left_layout.addWidget(self._queue_kicker)

        self._queue_title = QLabel("项目知识流")
        left_layout.addWidget(self._queue_title)

        self._queue_hint = QLabel("上方项目条用于切换知识域，左侧卡片区保留当前项目下的笔记列表。")
        self._queue_hint.setWordWrap(True)
        left_layout.addWidget(self._queue_hint)

        proj_scroll = QScrollArea()
        proj_scroll.setWidgetResizable(True)
        proj_scroll.setFrameShape(QFrame.NoFrame)
        proj_scroll.setFixedHeight(44)
        proj_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        proj_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        proj_scroll.setStyleSheet("background: transparent; border: none;")
        self._proj_bar = QWidget()
        self._proj_flow = QHBoxLayout(self._proj_bar)
        self._proj_flow.setContentsMargins(0, 2, 0, 2)
        self._proj_flow.setSpacing(4)
        self._proj_btn_group = QButtonGroup(self)
        self._proj_btn_group.setExclusive(True)
        self._proj_btn_group.buttonClicked.connect(self._on_proj_btn_clicked)
        self._proj_flow.addStretch()
        proj_scroll.setWidget(self._proj_bar)
        left_layout.addWidget(proj_scroll)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        self.container = QWidget()
        self.list_layout = QVBoxLayout(self.container)
        self.list_layout.setContentsMargins(0, 0, 0, 0)
        self.list_layout.setSpacing(10)
        scroll.setWidget(self.container)
        left_layout.addWidget(scroll)

        right_widget = QFrame()
        self._right_panel = right_widget
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        detail_header = QFrame()
        self._detail_header = detail_header
        detail_header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        detail_header_layout = QVBoxLayout(detail_header)
        detail_header_layout.setContentsMargins(16, 14, 16, 14)
        detail_header_layout.setSpacing(8)

        self._detail_kicker = QLabel("DETAIL CANVAS")
        self._detail_kicker.setVisible(False)
        detail_header_layout.addWidget(self._detail_kicker, 0, Qt.AlignLeft)

        self._detail_title = QLabel("笔记详情")
        detail_header_layout.addWidget(self._detail_title)

        self._detail_hint = QLabel("点击左侧知识项查看详细内容")
        self._detail_hint.setWordWrap(True)
        detail_header_layout.addWidget(self._detail_hint)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)
        action_row.addStretch(1)
        for w in self.detail.get_action_widgets():
            action_row.addWidget(w)
        detail_header_layout.addLayout(action_row)

        right_layout.addWidget(detail_header)
        right_layout.addWidget(self.detail, 1)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([420, 820])
        layout.addWidget(splitter, 1)

        self._batch_bar = BatchActionBar(self)
        self._batch_bar.archive_requested.connect(self._batch_archive)
        self._batch_bar.tag_requested.connect(self._batch_tag)
        self._batch_bar.select_all_requested.connect(self._select_all)
        self._batch_bar.deselect_all_requested.connect(self._deselect_all)
        self._batch_bar.exit_requested.connect(self.exit_batch_mode)
        layout.addWidget(self._batch_bar)

        self._apply_shell_styles()

    def topbar_context_widgets(self):
        summary_widgets = [self._status_label]
        summary_widgets.extend(frame for frame, *_ in self._metric_values.values())
        return summary_widgets, [self._batch_btn]

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

    def _apply_shell_styles(self):
        self._hero_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        self._hero_kicker.setStyleSheet(
            f"color: {C['blue']}; font-size: 11px; font-weight: 800; background: {_rgba(C['blue'], 0.14)}; border: 1px solid {_rgba(C['blue'], 0.22)}; border-radius: 999px; padding: 5px 10px;"
        )
        self._header.setStyleSheet(f"color: {C['text']}; font-size: 24px; font-weight: 800;")
        self._hero_desc.setStyleSheet(f"color: {C['subtext0']}; font-size: 13px;")
        self._status_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; font-weight: 700;")
        self._batch_btn.setStyleSheet(secondary_btn_style())
        for frame, label, value, color_key in self._metric_values.values():
            frame.setStyleSheet(self._sub_panel_style())
            label.setStyleSheet(f"color: {C['subtext0']}; font-size: 11px; font-weight: 700; background: transparent; border: none;")
            value.setStyleSheet(f"color: {C[color_key]}; font-size: 22px; font-weight: 800; background: transparent; border: none;")
        self._left_panel.setStyleSheet(self._panel_style())
        self._queue_kicker.setStyleSheet(f"color: {C['teal']}; font-size: 11px; font-weight: 800; background: transparent; border: none;")
        self._queue_title.setStyleSheet(f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;")
        self._queue_hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        self._right_panel.setStyleSheet(self._panel_style())
        self._detail_header.setStyleSheet(self._sub_panel_style())
        self._detail_kicker.setStyleSheet(f"color: {C['lavender']}; font-size: 11px; font-weight: 800; background: transparent; border: none;")
        self._detail_title.setStyleSheet(f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;")
        self._detail_hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")

    def _update_summary(self):
        project_count = len({mem.project or "(通用)" for mem in self._all_memories})
        visible_count = len(self._memories)
        self._metric_values["items"][2].setText(str(visible_count))
        self._metric_values["projects"][2].setText(str(project_count))
        self._metric_values["selected"][2].setText(str(len(self._selected_ids)))
        current_project = self._current_project or "全部项目"
        self._status_label.setText(f"当前范围: {current_project} · {visible_count} 条笔记")

    def _proj_btn_style(self, selected: bool = False) -> str:
        if selected:
            return (
                f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['blue']}, stop:1 {C['teal']}); color: white; "
                f"border: none; border-radius: 14px; padding: 4px 12px; "
                f"font-size: 11px; font-weight: 800; }}"
            )
        return (
            f"QPushButton {{ background: {_rgba(C['base'], 0.94)}; color: {C['subtext0']}; "
            f"border: 1px solid {_rgba(C['surface2'], 0.4)}; border-radius: 14px; "
            f"padding: 4px 12px; font-size: 11px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {_rgba(C['surface0'], 0.72)}; color: {C['text']}; border-color: {_rgba(C['blue'], 0.42)}; }}"
        )

    def _rebuild_proj_buttons(self):
        for btn in list(self._proj_buttons.values()):
            self._proj_btn_group.removeButton(btn)
            btn.deleteLater()
        self._proj_buttons.clear()

        while self._proj_flow.count():
            item = self._proj_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        by_project: dict[str, int] = {}
        for mem in self._all_memories:
            proj = mem.project or "(通用)"
            by_project[proj] = by_project.get(proj, 0) + 1

        all_btn = QPushButton(f"全部 ({len(self._all_memories)})")
        all_btn.setCheckable(True)
        all_btn.setCursor(Qt.PointingHandCursor)
        all_btn.setProperty("proj_key", None)
        all_btn.setFixedHeight(24)
        all_btn.setStyleSheet(self._proj_btn_style(self._current_project is None))
        if self._current_project is None:
            all_btn.setChecked(True)
        self._proj_btn_group.addButton(all_btn)
        self._proj_flow.addWidget(all_btn)
        self._proj_buttons["__all__"] = all_btn

        for proj in sorted(by_project.keys()):
            count = by_project[proj]
            btn = QPushButton(f"{proj} ({count})")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("proj_key", proj)
            btn.setFixedHeight(24)
            is_sel = (self._current_project == proj)
            btn.setStyleSheet(self._proj_btn_style(is_sel))
            if is_sel:
                btn.setChecked(True)
            self._proj_btn_group.addButton(btn)
            self._proj_flow.addWidget(btn)
            self._proj_buttons[proj] = btn

        self._proj_flow.addStretch()
        self._update_summary()

    def _on_proj_btn_clicked(self, btn: QPushButton):
        proj = btn.property("proj_key")
        self._current_project = proj
        for key, b in self._proj_buttons.items():
            is_sel = (key == "__all__" and proj is None) or (key == proj)
            b.setStyleSheet(self._proj_btn_style(is_sel))
        self._populate_list()

    def _populate_list(self):
        self._cards.clear()
        while self.list_layout.count():
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        if self._current_project is None:
            mems = self._all_memories
        else:
            mems = [m for m in self._all_memories if (m.project or "(通用)") == self._current_project]

        self._memories = mems

        for mem in mems:
            card = MemoryCard(mem)
            card.clicked.connect(self._on_card_click)
            card.selection_changed.connect(self._on_selection_changed)
            if self._batch_mode:
                card.set_selectable(True)
            self._cards.append(card)
            self.list_layout.addWidget(card)

        self.list_layout.addStretch()

    def _toggle_batch_mode(self):
        self._batch_mode = not self._batch_mode
        self._selected_ids.clear()
        self._batch_bar.setVisible(self._batch_mode)
        self._batch_bar.update_selection(self._selected_ids)
        for card in self._cards:
            card.set_selectable(self._batch_mode)
        self.detail.export_btn.setVisible(not self._batch_mode)
        if hasattr(self.detail, 'edit_btn'):
            self.detail.edit_btn.setVisible(not self._batch_mode)
        if hasattr(self.detail, 'delete_btn'):
            self.detail.delete_btn.setVisible(not self._batch_mode)
        self._batch_btn.setVisible(not self._batch_mode)
        self._queue_hint.setText("批量模式已开启，可在当前项目下勾选多条笔记统一处理。" if self._batch_mode else "上方项目条用于切换知识域，左侧卡片区保留当前项目下的笔记列表。")
        self._update_summary()

    def exit_batch_mode(self):
        if self._batch_mode:
            self._toggle_batch_mode()

    def _on_selection_changed(self, mem_id: str, checked: bool):
        if checked:
            self._selected_ids.add(mem_id)
        else:
            self._selected_ids.discard(mem_id)
        self._batch_bar.update_selection(self._selected_ids)
        self._update_summary()

    def _select_all(self):
        for card in self._cards:
            card.set_checked(True)

    def _deselect_all(self):
        for card in self._cards:
            card.set_checked(False)

    def _batch_archive(self, ids: list[str]):
        self.bridge.batch_archive(ids)
        self.exit_batch_mode()
        self.refresh()

    def _batch_tag(self, ids: list[str], tag: str):
        self.bridge.batch_add_tag(ids, tag)
        self.exit_batch_mode()
        self.refresh()

    def refresh_style(self):
        self._apply_shell_styles()
        self._batch_bar.refresh_style()
        self.detail.refresh_style()
        for key, btn in self._proj_buttons.items():
            is_sel = (key == "__all__" and self._current_project is None) or (key == self._current_project)
            btn.setStyleSheet(self._proj_btn_style(is_sel))

    def refresh(self):
        self._all_memories = self.bridge.list_memories(types=["semantic"])
        self._rebuild_proj_buttons()
        self._populate_list()
        self._update_summary()

    def _on_card_click(self, mem_id: str):
        for mem in self._memories:
            if mem.id == mem_id:
                self.detail.show_memory(mem)
                self._detail_title.setText(mem.summary or "笔记详情")
                self._detail_hint.setText(f"项目: {mem.project or '(通用)'} · 强度: {mem.strength:.1f}")
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
            self, "确认归档", "确定要归档这条记忆吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.bridge.update_memory(mem_id, status="archived")
            self.detail.show_placeholder("记忆已归档")
            self.refresh()
