from __future__ import annotations

from typing import Optional

from ..index.vector import VectorIndex
from ..storage.memory_store import MemoryStore


class DedupChecker:
    """入库前去重检查"""

    MERGE_THRESHOLD = 0.10      # distance < 0.10 → 合并（余弦相似度 > 0.90）
    LINK_THRESHOLD = 0.30       # 0.10 < distance < 0.30 → 标记关联

    def __init__(self, vector_index: Optional[VectorIndex], store: MemoryStore):
        self.vector = vector_index
        self.store = store

    def check(self, content: str) -> dict:
        """
        检查内容是否与已有记忆重复。
        返回:
          {"action": "merge", "target_id": "xxx", "distance": 0.05}
          {"action": "link", "target_ids": ["xxx", "yyy"]}
          {"action": "new"}
        """
        if not self.vector or not self.vector.available:
            return {"action": "new"}

        similar = self.vector.find_similar(
            content, threshold=self.LINK_THRESHOLD, top_k=5
        )

        if not similar:
            return {"action": "new"}

        for mid, distance in similar:
            if distance < self.MERGE_THRESHOLD:
                existing = self.store.get(mid)
                if existing and not existing.archived:
                    return {
                        "action": "merge",
                        "target_id": mid,
                        "distance": distance,
                    }

        link_ids = [mid for mid, dist in similar if dist < self.LINK_THRESHOLD]
        if link_ids:
            return {"action": "link", "target_ids": link_ids}

        return {"action": "new"}
