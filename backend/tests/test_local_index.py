"""LocalIndexSync 本地索引测试"""
import json
import tempfile
from pathlib import Path

import pytest

from ai_memory.core.memory import Memory
from ai_memory.core.types import AssetType
from ai_memory.storage.database import Database
from ai_memory.storage.memory_store import MemoryStore
from ai_memory.storage.entity_store import EntityStore
from ai_memory.asset.registry import AssetRegistry, Asset
from ai_memory.readable.local_index import LocalIndexSync


@pytest.fixture
def setup():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        db.initialize()

        readable_path = Path(tmpdir) / "readable"
        readable_path.mkdir()

        memory_store = MemoryStore(db)
        entity_store = EntityStore(db)
        asset_registry = AssetRegistry(db)

        sync = LocalIndexSync(readable_path, memory_store, entity_store, asset_registry)

        yield {
            "db": db,
            "sync": sync,
            "memory_store": memory_store,
            "entity_store": entity_store,
            "asset_registry": asset_registry,
            "readable_path": readable_path,
            "tmpdir": tmpdir,
        }
        db.close()


class TestLocalIndexSync:
    def _index_path(self, setup) -> Path:
        return setup["readable_path"] / "INDEX.json"

    def _load_index(self, setup) -> dict:
        return json.loads(self._index_path(setup).read_text(encoding="utf-8"))

    def test_rebuild_empty(self, setup):
        setup["sync"].rebuild()
        index = self._load_index(setup)
        assert index["memories"] == []
        assert index["assets"] == []
        assert index["entities"] == []
        assert "generated_at" in index

    def test_rebuild_with_data(self, setup):
        mem = Memory.create(content="IME 死锁修复", type="semantic", project="ingo", entities=["IME"])
        setup["memory_store"].save(mem)

        entity = setup["entity_store"].get_or_create("IME")
        setup["entity_store"].link_memory(mem.id, entity.id)

        artifact_dir = Path(setup["tmpdir"]) / "artifacts"
        artifact_dir.mkdir()
        asset = Asset(
            name="test-tool",
            type=AssetType.TOOL,
            artifact_path=str(artifact_dir),
            tags=["test"],
        )
        setup["asset_registry"].register(asset)

        setup["sync"].rebuild()
        index = self._load_index(setup)

        assert len(index["memories"]) == 1
        assert index["memories"][0]["id"] == mem.id
        assert index["memories"][0]["project"] == "ingo"

        assert len(index["assets"]) == 1
        assert index["assets"][0]["name"] == "test-tool"

        assert len(index["entities"]) == 1
        assert index["entities"][0]["name"] == "IME"

    def test_on_memory_change_add(self, setup):
        mem = Memory.create(content="新记忆", type="episodic")
        setup["memory_store"].save(mem)
        setup["sync"].on_memory_change(mem)

        index = self._load_index(setup)
        assert len(index["memories"]) == 1
        assert index["memories"][0]["id"] == mem.id

    def test_on_memory_change_update(self, setup):
        mem = Memory.create(content="原始", type="semantic")
        setup["memory_store"].save(mem)
        setup["sync"].on_memory_change(mem)

        mem.content = "更新后"
        mem.strength = 3.0
        setup["memory_store"].save(mem)
        setup["sync"].on_memory_change(mem)

        index = self._load_index(setup)
        assert len(index["memories"]) == 1
        assert index["memories"][0]["strength"] == 3.0

    def test_on_memory_change_archive(self, setup):
        mem = Memory.create(content="将被归档", type="episodic")
        setup["memory_store"].save(mem)
        setup["sync"].on_memory_change(mem)
        assert len(self._load_index(setup)["memories"]) == 1

        mem.archived = True
        setup["sync"].on_memory_change(mem)
        assert len(self._load_index(setup)["memories"]) == 0

    def test_on_asset_change(self, setup):
        artifact_dir = Path(setup["tmpdir"]) / "art"
        artifact_dir.mkdir()
        asset = Asset(
            name="jadx",
            type=AssetType.TOOL,
            artifact_path=str(artifact_dir),
            tags=["decompiler"],
        )
        setup["asset_registry"].register(asset)
        setup["sync"].on_asset_change(asset)

        index = self._load_index(setup)
        assert len(index["assets"]) == 1
        assert index["assets"][0]["name"] == "jadx"
        assert index["assets"][0]["valid"] is True

    def test_on_asset_change_invalidate(self, setup):
        artifact_dir = Path(setup["tmpdir"]) / "art2"
        artifact_dir.mkdir()
        asset = Asset(
            name="old-tool",
            type=AssetType.TOOL,
            artifact_path=str(artifact_dir),
        )
        setup["asset_registry"].register(asset)
        setup["sync"].on_asset_change(asset)

        asset.valid = False
        setup["sync"].on_asset_change(asset)

        index = self._load_index(setup)
        assert index["assets"][0]["valid"] is False

    def test_memory_file_path_in_index(self, setup):
        episodic = Memory.create(content="会话记录", type="episodic")
        semantic = Memory.create(content="知识", type="semantic", project="myproj")
        procedural = Memory.create(content="偏好", type="procedural")

        for m in [episodic, semantic, procedural]:
            setup["memory_store"].save(m)
            setup["sync"].on_memory_change(m)

        index = self._load_index(setup)
        files = {m["type"]: m["file"] for m in index["memories"]}

        assert files["episodic"].startswith("episodic/")
        assert files["semantic"].startswith("semantic/myproj/")
        assert files["procedural"].startswith("procedural/")

    def test_incremental_no_existing_falls_back_to_rebuild(self, setup):
        mem1 = Memory.create(content="记忆1", type="semantic")
        mem2 = Memory.create(content="记忆2", type="semantic")
        setup["memory_store"].save(mem1)
        setup["memory_store"].save(mem2)

        setup["sync"].on_memory_change(mem1)

        index = self._load_index(setup)
        assert len(index["memories"]) >= 1
