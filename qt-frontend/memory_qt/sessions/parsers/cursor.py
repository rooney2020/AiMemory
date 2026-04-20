"""Cursor Agent Transcript 解析器"""

from __future__ import annotations

import json
import re
import sqlite3
from datetime import datetime
from pathlib import Path

from .base import BaseParser
from ..models import FrameworkType, SessionSource, SessionInfo, SessionMessage

_CURSOR_BASE = Path.home() / ".cursor" / "projects"
_GLOBAL_STATE_DB = Path.home() / ".config" / "Cursor" / "User" / "globalStorage" / "state.vscdb"
_TAG_RE = re.compile(r"<[^>]+>")


def _strip_xml_tags(text: str) -> str:
    return _TAG_RE.sub("", text).strip()


def _extract_user_query(text: str) -> str:
    """从 <user_query>...</user_query> 中提取真正的用户消息"""
    m = re.search(r"<user_query>\s*(.*?)\s*</user_query>", text, re.DOTALL)
    if m:
        return m.group(1).strip()
    return _strip_xml_tags(text)


def _slug_to_workspace(slug: str) -> str:
    """将路径 slug 转为可读的工作区名（取最后两级）"""
    parts = slug.split("-")
    meaningful = [p for p in parts if p not in ("home", "tsdl", "ssd", "code", "temp")]
    return "/".join(meaningful[-2:]) if len(meaningful) >= 2 else slug


class CursorParser(BaseParser):
    @property
    def framework(self) -> FrameworkType:
        return FrameworkType.CURSOR

    def detect(self) -> list[SessionSource]:
        sources = []
        if not _CURSOR_BASE.is_dir():
            return sources

        for proj_dir in sorted(_CURSOR_BASE.iterdir()):
            transcripts = proj_dir / "agent-transcripts"
            if not transcripts.is_dir():
                continue

            jsonl_dirs = [d for d in transcripts.iterdir()
                          if d.is_dir() and (d / f"{d.name}.jsonl").exists()]
            txt_files = [f for f in transcripts.glob("*.txt") if f.is_file()]

            txt_ids = {f.stem for f in txt_files}
            jsonl_ids = {d.name for d in jsonl_dirs}
            total = len(jsonl_ids | txt_ids)

            if total == 0:
                continue

            sources.append(SessionSource(
                framework=FrameworkType.CURSOR,
                base_path=transcripts,
                session_count=total,
                workspace_name=_slug_to_workspace(proj_dir.name),
            ))

        return sources

    def list_sessions(self, source: SessionSource) -> list[SessionInfo]:
        sessions = []
        transcripts_dir = source.base_path
        seen_ids = set()

        for session_dir in transcripts_dir.iterdir():
            if not session_dir.is_dir():
                continue
            jsonl = session_dir / f"{session_dir.name}.jsonl"
            if not jsonl.exists():
                continue

            sid = session_dir.name
            seen_ids.add(sid)

            txt_file = transcripts_dir / f"{sid}.txt"
            preferred_file = txt_file if txt_file.exists() else jsonl
            file_format = "txt" if txt_file.exists() else "jsonl"

            mtime = self._safe_stat_mtime(preferred_file)
            first_msg = None
            msg_count = 0
            title = ""

            if file_format == "txt":
                first_msg, title, msg_count = _peek_txt(txt_file)
            else:
                first_msg, title, msg_count = _peek_jsonl(jsonl)

            sessions.append(SessionInfo(
                id=sid,
                framework=FrameworkType.CURSOR,
                title=title,
                workspace=source.workspace_name,
                file_path=preferred_file,
                created_at=mtime,
                updated_at=mtime,
                message_count=msg_count,
                first_user_message=first_msg,
                metadata={"format": file_format},
            ))

        for txt_file in transcripts_dir.glob("*.txt"):
            sid = txt_file.stem
            if sid in seen_ids:
                continue
            seen_ids.add(sid)

            mtime = self._safe_stat_mtime(txt_file)
            first_msg, title, msg_count = _peek_txt(txt_file)

            sessions.append(SessionInfo(
                id=sid,
                framework=FrameworkType.CURSOR,
                title=title,
                workspace=source.workspace_name,
                file_path=txt_file,
                created_at=mtime,
                updated_at=mtime,
                message_count=msg_count,
                first_user_message=first_msg,
                metadata={"format": "txt"},
            ))

        sessions.sort(key=lambda s: s.updated_at or datetime.min, reverse=True)
        return sessions

    def load_messages(self, session: SessionInfo) -> SessionInfo:
        result = _load_from_statedb(session)
        if result and result.messages:
            return result

        fmt = session.metadata.get("format", "")
        if fmt == "txt" or session.file_path.suffix == ".txt":
            return _load_txt_messages(session)
        return _load_jsonl_messages(session)


