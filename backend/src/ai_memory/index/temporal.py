from __future__ import annotations

from datetime import datetime, timedelta
from typing import Optional

from ..storage.database import Database


class TemporalIndex:
    """L3: 时间窗口查询"""

    def __init__(self, db: Database):
        self.db = db

    def query(
        self,
        time_range: tuple[datetime, datetime],
        project: Optional[str] = None,
        top_k: int = 30,
    ) -> list[tuple[str, float]]:
        """按时间范围检索，返回 [(memory_id, recency_score), ...]"""
        start, end = time_range
        conditions = [
            "archived = 0",
            "created_at >= ?",
            "created_at <= ?",
        ]
        params: list = [start.isoformat(), end.isoformat()]

        if project:
            conditions.append("project = ?")
            params.append(project)

        where = " AND ".join(conditions)
        rows = self.db.execute(f"""
            SELECT id, created_at FROM memories
            WHERE {where}
            ORDER BY created_at DESC
            LIMIT ?
        """, (*params, top_k)).fetchall()

        now = datetime.now()
        results = []
        for row in rows:
            created = datetime.fromisoformat(row["created_at"])
            days_ago = max((now - created).days, 1)
            recency_score = 1.0 / days_ago
            results.append((row["id"], recency_score))

        return results

    @staticmethod
    def parse_time_range(spec: str) -> tuple[datetime, datetime]:
        now = datetime.now()
        spec = spec.strip().lower()

        if spec == "last_week":
            return (now - timedelta(days=7), now)
        elif spec == "last_month":
            return (now - timedelta(days=30), now)
        elif spec == "last_3_months":
            return (now - timedelta(days=90), now)
        elif ".." in spec:
            parts = spec.split("..")
            start = datetime.fromisoformat(parts[0].strip())
            end = datetime.fromisoformat(parts[1].strip())
            return (start, end)
        else:
            return (now - timedelta(days=30), now)
