from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Optional

from ..core.memory import Memory
from ..core.types import MemoryType
from .database import Database
from .entity_store import EntityStore


class MemoryStore:
    AUTO_RELATION = "co_occurs"
    RELATION_KEYWORDS = {
        "fixes": ("修复", "解决", "处理", "修正", "fixes", "resolves"),
        "contains": ("包含", "包括", "含有", "组成", "内含", "contains", "includes"),
        "depends_on": ("依赖", "基于", "使用", "采用", "调用", "引用", "depends on", "uses", "calls", "imports"),
        "causes": ("导致", "引发", "造成", "触发", "causes", "triggers"),
    }
    SENTENCE_SPLIT_RE = re.compile(r"[。！？!?；;\n]+")
    RELATION_TYPE_RULES = {
        "contains": {
            "source": {"project", "component"},
            "target": {"component", "issue", "workflow"},
        },
        "depends_on": {
            "source": {"project", "component", "tool", "workflow"},
            "target": {"technology", "tool", "component", "project"},
        },
        "fixes": {
            "source": {"project", "component", "tool", "workflow"},
            "target": {"issue"},
        },
        "causes": {
            "source": {"project", "component", "tool", "issue"},
            "target": {"issue", "component"},
        },
    }

    def __init__(self, db: Database):
        self.db = db
        self.entity_store = EntityStore(db)

    def save(self, memory: Memory) -> Memory:
        now = datetime.now()
        if not memory.created_at:
            memory.created_at = now
        memory.updated_at = now
        memory.entities = self._normalize_entities(memory.entities)
        entities_json = json.dumps(memory.entities, ensure_ascii=False) if memory.entities else "[]"
        tags_json = json.dumps(memory.tags, ensure_ascii=False) if hasattr(memory, 'tags') and memory.tags else "[]"

        self.db.execute("""
            INSERT INTO memories (
                id, type, content, summary, embedding,
                project, session_id, entities, tags, created_at, updated_at,
                strength, access_count, last_accessed, decay_rate, archived
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                content=excluded.content,
                summary=excluded.summary,
                embedding=excluded.embedding,
                entities=excluded.entities,
                tags=excluded.tags,
                updated_at=excluded.updated_at,
                strength=excluded.strength,
                access_count=excluded.access_count,
                last_accessed=excluded.last_accessed,
                archived=excluded.archived
        """, (
            memory.id, memory.type.value, memory.content, memory.summary,
            memory.embedding,
            memory.project, memory.session_id, entities_json, tags_json,
            memory.created_at.isoformat(), memory.updated_at.isoformat(),
            memory.strength, memory.access_count,
            memory.last_accessed.isoformat() if memory.last_accessed else None,
            memory.decay_rate, int(memory.archived),
        ))
        self.db.commit()
        self._sync_memory_entities(memory)
        self._sync_memory_relations(memory)
        return memory

    def get(self, memory_id: str) -> Optional[Memory]:
        row = self.db.execute(
            "SELECT * FROM memories WHERE id = ?", (memory_id,)
        ).fetchone()
        if row is None:
            return None
        return self._row_to_memory(row)

    def delete(self, memory_id: str):
        self._clear_memory_relations(memory_id)
        self._clear_memory_entities(memory_id)
        self.db.execute("DELETE FROM memories WHERE id = ?", (memory_id,))
        self.db.commit()

    def rebuild_graph(self, memory: Memory, persist_entities: bool = False) -> Memory:
        memory.entities = self._normalize_entities(memory.entities)
        if persist_entities:
            entities_json = json.dumps(memory.entities, ensure_ascii=False) if memory.entities else "[]"
            self.db.execute(
                "UPDATE memories SET entities = ? WHERE id = ?",
                (entities_json, memory.id),
            )
            self.db.commit()

        self._sync_memory_entities(memory)
        self._sync_memory_relations(memory)
        return memory

    def list_active(
        self,
        types: Optional[list[str]] = None,
        exclude_types: Optional[list[str]] = None,
        project: Optional[str] = None,
        min_strength: Optional[float] = None,
        max_strength: Optional[float] = None,
        last_accessed_before: Optional[datetime] = None,
        order_by: str = "created_at DESC",
        limit: Optional[int] = None,
    ) -> list[Memory]:
        conditions = ["archived = 0"]
        params: list = []

        if types:
            placeholders = ",".join("?" for _ in types)
            conditions.append(f"type IN ({placeholders})")
            params.extend(types)

        if exclude_types:
            placeholders = ",".join("?" for _ in exclude_types)
            conditions.append(f"type NOT IN ({placeholders})")
            params.extend(exclude_types)

        if project:
            conditions.append("project = ?")
            params.append(project)

        if min_strength is not None:
            conditions.append("strength >= ?")
            params.append(min_strength)

        if max_strength is not None:
            conditions.append("strength < ?")
            params.append(max_strength)

        if last_accessed_before is not None:
            conditions.append("(last_accessed IS NULL OR last_accessed < ?)")
            params.append(last_accessed_before.isoformat())

        where = " AND ".join(conditions)
        sql = f"SELECT * FROM memories WHERE {where} ORDER BY {order_by}"
        if limit:
            sql += f" LIMIT {limit}"

        rows = self.db.execute(sql, tuple(params)).fetchall()
        return [self._row_to_memory(row) for row in rows]

    def get_stats(self) -> dict:
        conn = self.db.conn
        total = conn.execute("SELECT COUNT(*) FROM memories").fetchone()[0]
        active = conn.execute("SELECT COUNT(*) FROM memories WHERE archived=0").fetchone()[0]
        archived = total - active
        episodic = conn.execute("SELECT COUNT(*) FROM memories WHERE type='episodic' AND archived=0").fetchone()[0]
        semantic = conn.execute("SELECT COUNT(*) FROM memories WHERE type='semantic' AND archived=0").fetchone()[0]
        procedural = conn.execute("SELECT COUNT(*) FROM memories WHERE type='procedural' AND archived=0").fetchone()[0]
        core = conn.execute(f"SELECT COUNT(*) FROM memories WHERE strength >= 5.0 AND archived=0").fetchone()[0]
        entities = conn.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        relations = conn.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        assets_total = conn.execute("SELECT COUNT(*) FROM assets").fetchone()[0]
        assets_valid = conn.execute("SELECT COUNT(*) FROM assets WHERE valid=1").fetchone()[0]

        return {
            "total": total,
            "active": active,
            "archived": archived,
            "episodic": episodic,
            "semantic": semantic,
            "procedural": procedural,
            "core": core,
            "entities": entities,
            "relations": relations,
            "assets_total": assets_total,
            "assets_valid": assets_valid,
        }

    @staticmethod
    def _row_to_memory(row) -> Memory:
        entities = json.loads(row["entities"]) if row["entities"] else []
        tags = json.loads(row["tags"]) if "tags" in row.keys() and row["tags"] else []
        last_accessed = (
            datetime.fromisoformat(row["last_accessed"])
            if row["last_accessed"]
            else None
        )
        return Memory(
            id=row["id"],
            type=MemoryType(row["type"]),
            content=row["content"],
            summary=row["summary"],
            embedding=row["embedding"],
            project=row["project"],
            session_id=row["session_id"],
            entities=entities,
            tags=tags,
            created_at=datetime.fromisoformat(row["created_at"]),
            updated_at=datetime.fromisoformat(row["updated_at"]),
            strength=row["strength"],
            access_count=row["access_count"],
            last_accessed=last_accessed,
            decay_rate=row["decay_rate"],
            archived=bool(row["archived"]),
        )

    @staticmethod
    def _normalize_entities(entities: list[str] | None) -> list[str]:
        if not entities:
            return []

        normalized = []
        seen: set[str] = set()
        for entity in entities:
            if not isinstance(entity, str):
                continue
            name = entity.strip()
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                continue
            seen.add(key)
            normalized.append(name)
        return normalized

    def _clear_memory_entities(self, memory_id: str):
        self.db.execute("DELETE FROM memory_entities WHERE memory_id = ?", (memory_id,))
        self.db.commit()

    def _sync_memory_entities(self, memory: Memory):
        self._clear_memory_entities(memory.id)
        if not memory.entities:
            return

        for entity_name in memory.entities:
            entity = self.entity_store.get_or_create(entity_name)
            self.entity_store.link_memory(memory.id, entity.id, role="mentioned")

    def _clear_memory_relations(self, memory_id: str):
        affected_pairs = self._get_memory_relation_keys(memory_id)
        self.db.execute("DELETE FROM memory_relations WHERE memory_id = ?", (memory_id,))
        self.db.commit()
        for source_id, target_id, relation in affected_pairs:
            self._refresh_aggregated_relation(source_id, target_id, relation)

    def _sync_memory_relations(self, memory: Memory):
        previous_pairs = self._get_memory_relation_keys(memory.id)
        current_pairs = self._build_memory_relation_rows(memory)

        self.db.execute("DELETE FROM memory_relations WHERE memory_id = ?", (memory.id,))
        if current_pairs:
            self.db.executemany(
                """
                INSERT INTO memory_relations (memory_id, source_id, target_id, relation, weight, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                current_pairs,
            )
        self.db.commit()

        affected_pairs = previous_pairs | {
            (source_id, target_id, relation)
            for _, source_id, target_id, relation, _, _ in current_pairs
        }
        for source_id, target_id, relation in affected_pairs:
            self._refresh_aggregated_relation(source_id, target_id, relation)

    def _build_memory_relation_rows(self, memory: Memory) -> list[tuple[str, str, str, str, float, str]]:
        entity_refs: list[tuple[str, str, str | None]] = []
        for entity_name in memory.entities:
            entity = self.entity_store.get_or_create(entity_name)
            entity_refs.append((entity.name, entity.id, entity.type))

        if len(entity_refs) < 2:
            return []

        created_at = datetime.now().isoformat()
        rows: dict[tuple[str, str, str], tuple[str, str, str, str, float, str]] = {}

        for source_name, source_id, _, target_name, target_id, _ in self._iter_sorted_entity_pairs(entity_refs):
            rows[(source_id, target_id, self.AUTO_RELATION)] = (
                memory.id,
                source_id,
                target_id,
                self.AUTO_RELATION,
                1.0,
                created_at,
            )

        for source_id, target_id, relation in self._extract_semantic_relation_keys(memory, entity_refs):
            rows[(source_id, target_id, relation)] = (
                memory.id,
                source_id,
                target_id,
                relation,
                1.0,
                created_at,
            )

        return list(rows.values())

    @staticmethod
    def _iter_sorted_entity_pairs(entity_refs: list[tuple[str, str, str | None]]):
        sorted_refs = sorted(entity_refs, key=lambda item: item[0].casefold())
        for index, (source_name, source_id, source_type) in enumerate(sorted_refs[:-1]):
            for target_name, target_id, target_type in sorted_refs[index + 1:]:
                yield source_name, source_id, source_type, target_name, target_id, target_type

    def _extract_semantic_relation_keys(
        self,
        memory: Memory,
        entity_refs: list[tuple[str, str, str | None]],
    ) -> set[tuple[str, str, str]]:
        text_parts = [memory.summary or "", memory.content or ""]
        text = "\n".join(part for part in text_parts if part)
        if not text:
            return set()

        relation_keys: set[tuple[str, str, str]] = set()
        for sentence in self.SENTENCE_SPLIT_RE.split(text):
            sentence = sentence.strip()
            if not sentence:
                continue

            mentions: list[tuple[int, str, str, str | None]] = []
            for entity_name, entity_id, entity_type in entity_refs:
                position = sentence.find(entity_name)
                if position >= 0:
                    mentions.append((position, entity_name, entity_id, entity_type))

            mentions.sort(key=lambda item: item[0])
            if len(mentions) < 2:
                continue

            for index, (source_pos, source_name, source_id, source_type) in enumerate(mentions[:-1]):
                if index > 0:
                    continue
                source_end = source_pos + len(source_name)
                for target_pos, target_name, target_id, target_type in mentions[index + 1:]:
                    gap = sentence[source_end:target_pos]
                    relation = self._classify_relation_gap(gap)
                    if relation and self._relation_type_allowed(relation, source_type, target_type):
                        relation_keys.add((source_id, target_id, relation))

        return relation_keys

    @classmethod
    def _classify_relation_gap(cls, gap: str) -> Optional[str]:
        if not gap:
            return None

        normalized_gap = gap.casefold()
        best_relation: Optional[str] = None
        best_position = -1

        for relation, keywords in cls.RELATION_KEYWORDS.items():
            for keyword in keywords:
                position = normalized_gap.rfind(keyword.casefold())
                if position > best_position:
                    best_relation = relation
                    best_position = position

        return best_relation if best_position >= 0 else None

    @classmethod
    def _relation_type_allowed(
        cls,
        relation: str,
        source_type: str | None,
        target_type: str | None,
    ) -> bool:
        rules = cls.RELATION_TYPE_RULES.get(relation)
        if not rules:
            return True

        allowed_sources = rules.get("source")
        allowed_targets = rules.get("target")
        if source_type and allowed_sources and source_type not in allowed_sources:
            return False
        if target_type and allowed_targets and target_type not in allowed_targets:
            return False
        return True

    def _get_memory_relation_keys(self, memory_id: str) -> set[tuple[str, str, str]]:
        rows = self.db.execute(
            "SELECT source_id, target_id, relation FROM memory_relations WHERE memory_id = ?",
            (memory_id,),
        ).fetchall()
        return {(row["source_id"], row["target_id"], row["relation"]) for row in rows}

    def _refresh_aggregated_relation(self, source_id: str, target_id: str, relation: str):
        row = self.db.execute(
            """
            SELECT COALESCE(SUM(weight), 0) AS total_weight
            FROM memory_relations
            WHERE source_id = ? AND target_id = ? AND relation = ?
            """,
            (source_id, target_id, relation),
        ).fetchone()
        total_weight = float(row["total_weight"] or 0.0)

        if total_weight <= 0:
            self.db.execute(
                "DELETE FROM relations WHERE source_id = ? AND target_id = ? AND relation = ?",
                (source_id, target_id, relation),
            )
            self.db.commit()
            return

        self.entity_store.add_relation(source_id, target_id, relation, weight=total_weight)
