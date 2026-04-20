"""搜索后台工作线程 — 会话内容 grep 搜索"""

from PyQt5.QtCore import QThread, pyqtSignal

from ..sessions.scanner import SessionScanner
from ..sessions.models import SessionInfo

_md_renderer = None


def get_md_renderer():
    global _md_renderer
    if _md_renderer is None:
        from markdown_it import MarkdownIt
        _md_renderer = MarkdownIt("commonmark", {"html": False})
        _md_renderer.enable(["table", "strikethrough"])
    return _md_renderer


class SessionSearchWorker(QThread):
    finished = pyqtSignal(str, list)

    def __init__(self, scanner: SessionScanner, query: str):
        super().__init__()
        self.scanner = scanner
        self.query = query

    def run(self):
        query_lower = self.query.lower()
        matches: list[SessionInfo] = []
        sources = self.scanner.scan()

        matched_paths = set(self.scanner.grep_search(sources, self.query))

        for src in sources:
            try:
                sessions = self.scanner.list_sessions(src)
            except Exception:
                continue
            for sess in sessions:
                searchable = f"{sess.title} {sess.first_user_message or ''} {sess.workspace or ''}".lower()
                old_match = query_lower in searchable
                grep_match = str(sess.file_path) in matched_paths

                if old_match or grep_match:
                    matches.append(sess)

        from datetime import datetime
        matches.sort(key=lambda s: s.updated_at or datetime.min, reverse=True)
        self.finished.emit(self.query, matches[:30])
