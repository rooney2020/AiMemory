"""索引层测试"""
import tempfile
from pathlib import Path

import pytest

from ai_memory.config import Config
from ai_memory.core.memory import Memory
from ai_memory.storage.database import Database
from ai_memory.storage.memory_store import MemoryStore
from ai_memory.storage.entity_store import EntityStore
from ai_memory.index.fts import FTSIndex
from ai_memory.index.graph import GraphIndex
from ai_memory.index.temporal import TemporalIndex
from ai_memory.index.fusion import FusionRetriever


@pytest.fixture
def setup():
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        db.initialize()

        store = MemoryStore(db)
        entity_store = EntityStore(db)
        fts = FTSIndex(db)
        graph = GraphIndex(db, entity_store)
        temporal = TemporalIndex(db)

        memories = [
            Memory.create(
                content="ABBA 死锁：MultiInstanceIMMS 中两个 mMethodMap 锁获取顺序不一致",
                type="semantic",
                project="ingo",
                entities=["IME死锁", "mMethodMap"],
            ),
            Memory.create(
                content="showImeRunner 时序问题：target 和 mImeRequester 不一致时 showInsets 发送到错误窗口",
                type="semantic",
                project="ingo",
                entities=["showImeRunner", "ImeInsetsSourceProvider"],
            ),
            Memory.create(
                content="ZPPB-14002 输入法霸屏：百度输入法 getDisplayId 取错导致键盘全屏显示",
                type="semantic",
                project="ingo",
                entities=["ZPPB-14002", "百度输入法"],
            ),
            Memory.create(
                content="用户偏好 Catppuccin Mocha 暗色主题",
                type="procedural",
                importance="critical",
            ),
            Memory.create(
                content="2026-03-27 验证三项修复全部通过",
                type="episodic",
                project="ingo",
            ),
        ]

        for mem in memories:
            store.save(mem)
            for ename in mem.entities:
                e = entity_store.get_or_create(ename)
                entity_store.link_memory(mem.id, e.id)

        entity_store.add_relation(
            entity_store.get_by_name("IME死锁").id,
            entity_store.get_by_name("mMethodMap").id,
            "causes",
        )

        yield {
            "db": db,
            "store": store,
            "entity_store": entity_store,
            "fts": fts,
            "graph": graph,
            "temporal": temporal,
            "memories": memories,
        }
        db.close()


class TestFTSIndex:
    def test_search_keyword(self, setup):
        results = setup["fts"].search("死锁")
        assert len(results) >= 1
        ids = [r[0] for r in results]
        assert setup["memories"][0].id in ids

    def test_search_english(self, setup):
        results = setup["fts"].search("showImeRunner")
        assert len(results) >= 1

    def test_search_no_match(self, setup):
        results = setup["fts"].search("完全不相关的内容xyzabc")
        assert len(results) == 0


class TestGraphIndex:
    def test_traverse(self, setup):
        results = setup["graph"].traverse(["IME死锁"])
        assert len(results) >= 1
        ids = [r[0] for r in results]
        assert setup["memories"][0].id in ids

    def test_traverse_neighbor(self, setup):
        results = setup["graph"].traverse(["mMethodMap"], max_depth=2)
        assert len(results) >= 1


class TestTemporalIndex:
    def test_parse_time_range(self):
        start, end = TemporalIndex.parse_time_range("last_week")
        assert (end - start).days == 7

    def test_parse_explicit_range(self):
        start, end = TemporalIndex.parse_time_range("2026-03-01..2026-03-27")
        assert start.month == 3
        assert start.day == 1


class TestFusionRetriever:
    def test_basic_retrieval(self, setup):
        config = Config()
        config.retrieval.channels["vector"].enabled = False

        retriever = FusionRetriever(
            fts_index=setup["fts"],
            graph_index=setup["graph"],
            temporal_index=setup["temporal"],
            memory_store=setup["store"],
            config=config,
        )

        results = retriever.retrieve("输入法死锁")
        assert len(results) >= 1
        assert results[0].score > 0

    def test_project_filter(self, setup):
        config = Config()
        config.retrieval.channels["vector"].enabled = False

        retriever = FusionRetriever(
            fts_index=setup["fts"],
            graph_index=setup["graph"],
            temporal_index=setup["temporal"],
            memory_store=setup["store"],
            config=config,
        )

        # Catppuccin 记忆 project=None，对所有项目可见
        results = retriever.retrieve("Catppuccin", project="ingo")
        assert len(results) >= 1

        # 非 ingo 项目的记忆不应该出现在 project=ingo 结果中
        results = retriever.retrieve("ABBA", project="nonexistent_project")
        ingo_ids = {m.id for m in setup["memories"] if m.project == "ingo"}
        result_ids = {r.memory_id for r in results}
        assert len(result_ids & ingo_ids) == 0
