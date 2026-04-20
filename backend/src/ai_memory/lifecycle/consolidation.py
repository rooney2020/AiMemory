from __future__ import annotations

import math
from datetime import datetime

from ..config import Config
from ..core.memory import Memory


class ConsolidationEngine:
    """记忆固化：每次访问时更新强度"""

    def __init__(self, config: Config):
        self.config = config

    def on_access(self, memory: Memory) -> Memory:
        now = datetime.now()

        if memory.last_accessed:
            hours_since = (now - memory.last_accessed).total_seconds() / 3600
            spacing_bonus = min(
                math.log(hours_since + 1),
                self.config.consolidation.spacing_bonus_max,
            )
        else:
            spacing_bonus = 1.0

        memory.strength += 0.5 + spacing_bonus * 0.3
        memory.access_count += 1
        memory.last_accessed = now
        memory.updated_at = now
        return memory

    def on_co_retrieval(self, memories: list[Memory]):
        bonus = self.config.consolidation.co_retrieval_bonus
        for m in memories:
            m.strength += bonus * len(memories)
