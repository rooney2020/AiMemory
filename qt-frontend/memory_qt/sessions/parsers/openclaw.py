"""OpenClaw 会话记录解析器"""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

from .base import BaseParser
from ..models import FrameworkType, SessionSource, SessionInfo, SessionMessage

_OPENCLAW_AGENTS = Path.home() / ".openclaw" / "agents"

_SENDER_META_RE = re.compile(
    r"(?:Conversation info \(untrusted metadata\):.*?```\s*\n)?"
    r"Sender \(untrusted metadata\):.*?```\s*\n"
    r"(?:\[.*?\]\s*)?",
    re.DOTALL,
)

_SESSION_STARTUP_PREFIX = "A new session was started via /new or /reset"


class OpenClawParser(BaseParser):
    @property
    def framework(self) -> FrameworkType:
        return FrameworkType.OPENCLAW

    def detect(self) -> list[SessionSource]:
        sources: list[SessionSource] = []
        if not _OPENCLAW_AGENTS.is_dir():
            return sources

        for agent_dir in sorted(_OPENCLAW_AGENTS.iterdir()):
            sessions_dir = agent_dir / "sessions"
            if not sessions_dir.is_dir():
                continue

            files = _list_session_files(sessions_dir)
            if not files:
                continue

            sources.append(SessionSource(
                framework=FrameworkType.OPENCLAW,
                base_path=sessions_dir,
                session_count=len(files),
                workspace_name=f"OpenClaw/{agent_dir.name}",
            ))

        return sources

    def list_sessions(self, source: SessionSource) -> list[SessionInfo]:
        sessions: list[SessionInfo] = []

        for jsonl_file in _list_session_files(source.base_path):
            mtime = self._safe_stat_mtime(jsonl_file)
            sid, title, first_msg, msg_count, created_at, cwd = _peek_session(jsonl_file)

            real_id = sid or jsonl_file.name.split(".")[0]

            ws = source.workspace_name
            if cwd:
                parts = Path(cwd).parts
                ws = "/".join(parts[-2:]) if len(parts) >= 2 else cwd

            is_archived = ".reset." in jsonl_file.name

            sessions.append(SessionInfo(
                id=real_id,
                framework=FrameworkType.OPENCLAW,
                title=title,
                workspace=ws,
                file_path=jsonl_file,
                created_at=created_at or mtime,
                updated_at=mtime,
                message_count=msg_count,
                first_user_message=first_msg,
                metadata={"archived": is_archived},
            ))

        sessions.sort(key=lambda s: s.updated_at or datetime.min, reverse=True)
        return sessions

    def load_messages(self, session: SessionInfo) -> SessionInfo:
        messages: list[SessionMessage] = []
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

                    if obj.get("type") != "message":
                        continue

                    msg = obj.get("message", {})
                    role = msg.get("role", "")
                    content = msg.get("content", [])

                    if role == "user":
                        text = _extract_text(content)
                        text = _strip_user_meta(text)
                        if text:
                            messages.append(SessionMessage(role="user", content=text))

                    elif role == "assistant":
                        text_parts: list[str] = []
                        tool_names: list[str] = []
                        thinking = ""

                        for block in (content if isinstance(content, list) else []):
                            if not isinstance(block, dict):
                                continue
                            btype = block.get("type", "")
                            if btype == "text":
                                t = block.get("text", "").strip()
                                if t:
                                    text_parts.append(t)
                            elif btype == "thinking":
                                thinking = block.get("thinking", "")
                            elif btype == "toolCall":
                                name = block.get("name", "?")
                                args = block.get("arguments", {})
                                hint = _tool_hint(name, args)
                                tool_names.append(hint)

                        combined = "\n\n".join(text_parts)

                        if tool_names and not combined:
                            combined = "调用工具: " + ", ".join(tool_names)
                        elif tool_names:
                            combined += "\n\n调用工具: " + ", ".join(tool_names)

                        if not combined and thinking:
                            combined = "> *思考中...*"

                        detail = ""
                        if thinking:
                            short = thinking[:500]
                            if len(thinking) > 500:
                                short += "..."
                            detail = f"> *思考: {short}*"

                        if combined:
                            messages.append(SessionMessage(
                                role="assistant", content=combined, detail=detail,
                            ))

                    elif role == "toolResult":
                        text = _extract_text(content)
                        if text:
                            short = text[:200] + ("..." if len(text) > 200 else "")
                            messages.append(SessionMessage(
                                role="tool", content=f"**工具结果:** {short}", detail=text,
                            ))

        except (OSError, UnicodeDecodeError):
            pass

        session.messages = messages
        session.message_count = len(messages)
        return session


def _list_session_files(sessions_dir: Path) -> list[Path]:
    files: list[Path] = []
    for f in sessions_dir.iterdir():
        name = f.name
        if name == "sessions.json" or name.endswith(".lock"):
            continue
        if ".deleted." in name:
            continue
        if name.endswith(".jsonl") or ".jsonl.reset." in name:
            files.append(f)
    return files


def _extract_text(content) -> str:
    if isinstance(content, str):
        return content.strip()
    if not isinstance(content, list):
        return ""
    parts = []
    for block in content:
        if isinstance(block, dict) and block.get("type") == "text":
            parts.append(block.get("text", ""))
    return "\n".join(parts).strip()


def _strip_user_meta(text: str) -> str:
    """去除 OpenClaw 用户消息中的 Sender/Conversation 元数据前缀"""
    if text.startswith(_SESSION_STARTUP_PREFIX):
        return ""
    cleaned = _SENDER_META_RE.sub("", text).strip()
    return cleaned if cleaned else text


def _tool_hint(name: str, args: dict) -> str:
    if name == "read" and args.get("path"):
        p = args["path"]
        return f"read({Path(p).name})"
    if name == "exec" and args.get("command"):
        cmd = args["command"]
        short = cmd[:40] + ("..." if len(cmd) > 40 else "")
        return f"exec({short})"
    if name == "write" and args.get("path"):
        return f"write({Path(args['path']).name})"
    return name


def _peek_session(path: Path) -> tuple[str, str, str | None, int, datetime | None, str]:
    sid = ""
    title = ""
    first_msg: str | None = None
    msg_count = 0
    created_at: datetime | None = None
    cwd = ""

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

                etype = obj.get("type", "")

                if etype == "session":
                    sid = obj.get("id", "")
                    cwd = obj.get("cwd", "")
                    ts = obj.get("timestamp", "")
                    if ts:
                        try:
                            created_at = datetime.fromisoformat(ts.replace("Z", "+00:00"))
                        except (ValueError, TypeError):
                            pass

                elif etype == "message":
                    msg = obj.get("message", {})
                    role = msg.get("role", "")
                    if role in ("user", "assistant"):
                        msg_count += 1
                    if first_msg is None and role == "user":
                        text = _extract_text(msg.get("content", []))
                        text = _strip_user_meta(text)
                        if text:
                            first_msg = text[:200]
                            title = text[:40]

    except (OSError, UnicodeDecodeError):
        pass

    return sid, title, first_msg, msg_count, created_at, cwd
