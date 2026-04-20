from __future__ import annotations

import json
from datetime import datetime
from typing import Optional
import uuid

from ..core.entity import Entity, Relation
from .database import Database


class EntityStore:
    def __init__(self, db: Database):
        self.db = db

    def get_or_create(self, name: str, entity_type: Optional[str] = None) -> Entity:
        row = self.db.execute(
            "SELECT * FROM entities WHERE name = ?", (name,)
        ).fetchone()
        if row:
            if entity_type and not row["type"]:
                self.db.execute("UPDATE entities SET type = ? WHERE id = ?", (entity_type, row["id"]))
                self.db.commit()
                row = self.db.execute(
                    "SELECT * FROM entities WHERE name = ?", (name,)
                ).fetchone()
            return self._row_to_entity(row)

        entity = Entity(
            name=name,
            id=str(uuid.uuid4()),
            type=entity_type,
            created_at=datetime.now(),
        )
        self.db.execute(
            "INSERT INTO entities (id, name, type, attrs, created_at) VALUES (?, ?, ?, ?, ?)",
            (entity.id, entity.name, entity.type, None, entity.created_at.isoformat()),
        )
        self.db.commit()
        return entity

    def get_by_name(self, name: str) -> Optional[Entity]:
        row = self.db.execute(
            "SELECT * FROM entities WHERE name = ?", (name,)
        ).fetchone()
        return self._row_to_entity(row) if row else None

    def get_all_names(self) -> list[str]:
        rows = self.db.execute("SELECT name FROM entities").fetchall()
        return [row["name"] for row in rows]

    def link_memory(self, memory_id: str, entity_id: str, role: str = "subject"):
        self.db.execute(
            "INSERT OR IGNORE INTO memory_entities (memory_id, entity_id, role) VALUES (?, ?, ?)",
            (memory_id, entity_id, role),
        )
        self.db.commit()

    def add_relation(
        self,
        source_id: str,
        target_id: str,
        relation: str,
        weight: float = 1.0,
    ) -> Relation:
        now = datetime.now()
        self.db.execute("""
            INSERT INTO relations (source_id, target_id, relation, weight, created_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(source_id, target_id, relation) DO UPDATE SET
                weight = excluded.weight,
                created_at = excluded.created_at
        """, (source_id, target_id, relation, weight, now.isoformat()))
        self.db.commit()
        return Relation(
            source_id=source_id,
            target_id=target_id,
            relation=relation,
            weight=weight,
            created_at=now,
        )

    def get_related_memories(self, entity_name: str) -> list[str]:
        rows = self.db.execute("""
            SELECT me.memory_id
            FROM memory_entities me
            JOIN entities e ON e.id = me.entity_id
            WHERE e.name = ?
        """, (entity_name,)).fetchall()
        return [row["memory_id"] for row in rows]

    def get_entity_neighbors(self, entity_id: str, max_depth: int = 2) -> list[str]:
        visited: set[str] = {entity_id}
        frontier = [entity_id]

        for _ in range(max_depth):
            if not frontier:
                break
            placeholders = ",".join("?" for _ in frontier)
            rows = self.db.execute(f"""
                SELECT target_id FROM relations WHERE source_id IN ({placeholders})
                UNION
                SELECT source_id FROM relations WHERE target_id IN ({placeholders})
            """, (*frontier, *frontier)).fetchall()

            next_frontier = []
            for row in rows:
                nid = row[0]
                if nid not in visited:
                    visited.add(nid)
                    next_frontier.append(nid)
            frontier = next_frontier

        visited.discard(entity_id)
        return list(visited)

    def list_all(self) -> list[Entity]:
        rows = self.db.execute("SELECT * FROM entities ORDER BY created_at DESC").fetchall()
        return [self._row_to_entity(row) for row in rows]

    @staticmethod
    def _row_to_entity(row) -> Entity:
        attrs = json.loads(row["attrs"]) if row["attrs"] else None
        return Entity(
            id=row["id"],
            name=row["name"],
            type=row["type"],
            attrs=attrs,
            created_at=datetime.fromisoformat(row["created_at"]),
        )
