"""Claude Code 会话记录解析器"""

from __future__ import annotations

import json
from pathlib import Path

from .base import BaseParser
from ..models import FrameworkType, SessionSource, SessionInfo, SessionMessage

_CLAUDE_BASE = Path.home() / ".claude"


class ClaudeCodeParser(BaseParser):
    @property
    def framework(self) -> FrameworkType:
        return FrameworkType.CLAUDE_CODE

    def detect(self) -> list[SessionSource]:
        sources = []
        projects_dir = _CLAUDE_BASE / "projects"
        if not projects_dir.is_dir():
            return sources

        total = 0
        for proj_dir in projects_dir.iterdir():
            if not proj_dir.is_dir():
                continue
            sessions_dir = proj_dir / "sessions"
            if sessions_dir.is_dir():
                total += len(list(sessions_dir.glob("*.jsonl")))

        if total > 0:
            sources.append(SessionSource(
                framework=FrameworkType.CLAUDE_CODE,
                base_path=projects_dir,
                session_count=total,
                workspace_name="Claude Code",
            ))

        return sources

    def list_sessions(self, source: SessionSource) -> list[SessionInfo]:
        sessions = []

        for proj_dir in sorted(source.base_path.iterdir(), reverse=True):
            if not proj_dir.is_dir():
                continue
            sessions_dir = proj_dir / "sessions"
            if not sessions_dir.is_dir():
                continue

            ws_name = _decode_project_path(proj_dir.name)

            for jsonl_file in sorted(sessions_dir.glob("*.jsonl"), reverse=True):
                mtime = self._safe_stat_mtime(jsonl_file)
                title, first_msg, msg_count = _peek_session(jsonl_file)

                sessions.append(SessionInfo(
                    id=jsonl_file.stem,
                    framework=FrameworkType.CLAUDE_CODE,
                    title=title,
                    workspace=ws_name,
                    file_path=jsonl_file,
                    created_at=mtime,
                    updated_at=mtime,
                    message_count=msg_count,
                    first_user_message=first_msg,
                ))

        sessions.sort(key=lambda s: s.updated_at or s.created_at or __import__("datetime").datetime.min, reverse=True)
        return sessions

    def load_messages(self, session: SessionInfo) -> SessionInfo:
        messages = []
        try:
            with open(session.file_path, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        obj = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    role = obj.get("role", "")
                    if role not in ("user", "assistant"):
                        continue

                    content = obj.get("content", "")
                    if isinstance(content, list):
                        text_parts = [
                            b.get("text", "") for b in content
                            if isinstance(b, dict) and b.get("type") == "text"
                        ]
                        content = "\n".join(text_parts)
                    elif not isinstance(content, str):
                        content = str(content)

                    if content.strip():
                        messages.append(SessionMessage(role=role, content=content.strip()))

        except (OSError, UnicodeDecodeError):
            pass

        session.messages = messages
        session.message_count = len(messages)
        return session


def _decode_project_path(encoded: str) -> str:
    """Claude Code 的项目目录名是编码后的路径"""
    decoded = encoded.replace("-", "/")
    parts = Path(decoded).parts
    return "/".join(parts[-2:]) if len(parts) >= 2 else encoded


def _peek_session(path: Path) -> tuple[str, str | None, int]:
    title = ""
    first_msg = None
    msg_count = 0

    try:
        with open(path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue

                role = obj.get("role", "")
                if role in ("user", "assistant"):
                    msg_count += 1
                    if not first_msg and role == "user":
                        content = obj.get("content", "")
                        if isinstance(content, list):
                            for b in content:
                                if isinstance(b, dict) and b.get("type") == "text":
                                    first_msg = b.get("text", "")[:200]
                                    break
                        elif isinstance(content, str):
                            first_msg = content[:200]
                        if first_msg:
                            title = first_msg[:40]
    except (OSError, UnicodeDecodeError):
        pass

    return title, first_msg, msg_count
