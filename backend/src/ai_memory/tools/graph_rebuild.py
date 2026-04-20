from __future__ import annotations

import json
import re
from dataclasses import dataclass

from ..core.memory import Memory
from ..storage.database import Database
from ..storage.entity_store import EntityStore
from ..storage.memory_store import MemoryStore


DEFAULT_ENTITY_TYPES = {
    "AI Memory": "project",
    "AI Memory Qt": "project",
    "FastPanel": "project",
    "CursorShare": "project",
    "OpenClaw": "project",
    "Toder": "tool",
    "Copilot": "tool",
    "Cursor": "tool",
    "PyQt5": "technology",
    "Qt": "technology",
    "Qt插件": "technology",
    "SQLite": "technology",
    "MCP": "technology",
    "Catppuccin": "technology",
    "AOSP": "technology",
    "Android": "technology",
    "Binder": "technology",
    "Playwright": "technology",
    "GraphIndex": "component",
    "IME": "component",
    "InputMethod": "component",
    "IMMS": "component",
    "interactive_feedback": "workflow",
    "AskQuestion": "workflow",
    "飞书": "tool",
    "Jira": "tool",
    "日报": "workflow",
    "会话记录": "component",
    "图谱页": "component",
    "资产页": "component",
    "死锁": "issue",
    "ABBA": "issue",
    "ZPPB-14002": "issue",
    "模糊": "issue",
    "blur": "issue",
}

ENTITY_ALIASES = {
    "AI Memory": ["AIMemory", "AiMemory"],
    "AI Memory Qt": ["AIMemory Qt", "AiMemory Qt"],
    "Copilot": ["GitHub Copilot"],
    "AskQuestion": ["AskQuestions"],
    "Qt插件": ["Qt 插件", "Qt plugin", "Qt plugins"],
}

ALIAS_TO_CANONICAL = {
    alias.casefold(): canonical
    for canonical, aliases in ENTITY_ALIASES.items()
    for alias in aliases
}

SEED_RELATIONS = [
    ("ingo", "IME", "contains"),
    ("ingo", "InputMethod", "contains"),
    ("ingo", "IMMS", "contains"),
    ("ingo", "ABBA", "contains"),
    ("ingo", "ZPPB-14002", "contains"),
    ("ingo", "AOSP", "depends_on"),
    ("ingo", "Android", "depends_on"),
    ("AI Memory", "SQLite", "depends_on"),
    ("AI Memory", "MCP", "depends_on"),
    ("AI Memory", "PyQt5", "depends_on"),
    ("AI Memory", "Catppuccin", "depends_on"),
    ("FastPanel", "PyQt5", "depends_on"),
    ("FastPanel", "Qt", "depends_on"),
    ("CursorShare", "MCP", "depends_on"),
    ("IME", "InputMethod", "relates_to"),
    ("IME", "IMMS", "relates_to"),
    ("ABBA", "IMMS", "relates_to"),
    ("模糊", "blur", "relates_to"),
]


@dataclass
class RebuildStats:
    memories_scanned: int = 0
    memories_with_entities: int = 0
    entity_links: int = 0
    entities_total: int = 0
    relations_total: int = 0
    changed_memories: int = 0

    def to_dict(self) -> dict:
        return {
            "memories_scanned": self.memories_scanned,
            "memories_with_entities": self.memories_with_entities,
            "entity_links": self.entity_links,
            "entities_total": self.entities_total,
            "relations_total": self.relations_total,
            "changed_memories": self.changed_memories,
        }


class EntityExtractor:
    def __init__(self, seed_entities: dict[str, str | None] | None = None):
        self.entity_types = dict(DEFAULT_ENTITY_TYPES)
        for name, entity_type in (seed_entities or {}).items():
            self.entity_types.setdefault(name, entity_type)
        self.match_patterns = self._build_match_patterns()

    def extract(
        self,
        memory: Memory,
        existing_entities: list[str] | None = None,
    ) -> list[str]:
        text_parts = [memory.summary or "", memory.content or ""]
        if memory.tags:
            text_parts.append(" ".join(memory.tags))
        haystack = "\n".join(part for part in text_parts if part)
        haystack_folded = haystack.casefold()

        entities: list[str] = []
        seen: set[str] = set()

        def add(name: str | None):
            if not name:
                return
            cleaned = self._canonical_name(name.strip())
            if not cleaned:
                return
            key = cleaned.casefold()
            if key in seen:
                return
            seen.add(key)
            entities.append(cleaned)

        for name in existing_entities or memory.entities or []:
            add(name)

        add(memory.project)

        for name, patterns in self.match_patterns:
            if any(self._matches(pattern, haystack, haystack_folded) for pattern in patterns):
                add(name)

        return entities

    def entity_type(self, name: str) -> str | None:
        return self.entity_types.get(self._canonical_name(name))

    @staticmethod
    def _canonical_name(name: str) -> str:
        return ALIAS_TO_CANONICAL.get(name.casefold(), name)

    def _build_match_patterns(self) -> list[tuple[str, list[str]]]:
        patterns = []
        names = sorted(self.entity_types, key=lambda item: (-len(item), item.casefold()))
        for name in names:
            aliases = ENTITY_ALIASES.get(name, [])
            patterns.append((name, [name, *aliases]))
        return patterns

    @staticmethod
    def _matches(pattern: str, haystack: str, haystack_folded: str) -> bool:
        if any("\u4e00" <= ch <= "\u9fff" for ch in pattern):
            return pattern in haystack

        escaped = re.escape(pattern.casefold())
        return re.search(rf"(?<![a-z0-9_\-]){escaped}(?![a-z0-9_\-])", haystack_folded) is not None


