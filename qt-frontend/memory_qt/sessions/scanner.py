"""会话记录扫描器 — 统一调度各框架解析器"""

from __future__ import annotations

from .models import SessionSource, SessionInfo
from .parsers import ALL_PARSERS, BaseParser


class SessionScanner:
    """扫描所有已知 AI 框架的会话记录"""

    def __init__(self):
        self._parsers: list[BaseParser] = [cls() for cls in ALL_PARSERS]
        self._sources: list[SessionSource] = []
        self._parser_map: dict[str, BaseParser] = {}

    def scan(self) -> list[SessionSource]:
        """扫描系统，检测所有框架的数据源"""
        self._sources.clear()
        self._parser_map.clear()

        for parser in self._parsers:
            try:
                sources = parser.detect()
                for src in sources:
                    key = f"{src.framework.value}:{src.base_path}"
                    self._parser_map[key] = parser
                self._sources.extend(sources)
            except Exception:
                continue

        return self._sources

    def list_sessions(self, source: SessionSource) -> list[SessionInfo]:
        """列出某个数据源下的会话"""
        parser = self._get_parser(source)
        if not parser:
            return []
        try:
            return parser.list_sessions(source)
        except Exception:
            return []

    def load_messages(self, session: SessionInfo) -> SessionInfo:
        """加载会话的完整消息"""
        for parser in self._parsers:
            if parser.framework == session.framework:
                try:
                    return parser.load_messages(session)
                except Exception:
                    return session
        return session

    def _get_parser(self, source: SessionSource) -> BaseParser | None:
        key = f"{source.framework.value}:{source.base_path}"
        if key in self._parser_map:
            return self._parser_map[key]
        for parser in self._parsers:
            if parser.framework == source.framework:
                return parser
        return None

    def grep_search(self, sources: list[SessionSource], query: str) -> list[str]:
        """用 grep 搜索会话文件内容，返回匹配的文件路径列表"""
        import subprocess
        from pathlib import Path

        matched_paths = []
        for source in sources:
            if not source.base_path or not Path(source.base_path).exists():
                continue
            try:
                # 用 grep -r 递归搜索
                result = subprocess.run(
                    ["grep", "-l", "-i", "-r", query, str(source.base_path)],
                    capture_output=True,
                    timeout=10,
                )
                if result.returncode == 0 and result.stdout:
                    for line in result.stdout.decode('utf-8', errors='ignore').strip().split('\n'):
                        if line:
                            matched_paths.append(line)
            except Exception:
                pass

        return matched_paths

    @property
    def sources(self) -> list[SessionSource]:
        return self._sources
