"""资产管理 — 资产卡片列表 + 详情面板"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QLineEdit, QScrollArea, QFrame, QSplitter, QSizePolicy, QApplication,
)
from PyQt5.QtCore import Qt, QTimer, QEvent
import subprocess
import os

from PyQt5.QtGui import QFont

from ..constants import C
from ..theme import lineedit_style, primary_btn_style, secondary_btn_style
from ..data_bridge import DataBridge


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


class AssetCard(QFrame):
    def __init__(self, asset, parent=None):
        super().__init__(parent)
        self.asset = asset
        self._selected = False
        self.setMinimumWidth(0)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._build_ui()
        self._apply_style()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 10, 14, 10)
        layout.setSpacing(4)

        top_row = QHBoxLayout()
        top_row.setSpacing(8)

        self.name_label = QLabel(self.asset.name)
        self.name_label.setFont(QFont("", 13, QFont.Bold))
        self.name_label.setMinimumWidth(0)
        self.name_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        top_row.addWidget(self.name_label, 1)

        self.type_badge = QLabel(self.asset.type.value)
        self.type_badge.setFixedHeight(20)
        top_row.addWidget(self.type_badge)

        self.status_badge = QLabel("有效" if self.asset.valid else "失效")
        self.status_badge.setFixedHeight(20)
        top_row.addWidget(self.status_badge)

        layout.addLayout(top_row)

        if self.asset.description:
            self.desc_label = QLabel()
            self.desc_label.setWordWrap(False)
            self.desc_label.setMinimumWidth(0)
            self.desc_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            self.desc_label.setToolTip(self.asset.description)
            self.desc_label.setText(self._elide_text(self.asset.description, 1))
            layout.addWidget(self.desc_label)
        else:
            self.desc_label = None

        if self.asset.tags:
            tags_text = " ".join(f"#{t}" for t in self.asset.tags[:6])
            self.tags_label = QLabel(tags_text)
            self.tags_label.setMinimumWidth(0)
            self.tags_label.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            layout.addWidget(self.tags_label)
        else:
            self.tags_label = None

        self.setCursor(Qt.PointingHandCursor)
        self.setFixedHeight(84 if self.asset.description else 65)

    def _elide_text(self, text: str, max_lines: int) -> str:
        metrics = self.desc_label.fontMetrics() if self.desc_label else self.fontMetrics()
        width = self.desc_label.width() if self.desc_label and self.desc_label.width() > 0 else self.width() - 28
        width = max(180, width)
        remaining = " ".join(text.split())
        lines = []

        for index in range(max_lines):
            if not remaining:
                break
            if index == max_lines - 1:
                lines.append(metrics.elidedText(remaining, Qt.ElideRight, width))
                break

            current = ""
            for char in remaining:
                if metrics.horizontalAdvance(current + char) > width:
                    break
                current += char
            if not current:
                current = remaining[0]
            lines.append(current.rstrip())
            remaining = remaining[len(current):].lstrip()

        return "\n".join(lines)

    def _apply_style(self):
        border_color = _rgba(C['blue'], 0.8) if self._selected else _rgba(C['surface2'], 0.38)
        bg = _rgba(C['surface0'], 0.92) if self._selected else _rgba(C['base'], 0.96)
        self.setStyleSheet(f"""
            AssetCard {{
                background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                    stop:0 {bg}, stop:1 {_rgba(C['surface1'], 0.96) if self._selected else _rgba(C['surface0'], 0.92)});
                border: 1px solid {border_color};
                border-radius: 18px;
            }}
            AssetCard:hover {{ border-color: {_rgba(C['blue'], 0.62)}; }}
        """)
        self.name_label.setStyleSheet(f"color: {C['text']}; font-weight: 800; border: none; background: transparent;")

        type_colors = {
            "app": C['blue'], "tool": C['green'], "script": C['peach'],
            "data": C['lavender'], "decompile": C['mauve'],
        }
        tc = type_colors.get(self.asset.type.value, C['overlay1'])
        self.type_badge.setStyleSheet(f"""
            background: {_rgba(tc, 0.14)}; color: {tc};
            border: 1px solid {_rgba(tc, 0.24)}; border-radius: 999px; font-size: 11px; font-weight: 800;
            padding: 2px 8px; border-width: 1px;
        """)

        sc = C['green'] if self.asset.valid else C['red']
        self.status_badge.setStyleSheet(f"""
            background: {_rgba(sc, 0.14)}; color: {sc};
            border: 1px solid {_rgba(sc, 0.24)}; border-radius: 999px; font-size: 11px; font-weight: 800;
            padding: 2px 8px; border-width: 1px;
        """)

        if self.desc_label:
            self.desc_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; border: none; background: transparent;")
            self.desc_label.setMaximumHeight(self.desc_label.fontMetrics().lineSpacing() + 2)
        if self.tags_label:
            self.tags_label.setStyleSheet(f"color: {C['overlay1']}; font-size: 11px; border: none; background: transparent;")

    def set_selected(self, selected):
        self._selected = selected
        self._apply_style()

    def refresh_style(self):
        self._apply_style()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.desc_label:
            self.desc_label.setText(self._elide_text(self.desc_label.toolTip(), 1))

    def mousePressEvent(self, event):
        super().mousePressEvent(event)
        p = self.parent()
        while p and not isinstance(p, AssetTab):
            p = p.parent()
        if p:
            p._select_asset(self)


class AssetTab(QWidget):
    def __init__(self, bridge: DataBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._assets = []
        self._cards = []
        self._selected_card = None
        self._metric_values = {}
        self._last_validation_summary = ""
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

        self._hero_kicker = QLabel("ASSET / REUSE")
        self._hero_kicker.setVisible(False)
        hero_text.addWidget(self._hero_kicker, 0, Qt.AlignLeft)

        self._header = QLabel("资产复用库")
        hero_text.addWidget(self._header)

        self._hero_desc = QLabel("管理可复用的应用、工具、脚本和文档资产，左侧检索，右侧聚焦验证、打开与追溯。")
        self._hero_desc.setWordWrap(True)
        self._hero_desc.setVisible(False)
        hero_text.addWidget(self._hero_desc)
        hero_text.addStretch(1)
        hero_layout.addLayout(hero_text, 1)

        hero_side = QVBoxLayout()
        hero_side.setContentsMargins(0, 0, 0, 0)
        hero_side.setSpacing(10)

        self._status_label = QLabel("等待加载资产")
        hero_side.addWidget(self._status_label, 0, Qt.AlignRight)

        metrics_row = QHBoxLayout()
        metrics_row.setContentsMargins(0, 0, 0, 0)
        metrics_row.setSpacing(10)
        metrics_row.addWidget(self._build_metric_card("total", "资产数", "blue"))
        metrics_row.addWidget(self._build_metric_card("valid", "有效", "green"))
        metrics_row.addWidget(self._build_metric_card("invalid", "失效", "red"))
        hero_side.addLayout(metrics_row)
        hero_layout.addLayout(hero_side)

        layout.addWidget(hero)
        hero.hide()

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_widget = QFrame()
        self._left_panel = left_widget
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        self._queue_kicker = QLabel("ASSET STREAM")
        self._queue_kicker.setVisible(False)
        left_layout.addWidget(self._queue_kicker)

        self._queue_title = QLabel("资产列表")
        left_layout.addWidget(self._queue_title)

        self._queue_hint = QLabel("输入关键词后直接筛选资产名称、简介或标签，左侧列表保留当前结果流。")
        self._queue_hint.setWordWrap(True)
        left_layout.addWidget(self._queue_hint)

        search_row = QHBoxLayout()
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索资产...")
        self.search_input.setFixedHeight(36)
        self.search_input.returnPressed.connect(self.refresh)
        search_row.addWidget(self.search_input)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setFixedHeight(36)
        self.refresh_btn.clicked.connect(self.refresh)
        search_row.addWidget(self.refresh_btn)
        left_layout.addLayout(search_row)

        self.validate_all_btn = QPushButton("验证全部资产")
        self.validate_all_btn.setFixedHeight(34)
        self.validate_all_btn.setToolTip("验证当前范围内的全部资产；未搜索时即为全部资产")
        self.validate_all_btn.clicked.connect(self._validate_all_assets)

        scroll = QScrollArea()
        self._list_scroll = scroll
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setViewportMargins(0, 0, 0, 0)
        scroll.viewport().installEventFilter(self)
        scroll.setStyleSheet(f"""
            QScrollArea {{ background: transparent; border: none; }}
            QWidget#asset_list_container {{ background: transparent; }}
        """)

        self.list_container = QWidget()
        self.list_container.setObjectName("asset_list_container")
        self.list_layout = QVBoxLayout(self.list_container)
        self.list_layout.setContentsMargins(0, 4, 10, 4)
        self.list_layout.setSpacing(8)
        self.list_layout.addStretch()
        scroll.setWidget(self.list_container)
        left_layout.addWidget(scroll, 1)

        splitter.addWidget(left_widget)

        right_widget = QFrame()
        self._right_panel = right_widget
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(16, 16, 16, 16)
        right_layout.setSpacing(12)

        detail_header = QFrame()
        self._detail_header = detail_header
        detail_header_layout = QVBoxLayout(detail_header)
        detail_header_layout.setContentsMargins(16, 14, 16, 14)
        detail_header_layout.setSpacing(8)

        self._detail_kicker = QLabel("DETAIL CANVAS")
        self._detail_kicker.setVisible(False)
        detail_header_layout.addWidget(self._detail_kicker, 0, Qt.AlignLeft)

        self._detail_hint = QLabel("选择左侧资产查看详情、验证状态和来源信息")
        self._detail_hint.setWordWrap(True)
        detail_header_layout.addWidget(self._detail_hint)

        btn_layout = QHBoxLayout()
        self.validate_btn = QPushButton("验证有效性")
        self.validate_btn.setToolTip("检查资产路径是否存在、源文件是否变更")
        self.validate_btn.setStyleSheet(primary_btn_style())
        self.validate_btn.setFixedHeight(34)
        self.validate_btn.clicked.connect(self._validate_selected)
        self.validate_btn.setEnabled(False)
        btn_layout.addWidget(self.validate_btn)

        self.open_btn = QPushButton("打开目录")
        self.open_btn.setStyleSheet(secondary_btn_style())
        self.open_btn.setFixedHeight(34)
        self.open_btn.clicked.connect(self._open_directory)
        self.open_btn.setEnabled(False)
        btn_layout.addWidget(self.open_btn)

        self.delete_btn = QPushButton("删除记录")
        self.delete_btn.setToolTip("从数据库中删除该资产记录（不操作实际文件）")
        self.delete_btn.setStyleSheet(f"""
            QPushButton {{
                background: {C['red']}; color: {C['crust']};
                border: none; border-radius: 8px;
                padding: 8px 16px; font-size: 13px; font-weight: bold;
            }}
            QPushButton:hover {{ background: {C['maroon']}; }}
        """)
        self.delete_btn.setFixedHeight(34)
        self.delete_btn.clicked.connect(self._delete_selected)
        self.delete_btn.setEnabled(False)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addStretch()
        detail_header_layout.addLayout(btn_layout)

        right_layout.addWidget(detail_header)

        self.detail_title = QLabel("选择一个资产查看详情")
        self.detail_title.setObjectName("detail_title")
        self.detail_title.setWordWrap(True)
        right_layout.addWidget(self.detail_title)

        self.detail_content = QLabel("")
        self.detail_content.setObjectName("detail_content")
        self.detail_content.setWordWrap(True)
        self.detail_content.setAlignment(Qt.AlignTop)
        self.detail_content.setTextInteractionFlags(Qt.TextSelectableByMouse)
        self.detail_content.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        right_layout.addWidget(self.detail_content, 1)

        splitter.addWidget(right_widget)
        splitter.setSizes([420, 820])
        layout.addWidget(splitter, 1)
        self._apply_shell_styles()

    def topbar_context_widgets(self):
        summary_widgets = [self._status_label]
        summary_widgets.extend(frame for frame, *_ in self._metric_values.values())
        return summary_widgets, [self.validate_all_btn]

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
        for frame, label, value, color_key in self._metric_values.values():
            frame.setStyleSheet(self._sub_panel_style())
            label.setStyleSheet(f"color: {C['subtext0']}; font-size: 11px; font-weight: 700; background: transparent; border: none;")
            value.setStyleSheet(f"color: {C[color_key]}; font-size: 22px; font-weight: 800; background: transparent; border: none;")
        self._left_panel.setStyleSheet(self._panel_style())
        self._queue_kicker.setStyleSheet(f"color: {C['teal']}; font-size: 11px; font-weight: 800; background: transparent; border: none;")
        self._queue_title.setStyleSheet(f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;")
        self._queue_hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        self.search_input.setStyleSheet(lineedit_style())
        self.refresh_btn.setStyleSheet(secondary_btn_style())
        self.validate_all_btn.setStyleSheet(primary_btn_style())
        self._right_panel.setStyleSheet(self._panel_style())
        self._detail_header.setStyleSheet(self._sub_panel_style())
        self._detail_kicker.setStyleSheet(f"color: {C['lavender']}; font-size: 11px; font-weight: 800; background: transparent; border: none;")
        self._detail_hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        self.validate_btn.setStyleSheet(primary_btn_style())
        self.open_btn.setStyleSheet(secondary_btn_style())
        self.delete_btn.setStyleSheet(
            f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['red']}, stop:1 {C['maroon']}); color: white; border: 1px solid transparent; border-radius: 14px; padding: 8px 16px; font-size: 13px; font-weight: 800; }}"
            f"QPushButton:hover {{ border-color: {_rgba(C['red'], 0.35)}; }}"
        )
        self.detail_title.setStyleSheet(f"color: {C['text']}; font-size: 20px; font-weight: 800; background: transparent; border: none;")
        self.detail_content.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 13px; line-height: 1.7; background: {_rgba(C['surface0'], 0.72)}; border: 1px solid {_rgba(C['surface2'], 0.28)}; border-radius: 18px; padding: 18px;"
        )

    def _update_summary(self):
        total = len(self._assets)
        valid = len([asset for asset in self._assets if asset.valid])
        invalid = total - valid
        self._metric_values["total"][2].setText(str(total))
        self._metric_values["valid"][2].setText(str(valid))
        self._metric_values["invalid"][2].setText(str(invalid))
        query = self.search_input.text().strip() or "全部资产"
        if self._last_validation_summary:
            self._status_label.setText(f"当前范围: {query} · {total} 条记录 · {self._last_validation_summary}")
        else:
            self._status_label.setText(f"当前范围: {query} · {total} 条记录")

    def refresh_style(self):
        self._apply_shell_styles()
        for card in self._cards:
            card.refresh_style()

    def refresh(self):
        query = self.search_input.text().strip() if self.search_input.text() else None
        self._assets = self.bridge.list_assets(valid_only=False)
        self._assets.sort(key=lambda a: a.created_at, reverse=True)
        if query:
            q = query.lower()
            self._assets = [
                a for a in self._assets
                if q in a.name.lower()
                or q in (a.description or "").lower()
                or q in " ".join(a.tags).lower()
            ]

        for card in self._cards:
            self.list_layout.removeWidget(card)
            card.deleteLater()
        self._cards.clear()
        self._selected_card = None

        stretch = self.list_layout.itemAt(self.list_layout.count() - 1)

        for asset in self._assets:
            card = AssetCard(asset, self.list_container)
            self.list_layout.insertWidget(self.list_layout.count() - 1, card)
            self._cards.append(card)

        if self._cards:
            self._select_asset(self._cards[0])
        else:
            self.detail_title.setText("未找到匹配资产")
            self.detail_content.setText("可调整关键词后重新搜索，或先刷新资产列表。")
            self._detail_hint.setText("当前没有可展示的资产详情")
            self.validate_btn.setEnabled(False)
            self.open_btn.setEnabled(False)
            self.delete_btn.setEnabled(False)

        QTimer.singleShot(0, self._sync_card_widths)
        self._update_summary()

    def _sync_card_widths(self):
        if not hasattr(self, "_list_scroll"):
            return

        margins = self.list_layout.contentsMargins()
        available_width = self._list_scroll.viewport().width() - margins.left() - margins.right()
        if available_width <= 0:
            return

        for card in self._cards:
            card.setFixedWidth(available_width)

    def eventFilter(self, watched, event):
        if hasattr(self, "_list_scroll") and watched is self._list_scroll.viewport() and event.type() == QEvent.Resize:
            QTimer.singleShot(0, self._sync_card_widths)
        return super().eventFilter(watched, event)

    def resizeEvent(self, event):
        super().resizeEvent(event)
        QTimer.singleShot(0, self._sync_card_widths)

    def _select_asset(self, card):
        if self._selected_card:
            self._selected_card.set_selected(False)
        card.set_selected(True)
        self._selected_card = card
        self.validate_btn.setEnabled(True)
        self.open_btn.setEnabled(True)
        self.delete_btn.setEnabled(True)
        self._show_detail(card.asset)

    def _show_detail(self, asset):
        self.detail_title.setText(asset.name)
        self._detail_hint.setText(f"类型: {asset.type.value} · 状态: {'有效' if asset.valid else '失效'}")

        size_str = "N/A"
        if asset.artifact_size:
            if asset.artifact_size < 1024:
                size_str = f"{asset.artifact_size} B"
            elif asset.artifact_size < 1048576:
                size_str = f"{asset.artifact_size / 1024:.0f} KB"
            else:
                size_str = f"{asset.artifact_size / 1048576:.1f} MB"

        lines = []
        lines.append(f"<b>类型：</b>{asset.type.value}")
        status_color = C['green'] if asset.valid else C['red']
        status_text = "有效" if asset.valid else "失效"
        lines.append(f"<b>状态：</b><span style='color: {status_color}'>{status_text}</span>")
        if asset.description:
            lines.append(f"<br><b>简介：</b>{asset.description}")
        lines.append(f"<br><b>路径：</b><code>{asset.artifact_path}</code>")
        lines.append(f"<b>大小：</b>{size_str}")
        if asset.tags:
            tags_html = " ".join(
                f'<span style="background: {C["surface1"]}; padding: 2px 6px; border-radius: 3px; font-size: 11px;">#{t}</span>'
                for t in asset.tags
            )
            lines.append(f"<br><b>标签：</b>{tags_html}")
        if asset.project:
            lines.append(f"<b>所属项目：</b>{asset.project}")
        if asset.tool_name:
            version = f" v{asset.tool_version}" if asset.tool_version else ""
            lines.append(f"<b>工具：</b>{asset.tool_name}{version}")
        lines.append(f"<b>使用次数：</b>{asset.use_count}")
        lines.append(f"<b>创建时间：</b>{asset.created_at.strftime('%Y-%m-%d %H:%M')}")
        if asset.last_used_at:
            lines.append(f"<b>最后使用：</b>{asset.last_used_at.strftime('%Y-%m-%d %H:%M')}")
        if not asset.valid and asset.invalid_reason:
            lines.append(f"<br><b>失效原因：</b><span style='color: {C['red']}'>{asset.invalid_reason}</span>")

        html = f"""
        <div style="color: {C['text']}; font-size: 13px; line-height: 2;">
            {'<br>'.join(lines)}
        </div>
        """
        self.detail_content.setText(html)

    def _validate_selected(self):
        if self._selected_card:
            asset = self._selected_card.asset
            self.bridge.validate_asset(asset.id)
            self._last_validation_summary = f"已验证 1 条 · {asset.name}"
            self.refresh()

    def _validate_all_assets(self):
        if not self._assets:
            self._last_validation_summary = "没有可验证的资产"
            self._update_summary()
            return

        self.validate_all_btn.setEnabled(False)
        self.validate_btn.setEnabled(False)
        self.open_btn.setEnabled(False)
        self.delete_btn.setEnabled(False)
        QApplication.processEvents()

        summary = self.bridge.validate_assets([asset.id for asset in self._assets])
        self._last_validation_summary = (
            f"已验证 {summary['total']} 条 · 有效 {summary['valid']} · 失效 {summary['invalid']}"
        )
        self.refresh()

    def _delete_selected(self):
        if self._selected_card:
            from PyQt5.QtWidgets import QDialog, QDialogButtonBox
            asset = self._selected_card.asset

            dlg = QDialog(self)
            dlg.setWindowTitle("删除资产记录")
            dlg.setFixedSize(400, 180)
            dlg.setStyleSheet(f"""
                QDialog {{
                    background: {C['base']};
                    border: 1px solid {C['surface1']};
                    border-radius: 12px;
                }}
            """)

            dlg_layout = QVBoxLayout(dlg)
            dlg_layout.setContentsMargins(24, 20, 24, 20)
            dlg_layout.setSpacing(16)

            title = QLabel("确认删除")
            title.setStyleSheet(f"color: {C['red']}; font-size: 16px; font-weight: bold;")
            dlg_layout.addWidget(title)

            name = asset.name
            msg = QLabel(f'从数据库中删除资产 "{name}" 吗？\n（不会删除实际文件）')
            msg.setWordWrap(True)
            msg.setStyleSheet(f"color: {C['text']}; font-size: 13px;")
            dlg_layout.addWidget(msg)

            dlg_layout.addStretch()

            btn_layout = QHBoxLayout()
            btn_layout.addStretch()

            cancel_btn = QPushButton("取消")
            cancel_btn.setStyleSheet(secondary_btn_style())
            cancel_btn.setFixedWidth(80)
            cancel_btn.clicked.connect(dlg.reject)
            btn_layout.addWidget(cancel_btn)

            confirm_btn = QPushButton("删除")
            confirm_btn.setStyleSheet(f"""
                QPushButton {{
                    background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
                        stop:0 {C['red']}, stop:1 {C['maroon']}); color: white;
                    border: 1px solid transparent; border-radius: 12px;
                    padding: 8px 16px; font-size: 13px; font-weight: 800;
                }}
                QPushButton:hover {{ border-color: {_rgba(C['red'], 0.35)}; }}
            """)
            confirm_btn.setFixedWidth(80)
            confirm_btn.clicked.connect(dlg.accept)
            btn_layout.addWidget(confirm_btn)

            dlg_layout.addLayout(btn_layout)

            if dlg.exec_() == QDialog.Accepted:
                self.bridge.delete_asset(asset.id)
                self.refresh()

    def _open_directory(self):
        if self._selected_card:
            path = self._selected_card.asset.artifact_path
            if os.path.exists(path):
                if os.path.isfile(path):
                    path = os.path.dirname(path)
                subprocess.Popen(["xdg-open", path])
