from __future__ import annotations

from ..storage.database import Database
from ..storage.entity_store import EntityStore


class GraphIndex:
    """L2: 实体图谱遍历"""

    def __init__(self, db: Database, entity_store: EntityStore):
        self.db = db
        self.entity_store = entity_store

    def traverse(
        self,
        entity_names: list[str],
        max_depth: int = 2,
        top_k: int = 30,
    ) -> list[tuple[str, float]]:
        """
        从给定实体出发 BFS，找到关联的记忆。
        返回 [(memory_id, graph_score), ...]
        graph_score 随深度递减。
        """
        memory_scores: dict[str, float] = {}

        for name in entity_names:
            entity = self.entity_store.get_by_name(name)
            if not entity:
                continue

            direct_mids = self.entity_store.get_related_memories(name)
            for mid in direct_mids:
                memory_scores[mid] = memory_scores.get(mid, 0) + 1.0

            if max_depth > 1:
                neighbor_ids = self.entity_store.get_entity_neighbors(
                    entity.id, max_depth=max_depth - 1
                )
                for nid in neighbor_ids:
                    neighbor_row = self.db.execute(
                        "SELECT name FROM entities WHERE id = ?", (nid,)
                    ).fetchone()
                    if neighbor_row:
                        indirect_mids = self.entity_store.get_related_memories(
                            neighbor_row["name"]
                        )
                        for mid in indirect_mids:
                            memory_scores[mid] = memory_scores.get(mid, 0) + 0.3

        results = sorted(memory_scores.items(), key=lambda x: x[1], reverse=True)
        return results[:top_k]

    def get_all_entity_names(self) -> list[str]:
        return self.entity_store.get_all_names()
