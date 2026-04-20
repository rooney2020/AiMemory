#!/usr/bin/env python3
"""
从现有 ~/.local/share/ai-memory/ Markdown 方案迁移到新数据库。

迁移映射：
  MEMORY.md 用户偏好   → procedural memories (strength=5.0)
  MEMORY.md 重要决策   → semantic memories (strength=3.0)
  MEMORY.md 已知问题   → semantic memories (strength=3.0)
  agents/*.md          → episodic memories (每个会话一条)
  topics/*.md          → semantic memories (每个议题一条)

用法：
  python scripts/migrate_from_markdown.py [--source ~/.local/share/ai-memory] [--db-path ~/.local/share/ai-memory/db/memory.db]
  python scripts/migrate_from_markdown.py --dry-run  # 预览不写入
"""

import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from ai_memory.config import load_config
from ai_memory.core.memory import Memory
from ai_memory.core.types import MemoryType
from ai_memory.storage.database import Database
from ai_memory.storage.memory_store import MemoryStore
from ai_memory.storage.entity_store import EntityStore


def extract_section(text: str, heading: str) -> str:
    pattern = rf"##\s+{re.escape(heading)}\s*\n(.*?)(?=\n##\s|\Z)"
    match = re.search(pattern, text, re.DOTALL)
    return match.group(1).strip() if match else ""


def parse_list_items(text: str) -> list[str]:
    items = []
    for line in text.strip().split("\n"):
        line = line.strip()
        if line.startswith("- ") or line.startswith("* "):
            items.append(line[2:].strip())
    return items


def extract_date(text: str) -> datetime:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", text)
    if match:
        return datetime.fromisoformat(match.group(1))
    return datetime.now()


def migrate_memory_md(path: Path) -> list[Memory]:
    if not path.exists():
        print(f"  跳过: {path} 不存在")
        return []

    content = path.read_text(encoding="utf-8")
    memories = []

    prefs = extract_section(content, "用户偏好")
    for item in parse_list_items(prefs):
        memories.append(Memory.create(
            content=item,
            type="procedural",
            importance="critical",
            summary=item[:80],
        ))

    decisions = extract_section(content, "重要决策")
    for item in parse_list_items(decisions):
        date = extract_date(item)
        mem = Memory.create(
            content=item,
            type="semantic",
            importance="high",
            summary=item[:80],
        )
        mem.created_at = date
        memories.append(mem)

    issues = extract_section(content, "已知问题")
    for item in parse_list_items(issues):
        mem = Memory.create(
            content=item,
            type="semantic",
            importance="normal",
            summary=item[:80],
        )
        memories.append(mem)

    return memories


def migrate_agents(agents_dir: Path) -> list[Memory]:
    if not agents_dir.exists():
        print(f"  跳过: {agents_dir} 不存在")
        return []

    memories = []
    for f in sorted(agents_dir.glob("*.md")):
        if f.name == "INDEX.md":
            continue

        content = f.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        title = lines[0].lstrip("# ").strip() if lines else f.stem

        date = extract_date(title) if re.search(r"\d{4}-\d{2}-\d{2}", title) else extract_date(f.stem)

        project_match = re.search(r"\*\*项目\*\*:\s*(\S+)", content)
        project = project_match.group(1) if project_match else None

        truncated = content[:3000]

        mem = Memory.create(
            content=truncated,
            type="episodic",
            importance="normal",
            summary=title[:80],
            project=project,
        )
        mem.created_at = date
        memories.append(mem)

    return memories


def migrate_topics(topics_dir: Path) -> list[tuple[Memory, list[str]]]:
    if not topics_dir.exists():
        print(f"  跳过: {topics_dir} 不存在")
        return []

    results = []
    for f in sorted(topics_dir.glob("*.md")):
        if f.name == "INDEX.md":
            continue

        content = f.read_text(encoding="utf-8")
        lines = content.strip().split("\n")
        title = lines[0].lstrip("# ").strip() if lines else f.stem

        entities = [title]
        for line in lines:
            if "ZPPB-" in line:
                match = re.search(r"(ZPPB-\d+)", line)
                if match and match.group(1) not in entities:
                    entities.append(match.group(1))

        truncated = content[:3000]

        mem = Memory.create(
            content=truncated,
            type="semantic",
            importance="high",
            summary=title[:80],
            entities=entities,
        )
        results.append((mem, entities))

    return results


def run_migration(source_dir: Path, db_path: Path, dry_run: bool = False):
    print(f"=== 迁移开始 ===")
    print(f"源目录: {source_dir}")
    print(f"目标数据库: {db_path}")
    print(f"模式: {'预览(dry-run)' if dry_run else '实际写入'}")
    print()

    all_memories: list[Memory] = []
    all_entities: list[tuple[str, list[str]]] = []

    print("1. 迁移 MEMORY.md")
    memory_md = source_dir / "MEMORY.md"
    md_memories = migrate_memory_md(memory_md)
    print(f"  → {len(md_memories)} 条 (偏好/决策/问题)")
    all_memories.extend(md_memories)

    print("2. 迁移 agents/")
    agent_memories = migrate_agents(source_dir / "agents")
    print(f"  → {len(agent_memories)} 条 (会话记录)")
    all_memories.extend(agent_memories)

    print("3. 迁移 topics/")
    topic_results = migrate_topics(source_dir / "topics")
    print(f"  → {len(topic_results)} 条 (知识库)")
    for mem, entities in topic_results:
        all_memories.append(mem)
        all_entities.append((mem.id, entities))

    print(f"\n总计: {len(all_memories)} 条记忆待导入")

    type_counts = {}
    for m in all_memories:
        type_counts[m.type.value] = type_counts.get(m.type.value, 0) + 1
    for t, c in type_counts.items():
        print(f"  {t}: {c}")

    if dry_run:
        print("\n[DRY RUN] 以上为预览，未写入数据库")
        return

    print("\n写入数据库...")
    db = Database(db_path)
    db.initialize()
    store = MemoryStore(db)
    entity_store = EntityStore(db)

    for mem in all_memories:
        store.save(mem)

    for mem_id, entity_names in all_entities:
        for name in entity_names:
            entity = entity_store.get_or_create(name)
            entity_store.link_memory(mem_id, entity.id)

    stats = store.get_stats()
    print(f"\n=== 迁移完成 ===")
    print(f"数据库记忆: {stats['total']} (活跃: {stats['active']})")
    print(f"实体: {stats['entities']}")
    db.close()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="从 Markdown 方案迁移到新数据库")
    parser.add_argument("--source", default="~/.local/share/ai-memory", help="源目录")
    parser.add_argument("--db-path", default=None, help="目标数据库路径")
    parser.add_argument("--dry-run", action="store_true", help="仅预览不写入")
    args = parser.parse_args()

    source = Path(args.source).expanduser()
    if args.db_path:
        db_path = Path(args.db_path).expanduser()
    else:
        config = load_config()
        db_path = config.db_path

    run_migration(source, db_path, dry_run=args.dry_run)
