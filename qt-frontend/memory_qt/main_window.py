"""主窗口 — Tab 容器 + 搜索栏 + 系统托盘"""

from datetime import datetime
from pathlib import Path
import re

from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QVBoxLayout, QHBoxLayout, QGridLayout,
    QWidget, QLabel, QStatusBar, QPushButton, QFrame, QSizePolicy,
    QSystemTrayIcon, QMenu, QAction, QToolButton, QGraphicsOpacityEffect, QDialog,
    QAbstractItemView,
    QCheckBox, QComboBox, QLineEdit, QSpinBox, QMessageBox, QTextEdit, QProgressBar,
    QStackedWidget, QScrollArea, QTableWidget, QTableWidgetItem, QHeaderView,
)
from PyQt5.QtGui import QDesktopServices, QIcon, QCloseEvent, QKeySequence, QColor, QBrush
from PyQt5.QtCore import Qt, QMimeData, QUrl, QPropertyAnimation, QEasingCurve, QThread, QTimer, pyqtSignal
from PyQt5.QtWidgets import QShortcut

from .constants import C, THEMES, DEFAULT_THEME, APP_NAME, APP_VERSION, reload_theme_config, save_default_theme
from .theme import apply_theme, global_style, lineedit_style, spinbox_style, primary_btn_style, secondary_btn_style, sync_action_btn_style, danger_btn_style
from .data_bridge import DataBridge
from .tabs.overview_tab import OverviewTab
from .tabs.episodic_tab import EpisodicTab
from .tabs.semantic_tab import SemanticTab
from .tabs.procedural_tab import ProceduralTab
from .tabs.asset_tab import AssetTab
from .tabs.graph_tab import GraphTab
from .tabs.search_tab import SearchTab
from .tabs.session_tab import SessionTab
from .components.search_bar import GlobalSearchBar
from ai_memory.sync.github_device_flow import GitHubDeviceFlowError

_ICON_PATH = Path(__file__).parent.parent / "assets" / "icon.svg"

_TAB_META = [
    {
        "code": "OV",
        "label": "总览",
        "kicker": "态势总览",
        "desc": "统一监控记忆、实体、资产和最近活动，先看系统状态，再下钻明细。",
    },
    {
        "code": "CS",
        "label": "会话记录",
        "kicker": "会话情报",
        "desc": "跨框架查看原始对话记录，按最新活动排序并快速跳转重点会话。",
    },
    {
        "code": "EP",
        "label": "会话摘要",
        "kicker": "事件摘要",
        "desc": "按时间线梳理阶段性总结，适合回看项目推进脉络和关键结论。",
    },
    {
        "code": "SE",
        "label": "笔记",
        "kicker": "语义记忆",
        "desc": "沉淀可复用知识、术语和事实说明，保持知识库清晰可检索。",
    },
    {
        "code": "PR",
        "label": "偏好",
        "kicker": "执行规则",
        "desc": "维护用户约束、协作规则和执行偏好，确保后续行为保持一致。",
    },
    {
        "code": "AS",
        "label": "资产",
        "kicker": "资产复用",
        "desc": "管理脚本、原型和交付成果，确认它们可追踪、可验证、可复用。",
    },
    {
        "code": "GP",
        "label": "图谱",
        "kicker": "关系图谱",
        "desc": "查看实体之间的关联网络，从节点关系反推记忆上下文。",
    },
    {
        "code": "SC",
        "label": "搜索",
        "kicker": "融合检索",
        "desc": "统一搜索记忆与会话，按多通道结果快速定位需要的上下文。",
    },
    {
        "code": "ST",
        "label": "设置",
        "kicker": "设置中心",
        "desc": "管理主题、同步、导入导出和安全规则，不再通过弹窗临时配置。",
    },
]


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


class SyncCycleWorker(QThread):
    finished = pyqtSignal(dict)
    failed = pyqtSignal(str)
    progress = pyqtSignal(str)

    def __init__(self, bridge: DataBridge, runtime_options: dict | None = None):
        super().__init__()
        self.bridge = bridge
        self.runtime_options = runtime_options or {}

    def run(self):
        try:
            result = self.bridge.run_sync_cycle(progress_callback=self.progress.emit, runtime_options=self.runtime_options)
        except Exception as exc:
            self.failed.emit(str(exc))
            return
        self.finished.emit(result)


class DeviceFlowStartWorker(QThread):
    finished = pyqtSignal(dict)
    failed = pyqtSignal(object)

    def __init__(self, bridge: DataBridge):
        super().__init__()
        self.bridge = bridge

    def run(self):
        try:
            flow = self.bridge.start_github_device_flow()
        except Exception as exc:
            self.failed.emit(exc)
            return
        self.finished.emit(flow)


class DeviceFlowPollWorker(QThread):
    finished = pyqtSignal(dict)
    failed = pyqtSignal(object)

    def __init__(self, bridge: DataBridge, device_code: str):
        super().__init__()
        self.bridge = bridge
        self.device_code = device_code

    def run(self):
        try:
            sync = self.bridge.complete_github_device_flow(self.device_code)
        except Exception as exc:
            self.failed.emit(exc)
            return
        self.finished.emit(sync)


