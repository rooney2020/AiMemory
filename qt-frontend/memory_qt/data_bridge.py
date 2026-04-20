"""数据层封装 — 桥接 ai_memory 模块到 Qt 界面"""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from ai_memory.config import Config, load_config
from ai_memory.core.memory import Memory
from ai_memory.core.types import MemoryType
from ai_memory.storage.database import Database
from ai_memory.storage.memory_store import MemoryStore
from ai_memory.storage.entity_store import EntityStore
from ai_memory.asset.registry import AssetRegistry, Asset
from ai_memory.index.fts import FTSIndex
from ai_memory.index.graph import GraphIndex
from ai_memory.index.temporal import TemporalIndex
from ai_memory.index.fusion import FusionRetriever


class DataBridge:
    """Qt 前端的数据访问接口"""

    def __init__(self, db_path: str | Path | None = None):
        self.config = load_config()
        actual_path = Path(db_path).expanduser() if db_path else self.config.db_path

        self.db = Database(actual_path)
        self.db.initialize()

        self.memory_store = MemoryStore(self.db)
        self.entity_store = EntityStore(self.db)
        self.asset_registry = AssetRegistry(self.db)

        self.fts = FTSIndex(self.db)
        self.graph = GraphIndex(self.db, self.entity_store)
        self.temporal = TemporalIndex(self.db)
        self.retriever = FusionRetriever(
            fts_index=self.fts,
            graph_index=self.graph,
            temporal_index=self.temporal,
            memory_store=self.memory_store,
            config=self.config,
        )

    def close(self):
        self.db.close()

    def get_stats(self) -> dict:
        return self.memory_store.get_stats()

    def list_memories(
        self,
        types: list[str] | None = None,
        project: str | None = None,
        min_strength: float | None = None,
        limit: int | None = None,
    ) -> list[Memory]:
        return self.memory_store.list_active(
            types=types, project=project,
            min_strength=min_strength, limit=limit,
        )

    def get_memory(self, memory_id: str) -> Memory | None:
        return self.memory_store.get(memory_id)

    def update_memory(self, memory_id: str, **kwargs):
        """更新记忆字段：content, summary, status ('archived') 等"""
        mem = self.memory_store.get(memory_id)
        if not mem:
            return
        if "content" in kwargs:
            mem.content = kwargs["content"]
        if "summary" in kwargs:
            mem.summary = kwargs["summary"]
        if "strength" in kwargs:
            mem.strength = max(0.0, min(10.0, kwargs["strength"]))
        if "entities" in kwargs:
            mem.entities = list(kwargs["entities"] or [])
        if kwargs.get("append_entities"):
            existing_entities = list(mem.entities) if mem.entities else []
            seen = {entity.casefold() for entity in existing_entities if isinstance(entity, str)}
            for entity in kwargs["append_entities"]:
                if not isinstance(entity, str):
                    continue
                name = entity.strip()
                if not name:
                    continue
                key = name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                existing_entities.append(name)
            mem.entities = existing_entities
        if "status" in kwargs and kwargs["status"] == "archived":
            mem.archived = True
        self.memory_store.save(mem)

    def search(self, query: str, top_k: int = 10, project: str | None = None):
        return self.retriever.retrieve(query=query, top_k=top_k, project=project)

    def list_entities(self) -> list:
        return self.entity_store.list_all()

    def get_entity_names(self) -> list[str]:
        return self.entity_store.get_all_names()

    def get_related_memories(self, entity_name: str) -> list[str]:
        return self.entity_store.get_related_memories(entity_name)

    def get_entity_neighbors(self, entity_id: str, depth: int = 2) -> list[str]:
        return self.entity_store.get_entity_neighbors(entity_id, depth)

    def get_relations(self) -> list[dict]:
        rows = self.db.execute("""
            SELECT r.source_id, r.target_id, r.relation, r.weight,
                   e1.name as source_name, e2.name as target_name
            FROM relations r
            JOIN entities e1 ON e1.id = r.source_id
            JOIN entities e2 ON e2.id = r.target_id
        """).fetchall()
        return [dict(row) for row in rows]

    def list_assets(self, valid_only: bool = True) -> list[Asset]:
        return self.asset_registry.lookup(valid_only=valid_only)

    def validate_asset(self, asset_id: str) -> dict:
        return self.asset_registry.validate(asset_id)

    def delete_asset(self, asset_id: str):
        self.db.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        self.db.commit()

    def import_memory(self, mem) -> str:
        """导入记忆。返回 'new'/'skipped'"""
        existing = self.memory_store.get(mem.id)
        if existing:
            return "skipped"
        self.memory_store.save(mem)
        return "new"

    def import_asset(self, asset) -> str:
        """导入资产。返回 'new'/'skipped'"""
        existing = self.asset_registry.get(asset.id)
        if existing:
            return "skipped"
        self.asset_registry.register(asset)
        return "new"

    def batch_archive(self, memory_ids: list[str]):
        for mid in memory_ids:
            mem = self.memory_store.get(mid)
            if mem:
                mem.archived = True
                self.memory_store.save(mem)

    def batch_add_tag(self, memory_ids: list[str], tag: str):
        for mid in memory_ids:
            mem = self.memory_store.get(mid)
            if mem:
                tags = set(mem.tags) if mem.tags else set()
                tags.add(tag)
                mem.tags = list(tags)
                self.memory_store.save(mem)

    def add_entity(self, name: str, entity_type: str = "technology"):
        return self.entity_store.get_or_create(name, entity_type)

    def add_relation(self, source_id: str, target_id: str, relation: str, weight: float = 1.0):
        return self.entity_store.add_relation(source_id, target_id, relation, weight)

    def delete_entity(self, entity_id: str):
        self.db.execute("DELETE FROM memory_entities WHERE entity_id = ?", (entity_id,))
        self.db.execute("DELETE FROM relations WHERE source_id = ? OR target_id = ?", (entity_id, entity_id))
        self.db.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        self.db.commit()

    def delete_relation(self, source_id: str, target_id: str, relation: str):
        self.db.execute(
            "DELETE FROM relations WHERE source_id = ? AND target_id = ? AND relation = ?",
            (source_id, target_id, relation),
        )
        self.db.commit()

    def get_projects(self) -> list[str]:
        rows = self.db.execute(
            "SELECT DISTINCT project FROM memories WHERE project IS NOT NULL AND archived=0"
        ).fetchall()
        return [row["project"] for row in rows]
