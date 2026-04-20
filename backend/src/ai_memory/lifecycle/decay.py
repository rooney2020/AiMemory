from __future__ import annotations

import math
from datetime import datetime, timedelta

from ..config import Config
from ..storage.memory_store import MemoryStore


class DecayEngine:
    """定期运行：降低长期未访问的记忆强度"""

    def __init__(self, store: MemoryStore, config: Config):
        self.store = store
        self.config = config

    def run(self) -> dict:
        now = datetime.now()
        protection_cutoff = now - timedelta(days=self.config.decay.protection_days)

        memories = self.store.list_active(
            max_strength=self.config.decay.core_threshold,
            last_accessed_before=protection_cutoff,
        )

        updated = 0
        archived = 0

        for memory in memories:
            ref_time = memory.last_accessed or memory.created_at
            elapsed_days = (now - ref_time).days

            rate = memory.decay_rate
            if memory.type.value == "procedural":
                rate *= self.config.decay.procedural_rate_factor

            lambda_ = rate / (1 + math.log(memory.strength + 1))
            new_strength = memory.strength * math.exp(-lambda_ * elapsed_days)

            if new_strength < self.config.decay.min_strength:
                memory.archived = True
                memory.updated_at = now
                archived += 1
            else:
                memory.strength = new_strength
                memory.updated_at = now
                updated += 1

            self.store.save(memory)

        return {"updated": updated, "archived": archived}