class GraphRebuilder:
    def __init__(self, db: Database):
        self.db = db
        self.store = MemoryStore(db)
        self.entity_store = EntityStore(db)
        self.extractor = EntityExtractor(self._load_seed_entities())

    def rebuild(self, include_archived: bool = False, limit: int | None = None) -> RebuildStats:
        memories = self._load_memories(include_archived=include_archived, limit=limit)
        extracted: list[tuple[Memory, list[str]]] = []
        stats = RebuildStats(memories_scanned=len(memories))

        for memory in memories:
            previous = list(memory.entities)
            entities = self.extractor.extract(memory, existing_entities=previous)
            if entities:
                stats.memories_with_entities += 1
            if entities != previous:
                stats.changed_memories += 1
            extracted.append((memory, entities))

        self._clear_graph_tables()

        for memory, entities in extracted:
            for entity_name in entities:
                desired_type = self.extractor.entity_type(entity_name)
                self.entity_store.get_or_create(entity_name, desired_type)

            memory.entities = entities
            self.store.rebuild_graph(memory, persist_entities=True)

            for entity_name in entities:
                entity = self.entity_store.get_by_name(entity_name)
                desired_type = self.extractor.entity_type(entity_name)
                if entity and desired_type and entity.type != desired_type:
                    self.db.execute(
                        "UPDATE entities SET type = ? WHERE id = ?",
                        (desired_type, entity.id),
                    )
                    self.db.commit()

        self._apply_seed_relations()

        stats.entity_links = self.db.execute("SELECT COUNT(*) FROM memory_entities").fetchone()[0]
        stats.entities_total = self.db.execute("SELECT COUNT(*) FROM entities").fetchone()[0]
        stats.relations_total = self.db.execute("SELECT COUNT(*) FROM relations").fetchone()[0]
        return stats

    def preview(self, include_archived: bool = False, limit: int | None = None, sample_size: int = 12) -> dict:
        memories = self._load_memories(include_archived=include_archived, limit=limit)
        samples = []
        changed = 0
        with_entities = 0

        for memory in memories:
            entities = self.extractor.extract(memory, existing_entities=memory.entities)
            if entities:
                with_entities += 1
            if entities != list(memory.entities):
                changed += 1
            if len(samples) < sample_size:
                samples.append({
                    "id": memory.id,
                    "type": memory.type.value if hasattr(memory.type, "value") else str(memory.type),
                    "summary": memory.summary,
                    "previous_entities": list(memory.entities),
                    "new_entities": entities,
                })

        return {
            "memories_scanned": len(memories),
            "memories_with_entities": with_entities,
            "changed_memories": changed,
            "samples": samples,
        }

    def _load_memories(self, include_archived: bool, limit: int | None) -> list[Memory]:
        if not include_archived:
            return self.store.list_active(limit=limit)

        sql = "SELECT * FROM memories ORDER BY updated_at DESC"
        if limit:
            sql += f" LIMIT {int(limit)}"
        rows = self.db.execute(sql).fetchall()
        return [self.store._row_to_memory(row) for row in rows]

    def _load_seed_entities(self) -> dict[str, str | None]:
        rows = self.db.execute("SELECT name, type FROM entities").fetchall()
        return {row["name"]: row["type"] for row in rows}

    def _clear_graph_tables(self):
        self.db.execute("DELETE FROM memory_relations")
        self.db.execute("DELETE FROM relations")
        self.db.execute("DELETE FROM memory_entities")
        self.db.execute("DELETE FROM entities")
        self.db.commit()

    def _apply_seed_relations(self):
        for source_name, target_name, relation in SEED_RELATIONS:
            source = self.entity_store.get_by_name(source_name)
            target = self.entity_store.get_by_name(target_name)
            if not source or not target:
                continue
            self.entity_store.add_relation(source.id, target.id, relation)