def _load_from_statedb(session: SessionInfo) -> SessionInfo | None:
    """从 Cursor 的全局 state.vscdb 加载完整对话（含工具调用）"""
    if not _GLOBAL_STATE_DB.exists():
        return None
    sid = session.id
    try:
        conn = sqlite3.connect(str(_GLOBAL_STATE_DB))
        c = conn.cursor()
        c.execute(
            "SELECT value FROM cursorDiskKV WHERE key=?",
            (f"composerData:{sid}",),
        )
        row = c.fetchone()
        if not row:
            conn.close()
            return None

        composer = json.loads(row[0] if isinstance(row[0], str) else row[0].decode("utf-8", errors="replace"))
        headers = composer.get("fullConversationHeadersOnly", [])
        if not headers:
            conn.close()
            return None

        messages: list[SessionMessage] = []
        for h in headers:
            bid = h.get("bubbleId", "")
            key = f"bubbleId:{sid}:{bid}"
            c.execute("SELECT value FROM cursorDiskKV WHERE key=?", (key,))
            brow = c.fetchone()
            if not brow:
                continue
            bubble = json.loads(brow[0] if isinstance(brow[0], str) else brow[0].decode("utf-8", errors="replace"))

            btype = bubble.get("type", 0)
            text = bubble.get("text", "")
            tfd = bubble.get("toolFormerData")

            if btype == 1 and text:
                messages.append(SessionMessage(
                    role="user",
                    content=_extract_user_query(text),
                ))
            elif tfd and isinstance(tfd, dict) and tfd.get("name"):
                tool_name = tfd["name"]
                is_mcp = tool_name.startswith("mcp-")

                if not is_mcp:
                    continue

                display_name = tool_name
                if is_mcp:
                    name_parts = tool_name.split("-")
                    if len(name_parts) > 3:
                        display_name = name_parts[-1]

                params_raw = tfd.get("params", "")
                status = tfd.get("status", "")
                result_raw = tfd.get("result", "")

                summary = f"**{display_name}**"
                if status:
                    summary += f"  *({status})*"

                detail_parts = [f"**{display_name}**"]
                if params_raw:
                    try:
                        p = json.loads(params_raw) if isinstance(params_raw, str) else params_raw
                        if isinstance(p, dict):
                            for pk, pv in p.items():
                                if pk in ("parsingResult",):
                                    continue
                                sv = str(pv)
                                if len(sv) > 500:
                                    sv = sv[:500] + "..."
                                detail_parts.append(f"`{pk}`: {sv}")
                    except (json.JSONDecodeError, TypeError):
                        detail_parts.append(str(params_raw)[:500])

                if result_raw:
                    try:
                        r = json.loads(result_raw) if isinstance(result_raw, str) else result_raw
                        rs = json.dumps(r, ensure_ascii=False, indent=2)
                        if len(rs) > 1000:
                            rs = rs[:1000] + "\n..."
                        detail_parts.append(f"\n**结果:**\n```\n{rs}\n```")
                    except (json.JSONDecodeError, TypeError):
                        rs = str(result_raw)
                        if len(rs) > 1000:
                            rs = rs[:1000] + "..."
                        detail_parts.append(f"\n**结果:** {rs}")

                messages.append(SessionMessage(
                    role="tool",
                    content=summary,
                    detail="\n".join(detail_parts),
                ))
            elif btype == 2 and text:
                messages.append(SessionMessage(
                    role="assistant",
                    content=text,
                ))

        conn.close()

        if messages:
            session.messages = messages
            session.message_count = len(messages)
            session.metadata["format"] = "statedb"
            return session
    except (sqlite3.Error, json.JSONDecodeError, KeyError, TypeError):
        pass
    return None


