from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from ..core.memory import Memory
from ..core.types import MemoryType
from ..storage.memory_store import MemoryStore


class ReadableSync:
    """将数据库记忆同步为 Markdown 文件"""

    def __init__(self, base_path: str | Path, store: MemoryStore):
        self.base = Path(base_path).expanduser()
        self.store = store
        self._ensure_dirs()

    def _ensure_dirs(self):
        for d in ["episodic", "semantic", "procedural"]:
            (self.base / d).mkdir(parents=True, exist_ok=True)

    def add(self, memory: Memory):
        self._write_memory(memory)
        self._update_overview()

    def update(self, memory: Memory):
        self._write_memory(memory)

    def archive(self, memory: Memory):
        src = self._memory_path(memory)
        if src.exists():
            archived_dir = src.parent / "_archived"
            archived_dir.mkdir(exist_ok=True)
            src.rename(archived_dir / src.name)

    def _write_memory(self, memory: Memory):
        path = self._memory_path(memory)
        path.parent.mkdir(parents=True, exist_ok=True)

        last_acc = (
            memory.last_accessed.strftime("%Y-%m-%d")
            if memory.last_accessed
            else "N/A"
        )
        entities_str = ", ".join(memory.entities) if memory.entities else "无"

        content = f"""# {memory.summary or memory.content[:60]}

**类型**: {memory.type.value} | **强度**: {memory.strength:.1f} | **访问**: {memory.access_count}次
**项目**: {memory.project or 'N/A'} | **创建**: {memory.created_at.strftime('%Y-%m-%d %H:%M')}
**实体**: {entities_str}

---

{memory.content}

---
_ID: {memory.id} | 最后访问: {last_acc}_
"""
        path.write_text(content, encoding="utf-8")

    def _memory_path(self, memory: Memory) -> Path:
        short_id = memory.id[:8]
        if memory.type == MemoryType.EPISODIC:
            month = memory.created_at.strftime("%Y-%m")
            return self.base / "episodic" / month / f"{short_id}.md"
        elif memory.type == MemoryType.SEMANTIC:
            project = memory.project or "_general"
            return self.base / "semantic" / project / f"{short_id}.md"
        else:
            return self.base / "procedural" / f"{short_id}.md"

    def _update_overview(self):
        stats = self.store.get_stats()
        core = self.store.list_active(types=["procedural"], min_strength=5.0)

        core_items = "\n".join(
            f"- {m.summary or m.content[:80]}" for m in core[:20]
        )

        content = f"""# 记忆系统总览

> 自动生成于 {datetime.now().strftime('%Y-%m-%d %H:%M')}

## 统计

- 总记忆: {stats['total']} (活跃: {stats['active']}, 归档: {stats['archived']})
- 情景: {stats['episodic']} | 语义: {stats['semantic']} | 程序: {stats['procedural']}
- 核心记忆 (strength≥5): {stats['core']}
- 实体: {stats['entities']} | 关系: {stats['relations']}
- 资产: {stats['assets_total']} (有效: {stats['assets_valid']})

## 核心偏好

{core_items or '(暂无)'}
"""
        (self.base / "OVERVIEW.md").write_text(content, encoding="utf-8")
