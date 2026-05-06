"""GitHub Copilot Chat 会话记录解析器"""

from __future__ import annotations

from copy import deepcopy
import json
from pathlib import Path
import re

from ai_memory.config import load_config

from .base import BaseParser
from ..models import FrameworkType, SessionSource, SessionInfo, SessionMessage

_WORKSPACE_STORAGE = (
    Path.home() / ".config" / "Code" / "User" / "workspaceStorage"
)
_SYNCED_COPILOT = load_config().readable_path / "synced-sessions" / "copilot"

_NOISY_TOOL_IDS = {
    "copilot_getErrors",
    "copilot_listDirectory",
    "copilot_readFile",
    "copilot_getNotebookSummary",
    "file_search",
    "get_changed_files",
    "get_errors",
    "get_search_view_results",
    "grep_search",
    "list_dir",
    "manage_todo_list",
    "memory",
    "read_file",
    "resolve_memory_file_uri",
    "semantic_search",
    "terminal_last_command",
    "terminal_selection",
}

_ALWAYS_VISIBLE_TOOL_IDS = {
    "apply_patch",
    "copilot_applyPatch",
    "mcp_interactive-f_interactive_feedback",
}

_NOISY_TERMINAL_COMMANDS = {
    "awk",
    "basename",
    "cat",
    "command",
    "cp",
    "cut",
    "date",
    "echo",
    "find",
    "git",
    "grep",
    "head",
    "kill",
    "ls",
    "mkdir",
    "mv",
    "nl",
    "pgrep",
    "ps",
    "pwd",
    "rg",
    "rm",
    "sed",
    "sort",
    "tail",
    "test",
    "touch",
    "wc",
}

_TERMINAL_PREAMBLE_COMMANDS = {
    "alias",
    "cd",
    "do",
    "done",
    "export",
    "fi",
    "for",
    "if",
    "popd",
    "pushd",
    "set",
    "source",
    "then",
    "unalias",
}

_MEANINGFUL_TERMINAL_KEYWORDS = (
    "apply_patch",
    "main.py",
    "make ",
    "npm ",
    "pnpm ",
    "pytest",
    "run.sh",
    "uv ",
    "yarn ",
)

_NOISY_TERMINAL_SUBSTRINGS = (
    "/.local/bin/ai-memory",
    "/.cursor/",
    "/chatsessions/",
    "/workspacestorage/",
    "/user/prompts",
    "backend/cli.py",
    "cat <<",
    "cli.py recall",
    "cli.py remember",
    "cli.py update",
    "cli.py working",
    "pgrep -af",
    "pids=$(",
    "python - <<",
    "python -c ",
    "python3 - <<",
    "python3 -c ",
)