def _peek_jsonl(jsonl: Path) -> tuple[str | None, str, int]:
    """快速读取 JSONL 获取第一条用户消息和消息数"""
    first_msg = None
    title = ""
    msg_count = 0
    try:
        with open(jsonl, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                except json.JSONDecodeError:
                    continue
                msg_count += 1
                if not first_msg and obj.get("role") == "user":
                    content_blocks = obj.get("message", {}).get("content", [])
                    for block in content_blocks:
                        if block.get("type") == "text":
                            raw = block.get("text", "")
                            first_msg = _extract_user_query(raw)
                            title = first_msg[:40]
                            break
    except (OSError, UnicodeDecodeError):
        pass
    return first_msg, title, msg_count


def _peek_txt(txt_file: Path) -> tuple[str | None, str, int]:
    """快速读取 .txt 文件获取第一条用户消息和消息数"""
    first_msg = None
    title = ""
    msg_count = 0
    in_first_user = False
    first_user_lines: list[str] = []
    try:
        with open(txt_file, "r", encoding="utf-8") as f:
            text = f.read(8192)
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped == "user:" or stripped.startswith("user:"):
                msg_count += 1
                if msg_count == 1:
                    in_first_user = True
                    rest = stripped[5:].strip()
                    if rest:
                        first_user_lines.append(rest)
                else:
                    in_first_user = False
            elif stripped == "assistant:" or stripped.startswith("assistant:"):
                msg_count += 1
                in_first_user = False
            elif stripped.startswith("[Tool call]"):
                msg_count += 1
                in_first_user = False
            elif in_first_user and stripped:
                first_user_lines.append(stripped)
        if first_user_lines:
            raw = "\n".join(first_user_lines)
            first_msg = _extract_user_query(raw)
            title = first_msg[:40]
    except (OSError, UnicodeDecodeError):
        pass
    return first_msg, title, msg_count


def _load_jsonl_messages(session: SessionInfo) -> SessionInfo:
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
                role = obj.get("role", "unknown")
                content_blocks = obj.get("message", {}).get("content", [])
                text_parts = []
                for block in content_blocks:
                    if block.get("type") == "text":
                        raw = block.get("text", "")
                        if role == "user":
                            raw = _extract_user_query(raw)
                        text_parts.append(raw)
                if text_parts:
                    messages.append(SessionMessage(role=role, content="\n".join(text_parts)))
    except (OSError, UnicodeDecodeError):
        pass
    session.messages = messages
    session.message_count = len(messages)
    return session


def _load_txt_messages(session: SessionInfo) -> SessionInfo:
    """解析 .txt 格式的 Cursor 会话记录（包含工具调用）"""
    messages = []
    try:
        with open(session.file_path, "r", encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        session.messages = messages
        return session

    lines = text.split("\n")
    current_role = None
    current_lines: list[str] = []

    def _flush():
        if current_role and current_lines:
            content = "\n".join(current_lines).strip()
            if not content:
                return
            if current_role == "user":
                content = _extract_user_query(content)
            if content:
                messages.append(SessionMessage(role=current_role, content=content))

    for line in lines:
        stripped = line.strip()

        if stripped == "user:" or stripped.startswith("user:"):
            _flush()
            current_role = "user"
            rest = stripped[5:].strip() if len(stripped) > 5 else ""
            current_lines = [rest] if rest else []

        elif stripped == "assistant:" or stripped.startswith("assistant:"):
            _flush()
            current_role = "assistant"
            rest = stripped[10:].strip() if len(stripped) > 10 else ""
            current_lines = [rest] if rest else []

        elif stripped.startswith("[Tool call]"):
            _flush()
            current_role = "tool"
            tool_name = stripped[len("[Tool call]"):].strip()
            current_lines = [f"**Tool: {tool_name}**"]

        elif stripped.startswith("[Tool result]"):
            _flush()
            current_role = None
            current_lines = []

        elif stripped.startswith("[Thinking]"):
            thinking = stripped[len("[Thinking]"):].strip()
            if current_role == "assistant":
                current_lines.append(f"\n> *思考: {thinking}*")
            else:
                _flush()
                current_role = "assistant"
                current_lines = [f"> *思考: {thinking}*"]

        else:
            if current_role == "tool":
                if stripped.startswith("  "):
                    current_lines.append(f"  `{stripped.strip()}`")
                elif stripped:
                    current_lines.append(f"`{stripped}`")
            elif current_role:
                current_lines.append(line)

    _flush()

    session.messages = messages
    session.message_count = len(messages)
    return session