class MainWindow(QMainWindow):
    _INITIAL_SYNC_CONFIRM_BYTES = 512 * 1024 * 1024
    _INITIAL_SYNC_CONFIRM_ITEMS = 50

    def __init__(self, bridge: DataBridge):
        super().__init__()
        self.bridge = bridge
        self._really_quit = False
        self._refresh_in_progress = False
        self._session_tab_busy = False
        self.current_theme = DEFAULT_THEME
        self._nav_buttons = []
        self._theme_buttons = {}
        self._theme_preview_cards = {}
        self._metric_values = {}
        self._settings_dialog = None
        self._settings_export_btn = None
        self._settings_nav_buttons = []
        self._settings_pages = None
        self._settings_scroll_viewports = []
        self._settings_page_contents = []
        self._sync_subnav_buttons = []
        self._sync_subpages = None
        self._sync_detail_dialog = None
        self._oversize_dialog = None
        self._sync_widgets = {}
        self._sync_field_cards = []
        self._sync_field_labels = []
        self._device_flow_context = None
        self._device_flow_start_worker = None
        self._device_flow_poll_worker = None
        self._sync_auth_timer = QTimer(self)
        self._sync_auth_timer.timeout.connect(self._poll_github_device_flow)
        self._scheduled_sync_timer = QTimer(self)
        self._scheduled_sync_timer.timeout.connect(self._run_scheduled_sync_cycle)
        self._sync_cycle_running = False
        self._sync_cycle_from_timer = False
        self._sync_cycle_summary = ""
        self._sync_progress_text = ""
        self._sync_worker = None
        self._sync_runtime_options = {}
        self._sync_preview_entries = []
        self._sync_uploaded_preview_count = 0
        self._sync_queue_paths = []
        self._sync_queue_status_cache = []
        self._pending_sync_progress_message = ""
        self._sync_progress_ui_timer = QTimer(self)
        self._sync_progress_ui_timer.setSingleShot(True)
        self._sync_progress_ui_timer.timeout.connect(self._flush_sync_progress_ui)
        self._selected_sync_device_id = ""
        self._sync_device_table = None
        self._sync_device_note_edit = None
        self._sync_device_note_save_btn = None
        self._sync_device_refresh_btn = None
        self._sync_topbar_save_btn = None
        self.overview_tab = None
        self.session_tab = None
        self.episodic_tab = None
        self.semantic_tab = None
        self.procedural_tab = None
        self.asset_tab = None
        self.graph_tab = None
        self.search_tab = None
        self.settings_tab = None
        self.setWindowTitle(f"{APP_NAME} v{APP_VERSION}")
        self.setMinimumSize(1200, 800)
        self.resize(1400, 900)

        self.setAcceptDrops(True)
        self._build_ui()
        self._build_tray()
        self._build_shortcuts()
        self._apply_styles()
        self._refresh_toolbar()

    def _build_ui(self):
        central = QWidget()
        central.setObjectName("app_shell")
        self.setCentralWidget(central)
        layout = QHBoxLayout(central)
        layout.setSpacing(18)

        layout.addWidget(self._build_sidebar())

        workspace = QWidget()
        workspace_layout = QVBoxLayout(workspace)
        workspace_layout.setContentsMargins(0, 0, 0, 0)
        workspace_layout.setSpacing(14)

        workspace_layout.addWidget(self._build_topbar())

        canvas = QFrame()
        canvas.setObjectName("workspace_canvas")
        canvas_layout = QVBoxLayout(canvas)
        canvas_layout.setContentsMargins(0, 0, 0, 0)
        canvas_layout.setSpacing(0)

        self.tabs = QTabWidget()
        self.tabs.setDocumentMode(True)
        self.tabs.setUsesScrollButtons(True)
        self.tabs.setElideMode(Qt.ElideNone)
        self.tabs.tabBar().setExpanding(False)

        self._tab_attr_names = [
            "overview_tab",
            "session_tab",
            "episodic_tab",
            "semantic_tab",
            "procedural_tab",
            "asset_tab",
            "graph_tab",
            "search_tab",
            "settings_tab",
        ]
        self._tab_factories = [
            lambda: OverviewTab(self.bridge),
            lambda: SessionTab(auto_scan=False),
            lambda: EpisodicTab(self.bridge),
            lambda: SemanticTab(self.bridge),
            lambda: ProceduralTab(self.bridge),
            lambda: AssetTab(self.bridge),
            lambda: GraphTab(self.bridge),
            lambda: SearchTab(self.bridge),
            lambda: self._build_settings_center_page(),
        ]
        self._tab_instances = [None] * len(self._tab_factories)

        for meta in _TAB_META:
            self.tabs.addTab(QWidget(), meta["label"])
        self.tabs.tabBar().hide()
        self.tabs.currentChanged.connect(self._on_tab_changed)

        canvas_layout.addWidget(self.tabs)
        workspace_layout.addWidget(canvas, 1)
        layout.addWidget(workspace, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._ensure_tab(0)
        self._update_status()
        self._build_toast()
        self._on_tab_changed(0)

    def _ensure_tab(self, index: int):
        if index < 0 or index >= len(self._tab_factories):
            return None
        existing = self._tab_instances[index]
        if existing is not None:
            return existing

        tab = self._tab_factories[index]()
        if self._tab_attr_names[index] == "session_tab":
            tab.busy_changed.connect(self._on_session_tab_busy_changed)

        current_index = self.tabs.currentIndex()
        old_widget = self.tabs.widget(index)
        self.tabs.blockSignals(True)
        self.tabs.removeTab(index)
        self.tabs.insertTab(index, tab, _TAB_META[index]["label"])
        self.tabs.setCurrentIndex(current_index)
        self.tabs.blockSignals(False)
        if old_widget is not None:
            old_widget.deleteLater()

        self._tab_instances[index] = tab
        setattr(self, self._tab_attr_names[index], tab)
        return tab

    def _build_sidebar(self) -> QWidget:
        sidebar = QFrame()
        sidebar.setObjectName("shell_sidebar")

        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(14, 18, 14, 18)
        layout.setSpacing(10)

        brand_mark = QLabel("AI")
        brand_mark.setObjectName("brand_mark")
        brand_mark.setAlignment(Qt.AlignCenter)
        brand_mark.setFixedSize(56, 56)
        layout.addWidget(brand_mark, 0, Qt.AlignHCenter)

        brand_title = QLabel("AI MEMORY")
        brand_title.setObjectName("brand_title")
        brand_title.setAlignment(Qt.AlignCenter)
        layout.addWidget(brand_title)

        brand_subtitle = QLabel("情报台")
        brand_subtitle.setObjectName("brand_subtitle")
        brand_subtitle.setAlignment(Qt.AlignCenter)
        layout.addWidget(brand_subtitle)

        layout.addSpacing(12)

        for index, meta in enumerate(_TAB_META):
            btn = QPushButton(f"{meta['code']}\n{meta['label']}")
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(80, 72)
            btn.clicked.connect(lambda checked=False, idx=index: self.tabs.setCurrentIndex(idx))
            self._nav_buttons.append(btn)
            layout.addWidget(btn, 0, Qt.AlignHCenter)

        layout.addStretch(1)

        footer = QLabel(f"v{APP_VERSION}")
        footer.setObjectName("sidebar_footer")
        footer.setAlignment(Qt.AlignCenter)
        layout.addWidget(footer)

        return sidebar

    def _build_topbar(self) -> QWidget:
        toolbar = QFrame()
        toolbar.setObjectName("shell_topbar")

        layout = QHBoxLayout(toolbar)
        layout.setContentsMargins(16, 10, 16, 10)
        layout.setSpacing(16)

        command_card = QFrame()
        self.command_card = command_card
        command_card.setObjectName("command_card")
        command_card.setMaximumWidth(280)
        command_card.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        command_layout = QHBoxLayout(command_card)
        command_layout.setContentsMargins(12, 8, 12, 8)
        command_layout.setSpacing(10)

        self.command_badge = QLabel("OV")
        self.command_badge.setObjectName("command_badge")
        self.command_badge.setAlignment(Qt.AlignCenter)
        command_layout.addWidget(self.command_badge)

        self.command_title = QLabel("态势总览")
        self.command_title.setObjectName("command_title")
        command_layout.addWidget(self.command_title, 1)

        self.command_subtitle = QLabel("")
        self.command_subtitle.setObjectName("command_subtitle")
        self.command_subtitle.hide()

        layout.addWidget(command_card, 0, Qt.AlignLeft)

        self.context_summary_bar = QWidget()
        self.context_summary_layout = QHBoxLayout(self.context_summary_bar)
        self.context_summary_layout.setContentsMargins(0, 0, 0, 0)
        self.context_summary_layout.setSpacing(8)
        layout.addWidget(self.context_summary_bar, 0, Qt.AlignLeft)

        layout.addStretch(1)

        self.search_bar = GlobalSearchBar()
        self.search_bar.setPlaceholderText("检索记忆、会话、资产...")
        self.search_bar.setFixedSize(260, 34)
        self.search_bar.search_triggered.connect(self._on_search)
        layout.addWidget(self.search_bar, 0, Qt.AlignCenter)

        layout.addStretch(1)

        actions_bar = QWidget()
        actions_bar.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        actions_layout = QHBoxLayout(actions_bar)
        actions_layout.setContentsMargins(0, 0, 0, 0)
        actions_layout.setSpacing(10)

        self.context_actions_bar = QWidget()
        self.context_actions_layout = QHBoxLayout(self.context_actions_bar)
        self.context_actions_layout.setContentsMargins(0, 0, 0, 0)
        self.context_actions_layout.setSpacing(8)
        actions_layout.addWidget(self.context_actions_bar)

        self.refresh_btn = QPushButton("刷新")
        self.refresh_btn.setObjectName("global_refresh")
        self.refresh_btn.setToolTip("重新加载所有数据")
        self.refresh_btn.setFixedSize(72, 34)
        self.refresh_btn.clicked.connect(self._on_global_refresh)
        actions_layout.addWidget(self.refresh_btn)

        layout.addWidget(actions_bar, 0, Qt.AlignRight)

        return toolbar

    def _build_settings_center_page(self) -> QWidget:
        page = QWidget()
        layout = QHBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(14)

        nav = QFrame()
        nav.setObjectName("settings_nav")
        nav.setFixedWidth(190)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(12, 12, 12, 12)
        nav_layout.setSpacing(8)

        title = QLabel("设置中心")
        title.setObjectName("settings_title")
        nav_layout.addWidget(title)

        self._settings_nav_buttons = []
        nav_items = [
            "主题与界面",
            "仓库配置",
            "同步规则",
            "同步状态",
            "数据导入导出",
        ]
        for index, label in enumerate(nav_items):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, idx=index: self._switch_settings_page(idx))
            self._settings_nav_buttons.append(btn)
            nav_layout.addWidget(btn)
        nav_layout.addStretch(1)
        layout.addWidget(nav)

        self._settings_pages = QStackedWidget()
        self._settings_pages.addWidget(self._build_settings_page(self._build_theme_settings_section()))
        self._settings_pages.addWidget(self._build_settings_page(self._build_sync_section()))
        self._settings_pages.addWidget(self._build_settings_page(self._build_data_settings_section()))
        layout.addWidget(self._settings_pages, 1)

        def _settings_topbar_context_widgets():
            if (
                self._settings_pages is not None
                and self._settings_pages.currentIndex() == 1
                and self._sync_subpages is not None
                and self._sync_subpages.currentIndex() != 2
                and self._sync_topbar_save_btn is not None
            ):
                return [], [self._sync_topbar_save_btn]
            return [], []

        page.topbar_context_widgets = _settings_topbar_context_widgets

        self._refresh_settings_panel()
        self._switch_settings_page(0)
        return page

    def _build_settings_dialog(self):
        dialog = QDialog(self, Qt.Popup | Qt.FramelessWindowHint)
        dialog.setObjectName("settings_dialog")
        dialog.setModal(False)
        dialog.setMinimumWidth(980)

        layout = QHBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        nav = QFrame()
        nav.setObjectName("settings_nav")
        nav.setFixedWidth(190)
        nav_layout = QVBoxLayout(nav)
        nav_layout.setContentsMargins(12, 12, 12, 12)
        nav_layout.setSpacing(8)

        title = QLabel("设置中心")
        title.setObjectName("settings_title")
        nav_layout.addWidget(title)

        self._settings_nav_buttons = []
        nav_items = [
            "主题与界面",
            "仓库配置",
            "同步规则",
            "同步状态",
            "数据导入导出",
        ]
        for index, label in enumerate(nav_items):
            btn = QPushButton(label)
            btn.setCheckable(True)
            btn.clicked.connect(lambda checked=False, idx=index: self._switch_settings_page(idx))
            self._settings_nav_buttons.append(btn)
            nav_layout.addWidget(btn)
        nav_layout.addStretch(1)
        layout.addWidget(nav)

        self._settings_pages = QStackedWidget()
        self._settings_pages.addWidget(self._build_settings_page(self._build_theme_settings_section()))
        self._settings_pages.addWidget(self._build_settings_page(self._build_sync_section()))
        self._settings_pages.addWidget(self._build_settings_page(self._build_data_settings_section()))
        layout.addWidget(self._settings_pages, 1)

        self._settings_dialog = dialog
        self._refresh_settings_panel()
        self._switch_settings_page(0)

    def _build_settings_page(self, widget: QWidget) -> QWidget:
        page = QWidget()
        page.setObjectName("settings_page")
        layout = QVBoxLayout(page)
        layout.setContentsMargins(0, 0, 0, 0)

        scroll = QScrollArea()
        scroll.setObjectName("settings_scroll")
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.viewport().setObjectName("settings_scroll_viewport")
        scroll.viewport().setAutoFillBackground(True)
        self._settings_scroll_viewports.append(scroll.viewport())

        content = QWidget()
        content.setObjectName("settings_content")
        content.setAutoFillBackground(True)
        self._settings_page_contents.append(content)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 4, 0)
        content_layout.setSpacing(0)
        content_layout.addWidget(widget)
        content_layout.addStretch(1)

        scroll.setWidget(content)
        layout.addWidget(scroll)
        return page

    def _build_theme_settings_section(self) -> QFrame:
        theme_section = QFrame()
        theme_section.setObjectName("settings_section")
        theme_layout = QVBoxLayout(theme_section)
        theme_layout.setContentsMargins(14, 14, 14, 14)
        theme_layout.setSpacing(10)

        theme_title = QLabel("主题与界面")
        theme_title.setObjectName("settings_section_title")
        theme_layout.addWidget(theme_title)

        theme_hint = QLabel("每张预览卡会同时展示这套主题的工作区背景、面板底色，以及 3 个代表性强调色。下方 3 个色块从左到右分别代表主强调色、辅助强调色、暖色提示色。")
        theme_hint.setWordWrap(True)
        theme_hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; line-height: 1.5; background: transparent; border: none;")
        theme_layout.addWidget(theme_hint)

        theme_switch = QFrame()
        self.theme_switch = theme_switch
        theme_switch.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        self.theme_switch_layout = QGridLayout(theme_switch)
        self.theme_switch_layout.setContentsMargins(6, 6, 6, 6)
        self.theme_switch_layout.setHorizontalSpacing(12)
        self.theme_switch_layout.setVerticalSpacing(12)
        self._rebuild_theme_switch_controls()
        theme_layout.addWidget(theme_switch, 0, Qt.AlignLeft)
        return theme_section

    def _rebuild_theme_switch_controls(self):
        if not hasattr(self, "theme_switch_layout") or self.theme_switch_layout is None:
            return

        while self.theme_switch_layout.count():
            item = self.theme_switch_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()

        self._theme_buttons = {}
        self._theme_preview_cards = {}

        for index, theme_name in enumerate(THEMES):
            option = QWidget()
            option_layout = QVBoxLayout(option)
            option_layout.setContentsMargins(0, 0, 0, 0)
            option_layout.setSpacing(8)

            preview = self._build_theme_preview_chip(theme_name)
            preview.setCursor(Qt.PointingHandCursor)
            preview.mousePressEvent = lambda event, name=theme_name: self._on_theme_preview_clicked(event, name)
            self._theme_preview_cards[theme_name] = preview
            option_layout.addWidget(preview)

            btn = QPushButton(theme_name.split("·")[-1])
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(96, 36)
            btn.clicked.connect(lambda checked=False, name=theme_name: self._on_theme_change(name))
            self._theme_buttons[theme_name] = btn
            option_layout.addWidget(btn, 0, Qt.AlignCenter)
            self.theme_switch_layout.addWidget(option, index // 4, index % 4)

    def _build_theme_preview_chip(self, theme_name: str) -> QWidget:
        palette = THEMES[theme_name]
        preview = QFrame()
        preview.setFixedSize(250, 150)
        preview.setStyleSheet(self._theme_preview_card_style(theme_name, active=False))

        layout = QVBoxLayout(preview)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        topbar = QFrame()
        topbar.setFixedHeight(24)
        topbar.setStyleSheet(
            f"QFrame {{ background: {_rgba(palette['mantle'], 0.94)}; border: 1px solid {_rgba(palette['surface2'], 0.38)}; border-radius: 10px; }}"
        )
        topbar_layout = QHBoxLayout(topbar)
        topbar_layout.setContentsMargins(8, 5, 8, 5)
        topbar_layout.setSpacing(6)

        title_badge = QLabel()
        title_badge.setFixedSize(14, 14)
        title_badge.setStyleSheet(
            f"QLabel {{ background: {palette['blue']}; border: none; border-radius: 7px; }}"
        )
        topbar_layout.addWidget(title_badge)

        title_line = QLabel()
        title_line.setFixedSize(74, 6)
        title_line.setStyleSheet(
            f"QLabel {{ background: {_rgba(palette['text'], 0.28)}; border: none; border-radius: 3px; }}"
        )
        topbar_layout.addWidget(title_line)
        topbar_layout.addStretch(1)

        action_chip = QLabel()
        action_chip.setFixedSize(28, 12)
        action_chip.setStyleSheet(
            f"QLabel {{ background: {_rgba(palette['teal'], 0.82)}; border: none; border-radius: 6px; }}"
        )
        topbar_layout.addWidget(action_chip)
        layout.addWidget(topbar)

        middle = QWidget()
        middle.setStyleSheet("background: transparent; border: none;")
        middle_layout = QHBoxLayout(middle)
        middle_layout.setContentsMargins(0, 0, 0, 0)
        middle_layout.setSpacing(8)

        sidebar = QFrame()
        sidebar.setFixedWidth(46)
        sidebar.setStyleSheet(
            f"QFrame {{ background: {_rgba(palette['crust'], 0.96)}; border: 1px solid {_rgba(palette['surface2'], 0.3)}; border-radius: 12px; }}"
        )
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(8, 10, 8, 10)
        sidebar_layout.setSpacing(7)
        for width in (16, 24, 14):
            nav_dot = QLabel()
            nav_dot.setFixedSize(width, 7)
            nav_dot.setStyleSheet(
                f"QLabel {{ background: {_rgba(palette['subtext0'], 0.38)}; border: none; border-radius: 3px; }}"
            )
            sidebar_layout.addWidget(nav_dot)
        sidebar_layout.addStretch(1)
        middle_layout.addWidget(sidebar)

        content = QWidget()
        content.setStyleSheet("background: transparent; border: none;")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 0, 0)
        content_layout.setSpacing(8)

        hero = QFrame()
        hero.setFixedHeight(50)
        hero.setStyleSheet(
            f"QFrame {{ background: {_rgba(palette['surface0'], 0.96)}; border: 1px solid {_rgba(palette['surface2'], 0.38)}; border-radius: 14px; }}"
        )
        hero_layout = QVBoxLayout(hero)
        hero_layout.setContentsMargins(10, 9, 10, 9)
        hero_layout.setSpacing(6)

        hero_title = QLabel()
        hero_title.setFixedSize(86, 8)
        hero_title.setStyleSheet(
            f"QLabel {{ background: {_rgba(palette['text'], 0.3)}; border: none; border-radius: 4px; }}"
        )
        hero_layout.addWidget(hero_title)

        hero_subtitle = QLabel()
        hero_subtitle.setFixedSize(116, 6)
        hero_subtitle.setStyleSheet(
            f"QLabel {{ background: {_rgba(palette['subtext1'], 0.24)}; border: none; border-radius: 3px; }}"
        )
        hero_layout.addWidget(hero_subtitle)
        content_layout.addWidget(hero)

        panel_row = QWidget()
        panel_row.setStyleSheet("background: transparent; border: none;")
        panel_row_layout = QHBoxLayout(panel_row)
        panel_row_layout.setContentsMargins(0, 0, 0, 0)
        panel_row_layout.setSpacing(6)
        for _ in range(2):
            panel = QFrame()
            panel.setFixedHeight(32)
            panel.setStyleSheet(
                f"QFrame {{ background: {_rgba(palette['surface1'], 0.92)}; border: 1px solid {_rgba(palette['surface2'], 0.32)}; border-radius: 12px; }}"
            )
            panel_row_layout.addWidget(panel)
        content_layout.addWidget(panel_row)
        middle_layout.addWidget(content, 1)
        layout.addWidget(middle, 1)

        swatch_row = QWidget()
        swatch_row.setStyleSheet("background: transparent; border: none;")
        swatch_layout = QHBoxLayout(swatch_row)
        swatch_layout.setContentsMargins(0, 0, 0, 0)
        swatch_layout.setSpacing(6)
        for color_key in ("blue", "teal", "peach"):
            swatch = QLabel()
            swatch.setFixedSize(32, 14)
            swatch.setStyleSheet(
                f"QLabel {{ background: {palette[color_key]}; border: none; border-radius: 5px; }}"
            )
            swatch_layout.addWidget(swatch)
        swatch_layout.addStretch(1)
        layout.addWidget(swatch_row)
        return preview

    def _theme_preview_card_style(self, theme_name: str, active: bool) -> str:
        palette = THEMES[theme_name]
        if active:
            return f"QFrame {{ background: {palette['base']}; border: 2px solid {palette['blue']}; border-radius: 18px; }}"
        return f"QFrame {{ background: {palette['base']}; border: 1px solid {_rgba(palette['surface2'], 0.72)}; border-radius: 18px; }}"

    def _on_theme_preview_clicked(self, event, theme_name: str):
        if event.button() == Qt.LeftButton:
            self._on_theme_change(theme_name)

    def _build_data_settings_section(self) -> QFrame:
        action_section = QFrame()
        action_section.setObjectName("settings_section")
        action_layout = QVBoxLayout(action_section)
        action_layout.setContentsMargins(14, 14, 14, 14)
        action_layout.setSpacing(10)

        action_title = QLabel("数据导入导出")
        action_title.setObjectName("settings_section_title")
        action_layout.addWidget(action_title)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        self.import_btn = QPushButton("导入")
        self.import_btn.setObjectName("global_import")
        self.import_btn.setToolTip("从 ZIP 文件导入记忆和资产")
        self.import_btn.setFixedSize(96, 36)
        self.import_btn.clicked.connect(self._on_import)
        action_row.addWidget(self.import_btn)

        self.export_btn = QToolButton()
        self.export_btn.setText("导出")
        self.export_btn.setObjectName("global_export")
        self.export_btn.setPopupMode(QToolButton.InstantPopup)
        self.export_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.export_btn.setFixedSize(96, 36)
        self._build_export_menu(self.export_btn)
        action_row.addWidget(self.export_btn)
        action_row.addStretch(1)
        action_layout.addLayout(action_row)
        return action_section

    def _build_settings_placeholder_page(self, title_text: str, content_text: str) -> QFrame:
        frame = QFrame()
        frame.setObjectName("settings_section")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        title = QLabel(title_text)
        title.setObjectName("settings_section_title")
        layout.addWidget(title)

        content = QLabel(content_text)
        content.setWordWrap(True)
        content.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(content)
        return frame

    def _switch_settings_page(self, index: int):
        if self._settings_pages is None:
            return
        if index == 0:
            page_index = 0
        elif index in (1, 2, 3):
            page_index = 1
            self._switch_sync_subpage(index - 1)
        else:
            page_index = 2
        self._settings_pages.setCurrentIndex(page_index)
        self._refresh_settings_nav_state(index)
        if self.settings_tab is not None and self.tabs.currentWidget() is self.settings_tab:
            self._sync_topbar_context(self.tabs.currentIndex())

    def _refresh_settings_nav_state(self, active_index: int):
        for index, btn in enumerate(self._settings_nav_buttons):
            active = index == active_index
            btn.setChecked(active)
            btn.setStyleSheet(
                f"QPushButton {{ background: {'qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 ' + C['blue'] + ', stop:1 ' + C['teal'] + ')' if active else _rgba(C['base'], 0.72)}; color: {'white' if active else C['text']}; border: 1px solid {_rgba(C['surface2'], 0.35)}; border-radius: 14px; padding: 10px 14px; text-align: left; font-size: 13px; font-weight: 700; }}"
            )

    def _switch_sync_subpage(self, index: int):
        if self._sync_subpages is None:
            return
        self._sync_subpages.setCurrentIndex(index)
        self._refresh_sync_subnav_state(index)

    def _refresh_sync_subnav_state(self, active_index: int):
        for index, btn in enumerate(self._sync_subnav_buttons):
            active = index == active_index
            btn.setChecked(active)
            btn.setStyleSheet(
                f"QPushButton {{ background: {'qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 ' + C['blue'] + ', stop:1 ' + C['teal'] + ')' if active else _rgba(C['base'], 0.78)}; color: {'white' if active else C['text']}; border: 1px solid {_rgba(C['surface2'], 0.32)}; border-radius: 12px; padding: 8px 14px; font-size: 12px; font-weight: 700; }}"
            )

    def _build_sync_section(self) -> QFrame:
        section = QFrame()
        section.setObjectName("settings_section")
        layout = QVBoxLayout(section)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(12)

        title = QLabel("同步")
        title.setObjectName("settings_section_title")
        layout.addWidget(title)

        hint = QLabel("从左侧菜单切换仓库配置、同步规则和同步状态，右侧只显示当前选中的工作区。")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(hint)
        self._sync_subnav_buttons = []

        enabled_check = QCheckBox("启用 GitHub 同步")
        form = QFrame()
        form_layout = QVBoxLayout(form)
        form_layout.setContentsMargins(0, 0, 0, 0)
        form_layout.setSpacing(10)

        provider_combo = QComboBox()
        provider_combo.addItem("GitHub API 直传", "github")
        provider_combo.addItem("Git 工作区 + git push", "git_worktree")

        owner_edit = QLineEdit()
        owner_edit.setPlaceholderText("仓库所有者，例如 tsdl")
        owner_edit.setStyleSheet(lineedit_style())

        repo_edit = QLineEdit()
        repo_edit.setPlaceholderText("仓库名，例如 ai-memory-sync")
        repo_edit.setStyleSheet(lineedit_style())

        branch_edit = QLineEdit()
        branch_edit.setPlaceholderText("main")
        branch_edit.setStyleSheet(lineedit_style())

        machine_edit = QLineEdit()
        machine_edit.setPlaceholderText("machine_id")
        machine_edit.setStyleSheet(lineedit_style())

        auth_combo = QComboBox()
        auth_combo.addItem("GitHub 登录（OAuth Device Flow）", "oauth")
        auth_combo.addItem("Personal Access Token", "token")

        client_id_edit = QLineEdit()
        client_id_edit.setPlaceholderText("GitHub OAuth App Client ID")
        client_id_edit.setStyleSheet(lineedit_style())

        worktree_edit = QLineEdit()
        worktree_edit.setPlaceholderText("~/.local/share/ai-memory/sync-worktree")
        worktree_edit.setStyleSheet(lineedit_style())

        auth_status = QLabel("")
        auth_status.setWordWrap(True)
        auth_status.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")

        lock_banner = QLabel("")
        lock_banner.setWordWrap(True)
        lock_banner.setStyleSheet(
            f"color: {C['text']}; font-size: 12px; background: {_rgba(C['yellow'], 0.08)}; border: 1px solid {_rgba(C['yellow'], 0.18)}; border-radius: 14px; padding: 10px 12px;"
        )

        github_user_display = QLabel("未登录")
        github_user_display.setWordWrap(True)
        github_user_display.setStyleSheet(
            f"color: {C['text']}; font-size: 12px; background: {_rgba(C['surface0'], 0.88)}; border: 1px solid {_rgba(C['surface2'], 0.35)}; border-radius: 14px; padding: 10px 12px;"
        )

        auth_action_row = QHBoxLayout()
        auth_action_row.setContentsMargins(0, 0, 0, 0)
        auth_action_row.setSpacing(8)

        login_btn = QPushButton("GitHub 登录")
        login_btn.setStyleSheet(primary_btn_style())
        login_btn.clicked.connect(self._start_github_device_flow)
        auth_action_row.addWidget(login_btn)

        logout_btn = QPushButton("退出登录")
        logout_btn.setStyleSheet(danger_btn_style())
        logout_btn.clicked.connect(self._logout_github_device_flow)
        auth_action_row.addWidget(logout_btn)
        auth_action_row.addStretch(1)

        mode_combo = QComboBox()
        mode_combo.addItem("手动同步", "manual")
        mode_combo.addItem("定时同步", "scheduled")
        mode_combo.addItem("仅拉取", "pull_only")

        interval_spin = QSpinBox()
        interval_spin.setRange(5, 1440)
        interval_spin.setSuffix(" 分钟")
        interval_spin.setStyleSheet(spinbox_style())

        upload_sessions = QCheckBox("上传原始会话文件")

        upload_assets = QCheckBox("上传托管资产")

        upload_sensitive = QCheckBox("允许上传敏感会话")

        status_label = QLabel("")
        status_label.setWordWrap(True)
        status_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")

        upload_rules = QFrame()
        upload_rules.setObjectName("settings_subsection")
        upload_rules.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        upload_rules_layout = QVBoxLayout(upload_rules)
        upload_rules_layout.setContentsMargins(10, 10, 10, 10)
        upload_rules_layout.setSpacing(8)

        upload_rules_title = QLabel("上传规则")
        upload_rules_title.setObjectName("settings_section_title")
        upload_rules_layout.addWidget(upload_rules_title)

        size_limit_spin = QSpinBox()
        size_limit_spin.setRange(1, 10240)
        size_limit_spin.setSuffix(" MB")
        size_limit_spin.setStyleSheet(spinbox_style())

        oversize_combo = QComboBox()
        oversize_combo.addItem("提示用户决定", "prompt")
        oversize_combo.addItem("自动跳过", "skip")
        oversize_combo.addItem("全部继续上传", "upload")

        asset_scope_combo = QComboBox()
        asset_scope_combo.addItem("按整个资产目录大小计算", "asset_directory")
        asset_scope_combo.addItem("按单文件大小计算", "single_file")

        compress_upload = QCheckBox("压缩上传")
        whitelist_first = QCheckBox("白名单优先")
        skip_blacklist = QCheckBox("命中黑名单则不上传")

        whitelist_edit = QTextEdit()
        whitelist_edit.setPlaceholderText("每行一条规则，例如\nassets/reports/\nsessions/copilot/")
        whitelist_edit.setFixedHeight(82)

        blacklist_edit = QTextEdit()
        blacklist_edit.setPlaceholderText("每行一条规则，例如\ntmp/\n*.mp4")
        blacklist_edit.setFixedHeight(82)

        upload_rules_grid = QGridLayout()
        upload_rules_grid.setContentsMargins(0, 0, 0, 0)
        upload_rules_grid.setHorizontalSpacing(10)
        upload_rules_grid.setVerticalSpacing(10)
        upload_rules_grid.addWidget(self._build_sync_field_card("大小限制", size_limit_spin), 0, 0)
        upload_rules_grid.addWidget(self._build_sync_field_card("超限处理", oversize_combo), 0, 1)
        upload_rules_grid.addWidget(self._build_sync_field_card("资产口径", asset_scope_combo), 1, 0, 1, 2)
        upload_rules_layout.addLayout(upload_rules_grid)

        rules_switch_panel = QFrame()
        rules_switch_panel.setObjectName("settings_subsection")
        rules_switch_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        rules_switch_layout = QVBoxLayout(rules_switch_panel)
        rules_switch_layout.setContentsMargins(10, 10, 10, 10)
        rules_switch_layout.setSpacing(8)
        rules_switch_title = QLabel("规则开关")
        rules_switch_title.setObjectName("settings_section_title")
        rules_switch_layout.addWidget(rules_switch_title)
        rules_switch_layout.addWidget(compress_upload)
        rules_switch_layout.addWidget(whitelist_first)
        rules_switch_layout.addWidget(skip_blacklist)
        upload_rules_layout.addWidget(rules_switch_panel)

        patterns_grid = QGridLayout()
        patterns_grid.setContentsMargins(0, 0, 0, 0)
        patterns_grid.setHorizontalSpacing(10)
        patterns_grid.setVerticalSpacing(10)
        patterns_grid.addWidget(self._build_sync_field_card("白名单", whitelist_edit), 0, 0)
        patterns_grid.addWidget(self._build_sync_field_card("黑名单", blacklist_edit), 0, 1)
        upload_rules_layout.addLayout(patterns_grid)

        progress_frame = QFrame()
        progress_frame.setObjectName("settings_subsection")
        progress_layout = QVBoxLayout(progress_frame)
        progress_layout.setContentsMargins(10, 10, 10, 10)
        progress_layout.setSpacing(8)

        progress_title = QLabel("当前进度")
        progress_title.setObjectName("settings_section_title")
        progress_layout.addWidget(progress_title)

        progress_label = QLabel("当前无进行中的同步任务")
        progress_label.setWordWrap(True)
        progress_label.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        progress_layout.addWidget(progress_label)

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 1)
        progress_bar.setValue(0)
        progress_bar.setFormat("0/0")
        progress_layout.addWidget(progress_bar)

        history_panel = QFrame()
        history_panel.setObjectName("settings_subsection")
        history_layout = QVBoxLayout(history_panel)
        history_layout.setContentsMargins(10, 10, 10, 10)
        history_layout.setSpacing(8)

        history_title = QLabel("同步记录")
        history_title.setObjectName("settings_section_title")
        history_layout.addWidget(history_title)

        history_hint = QLabel("按时间和内容查看最近同步动作，避免只看到单个时间戳。")
        history_hint.setWordWrap(True)
        history_hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        history_layout.addWidget(history_hint)

        history_table = QTableWidget(0, 3)
        history_table.setHorizontalHeaderLabels(["时间", "内容", "结果"])
        history_table.verticalHeader().setVisible(False)
        history_table.setEditTriggers(QTableWidget.NoEditTriggers)
        history_table.setSelectionMode(QAbstractItemView.NoSelection)
        history_table.setFocusPolicy(Qt.NoFocus)
        history_table.setShowGrid(False)
        history_table.horizontalHeader().setStretchLastSection(False)
        history_table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeToContents)
        history_table.horizontalHeader().setSectionResizeMode(1, QHeaderView.Stretch)
        history_table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        history_table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        history_table.setStyleSheet(
            f"QTableWidget {{ background: {_rgba(C['base'], 0.9)}; color: {C['text']}; border: 1px solid {_rgba(C['surface2'], 0.42)}; border-radius: 16px; font-size: 12px; gridline-color: transparent; }}"
            f"QHeaderView::section {{ background: {_rgba(C['surface0'], 0.92)}; color: {C['subtext0']}; border: none; border-bottom: 1px solid {_rgba(C['surface2'], 0.35)}; padding: 10px 12px; font-size: 12px; font-weight: 700; }}"
            f"QTableWidget::item {{ border-bottom: 1px solid {_rgba(C['surface2'], 0.16)}; padding: 10px 12px; }}"
        )
        history_layout.addWidget(history_table)

        queue_panel, queue_table = self._build_sync_queue_panel()

        sync_save_btn = QPushButton("保存同步设置")
        sync_save_btn.setStyleSheet(secondary_btn_style())
        sync_save_btn.clicked.connect(self._save_sync_settings)
        self._sync_topbar_save_btn = sync_save_btn

        sync_now_btn = QPushButton("立即同步")
        sync_now_btn.setCursor(Qt.PointingHandCursor)
        sync_now_btn.setMinimumHeight(40)
        sync_now_btn.setStyleSheet(sync_action_btn_style())
        sync_now_btn.clicked.connect(self._run_sync_cycle)

        repo_page = QFrame()
        repo_page.setObjectName("settings_subsection")
        repo_layout = QVBoxLayout(repo_page)
        repo_layout.setContentsMargins(12, 12, 12, 12)
        repo_layout.setSpacing(8)
        repo_layout.addWidget(enabled_check)
        repo_layout.addWidget(auth_status)
        repo_layout.addWidget(lock_banner)

        locked_group = QFrame()
        locked_group.setObjectName("settings_subsection")
        locked_group_layout = QVBoxLayout(locked_group)
        locked_group_layout.setContentsMargins(10, 10, 10, 10)
        locked_group_layout.setSpacing(8)
        locked_group_title = QLabel("登录后锁定配置")
        locked_group_title.setObjectName("settings_section_title")
        locked_group_layout.addWidget(locked_group_title)
        locked_group_hint = QLabel("这些配置会和当前登录态绑定。已登录时需要先退出登录，才能修改后重新登录。")
        locked_group_hint.setWordWrap(True)
        locked_group_hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        locked_group_layout.addWidget(locked_group_hint)
        locked_grid = QGridLayout()
        locked_grid.setContentsMargins(0, 0, 0, 0)
        locked_grid.setHorizontalSpacing(10)
        locked_grid.setVerticalSpacing(10)
        locked_grid.addWidget(self._build_sync_field_card("同步引擎", provider_combo), 0, 0)
        locked_grid.addWidget(self._build_sync_field_card("仓库所有者", owner_edit), 1, 0)
        locked_grid.addWidget(self._build_sync_field_card("仓库名称", repo_edit), 1, 1)
        locked_grid.addWidget(self._build_sync_field_card("分支", branch_edit), 2, 0)
        locked_grid.addWidget(self._build_sync_field_card("认证方式", auth_combo), 2, 1)
        locked_grid.addWidget(self._build_sync_field_card("OAuth Client ID", client_id_edit), 3, 0, 1, 2)
        locked_grid.addWidget(self._build_sync_field_card("GitHub 已登录用户", github_user_display), 4, 0, 1, 2)
        locked_group_layout.addLayout(locked_grid)
        locked_group_layout.addLayout(auth_action_row)
        repo_layout.addWidget(locked_group)

        editable_group = QFrame()
        editable_group.setObjectName("settings_subsection")
        editable_group_layout = QVBoxLayout(editable_group)
        editable_group_layout.setContentsMargins(10, 10, 10, 10)
        editable_group_layout.setSpacing(8)
        editable_group_title = QLabel("可直接调整")
        editable_group_title.setObjectName("settings_section_title")
        editable_group_layout.addWidget(editable_group_title)
        editable_group_hint = QLabel("这组参数不和登录身份强绑定，独立放在下方区域。")
        editable_group_hint.setWordWrap(True)
        editable_group_hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        editable_group_layout.addWidget(editable_group_hint)
        editable_grid = QGridLayout()
        editable_grid.setContentsMargins(0, 0, 0, 0)
        editable_grid.setHorizontalSpacing(10)
        editable_grid.setVerticalSpacing(10)
        editable_grid.addWidget(self._build_sync_field_card("同步模式", mode_combo), 0, 0)
        editable_grid.addWidget(self._build_sync_field_card("定时间隔", interval_spin), 0, 1)
        editable_grid.addWidget(self._build_sync_field_card("机器标识", machine_edit), 1, 0)
        editable_grid.addWidget(self._build_sync_field_card("工作区路径", worktree_edit), 1, 1)
        editable_group_layout.addLayout(editable_grid)
        repo_layout.addWidget(editable_group)
        repo_layout.addWidget(self._build_sync_device_panel())

        rules_page = QFrame()
        rules_page.setObjectName("settings_subsection")
        rules_layout = QVBoxLayout(rules_page)
        rules_layout.setContentsMargins(12, 12, 12, 12)
        rules_layout.setSpacing(8)

        rules_scope_panel = QFrame()
        rules_scope_panel.setObjectName("settings_subsection")
        rules_scope_panel.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        rules_scope_layout = QVBoxLayout(rules_scope_panel)
        rules_scope_layout.setContentsMargins(10, 10, 10, 10)
        rules_scope_layout.setSpacing(8)
        rules_scope_title = QLabel("上传范围")
        rules_scope_title.setObjectName("settings_section_title")
        rules_scope_layout.addWidget(rules_scope_title)
        rules_scope_hint = QLabel("先定义要上传什么，再继续配置大小限制、压缩和白黑名单规则。")
        rules_scope_hint.setWordWrap(True)
        rules_scope_hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        rules_scope_layout.addWidget(rules_scope_hint)
        rules_scope_layout.addWidget(upload_sessions)
        rules_scope_layout.addWidget(upload_assets)
        rules_scope_layout.addWidget(upload_sensitive)
        rules_layout.addWidget(rules_scope_panel)
        rules_layout.addWidget(upload_rules)
        rules_layout.addStretch(1)

        status_page = QFrame()
        status_page.setObjectName("settings_subsection")
        status_layout = QVBoxLayout(status_page)
        status_layout.setContentsMargins(12, 12, 12, 12)
        status_layout.setSpacing(8)

        overview_panel = QFrame()
        overview_panel.setObjectName("settings_subsection")
        overview_layout = QVBoxLayout(overview_panel)
        overview_layout.setContentsMargins(10, 10, 10, 10)
        overview_layout.setSpacing(8)

        overview_header = QHBoxLayout()
        overview_header.setContentsMargins(0, 0, 0, 0)
        overview_header.setSpacing(8)
        overview_title = QLabel("当前概览")
        overview_title.setObjectName("settings_section_title")
        overview_header.addWidget(overview_title)
        overview_header.addStretch(1)
        overview_header.addWidget(sync_now_btn)
        overview_layout.addLayout(overview_header)
        overview_layout.addWidget(status_label)
        overview_layout.addWidget(progress_frame)

        top_split = QHBoxLayout()
        top_split.setContentsMargins(0, 0, 0, 0)
        top_split.setSpacing(10)
        top_split.addWidget(history_panel, 3)
        top_split.addWidget(overview_panel, 2)

        status_layout.addLayout(top_split)
        status_layout.addWidget(queue_panel, 1)

        self._sync_subpages = QStackedWidget()
        self._sync_subpages.addWidget(repo_page)
        self._sync_subpages.addWidget(rules_page)
        self._sync_subpages.addWidget(status_page)
        form_layout.addWidget(self._sync_subpages)

        layout.addWidget(form)

        self._sync_widgets = {
            "enabled": enabled_check,
            "provider": provider_combo,
            "repo_owner": owner_edit,
            "repo_name": repo_edit,
            "branch": branch_edit,
            "machine_id": machine_edit,
            "worktree_path": worktree_edit,
            "auth_mode": auth_combo,
            "oauth_client_id": client_id_edit,
            "auth_status": auth_status,
            "lock_banner": lock_banner,
            "github_user_display": github_user_display,
            "login_btn": login_btn,
            "logout_btn": logout_btn,
            "sync_mode": mode_combo,
            "sync_interval_minutes": interval_spin,
            "upload_sessions": upload_sessions,
            "upload_assets": upload_assets,
            "upload_sensitive_sessions": upload_sensitive,
            "upload_size_limit_mb": size_limit_spin,
            "oversize_action": oversize_combo,
            "asset_size_scope": asset_scope_combo,
            "compress_upload": compress_upload,
            "whitelist_first": whitelist_first,
            "skip_blacklist_matches": skip_blacklist,
            "whitelist_patterns": whitelist_edit,
            "blacklist_patterns": blacklist_edit,
            "progress_label": progress_label,
            "progress_bar": progress_bar,
            "history_table": history_table,
            "queue_table": queue_table,
            "status_label": status_label,
            "save_btn": sync_save_btn,
            "sync_now_btn": sync_now_btn,
            "device_table": self._sync_device_table,
            "device_note_edit": self._sync_device_note_edit,
            "device_note_save_btn": self._sync_device_note_save_btn,
            "device_refresh_btn": self._sync_device_refresh_btn,
        }

        provider_combo.currentIndexChanged.connect(self._refresh_sync_settings_state)
        auth_combo.currentIndexChanged.connect(self._refresh_sync_settings_state)
        mode_combo.currentIndexChanged.connect(self._refresh_sync_settings_state)
        upload_sessions.toggled.connect(self._refresh_sync_settings_state)

        self._load_sync_settings_into_form()
        self._switch_sync_subpage(0)
        return section

    def _build_sync_device_panel(self) -> QFrame:
        frame = QFrame()
        frame.setObjectName("settings_subsection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(8)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(8)

        title = QLabel("设备列表")
        title.setObjectName("settings_section_title")
        header_row.addWidget(title)

        header_row.addStretch(1)

        refresh_btn = QPushButton("刷新设备列表")
        refresh_btn.setStyleSheet(secondary_btn_style())
        refresh_btn.clicked.connect(self._refresh_sync_devices)
        header_row.addWidget(refresh_btn)

        layout.addLayout(header_row)

        hint = QLabel("汇总当前机器、git_worktree 提交历史和同步缓存中出现过的设备；选中设备后可填写备注。")
        hint.setWordWrap(True)
        hint.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(hint)

        table = QTableWidget(0, 5)
        table.setHorizontalHeaderLabels(["设备标识", "来源", "最近活跃", "备注", "操作"])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setSelectionMode(QAbstractItemView.SingleSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.setShowGrid(False)
        table.setWordWrap(True)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Interactive)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(3, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(4, QHeaderView.Fixed)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        table.setStyleSheet(
            f"QTableWidget {{ background: {_rgba(C['base'], 0.9)}; color: {C['text']}; border: 1px solid {_rgba(C['surface2'], 0.42)}; border-radius: 16px; font-size: 12px; gridline-color: transparent; selection-background-color: {_rgba(C['surface1'], 0.6)}; selection-color: {C['text']}; }}"
            f"QHeaderView::section {{ background: {_rgba(C['surface0'], 0.92)}; color: {C['subtext0']}; border: none; border-bottom: 1px solid {_rgba(C['surface2'], 0.35)}; padding: 10px 12px; font-size: 12px; font-weight: 700; }}"
            f"QTableWidget::item {{ border-bottom: 1px solid {_rgba(C['surface2'], 0.16)}; padding: 10px 12px; }}"
        )
        table.itemSelectionChanged.connect(self._handle_sync_device_selection_changed)
        layout.addWidget(table)

        self._sync_device_table = table
        self._sync_device_note_edit = None
        self._sync_device_note_save_btn = None
        self._sync_device_refresh_btn = refresh_btn
        return frame

    def _make_settings_row(self, label_text: str, widget: QWidget) -> QWidget:
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)

        label = QLabel(label_text)
        label.setFixedWidth(84)
        label.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; font-weight: 700; background: transparent; border: none;")
        layout.addWidget(label)
        layout.addWidget(widget, 1)
        return row

    def _build_sync_field_card(self, label_text: str, widget: QWidget) -> QWidget:
        card = QFrame()
        card.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Maximum)
        self._apply_sync_field_card_style(card)
        self._sync_field_cards.append(card)
        layout = QVBoxLayout(card)
        layout.setContentsMargins(12, 10, 12, 10)
        layout.setSpacing(8)

        label = QLabel(label_text)
        self._apply_sync_field_label_style(label)
        self._sync_field_labels.append(label)
        layout.addWidget(label)

        if isinstance(widget, QTextEdit):
            widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
            widget.setFixedHeight(max(widget.height(), 82))
        if isinstance(widget, QLabel):
            widget.setMinimumHeight(40)
        else:
            widget.setMinimumHeight(40)
        layout.addWidget(widget)
        return card

    def _apply_sync_field_card_style(self, card: QFrame):
        card.setStyleSheet(
            f"QFrame {{ background: {_rgba(C['surface0'], 0.78)}; border: 1px solid {_rgba(C['surface2'], 0.32)}; border-radius: 16px; }}"
        )

    def _apply_sync_field_label_style(self, label: QLabel):
        label.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 12px; font-weight: 700; background: transparent; border: none;"
        )

    def _refresh_sync_control_styles(self):
        if not self._sync_widgets:
            return

        for card in self._sync_field_cards:
            if card is not None:
                self._apply_sync_field_card_style(card)
        for label in self._sync_field_labels:
            if label is not None:
                self._apply_sync_field_label_style(label)

        for key in ("repo_owner", "repo_name", "branch", "machine_id", "oauth_client_id", "worktree_path"):
            widget = self._sync_widgets.get(key)
            if isinstance(widget, QLineEdit):
                widget.setStyleSheet(lineedit_style())

        for key in ("sync_interval_minutes", "upload_size_limit_mb"):
            widget = self._sync_widgets.get(key)
            if isinstance(widget, QSpinBox):
                widget.setStyleSheet(spinbox_style())

        for key in ("provider", "auth_mode", "sync_mode", "oversize_action", "asset_size_scope"):
            widget = self._sync_widgets.get(key)
            if isinstance(widget, QComboBox):
                widget.setStyleSheet("")

        text_label_style = f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;"
        for key in ("auth_status", "status_label", "progress_label"):
            widget = self._sync_widgets.get(key)
            if isinstance(widget, QLabel):
                widget.setStyleSheet(text_label_style)

        lock_banner = self._sync_widgets.get("lock_banner")
        if isinstance(lock_banner, QLabel):
            lock_banner.setStyleSheet(
                f"color: {C['text']}; font-size: 12px; background: {_rgba(C['yellow'], 0.08)}; border: 1px solid {_rgba(C['yellow'], 0.18)}; border-radius: 14px; padding: 10px 12px;"
            )

        github_user_display = self._sync_widgets.get("github_user_display")
        if isinstance(github_user_display, QLabel):
            github_user_display.setStyleSheet(
                f"color: {C['text']}; font-size: 12px; background: {_rgba(C['surface0'], 0.88)}; border: 1px solid {_rgba(C['surface2'], 0.35)}; border-radius: 14px; padding: 10px 12px;"
            )

        history_table = self._sync_widgets.get("history_table")
        if isinstance(history_table, QTableWidget):
            history_table.setStyleSheet(
                f"QTableWidget {{ background: {_rgba(C['base'], 0.9)}; color: {C['text']}; border: 1px solid {_rgba(C['surface2'], 0.42)}; border-radius: 16px; font-size: 12px; gridline-color: transparent; }}"
                f"QHeaderView::section {{ background: {_rgba(C['surface0'], 0.92)}; color: {C['subtext0']}; border: none; border-bottom: 1px solid {_rgba(C['surface2'], 0.35)}; padding: 10px 12px; font-size: 12px; font-weight: 700; }}"
                f"QTableWidget::item {{ border-bottom: 1px solid {_rgba(C['surface2'], 0.16)}; padding: 10px 12px; }}"
            )

        device_table = self._sync_widgets.get("device_table")
        if isinstance(device_table, QTableWidget):
            device_table.setStyleSheet(
                f"QTableWidget {{ background: {_rgba(C['base'], 0.9)}; color: {C['text']}; border: 1px solid {_rgba(C['surface2'], 0.42)}; border-radius: 16px; font-size: 12px; gridline-color: transparent; selection-background-color: {_rgba(C['surface1'], 0.6)}; selection-color: {C['text']}; }}"
                f"QHeaderView::section {{ background: {_rgba(C['surface0'], 0.92)}; color: {C['subtext0']}; border: none; border-bottom: 1px solid {_rgba(C['surface2'], 0.35)}; padding: 10px 12px; font-size: 12px; font-weight: 700; }}"
                f"QTableWidget::item {{ border-bottom: 1px solid {_rgba(C['surface2'], 0.16)}; padding: 10px 12px; }}"
            )

        queue_table = self._sync_widgets.get("queue_table")
        if isinstance(queue_table, QTableWidget):
            queue_table.setStyleSheet(
                f"QTableWidget {{ background: {_rgba(C['base'], 0.9)}; alternate-background-color: {_rgba(C['surface0'], 0.36)}; color: {C['text']}; border: 1px solid {_rgba(C['surface2'], 0.42)}; border-radius: 16px; font-size: 12px; gridline-color: transparent; selection-background-color: {_rgba(C['surface1'], 0.6)}; }}"
                f"QHeaderView::section {{ background: {_rgba(C['surface0'], 0.92)}; color: {C['subtext0']}; border: none; border-bottom: 1px solid {_rgba(C['surface2'], 0.35)}; padding: 10px 12px; font-size: 12px; font-weight: 700; }}"
                f"QTableWidget::item {{ border-bottom: 1px solid {_rgba(C['surface2'], 0.16)}; padding: 10px 12px; }}"
            )

        if hasattr(self, "_sync_queue_summary_label") and isinstance(self._sync_queue_summary_label, QLabel):
            self._sync_queue_summary_label.setStyleSheet(
                f"color: {C['subtext0']}; font-size: 12px; background: {_rgba(C['surface0'], 0.62)}; border: 1px solid {_rgba(C['surface2'], 0.28)}; border-radius: 12px; padding: 6px 10px;"
            )

        button_styles = {
            "login_btn": primary_btn_style(),
            "logout_btn": danger_btn_style(),
            "save_btn": secondary_btn_style(),
            "sync_now_btn": sync_action_btn_style(),
            "device_refresh_btn": secondary_btn_style(),
        }
        for key, style in button_styles.items():
            widget = self._sync_widgets.get(key)
            if isinstance(widget, QPushButton):
                widget.setStyleSheet(style)

    def _set_combo_value(self, combo: QComboBox, value: str):
        index = combo.findData(value)
        combo.setCurrentIndex(index if index >= 0 else 0)

    def _load_sync_settings_into_form(self):
        if not self._sync_widgets:
            return
        sync = self.bridge.get_sync_config()
        self._sync_widgets["enabled"].setChecked(sync["enabled"])
        self._set_combo_value(self._sync_widgets["provider"], sync.get("provider") or "github")
        self._sync_widgets["repo_owner"].setText(sync["repo_owner"])
        self._sync_widgets["repo_name"].setText(sync["repo_name"])
        self._sync_widgets["branch"].setText(sync["branch"])
        self._sync_widgets["machine_id"].setText(sync["machine_id"])
        self._sync_widgets["worktree_path"].setText(sync.get("worktree_path") or "")
        self._set_combo_value(self._sync_widgets["auth_mode"], sync["auth_mode"])
        self._sync_widgets["oauth_client_id"].setText(sync["oauth_client_id"])
        self._set_combo_value(self._sync_widgets["sync_mode"], sync["sync_mode"])
        self._sync_widgets["sync_interval_minutes"].setValue(sync["sync_interval_minutes"])
        self._sync_widgets["upload_sessions"].setChecked(sync["upload_sessions"])
        self._sync_widgets["upload_assets"].setChecked(sync["upload_assets"])
        self._sync_widgets["upload_sensitive_sessions"].setChecked(sync["upload_sensitive_sessions"])
        self._sync_widgets["upload_size_limit_mb"].setValue(sync["upload_size_limit_mb"])
        self._set_combo_value(self._sync_widgets["oversize_action"], sync["oversize_action"])
        self._set_combo_value(self._sync_widgets["asset_size_scope"], sync["asset_size_scope"])
        self._sync_widgets["compress_upload"].setChecked(sync["compress_upload"])
        self._sync_widgets["whitelist_first"].setChecked(sync["whitelist_first"])
        self._sync_widgets["skip_blacklist_matches"].setChecked(sync["skip_blacklist_matches"])
        self._sync_widgets["whitelist_patterns"].setPlainText(self._patterns_to_text(sync["whitelist_patterns"]))
        self._sync_widgets["blacklist_patterns"].setPlainText(self._patterns_to_text(sync["blacklist_patterns"]))
        self._refresh_sync_settings_state()
        self._update_sync_settings_status(sync)
        self._update_sync_auth_state(sync)
        self._refresh_sync_scheduler_state(sync)
        self._refresh_sync_preview(sync)
        self._refresh_sync_devices()
        self._refresh_sync_history(sync)

    def _refresh_sync_settings_state(self):
        if not self._sync_widgets:
            return
        sync_state = self._collect_sync_form_state()
        provider = self._sync_widgets["provider"].currentData()
        mode = self._sync_widgets["sync_mode"].currentData()
        sessions_enabled = self._sync_widgets["upload_sessions"].isChecked()
        auth_mode = self._sync_widgets["auth_mode"].currentData()
        login_locked = self._sync_form_is_logged_in(sync_state)
        self._sync_widgets["sync_interval_minutes"].setEnabled(mode == "scheduled")
        self._sync_widgets["upload_sensitive_sessions"].setEnabled(sessions_enabled)
        self._set_sync_locked_widget_state(self._sync_widgets["provider"], login_locked)
        self._set_sync_locked_widget_state(self._sync_widgets["repo_owner"], login_locked)
        self._set_sync_locked_widget_state(self._sync_widgets["repo_name"], login_locked)
        self._set_sync_locked_widget_state(self._sync_widgets["branch"], login_locked)
        self._set_sync_locked_widget_state(self._sync_widgets["auth_mode"], login_locked)
        self._set_sync_locked_widget_state(self._sync_widgets["oauth_client_id"], login_locked or auth_mode != "oauth")
        self._sync_widgets["worktree_path"].setEnabled(provider == "git_worktree")
        if not sessions_enabled:
            self._sync_widgets["upload_sensitive_sessions"].setChecked(False)
        self._update_sync_auth_state(sync_state)
        self._refresh_sync_preview(sync_state)
        self._refresh_sync_history(sync_state)

    @staticmethod
    def _sync_form_is_logged_in(sync: dict) -> bool:
        return bool((sync.get("access_token") or "").strip() or (sync.get("github_user") or "").strip())

    def _set_sync_locked_widget_state(self, widget: QWidget, locked: bool):
        if isinstance(widget, QLineEdit):
            widget.setReadOnly(locked)
            widget.setStyleSheet(
                f"QLineEdit {{ background: {(_rgba(C['surface1'], 0.78) if locked else _rgba(C['surface0'], 0.94))}; color: {(C['subtext0'] if locked else C['text'])}; border: 1px solid {_rgba(C['surface2'], 0.4)}; border-radius: 12px; padding: 8px 10px; }}"
            )
            return
        if isinstance(widget, QComboBox):
            widget.setEnabled(not locked)
            widget.setStyleSheet(
                (
                    f"QComboBox {{ background: {_rgba(C['surface1'], 0.78)}; color: {C['subtext0']}; border: 1px solid {_rgba(C['surface2'], 0.4)}; border-radius: 12px; padding: 8px 10px; }}"
                    f"QComboBox::drop-down {{ border: none; width: 24px; }}"
                ) if locked else ""
            )
            return
        widget.setEnabled(not locked)

    def _collect_sync_form_state(self) -> dict:
        sync = self.bridge.get_sync_config()
        if not self._sync_widgets:
            return sync
        sync.update({
            "enabled": self._sync_widgets["enabled"].isChecked(),
            "provider": self._sync_widgets["provider"].currentData(),
            "repo_owner": self._sync_widgets["repo_owner"].text().strip() or "",
            "repo_name": self._sync_widgets["repo_name"].text().strip(),
            "branch": self._sync_widgets["branch"].text().strip() or "main",
            "machine_id": self._sync_widgets["machine_id"].text().strip(),
            "worktree_path": self._sync_widgets["worktree_path"].text().strip() or "~/.local/share/ai-memory/sync-worktree",
            "auth_mode": self._sync_widgets["auth_mode"].currentData(),
            "oauth_client_id": self._sync_widgets["oauth_client_id"].text().strip(),
            "sync_mode": self._sync_widgets["sync_mode"].currentData(),
            "sync_interval_minutes": self._sync_widgets["sync_interval_minutes"].value(),
            "upload_sessions": self._sync_widgets["upload_sessions"].isChecked(),
            "upload_assets": self._sync_widgets["upload_assets"].isChecked(),
            "upload_sensitive_sessions": self._sync_widgets["upload_sensitive_sessions"].isChecked(),
            "upload_size_limit_mb": self._sync_widgets["upload_size_limit_mb"].value(),
            "oversize_action": self._sync_widgets["oversize_action"].currentData(),
            "asset_size_scope": self._sync_widgets["asset_size_scope"].currentData(),
            "compress_upload": self._sync_widgets["compress_upload"].isChecked(),
            "whitelist_first": self._sync_widgets["whitelist_first"].isChecked(),
            "skip_blacklist_matches": self._sync_widgets["skip_blacklist_matches"].isChecked(),
            "whitelist_patterns": self._text_to_patterns(self._sync_widgets["whitelist_patterns"].toPlainText()),
            "blacklist_patterns": self._text_to_patterns(self._sync_widgets["blacklist_patterns"].toPlainText()),
        })
        return sync

    @staticmethod
    def _patterns_to_text(patterns: list[str]) -> str:
        return "\n".join(item for item in (patterns or []) if isinstance(item, str))

    @staticmethod
    def _text_to_patterns(text: str) -> list[str]:
        seen = set()
        results = []
        for raw in text.splitlines():
            item = raw.strip()
            if not item or item in seen:
                continue
            seen.add(item)
            results.append(item)
        return results

    def _refresh_sync_preview(self, sync: dict | None = None):
        if not self._sync_widgets:
            return
        sync = sync or self.bridge.get_sync_config()
        oversize_limit = int(sync.get("upload_size_limit_mb") or 0) * 1024 * 1024
        entries = self.bridge.preview_sync_entries(limit=500)
        self._sync_preview_entries = entries
        total = len(entries)
        if total == 0:
            self._sync_widgets["progress_bar"].setRange(0, 1)
            self._sync_widgets["progress_bar"].setValue(0)
            self._sync_widgets["progress_bar"].setFormat("0/0")
            self._render_sync_queue([])
            return

        oversize_count = sum(
            1
            for entry in entries
            if oversize_limit > 0 and int(entry.get("size") or 0) > oversize_limit and not entry.get("whitelisted")
        )
        preview_text = f"待同步 {total} 项"
        if oversize_count:
            preview_text += f"，其中 {oversize_count} 项超限，启动同步时会逐项确认"
        self._sync_widgets["progress_label"].setText(preview_text)
        if not self._sync_cycle_running:
            self._sync_widgets["progress_bar"].setRange(0, max(total, 1))
            self._sync_widgets["progress_bar"].setValue(0)
            self._sync_widgets["progress_bar"].setFormat(f"0/{total}")
            status_overrides = {}
            for entry in entries:
                if oversize_limit > 0 and int(entry.get("size") or 0) > oversize_limit and not entry.get("whitelisted"):
                    status_overrides[str(entry.get("path") or "")] = "超限待确认"
            self._render_sync_queue(entries, status_overrides=status_overrides)

    def _refresh_sync_history(self, sync: dict | None = None):
        if not self._sync_widgets:
            return
        table = self._sync_widgets["history_table"]
        rows = []
        if self._sync_progress_text:
            rows.insert(0, ("进行中", self._sync_progress_text, "执行中"))

        for item in self.bridge.list_sync_history(limit=12):
            rows.append((
                self._format_sync_history_time(item.get("created_at") or ""),
                str(item.get("content") or "同步记录"),
                str(item.get("result") or "-"),
            ))

        if not rows:
            rows.append(("尚无记录", "当前还没有同步历史记录，执行一次同步后会在这里持续累积。", "空白"))

        table.setRowCount(len(rows))
        for row, (when_text, content_text, result_text) in enumerate(rows):
            table.setItem(row, 0, QTableWidgetItem(when_text))
            table.setItem(row, 1, QTableWidgetItem(content_text))
            table.setItem(row, 2, QTableWidgetItem(result_text))
            table.setRowHeight(row, 56)

    @staticmethod
    def _format_sync_history_time(value: str) -> str:
        try:
            parsed = datetime.fromisoformat(value)
        except ValueError:
            return value or "-"
        return parsed.astimezone().strftime("%Y-%m-%d %H:%M:%S")

    def _refresh_sync_devices(self):
        if not self._sync_widgets or "device_table" not in self._sync_widgets:
            return
        devices = self.bridge.list_sync_devices()
        table = self._sync_widgets["device_table"]

        table.setRowCount(len(devices))
        selected_row = -1
        for row, device in enumerate(devices):
            machine_id = device["machine_id"]
            label = f"{machine_id}\n当前设备" if device.get("is_current") else machine_id

            machine_item = QTableWidgetItem(label)
            machine_item.setData(Qt.UserRole, machine_id)
            source_item = QTableWidgetItem(device.get("source_summary") or "-")
            last_seen_item = QTableWidgetItem(device.get("last_seen") or "-")
            note_item = QTableWidgetItem("")

            machine_item.setForeground(QBrush(QColor(C["text"])))
            source_item.setForeground(QBrush(QColor(C["text"])))
            last_seen_item.setForeground(QBrush(QColor(C["text"])))
            note_item.setForeground(QBrush(QColor(C["text"])))

            table.setItem(row, 0, machine_item)
            table.setItem(row, 1, source_item)
            table.setItem(row, 2, last_seen_item)
            table.setItem(row, 3, note_item)
            table.setRowHeight(row, 64)

            note_edit = QLineEdit(device.get("note") or "")
            note_edit.setPlaceholderText("填写设备备注")
            note_edit.setStyleSheet(lineedit_style())
            note_edit.setMaximumWidth(560)
            note_cell = QWidget()
            note_layout = QHBoxLayout(note_cell)
            note_layout.setContentsMargins(0, 4, 12, 4)
            note_layout.setSpacing(0)
            note_layout.addWidget(note_edit, 1)
            table.setCellWidget(row, 3, note_cell)

            save_btn = QPushButton("保存备注")
            save_btn.setStyleSheet(primary_btn_style())
            save_btn.setFixedHeight(36)
            save_btn.setFixedWidth(108)
            save_btn.clicked.connect(lambda checked=False, mid=machine_id, editor=note_edit: self._save_sync_device_note(mid, editor))
            action_cell = QWidget()
            action_layout = QHBoxLayout(action_cell)
            action_layout.setContentsMargins(0, 4, 8, 4)
            action_layout.setSpacing(0)
            action_layout.addWidget(save_btn)
            action_layout.setAlignment(Qt.AlignCenter)
            table.setCellWidget(row, 4, action_cell)

            if machine_id == self._selected_sync_device_id:
                selected_row = row

        if devices and selected_row >= 0:
            table.selectRow(selected_row)
        elif devices and not self._selected_sync_device_id:
            table.selectRow(0)
        table.setColumnWidth(0, 320)
        table.setColumnWidth(4, 156)

    def _handle_sync_device_selection_changed(self):
        if not self._sync_widgets or "device_table" not in self._sync_widgets:
            return
        table = self._sync_widgets["device_table"]
        row = table.currentRow()
        if row < 0:
            self._selected_sync_device_id = ""
            return
        machine_item = table.item(row, 0)
        if machine_item is None:
            self._selected_sync_device_id = ""
            return
        machine_id = str(machine_item.data(Qt.UserRole) or "").strip()
        self._selected_sync_device_id = machine_id

    def _save_sync_device_note(self, machine_id: str | None = None, note_widget: QLineEdit | None = None):
        machine_id = (machine_id or self._selected_sync_device_id).strip()
        if not machine_id:
            QMessageBox.information(self, "未选择设备", "请先在设备列表中选中一个设备。")
            return
        note = note_widget.text() if note_widget is not None else ""
        self.bridge.update_sync_device_note(machine_id, note)
        self.status_bar.showMessage(f"设备备注已保存：{machine_id}", 3000)
        self._show_toast("设备备注已保存")
        self._refresh_sync_devices()

    def _update_sync_settings_status(self, sync: dict):
        if not self._sync_widgets:
            return
        status_label = self._sync_widgets["status_label"]
        status_label.setText("\n".join(self._build_sync_overview_lines(sync)))

    def _build_sync_overview_lines(self, sync: dict) -> list[str]:
        repo_ready = bool(sync["repo_owner"].strip() and sync["repo_name"].strip())
        if not repo_ready:
            return ["当前未配置 GitHub 仓库", "同步保持关闭"]

        mode_map = {
            "manual": "手动同步",
            "scheduled": "定时同步",
            "pull_only": "仅拉取",
        }
        provider_map = {
            "github": "GitHub API 直传",
            "git_worktree": "Git 工作区 + git push",
        }
        lines = [f"已保存 GitHub 仓库配置：{sync['repo_owner']}/{sync['repo_name']}"]
        lines.append(f"当前引擎：{provider_map.get(sync.get('provider'), sync.get('provider', '未配置'))}")

        mode_text = mode_map.get(sync.get("sync_mode"), sync.get("sync_mode", "未配置"))
        if sync.get("sync_mode") == "scheduled":
            mode_text = f"{mode_text}，每 {sync['sync_interval_minutes']} 分钟"
        lines.append(f"当前模式：{mode_text}")

        if sync.get("provider") == "git_worktree":
            lines.append(f"工作区：{sync.get('worktree_path') or '未配置'}")

        last_sync_text = self._format_sync_history_time(str(sync.get("last_sync_at") or "")) if sync.get("last_sync_at") else "尚未同步"
        lines.append(f"上次同步：{last_sync_text}")

        if not sync.get("enabled"):
            lines.append("同步总开关：关闭")
        return lines

    def _update_sync_auth_state(self, sync: dict, pending_text: str = ""):
        if not self._sync_widgets:
            return
        auth_status = self._sync_widgets["auth_status"]
        lock_banner = self._sync_widgets["lock_banner"]
        github_user_display = self._sync_widgets["github_user_display"]
        login_btn = self._sync_widgets["login_btn"]
        logout_btn = self._sync_widgets["logout_btn"]
        auth_mode = sync.get("auth_mode", "oauth")
        github_user = (sync.get("github_user") or "").strip()
        token_ready = bool((sync.get("access_token") or "").strip())

        if pending_text:
            auth_status.setText(pending_text)
            lock_banner.setText("当前正在处理 GitHub 登录流程。流程完成前，锁定配置保持不变。")
            github_user_display.setText(github_user or "登录后显示用户")
            login_btn.setVisible(False)
            logout_btn.setVisible(False)
            return

        if auth_mode != "oauth":
            auth_status.setText("当前为 PAT 模式。OAuth 登录按钮不可用，后续可继续接入 PAT 输入与校验。")
            lock_banner.setText("当前使用 PAT 模式。建议在未登录或令牌失效时调整认证相关配置。")
            github_user_display.setText(github_user or "登录后显示用户")
            login_btn.setVisible(False)
            logout_btn.setVisible(token_ready)
            return

        if github_user:
            auth_status.setText(f"GitHub 已登录：{github_user}")
            lock_banner.setText("当前处于已登录状态。同步引擎、仓库、分支、认证方式、OAuth Client ID 和登录用户信息已锁定；如需修改，请先退出登录。")
            github_user_display.setText(github_user)
        elif token_ready:
            auth_status.setText("GitHub 访问令牌已保存，但尚未取得用户信息。")
            lock_banner.setText("检测到已保存的访问令牌。建议先确认登录状态，再决定是否调整锁定配置。")
            github_user_display.setText("登录后显示用户")
        else:
            auth_status.setText("GitHub 未登录。填写 OAuth Client ID 后，可发起 Device Flow 登录。")
            lock_banner.setText("当前处于未登录状态。你可以先调整仓库与认证配置，确认无误后再发起 GitHub 登录。")
            github_user_display.setText("登录后显示用户")
        login_btn.setVisible(not token_ready)
        logout_btn.setVisible(token_ready)
        login_btn.setEnabled(not token_ready)
        logout_btn.setEnabled(token_ready)

    def _save_sync_settings(self, show_feedback: bool = True):
        if not self._sync_widgets:
            return None
        repo_owner = self._sync_widgets["repo_owner"].text().strip()
        repo_name = self._sync_widgets["repo_name"].text().strip()
        requested_enabled = self._sync_widgets["enabled"].isChecked()
        effective_enabled = requested_enabled and bool(repo_owner and repo_name)
        if requested_enabled and not effective_enabled:
            QMessageBox.information(self, "同步未启用", "请先填写 GitHub 仓库所有者和仓库名称；已保存其他同步设置，但当前不会启用同步。")

        sync = self.bridge.update_sync_config(
            enabled=effective_enabled,
            provider=self._sync_widgets["provider"].currentData(),
            repo_owner=repo_owner,
            repo_name=self._sync_widgets["repo_name"].text().strip(),
            branch=self._sync_widgets["branch"].text().strip() or "main",
            auth_mode=self._sync_widgets["auth_mode"].currentData(),
            oauth_client_id=self._sync_widgets["oauth_client_id"].text().strip(),
            machine_id=self._sync_widgets["machine_id"].text().strip(),
            worktree_path=self._sync_widgets["worktree_path"].text().strip() or "~/.local/share/ai-memory/sync-worktree",
            sync_mode=self._sync_widgets["sync_mode"].currentData(),
            sync_interval_minutes=self._sync_widgets["sync_interval_minutes"].value(),
            upload_sessions=self._sync_widgets["upload_sessions"].isChecked(),
            upload_assets=self._sync_widgets["upload_assets"].isChecked(),
            upload_sensitive_sessions=self._sync_widgets["upload_sensitive_sessions"].isChecked(),
            upload_size_limit_mb=self._sync_widgets["upload_size_limit_mb"].value(),
            oversize_action=self._sync_widgets["oversize_action"].currentData(),
            asset_size_scope=self._sync_widgets["asset_size_scope"].currentData(),
            compress_upload=self._sync_widgets["compress_upload"].isChecked(),
            whitelist_first=self._sync_widgets["whitelist_first"].isChecked(),
            skip_blacklist_matches=self._sync_widgets["skip_blacklist_matches"].isChecked(),
            whitelist_patterns=self._text_to_patterns(self._sync_widgets["whitelist_patterns"].toPlainText()),
            blacklist_patterns=self._text_to_patterns(self._sync_widgets["blacklist_patterns"].toPlainText()),
        )
        self._sync_widgets["enabled"].setChecked(sync["enabled"])
        self._update_sync_settings_status(sync)
        self._update_sync_auth_state(sync)
        self._refresh_sync_scheduler_state(sync)
        if show_feedback:
            self.status_bar.showMessage("同步设置已保存", 3000)
            self._show_toast("同步设置已保存")
        self._refresh_sync_preview(sync)
        return sync

    def _start_github_device_flow(self):
        sync = self._save_sync_settings(show_feedback=False)
        if not sync:
            return
        if sync["auth_mode"] != "oauth":
            QMessageBox.information(self, "当前不是 OAuth 模式", "请先把认证方式切换为 GitHub 登录（OAuth Device Flow）。")
            return
        if self._device_flow_start_worker is not None and self._device_flow_start_worker.isRunning():
            return
        self._update_sync_auth_state(
            self.bridge.get_sync_config(),
            pending_text="正在连接 GitHub，准备发起 Device Flow 登录...",
        )
        worker = DeviceFlowStartWorker(self.bridge)
        worker.finished.connect(self._on_github_device_flow_started)
        worker.failed.connect(self._on_github_device_flow_start_failed)
        self._device_flow_start_worker = worker
        worker.start()

    def _on_github_device_flow_started(self, flow: dict):
        self._device_flow_start_worker = None
        self._device_flow_context = flow
        self._sync_auth_timer.start(max(1, int(flow["interval"])) * 1000)
        self._update_sync_auth_state(
            self.bridge.get_sync_config(),
            pending_text=f"已发起 GitHub Device Flow。请在浏览器中输入验证码 {flow['user_code']} 完成授权，应用会自动轮询登录结果。",
        )
        QDesktopServices.openUrl(QUrl(flow["verification_uri"]))
        QMessageBox.information(
            self,
            "GitHub Device Flow",
            f"浏览器授权页已打开。\n\n请在 GitHub 页面输入验证码：{flow['user_code']}\n\n地址：{flow['verification_uri']}",
        )

    def _on_github_device_flow_start_failed(self, exc: object):
        self._device_flow_start_worker = None
        self._update_sync_auth_state(self.bridge.get_sync_config())
        message = str(exc)
        if isinstance(exc, GitHubDeviceFlowError) and exc.code == "network_error" and "timed out" in message.lower():
            message = f"{message}\n\n当前网络到 GitHub 握手超时。请检查网络、代理或稍后重试。"
        QMessageBox.warning(self, "GitHub 登录启动失败", message)

    def _poll_github_device_flow(self):
        if not self._device_flow_context:
            self._sync_auth_timer.stop()
            return
        if self._device_flow_poll_worker is not None and self._device_flow_poll_worker.isRunning():
            return
        worker = DeviceFlowPollWorker(self.bridge, self._device_flow_context["device_code"])
        worker.finished.connect(self._on_github_device_flow_poll_succeeded)
        worker.failed.connect(self._on_github_device_flow_poll_failed)
        self._device_flow_poll_worker = worker
        worker.start()

    def _on_github_device_flow_poll_succeeded(self, sync: dict):
        self._device_flow_poll_worker = None
        if not self._device_flow_context:
            return
        self._sync_auth_timer.stop()
        self._device_flow_context = None
        self._update_sync_settings_status(sync)
        self._update_sync_auth_state(sync)
        self._refresh_sync_settings_state()
        self._refresh_sync_scheduler_state(sync)
        self.status_bar.showMessage("GitHub 登录成功", 3000)
        self._show_toast("GitHub 登录成功")

    def _on_github_device_flow_poll_failed(self, exc: object):
        self._device_flow_poll_worker = None
        if not isinstance(exc, GitHubDeviceFlowError):
            self._sync_auth_timer.stop()
            self._device_flow_context = None
            self._update_sync_auth_state(self.bridge.get_sync_config())
            QMessageBox.warning(self, "GitHub 登录失败", str(exc))
            return
        if exc.code == "authorization_pending":
            return
        if exc.code == "slow_down":
            self._sync_auth_timer.start(self._sync_auth_timer.interval() + 5000)
            return
        self._sync_auth_timer.stop()
        self._device_flow_context = None
        self._update_sync_auth_state(self.bridge.get_sync_config())
        QMessageBox.warning(self, "GitHub 登录失败", str(exc))

    def _logout_github_device_flow(self):
        if self._sync_auth_timer.isActive():
            self._sync_auth_timer.stop()
        self._device_flow_context = None
        sync = self.bridge.logout_github()
        self._update_sync_settings_status(sync)
        self._update_sync_auth_state(sync)
        self._refresh_sync_settings_state()
        self._refresh_sync_scheduler_state(sync)
        self.status_bar.showMessage("GitHub 已退出登录", 3000)
        self._show_toast("GitHub 已退出登录")

    def _run_sync_cycle(self):
        self._run_sync_cycle_impl(from_timer=False)

    def _run_scheduled_sync_cycle(self):
        self._run_sync_cycle_impl(from_timer=True)

    def _run_sync_cycle_impl(self, from_timer: bool):
        if self._sync_cycle_running:
            return
        sync = self._save_sync_settings(show_feedback=False)
        if not sync:
            return

        workload = None
        if not from_timer:
            workload = self.bridge.preview_sync_workload()
            workload = self._confirm_initial_sync_workload(workload)
            if workload is None:
                return

        runtime_options = {"skip_paths": [], "force_upload_paths": []}
        if not from_timer and sync.get("oversize_action") == "prompt":
            runtime_options = self._prompt_oversize_entries(sync) or None
            if runtime_options is None:
                return

        self._sync_cycle_running = True
        self._sync_cycle_from_timer = from_timer
        self._sync_cycle_summary = self._describe_sync_workload(workload) if workload else ""
        self._sync_progress_text = ""
        self._sync_runtime_options = runtime_options
        self._sync_uploaded_preview_count = 0
        self._set_sync_busy_state(True)
        if self._sync_cycle_summary:
            self.status_bar.showMessage(f"正在后台同步，预计处理 {self._sync_cycle_summary}", 5000)
        else:
            self.status_bar.showMessage("正在后台同步...", 3000)

        worker = SyncCycleWorker(self.bridge, runtime_options=runtime_options)
        worker.progress.connect(self._handle_sync_cycle_progress)
        worker.finished.connect(self._handle_sync_cycle_finished)
        worker.failed.connect(self._handle_sync_cycle_failed)
        worker.finished.connect(worker.deleteLater)
        worker.failed.connect(worker.deleteLater)
        self._sync_worker = worker
        worker.start()

    def _handle_sync_cycle_finished(self, result: dict):
        latest_sync = self.bridge.get_sync_config()
        self._update_sync_settings_status(latest_sync)
        self._update_sync_auth_state(latest_sync)
        self._refresh_sync_scheduler_state(latest_sync)
        self._refresh_sync_preview(latest_sync)
        self.bridge.append_sync_history(result.get("message") or "同步完成", "成功", event_type="success")
        self._refresh_sync_history(latest_sync)
        self._finalize_sync_cycle()
        self.status_bar.showMessage(result.get("message") or "同步完成", 5000)
        self._show_toast("定时同步已运行" if self._sync_cycle_from_timer else "同步骨架已运行")

    def _handle_sync_cycle_progress(self, message: str):
        self._sync_progress_text = message
        self._pending_sync_progress_message = message
        if not self._sync_progress_ui_timer.isActive():
            self._sync_progress_ui_timer.start(90)
        self.status_bar.showMessage(message, 5000)

    def _handle_sync_cycle_failed(self, error_text: str):
        self.bridge.append_sync_history(error_text, "失败", event_type="failed")
        self._refresh_sync_history(self.bridge.get_sync_config())
        self._finalize_sync_cycle()
        if self._sync_cycle_from_timer:
            self.status_bar.showMessage(f"定时同步失败: {error_text}", 5000)
        else:
            QMessageBox.warning(self, "同步失败", error_text)

    def _finalize_sync_cycle(self):
        self._sync_cycle_running = False
        self._sync_cycle_summary = ""
        self._sync_progress_text = ""
        self._sync_runtime_options = {}
        self._sync_uploaded_preview_count = 0
        self._pending_sync_progress_message = ""
        self._sync_progress_ui_timer.stop()
        self._set_sync_busy_state(False)
        self._sync_worker = None

    def _flush_sync_progress_ui(self):
        message = self._pending_sync_progress_message.strip()
        if not message or not self._sync_widgets:
            return
        detail = self._build_sync_status_text()
        if detail:
            self._sync_widgets["status_label"].setText(detail)
        self._update_sync_progress_widgets(message)
        self._refresh_sync_history()

    def _set_sync_busy_state(self, busy: bool):
        if not self._sync_widgets:
            return
        save_btn = self._sync_widgets["save_btn"]
        sync_now_btn = self._sync_widgets["sync_now_btn"]
        status_label = self._sync_widgets["status_label"]

        save_btn.setEnabled(not busy)
        sync_now_btn.setEnabled(not busy)
        if busy:
            self._sync_widgets["login_btn"].setEnabled(False)
            self._sync_widgets["logout_btn"].setEnabled(False)
            self._sync_widgets["progress_bar"].setRange(0, 0)
            self._sync_widgets["progress_bar"].setFormat("同步中")
            self._refresh_sync_queue_statuses(fallback_status="准备中")
        sync_now_btn.setText("同步中..." if busy else "立即同步")

        if busy:
            status_label.setText(self._build_sync_status_text())
        else:
            latest_sync = self.bridge.get_sync_config()
            self._update_sync_settings_status(latest_sync)
            self._update_sync_auth_state(latest_sync)
            self._refresh_sync_preview(latest_sync)

    def _refresh_sync_scheduler_state(self, sync: dict | None = None):
        if sync is None:
            sync = self.bridge.get_sync_config()
        should_schedule = (
            sync.get("enabled")
            and sync.get("sync_mode") == "scheduled"
            and bool((sync.get("access_token") or "").strip())
            and bool((sync.get("repo_owner") or "").strip())
            and bool((sync.get("repo_name") or "").strip())
        )
        if should_schedule and not sync.get("last_sync_at") and (sync.get("upload_sessions") or sync.get("upload_assets")):
            self._scheduled_sync_timer.stop()
            return
        if not should_schedule:
            self._scheduled_sync_timer.stop()
            return
        interval_ms = max(5, int(sync.get("sync_interval_minutes") or 30)) * 60 * 1000
        self._scheduled_sync_timer.start(interval_ms)

    def _confirm_initial_sync_workload(self, workload: dict) -> dict | None:
        if not workload.get("first_sync"):
            return workload
        if workload.get("total_items", 0) < self._INITIAL_SYNC_CONFIRM_ITEMS and workload.get("total_bytes", 0) < self._INITIAL_SYNC_CONFIRM_BYTES:
            return workload

        detail_lines = [
            "当前还没有同步基线，这次会按历史全量补传。",
            f"预计会话：{workload['sessions']['count']} 个，约 {self._format_bytes(workload['sessions']['bytes'])}",
            f"预计资产：{workload['assets']['count']} 个，约 {self._format_bytes(workload['assets']['bytes'])}",
            f"合计：{workload['total_items']} 项，约 {self._format_bytes(workload['total_bytes'])}",
            "如果你只是想让后续增量同步立即可用，建议先建立基线，从现在开始同步。",
        ]

        dialog = QMessageBox(self)
        dialog.setIcon(QMessageBox.Warning)
        dialog.setWindowTitle("首次同步确认")
        dialog.setText("检测到首次同步体量较大")
        dialog.setInformativeText("\n".join(detail_lines))

        baseline_btn = dialog.addButton("从现在开始同步", QMessageBox.AcceptRole)
        full_sync_btn = dialog.addButton("继续全量补传", QMessageBox.ActionRole)
        cancel_btn = dialog.addButton("取消", QMessageBox.RejectRole)
        dialog.setDefaultButton(baseline_btn)
        dialog.exec_()

        clicked = dialog.clickedButton()
        if clicked is baseline_btn:
            sync = self.bridge.mark_sync_baseline_now()
            self.bridge.append_sync_history("已建立同步基线，本次只同步当前之后的新变化。", "已设基线", event_type="baseline")
            self._update_sync_settings_status(sync)
            self._update_sync_auth_state(sync)
            self._refresh_sync_scheduler_state(sync)
            self._refresh_sync_history(sync)
            self.status_bar.showMessage("已建立同步基线，本次只同步当前之后的新变化", 5000)
            self._show_toast("已建立同步基线")
            return self.bridge.preview_sync_workload()
        if clicked is full_sync_btn:
            return workload
        if clicked is cancel_btn:
            return None
        return None

    @staticmethod
    def _format_bytes(value: int) -> str:
        size = float(max(0, value))
        units = ["B", "KB", "MB", "GB", "TB"]
        for unit in units:
            if size < 1024.0 or unit == units[-1]:
                return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
            size /= 1024.0
        return f"{size:.1f} TB"

    def _describe_sync_workload(self, workload: dict | None) -> str:
        if not workload:
            return ""
        parts = []
        memories = workload.get("memories") or {}
        sessions = workload.get("sessions") or {}
        assets = workload.get("assets") or {}
        if memories.get("count"):
            parts.append(f"{memories['count']} 条记忆（{self._format_bytes(int(memories.get('bytes') or 0))}）")
        if sessions.get("count"):
            parts.append(f"{sessions['count']} 个会话（{self._format_bytes(int(sessions.get('bytes') or 0))}）")
        if assets.get("count"):
            parts.append(f"{assets['count']} 个资产（{self._format_bytes(int(assets.get('bytes') or 0))}）")
        if not parts:
            return "本地暂无待补传的大文件"
        return "、".join(parts)

    def _build_sync_status_text(self) -> str:
        pieces = []
        if self._sync_progress_text:
            pieces.append(f"当前进度：{self._sync_progress_text}")
        if self._sync_cycle_summary:
            pieces.append(f"预计处理：{self._sync_cycle_summary}")
        if not pieces:
            return "当前无进行中的同步任务\n首次上传原始会话和托管资产可能需要较长时间"
        pieces.append("请勿重复点击立即同步")
        return "\n".join(pieces)

    def _update_sync_progress_widgets(self, message: str):
        if not self._sync_widgets:
            return
        upload_match = re.search(r"正在上传 GitHub 文件\s+(\d+)/(\d+):\s+(.+)$", message)
        if upload_match:
            current = int(upload_match.group(1))
            total = int(upload_match.group(2))
            self._sync_uploaded_preview_count = max(self._sync_uploaded_preview_count, current - 1)
            self._sync_widgets["progress_bar"].setRange(0, max(total, 1))
            self._sync_widgets["progress_bar"].setValue(min(current, total))
            self._sync_widgets["progress_bar"].setFormat(f"{min(current, total)}/{total}")
            self._refresh_sync_queue_statuses(
                uploaded_count=max(0, current - 1),
                active_index=(current - 1) if 0 <= current - 1 < len(self._sync_preview_entries) else None,
            )
            self._sync_widgets["progress_label"].setText(f"正在上传 {min(current, total)}/{total}")
            return

        self._sync_widgets["progress_label"].setText(message)
        self._sync_widgets["progress_bar"].setRange(0, 0)
        self._sync_widgets["progress_bar"].setFormat("同步中")
        self._refresh_sync_queue_statuses(
            uploaded_count=self._sync_uploaded_preview_count,
            status_overrides={str(entry.get("path") or ""): message for entry in self._sync_preview_entries[self._sync_uploaded_preview_count:]},
            fallback_status="准备中",
        )

    def _prompt_oversize_entries(self, sync: dict) -> dict | None:
        limit_bytes = int(sync.get("upload_size_limit_mb") or 0) * 1024 * 1024
        if limit_bytes <= 0:
            return {"skip_paths": [], "force_upload_paths": []}

        entries = [
            entry for entry in self.bridge.preview_sync_entries(limit=500)
            if int(entry.get("size") or 0) > limit_bytes and not entry.get("whitelisted")
        ]
        if not entries:
            return {"skip_paths": [], "force_upload_paths": []}

        dialog = QDialog(self)
        dialog.setWindowTitle("超限上传确认")
        dialog.resize(760, 560)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("检测到超限内容")
        title.setStyleSheet(f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;")
        layout.addWidget(title)

        subtitle = QLabel(f"以下内容超过当前限制 {sync.get('upload_size_limit_mb')} MB。请在同步开始前确认每一项是继续上传还是跳过。")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(subtitle)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QScrollArea.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)

        scroll_content = QWidget()
        scroll_layout = QVBoxLayout(scroll_content)
        scroll_layout.setContentsMargins(0, 0, 6, 0)
        scroll_layout.setSpacing(10)

        decision_rows: list[tuple[str, QComboBox]] = []
        for entry in entries:
            row = QFrame()
            row.setObjectName("settings_subsection")
            row_layout = QHBoxLayout(row)
            row_layout.setContentsMargins(12, 10, 12, 10)
            row_layout.setSpacing(10)

            info = QLabel(f"{entry.get('name')}\n{self._format_bytes(int(entry.get('size') or 0))}\n{entry.get('path')}")
            info.setWordWrap(True)
            info.setStyleSheet(f"color: {C['text']}; font-size: 12px; background: transparent; border: none;")
            row_layout.addWidget(info, 1)

            choice = QComboBox()
            choice.addItem("继续上传", "upload")
            choice.addItem("跳过本项", "skip")
            choice.setCurrentIndex(1)
            decision_rows.append((str(entry.get("path") or ""), choice))
            row_layout.addWidget(choice)
            scroll_layout.addWidget(row)

        scroll_layout.addStretch(1)
        scroll.setWidget(scroll_content)
        layout.addWidget(scroll, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        confirm_btn = QPushButton("开始同步")
        confirm_btn.setStyleSheet(primary_btn_style())
        confirm_btn.clicked.connect(dialog.accept)
        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(secondary_btn_style())
        cancel_btn.clicked.connect(dialog.reject)
        button_row.addWidget(confirm_btn)
        button_row.addWidget(cancel_btn)
        layout.addLayout(button_row)

        if dialog.exec_() != QDialog.Accepted:
            return None

        force_upload_paths = []
        skip_paths = []
        for entry_path, choice in decision_rows:
            if choice.currentData() == "upload":
                force_upload_paths.append(entry_path)
            else:
                skip_paths.append(entry_path)
        return {
            "skip_paths": skip_paths,
            "force_upload_paths": force_upload_paths,
        }

    def _show_sync_detail_dialog(self):
        sync = self._collect_sync_form_state()
        entries = self.bridge.preview_sync_entries(limit=12)
        total = max(1, len(entries))
        uploaded = entries[:min(3, len(entries))]
        active = entries[min(3, len(entries)):min(5, len(entries))]
        pending = entries[min(5, len(entries)):]
        progress = int(((len(uploaded) + (0.5 if active else 0.0)) / total) * 100) if entries else 0

        dialog = QDialog(self)
        dialog.setWindowTitle("同步详情")
        dialog.resize(980, 620)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("同步详情")
        title.setStyleSheet(f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;")
        layout.addWidget(title)

        subtitle = QLabel("查看已上传、正在上传和等待上传的内容。")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(subtitle)

        progress_label = QLabel(f"当前进度：{progress}%")
        progress_label.setStyleSheet(f"color: {C['subtext1']}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(progress_label)

        progress_bar = QProgressBar()
        progress_bar.setRange(0, 100)
        progress_bar.setValue(progress)
        progress_bar.setFormat("%p%")
        progress_bar.setStyleSheet(
            f"QProgressBar {{ background: {_rgba(C['base'], 0.92)}; color: {C['text']}; border: 1px solid {_rgba(C['surface2'], 0.42)}; border-radius: 12px; text-align: center; padding: 3px; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {C['blue']}, stop:1 {C['teal']}); border-radius: 8px; }}"
        )
        layout.addWidget(progress_bar)

        columns = QHBoxLayout()
        columns.setSpacing(12)
        columns.addWidget(self._build_sync_detail_column("已上传", uploaded))
        columns.addWidget(self._build_sync_detail_column("正在上传", active))
        columns.addWidget(self._build_sync_detail_column("等待上传", pending))
        layout.addLayout(columns, 1)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(secondary_btn_style())
        close_btn.clicked.connect(dialog.accept)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        dialog.exec_()

    def _build_sync_detail_column(self, title: str, entries: list[dict]) -> QWidget:
        frame = QFrame()
        frame.setObjectName("settings_subsection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        label = QLabel(title)
        label.setStyleSheet(f"color: {C['text']}; font-size: 14px; font-weight: 800; background: transparent; border: none;")
        layout.addWidget(label)

        text = QTextEdit()
        text.setReadOnly(True)
        text.setMinimumWidth(280)
        text.setStyleSheet(
            f"QTextEdit {{ background: {_rgba(C['base'], 0.94)}; color: {C['text']}; border: 1px solid {_rgba(C['surface2'], 0.45)}; border-radius: 14px; padding: 10px; font-size: 12px; }}"
        )
        if not entries:
            text.setPlainText("暂无内容")
        else:
            lines = []
            for entry in entries:
                lines.append(f"{entry.get('name')}\n{self._format_bytes(int(entry.get('size') or 0))}\n{entry.get('path')}\n")
            text.setPlainText("\n".join(lines))
        layout.addWidget(text, 1)
        return frame

    def _build_sync_queue_panel(self) -> tuple[QWidget, QTableWidget]:
        frame = QFrame()
        frame.setObjectName("settings_subsection")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(10)

        header_row = QHBoxLayout()
        header_row.setContentsMargins(0, 0, 0, 0)
        header_row.setSpacing(10)

        label = QLabel("待同步摘要")
        label.setStyleSheet(f"color: {C['text']}; font-size: 15px; font-weight: 800; background: transparent; border: none;")
        header_row.addWidget(label)

        summary = QLabel("等待生成同步计划")
        summary.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 12px; background: {_rgba(C['surface0'], 0.62)}; border: 1px solid {_rgba(C['surface2'], 0.28)}; border-radius: 12px; padding: 6px 10px;"
        )
        header_row.addWidget(summary, 0, Qt.AlignRight)
        header_row.addStretch(1)
        layout.addLayout(header_row)

        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["文件名", "大小", "上传状态"])
        table.verticalHeader().setVisible(False)
        table.setAlternatingRowColors(False)
        table.setEditTriggers(QTableWidget.NoEditTriggers)
        table.setSelectionMode(QTableWidget.NoSelection)
        table.setFocusPolicy(Qt.NoFocus)
        table.setShowGrid(False)
        table.setWordWrap(True)
        table.horizontalHeader().setStretchLastSection(False)
        table.horizontalHeader().setSectionResizeMode(0, QHeaderView.Stretch)
        table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeToContents)
        table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeToContents)
        table.horizontalHeader().setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        table.setStyleSheet(
            f"QTableWidget {{ background: {_rgba(C['base'], 0.9)}; alternate-background-color: {_rgba(C['surface0'], 0.36)}; color: {C['text']}; border: 1px solid {_rgba(C['surface2'], 0.42)}; border-radius: 16px; font-size: 12px; gridline-color: transparent; selection-background-color: {_rgba(C['surface1'], 0.6)}; }}"
            f"QHeaderView::section {{ background: {_rgba(C['surface0'], 0.92)}; color: {C['subtext0']}; border: none; border-bottom: 1px solid {_rgba(C['surface2'], 0.35)}; padding: 10px 12px; font-size: 12px; font-weight: 700; }}"
            f"QTableWidget::item {{ border-bottom: 1px solid {_rgba(C['surface2'], 0.16)}; padding: 10px 12px; }}"
        )
        layout.addWidget(table, 1)
        self._sync_queue_summary_label = summary
        return frame, table

    def _format_sync_queue_item(self, entry: dict) -> str:
        name = entry.get("name") or "未命名"
        kind_map = {"session": "原始会话", "asset": "资产", "memory": "记忆"}
        kind = kind_map.get(entry.get("kind"), "条目")
        memory_type_map = {"episodic": "会话摘要", "semantic": "笔记", "procedural": "偏好"}
        path = entry.get("path") or ""
        if entry.get("kind") == "memory":
            kind = memory_type_map.get(entry.get("memory_type"), "记忆")
        compact_path = path if len(path) <= 72 else f"...{path[-69:]}"
        lines = [name, kind]
        if path:
            lines.append(compact_path)
        return "\n".join(lines)

    def _render_sync_queue(
        self,
        entries: list[dict],
        uploaded_count: int = 0,
        active_index: int | None = None,
        status_overrides: dict[str, str] | None = None,
        fallback_status: str = "等待上传",
    ):
        if not self._sync_widgets or "queue_table" not in self._sync_widgets:
            return
        table = self._sync_widgets["queue_table"]
        self._sync_queue_paths = [str(entry.get("path") or "") for entry in entries]
        self._sync_queue_status_cache = [""] * len(entries)
        table.setRowCount(len(entries))
        for row, entry in enumerate(entries):
            name_item = QTableWidgetItem(self._format_sync_queue_item(entry))
            size_item = QTableWidgetItem(self._format_bytes(int(entry.get("size") or 0)))
            name_item.setTextAlignment(Qt.AlignLeft | Qt.AlignVCenter)
            size_item.setTextAlignment(Qt.AlignRight | Qt.AlignVCenter)
            table.setItem(row, 0, name_item)
            table.setItem(row, 1, size_item)
            table.setRowHeight(row, 62)

        if not entries:
            table.setRowCount(1)
            table.setItem(0, 0, QTableWidgetItem("暂无待上传内容"))
            table.setItem(0, 1, QTableWidgetItem("-"))
            table.setRowHeight(0, 46)

        self._refresh_sync_queue_statuses(uploaded_count, active_index, status_overrides, fallback_status)

    def _refresh_sync_queue_statuses(
        self,
        uploaded_count: int = 0,
        active_index: int | None = None,
        status_overrides: dict[str, str] | None = None,
        fallback_status: str = "等待上传",
    ):
        if not self._sync_widgets or "queue_table" not in self._sync_widgets:
            return
        table = self._sync_widgets["queue_table"]
        status_overrides = status_overrides or {}
        status_counts: dict[str, int] = {}
        if not self._sync_preview_entries:
            if table.rowCount() == 0:
                table.setRowCount(1)
            table.setItem(0, 2, QTableWidgetItem("空闲"))
            if hasattr(self, "_sync_queue_summary_label"):
                self._sync_queue_summary_label.setText("当前队列为空")
            return

        for row, entry in enumerate(self._sync_preview_entries):
            path = self._sync_queue_paths[row] if row < len(self._sync_queue_paths) else str(entry.get("path") or "")
            status = status_overrides.get(path, fallback_status)
            if row < uploaded_count:
                status = "上传成功"
            elif active_index is not None and row == active_index:
                status = "正在上传"
            status_counts[status] = status_counts.get(status, 0) + 1
            cached_status = self._sync_queue_status_cache[row] if row < len(self._sync_queue_status_cache) else ""
            if cached_status == status:
                continue
            status_item = QTableWidgetItem(status)
            status_item.setTextAlignment(Qt.AlignCenter)

            status_color_map = {
                "上传成功": C["green"],
                "正在上传": C["blue"],
                "超限待确认": C["yellow"],
                "等待上传": C["subtext1"],
                "准备中": C["subtext0"],
            }
            status_color = QColor(status_color_map.get(status, C["subtext0"]))
            status_bg = QColor(status_color)
            status_bg.setAlpha(38)
            status_item.setForeground(QBrush(status_color))
            status_item.setBackground(QBrush(status_bg))
            table.setItem(row, 2, status_item)
            if row < len(self._sync_queue_status_cache):
                self._sync_queue_status_cache[row] = status

        if hasattr(self, "_sync_queue_summary_label"):
            if not self._sync_preview_entries:
                self._sync_queue_summary_label.setText("当前队列为空")
            else:
                waiting_count = status_counts.get("等待上传", 0)
                active_count = status_counts.get("正在上传", 0)
                success_count = status_counts.get("上传成功", 0)
                oversize_count = status_counts.get("超限待确认", 0)
                self._sync_queue_summary_label.setText(
                    f"共 {len(self._sync_preview_entries)} 项  ·  上传成功 {success_count}  ·  正在上传 {active_count}  ·  等待上传 {waiting_count}  ·  超限待确认 {oversize_count}"
                )

    def _show_oversize_dialog(self):
        sync = self._collect_sync_form_state()
        limit_bytes = int(sync.get("upload_size_limit_mb") or 0) * 1024 * 1024
        entries = [
            entry for entry in self.bridge.preview_sync_entries(limit=20)
            if limit_bytes > 0 and int(entry.get("size") or 0) > limit_bytes
        ]

        dialog = QDialog(self)
        dialog.setWindowTitle("超限上传确认")
        dialog.resize(720, 520)
        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel("超限上传确认")
        title.setStyleSheet(f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;")
        layout.addWidget(title)

        subtitle = QLabel("超过大小限制的内容会在这里逐项确认，用户可以决定继续上传还是跳过。")
        subtitle.setWordWrap(True)
        subtitle.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
        layout.addWidget(subtitle)

        if not entries:
            empty = QLabel("当前没有超出限制的待同步项。")
            empty.setStyleSheet(f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;")
            layout.addWidget(empty)
        else:
            for entry in entries[:6]:
                row = QFrame()
                row.setObjectName("settings_subsection")
                row_layout = QHBoxLayout(row)
                row_layout.setContentsMargins(12, 10, 12, 10)
                row_layout.setSpacing(10)

                info = QLabel(f"{entry.get('name')}\n{self._format_bytes(int(entry.get('size') or 0))} / 限制 {sync.get('upload_size_limit_mb')} MB")
                info.setWordWrap(True)
                info.setStyleSheet(f"color: {C['text']}; font-size: 12px; background: transparent; border: none;")
                row_layout.addWidget(info, 1)

                choice = QComboBox()
                choice.addItem("继续上传", "upload")
                choice.addItem("跳过本项", "skip")
                choice.setCurrentIndex(1)
                row_layout.addWidget(choice)
                layout.addWidget(row)

        button_row = QHBoxLayout()
        button_row.addStretch(1)
        confirm_btn = QPushButton("确认选择")
        confirm_btn.setStyleSheet(primary_btn_style())
        confirm_btn.clicked.connect(dialog.accept)
        close_btn = QPushButton("关闭")
        close_btn.setStyleSheet(secondary_btn_style())
        close_btn.clicked.connect(dialog.reject)
        button_row.addWidget(confirm_btn)
        button_row.addWidget(close_btn)
        layout.addLayout(button_row)

        dialog.exec_()

    def _refresh_settings_panel(self):
        shared_style = (
            f"QFrame#settings_nav {{ background: {_rgba(C['surface0'], 0.82)}; border: 1px solid {_rgba(C['surface2'], 0.28)}; border-radius: 18px; }}"
            f"QWidget#settings_page {{ background: transparent; border: none; }}"
            f"QScrollArea#settings_scroll {{ background: transparent; border: none; }}"
            f"QWidget#settings_scroll_viewport {{ background: {_rgba(C['mantle'], 0.94)}; border: none; border-radius: 18px; }}"
            f"QWidget#settings_content {{ background: {_rgba(C['mantle'], 0.94)}; border: none; }}"
            f"QFrame#settings_section {{ background: {_rgba(C['surface0'], 0.74)}; border: 1px solid {_rgba(C['surface2'], 0.28)}; border-radius: 18px; }}"
            f"QFrame#settings_subsection {{ background: {_rgba(C['base'], 0.72)}; border: 1px solid {_rgba(C['surface2'], 0.24)}; border-radius: 16px; }}"
            f"QLabel#settings_title {{ color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none; }}"
            f"QLabel#settings_section_title {{ color: {C['subtext0']}; font-size: 12px; font-weight: 800; background: transparent; border: none; }}"
            f"QTextEdit {{ background: {_rgba(C['surface0'], 0.9)}; color: {C['text']}; border: 1px solid {_rgba(C['surface2'], 0.48)}; border-radius: 14px; padding: 8px 10px; font-size: 12px; }}"
            f"QProgressBar {{ background: {_rgba(C['base'], 0.92)}; color: {C['text']}; border: 1px solid {_rgba(C['surface2'], 0.42)}; border-radius: 12px; text-align: center; padding: 3px; }}"
            f"QProgressBar::chunk {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {C['blue']}, stop:1 {C['teal']}); border-radius: 8px; }}"
        )
        if self._settings_dialog:
            self._settings_dialog.setStyleSheet(
                f"QDialog#settings_dialog {{ background: {_rgba(C['base'], 0.985)}; border: 1px solid {_rgba(C['surface2'], 0.48)}; border-radius: 20px; }}"
                + shared_style
            )
        if self.settings_tab is not None:
            self.settings_tab.setStyleSheet(shared_style)
        viewport_style = f"QWidget {{ background: {_rgba(C['mantle'], 0.94)}; border: none; border-radius: 18px; }}"
        content_style = f"QWidget {{ background: {_rgba(C['mantle'], 0.94)}; border: none; }}"
        for viewport in self._settings_scroll_viewports:
            if viewport is not None:
                viewport.setStyleSheet(viewport_style)
        for content in self._settings_page_contents:
            if content is not None:
                content.setStyleSheet(content_style)
        active_settings_index = next((index for index, btn in enumerate(self._settings_nav_buttons) if btn.isChecked()), None)
        if active_settings_index is not None:
            self._refresh_settings_nav_state(active_settings_index)
        if self._sync_subpages is not None:
            self._refresh_sync_subnav_state(self._sync_subpages.currentIndex())
        if hasattr(self, "theme_switch") and self.theme_switch is not None:
            self.theme_switch.setStyleSheet(
                f"QFrame {{ background: {_rgba(C['base'], 0.95)}; border: 1px solid {_rgba(C['surface2'], 0.34)}; border-radius: 18px; }}"
            )
        if hasattr(self, "import_btn") and self.import_btn is not None:
            self.import_btn.setStyleSheet(secondary_btn_style())
        if hasattr(self, "export_btn") and self.export_btn is not None:
            self.export_btn.setStyleSheet(self._tool_button_style())
        self._refresh_sync_control_styles()
        self._refresh_sync_settings_state()
        self._sync_theme_state()

    def _show_settings_panel(self):
        self.tabs.setCurrentIndex(len(_TAB_META) - 1)

    def _build_section_banner(self) -> QWidget:
        banner = QFrame()
        banner.setObjectName("section_banner")

        layout = QHBoxLayout(banner)
        layout.setContentsMargins(20, 18, 20, 18)
        layout.setSpacing(18)

        text_layout = QVBoxLayout()
        text_layout.setContentsMargins(0, 0, 0, 0)
        text_layout.setSpacing(6)

        self.section_kicker = QLabel("态势总览")
        self.section_kicker.setObjectName("section_kicker")
        text_layout.addWidget(self.section_kicker)

        self.section_title = QLabel("总览")
        self.section_title.setObjectName("section_title")
        text_layout.addWidget(self.section_title)

        self.section_subtitle = QLabel("")
        self.section_subtitle.setObjectName("section_subtitle")
        self.section_subtitle.setWordWrap(True)
        text_layout.addWidget(self.section_subtitle)
        layout.addLayout(text_layout, 1)

        metrics_layout = QHBoxLayout()
        metrics_layout.setContentsMargins(0, 0, 0, 0)
        metrics_layout.setSpacing(12)

        metrics_layout.addWidget(self._build_metric_card("active", "活跃记忆", "blue"))
        metrics_layout.addWidget(self._build_metric_card("entities", "实体节点", "teal"))
        metrics_layout.addWidget(self._build_metric_card("assets", "有效资产", "yellow"))
        layout.addLayout(metrics_layout)

        return banner

    def _build_metric_card(self, key: str, title: str, color_key: str) -> QWidget:
        frame = QFrame()
        frame.setProperty("bannerMetric", True)
        frame.setMinimumWidth(128)

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(4)

        label = QLabel(title)
        label.setObjectName("metric_label")
        layout.addWidget(label)

        value = QLabel("0")
        value.setObjectName("metric_value")
        value.setStyleSheet(
            f"color: {C[color_key]}; background: transparent; border: none; font-size: 22px; font-weight: 800;"
        )
        layout.addWidget(value)

        self._metric_values[key] = (value, color_key)
        return frame

    def _nav_btn_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                f"stop:0 {_rgba(C['surface1'], 0.98)}, stop:1 {_rgba(C['surface0'], 0.94)}); "
                f"color: {C['text']}; border: 1px solid {_rgba(C['blue'], 0.58)}; "
                f"border-left: 3px solid {C['blue']}; border-radius: 18px; "
                f"font-size: 11px; font-weight: 800; padding: 8px 4px 8px 8px; }}"
            )
        return (
            f"QPushButton {{ background: transparent; color: {C['subtext0']}; "
            f"border: 1px solid transparent; border-radius: 18px; "
            f"font-size: 11px; font-weight: 700; padding: 8px 6px; }}"
            f"QPushButton:hover {{ background: {_rgba(C['surface0'], 0.72)}; "
            f"border-color: {_rgba(C['surface2'], 0.38)}; color: {C['text']}; }}"
        )

    def _theme_btn_style(self, active: bool) -> str:
        if active:
            return (
                f"QPushButton {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, "
                f"stop:0 {C['blue']}, stop:1 {C['teal']}); color: white; border: none; "
                f"border-radius: 12px; font-size: 12px; font-weight: 800; padding: 0 10px; }}"
            )
        return (
            f"QPushButton {{ background: transparent; color: {C['subtext0']}; "
            f"border: 1px solid transparent; border-radius: 12px; font-size: 12px; "
            f"font-weight: 700; padding: 0 10px; }}"
            f"QPushButton:hover {{ background: {_rgba(C['surface0'], 0.72)}; color: {C['text']}; }}"
        )

    def _tool_button_style(self) -> str:
        return (
            f"QToolButton {{ background: {_rgba(C['base'], 0.95)}; color: {C['text']}; "
            f"border: 1px solid {_rgba(C['surface2'], 0.45)}; border-radius: 14px; "
            f"padding: 0 14px; font-size: 13px; font-weight: 700; }}"
            f"QToolButton:hover {{ border-color: {_rgba(C['blue'], 0.48)}; "
            f"background: {_rgba(C['surface0'], 0.78)}; }}"
            f"QToolButton::menu-indicator {{ image: none; }}"
        )

    def _sync_nav_state(self):
        current_index = self.tabs.currentIndex()
        for index, btn in enumerate(self._nav_buttons):
            btn.setChecked(index == current_index)
            btn.setStyleSheet(self._nav_btn_style(index == current_index))

    def _sync_theme_state(self):
        if self.current_theme not in THEMES:
            self.current_theme = next(iter(THEMES), DEFAULT_THEME)
        for theme_name, btn in self._theme_buttons.items():
            active = theme_name == self.current_theme
            btn.setChecked(active)
            btn.setStyleSheet(self._theme_btn_style(active))
        for theme_name, preview in self._theme_preview_cards.items():
            preview.setStyleSheet(self._theme_preview_card_style(theme_name, theme_name == self.current_theme))

    def _on_tab_changed(self, index: int):
        if index < 0 or index >= len(_TAB_META):
            return
        self._ensure_tab(index)
        self._sync_nav_state()
        self._refresh_workspace_context()
        if _TAB_META[index]["code"] == "CS" and not self.session_tab.has_loaded_data():
            self.session_tab.refresh()

    def _build_export_menu(self, target: QToolButton):
        from .components.exporter import FORMATS, _EXT_MAP
        menu = QMenu(target)
        menu.setStyleSheet(
            f"QMenu {{ background: {_rgba(C['base'], 0.98)}; color: {C['text']}; "
            f"border: 1px solid {_rgba(C['surface2'], 0.45)}; border-radius: 12px; padding: 6px; }}"
            f"QMenu::item {{ padding: 7px 16px; border-radius: 8px; }}"
            f"QMenu::item:selected {{ background: {_rgba(C['blue'], 0.12)}; }}"
        )

        categories = [
            ("全部", "all"),
            ("会话记录", "sessions"),
            ("会话摘要", "episodic"),
            ("笔记", "semantic"),
            ("偏好", "procedural"),
            ("资产列表", "assets"),
        ]
        for cat_label, cat_key in categories:
            sub = menu.addMenu(cat_label)
            sub.setStyleSheet(menu.styleSheet())
            for fmt in FORMATS:
                action = QAction(f"{fmt} ({_EXT_MAP[fmt]})", sub)
                action.triggered.connect(
                    lambda checked=False, k=cat_key, f=fmt: self._do_global_export(k, f)
                )
                sub.addAction(action)

        target.setMenu(menu)

    def _refresh_workspace_context(self):
        if not hasattr(self, "tabs"):
            return

        index = self.tabs.currentIndex()
        if index < 0 or index >= len(_TAB_META):
            return

        meta = _TAB_META[index]
        stats = self.bridge.get_stats()

        self.command_badge.setText(meta["code"])
        self.command_title.setText(meta["kicker"])
        self.command_card.setToolTip(
            f"{meta['desc']} 当前系统中有 {stats['active']} 条活跃记忆、{stats['entities']} 个实体节点。"
        )
        self._sync_topbar_context(index)

        if hasattr(self, "section_kicker"):
            self.section_kicker.setText(meta["kicker"])
            self.section_title.setText(meta["label"])
            self.section_subtitle.setText(f"{meta['desc']} 可使用 Ctrl+1 到 Ctrl+8 快速切换工作区。")

        if self._metric_values:
            metric_map = {
                "active": stats["active"],
                "entities": stats["entities"],
                "assets": stats["assets_valid"],
            }
            for key, value in metric_map.items():
                label, color_key = self._metric_values[key]
                label.setText(str(value))
                label.setStyleSheet(
                    f"color: {C[color_key]}; background: transparent; border: none; font-size: 22px; font-weight: 800;"
                )

    def _clear_layout_widgets(self, layout: QHBoxLayout):
        while layout.count():
            item = layout.takeAt(0)
            widget = item.widget()
            if widget:
                widget.setParent(None)

    def _sync_topbar_context(self, index: int):
        self._clear_layout_widgets(self.context_summary_layout)
        self._clear_layout_widgets(self.context_actions_layout)

        tab = self.tabs.widget(index)
        if not hasattr(tab, "topbar_context_widgets"):
            self.context_summary_bar.hide()
            self.context_actions_bar.hide()
            return

        summary_widgets, action_widgets = tab.topbar_context_widgets()

        has_summary = False
        for widget in summary_widgets:
            if not widget:
                continue
            if isinstance(widget, QFrame):
                widget.setMinimumWidth(max(widget.minimumWidth(), 92))
                widget.setMaximumHeight(64)
                widget.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
                if widget.layout():
                    widget.layout().setContentsMargins(10, 8, 10, 8)
                    widget.layout().setSpacing(2)
            self.context_summary_layout.addWidget(widget, 0, Qt.AlignVCenter)
            has_summary = True

        has_actions = False
        for widget in action_widgets:
            if not widget:
                continue
            self.context_actions_layout.addWidget(widget, 0, Qt.AlignVCenter)
            has_actions = True

        self.context_summary_bar.setVisible(has_summary)
        self.context_actions_bar.setVisible(has_actions)

    def _collect_all_sessions(self) -> list:
        """收集所有框架的会话列表（含未缓存的框架）"""
        session_tab = self._ensure_tab(1)
        all_sessions = []
        cached_fws = set()
        for fw_key, sessions in session_tab._sessions_cache.items():
            all_sessions.extend(sessions)
            cached_fws.add(fw_key)
        for fw_key, sources in session_tab._fw_groups.items():
            if fw_key not in cached_fws:
                for source in sources:
                    try:
                        sessions = session_tab.scanner.list_sessions(source)
                        all_sessions.extend(sessions)
                    except Exception:
                        pass
        return all_sessions

    def _do_global_export(self, category: str, fmt: str):
        from .components.exporter import (
            format_memories, format_assets, format_session_list,
            save_with_dialog, export_all_as_zip, load_session_messages,
        )
        if category == "all":
            memories_by_type = {}
            for t in ("episodic", "semantic", "procedural"):
                mems = self.bridge.list_memories(types=[t])
                if mems:
                    memories_by_type[t] = mems
            assets = self.bridge.list_assets(valid_only=False)
            all_sessions = self._collect_all_sessions()
            all_sessions = load_session_messages(
                all_sessions, self.session_tab.scanner, self
            )

            if fmt == "HTML":
                from .components.exporter import export_all_html_zip
                result = export_all_html_zip(
                    memories_by_type, assets, all_sessions, None, self,
                )
            else:
                result = export_all_as_zip(memories_by_type, assets, all_sessions, fmt, self)
            if result:
                self.status_bar.showMessage(f"已导出到: {result}", 5000)
        elif category == "sessions":
            session_tab = self._ensure_tab(1)
            all_sessions = []
            for fw_key, sessions in session_tab._sessions_cache.items():
                all_sessions.extend(sessions)
            if not all_sessions:
                from PyQt5.QtWidgets import QMessageBox
                QMessageBox.information(self, "提示", "请先在「会话记录」页面扫描并加载会话列表")
                return
            content = format_session_list(all_sessions, fmt)
            save_with_dialog(content, "会话记录", fmt, self)
        elif category == "assets":
            assets = self.bridge.list_assets(valid_only=False)
            content = format_assets(assets, fmt)
            save_with_dialog(content, "资产列表", fmt, self)
        else:
            mems = self.bridge.list_memories(types=[category])
            type_cn = {"episodic": "会话摘要", "semantic": "笔记", "procedural": "偏好"}.get(category, category)
            content = format_memories(mems, fmt, title=type_cn)
            save_with_dialog(content, type_cn, fmt, self)

    def _on_import(self):
        from .import_handler import import_from_dialog
        if import_from_dialog(self.bridge, self):
            self._on_global_refresh()

    def _build_shortcuts(self):
        QShortcut(QKeySequence("Ctrl+F"), self).activated.connect(
            lambda: self.search_bar.setFocus()
        )
        QShortcut(QKeySequence("F5"), self).activated.connect(self._on_global_refresh)
        QShortcut(QKeySequence("Ctrl+I"), self).activated.connect(self._on_import)
        for i in range(min(self.tabs.count(), 9)):
            sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.activated.connect(lambda idx=i: self.tabs.setCurrentIndex(idx))
        QShortcut(QKeySequence("Escape"), self).activated.connect(self._on_escape)

    def _on_escape(self):
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, "exit_batch_mode"):
                tab.exit_batch_mode()

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            for url in event.mimeData().urls():
                if url.toLocalFile().endswith(".zip"):
                    event.acceptProposedAction()
                    return
        event.ignore()

    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()

    def dropEvent(self, event):
        for url in event.mimeData().urls():
            path = url.toLocalFile()
            if path.endswith(".zip"):
                self._import_from_path(path)
                return

    def _import_from_path(self, path: str):
        from .import_handler import import_from_path
        if import_from_path(self.bridge, path, self):
            self._on_global_refresh()

    def _refresh_toolbar(self):
        self.search_bar.setStyleSheet(lineedit_style())
        self.refresh_btn.setStyleSheet(primary_btn_style())
        self._sync_nav_state()
        self._sync_theme_state()
        self._refresh_workspace_context()
        self._refresh_settings_panel()
        if hasattr(self, "_toast"):
            self._toast.setStyleSheet(
                f"QLabel {{ background: {_rgba(C['base'], 0.98)}; color: {C['text']}; "
                f"border: 1px solid {_rgba(C['surface2'], 0.45)}; border-radius: 16px; "
                f"padding: 10px 16px; font-size: 13px; font-weight: bold; }}"
            )

    def _on_global_refresh(self):
        if self._refresh_in_progress or self._session_tab_busy:
            return

        self._set_refresh_busy(True)
        from PyQt5.QtWidgets import QApplication
        QApplication.processEvents()

        self._reload_themes_from_disk()

        for tab in self._tab_instances:
            if tab is None:
                continue
            if hasattr(tab, "refresh"):
                tab.refresh()
        self._update_status()

        if self.session_tab is None or not self.session_tab.is_busy():
            self._finish_global_refresh()

    def _on_session_tab_busy_changed(self, busy: bool):
        self._session_tab_busy = busy
        if self._refresh_in_progress and not busy:
            self._finish_global_refresh()
            return
        self._update_refresh_button_state()

    def _set_refresh_busy(self, busy: bool):
        self._refresh_in_progress = busy
        if busy:
            self.status_bar.showMessage("刷新中...", 0)
            self._refresh_anim_step = 0
            self._refresh_anim_timer.start()
            self._advance_refresh_button_text()
        else:
            self._refresh_anim_timer.stop()
            self.refresh_btn.setText("刷新")
        self._update_refresh_button_state()

    def _finish_global_refresh(self):
        if not self._refresh_in_progress:
            return

        self._set_refresh_busy(False)
        self._update_status()
        self.status_bar.showMessage("刷新成功", 3000)
        self._show_toast("刷新成功")

    def _update_refresh_button_state(self):
        self.refresh_btn.setEnabled(not (self._refresh_in_progress or self._session_tab_busy))

    def _advance_refresh_button_text(self):
        dots = "." * ((self._refresh_anim_step % 3) + 1)
        self.refresh_btn.setText(f"刷新中{dots}")
        self._refresh_anim_step += 1

    def _build_toast(self):
        self._refresh_anim_timer = QTimer(self)
        self._refresh_anim_timer.setInterval(220)
        self._refresh_anim_timer.timeout.connect(self._advance_refresh_button_text)
        self._refresh_anim_step = 0

        self._toast = QLabel(self)
        self._toast.setVisible(False)
        self._toast.setAttribute(Qt.WA_TransparentForMouseEvents, True)
        self._toast.setStyleSheet(
            f"QLabel {{ background: rgba(24, 24, 37, 235); color: {C['text']}; "
            f"border: 1px solid {C['surface1']}; border-radius: 10px; "
            f"padding: 10px 16px; font-size: 13px; font-weight: bold; }}"
        )

        self._toast_effect = QGraphicsOpacityEffect(self._toast)
        self._toast.setGraphicsEffect(self._toast_effect)
        self._toast_effect.setOpacity(0.0)

        self._toast_anim = QPropertyAnimation(self._toast_effect, b"opacity", self)
        self._toast_anim.setDuration(180)
        self._toast_anim.setEasingCurve(QEasingCurve.OutCubic)

        self._toast_hide_timer = QTimer(self)
        self._toast_hide_timer.setSingleShot(True)
        self._toast_hide_timer.timeout.connect(self._hide_toast)

    def _show_toast(self, text: str):
        self._toast_hide_timer.stop()
        self._toast_anim.stop()

        self._toast.setText(text)
        self._toast.adjustSize()
        x = (self.width() - self._toast.width()) // 2
        y = self.height() - self.status_bar.height() - self._toast.height() - 28
        self._toast.move(max(12, x), max(12, y))
        self._toast.raise_()
        self._toast.show()

        self._toast_anim.setStartValue(0.0)
        self._toast_anim.setEndValue(1.0)
        self._toast_anim.start()
        self._toast_hide_timer.start(1800)

    def _hide_toast(self):
        self._toast_anim.stop()
        self._toast_anim.setStartValue(self._toast_effect.opacity())
        self._toast_anim.setEndValue(0.0)
        try:
            self._toast_anim.finished.disconnect(self._toast.hide)
        except TypeError:
            pass
        self._toast_anim.finished.connect(self._toast.hide)
        self._toast_anim.start()

    def _on_search(self, query: str):
        search_tab = self._ensure_tab(7)
        search_tab.do_search(query)
        self.tabs.setCurrentWidget(search_tab)

    def _on_theme_change(self, theme_name: str):
        if theme_name not in THEMES:
            return
        self.current_theme = theme_name
        apply_theme(theme_name)
        save_default_theme(theme_name)
        self._rebuild_all()

    def _rebuild_all(self):
        self._apply_styles()
        self._refresh_toolbar()
        self._update_status()
        for tab in self._tab_instances:
            if tab is None:
                continue
            if hasattr(tab, "refresh_style"):
                tab.refresh_style()
            if hasattr(tab, "refresh"):
                tab.refresh()

    def _reload_themes_from_disk(self):
        self.current_theme = reload_theme_config(self.current_theme)
        self._rebuild_theme_switch_controls()
        self._apply_styles()
        self._refresh_toolbar()
        for tab in self._tab_instances:
            if tab is None:
                continue
            if hasattr(tab, "refresh_style"):
                tab.refresh_style()

    def _apply_styles(self):
        self.setStyleSheet(global_style())
        self.tabs.setStyleSheet("QTabWidget::pane { background: transparent; border: none; }")

    def _update_status(self):
        stats = self.bridge.get_stats()
        self.status_bar.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 12px; padding-left: 8px;"
        )
        self.status_bar.showMessage(
            f"记忆: {stats['active']}条活跃 / {stats['archived']}条归档 | "
            f"情景: {stats['episodic']} | 语义: {stats['semantic']} | 偏好: {stats['procedural']} | "
            f"实体: {stats['entities']} | 资产: {stats['assets_valid']}有效"
        )
        self._refresh_workspace_context()

    def _build_tray(self):
        if not QSystemTrayIcon.isSystemTrayAvailable():
            return
        icon = QIcon(str(_ICON_PATH)) if _ICON_PATH.exists() else self.windowIcon()
        self.tray = QSystemTrayIcon(icon, self)
        self.tray.setToolTip(APP_NAME)

        menu = QMenu()
        show_action = QAction("显示主窗口", self)
        show_action.triggered.connect(self._show_window)
        menu.addAction(show_action)

        menu.addSeparator()

        quit_action = QAction("退出", self)
        quit_action.triggered.connect(self._quit_app)
        menu.addAction(quit_action)

        self.tray.setContextMenu(menu)
        self.tray.activated.connect(self._on_tray_activated)
        self.tray.show()

    def _on_tray_activated(self, reason):
        if reason == QSystemTrayIcon.Trigger:
            self._show_window()

    def _show_window(self):
        self.showNormal()
        self.activateWindow()
        self.raise_()

    def _quit_app(self):
        self._really_quit = True
        from PyQt5.QtWidgets import QApplication
        QApplication.instance().quit()

    def closeEvent(self, event: QCloseEvent):
        if self._really_quit or not hasattr(self, 'tray') or not self.tray.isVisible():
            event.accept()
            return
        self.hide()
        event.ignore()
