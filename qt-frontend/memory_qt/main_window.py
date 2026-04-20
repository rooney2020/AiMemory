"""主窗口 — Tab 容器 + 搜索栏 + 系统托盘"""

from pathlib import Path

from PyQt5.QtWidgets import (
    QMainWindow, QTabWidget, QVBoxLayout, QHBoxLayout,
    QWidget, QLabel, QStatusBar, QPushButton, QFrame, QSizePolicy,
    QSystemTrayIcon, QMenu, QAction, QToolButton, QGraphicsOpacityEffect, QDialog,
)
from PyQt5.QtGui import QIcon, QCloseEvent, QKeySequence
from PyQt5.QtCore import Qt, QMimeData, QUrl, QPropertyAnimation, QEasingCurve, QTimer
from PyQt5.QtWidgets import QShortcut

from .constants import C, THEMES, DEFAULT_THEME, APP_NAME, APP_VERSION
from .theme import apply_theme, global_style, lineedit_style, primary_btn_style, secondary_btn_style
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
]


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


class MainWindow(QMainWindow):
    def __init__(self, bridge: DataBridge):
        super().__init__()
        self.bridge = bridge
        self._really_quit = False
        self._refresh_in_progress = False
        self._session_tab_busy = False
        self.current_theme = DEFAULT_THEME
        self._nav_buttons = []
        self._theme_buttons = {}
        self._metric_values = {}
        self._settings_dialog = None
        self._settings_export_btn = None
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
        layout.setContentsMargins(18, 18, 18, 12)
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

        self.overview_tab = OverviewTab(self.bridge)
        self.episodic_tab = EpisodicTab(self.bridge)
        self.semantic_tab = SemanticTab(self.bridge)
        self.procedural_tab = ProceduralTab(self.bridge)
        self.asset_tab = AssetTab(self.bridge)
        self.graph_tab = GraphTab(self.bridge)
        self.search_tab = SearchTab(self.bridge)
        self.session_tab = SessionTab()
        self.session_tab.busy_changed.connect(self._on_session_tab_busy_changed)

        self.tabs.addTab(self.overview_tab, "总览")
        self.tabs.addTab(self.session_tab, "会话记录")
        self.tabs.addTab(self.episodic_tab, "会话摘要")
        self.tabs.addTab(self.semantic_tab, "笔记")
        self.tabs.addTab(self.procedural_tab, "偏好")
        self.tabs.addTab(self.asset_tab, "资产")
        self.tabs.addTab(self.graph_tab, "图谱")
        self.tabs.addTab(self.search_tab, "搜索")
        self.tabs.tabBar().hide()
        self.tabs.currentChanged.connect(self._on_tab_changed)

        canvas_layout.addWidget(self.tabs)
        workspace_layout.addWidget(canvas, 1)
        layout.addWidget(workspace, 1)

        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self._update_status()
        self._build_toast()
        self._on_tab_changed(0)

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

        self.settings_btn = QPushButton("设置")
        self.settings_btn.setObjectName("global_settings")
        self.settings_btn.setToolTip("打开主题与导入导出设置")
        self.settings_btn.setFixedSize(72, 34)
        self.settings_btn.clicked.connect(self._show_settings_panel)
        actions_layout.addWidget(self.settings_btn)

        layout.addWidget(actions_bar, 0, Qt.AlignRight)

        return toolbar

    def _build_settings_dialog(self):
        dialog = QDialog(self, Qt.Popup | Qt.FramelessWindowHint)
        dialog.setObjectName("settings_dialog")
        dialog.setModal(False)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(14)

        title = QLabel("设置")
        title.setObjectName("settings_title")
        layout.addWidget(title)

        theme_section = QFrame()
        theme_section.setObjectName("settings_section")
        theme_layout = QVBoxLayout(theme_section)
        theme_layout.setContentsMargins(14, 14, 14, 14)
        theme_layout.setSpacing(10)

        theme_title = QLabel("主题")
        theme_title.setObjectName("settings_section_title")
        theme_layout.addWidget(theme_title)

        theme_switch = QFrame()
        self.theme_switch = theme_switch
        theme_switch.setSizePolicy(QSizePolicy.Maximum, QSizePolicy.Fixed)
        self.theme_switch_layout = QHBoxLayout(theme_switch)
        self.theme_switch_layout.setContentsMargins(6, 6, 6, 6)
        self.theme_switch_layout.setSpacing(6)
        for theme_name in THEMES:
            btn = QPushButton(theme_name.split("·")[-1])
            btn.setCheckable(True)
            btn.setCursor(Qt.PointingHandCursor)
            btn.setFixedSize(48, 28)
            btn.clicked.connect(lambda checked=False, name=theme_name: self._on_theme_change(name))
            self._theme_buttons[theme_name] = btn
            self.theme_switch_layout.addWidget(btn)
        theme_layout.addWidget(theme_switch, 0, Qt.AlignLeft)
        layout.addWidget(theme_section)

        action_section = QFrame()
        action_section.setObjectName("settings_section")
        action_layout = QVBoxLayout(action_section)
        action_layout.setContentsMargins(14, 14, 14, 14)
        action_layout.setSpacing(10)

        action_title = QLabel("数据")
        action_title.setObjectName("settings_section_title")
        action_layout.addWidget(action_title)

        action_row = QHBoxLayout()
        action_row.setContentsMargins(0, 0, 0, 0)
        action_row.setSpacing(8)

        self.import_btn = QPushButton("导入")
        self.import_btn.setObjectName("global_import")
        self.import_btn.setToolTip("从 ZIP 文件导入记忆和资产")
        self.import_btn.setFixedSize(76, 34)
        self.import_btn.clicked.connect(self._on_import)
        action_row.addWidget(self.import_btn)

        self.export_btn = QToolButton()
        self.export_btn.setText("导出")
        self.export_btn.setObjectName("global_export")
        self.export_btn.setPopupMode(QToolButton.InstantPopup)
        self.export_btn.setToolButtonStyle(Qt.ToolButtonTextOnly)
        self.export_btn.setFixedSize(76, 34)
        self._build_export_menu(self.export_btn)
        action_row.addWidget(self.export_btn)
        action_row.addStretch(1)
        action_layout.addLayout(action_row)
        layout.addWidget(action_section)

        self._settings_dialog = dialog
        self._refresh_settings_panel()

    def _refresh_settings_panel(self):
        if not self._settings_dialog:
            return
        self._settings_dialog.setStyleSheet(
            f"QDialog#settings_dialog {{ background: {_rgba(C['base'], 0.985)}; border: 1px solid {_rgba(C['surface2'], 0.48)}; border-radius: 20px; }}"
            f"QFrame#settings_section {{ background: {_rgba(C['surface0'], 0.74)}; border: 1px solid {_rgba(C['surface2'], 0.28)}; border-radius: 18px; }}"
            f"QLabel#settings_title {{ color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none; }}"
            f"QLabel#settings_section_title {{ color: {C['subtext0']}; font-size: 12px; font-weight: 800; background: transparent; border: none; }}"
        )
        self.theme_switch.setStyleSheet(
            f"QFrame {{ background: {_rgba(C['base'], 0.95)}; border: 1px solid {_rgba(C['surface2'], 0.34)}; border-radius: 18px; }}"
        )
        self.import_btn.setStyleSheet(secondary_btn_style())
        self.export_btn.setStyleSheet(self._tool_button_style())
        self._sync_theme_state()

    def _show_settings_panel(self):
        if not self._settings_dialog:
            self._build_settings_dialog()

        self._refresh_settings_panel()
        if self._settings_dialog.isVisible():
            self._settings_dialog.hide()
            return

        anchor = self.settings_btn.mapToGlobal(self.settings_btn.rect().bottomRight())
        self._settings_dialog.adjustSize()
        panel_width = max(260, self._settings_dialog.width())
        x = anchor.x() - panel_width
        y = anchor.y() + 10
        self._settings_dialog.move(x, y)
        self._settings_dialog.show()
        self._settings_dialog.raise_()

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
        for theme_name, btn in self._theme_buttons.items():
            active = theme_name == self.current_theme
            btn.setChecked(active)
            btn.setStyleSheet(self._theme_btn_style(active))

    def _on_tab_changed(self, index: int):
        if index < 0 or index >= len(_TAB_META):
            return
        self._sync_nav_state()
        self._refresh_workspace_context()

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
        all_sessions = []
        cached_fws = set()
        for fw_key, sessions in self.session_tab._sessions_cache.items():
            all_sessions.extend(sessions)
            cached_fws.add(fw_key)
        for fw_key, sources in self.session_tab._fw_groups.items():
            if fw_key not in cached_fws:
                for source in sources:
                    try:
                        sessions = self.session_tab.scanner.list_sessions(source)
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
            all_sessions = []
            for fw_key, sessions in self.session_tab._sessions_cache.items():
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
        self.settings_btn.setStyleSheet(secondary_btn_style())
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

        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, "refresh"):
                tab.refresh()
        self._update_status()

        if not self.session_tab.is_busy():
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
        self.search_tab.do_search(query)
        self.tabs.setCurrentWidget(self.search_tab)

    def _on_theme_change(self, theme_name: str):
        if theme_name not in THEMES:
            return
        self.current_theme = theme_name
        apply_theme(theme_name)
        self._rebuild_all()

    def _rebuild_all(self):
        self._apply_styles()
        self._refresh_toolbar()
        self._update_status()
        for i in range(self.tabs.count()):
            tab = self.tabs.widget(i)
            if hasattr(tab, "refresh_style"):
                tab.refresh_style()
            if hasattr(tab, "refresh"):
                tab.refresh()

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
