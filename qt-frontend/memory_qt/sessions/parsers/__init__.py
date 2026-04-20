"""会话记录解析器集合"""

from .base import BaseParser
from .cursor import CursorParser
from .toder import ToderParser
from .copilot import CopilotParser
from .claude_code import ClaudeCodeParser
from .openclaw import OpenClawParser

ALL_PARSERS = [CursorParser, ToderParser, CopilotParser, ClaudeCodeParser, OpenClawParser]

__all__ = ["BaseParser", "ALL_PARSERS"]
