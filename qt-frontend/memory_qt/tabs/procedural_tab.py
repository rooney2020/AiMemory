"""程序偏好 — 偏好/规则列表 + 详情 + 编辑/删除"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSplitter, QMessageBox, QDialog, QTextEdit,
    QPushButton, QLineEdit, QSlider, QSizePolicy,
)
from PyQt5.QtCore import Qt

from ..constants import C
from ..theme import secondary_btn_style, primary_btn_style, text_edit_style, lineedit_style
from ..data_bridge import DataBridge
from ..components.memory_card import MemoryCard
from ..components.detail_panel import DetailPanel


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


class EditDialog(QDialog):
    def __init__(self, mem, parent=None):
        super().__init__(parent)
        self.setWindowTitle("编辑记忆")
        self.setMinimumSize(600, 500)
        self.setStyleSheet(
            f"QDialog {{ background: {_rgba(C['base'], 0.98)}; color: {C['text']}; border: 1px solid {_rgba(C['surface2'], 0.45)}; border-radius: 24px; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        title = QLabel("规则编辑")
        title.setStyleSheet(f"color: {C['text']}; font-size: 20px; font-weight: 800;")
        layout.addWidget(title)

        hint = QLabel("保持摘要简洁、内容明确，强度用于控制偏好或规则在系统中的稳定性。")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px;")
        layout.addWidget(hint)

        summary_label = QLabel("摘要")
        summary_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; font-weight: 700;")
        layout.addWidget(summary_label)

        self.summary_edit = QLineEdit(mem.summary or "")
        self.summary_edit.setStyleSheet(lineedit_style())
        layout.addWidget(self.summary_edit)

        content_label = QLabel("内容")
        content_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; font-weight: 700;")
        layout.addWidget(content_label)

        self.content_edit = QTextEdit()
        self.content_edit.setPlainText(mem.content)
        self.content_edit.setStyleSheet(text_edit_style())
        layout.addWidget(self.content_edit, 1)

        strength_row = QHBoxLayout()
        strength_label = QLabel("强度")
        strength_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; font-weight: 700;")
        strength_row.addWidget(strength_label)

        self.strength_slider = QSlider(Qt.Horizontal)
        self.strength_slider.setRange(0, 100)
        self.strength_slider.setValue(int(mem.strength * 10))
        self.strength_slider.setStyleSheet(f"""
            QSlider::groove:horizontal {{
                background: {_rgba(C['surface0'], 0.92)}; height: 6px; border-radius: 3px;
            }}
            QSlider::handle:horizontal {{
                background: {C['blue']}; width: 16px; height: 16px;
                margin: -5px 0; border-radius: 8px;
            }}
            QSlider::sub-page:horizontal {{
                background: {C['blue']}; border-radius: 3px;
            }}
        """)
        strength_row.addWidget(self.strength_slider, 1)

        self.strength_value_label = QLabel(f"{mem.strength:.1f}")
        self.strength_value_label.setFixedWidth(40)
        self.strength_value_label.setAlignment(Qt.AlignCenter)
        self.strength_value_label.setStyleSheet(
            f"color: {C['text']}; font-size: 13px; font-weight: 800;"
        )
        strength_row.addWidget(self.strength_value_label)
        self.strength_slider.valueChanged.connect(
            lambda v: self.strength_value_label.setText(f"{v / 10:.1f}")
        )
        layout.addLayout(strength_row)

        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(secondary_btn_style())
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        save_btn = QPushButton("保存")
        save_btn.setStyleSheet(primary_btn_style())
        save_btn.clicked.connect(self.accept)
        btn_layout.addWidget(save_btn)

        layout.addLayout(btn_layout)


class ProceduralTab(QWidget):
    def __init__(self, bridge: DataBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._memories = []
        self._batch_mode = False
        self._selected_ids: set[str] = set()
        self._cards: list[MemoryCard] = []
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

        self._hero_kicker = QLabel("PROCEDURAL / RULES")
        self._hero_kicker.setVisible(False)
        hero_text.addWidget(self._hero_kicker, 0, Qt.AlignLeft)

        self._header = QLabel("偏好与执行规则")
        hero_text.addWidget(self._header)

        self._hero_desc = QLabel("集中维护稳定偏好、长期规则和执行约束，右侧可直接展开详情或进入编辑状态。")
        self._hero_desc.setWordWrap(True)
        self._hero_desc.setVisible(False)
        hero_text.addWidget(self._hero_desc)
        hero_text.addStretch(1)
        hero_layout.addLayout(hero_text, 1)

        hero_side = QVBoxLayout()
        hero_side.setContentsMargins(0, 0, 0, 0)
        hero_side.setSpacing(10)

        self._status_label = QLabel("核心偏好（≥5.0）永不衰减")
        hero_side.addWidget(self._status_label, 0, Qt.AlignRight)

        self._batch_btn = QPushButton("批量操作")
        self._batch_btn.setFixedHeight(38)
        self._batch_btn.clicked.connect(self._toggle_batch_mode)
        hero_side.addWidget(self._batch_btn, 0, Qt.AlignRight)

        metrics_row = QHBoxLayout()
        metrics_row.setContentsMargins(0, 0, 0, 0)
        metrics_row.setSpacing(10)
        metrics_row.addWidget(self._build_metric_card("items", "规则数", "mauve"))
        metrics_row.addWidget(self._build_metric_card("core", "核心规则", "blue"))
        metrics_row.addWidget(self._build_metric_card("selected", "已选中", "yellow"))
        hero_side.addLayout(metrics_row)
        hero_layout.addLayout(hero_side)

        layout.addWidget(hero)
        hero.hide()

        self.detail = DetailPanel(show_actions=True, embed_buttons=False)
        self.detail.show_placeholder("点击左侧偏好查看详情")
        self.detail.edit_requested.connect(self._on_edit)
        self.detail.delete_requested.connect(self._on_delete)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_widget = QFrame()
        self._left_panel = left_widget
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        self._queue_kicker = QLabel("RULE STREAM")
        self._queue_kicker.setVisible(False)
        left_layout.addWidget(self._queue_kicker)

        self._queue_title = QLabel("规则列表")
        left_layout.addWidget(self._queue_title)

        self._queue_hint = QLabel("这里按强度从高到低排列，适合先看最稳定的偏好和约束。")
        self._queue_hint.setWordWrap(True)
        left_layout.addWidget(self._queue_hint)

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

        self._detail_title = QLabel("规则详情")
        detail_header_layout.addWidget(self._detail_title)

        self._detail_hint = QLabel("点击左侧规则查看详细内容")
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

        from ..components.batch_bar import BatchActionBar
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
            f"color: {C['mauve']}; font-size: 11px; font-weight: 800; background: {_rgba(C['mauve'], 0.14)}; border: 1px solid {_rgba(C['mauve'], 0.22)}; border-radius: 999px; padding: 5px 10px;"
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
        self._queue_kicker.setStyleSheet(f"color: {C['blue']}; font-size: 11px; font-weight: 800; background: transparent; border: none;")
        self._queue_title.setStyleSheet(f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;")
        self._queue_hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        self._right_panel.setStyleSheet(self._panel_style())
        self._detail_header.setStyleSheet(self._sub_panel_style())
        self._detail_kicker.setStyleSheet(f"color: {C['lavender']}; font-size: 11px; font-weight: 800; background: transparent; border: none;")
        self._detail_title.setStyleSheet(f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;")
        self._detail_hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")

    def _update_summary(self):
        core_count = len([mem for mem in self._memories if mem.strength >= 5.0])
        self._metric_values["items"][2].setText(str(len(self._memories)))
        self._metric_values["core"][2].setText(str(core_count))
        self._metric_values["selected"][2].setText(str(len(self._selected_ids)))

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
        self._queue_hint.setText("批量模式已开启，可勾选多条规则统一归档或打标签。" if self._batch_mode else "这里按强度从高到低排列，适合先看最稳定的偏好和约束。")
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

    def refresh(self):
        self._cards.clear()
        while self.list_layout.count():
            child = self.list_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self._memories = self.bridge.list_memories(types=["procedural"])
        self._memories.sort(key=lambda m: m.strength, reverse=True)

        for mem in self._memories:
            card = MemoryCard(mem)
            card.clicked.connect(self._on_card_click)
            card.selection_changed.connect(self._on_selection_changed)
            if self._batch_mode:
                card.set_selectable(True)
            self._cards.append(card)
            self.list_layout.addWidget(card)

        self.list_layout.addStretch()
        self._update_summary()

    def _on_card_click(self, mem_id: str):
        for mem in self._memories:
            if mem.id == mem_id:
                self.detail.show_memory(mem)
                self._detail_title.setText(mem.summary or "规则详情")
                self._detail_hint.setText(f"强度: {mem.strength:.1f} · 项目: {mem.project or '(通用)'}")
                break

    def _on_edit(self, mem_id: str):
        mem = None
        for m in self._memories:
            if m.id == mem_id:
                mem = m
                break
        if not mem:
            return

        dialog = EditDialog(mem, self)
        if dialog.exec_() == QDialog.Accepted:
            new_summary = dialog.summary_edit.text().strip()
            new_content = dialog.content_edit.toPlainText().strip()
            new_strength = dialog.strength_slider.value() / 10.0
            if new_content:
                self.bridge.update_memory(
                    mem_id,
                    content=new_content,
                    summary=new_summary or None,
                    strength=new_strength,
                )
                self.refresh()
                for m in self._memories:
                    if m.id == mem_id:
                        self.detail.show_memory(m)
                        break

    def _on_delete(self, mem_id: str):
        reply = QMessageBox.question(
            self, "确认删除",
            "确定要删除这条记忆吗？\n（实际执行归档操作，不会永久删除）",
            QMessageBox.Yes | QMessageBox.No,
            QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.bridge.update_memory(mem_id, status="archived")
            self.detail.show_placeholder("记忆已归档")
            self.refresh()
