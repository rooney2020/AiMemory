"""会话收藏管理 — 使用本地 JSON 文件持久化"""

import json
from pathlib import Path
from typing import Set

_BOOKMARK_FILE = Path.home() / ".cursor" / "memory" / "bookmarks.json"


class BookmarkManager:
    def __init__(self):
        self._bookmarks: Set[str] = set()
        self._load()

    def _load(self):
        try:
            if _BOOKMARK_FILE.exists():
                data = json.loads(_BOOKMARK_FILE.read_text(encoding="utf-8"))
                self._bookmarks = set(data.get("session_ids", []))
        except Exception:
            self._bookmarks = set()

    def _save(self):
        _BOOKMARK_FILE.parent.mkdir(parents=True, exist_ok=True)
        data = {"session_ids": sorted(self._bookmarks)}
        _BOOKMARK_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

    def is_bookmarked(self, session_id: str) -> bool:
        return session_id in self._bookmarks

    def toggle(self, session_id: str) -> bool:
        if session_id in self._bookmarks:
            self._bookmarks.discard(session_id)
            self._save()
            return False
        else:
            self._bookmarks.add(session_id)
            self._save()
            return True

    def add(self, session_id: str):
        self._bookmarks.add(session_id)
        self._save()

    def remove(self, session_id: str):
        self._bookmarks.discard(session_id)
        self._save()

    def get_all(self) -> Set[str]:
        return set(self._bookmarks)

    @property
    def count(self) -> int:
        return len(self._bookmarks)
