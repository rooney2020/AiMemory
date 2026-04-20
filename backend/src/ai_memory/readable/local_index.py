from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core.memory import Memory
from ..core.types import MemoryType
from ..storage.memory_store import MemoryStore
from ..storage.entity_store import EntityStore
from ..asset.registry import AssetRegistry, Asset


class LocalIndexSync:
    """生成 INDEX.json 供 MCP 不可用时降级使用"""

    def __init__(
        self,
        readable_path: str | Path,
        memory_store: MemoryStore,
        entity_store: EntityStore,
        asset_registry: AssetRegistry,
    ):
        self.base = Path(readable_path).expanduser()
        self.store = memory_store
        self.entity_store = entity_store
        self.assets = asset_registry

    def rebuild(self):
        """全量重建索引"""
        index = {
            "generated_at": datetime.now().isoformat(),
            "memories": [],
            "assets": [],
            "entities": [],
        }

        for mem in self.store.list_active():
            index["memories"].append(self._memory_entry(mem))

        for asset in self.assets.lookup(valid_only=False):
            index["assets"].append(self._asset_entry(asset))

        for entity in self.entity_store.list_all():
            related = self.entity_store.get_related_memories(entity.name)
            index["entities"].append({
                "name": entity.name,
                "type": entity.type,
                "related_memories": related,
            })

        self._write_index(index)

    def on_memory_change(self, memory: Memory):
        """记忆变更时增量更新"""
        index = self._read_index()
        if index is None:
            return self.rebuild()

        index["generated_at"] = datetime.now().isoformat()
        entry = self._memory_entry(memory)

        found = False
        for i, m in enumerate(index["memories"]):
            if m["id"] == memory.id:
                if memory.archived:
                    index["memories"].pop(i)
                else:
                    index["memories"][i] = entry
                found = True
                break

        if not found and not memory.archived:
            index["memories"].append(entry)

        self._write_index(index)

    def on_asset_change(self, asset: Asset):
        """资产变更时增量更新"""
        index = self._read_index()
        if index is None:
            return self.rebuild()

        index["generated_at"] = datetime.now().isoformat()
        entry = self._asset_entry(asset)

        found = False
        for i, a in enumerate(index["assets"]):
            if a["id"] == asset.id:
                index["assets"][i] = entry
                found = True
                break

        if not found:
            index["assets"].append(entry)

        self._write_index(index)

    def _memory_entry(self, mem: Memory) -> dict:
        short_id = mem.id[:8]
        if mem.type == MemoryType.EPISODIC:
            month = mem.created_at.strftime("%Y-%m")
            file_path = f"episodic/{month}/{short_id}.md"
        elif mem.type == MemoryType.SEMANTIC:
            project = mem.project or "_general"
            file_path = f"semantic/{project}/{short_id}.md"
        else:
            file_path = f"procedural/{short_id}.md"

        return {
            "id": mem.id,
            "type": mem.type.value,
            "summary": mem.summary or mem.content[:80],
            "project": mem.project,
            "entities": mem.entities,
            "strength": round(mem.strength, 1),
            "created_at": mem.created_at.strftime("%Y-%m-%d"),
            "file": file_path,
        }

    @staticmethod
    def _asset_entry(asset: Asset) -> dict:
        return {
            "id": asset.id,
            "type": asset.type.value,
            "name": asset.name,
            "source_hash": asset.source_hash,
            "artifact_path": asset.artifact_path,
            "tags": asset.tags,
            "valid": asset.valid,
        }

    def _read_index(self) -> Optional[dict]:
        index_path = self.base / "INDEX.json"
        if not index_path.exists():
            return None
        try:
            return json.loads(index_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return None

    def _write_index(self, index: dict):
        self.base.mkdir(parents=True, exist_ok=True)
        index_path = self.base / "INDEX.json"
        index_path.write_text(
            json.dumps(index, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
