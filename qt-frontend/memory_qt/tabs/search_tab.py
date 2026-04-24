"""搜索结果 — 多通道检索结果展示 + 会话记录搜索 + 详情面板"""

from PyQt5.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QScrollArea,
    QFrame, QSplitter, QMessageBox, QPushButton, QSizePolicy,
)
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QUrl

from ..constants import C
from ..theme import secondary_btn_style
from ..data_bridge import DataBridge
from ..components.memory_card import MemoryCard
from ..components.detail_panel import DetailPanel
from ..sessions.scanner import SessionScanner
from ..sessions.models import SessionInfo
from .search_workers import SessionSearchWorker, get_md_renderer


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


class SearchTab(QWidget):
    def __init__(self, bridge: DataBridge, parent=None):
        super().__init__(parent)
        self.bridge = bridge
        self._result_memories: dict[str, object] = {}
        self._session_scanner = SessionScanner()
        self._session_results: list[SessionInfo] = []
        self._session_worker = None
        self._metric_values = {}
        self._current_query = ""
        self._selected_memory_id: str | None = None
        self._selected_session_card = None
        self._session_card_map: dict[str, QFrame] = {}
        self._build_ui()

    def _build_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(14)

        hero = QFrame()
        self._hero_frame = hero
        hero.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Minimum)
        hero.setStyleSheet("QFrame { background: transparent; border: none; }")
        hero_layout = QHBoxLayout(hero)
        hero_layout.setContentsMargins(4, 2, 4, 0)
        hero_layout.setSpacing(16)

        hero_text = QVBoxLayout()
        hero_text.setContentsMargins(0, 0, 0, 0)
        hero_text.setSpacing(6)

        self._hero_kicker = QLabel("SEARCH / FUSION")
        self._hero_kicker.setVisible(False)
        hero_text.addWidget(self._hero_kicker, 0, Qt.AlignLeft)

        self.header = QLabel("融合搜索结果")
        hero_text.addWidget(self.header)

        self.result_info = QLabel("在上方搜索栏输入关键词后按回车搜索")
        self.result_info.setVisible(False)
        hero_text.addWidget(self.result_info)
        hero_text.addStretch(1)
        hero_layout.addLayout(hero_text, 1)

        metrics_row = QHBoxLayout()
        metrics_row.setContentsMargins(0, 0, 0, 0)
        metrics_row.setSpacing(10)
        metrics_row.addWidget(self._build_metric_card("memory", "命中记忆", "blue"))
        metrics_row.addWidget(self._build_metric_card("session", "命中会话", "teal"))
        metrics_row.addWidget(self._build_metric_card("query", "查询词长", "yellow"))
        hero_layout.addLayout(metrics_row)

        layout.addWidget(hero)
        hero.hide()

        self.detail = DetailPanel(show_actions=True, embed_buttons=False)
        self._show_actions_ref = True
        self.detail.show_placeholder("点击搜索结果查看详情")
        self.detail.edit_requested.connect(self._on_edit)
        self.detail.delete_requested.connect(self._on_delete)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setChildrenCollapsible(False)

        left_widget = QFrame()
        self._left_panel = left_widget
        left_layout = QVBoxLayout(left_widget)
        left_layout.setContentsMargins(16, 16, 16, 16)
        left_layout.setSpacing(12)

        self._stream_kicker = QLabel("RESULT STREAM")
        self._stream_kicker.setVisible(False)
        left_layout.addWidget(self._stream_kicker)

        self._stream_title = QLabel("多通道结果流")
        left_layout.addWidget(self._stream_title)

        self._stream_hint = QLabel("记忆结果和会话结果会按同一查询词汇总在左侧，右侧用于集中展开详情。")
        self._stream_hint.setWordWrap(True)
        left_layout.addWidget(self._stream_hint)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        scroll.setStyleSheet("background: transparent; border: none;")

        self.container = QWidget()
        self.results_layout = QVBoxLayout(self.container)
        self.results_layout.setContentsMargins(0, 0, 0, 0)
        self.results_layout.setSpacing(10)
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

        detail_text = QVBoxLayout()
        detail_text.setContentsMargins(0, 0, 0, 0)
        detail_text.setSpacing(4)

        self._detail_kicker = QLabel("DETAIL CANVAS")
        self._detail_kicker.setVisible(False)
        detail_text.addWidget(self._detail_kicker)

        self._detail_title = QLabel("详情画布")
        self._detail_title.setMinimumHeight(32)
        self._detail_title.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        detail_text.addWidget(self._detail_title)

        self._detail_hint = QLabel("点击左侧结果查看详情")
        self._detail_hint.setMinimumHeight(24)
        self._detail_hint.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Fixed)
        detail_text.addWidget(self._detail_hint)
        detail_header_layout.addLayout(detail_text)

        detail_actions = QHBoxLayout()
        detail_actions.setContentsMargins(0, 0, 0, 0)
        detail_actions.setSpacing(8)
        detail_actions.addStretch(1)
        for w in self.detail.get_action_widgets():
            detail_actions.addWidget(w)

        detail_header_layout.addLayout(detail_actions)

        right_layout.addWidget(detail_header)
        right_layout.addWidget(self.detail, 1)

        splitter.addWidget(left_widget)
        splitter.addWidget(right_widget)
        splitter.setSizes([420, 820])
        layout.addWidget(splitter, 1)

        self._apply_shell_styles()

    def topbar_context_widgets(self):
        summary_widgets = [frame for frame, *_ in self._metric_values.values()]
        return summary_widgets, []

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

    def _update_summary(self, memory_count: int, session_count: int, query: str):
        self._metric_values["memory"][2].setText(str(memory_count))
        self._metric_values["session"][2].setText(str(session_count))
        self._metric_values["query"][2].setText(str(len(query.strip())))

    def _set_detail_state(self, title: str, hint: str):
        self._detail_title.setText(title)
        self._detail_hint.setText(hint)

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
            f"color: {C['lavender']}; font-size: 11px; font-weight: 800; "
            f"background: {_rgba(C['lavender'], 0.12)}; border: 1px solid {_rgba(C['lavender'], 0.2)}; "
            f"border-radius: 999px; padding: 5px 10px;"
        )
        self.header.setStyleSheet(f"color: {C['text']}; font-size: 24px; font-weight: 800;")
        self.result_info.setStyleSheet(f"color: {C['subtext0']}; font-size: 13px;")
        for frame, label, value, color_key in self._metric_values.values():
            frame.setStyleSheet(
                f"QFrame {{ background: {_rgba(C['surface0'], 0.72)}; border: 1px solid {_rgba(C['surface2'], 0.28)}; border-radius: 16px; }}"
            )
            label.setStyleSheet(
                f"color: {C['subtext0']}; font-size: 11px; font-weight: 700; background: transparent; border: none;"
            )
            value.setStyleSheet(
                f"color: {C[color_key]}; font-size: 22px; font-weight: 800; background: transparent; border: none;"
            )
        self._left_panel.setStyleSheet(self._panel_style())
        self._stream_kicker.setStyleSheet(
            f"color: {C['blue']}; font-size: 11px; font-weight: 800; background: transparent; border: none;"
        )
        self._stream_title.setStyleSheet(
            f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;"
        )
        self._stream_hint.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;"
        )
        self._right_panel.setStyleSheet(self._panel_style())
        self._detail_header.setStyleSheet(self._sub_panel_style())
        self._detail_kicker.setStyleSheet(
            f"color: {C['teal']}; font-size: 11px; font-weight: 800; background: transparent; border: none;"
        )
        self._detail_title.setStyleSheet(
            f"color: {C['text']}; font-size: 18px; font-weight: 800; background: transparent; border: none;"
        )
        self._detail_hint.setStyleSheet(
            f"color: {C['subtext0']}; font-size: 12px; background: transparent; border: none;"
        )

    def do_search(self, query: str):
        self._current_query = query
        self.header.setText(f'融合搜索: "{query}"')
        self._result_memories.clear()
        self._session_results.clear()
        self._set_detail_state("详情画布", f"正在为“{query}”聚合记忆与会话结果")

        while self.results_layout.count():
            child = self.results_layout.takeAt(0)
            if child.widget():
                child.widget().deleteLater()

        self._selected_memory_id = None
        self._selected_session_card = None
        self._session_card_map.clear()

        results = self.bridge.search(query, top_k=20)

        mem_count = 0
        if results:
            section = QLabel("记忆")
            section.setStyleSheet(
                f"color: {C['lavender']}; font-size: 13px; font-weight: bold;"
                f" padding: 4px 0;"
            )
            self.results_layout.addWidget(section)

            for result in results:
                mem = self.bridge.get_memory(result.memory_id)
                if mem:
                    self._result_memories[mem.id] = mem
                    mem_count += 1

                    card = MemoryCard(mem)
                    card.clicked.connect(self._on_card_click)

                    channels = ", ".join(f"{k}={v:.2f}" for k, v in result.channels.items())
                    score_label = QLabel(f"score={result.score:.3f}  [{channels}]")
                    score_label.setStyleSheet(
                        f"color: {C['overlay0']}; font-size: 10px; padding-left: 12px;"
                    )

                    wrapper = QFrame()
                    wrapper_layout = QVBoxLayout(wrapper)
                    wrapper_layout.setContentsMargins(0, 0, 0, 0)
                    wrapper_layout.setSpacing(2)
                    wrapper_layout.addWidget(card)
                    wrapper_layout.addWidget(score_label)

                    self.results_layout.addWidget(wrapper)

        self._session_section_label = QLabel("会话记录 (搜索中...)")
        self._session_section_label.setStyleSheet(
            f"color: {C['teal']}; font-size: 13px; font-weight: bold;"
            f" padding: 12px 0 4px 0;"
        )
        self.results_layout.addWidget(self._session_section_label)

        self._session_placeholder = QLabel("正在搜索会话记录...")
        self._session_placeholder.setStyleSheet(
            f"color: {C['overlay0']}; font-size: 12px; padding-left: 8px;"
        )
        self.results_layout.addWidget(self._session_placeholder)
        self.results_layout.addStretch()

        self._session_worker = SessionSearchWorker(self._session_scanner, query)
        self._session_worker.finished.connect(self._on_session_search_done)
        self._session_worker.start()

        total_label = f"找到 {mem_count} 条记忆" if mem_count else "未找到匹配记忆"
        self.result_info.setText(total_label + " | 会话搜索中...")
        self._update_summary(mem_count, 0, query)

        if results:
            first_mem_id = results[0].memory_id
            if first_mem_id in self._result_memories:
                self.detail.show_memory(
                    self._result_memories[first_mem_id],
                    highlight_term=query,
                )
                self._set_detail_state("记忆详情", self._result_memories[first_mem_id].summary or "首条记忆结果")
        elif not results:
            self.detail.show_placeholder("等待会话搜索结果...")

    def _on_session_search_done(self, query: str, sessions: list[SessionInfo]):
        if query != self._current_query:
            return
        self._session_results = sessions

        if hasattr(self, '_session_placeholder') and self._session_placeholder:
            self._session_placeholder.deleteLater()
            self._session_placeholder = None

        if sessions:
            self._session_section_label.setText(f"会话记录 ({len(sessions)})")

            stretch = None
            if self.results_layout.count() > 0:
                last = self.results_layout.itemAt(self.results_layout.count() - 1)
                if last and last.widget() is None:
                    stretch = self.results_layout.takeAt(self.results_layout.count() - 1)

            for sess in sessions:
                card = self._make_session_card(sess)
                self.results_layout.addWidget(card)

            self.results_layout.addStretch()
        else:
            self._session_section_label.setText("会话记录 (0)")

        mem_count = len(self._result_memories)
        total = f"找到 {mem_count} 条记忆" if mem_count else "未找到匹配记忆"
        total += f"，{len(sessions)} 条会话"
        self.result_info.setText(total)
        self._update_summary(mem_count, len(sessions), query)

    def _make_session_card(self, sess: SessionInfo) -> QFrame:
        card = QFrame()
        self._apply_session_card_style(card, sess.framework.color_key, selected=False)
        card.setCursor(Qt.PointingHandCursor)

        layout = QVBoxLayout(card)
        layout.setContentsMargins(14, 12, 14, 12)
        layout.setSpacing(6)

        kicker = QLabel(sess.framework.value.upper())
        kicker.setStyleSheet(
            f"color: {C[sess.framework.color_key]}; font-size: 10px; font-weight: 800; background: transparent; border: none;"
        )
        layout.addWidget(kicker)

        title = sess.display_title.replace("\n", " ")
        if len(title) > 80:
            title = title[:80] + "..."
        title_label = QLabel(title)
        title_label.setWordWrap(True)
        title_label.setStyleSheet(
            f"color: {C['text']}; font-size: 13px; font-weight: 800; border: none; background: transparent;"
        )
        layout.addWidget(title_label)

        preview = (getattr(sess, 'first_user_message', '') or '').replace("\n", " ").strip()
        if preview:
            if len(preview) > 110:
                preview = preview[:110] + "..."
            preview_label = QLabel(preview)
            preview_label.setWordWrap(True)
            preview_label.setStyleSheet(
                f"color: {C['subtext0']}; font-size: 12px; border: none; background: transparent;"
            )
            layout.addWidget(preview_label)

        meta_parts = [sess.framework.value]
        if sess.display_time:
            meta_parts.append(sess.display_time)
        meta_parts.append(f"{sess.message_count} 条消息")
        if sess.workspace:
            meta_parts.append(sess.workspace)

        meta = QLabel(" · ".join(meta_parts))
        meta.setStyleSheet(
            f"color: {C['overlay0']}; font-size: 10px; border: none; background: transparent;"
        )
        layout.addWidget(meta)

        card.mousePressEvent = lambda e, s=sess, c=card: self._on_session_card_click(s, c)
        return card

    def _apply_session_card_style(self, card: QFrame, color_key: str, selected: bool):
        border = _rgba(C[color_key], 0.82) if selected else _rgba(C['surface2'], 0.38)
        bg_start = _rgba(C['surface0'], 0.88) if selected else _rgba(C['base'], 0.96)
        bg_end = _rgba(C['surface1'], 0.94) if selected else _rgba(C['surface0'], 0.9)
        card.setStyleSheet(
            f"QFrame {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {bg_start}, stop:1 {bg_end});"
            f" border: 1px solid {border}; border-left: 3px solid {C[color_key]}; border-radius: 16px; }}"
            f"QFrame:hover {{ border: 1px solid {_rgba(C[color_key], 0.62)}; border-left: 3px solid {C[color_key]}; }}"
        )

    def _on_session_card_click(self, sess: SessionInfo, card: QFrame):
        if self._selected_session_card and self._selected_session_card is not card:
            self._apply_session_card_style(self._selected_session_card, self._selected_session_card.property("fw_color_key"), selected=False)
        card.setProperty("fw_color_key", sess.framework.color_key)
        self._apply_session_card_style(card, sess.framework.color_key, selected=True)
        self._selected_session_card = card
        loaded = self._session_scanner.load_messages(sess)
        # 保存当前会话，用于展开跳过段
        self._current_session = loaded
        self._expanded_ranges = set()

        html, match_count = self._format_session_html(loaded, expanded_ranges=set())
        query = getattr(self, '_current_query', '')

        self.detail.show_session(html, highlight_term=query, match_count=match_count)
        self._set_detail_state("会话详情", f"{sess.framework.value} · {sess.display_title}")
        try:
            self.detail.browser.anchorClicked.disconnect()
        except:
            pass
        self.detail.browser.anchorClicked.connect(self._on_session_link_click)

    def _on_session_link_click(self, url: QUrl):
        """处理会话详情中的链接点击"""
        link = url.toString()
        if link.startswith("expand:"):
            # 展开跳过的消息
            range_str = link[7:]  # "expand:start-end"
            try:
                start, end = map(int, range_str.split("-"))
                expanded = getattr(self, '_expanded_ranges', set()) | {(start, end)}
                self._expanded_ranges = expanded
                html, match_count = self._format_session_html(self._current_session, expanded_ranges=expanded)
                query = getattr(self, '_current_query', '')
                self.detail.show_session(html, highlight_term=query, match_count=match_count)
            except:
                pass

    def _format_session_html(self, sess: SessionInfo, expanded_ranges: set = None) -> tuple[str, int]:
        """格式化会话为 HTML，支持智能筛选和可展开跳过段
        
        Args:
            sess: 会话信息
            expanded_ranges: 已展开的范围集合，如 {(5, 10), (15, 20)}
            
        Returns:
            (HTML, 匹配数)
        """
        from ..components.detail_formatters import detail_css as _detail_css, highlight_html as _highlight_html
        import html as _html
        
        if expanded_ranges is None:
            expanded_ranges = set()

        title = _html.escape(sess.display_title.replace("\n", " "))
        parts = [
            f'<html><head><style>{_detail_css()}</style></head><body>',
            f'<h1>{title}</h1>',
            f'<div class="meta-block">',
            f'<strong>框架:</strong> {sess.framework.value} &nbsp; ',
            f'<strong>消息:</strong> {sess.message_count} 条 &nbsp; ',
        ]
        if sess.workspace:
            parts.append(f'<strong>工作区:</strong> {_html.escape(sess.workspace)} &nbsp; ')
        if sess.display_time:
            parts.append(f'<strong>时间:</strong> {sess.display_time}')
        parts.append('</div>')

        query = getattr(self, '_current_query', '')

        match_indices = set()
        if query:
            from ..components.detail_formatters import split_terms
            terms = split_terms(query)
            for i, msg in enumerate(sess.messages):
                content_lower = msg.content.lower()
                if any(t in content_lower for t in terms):
                    match_indices.add(i)
        
        if not match_indices:
            messages_to_show = [('msg', i, msg) for i, msg in enumerate(sess.messages[:30])]
            remaining = len(sess.messages) - 30
        else:
            # 生成片段：每个匹配 + 前后各 1 条上下文
            fragments = []
            for idx in sorted(match_indices):
                start = max(0, idx - 1)
                end = min(len(sess.messages), idx + 2)  # end 是 exclusive
                fragments.append((start, end))
            
            # 合并相邻/重叠的片段
            merged = []
            for start, end in sorted(fragments):
                if merged and start <= merged[-1][1]:
                    merged[-1] = (merged[-1][0], max(merged[-1][1], end))
                else:
                    merged.append((start, end))
            
            # 添加已展开的范围
            for start, end in expanded_ranges:
                merged.append((start, end))
                merged.sort()
            
            # 再次合并
            final_merged = []
            for start, end in sorted(merged):
                if final_merged and start <= final_merged[-1][1]:
                    final_merged[-1] = (final_merged[-1][0], max(final_merged[-1][1], end))
                else:
                    final_merged.append((start, end))
            merged = final_merged
            
            # 生成消息列表（带跳过标记）
            messages_to_show = []
            last_end = 0
            for start, end in merged:
                if start > last_end:
                    # 跳过的部分
                    messages_to_show.append(('skip', last_end, start))
                messages_to_show.extend(('msg', i, sess.messages[i]) for i in range(start, end))
                last_end = end
            
            if last_end < len(sess.messages):
                messages_to_show.append(('skip', last_end, len(sess.messages)))
            
            remaining = 0

        total_matches = 0
        role_map = {"user": ("用户", C["blue"]), "assistant": ("AI", C["green"]), "tool": ("工具", C["yellow"])}

        for item in messages_to_show:
            if item[0] == 'skip':
                _, start, end = item
                count = end - start
                if count > 0:
                    parts.append(
                        f'<div style="margin: 12px 0; padding: 8px; text-align: center;'
                        f' background: {C["surface0"]}; border-radius: 4px;">'
                        f'<a href="expand:{start}-{end}" style="color: {C["blue"]}; text-decoration: none; cursor: pointer;">'
                        f'显示跳过的 {count} 条消息</a></div>'
                    )
            else:
                _, idx, msg = item
                role_name, role_color = role_map.get(msg.role, (msg.role, C["text"]))
                
                # 智能截断：如果消息包含关键词，截断包含关键词的部分
                max_len = 1500
                if query and len(msg.content) > max_len:
                    from ..components.detail_formatters import split_terms
                    terms = split_terms(query)
                    content_lower = msg.content.lower()
                    
                    # 找到第一个匹配词的位置
                    match_pos = -1
                    for t in terms:
                        pos = content_lower.find(t)
                        if pos != -1:
                            if match_pos == -1 or pos < match_pos:
                                match_pos = pos
                    
                    if match_pos != -1:
                        # 截断包含匹配的部分：前后各取一半
                        half = max_len // 2
                        start = max(0, match_pos - half)
                        end = min(len(msg.content), start + max_len)
                        # 确保完整字符（不截断中文）
                        content_raw = msg.content[start:end]
                        if start > 0:
                            content_raw = "..." + content_raw
                        if end < len(msg.content):
                            content_raw = content_raw + "..."
                    else:
                        content_raw = msg.content[:max_len]
                        if len(msg.content) > max_len:
                            content_raw += "..."
                else:
                    content_raw = msg.content[:max_len]
                    if len(msg.content) > max_len:
                        content_raw += "..."
                
                # 渲染 Markdown
                md = get_md_renderer()
                content = md.render(content_raw)
                
                # 高亮关键词（在 HTML 中进行）
                if query:
                    content_html, match_count = _highlight_html(content, query)
                    content = content_html
                    total_matches += match_count
                
                parts.append(
                    f'<div style="margin: 8px 0; padding: 8px 12px;'
                    f' background: {C["mantle"]}; border-radius: 6px;'
                    f' border-left: 3px solid {role_color};">'
                    f'<div style="font-size: 11px; color: {role_color}; font-weight: bold; margin-bottom: 4px;">{role_name}</div>'
                    f'<div style="font-size: 13px;">{content}</div>'
                    f'</div>'
                )

        if remaining > 0:
            parts.append(f'<p style="color: {C["overlay0"]}; text-align: center;">... 还有 {remaining} 条消息</p>')

        parts.append('</body></html>')
        return "\n".join(parts), total_matches

    def _on_card_click(self, mem_id: str):
        self._selected_memory_id = mem_id
        if mem_id in self._result_memories:
            for layout_index in range(self.results_layout.count()):
                item = self.results_layout.itemAt(layout_index)
                widget = item.widget() if item else None
                if not widget:
                    continue
                card = widget.findChild(MemoryCard)
                if card:
                    card.set_selected(card.memory_id == mem_id)
            self.detail.show_memory(
                self._result_memories[mem_id],
                highlight_term=getattr(self, '_current_query', ''),
            )
            self._set_detail_state("记忆详情", self._result_memories[mem_id].summary or mem_id)

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
                if hasattr(self, '_current_query') and self._current_query:
                    self.do_search(self._current_query)

    def _on_delete(self, mem_id: str):
        reply = QMessageBox.question(
            self, "确认归档",
            "确定要归档这条记忆吗？",
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            self.bridge.update_memory(mem_id, status="archived")
            self.detail.show_placeholder("记忆已归档")
            if hasattr(self, '_current_query') and self._current_query:
                self.do_search(self._current_query)

    def refresh_style(self):
        self._apply_shell_styles()
        self.detail.refresh_style()
        if self._current_query:
            self.do_search(self._current_query)

    def refresh(self):
        pass
