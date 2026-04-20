from __future__ import annotations

import struct
import logging
from typing import Optional

from ..embedding.base import EmbeddingModel
from ..storage.database import Database

logger = logging.getLogger("ai-memory.vector")


class VectorIndex:
    """L1: sqlite-vec 向量索引"""

    def __init__(self, db: Database, embed_model: EmbeddingModel):
        self.db = db
        self.embed_model = embed_model
        self._vec_loaded = False
        self._init_vec()

    def _init_vec(self):
        """加载 sqlite-vec 扩展并创建虚拟表"""
        try:
            import sqlite_vec
            self.db.conn.enable_load_extension(True)
            sqlite_vec.load(self.db.conn)
            self.db.conn.enable_load_extension(False)
            self._vec_loaded = True

            dim = self.embed_model.dimension()
            self.db.execute(f"""
                CREATE VIRTUAL TABLE IF NOT EXISTS memories_vec
                USING vec0(id TEXT PRIMARY KEY, embedding float[{dim}])
            """)
            self.db.commit()
            logger.info(f"sqlite-vec 初始化完成, 维度={dim}")
        except ImportError:
            logger.warning("sqlite-vec 未安装，向量搜索不可用")
        except Exception as e:
            logger.warning(f"sqlite-vec 初始化失败: {e}")

    @property
    def available(self) -> bool:
        return self._vec_loaded

    def add(self, memory_id: str, text: str) -> Optional[list[float]]:
        """生成嵌入并添加到向量索引"""
        if not self.available:
            return None

        embedding = self.embed_model.encode(text)
        vec_bytes = _floats_to_bytes(embedding)

        self.db.execute(
            "UPDATE memories SET embedding = ? WHERE id = ?",
            (vec_bytes, memory_id),
        )
        self.db.execute(
            "INSERT OR REPLACE INTO memories_vec(id, embedding) VALUES (?, ?)",
            (memory_id, vec_bytes),
        )
        self.db.commit()
        return embedding

    def add_batch(self, items: list[tuple[str, str]]):
        """批量添加 [(memory_id, text), ...]"""
        if not self.available or not items:
            return

        texts = [text for _, text in items]
        embeddings = self.embed_model.encode_batch(texts)

        for (mid, _), emb in zip(items, embeddings):
            vec_bytes = _floats_to_bytes(emb)
            self.db.execute(
                "UPDATE memories SET embedding = ? WHERE id = ?",
                (vec_bytes, mid),
            )
            self.db.execute(
                "INSERT OR REPLACE INTO memories_vec(id, embedding) VALUES (?, ?)",
                (mid, vec_bytes),
            )
        self.db.commit()

    def search(
        self,
        query: str,
        top_k: int = 10,
        project: Optional[str] = None,
    ) -> list[tuple[str, float]]:
        """向量近邻搜索，返回 [(memory_id, distance), ...]"""
        if not self.available:
            return []

        query_embedding = self.embed_model.encode(query)
        query_bytes = _floats_to_bytes(query_embedding)

        rows = self.db.execute("""
            SELECT id, distance
            FROM memories_vec
            WHERE embedding MATCH ?
              AND k = ?
            ORDER BY distance
        """, (query_bytes, top_k * 2)).fetchall()

        if project:
            filtered = []
            for row in rows:
                mem = self.db.execute(
                    "SELECT 1 FROM memories WHERE id=? AND (project=? OR project IS NULL) AND archived=0",
                    (row["id"], project),
                ).fetchone()
                if mem:
                    filtered.append((row["id"], row["distance"]))
            return filtered[:top_k]

        return [(row["id"], row["distance"]) for row in rows[:top_k]]

    def find_similar(self, text: str, threshold: float = 0.1, top_k: int = 3) -> list[tuple[str, float]]:
        """找到与给定文本高度相似的记忆（用于去重）"""
        if not self.available:
            return []

        query_embedding = self.embed_model.encode(text)
        query_bytes = _floats_to_bytes(query_embedding)

        rows = self.db.execute("""
            SELECT id, distance
            FROM memories_vec
            WHERE embedding MATCH ?
              AND k = ?
            ORDER BY distance
        """, (query_bytes, top_k)).fetchall()

        return [(row["id"], row["distance"]) for row in rows if row["distance"] < threshold]

    def remove(self, memory_id: str):
        """从向量索引中移除"""
        if self.available:
            self.db.execute("DELETE FROM memories_vec WHERE id = ?", (memory_id,))
            self.db.commit()


def _floats_to_bytes(floats: list[float]) -> bytes:
    """将浮点数列表转为 little-endian float32 字节"""
    return struct.pack(f"<{len(floats)}f", *floats)


def _bytes_to_floats(data: bytes) -> list[float]:
    """将字节转回浮点数列表"""
    count = len(data) // 4
    return list(struct.unpack(f"<{count}f", data))
