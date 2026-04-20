"""会话浏览 — 跨框架 AI 会话记录检测与查看"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QSplitter,
    QListWidget, QListWidgetItem, QScrollArea, QFrame,
    QPushButton, QLineEdit, QApplication, QSizePolicy,
    QButtonGroup, QTextBrowser, QToolButton, QMenu, QAction,
)
from PyQt5.QtCore import Qt, QTimer, QSize, pyqtSignal, QThread
from PyQt5.QtGui import QFont, QColor

from ..constants import C
from ..theme import (
    list_style, scrollbar_style, secondary_btn_style,
    lineedit_style,
)
from ..sessions.scanner import SessionScanner
from ..sessions.models import SessionSource, SessionInfo, FrameworkType
from ..sessions.bookmarks import BookmarkManager

from .session_workers import ScanWorker, FrameworkWarmupWorker, LoadWorker, MessageLoadWorker
from .session_renderers import (
    AutoHeightBrowser, split_thinking, render_markdown,
    highlight_search, make_dot_icon, SessionDelegate,
    MESSAGES_PER_PAGE, RENDER_BATCH_SIZE,
)


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


class SessionTab(QWidget):
    busy_changed = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.scanner = SessionScanner()
        self.bookmarks = BookmarkManager()
        self._sources: list[SessionSource] = []
        self._fw_groups: dict[str, list[SessionSource]] = {}
        self._sessions_cache: dict[str, list[SessionInfo]] = {}
        self._fw_latest_time: dict[str, object] = {}
        self._current_fw: str | None = None
        self._current_session: SessionInfo | None = None
        self._displayed_count = 0
        self._worker = None
        self._order_worker = None
        self._msg_worker = None
        self._active_workers: list[QThread] = []
        self._pending_render: list[int] = []
        self._render_target_end = 0
        self._load_more_btn = None
        self._load_request_token = 0
        self._render_request_token = 0
        self._pending_message_load: tuple[SessionInfo, int] | None = None
        self._visible_session_messages = []
        self._show_tool_messages = False
        self._fw_buttons: dict[str, QPushButton] = {}
        self._show_bookmarks_only = False
        self._compare_mode = False
        self._compare_sessions: list[SessionInfo] = []
        self._highlight_term: str = ""
        self._busy = False
        self._metric_values = {}
        self._build_ui()
        self._do_scan()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        hero = QFrame()
        self._hero_frame = hero
        hero.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        hero.setStyleSheet("QFrame { background: transparent; border: none; }")
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(4, 2, 4, 0)
        hero_layout.setSpacing(12)

        hero_top_row = QHBoxLayout()
        hero_top_row.setContentsMargins(0, 0, 0, 0)
        hero_top_row.setSpacing(16)

        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(6)

        self._hero_kicker = QLabel("SESSION / INTEL")
        self._hero_kicker.setVisible(False)
        hero_text.addWidget(self._hero_kicker, 0, Qt.AlignLeft)

        self._header = QLabel("会话情报中心")
        self._header.setObjectName("tab_header")
        self._header.setMinimumHeight(38)
        self._header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        hero_text.addWidget(self._header)

        self._hero_desc = QLabel("跨框架整理原始对话记录，按最近活跃排序，并支持内容级检索、收藏与对比阅读。")
        self._hero_desc.setWordWrap(True)
        self._hero_desc.setMinimumHeight(28)
        self._hero_desc.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self._hero_desc.setVisible(False)
        hero_text.addWidget(self._hero_desc)
        hero_text.addStretch(1)
        hero_top_row.addLayout(hero_text, 1)

        hero_side = QVBoxLayout()
        hero_side.setContentsMargins(0, 0, 0, 0)
        hero_side.setSpacing(10)

        self._status_label = QLabel("等待扫描")
        hero_side.addWidget(self._status_label, 0, Qt.AlignRight)

        actions_row = QHBoxLayout()
        actions_row.setContentsMargins(0, 0, 0, 0)
        actions_row.setSpacing(8)

        self._compare_btn = QPushButton("对比模式")
        self._compare_btn.setStyleSheet(
            f"QPushButton {{ background: {_rgba(C['base'], 0.96)}; color: {C['text']}; "
            f"border: 1px solid {_rgba(C['surface2'], 0.45)}; border-radius: 14px; "
            f"padding: 8px 16px; font-size: 13px; font-weight: 700; }}"
            f"QPushButton:hover {{ border-color: {_rgba(C['blue'], 0.48)}; background: {_rgba(C['surface0'], 0.72)}; }}"
            f"QPushButton:checked {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['blue']}, stop:1 {C['teal']}); "
            f"color: white; border-color: transparent; }}"
        )
        self._compare_btn.setCheckable(True)
        self._compare_btn.setFixedHeight(38)
        self._compare_btn.toggled.connect(self._on_compare_mode_toggled)
        self._compare_btn.hide()

        self._scan_btn = QPushButton("重新扫描")
        self._scan_btn.setStyleSheet(secondary_btn_style())
        self._scan_btn.setFixedHeight(38)
        self._scan_btn.clicked.connect(self._do_scan)
        actions_row.addWidget(self._scan_btn)

        self._tool_filter_btn = QPushButton("工具已隐藏")
        self._tool_filter_btn.setCheckable(True)
        self._tool_filter_btn.setFixedHeight(38)
        self._tool_filter_btn.toggled.connect(self._on_tool_visibility_toggled)
        self._tool_filter_btn.setEnabled(False)
        actions_row.addWidget(self._tool_filter_btn)
        hero_side.addLayout(actions_row)

        hero_top_row.addLayout(hero_side)
        hero_layout.addLayout(hero_top_row)

        metrics_row = QHBoxLayout()
        metrics_row.setContentsMargins(0, 0, 0, 0)
        metrics_row.setSpacing(10)
        metrics_row.addStretch(1)
        metrics_row.addWidget(self._build_metric_card("frameworks", "框架数", "blue"))
        metrics_row.addWidget(self._build_metric_card("visible", "当前队列", "teal"))
        metrics_row.addWidget(self._build_metric_card("bookmarks", "收藏数", "yellow"))
        hero_layout.addLayout(metrics_row)

        layout.addWidget(hero)
        hero.hide()

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_panel = QFrame()
        self._left_panel = left_panel
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        self._queue_kicker = QLabel("SESSION QUEUE")
        self._queue_kicker.setVisible(False)
        left_layout.addWidget(self._queue_kicker)

        self._queue_title = QLabel("最近活跃会话")
        left_layout.addWidget(self._queue_title)

        self._queue_hint = QLabel("切换框架或输入关键词后，左侧队列会自动按最新活跃上下文重新整理。")
        self._queue_hint.setWordWrap(True)
        left_layout.addWidget(self._queue_hint)

        self._fw_container = QWidget()
        self._fw_flow = QHBoxLayout(self._fw_container)
        self._fw_flow.setContentsMargins(0, 2, 0, 2)
        self._fw_flow.setSpacing(6)
        self._fw_btn_group = QButtonGroup(self)
        self._fw_btn_group.setExclusive(True)
        self._fw_btn_group.buttonClicked.connect(self._on_fw_selected)
        self._fw_flow.addStretch()
        left_layout.addWidget(self._fw_container)

        filter_row = QHBoxLayout()
        filter_row.setSpacing(6)

        self._filter_edit = QLineEdit()
        self._filter_edit.setPlaceholderText("搜索会话...")
        self._filter_edit.setStyleSheet(lineedit_style())
        self._filter_edit.setFixedHeight(36)
        self._filter_edit.textChanged.connect(self._on_filter)
        filter_row.addWidget(self._filter_edit)

        self._bookmark_filter_btn = QPushButton("★")
        self._bookmark_filter_btn.setCheckable(True)
        self._bookmark_filter_btn.setFixedSize(38, 34)
        self._bookmark_filter_btn.setToolTip("仅显示收藏")
        self._bookmark_filter_btn.toggled.connect(self._on_bookmark_filter_toggled)
        filter_row.addWidget(self._bookmark_filter_btn)

        left_layout.addLayout(filter_row)

        self._session_list = QListWidget()
        self._session_list.setStyleSheet(
            f"QListWidget {{ background: transparent; border: 1px solid {_rgba(C['surface2'], 0.35)};"
            f" border-radius: 18px; outline: none; padding: 6px; }}"
            f"QListWidget::item {{ padding: 0; margin: 0; border: none; }}"
            f"QListWidget::item:selected {{ background: transparent; }}"
        )
        self._session_list.setItemDelegate(SessionDelegate(self._session_list))
        self._session_list.setMouseTracking(True)
        self._session_list.setMinimumWidth(320)
        self._session_list.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self._session_list.setTextElideMode(Qt.ElideRight)
        self._session_list.currentRowChanged.connect(self._on_session_selected)
        left_layout.addWidget(self._session_list, 1)

        right_widget = QFrame()
        self._right_panel = right_widget
        right_layout = QVBoxLayout(right_widget)
        right_layout.setContentsMargins(16, 16, 16, 0)
        right_layout.setSpacing(12)

        reader_header = QFrame()
        self._reader_header = reader_header
        reader_header.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        reader_layout = QVBoxLayout(reader_header)
        reader_layout.setContentsMargins(16, 14, 16, 14)
        reader_layout.setSpacing(6)

        self._reader_badge = QLabel("IDLE")
        self._reader_badge.setVisible(False)
        reader_layout.addWidget(self._reader_badge, 0, Qt.AlignLeft)

        self._reader_title = QLabel("阅读画布")
        reader_layout.addWidget(self._reader_title)

        self._reader_subtitle = QLabel("选择左侧会话后，右侧会按消息角色分层显示内容，并保留思考过程折叠能力。")
        self._reader_subtitle.setWordWrap(True)
        reader_layout.addWidget(self._reader_subtitle)
        right_layout.addWidget(reader_header)

        self._chat_scroll = QScrollArea()
        self._chat_scroll.setWidgetResizable(True)
        self._chat_scroll.setFrameShape(QFrame.NoFrame)
        self._chat_scroll.setStyleSheet("background: transparent; border: none;")

        self._chat_container = QWidget()
        self._chat_layout = QVBoxLayout(self._chat_container)
        self._chat_layout.setContentsMargins(16, 12, 16, 12)
        self._chat_layout.setSpacing(12)
        self._chat_layout.addStretch()
        self._chat_scroll.setWidget(self._chat_container)
        self._chat_scroll.verticalScrollBar().valueChanged.connect(self._on_chat_scroll)
        right_layout.addWidget(self._chat_scroll)

        self._detail_bar = QWidget()
        self._detail_bar.setFixedHeight(48)
        self._detail_bar.setStyleSheet(
            f"background: transparent; border-top: 1px solid {_rgba(C['surface2'], 0.28)};"
        )
        bar_layout = QHBoxLayout(self._detail_bar)
        bar_layout.setContentsMargins(4, 0, 4, 0)
        self._detail_info = QLabel("")
        self._detail_info.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 12px; border: none; background: transparent;"
        )
        bar_layout.addWidget(self._detail_info)
        bar_layout.addStretch()

        from ..components.exporter import make_export_button, build_format_menu
        self._export_btn = make_export_button(self)
        self._export_btn.setVisible(False)
        build_format_menu(self._export_btn, self._export_session)
        bar_layout.addWidget(self._export_btn)

        self._bookmark_btn = QPushButton("收藏")
        self._bookmark_btn.setStyleSheet(secondary_btn_style())
        self._bookmark_btn.setFixedWidth(90)
        self._bookmark_btn.clicked.connect(self._toggle_bookmark)
        self._bookmark_btn.setVisible(False)
        bar_layout.addWidget(self._bookmark_btn)

        self._copy_btn = QPushButton("复制全文")
        self._copy_btn.setStyleSheet(secondary_btn_style())
        self._copy_btn.setFixedWidth(90)
        self._copy_btn.clicked.connect(self._copy_all)
        self._copy_btn.setVisible(False)
        bar_layout.addWidget(self._copy_btn)

        right_layout.addWidget(self._detail_bar)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_widget)
        splitter.setHandleWidth(12)
        splitter.setOpaqueResize(True)
        splitter.setSizes([360, 820])
        layout.addWidget(splitter, 1)

        self._apply_shell_styles()
        self._show_placeholder("正在扫描 AI 框架...")

    def topbar_context_widgets(self):
        summary_widgets = [self._status_label]
        summary_widgets.extend(frame for frame, *_ in self._metric_values.values())
        return summary_widgets, [self._tool_filter_btn, self._scan_btn]

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

    def _set_overview_metrics(self, visible_count: int | None = None):
        total_frameworks = len(self._fw_groups)
        bookmarks = len(self.bookmarks.get_all())
        if visible_count is None:
            if self._current_fw and self._current_fw in self._sessions_cache:
                visible_count = len(self._sessions_cache[self._current_fw])
            else:
                visible_count = sum(source.session_count for source in self._sources)

        self._metric_values["frameworks"][2].setText(str(total_frameworks))
        self._metric_values["visible"][2].setText(str(visible_count))
        self._metric_values["bookmarks"][2].setText(str(bookmarks))

        if self._current_fw:
            self._hero_desc.setText(
                f"当前焦点为 {self._current_fw}，支持队列过滤、文件内容级 grep 命中和会话对比，便于快速回看关键上下文。"
            )
        else:
            self._hero_desc.setText(
                "跨框架整理原始对话记录，按最近活跃排序，并支持内容级检索、收藏与对比阅读。"
            )

    def _set_reader_state(self, badge: str, title: str, subtitle: str):
        self._reader_badge.setText(badge)
        self._reader_title.setText(title)
        self._reader_subtitle.setText(subtitle)

    def _panel_style(self) -> str:
        return (
            f"QFrame {{ background: {_rgba(C['base'], 0.96)}; border: 1px solid {_rgba(C['surface2'], 0.42)}; border-radius: 22px; }}"
        )

    def _sub_panel_style(self) -> str:
        return (
            f"QFrame {{ background: {_rgba(C['surface0'], 0.72)}; border: 1px solid {_rgba(C['surface2'], 0.28)}; border-radius: 18px; }}"
        )

    def _compare_btn_style(self) -> str:
        return (
            f"QPushButton {{ background: {_rgba(C['base'], 0.96)}; color: {C['text']}; "
            f"border: 1px solid {_rgba(C['surface2'], 0.45)}; border-radius: 14px; "
            f"padding: 8px 16px; font-size: 13px; font-weight: 700; }}"
            f"QPushButton:hover {{ border-color: {_rgba(C['blue'], 0.48)}; background: {_rgba(C['surface0'], 0.72)}; }}"
            f"QPushButton:checked {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {C['blue']}, stop:1 {C['teal']}); "
            f"color: white; border-color: transparent; }}"
        )

    def _bookmark_filter_style(self) -> str:
        return (
            f"QPushButton {{ background: {_rgba(C['base'], 0.96)}; color: {C['overlay0']}; "
            f"border: 1px solid {_rgba(C['surface2'], 0.45)}; border-radius: 12px; font-size: 15px; font-weight: 800; }}"
            f"QPushButton:checked {{ background: {_rgba(C['yellow'], 0.16)}; color: {C['yellow']}; "
            f"border-color: {_rgba(C['yellow'], 0.5)}; }}"
            f"QPushButton:hover {{ border-color: {_rgba(C['yellow'], 0.5)}; color: {C['yellow']}; }}"
        )

    def _apply_shell_styles(self):
        self._hero_frame.setStyleSheet("QFrame { background: transparent; border: none; }")
        self._hero_kicker.setStyleSheet(
            f"color: {C['blue']}; font-size: 11px; font-weight: 800; "
            f"background: {_rgba(C['blue'], 0.14)}; border: 1px solid {_rgba(C['blue'], 0.22)}; "
            f"border-radius: 999px; padding: 5px 10px;"
        )
        self._header.setStyleSheet(f"color: {C['text']}; font-size: 24px; font-weight: 800;")
        self._hero_desc.setStyleSheet(f"color: {C['subtext0']}; font-size: 13px; line-height: 1.6;")
        self._status_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; font-weight: 600;")
        for frame, label, value, color_key in self._metric_values.values():
            frame.setStyleSheet(self._sub_panel_style())
            label.setStyleSheet(
                f"color: {C['subtext0']}; font-size: 11px; font-weight: 700; background: transparent; border: none;"
            )
            value.setStyleSheet(
                f"color: {C[color_key]}; font-size: 22px; font-weight: 800; background: transparent; border: none;"
            )
        self._compare_btn.setStyleSheet(self._compare_btn_style())
        self._scan_btn.setStyleSheet(secondary_btn_style())
        self._tool_filter_btn.setStyleSheet(self._compare_btn_style())
        self._left_panel.setStyleSheet(self._panel_style())
        self._queue_kicker.setStyleSheet(
            f"color: {C['teal']}; font-size: 11px; font-weight: 800; background: transparent; border: none;"
        )
        self._queue_title.setStyleSheet(
            f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;"
        )
        self._queue_hint.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;"
        )
        self._filter_edit.setStyleSheet(lineedit_style())
        self._bookmark_filter_btn.setStyleSheet(self._bookmark_filter_style())
        self._session_list.setStyleSheet(
            f"QListWidget {{ background: transparent; border: 1px solid {_rgba(C['surface2'], 0.35)};"
            f" border-radius: 18px; outline: none; padding: 6px; }}"
            f"QListWidget::item {{ padding: 0; margin: 0; border: none; }}"
            f"QListWidget::item:selected {{ background: transparent; }}"
        )
        self._right_panel.setStyleSheet(self._panel_style())
        self._reader_header.setStyleSheet(self._sub_panel_style())
        self._reader_badge.setStyleSheet(
            f"color: {C['lavender']}; font-size: 11px; font-weight: 800; background: {_rgba(C['lavender'], 0.12)}; "
            f"border: 1px solid {_rgba(C['lavender'], 0.2)}; border-radius: 999px; padding: 4px 10px;"
        )
        self._reader_title.setStyleSheet(
            f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;"
        )
        self._reader_subtitle.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;"
        )
        self._detail_bar.setStyleSheet(
            f"background: transparent; border-top: 1px solid {_rgba(C['surface2'], 0.28)};"
        )
        self._detail_info.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 12px; border: none; background: transparent;"
        )
        self._copy_btn.setStyleSheet(secondary_btn_style())

    def _fw_btn_style(self, color: str, selected: bool = False) -> str:
        if selected:
            return (
                f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {color}, stop:1 {C['teal']}); "
                f"color: white; border: none; border-radius: 14px; padding: 6px 12px;"
                f" font-size: 11px; font-weight: 800; }}"
            )
        return (
            f"QPushButton {{ background: {_rgba(C['base'], 0.94)}; color: {color};"
            f" border: 1px solid {_rgba(color, 0.45)}; border-radius: 14px;"
            f" padding: 6px 12px; font-size: 11px; font-weight: 700; }}"
            f"QPushButton:hover {{ background: {_rgba(C['surface0'], 0.72)}; border-color: {_rgba(color, 0.68)}; }}"
        )

    def _do_scan(self):
        if self._busy:
            return

        self._set_busy(True)
        self._status_label.setText("扫描中...")
        self._worker = ScanWorker(self.scanner)
        self._track_worker(self._worker)
        self._worker.finished.connect(self._on_scan_done)
        self._worker.start()

    def _on_scan_done(self, sources: list[SessionSource]):
        self._sources = sources
        self._sessions_cache.clear()

        self._fw_groups.clear()
        self._fw_latest_time.clear()
        for src in sources:
            key = src.framework.value
            self._fw_groups.setdefault(key, []).append(src)

        total = sum(s.session_count for s in sources)
        fw_count = len(self._fw_groups)

        if not sources:
            self._status_label.setText("未检测到会话")
            self._set_overview_metrics(0)
            self._show_placeholder("未检测到任何 AI 框架的会话记录")
            self._set_busy(False)
        elif self._fw_groups:
            self._status_label.setText(f"正在整理会话顺序... {fw_count} 个框架, {total} 个会话")
            self._set_overview_metrics(total)
            self._order_worker = FrameworkWarmupWorker(self.scanner, self._fw_groups)
            self._order_worker.finished.connect(self._on_framework_order_ready)
            self._order_worker.start()

    def _on_framework_order_ready(self, latest_times: dict, sessions_cache: dict):
        self._fw_latest_time = latest_times
        self._sessions_cache = sessions_cache
        self._rebuild_fw_buttons()

        total = sum(s.session_count for s in self._sources)
        fw_count = len(self._fw_groups)
        self._status_label.setText(f"{fw_count} 个框架, {total} 个会话")
        self._set_overview_metrics(total)

        if not self._fw_groups:
            return

        from datetime import datetime
        sorted_keys = sorted(
            self._fw_groups.keys(),
            key=lambda k: self._fw_latest_time.get(k, datetime.min),
            reverse=True,
        )
        first_key = sorted_keys[0]
        btn = self._fw_buttons.get(first_key)
        if btn:
            btn.setChecked(True)
            self._on_fw_selected(btn)

        self._set_busy(False)

    def _set_busy(self, busy: bool):
        if self._busy == busy:
            return

        self._busy = busy
        self._scan_btn.setEnabled(not busy)
        self._scan_btn.setText("扫描中..." if busy else "重新扫描")
        self.busy_changed.emit(busy)

    def is_busy(self) -> bool:
        return self._busy

    def _rebuild_fw_buttons(self):
        for btn in list(self._fw_buttons.values()):
            self._fw_btn_group.removeButton(btn)
            btn.deleteLater()
        self._fw_buttons.clear()

        while self._fw_flow.count():
            item = self._fw_flow.takeAt(0)
            if item.widget():
                item.widget().deleteLater()

        from datetime import datetime
        sorted_keys = sorted(
            self._fw_groups.keys(),
            key=lambda k: self._fw_latest_time.get(k, datetime.min),
            reverse=True,
        )

        for fw_key in sorted_keys:
            sources = self._fw_groups[fw_key]
            fw_type = sources[0].framework
            total = sum(s.session_count for s in sources)
            color = C[fw_type.color_key]

            btn = QPushButton(f"{fw_key} ({total})")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setProperty("fw_key", fw_key)
            btn.setProperty("fw_color", color)
            btn.setStyleSheet(self._fw_btn_style(color, False))
            btn.setFixedHeight(24)

            self._fw_btn_group.addButton(btn)
            self._fw_flow.addWidget(btn)
            self._fw_buttons[fw_key] = btn

        self._fw_flow.addStretch()

    def _reorder_fw_buttons(self):
        """按最新记录时间对框架按钮重新排序"""
        from datetime import datetime
        ordered = sorted(
            self._fw_buttons.keys(),
            key=lambda k: self._fw_latest_time.get(k, datetime.min),
            reverse=True,
        )
        for btn in self._fw_buttons.values():
            self._fw_flow.removeWidget(btn)
        for key in ordered:
            self._fw_flow.insertWidget(self._fw_flow.count() - 1, self._fw_buttons[key])

    def _on_fw_selected(self, btn: QPushButton):
        fw_key = btn.property("fw_key")
        self._current_fw = fw_key

        for k, b in self._fw_buttons.items():
            color = b.property("fw_color")
            b.setStyleSheet(self._fw_btn_style(color, k == fw_key))

        if fw_key in self._sessions_cache:
            self._populate_session_list(self._sessions_cache[fw_key])
        else:
            self._session_list.clear()
            sources = self._fw_groups.get(fw_key, [])
            if not sources:
                return
            self._status_label.setText("加载会话列表...")
            worker = LoadWorker(self.scanner, sources, fw_key)
            self._track_worker(worker)
            worker.finished.connect(self._on_sessions_loaded)
            worker.start()
            self._worker = worker

    def _on_sessions_loaded(self, fw_key: str, sessions: list[SessionInfo]):
        self._sessions_cache[fw_key] = sessions
        self._status_label.setText(f"已加载 {len(sessions)} 个会话")

        if sessions:
            latest = max((s.updated_at or s.created_at for s in sessions if s.updated_at or s.created_at), default=None)
            if latest:
                self._fw_latest_time[fw_key] = latest
                self._reorder_fw_buttons()

        if self._current_fw == fw_key:
            self._populate_session_list(sessions)

    def _populate_session_list(self, sessions: list[SessionInfo]):
        self._session_list.clear()
        filter_text = self._filter_edit.text().strip().lower()
        has_multi_ws = len(set(s.workspace for s in sessions if s.workspace)) > 1

        fw_color = C["blue"]
        if self._current_fw:
            sources = self._fw_groups.get(self._current_fw, [])
            if sources:
                fw_color = C[sources[0].framework.color_key]

        # 如果有搜索词， 先用 grep 搜索文件内容
        matched_paths = None
        if filter_text:
            sources = self._fw_groups.get(self._current_fw, [])
            if sources:
                matched_paths = set(self.scanner.grep_search(sources, filter_text))

        bookmarked_ids = self.bookmarks.get_all()
        visible_count = 0

        for sess in sessions:
            if self._show_bookmarks_only and sess.id not in bookmarked_ids:
                continue

            if filter_text:
                searchable = f"{sess.title} {sess.first_user_message or ''} {sess.workspace or ''}".lower()
                if filter_text in searchable:
                    pass
                elif matched_paths and str(sess.file_path) in matched_paths:
                    pass
                else:
                    continue

            ws_short = ""
            if has_multi_ws and sess.workspace:
                ws_short = sess.workspace.split("/")[-1] if "/" in (sess.workspace or "") else (sess.workspace or "")

            item = QListWidgetItem()
            item.setData(Qt.UserRole, sess)
            clean_title = sess.display_title.replace("\n", " ").replace("\r", "").strip()
            is_bm = sess.id in bookmarked_ids
            if is_bm:
                clean_title = "[收藏] " + clean_title
            item.setData(Qt.UserRole + 1, {
                "title": clean_title,
                "time": sess.display_time,
                "msg_count": sess.message_count,
                "workspace": ws_short,
                "archived": bool(sess.metadata.get("archived")),
                "fw_color": fw_color,
            })
            item.setSizeHint(QSize(0, 58))
            item.setToolTip(
                f"{sess.title}\n{sess.message_count} 条消息\n{sess.file_path}"
            )
            self._session_list.addItem(item)
            visible_count += 1

        self._set_overview_metrics(visible_count)
        if self._show_bookmarks_only:
            self._queue_hint.setText("当前仅显示收藏会话。关闭星标过滤后可恢复完整队列。")
        elif filter_text:
            self._queue_hint.setText(f"当前关键词为“{filter_text}”，队列只保留标题或文件内容命中的会话。")
        else:
            self._queue_hint.setText("切换框架或输入关键词后，左侧队列会自动按最新活跃上下文重新整理。")

        if visible_count > 0 and not self._compare_mode:
            self._session_list.setCurrentRow(0)
        else:
            self._show_placeholder("未找到可显示的会话")

    def _tool_type_from_message(self, msg) -> str:
        if msg.role != "tool":
            return ""

        first_line = msg.content.splitlines()[0].strip() if msg.content else ""
        explicit_labels = {
            "应用补丁",
            "终端命令",
            "读取文件",
            "列出目录",
            "错误检查",
            "待办列表",
            "互动反馈",
        }
        if first_line in explicit_labels:
            return first_line

        text = f"{msg.content}\n{msg.detail}".lower()
        if "apply_patch" in text:
            return "应用补丁"
        if any(key in text for key in ("run_in_terminal", "send_to_terminal", "terminal_", "exec(")):
            return "终端命令"
        if any(key in text for key in ("read_file", "list_dir", "grep_search", "file_search", "semantic_search", "read(")):
            return "文件检索"
        if any(key in text for key in ("create_file", "write(", "replace", "edit_file")):
            return "文件写入"
        if any(key in text for key in ("memory", "cli.py remember", "cli.py update", "cli.py recall")):
            return "记忆管理"
        if any(key in text for key in ("get_errors", "copilot_geterrors")):
            return "错误检查"
        if any(key in text for key in ("interactive_feedback", "askquestion")):
            return "交互反馈"
        if any(key in text for key in ("browser_", "playwright", "navigate", "click(")):
            return "浏览器操作"
        if any(key in text for key in ("install_", "pip ", "npm ", "pnpm ", "yarn ")):
            return "依赖安装"
        if any(key in text for key in ("configure_python_environment", "get_python_", "pylance")):
            return "Python 环境"

        import re
        starred = re.search(r"\*\*(.*?)\*\*", msg.content)
        if starred:
            return starred.group(1).strip()
        named = re.search(r"([a-zA-Z_][\w.-]+)\(", text)
        if named:
            return named.group(1)
        return "其他工具"

    def _sync_tool_filter_button_state(self, session: SessionInfo | None):
        has_tools = bool(session and any(msg.role == "tool" for msg in session.messages))
        self._tool_filter_btn.setEnabled(has_tools)
        if not has_tools:
            self._show_tool_messages = False
            self._tool_filter_btn.setChecked(False)
        self._tool_filter_btn.setText("工具已显示" if self._show_tool_messages else "工具已隐藏")

    def _on_tool_visibility_toggled(self, checked: bool):
        self._show_tool_messages = checked
        self._tool_filter_btn.setText("工具已显示" if checked else "工具已隐藏")
        if self._current_session and self._current_session.messages:
            self._render_chat(self._current_session, self._render_request_token)

    def _filtered_messages(self, messages):
        filtered = []
        for msg in messages:
            if msg.role != "tool":
                filtered.append(msg)
                continue
            if self._show_tool_messages:
                filtered.append(msg)
        return filtered

    def _load_and_show(self, session: SessionInfo):
        self._load_request_token += 1
        self._render_request_token += 1
        self._current_session = session
        self._pending_render = []
        self._render_target_end = 0
        self._highlight_term = self._filter_edit.text().strip()

        if session.messages:
            self._pending_message_load = None
            self._render_request_token = self._load_request_token
            self._render_chat(session, self._render_request_token)
            return

        self._show_placeholder("正在加载会话...")
        self._set_reader_state("LOAD", "正在载入会话", f"{session.framework.value} · {session.display_title}")

        if self._msg_worker and self._msg_worker.isRunning():
            self._pending_message_load = (session, self._load_request_token)
            return

        self._start_message_load(session, self._load_request_token)

    def _start_message_load(self, session: SessionInfo, request_token: int):
        worker = MessageLoadWorker(self.scanner, session, request_token)
        self._track_worker(worker)
        worker.finished.connect(self._on_messages_loaded)
        worker.start()
        self._msg_worker = worker

    def _track_worker(self, worker: QThread):
        self._active_workers.append(worker)
        worker.finished.connect(lambda *_args, w=worker: self._release_worker(w))

    def _release_worker(self, worker: QThread):
        if worker in self._active_workers:
            self._active_workers.remove(worker)
        if self._worker is worker:
            self._worker = None
        if self._order_worker is worker:
            self._order_worker = None
        if self._msg_worker is worker:
            self._msg_worker = None
        worker.deleteLater()

    def _clear_chat_layout(self):
        self._load_more_btn = None
        self._chat_container.setUpdatesEnabled(False)
        while self._chat_layout.count():
            child = self._chat_layout.takeAt(0)
            widget = child.widget()
            if widget:
                widget.deleteLater()
        self._chat_container.setUpdatesEnabled(True)

    def _on_messages_loaded(self, session_id: str, session: SessionInfo, request_token: int):
        next_request = self._pending_message_load
        self._pending_message_load = None

        if next_request and next_request[1] > request_token:
            next_session, next_token = next_request
            self._start_message_load(next_session, next_token)
            return

        if request_token != self._load_request_token:
            return
        if not self._current_session or self._current_session.id != session_id:
            return
        self._current_session = session
        for row in range(self._session_list.count()):
            item = self._session_list.item(row)
            listed = item.data(Qt.UserRole)
            if listed and listed.id == session_id:
                listed.message_count = session.message_count
                meta = item.data(Qt.UserRole + 1) or {}
                meta["msg_count"] = session.message_count
                item.setData(Qt.UserRole, listed)
                item.setData(Qt.UserRole + 1, meta)
                break
        self._render_request_token = request_token
        self._render_chat(session, request_token)

    def _render_chat(self, session: SessionInfo, request_token: int):
        if request_token != self._render_request_token:
            return
        self._pending_render = []
        self._clear_chat_layout()
        self._sync_tool_filter_button_state(session)
        self._visible_session_messages = self._filtered_messages(session.messages)

        if not self._visible_session_messages:
            self._show_placeholder("此会话没有可显示的消息")
            return

        meta_parts = []
        if session.workspace:
            meta_parts.append(f"工作区: {session.workspace}")
        meta_parts.append(f"框架: {session.framework.value}")
        meta_parts.append(f"消息: {session.message_count} 条")
        if session.display_time:
            meta_parts.append(f"时间: {session.display_time}")
        if session.metadata.get("model"):
            meta_parts.append(f"模型: {session.metadata['model']}")

        fmt = session.metadata.get("format", "")
        if fmt:
            meta_parts.append(f"格式: {fmt}")

        self._set_reader_state(
            session.framework.value[:4].upper(),
            session.display_title,
            " | ".join(meta_parts),
        )

        if fmt == "jsonl":
            hint = QLabel("JSONL 格式不包含工具调用记录，仅 TXT 格式的会话可查看完整工具调用过程")
            hint.setWordWrap(True)
            hint.setStyleSheet(
                f"color: {C['yellow']}; font-size: 11px; padding: 8px 12px; "
                f"background: {_rgba(C['yellow'], 0.1)}; border: 1px solid {_rgba(C['yellow'], 0.2)}; border-radius: 12px;"
            )
            self._chat_layout.addWidget(hint)

        self._displayed_count = 0
        self._load_more_messages(request_token)

        self._detail_info.setText(
            f"{session.framework.value} | {session.message_count} 条消息 | {session.file_path}"
        )
        self._export_btn.setVisible(True)
        self._bookmark_btn.setVisible(True)
        self._copy_btn.setVisible(True)
        self._update_bookmark_btn(self.bookmarks.is_bookmarked(session.id))

    def _on_chat_scroll(self, value):
        sb = self._chat_scroll.verticalScrollBar()
        if sb.maximum() > 0 and value >= sb.maximum() - 50:
            if self._visible_session_messages and self._displayed_count < len(self._visible_session_messages):
                self._load_more_messages(self._render_request_token)

    def _load_more_messages(self, request_token: int):
        if request_token != self._render_request_token:
            return
        if not self._current_session or not self._visible_session_messages:
            return
        if self._pending_render:
            return

        messages = self._visible_session_messages
        start = self._displayed_count
        page_size = MESSAGES_PER_PAGE
        if start == 0 and len(messages) <= 50:
            page_size = len(messages)
        end = min(start + page_size, len(messages))

        if start >= len(messages):
            return

        if self._load_more_btn is not None:
            try:
                self._load_more_btn.deleteLater()
            except RuntimeError:
                pass
            self._load_more_btn = None

        if self._chat_layout.count() > 0:
            last = self._chat_layout.itemAt(self._chat_layout.count() - 1)
            if last and last.widget() is None:
                self._chat_layout.takeAt(self._chat_layout.count() - 1)

        self._pending_render = list(range(start, end))
        self._render_target_end = end
        self._render_next_batch(request_token)

    def _render_next_batch(self, request_token: int):
        if request_token != self._render_request_token:
            return
        if not self._pending_render or not self._current_session:
            if not self._pending_render:
                self._finalize_load(request_token)
            return

        batch = self._pending_render[:RENDER_BATCH_SIZE]
        self._pending_render = self._pending_render[RENDER_BATCH_SIZE:]

        messages = self._visible_session_messages
        self._chat_container.setUpdatesEnabled(False)
        for i in batch:
            if i < len(messages):
                msg = messages[i]
                bubble = self._make_bubble(msg.role, msg.content, getattr(msg, 'detail', ''))
                alignment = Qt.AlignRight if msg.role == "user" else Qt.AlignLeft
                self._chat_layout.addWidget(bubble, 0, alignment)
        self._chat_container.setUpdatesEnabled(True)

        if self._pending_render:
            QTimer.singleShot(0, lambda token=request_token: self._render_next_batch(token))
        else:
            self._finalize_load(request_token)

    def _finalize_load(self, request_token: int):
        if request_token != self._render_request_token:
            return
        if not self._current_session:
            return

        self._displayed_count = self._render_target_end
        remaining = len(self._visible_session_messages) - self._render_target_end

        if remaining > 0:
            self._load_more_btn = QPushButton(f"加载更多 ({remaining} 条剩余)")
            self._load_more_btn.setStyleSheet(secondary_btn_style())
            self._load_more_btn.setFixedHeight(36)
            self._load_more_btn.clicked.connect(self._load_more_messages)
            self._chat_layout.addWidget(self._load_more_btn)
        else:
            self._load_more_btn = None

        self._chat_layout.addStretch()

    def _make_bubble(self, role: str, content: str, detail: str = "") -> QFrame:
        container = QFrame()
        is_user = role == "user"
        is_tool = role == "tool"
        text = content.strip()
        hl = self._highlight_term

        if is_user:
            container.setMaximumWidth(760)
            container.setStyleSheet(
                f"QFrame {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {_rgba(C['blue'], 0.18)}, stop:1 {_rgba(C['surface0'], 0.92)}); "
                f"border: 1px solid {_rgba(C['blue'], 0.38)}; border-radius: 18px; }}"
            )
            layout = QVBoxLayout(container)
            layout.setContentsMargins(14, 10, 14, 10)
            layout.setSpacing(4)

            role_label = QLabel("用户指令")
            role_label.setStyleSheet(
                f"color: {C['blue']}; font-size: 11px; font-weight: 800; border: none; background: transparent;"
            )
            layout.addWidget(role_label)

            if hl:
                import html as _html
                escaped = _html.escape(text).replace("\n", "<br>")
                highlighted = highlight_search(escaped, hl)
                content_label = QLabel(highlighted)
                content_label.setTextFormat(Qt.RichText)
            else:
                content_label = QLabel(text)
                content_label.setTextFormat(Qt.PlainText)
            content_label.setWordWrap(True)
            content_label.setStyleSheet(
                f"color: {C['text']}; font-size: 13px; border: none; "
                f"background: transparent; line-height: 1.6;"
            )
            layout.addWidget(content_label)
            return container

        if is_tool:
            container.setMinimumWidth(540)
            container.setMaximumWidth(1180)
            container.setStyleSheet(
                f"QFrame {{ background: {_rgba(C['mantle'], 0.96)}; border: 1px solid {_rgba(C['surface2'], 0.32)}; "
                f"border-left: 3px solid {C['yellow']}; border-radius: 16px; }}"
            )
            outer = QVBoxLayout(container)
            outer.setContentsMargins(12, 8, 12, 8)
            outer.setSpacing(4)

            first_line = text.split("\n", 1)[0][:120]
            expand_text = detail if detail else text
            has_more = bool(detail) or len(text.strip()) > len(first_line.strip())
            if has_more:
                first_line = first_line.rstrip() + " …"

            tool_label = QLabel("工具调用")
            tool_label.setStyleSheet(
                f"color: {C['yellow']}; font-size: 11px; font-weight: 800; background: transparent; border: none;"
            )

            row = QHBoxLayout()
            row.setSpacing(6)
            row.addWidget(tool_label, 0, Qt.AlignVCenter)

            summary_label = QLabel(first_line)
            summary_label.setStyleSheet(
                f"color: {C['subtext0']}; font-size: 12px; border: none; background: transparent;"
            )
            summary_label.setWordWrap(False)
            row.addWidget(summary_label, 1)

            if has_more:
                expand_btn = QPushButton("展开")
                expand_btn.setCursor(Qt.PointingHandCursor)
                expand_btn.setFixedHeight(22)
                expand_btn.setStyleSheet(
                    f"QPushButton {{ color: {C['overlay0']}; font-size: 11px; "
                    f"border: 1px solid {C['surface1']}; border-radius: 4px; padding: 0 8px; "
                    f"background: {C['surface0']}; }}"
                    f"QPushButton:hover {{ color: {C['text']}; border-color: {C['blue']}; }}"
                )
                row.addWidget(expand_btn)

                browser_holder = [None]

                def _toggle_expand(checked=False, sl=summary_label, bh=browser_holder,
                                   btn=expand_btn, ol=outer, et=expand_text):
                    if bh[0] is not None and bh[0].isVisible():
                        bh[0].setVisible(False)
                        sl.setVisible(True)
                        btn.setText("展开")
                    else:
                        if bh[0] is None:
                            bh[0] = AutoHeightBrowser()
                            full_html = render_markdown(et, C["mantle"], False)
                            bh[0].setHtml(full_html)
                            bh[0].setStyleSheet(
                                f"QTextBrowser {{ background: transparent; border: none; "
                                f"color: {C['subtext0']}; font-size: 12px; }}"
                            )
                            bh[0].document().setDocumentMargin(0)
                            bh[0].setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                            bh[0].setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
                            ol.addWidget(bh[0])
                        sl.setVisible(False)
                        bh[0].setVisible(True)
                        btn.setText("收起")

                expand_btn.clicked.connect(_toggle_expand)

            outer.addLayout(row)
            return container

        container.setMaximumWidth(1180)
        container.setMinimumWidth(760)
        container.setStyleSheet(
            f"QFrame {{ background: {_rgba(C['base'], 0.96)}; border: 1px solid {_rgba(C['surface2'], 0.35)}; border-radius: 18px; }}"
        )
        layout = QVBoxLayout(container)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        role_label = QLabel("AI 响应")
        role_label.setStyleSheet(
            f"color: {C['teal']}; font-size: 11px; font-weight: 800; background: transparent; border: none;"
        )
        layout.addWidget(role_label)

        visible_text, thinking_text = split_thinking(text)

        if len(visible_text) > 1500:
            visible_text = visible_text[:1500] + "\n\n... (内容已截断)"

        bg = C["base"]
        html_str = render_markdown(visible_text, bg, False)
        if hl:
            html_str = highlight_search(html_str, hl)
        browser = AutoHeightBrowser()
        browser.setOpenExternalLinks(True)
        browser.setStyleSheet(
            f"QTextBrowser {{ background: transparent; border: none; "
            f"color: {C['text']}; font-size: 13px; }}"
        )
        browser.document().setDocumentMargin(0)
        browser.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        browser.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        browser.setHtml(html_str)
        layout.addWidget(browser)

        if thinking_text:
            toggle_btn = QPushButton(f"查看思考过程 ({len(thinking_text)} 字)")
            toggle_btn.setStyleSheet(
                f"QPushButton {{ color: {C['overlay0']}; font-size: 11px; "
                f"border: none; text-align: left; padding: 2px 0; }}"
                f"QPushButton:hover {{ color: {C['subtext0']}; }}"
            )
            thinking_holder = [None]

            def _toggle(checked=False, th=thinking_holder, btn=toggle_btn,
                        tt=thinking_text, parent_layout=layout):
                if th[0] is not None and th[0].isVisible():
                    th[0].setVisible(False)
                    btn.setText(f"查看思考过程 ({len(tt)} 字)")
                else:
                    if th[0] is None:
                        th[0] = QTextBrowser()
                        thinking_html = render_markdown(tt[:2000], bg, False)
                        th[0].setHtml(thinking_html)
                        th[0].setStyleSheet(
                            f"QTextBrowser {{ background: {C['mantle']}; border: none; "
                            f"border-radius: 6px; color: {C['subtext0']}; font-size: 12px; padding: 8px; }}"
                        )
                        th[0].document().setDocumentMargin(4)
                        th[0].setVerticalScrollBarPolicy(Qt.ScrollBarAsNeeded)
                        th[0].setMaximumHeight(300)
                        parent_layout.addWidget(th[0])
                    th[0].setVisible(True)
                    btn.setText("收起思考过程")

            toggle_btn.clicked.connect(_toggle)
            layout.addWidget(toggle_btn)

        return container

    def _show_placeholder(self, text: str):
        self._pending_render = []
        self._render_target_end = 0
        self._set_reader_state("IDLE", "阅读画布", text)
        self._clear_chat_layout()

        label = QLabel(text)
        label.setAlignment(Qt.AlignCenter)
        label.setStyleSheet(
            f"color: {C['overlay0']}; font-size: 14px; padding: 60px; background: transparent; border: none;"
        )
        self._chat_layout.addWidget(label)
        self._chat_layout.addStretch()
        self._export_btn.setVisible(False)
        self._bookmark_btn.setVisible(False)
        self._copy_btn.setVisible(False)

    def _toggle_bookmark(self):
        if not self._current_session:
            return
        is_bm = self.bookmarks.toggle(self._current_session.id)
        self._update_bookmark_btn(is_bm)
        self._set_overview_metrics()
        if self._current_fw and self._current_fw in self._sessions_cache:
            self._populate_session_list(self._sessions_cache[self._current_fw])

    def _update_bookmark_btn(self, is_bookmarked: bool):
        if is_bookmarked:
            self._bookmark_btn.setText("已收藏")
            self._bookmark_btn.setStyleSheet(
                f"QPushButton {{ background: {C['yellow']}; color: {C['crust']}; "
                f"border: none; border-radius: 8px; padding: 8px 16px; font-size: 13px; font-weight: bold; }}"
                f"QPushButton:hover {{ background: {C['peach']}; }}"
            )
        else:
            self._bookmark_btn.setText("收藏")
            self._bookmark_btn.setStyleSheet(secondary_btn_style())

    def _on_bookmark_filter_toggled(self, checked: bool):
        self._show_bookmarks_only = checked
        if self._current_fw and self._current_fw in self._sessions_cache:
            self._populate_session_list(self._sessions_cache[self._current_fw])

    def _on_compare_mode_toggled(self, checked: bool):
        self._compare_mode = checked
        self._compare_sessions.clear()
        if checked:
            self._show_placeholder("对比模式：请在左侧选择 2 个会话")
            self._session_list.setSelectionMode(self._session_list.MultiSelection)
        else:
            self._session_list.setSelectionMode(self._session_list.SingleSelection)
            self._show_placeholder("点击左侧会话查看详情")

    def _on_session_selected(self, row: int):
        if row < 0:
            return
        item = self._session_list.item(row)
        if not item:
            return
        session = item.data(Qt.UserRole)
        if not session:
            return

        if self._compare_mode:
            selected_items = self._session_list.selectedItems()
            self._compare_sessions = [
                it.data(Qt.UserRole) for it in selected_items if it.data(Qt.UserRole)
            ]
            if len(self._compare_sessions) == 2:
                self._show_compare_view(self._compare_sessions[0], self._compare_sessions[1])
            elif len(self._compare_sessions) == 1:
                self._show_placeholder("对比模式：已选择 1 个会话，请再选择 1 个")
            elif len(self._compare_sessions) > 2:
                self._compare_sessions = self._compare_sessions[:2]
                self._show_compare_view(self._compare_sessions[0], self._compare_sessions[1])
        else:
            self._load_and_show(session)

    def _show_compare_view(self, s1: SessionInfo, s2: SessionInfo):
        self._render_request_token += 1
        self._pending_render = []
        self._render_target_end = 0
        self._set_reader_state("CMP", "会话对比", f"{s1.framework.value} 与 {s2.framework.value} 的摘要和前 20 条消息对照")
        self._clear_chat_layout()

        compare_data = [
            ("标题", s1.display_title, s2.display_title),
            ("框架", s1.framework.value, s2.framework.value),
            ("消息数", str(s1.message_count), str(s2.message_count)),
            ("时间", s1.display_time, s2.display_time),
            ("工作区", s1.workspace or "-", s2.workspace or "-"),
        ]

        for label, v1, v2 in compare_data:
            row = QFrame()
            row.setStyleSheet(
                f"QFrame {{ background: {C['surface0']}; border-radius: 8px; }}"
            )
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 8, 12, 8)

            l_label = QLabel(label)
            l_label.setFixedWidth(80)
            l_label.setStyleSheet(
                f"color: {C['subtext0']}; font-size: 12px; font-weight: bold;"
            )
            row_layout.addWidget(l_label)

            v1_label = QLabel(v1)
            v1_label.setWordWrap(True)
            v1_label.setStyleSheet(f"color: {C['text']}; font-size: 13px;")
            row_layout.addWidget(v1_label, 1)

            sep = QFrame()
            sep.setFixedWidth(2)
            sep.setStyleSheet(f"background: {C['surface2']};")
            row_layout.addWidget(sep)

            v2_label = QLabel(v2)
            v2_label.setWordWrap(True)
            v2_label.setStyleSheet(f"color: {C['text']}; font-size: 13px;")
            row_layout.addWidget(v2_label, 1)

            self._chat_layout.addWidget(row)

        if s1.messages and s2.messages:
            msg_title = QLabel("消息对比（首 20 条）")
            msg_title.setStyleSheet(
                f"color: {C['text']}; font-size: 14px; font-weight: bold; padding: 8px 0;"
            )
            self._chat_layout.addWidget(msg_title)

            max_msgs = min(20, max(len(s1.messages), len(s2.messages)))
            for i in range(max_msgs):
                row = QFrame()
                row.setStyleSheet(f"QFrame {{ border-bottom: 1px solid {C['surface0']}; }}")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(4, 4, 4, 4)
                row_layout.setSpacing(8)

                m1 = s1.messages[i] if i < len(s1.messages) else None
                m2 = s2.messages[i] if i < len(s2.messages) else None

                for msg in [m1, m2]:
                    if msg:
                        preview = msg.content[:200].replace("\n", " ")
                        color = C["blue"] if msg.role == "user" else C["text"]
                        label = QLabel(f"[{msg.role}] {preview}")
                        label.setWordWrap(True)
                        label.setStyleSheet(f"color: {color}; font-size: 12px;")
                    else:
                        label = QLabel("-")
                        label.setStyleSheet(f"color: {C['overlay0']}; font-size: 12px;")
                    row_layout.addWidget(label, 1)

                self._chat_layout.addWidget(row)

        self._chat_layout.addStretch()
        self._export_btn.setVisible(False)
        self._bookmark_btn.setVisible(False)
        self._copy_btn.setVisible(False)

    def _export_session(self, fmt: str):
        if not self._current_session:
            return
        from ..components.exporter import format_session, save_with_dialog
        content = format_session(self._current_session, fmt)
        safe_name = (self._current_session.title or self._current_session.id[:12]).replace("/", "_")[:50]
        save_with_dialog(content, safe_name, fmt, self)

    def _copy_all(self):
        if not self._current_session or not self._current_session.messages:
            return
        lines = []
        for msg in self._current_session.messages:
            role_map = {"user": "用户", "assistant": "AI", "tool": "工具"}
            prefix = role_map.get(msg.role, msg.role)
            lines.append(f"[{prefix}]\n{msg.content}\n")
        QApplication.clipboard().setText("\n".join(lines))

    def _on_filter(self, text: str):
        if not self._current_fw or self._current_fw not in self._sessions_cache:
            return

        text = text.strip().lower()
        if not text:
            self._populate_session_list(self._sessions_cache[self._current_fw])
            return

        sources = self._fw_groups.get(self._current_fw, [])
        if not sources:
            return

        matched_paths = self.scanner.grep_search(sources, text)
        matched_paths_set = set(matched_paths)

        all_sessions = self._sessions_cache[self._current_fw]
        matched_sessions = [
            s for s in all_sessions
            if str(s.file_path) in matched_paths_set
        ]

        self._populate_session_list(matched_sessions)
        self._status_label.setText(f"找到 {len(matched_sessions)} 个匹配会话")

    def refresh(self):
        self._do_scan()

    def refresh_style(self):
        self._apply_shell_styles()
        self._set_overview_metrics()

        for k, btn in self._fw_buttons.items():
            color = btn.property("fw_color")
            btn.setStyleSheet(self._fw_btn_style(color, k == self._current_fw))

        if self._current_session and self._current_session.messages:
            self._render_chat(self._current_session, self._render_request_token)
