"""Toder / Cline 会话记录解析器"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from .base import BaseParser
from ..models import FrameworkType, SessionSource, SessionInfo, SessionMessage

_TODER_BASE = (
    Path.home() / ".config" / "Code" / "User" / "globalStorage" / "thundersoft.toder"
)
_CLINE_BASE = (
    Path.home() / ".config" / "Code" / "User" / "globalStorage" / "saoudrizwan.claude-dev"
)


class ToderParser(BaseParser):
    """同时检测 Toder 和 Cline 原版（格式相同）"""

    @property
    def framework(self) -> FrameworkType:
        return FrameworkType.TODER

    def detect(self) -> list[SessionSource]:
        sources = []
        for base, fw in [(_TODER_BASE, FrameworkType.TODER), (_CLINE_BASE, FrameworkType.CLINE)]:
            tasks_dir = base / "tasks"
            if not tasks_dir.is_dir():
                continue

            task_dirs = [d for d in tasks_dir.iterdir()
                         if d.is_dir() and (d / "ui_messages.json").exists()]
            if not task_dirs:
                continue

            sources.append(SessionSource(
                framework=fw,
                base_path=base,
                session_count=len(task_dirs),
                workspace_name=fw.value,
            ))

        return sources

    def list_sessions(self, source: SessionSource) -> list[SessionInfo]:
        sessions = []
        history_file = source.base_path / "state" / "taskHistory.json"
        history_map: dict[str, dict] = {}

        if history_file.exists():
            try:
                with open(history_file, "r", encoding="utf-8") as f:
                    history = json.load(f)
                if isinstance(history, list):
                    for item in history:
                        tid = str(item.get("id", ""))
                        if tid:
                            history_map[tid] = item
            except (json.JSONDecodeError, OSError):
                pass

        tasks_dir = source.base_path / "tasks"
        for task_dir in tasks_dir.iterdir():
            if not task_dir.is_dir():
                continue
            ui_file = task_dir / "ui_messages.json"
            if not ui_file.exists():
                continue

            tid = task_dir.name
            hist = history_map.get(tid, {})

            title = hist.get("task", "")
            if title:
                title = title[:80]

            ts_val = hist.get("ts")
            created = None
            if ts_val:
                try:
                    created = datetime.fromtimestamp(ts_val / 1000)
                except (OSError, ValueError, TypeError):
                    pass

            mtime = self._safe_stat_mtime(ui_file)

            msg_count = 0
            first_msg = None
            try:
                with open(ui_file, "r", encoding="utf-8") as f:
                    msgs = json.load(f)
                if isinstance(msgs, list):
                    msg_count = len(msgs)
                    for m in msgs:
                        if m.get("type") == "say" and m.get("say") == "text":
                            first_msg = (m.get("text", "") or "")[:200]
                            if not title:
                                title = first_msg[:80]
                            break
            except (json.JSONDecodeError, OSError):
                pass

            sessions.append(SessionInfo(
                id=tid,
                framework=source.framework,
                title=title,
                workspace=source.workspace_name,
                file_path=ui_file,
                created_at=created or mtime,
                updated_at=mtime,
                message_count=msg_count,
                first_user_message=first_msg,
                metadata={
                    "tokens_in": hist.get("tokensIn", 0),
                    "tokens_out": hist.get("tokensOut", 0),
                    "model": hist.get("modelId", ""),
                },
            ))

        from datetime import datetime as _dt
        sessions.sort(key=lambda s: s.updated_at or s.created_at or _dt.min, reverse=True)
        return sessions

    def load_messages(self, session: SessionInfo) -> SessionInfo:
        messages = []
        try:
            with open(session.file_path, "r", encoding="utf-8") as f:
                msgs = json.load(f)
            if not isinstance(msgs, list):
                session.messages = messages
                return session

            for m in msgs:
                msg_type = m.get("type", "")
                say_type = m.get("say", "")

                if msg_type == "say" and say_type == "text":
                    messages.append(SessionMessage(
                        role="assistant",
                        content=m.get("text", ""),
                        timestamp=_ts_to_dt(m.get("ts")),
                    ))
                elif msg_type == "ask":
                    text = m.get("text", "")
                    if text:
                        messages.append(SessionMessage(
                            role="user",
                            content=text,
                            timestamp=_ts_to_dt(m.get("ts")),
                        ))
                elif msg_type == "say" and say_type == "api_req_started":
                    pass
                elif msg_type == "say" and say_type in ("user_feedback", "user_feedback_diff"):
                    messages.append(SessionMessage(
                        role="user",
                        content=m.get("text", ""),
                        timestamp=_ts_to_dt(m.get("ts")),
                    ))

        except (json.JSONDecodeError, OSError):
            pass

        session.messages = messages
        session.message_count = len(messages)
        return session


def _ts_to_dt(ts) -> datetime | None:
    if ts is None:
        return None
    try:
        if isinstance(ts, (int, float)):
            if ts > 1e12:
                ts = ts / 1000
            return datetime.fromtimestamp(ts)
    except (OSError, ValueError):
        pass
    return None
