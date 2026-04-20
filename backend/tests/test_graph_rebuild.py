import tempfile
from pathlib import Path

from ai_memory.core.memory import Memory
from ai_memory.storage.database import Database
from ai_memory.storage.memory_store import MemoryStore
from ai_memory.tools.graph_rebuild import EntityExtractor, GraphRebuilder


def test_entity_extractor_merges_existing_project_and_keywords():
    extractor = EntityExtractor({"CustomTool": "tool"})
    memory = Memory.create(
        content="AI Memory 依赖 SQLite，并优先使用 interactive_feedback。",
        type="semantic",
        project="ingo",
    )
    memory.tags = ["日报"]
    memory.entities = ["MCP"]

    entities = extractor.extract(memory)
    assert set(entities) >= {"MCP", "ingo", "AI Memory", "SQLite", "interactive_feedback", "日报"}


def test_entity_extractor_does_not_match_ascii_substrings_inside_words():
    extractor = EntityExtractor()
    memory = Memory.create(
        content="runtime timeline sometime",
        type="semantic",
    )

    entities = extractor.extract(memory)
    assert "IME" not in entities


def test_graph_rebuilder_rebuilds_entities_and_relations():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        db.initialize()
        store = MemoryStore(db)

        memory = Memory.create(
            content="AI Memory 依赖 SQLite，并包含 GraphIndex 模块。",
            type="semantic",
        )
        store.save(memory)

        rebuilder = GraphRebuilder(db)
        stats = rebuilder.rebuild()

        loaded = store.get(memory.id)
        assert set(loaded.entities) >= {"AI Memory", "SQLite", "GraphIndex"}
        assert stats.entities_total >= 3

        rows = db.execute(
            """
            SELECT e1.name AS source_name, e2.name AS target_name, r.relation
            FROM relations r
            JOIN entities e1 ON e1.id = r.source_id
            JOIN entities e2 ON e2.id = r.target_id
            """
        ).fetchall()
        relation_names = {tuple(row) for row in rows}
        assert ("AI Memory", "SQLite", "depends_on") in relation_names
        assert ("AI Memory", "GraphIndex", "contains") in relation_names

        db.close()