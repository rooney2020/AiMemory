"""基础存储层测试"""
import tempfile
from pathlib import Path

import pytest

from ai_memory.config import Config, MemoryConfig
from ai_memory.core.memory import Memory
from ai_memory.core.types import MemoryType
from ai_memory.storage.database import Database
from ai_memory.storage.memory_store import MemoryStore
from ai_memory.storage.entity_store import EntityStore


@pytest.fixture
def db():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        database = Database(db_path)
        database.initialize()
        yield database
        database.close()


@pytest.fixture
def memory_store(db):
    return MemoryStore(db)


@pytest.fixture
def entity_store(db):
    return EntityStore(db)


class TestMemoryStore:
    def test_save_and_get(self, memory_store):
        mem = Memory.create(
            content="ABBA 死锁：两个 mMethodMap 锁顺序不一致",
            type="semantic",
            project="ingo",
            entities=["IME死锁", "mMethodMap"],
        )
        memory_store.save(mem)

        loaded = memory_store.get(mem.id)
        assert loaded is not None
        assert loaded.content == mem.content
        assert loaded.type == MemoryType.SEMANTIC
        assert loaded.project == "ingo"
        assert "IME死锁" in loaded.entities
        assert loaded.strength == 1.0

    def test_save_upsert(self, memory_store):
        mem = Memory.create(content="原始内容", type="episodic")
        memory_store.save(mem)

        mem.content = "更新后内容"
        mem.strength = 3.0
        memory_store.save(mem)

        loaded = memory_store.get(mem.id)
        assert loaded.content == "更新后内容"
        assert loaded.strength == 3.0

    def test_save_upsert_updates_entities(self, memory_store):
        mem = Memory.create(content="原始内容", type="episodic", entities=["A", "B"])
        memory_store.save(mem)

        mem.entities = ["A", "C"]
        memory_store.save(mem)

        loaded = memory_store.get(mem.id)
        assert loaded.entities == ["A", "C"]

    def test_auto_relations_created_from_entities(self, memory_store, db):
        mem = Memory.create(content="图谱关系", type="semantic", entities=["A", "B", "C"])
        memory_store.save(mem)

        rows = db.execute(
            "SELECT relation, weight FROM relations ORDER BY source_id, target_id"
        ).fetchall()
        assert len(rows) == 3
        assert {row["relation"] for row in rows} == {"co_occurs"}
        assert {row["weight"] for row in rows} == {1.0}

    def test_auto_relations_rebuild_on_update(self, memory_store, db):
        mem = Memory.create(content="图谱关系", type="semantic", entities=["A", "B"])
        memory_store.save(mem)

        mem.entities = ["A", "C"]
        memory_store.save(mem)

        relation_names = {
            tuple(row)
            for row in db.execute(
                """
                SELECT e1.name, e2.name, r.relation
                FROM relations r
                JOIN entities e1 ON e1.id = r.source_id
                JOIN entities e2 ON e2.id = r.target_id
                """
            ).fetchall()
        }
        assert relation_names == {("A", "C", "co_occurs")}

    def test_semantic_relations_extracted_from_content(self, memory_store, db):
        mem = Memory.create(
            content=(
                "AI Memory 依赖 SQLite，并包含 GraphIndex 模块。"
                "GraphIndex 使用 SQLite。"
                "BugFix 修复 CrashIssue。"
                "LoopA 导致 LoopB。"
            ),
            type="semantic",
            entities=["AI Memory", "SQLite", "GraphIndex", "BugFix", "CrashIssue", "LoopA", "LoopB"],
        )
        memory_store.save(mem)

        rows = db.execute(
            """
            SELECT e1.name AS source_name, e2.name AS target_name, r.relation
            FROM relations r
            JOIN entities e1 ON e1.id = r.source_id
            JOIN entities e2 ON e2.id = r.target_id
            WHERE r.relation != 'co_occurs'
            """
        ).fetchall()
        relation_names = {tuple(row) for row in rows}
        assert relation_names == {
            ("AI Memory", "SQLite", "depends_on"),
            ("AI Memory", "GraphIndex", "contains"),
            ("GraphIndex", "SQLite", "depends_on"),
            ("BugFix", "CrashIssue", "fixes"),
            ("LoopA", "LoopB", "causes"),
        }

    def test_semantic_relations_respect_entity_types(self, memory_store, db):
        memory_store.entity_store.get_or_create("图谱页", "component")
        memory_store.entity_store.get_or_create("Qt", "technology")
        memory_store.entity_store.get_or_create("Android", "technology")
        memory_store.entity_store.get_or_create("ingo", "project")

        mem = Memory.create(
            content="图谱页导致 Qt。Android 修复 ingo。",
            type="semantic",
            entities=["图谱页", "Qt", "Android", "ingo"],
        )
        memory_store.save(mem)

        rows = db.execute(
            "SELECT relation FROM relations WHERE relation != 'co_occurs'"
        ).fetchall()
        assert rows == []

    def test_auto_relations_aggregate_and_cleanup_on_delete(self, memory_store, db):
        mem1 = Memory.create(content="关系1", type="semantic", entities=["A", "B"])
        mem2 = Memory.create(content="关系2", type="semantic", entities=["B", "A"])
        memory_store.save(mem1)
        memory_store.save(mem2)

        row = db.execute("SELECT weight FROM relations WHERE relation = 'co_occurs'").fetchone()
        assert row["weight"] == 2.0

        memory_store.delete(mem1.id)
        row = db.execute("SELECT weight FROM relations WHERE relation = 'co_occurs'").fetchone()
        assert row["weight"] == 1.0

        memory_store.delete(mem2.id)
        row = db.execute("SELECT COUNT(*) AS count FROM relations WHERE relation = 'co_occurs'").fetchone()
        assert row["count"] == 0

    def test_list_active(self, memory_store):
        for i in range(5):
            mem = Memory.create(
                content=f"记忆 {i}",
                type="episodic" if i % 2 == 0 else "semantic",
                project="ingo",
            )
            memory_store.save(mem)

        all_active = memory_store.list_active()
        assert len(all_active) == 5

        episodic = memory_store.list_active(types=["episodic"])
        assert len(episodic) == 3

        semantic = memory_store.list_active(types=["semantic"])
        assert len(semantic) == 2

    def test_list_active_with_strength_filter(self, memory_store):
        for s in [0.5, 1.0, 3.0, 5.0, 8.0]:
            mem = Memory.create(content=f"strength={s}", type="semantic")
            mem.strength = s
            memory_store.save(mem)

        strong = memory_store.list_active(min_strength=5.0)
        assert len(strong) == 2

        weak = memory_store.list_active(max_strength=2.0)
        assert len(weak) == 2

    def test_archived_excluded(self, memory_store):
        mem = Memory.create(content="将被归档", type="episodic")
        mem.archived = True
        memory_store.save(mem)

        active = memory_store.list_active()
        assert len(active) == 0

    def test_get_stats(self, memory_store):
        memory_store.save(Memory.create(content="e1", type="episodic"))
        memory_store.save(Memory.create(content="s1", type="semantic"))
        memory_store.save(Memory.create(content="p1", type="procedural", importance="critical"))

        stats = memory_store.get_stats()
        assert stats["total"] == 3
        assert stats["active"] == 3
        assert stats["episodic"] == 1
        assert stats["semantic"] == 1
        assert stats["procedural"] == 1
        assert stats["core"] == 1


class TestEntityStore:
    def test_get_or_create(self, entity_store):
        e1 = entity_store.get_or_create("IME死锁")
        e2 = entity_store.get_or_create("IME死锁")
        assert e1.id == e2.id
        assert e1.name == "IME死锁"

    def test_link_memory(self, entity_store, memory_store):
        mem = Memory.create(content="测试", type="episodic")
        memory_store.save(mem)

        entity = entity_store.get_or_create("TestEntity")
        entity_store.link_memory(mem.id, entity.id)

        related = entity_store.get_related_memories("TestEntity")
        assert mem.id in related

    def test_add_relation(self, entity_store):
        e1 = entity_store.get_or_create("BugA")
        e2 = entity_store.get_or_create("FixA")
        entity_store.add_relation(e1.id, e2.id, "fixes")

        neighbors = entity_store.get_entity_neighbors(e1.id, max_depth=1)
        assert e2.id in neighbors

    def test_get_all_names(self, entity_store):
        entity_store.get_or_create("A")
        entity_store.get_or_create("B")
        entity_store.get_or_create("C")
        names = entity_store.get_all_names()
        assert set(names) == {"A", "B", "C"}
