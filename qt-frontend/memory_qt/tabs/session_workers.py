"""会话扫描/加载后台线程"""

from datetime import datetime
from PyQt5.QtCore import QThread, pyqtSignal

from ..sessions.scanner import SessionScanner
from ..sessions.models import SessionSource, SessionInfo


class ScanWorker(QThread):
    finished = pyqtSignal(list)

    def __init__(self, scanner: SessionScanner):
        super().__init__()
        self.scanner = scanner

    def run(self):
        sources = self.scanner.scan()
        self.finished.emit(sources)


class FrameworkWarmupWorker(QThread):
    """预加载各框架会话元信息，用于首屏准确排序。"""

    finished = pyqtSignal(object, object)

    def __init__(self, scanner: SessionScanner, fw_groups: dict[str, list[SessionSource]]):
        super().__init__()
        self.scanner = scanner
        self.fw_groups = fw_groups

    def run(self):
        latest_times: dict[str, datetime] = {}
        sessions_cache: dict[str, list[SessionInfo]] = {}

        for fw_key, sources in self.fw_groups.items():
            all_sessions: list[SessionInfo] = []
            for src in sources:
                all_sessions.extend(self.scanner.list_sessions(src))

            all_sessions.sort(key=lambda s: s.updated_at or s.created_at or datetime.min, reverse=True)
            sessions_cache[fw_key] = all_sessions

            latest = max(
                (s.updated_at or s.created_at for s in all_sessions if s.updated_at or s.created_at),
                default=None,
            )
            if latest:
                latest_times[fw_key] = latest

        self.finished.emit(latest_times, sessions_cache)


class LoadWorker(QThread):
    finished = pyqtSignal(str, list)

    def __init__(self, scanner: SessionScanner, sources: list[SessionSource], fw_key: str):
        super().__init__()
        self.scanner = scanner
        self.sources = sources
        self.fw_key = fw_key

    def run(self):
        all_sessions: list[SessionInfo] = []
        for src in self.sources:
            all_sessions.extend(self.scanner.list_sessions(src))
        all_sessions.sort(key=lambda s: s.updated_at or datetime.min, reverse=True)
        self.finished.emit(self.fw_key, all_sessions)


class MessageLoadWorker(QThread):
    """后台线程加载会话消息，避免 I/O 阻塞主线程"""
    finished = pyqtSignal(str, object, int)

    def __init__(self, scanner: SessionScanner, session: SessionInfo, request_token: int):
        super().__init__()
        self.scanner = scanner
        self.session = session
        self.request_token = request_token

    def run(self):
        result = self.scanner.load_messages(self.session)
        self.finished.emit(self.session.id, result, self.request_token)
