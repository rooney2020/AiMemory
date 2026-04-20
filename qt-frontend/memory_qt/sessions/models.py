"""统一数据模型 — 跨框架的会话记录抽象"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from pathlib import Path
from typing import Optional


class FrameworkType(Enum):
    CURSOR = "Cursor"
    TODER = "Toder"
    CLINE = "Cline"
    COPILOT = "Copilot Chat"
    CLAUDE_CODE = "Claude Code"
    OPENCLAW = "OpenClaw"
    CONTINUE = "Continue.dev"
    AIDER = "Aider"

    @property
    def color_key(self) -> str:
        return {
            FrameworkType.CURSOR: "blue",
            FrameworkType.TODER: "green",
            FrameworkType.CLINE: "green",
            FrameworkType.COPILOT: "mauve",
            FrameworkType.CLAUDE_CODE: "peach",
            FrameworkType.OPENCLAW: "teal",
            FrameworkType.CONTINUE: "yellow",
            FrameworkType.AIDER: "pink",
        }[self]


@dataclass
class SessionSource:
    """检测到的 AI 框架数据源"""
    framework: FrameworkType
    base_path: Path
    session_count: int = 0
    workspace_name: Optional[str] = None


@dataclass
class SessionMessage:
    """单条对话消息"""
    role: str  # "user" / "assistant" / "system" / "tool"
    content: str
    timestamp: Optional[datetime] = None
    detail: str = ""


@dataclass
class SessionInfo:
    """一次完整的会话/对话"""
    id: str
    framework: FrameworkType
    title: str
    workspace: Optional[str] = None
    file_path: Path = field(default_factory=lambda: Path())
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    message_count: int = 0
    first_user_message: Optional[str] = None
    messages: list[SessionMessage] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    @property
    def display_title(self) -> str:
        if self.title:
            return self.title
        if self.first_user_message:
            text = self.first_user_message[:80]
            return text + "..." if len(self.first_user_message) > 80 else text
        return self.id[:12]

    @property
    def display_time(self) -> str:
        t = self.updated_at or self.created_at
        if not t:
            return ""
        return t.strftime("%m-%d %H:%M")
