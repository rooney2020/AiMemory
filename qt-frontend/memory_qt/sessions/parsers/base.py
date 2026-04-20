"""抽象解析器基类"""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from ..models import FrameworkType, SessionSource, SessionInfo


class BaseParser(ABC):
    """所有框架解析器的基类"""

    @property
    @abstractmethod
    def framework(self) -> FrameworkType:
        ...

    @abstractmethod
    def detect(self) -> list[SessionSource]:
        """扫描系统，返回检测到的数据源列表"""
        ...

    @abstractmethod
    def list_sessions(self, source: SessionSource) -> list[SessionInfo]:
        """列出某个数据源下的所有会话（不加载完整消息）"""
        ...

    @abstractmethod
    def load_messages(self, session: SessionInfo) -> SessionInfo:
        """加载指定会话的完整消息列表"""
        ...

    @staticmethod
    def _safe_stat_mtime(path: Path):
        """安全获取文件修改时间"""
        from datetime import datetime
        try:
            return datetime.fromtimestamp(path.stat().st_mtime)
        except OSError:
            return None
