from __future__ import annotations

from ..storage.database import Database


class FTSIndex:
    """L0: SQLite FTS5 全文搜索 + LIKE 降级"""

    def __init__(self, db: Database):
        self.db = db

    def search(self, query: str, top_k: int = 30) -> list[tuple[str, float]]:
        """
        混合搜索：先 FTS5 BM25，结果不足时用 LIKE 补充。
        返回 [(memory_id, score), ...] 按分数降序。
        """
        if not query.strip():
            return []

        results: dict[str, float] = {}

        fts_query = self._build_fts_query(query)
        if fts_query:
            try:
                rows = self.db.execute("""
                    SELECT m.id, bm25(memories_fts, 1.0, 10.0) AS score
                    FROM memories_fts fts
                    JOIN memories m ON m.rowid = fts.rowid
                    WHERE memories_fts MATCH ?
                      AND m.archived = 0
                    ORDER BY score
                    LIMIT ?
                """, (fts_query, top_k)).fetchall()
                for row in rows:
                    results[row["id"]] = -row["score"]
            except Exception:
                pass

        if results:
            max_score = max(results.values())
            if max_score > 0:
                threshold = max_score * 0.5
                results = {k: v for k, v in results.items() if v >= threshold}

        if not results:
            like_results = self._like_search(query, top_k)
            for mid, score in like_results:
                if mid not in results:
                    results[mid] = score

        sorted_results = sorted(results.items(), key=lambda x: x[1], reverse=True)
        return sorted_results[:top_k]

    def _like_search(self, query: str, top_k: int) -> list[tuple[str, float]]:
        """LIKE 降级搜索：按子串匹配，支持中文滑动窗口"""
        search_terms = self._extract_search_terms(query)
        if not search_terms:
            return []

        conditions = []
        params = []
        for term in search_terms:
            conditions.append("(content LIKE ? OR summary LIKE ?)")
            params.extend([f"%{term}%", f"%{term}%"])

        where = " OR ".join(conditions)
        rows = self.db.execute(f"""
            SELECT id FROM memories
            WHERE ({where}) AND archived = 0
            LIMIT ?
        """, (*params, top_k)).fetchall()

        return [(row["id"], 1.0) for row in rows]

    @staticmethod
    def _extract_search_terms(query: str) -> list[str]:
        """从查询中提取搜索词，包括中文滑动窗口"""
        terms = set()
        tokens = query.strip().split()

        for token in tokens:
            if len(token) >= 2:
                terms.add(token)

            has_cjk = any('\u4e00' <= c <= '\u9fff' for c in token)
            if has_cjk and len(token) > 2:
                for window_size in (2, 3):
                    for i in range(len(token) - window_size + 1):
                        sub = token[i:i + window_size]
                        if any('\u4e00' <= c <= '\u9fff' for c in sub):
                            terms.add(sub)

        return list(terms)

    @staticmethod
    def _build_fts_query(query: str) -> str:
        tokens = query.strip().split()
        if not tokens:
            return ""
        if len(tokens) == 1:
            return tokens[0]
        return " OR ".join(tokens)