class CopilotParser(BaseParser):
    @property
    def framework(self) -> FrameworkType:
        return FrameworkType.COPILOT

    def detect(self) -> list[SessionSource]:
        sources = []
        if _WORKSPACE_STORAGE.is_dir():
            total = 0
            for ws_dir in _WORKSPACE_STORAGE.iterdir():
                chat_dir = ws_dir / "chatSessions"
                if chat_dir.is_dir():
                    for jsonl_file in chat_dir.glob("*.jsonl"):
                        title, first_msg, msg_count = _peek_jsonl(jsonl_file)
                        if _is_valid_session(title, first_msg, msg_count):
                            total += 1

            if total > 0:
                sources.append(SessionSource(
                    framework=FrameworkType.COPILOT,
                    base_path=_WORKSPACE_STORAGE,
                    session_count=total,
                    workspace_name="VS Code",
                ))

        if _SYNCED_COPILOT.is_dir():
            for machine_dir in sorted(_SYNCED_COPILOT.iterdir()):
                if not machine_dir.is_dir():
                    continue
                files = [path for path in machine_dir.glob("*.jsonl") if path.is_file()]
                if not files:
                    continue
                sources.append(SessionSource(
                    framework=FrameworkType.COPILOT,
                    base_path=machine_dir,
                    session_count=len(files),
                    workspace_name=f"同步/{machine_dir.name}",
                ))

        return sources

    def list_sessions(self, source: SessionSource) -> list[SessionInfo]:
        sessions = []

        if source.base_path != _WORKSPACE_STORAGE:
            for jsonl_file in sorted(source.base_path.glob("*.jsonl"), reverse=True):
                mtime = self._safe_stat_mtime(jsonl_file)
                title, requests = _load_requests(jsonl_file)
                messages = _messages_from_requests(requests)
                first_msg = next((msg.content for msg in messages if msg.role == "user" and msg.content), None)
                msg_count = len(messages)
                if not title and first_msg:
                    title = first_msg[:40]
                if not _is_valid_session(title, first_msg, msg_count):
                    continue
                sessions.append(SessionInfo(
                    id=jsonl_file.stem,
                    framework=FrameworkType.COPILOT,
                    title=title,
                    workspace=source.workspace_name,
                    file_path=jsonl_file,
                    created_at=mtime,
                    updated_at=mtime,
                    message_count=msg_count,
                    first_user_message=first_msg,
                ))

            sessions.sort(key=lambda s: s.updated_at or s.created_at or __import__("datetime").datetime.min, reverse=True)
            return sessions

        for ws_dir in sorted(source.base_path.iterdir(), reverse=True):
            chat_dir = ws_dir / "chatSessions"
            if not chat_dir.is_dir():
                continue

            ws_name = _resolve_workspace_name(ws_dir)

            for jsonl_file in sorted(chat_dir.glob("*.jsonl"), reverse=True):
                mtime = self._safe_stat_mtime(jsonl_file)
                title, requests = _load_requests(jsonl_file)
                messages = _messages_from_requests(requests)
                first_msg = next((msg.content for msg in messages if msg.role == "user" and msg.content), None)
                msg_count = len(messages)
                if not title and first_msg:
                    title = first_msg[:40]

                if not _is_valid_session(title, first_msg, msg_count):
                    continue

                sessions.append(SessionInfo(
                    id=jsonl_file.stem,
                    framework=FrameworkType.COPILOT,
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
        custom_title, messages = _load_event_messages(session.file_path)

        if custom_title:
            session.title = custom_title
        session.messages = messages
        session.message_count = len(messages)
        return session


def _load_event_messages(path: Path) -> tuple[str, list[SessionMessage]]:
    custom_title = ""
    raw_messages: list[SessionMessage] = []
    seen_request_ids: set[str] = set()

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

                if not custom_title:
                    custom_title = _extract_custom_title(obj)

                for req in _extract_new_requests(obj):
                    request_id = req.get("requestId") or f"request-{len(seen_request_ids)}"
                    if request_id not in seen_request_ids:
                        seen_request_ids.add(request_id)
                        user_text = _extract_user_text(req)
                        if user_text:
                            raw_messages.append(SessionMessage(role="user", content=user_text))

                    raw_messages.extend(_extract_response_messages(req.get("response")))

                path_keys = obj.get("k")
                if not (
                    obj.get("kind") == 2
                    and isinstance(path_keys, list)
                    and len(path_keys) == 3
                    and path_keys[0] == "requests"
                    and isinstance(path_keys[1], int)
                    and path_keys[2] == "response"
                    and isinstance(obj.get("v"), list)
                ):
                    continue

                raw_messages.extend(_extract_response_messages(obj.get("v")))

    except (OSError, UnicodeDecodeError):
        return custom_title, []

    return custom_title, _compact_event_messages(raw_messages)


def _messages_from_requests(requests: list[dict]) -> list[SessionMessage]:
    messages: list[SessionMessage] = []

    for req in requests:
        user_text = _extract_user_text(req)
        if user_text:
            messages.append(SessionMessage(role="user", content=user_text))

        for response_message in _extract_response_messages(req.get("response")):
            if (
                messages
                and response_message.role == "assistant"
                and messages[-1].role == "assistant"
                and not response_message.detail
                and response_message.content not in messages[-1].content
            ):
                messages[-1].content += "\n\n" + response_message.content
            else:
                messages.append(response_message)

    return messages


def _compact_event_messages(messages: list[SessionMessage]) -> list[SessionMessage]:
    compacted: list[SessionMessage] = []
    seen_global: set[tuple[str, str, str]] = set()
    seen_since_user: dict[str, set[tuple[str, str]]] = {
        "assistant": set(),
        "tool": set(),
        "system": set(),
    }

    for message in messages:
        content = message.content.strip()
        detail = message.detail.strip()
        if not content and not detail:
            continue
        if message.role == "assistant" and _is_non_visual_assistant_text(content):
            continue

        normalized = SessionMessage(
            role=message.role,
            content=content,
            timestamp=message.timestamp,
            detail=detail,
        )

        if normalized.role == "user":
            if compacted and compacted[-1].role == "user" and compacted[-1].content == normalized.content:
                continue
            compacted.append(normalized)
            seen_since_user = {
                "assistant": set(),
                "tool": set(),
                "system": set(),
            }
            continue

        if normalized.role == "assistant":
            previous_assistant_index = _find_recent_turn_message(compacted, "assistant")
            if previous_assistant_index is not None:
                previous_assistant = compacted[previous_assistant_index]
                if (
                    not previous_assistant.detail
                    and not normalized.detail
                    and _is_stream_update(previous_assistant.content, normalized.content)
                ):
                    old_key = (previous_assistant.content, previous_assistant.detail)
                    seen_since_user["assistant"].discard(old_key)
                    compacted[previous_assistant_index] = normalized
                    seen_since_user["assistant"].add((normalized.content, normalized.detail))
                    continue

        role_seen = seen_since_user.setdefault(normalized.role, set())
        key = (normalized.content, normalized.detail)
        if key in role_seen:
            continue

        global_key = (normalized.role, normalized.content, normalized.detail)
        if normalized.role in {"tool", "system"} and global_key in seen_global:
            continue

        role_seen.add(key)
        if normalized.role in {"tool", "system"}:
            seen_global.add(global_key)
        compacted.append(normalized)

    return compacted


def _find_recent_turn_message(messages: list[SessionMessage], role: str) -> int | None:
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if message.role == "user":
            return None
        if message.role == role:
            return index
    return None


def _is_stream_update(previous: str, current: str) -> bool:
    if previous == current:
        return True

    short_text, long_text = (previous, current) if len(previous) <= len(current) else (current, previous)
    if len(short_text) >= 24 and short_text in long_text:
        return True
    if len(short_text) >= 12 and long_text.startswith(short_text):
        return True
    if len(short_text) >= 12 and long_text.endswith(short_text):
        return True
    return False


def _is_non_visual_assistant_text(content: str) -> bool:
    if not content:
        return True
    stripped = re.sub(r"[`\s]+", "", content)
    return stripped == ""


def _resolve_workspace_name(ws_dir: Path) -> str:
    ws_json = ws_dir / "workspace.json"
    if ws_json.exists():
        try:
            with open(ws_json, "r", encoding="utf-8") as f:
                data = json.load(f)
            folder = data.get("folder", "")
            if folder.startswith("file://"):
                folder = folder[7:]
            parts = Path(folder).parts
            return "/".join(parts[-2:]) if len(parts) >= 2 else folder
        except (json.JSONDecodeError, OSError):
            pass
    return ws_dir.name[:12]


def _peek_jsonl(path: Path) -> tuple[str, str | None, int]:
    """快速读取 JSONL 文件获取标题和首条消息。"""
    title = ""
    first_msg = None
    request_ids: set[str] = set()

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

                custom_title = _extract_custom_title(obj)
                if custom_title:
                    title = custom_title

                for req in _extract_new_requests(obj):
                    request_id = req.get("requestId") or f"request-{len(request_ids)}"
                    if request_id in request_ids:
                        continue
                    request_ids.add(request_id)

                    if not first_msg:
                        first_msg = _extract_user_text(req)

    except (OSError, UnicodeDecodeError):
        pass

    if not title and first_msg:
        title = first_msg[:40]

    return title, first_msg, len(request_ids) * 2


def _load_requests(path: Path) -> tuple[str, list[dict]]:
    state: dict = {"requests": []}
    custom_title = ""

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

                if not custom_title:
                    custom_title = _extract_custom_title(obj)

                kind = obj.get("kind")
                if kind == 0:
                    v_field = obj.get("v")
                    if isinstance(v_field, dict) and isinstance(v_field.get("requests"), list):
                        state["requests"] = deepcopy(v_field.get("requests", []))
                    continue

                if kind != 2:
                    continue

                path_keys = obj.get("k")
                value = deepcopy(obj.get("v"))
                if not isinstance(path_keys, list) or not path_keys:
                    continue

                if path_keys == ["requests"] and isinstance(value, list):
                    for req in value:
                        if not isinstance(req, dict):
                            continue
                        request_id = req.get("requestId")
                        existing = _find_request_index(state["requests"], request_id)
                        if existing is None:
                            state["requests"].append(req)
                        else:
                            state["requests"][existing] = req
                    continue

                if path_keys[0] == "requests":
                    splice_index = obj.get("i") if isinstance(obj.get("i"), int) else None
                    _apply_patch(state["requests"], path_keys[1:], value, splice_index)

    except (OSError, UnicodeDecodeError):
        pass

    requests = [req for req in state.get("requests", []) if isinstance(req, dict)]
    return custom_title, requests


def _extract_new_requests(obj: dict) -> list[dict]:
    kind = obj.get("kind")
    if kind == 0:
        v_field = obj.get("v")
        if isinstance(v_field, dict) and isinstance(v_field.get("requests"), list):
            return [req for req in v_field.get("requests", []) if isinstance(req, dict)]
        return []

    if kind == 2 and obj.get("k") == ["requests"] and isinstance(obj.get("v"), list):
        return [req for req in obj.get("v", []) if isinstance(req, dict)]

    return []


def _extract_custom_title(obj: dict) -> str:
    if obj.get("kind") == 1 and obj.get("k") == ["customTitle"] and isinstance(obj.get("v"), str):
        return obj["v"].strip()
    return ""


def _extract_user_text(req: dict) -> str:
    message = req.get("message", {})
    if isinstance(message, dict):
        if isinstance(message.get("text"), str) and message["text"].strip():
            return message["text"].strip()
        parts = message.get("parts")
        if isinstance(parts, list):
            texts = [part.get("text", "").strip() for part in parts if isinstance(part, dict) and part.get("text")]
            if texts:
                return "\n".join(texts)
    if isinstance(message, str):
        return message.strip()
    return ""


def _extract_response_messages(response) -> list[SessionMessage]:
    messages: list[SessionMessage] = []

    if isinstance(response, str):
        text = response.strip()
        if text:
            messages.append(SessionMessage(role="assistant", content=text))
        return messages

    if isinstance(response, dict):
        text = _extract_text_value(response)
        if text:
            messages.append(SessionMessage(role="assistant", content=text))
        return messages

    if not isinstance(response, list):
        return messages

    for item in response:
        if not isinstance(item, dict):
            continue

        if item.get("kind") == "toolInvocationSerialized":
            feedback_request = _extract_interactive_feedback_request(item)
            feedback_reply = _extract_interactive_feedback(item)

            if feedback_request:
                messages.append(SessionMessage(role="assistant", content=feedback_request))

            if _is_interactive_feedback_tool(item):
                if feedback_reply:
                    messages.append(SessionMessage(role="user", content=feedback_reply))
                continue

            if _should_hide_tool_message(item):
                continue
            content = _tool_summary(item)
            detail = _tool_detail(item)
            messages.append(SessionMessage(role="tool", content=content, detail=detail))
            if feedback_reply:
                messages.append(SessionMessage(role="user", content=feedback_reply))
            continue

        text = _extract_text_value(item)
        if text:
            messages.append(SessionMessage(role="assistant", content=text))

    return messages


def _extract_text_value(item: dict) -> str:
    if item.get("kind") == "thinking":
        return ""

    value = item.get("value")
    if isinstance(value, str) and value.strip():
        if value.strip() == "```":
            return ""
        return value.strip()

    content = item.get("content")
    if isinstance(content, dict):
        nested = content.get("value")
        if isinstance(nested, str) and nested.strip():
            if nested.strip() == "```":
                return ""
            return nested.strip()

    return ""


def _is_valid_session(title: str, first_msg: str | None, msg_count: int) -> bool:
    return bool(msg_count > 0 or title or first_msg)


def _tool_summary(item: dict) -> str:
    label = _tool_label(item)
    feedback_reply = _extract_interactive_feedback(item)
    if feedback_reply:
        return f"{label}\n用户反馈: {_preview_text(feedback_reply, 80)}"

    invocation = _message_text(item.get("invocationMessage"))
    if invocation:
        return f"{label}\n{invocation}"

    return label


def _tool_detail(item: dict) -> str:
    parts: list[str] = []
    outputs = _tool_outputs(item)
    feedback_reply = _extract_interactive_feedback(item)

    raw_input = item.get("toolSpecificData", {}).get("rawInput")
    if feedback_reply:
        if isinstance(raw_input, dict):
            message = raw_input.get("message")
            if isinstance(message, str) and message.strip():
                parts.append(f"反馈请求\n{message.strip()}")
        parts.append(f"用户反馈\n{feedback_reply}")

    for output in outputs:
        if feedback_reply and _parse_feedback_output(output):
            continue
        parts.append(output)

    if not feedback_reply and isinstance(raw_input, dict):
        message = raw_input.get("message")
        if isinstance(message, str) and message.strip():
            parts.append(message.strip())

    return "\n\n".join(parts)


def _tool_label(item: dict) -> str:
    origin = item.get("originMessage")
    if isinstance(origin, str) and origin.strip():
        return origin.strip()

    tool_id = item.get("toolId")
    mapped = {
        "run_in_terminal": "终端命令",
        "copilot_applyPatch": "应用补丁",
        "copilot_readFile": "读取文件",
        "copilot_listDirectory": "列出目录",
        "copilot_getErrors": "错误检查",
        "manage_todo_list": "待办列表",
        "mcp_interactive-f_interactive_feedback": "互动反馈",
    }.get(tool_id)
    if mapped:
        return mapped

    source = item.get("source")
    if isinstance(source, dict):
        label = source.get("label", "") or ""
        if label and label != "Built-In":
            return label

    tool_kind = item.get("toolSpecificData", {}).get("kind")
    if tool_kind == "terminal":
        return "终端命令"
    if tool_kind == "todoList":
        return "待办列表"

    if isinstance(source, dict):
        label = source.get("label", "") or ""
        if label:
            return label

    return "工具调用"


def _should_hide_tool_message(item: dict) -> bool:
    if _extract_interactive_feedback(item):
        return False

    tool_id = item.get("toolId")
    if isinstance(tool_id, str):
        if tool_id in _ALWAYS_VISIBLE_TOOL_IDS:
            return False
        if tool_id in _NOISY_TOOL_IDS:
            return True

    tool_data = item.get("toolSpecificData")
    if isinstance(tool_data, dict):
        tool_kind = tool_data.get("kind")
        if tool_kind == "todoList":
            return True
        if tool_kind == "terminal":
            return _is_noisy_terminal_tool(tool_data)

    source = item.get("source")
    if isinstance(source, dict) and source.get("label") == "Python":
        return True
    if isinstance(source, dict) and source.get("label") == "Built-In":
        return True

    return False


def _is_noisy_terminal_tool(tool_data: dict) -> bool:
    command = _terminal_command_text(tool_data)
    if not command:
        return False

    lowered = command.lower()
    if any(pattern in lowered for pattern in _NOISY_TERMINAL_SUBSTRINGS):
        return True
    if "python" in lowered and (" - <<" in lowered or " -c " in lowered):
        return True
    if " -m pip " in lowered or " pip install " in lowered:
        return True
    if any(keyword in lowered for keyword in _MEANINGFUL_TERMINAL_KEYWORDS):
        return False

    saw_noisy_command = False
    for segment in re.split(r"\n|&&|\|\||;", command):
        stripped = segment.strip()
        if not stripped:
            continue

        token = stripped.split(None, 1)[0].lower()
        if token in _TERMINAL_PREAMBLE_COMMANDS:
            continue

        if "=" in token and not token.startswith(("./", "/")):
            continue

        if token in _NOISY_TERMINAL_COMMANDS:
            saw_noisy_command = True
            continue

        return False

    return saw_noisy_command


def _terminal_command_text(tool_data: dict) -> str:
    command_line = tool_data.get("commandLine")
    if isinstance(command_line, dict):
        for key in ("forDisplay", "toolEdited", "original"):
            value = command_line.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()

    for key in ("command", "commandText"):
        value = tool_data.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return ""


def _message_text(value) -> str:
    if isinstance(value, dict):
        nested = value.get("value")
        if isinstance(nested, str) and nested.strip():
            return nested.strip()
        return ""
    if isinstance(value, str) and value.strip():
        return value.strip()
    return ""


def _tool_outputs(item: dict) -> list[str]:
    outputs: list[str] = []
    result_details = item.get("resultDetails")
    if not isinstance(result_details, dict):
        return outputs

    raw_outputs = result_details.get("output")
    if not isinstance(raw_outputs, list):
        return outputs

    for output in raw_outputs:
        if not isinstance(output, dict):
            continue
        mime_type = output.get("mimeType")
        if isinstance(mime_type, str) and mime_type.startswith("image/"):
            continue
        if output.get("isText") is False:
            continue
        value = output.get("value")
        if isinstance(value, str) and value.strip():
            outputs.append(value.strip())
    return outputs


def _extract_interactive_feedback(item: dict) -> str:
    outputs = _tool_outputs(item)
    feedback_parts: list[str] = []
    seen: set[str] = set()

    for output in outputs:
        feedback = _parse_feedback_output(output)
        if feedback and feedback not in seen:
            seen.add(feedback)
            feedback_parts.append(feedback)

    if feedback_parts:
        return "\n\n".join(feedback_parts)

    if _is_interactive_feedback_tool(item):
        for output in outputs:
            cleaned = _clean_feedback_text(output)
            if cleaned:
                return cleaned

    return ""


def _extract_interactive_feedback_request(item: dict) -> str:
    if not _is_interactive_feedback_tool(item):
        return ""

    raw_input = item.get("toolSpecificData", {}).get("rawInput")
    if not isinstance(raw_input, dict):
        return ""

    message = raw_input.get("message")
    if isinstance(message, str) and message.strip():
        return _clean_feedback_text(message)

    return ""


def _parse_feedback_output(output: str) -> str:
    try:
        data = json.loads(output)
    except json.JSONDecodeError:
        return ""

    if not isinstance(data, dict):
        return ""

    feedback = data.get("interactive_feedback")
    if isinstance(feedback, str) and feedback.strip():
        return _clean_feedback_text(feedback)
    return ""


def _is_interactive_feedback_tool(item: dict) -> bool:
    tool_id = item.get("toolId")
    if tool_id == "mcp_interactive-f_interactive_feedback":
        return True

    origin = item.get("originMessage")
    if isinstance(origin, str) and "interactive-feedback" in origin.lower():
        return True

    source = item.get("source")
    if isinstance(source, dict):
        label = source.get("label")
        if isinstance(label, str) and "interactive-feedback" in label.lower():
            return True

    return False


def _clean_feedback_text(text: str) -> str:
    cleaned_lines: list[str] = []
    for line in text.splitlines():
        stripped = line.strip()
        if not stripped:
            cleaned_lines.append("")
            continue
        if stripped.startswith("[Screenshots saved to:"):
            continue
        if stripped.startswith("[Image URI:"):
            continue
        if stripped.startswith("/tmp/mcp_feedback_"):
            continue
        cleaned_lines.append(line)

    cleaned = "\n".join(cleaned_lines).strip()
    while "\n\n\n" in cleaned:
        cleaned = cleaned.replace("\n\n\n", "\n\n")
    return cleaned


def _preview_text(text: str, limit: int) -> str:
    one_line = " ".join(text.split())
    if len(one_line) <= limit:
        return one_line
    return one_line[: limit - 1].rstrip() + "…"


def _find_request_index(requests: list[dict], request_id: str | None) -> int | None:
    if not request_id:
        return None
    for index, req in enumerate(requests):
        if isinstance(req, dict) and req.get("requestId") == request_id:
            return index
    return None


def _apply_patch(root, path: list, value, splice_index: int | None = None) -> None:
    if not path:
        return

    container = root
    for index, key in enumerate(path[:-1]):
        next_key = path[index + 1]
        if isinstance(key, int):
            if not isinstance(container, list):
                return
            while len(container) <= key:
                container.append([] if isinstance(next_key, int) else {})
            if container[key] is None:
                container[key] = [] if isinstance(next_key, int) else {}
            container = container[key]
            continue

        if not isinstance(container, dict):
            return
        if key not in container or container[key] is None:
            container[key] = [] if isinstance(next_key, int) else {}
        container = container[key]

    last = path[-1]
    if isinstance(last, int):
        if not isinstance(container, list):
            return
        while len(container) <= last:
            container.append(None)
        container[last] = value
        return

    if isinstance(container, dict):
        if last == "response" and isinstance(value, list):
            existing = container.get(last)
            if isinstance(existing, list):
                start = splice_index if splice_index is not None else 0
                container[last] = _patch_list_items(existing, start, value)
            else:
                container[last] = value
            return
        container[last] = value


def _patch_list_items(existing: list, start: int, incoming: list) -> list:
    patched = list(existing)
    while len(patched) < start:
        patched.append(None)

    for offset, item in enumerate(incoming):
        index = start + offset
        if index < len(patched):
            patched[index] = item
        else:
            patched.append(item)

    return patched


def _response_item_key(item) -> str:
    if not isinstance(item, dict):
        return ""

    kind = item.get("kind")
    if kind == "toolInvocationSerialized":
        tool_call_id = item.get("toolCallId")
        if isinstance(tool_call_id, str) and tool_call_id:
            return f"tool:{tool_call_id}"

    item_id = item.get("id")
    if isinstance(item_id, str) and item_id:
        return f"id:{kind}:{item_id}"

    if kind == "elicitationSerialized":
        title = _message_text(item.get("title"))
        message = _message_text(item.get("message"))
        return f"elicitation:{title}:{message}:{item.get('state', '')}"

    value = _message_text(item.get("value"))
    if value:
        return f"value:{kind}:{value}"

    uri = item.get("uri")
    if isinstance(uri, dict):
        path = uri.get("path")
        if isinstance(path, str) and path:
            return f"uri:{kind}:{path}"

    try:
        return json.dumps(item, ensure_ascii=False, sort_keys=True)
    except TypeError:
        return ""
