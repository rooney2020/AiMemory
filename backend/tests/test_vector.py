"""向量索引测试"""
import tempfile
from pathlib import Path

import pytest

from ai_memory.core.memory import Memory
from ai_memory.storage.database import Database
from ai_memory.storage.memory_store import MemoryStore
from ai_memory.embedding.local import LocalEmbedding
from ai_memory.index.vector import VectorIndex


def _vec_available() -> bool:
    try:
        import sqlite_vec
        return True
    except ImportError:
        return False


@pytest.fixture(scope="module")
def embed_model():
    """模块级别的嵌入模型（避免每个测试都加载）"""
    return LocalEmbedding(
        model_name="all-MiniLM-L6-v2",
        device="cpu",
        lazy_load=False,
    )


@pytest.fixture
def setup(embed_model):
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "test.db"
        db = Database(db_path)
        db.initialize()

        store = MemoryStore(db)
        vec = VectorIndex(db, embed_model)

        memories = [
            Memory.create(
                content="ABBA deadlock in MultiInstanceIMMS: inconsistent lock ordering of mMethodMap",
                type="semantic",
                project="ingo",
            ),
            Memory.create(
                content="showImeRunner race condition: target and mImeRequester mismatch sends showInsets to wrong window",
                type="semantic",
                project="ingo",
            ),
            Memory.create(
                content="ZPPB-14002 input method full screen: Baidu IME getDisplayId returns wrong value causing keyboard overlay",
                type="semantic",
                project="ingo",
            ),
            Memory.create(
                content="User prefers Catppuccin Mocha dark theme for all applications",
                type="procedural",
            ),
            Memory.create(
                content="Python is a high-level programming language known for readability",
                type="semantic",
            ),
        ]

        for mem in memories:
            store.save(mem)
            vec.add(mem.id, mem.content)

        yield {
            "db": db,
            "store": store,
            "vec": vec,
            "memories": memories,
            "embed_model": embed_model,
        }
        db.close()


@pytest.mark.skipif(
    not _vec_available(),
    reason="sqlite-vec not available",
)
class TestVectorIndex:
    def test_available(self, setup):
        assert setup["vec"].available is True

    def test_search_semantic(self, setup):
        results = setup["vec"].search("IME deadlock problem")
        assert len(results) >= 1
        top_id = results[0][0]
        assert top_id == setup["memories"][0].id

    def test_search_similar_concept(self, setup):
        results = setup["vec"].search("keyboard display bug")
        assert len(results) >= 1
        ids = [r[0] for r in results[:3]]
        assert setup["memories"][2].id in ids

    def test_find_similar_dedup(self, setup):
        similar = setup["vec"].find_similar(
            "ABBA deadlock: lock ordering inconsistency in MultiInstanceIMMS",
            threshold=0.5,
        )
        assert len(similar) >= 1
        assert similar[0][0] == setup["memories"][0].id

    def test_find_similar_no_match(self, setup):
        similar = setup["vec"].find_similar(
            "Completely unrelated content about cooking recipes",
            threshold=0.15,
        )
        assert len(similar) == 0

    def test_search_with_project_filter(self, setup):
        results = setup["vec"].search("theme preference", project="ingo")
        ids = [r[0] for r in results]
        assert setup["memories"][3].id in ids

    def test_remove(self, setup):
        mid = setup["memories"][4].id
        setup["vec"].remove(mid)
        results = setup["vec"].search("Python programming language")
        ids = [r[0] for r in results]
        assert mid not in ids
