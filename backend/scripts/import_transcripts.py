#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""将 AI 记忆系统的所有数据源导入到数据库，包括：
1. MEMORY.md → procedural（偏好/规则）
2. agents/*.md → episodic（会话记录，完整内容）
3. topics/*.md → semantic（知识积累）
4. agent-transcripts/*.jsonl → 补充缺失的会话
"""

import json
import os
import re
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "backend" / "src"))

from ai_memory.config import load_config
from ai_memory.storage.database import Database
from ai_memory.storage.memory_store import MemoryStore
from ai_memory.storage.entity_store import EntityStore
from ai_memory.core.memory import Memory
from ai_memory.core.types import MemoryType

MEMORY_BASE = Path("/home/tsdl/.local/share/ai-memory")
TRANSCRIPT_BASE = Path("/home/tsdl/.local/share/ai-memory/projects")

config = load_config()
db = Database(str(config.db_path))
db.initialize()
store = MemoryStore(db)
entity_store = EntityStore(db)

db.execute("PRAGMA foreign_keys = OFF")
db.execute("DELETE FROM memory_entities")
db.execute("DELETE FROM relations")
db.execute("DELETE FROM entities")
db.execute("DELETE FROM memories")
db.execute("PRAGMA foreign_keys = ON")
db.commit()
print("已清空数据库\n")

entity_cache = {}
stats = {"episodic": 0, "semantic": 0, "procedural": 0}


def get_or_create_entity(name, etype=None):
    if name not in entity_cache:
        entity_cache[name] = entity_store.get_or_create(name, etype)
    return entity_cache[name]


def extract_entities(text):
    keywords = {
        "PyQt5": "technology", "Qt": "technology", "SQLite": "technology",
        "MCP": "technology", "Catppuccin": "technology", "AOSP": "technology",
        "Android": "technology", "Binder": "technology", "Playwright": "technology",
        "IME": "component", "InputMethod": "component", "IMMS": "component",
        "FastPanel": "project", "CursorShare": "project", "AI Memory": "project",
        "icon-picker": "project", "qt-style-showcase": "project", "ingo": "project",
        "死锁": "issue", "ABBA": "issue", "ZPPB-14002": "issue",
        "模糊": "issue", "blur": "issue",
        "飞书": "tool", "Jira": "tool", "日报": "workflow",
    }
    found = []
    for kw, etype in keywords.items():
        if kw in text:
            found.append(kw)
            get_or_create_entity(kw, etype)
    return found


def save_memory(mem_type, summary, content, importance="normal", project=None, 
                session_id=None, entities=None, created_at=None):
    mem = Memory.create(
        content=content,
        type=mem_type,
        importance=importance,
        summary=summary,
        project=project,
        session_id=session_id,
        entities=entities or [],
    )
    if created_at:
        mem.created_at = created_at
        mem.updated_at = created_at
    store.save(mem)
    stats[mem_type] += 1

    if entities:
        for ent_name in entities:
            ent = get_or_create_entity(ent_name)
            entity_store.link_memory(mem.id, ent.id)

    return mem


# ============================================================
# 1. MEMORY.md → procedural
# ============================================================
print("=== 1. 导入 MEMORY.md 偏好/规则 ===")

memory_md = MEMORY_BASE / "MEMORY.md"
if memory_md.exists():
    text = memory_md.read_text(encoding="utf-8")

    prefs_match = re.search(r"## 用户偏好\n(.*?)(?=\n## )", text, re.DOTALL)
    if prefs_match:
        for line in prefs_match.group(1).strip().split("\n"):
            line = line.strip()
            if line.startswith("- ") and len(line) > 10:
                pref = line[2:].strip()
                parts = pref.split("：", 1) if "：" in pref else pref.split(":", 1)
                summary = parts[0].strip()[:80]
                save_memory("procedural", summary, pref, "high")
                print(f"  偏好: {summary}")

    decisions_match = re.search(r"## 重要决策\n(.*?)(?=\n## )", text, re.DOTALL)
    if decisions_match:
        for line in decisions_match.group(1).strip().split("\n"):
            line = line.strip()
            if line.startswith("- ") and len(line) > 15:
                decision = line[2:].strip()
                if decision.startswith("~~"):
                    continue
                date_match = re.match(r"(\d{4}-\d{2}-\d{2}):\s*(.*)", decision)
                if date_match:
                    date_str, desc = date_match.groups()
                    summary = desc[:80]
                    try:
                        created = datetime.strptime(date_str, "%Y-%m-%d")
                    except:
                        created = None
                    entities_found = extract_entities(desc)
                    save_memory("semantic", summary, decision, "high",
                               created_at=created, entities=entities_found)
                    print(f"  决策: {summary}")

    issues_match = re.search(r"## 已知问题\n(.*?)(?=\n## )", text, re.DOTALL)
    if issues_match:
        for line in issues_match.group(1).strip().split("\n"):
            line = line.strip()
            if line.startswith("- ") and len(line) > 10:
                issue = line[2:].strip()
                summary = issue[:80]
                save_memory("semantic", summary, issue, "normal",
                            entities=extract_entities(issue))
                print(f"  已知问题: {summary}")


# ============================================================
# 2. agents/*.md → episodic (完整会话记录)
# ============================================================
print("\n=== 2. 导入 agents/ 会话记录 ===")

agents_dir = MEMORY_BASE / "agents"
imported_sessions = set()

for md_file in sorted(agents_dir.glob("2026-*.md")):
    text = md_file.read_text(encoding="utf-8")

    title_match = re.match(r"#\s+(.+)", text)
    title = title_match.group(1) if title_match else md_file.stem

    project_match = re.search(r"\*\*项目\*\*:\s*(.+?)[\s|]", text)
    project = project_match.group(1).strip() if project_match else None

    time_match = re.search(r"\*\*时间\*\*:\s*(\d{4}-\d{2}-\d{2})\s+(\d{2}:\d{2})", text)
    created = None
    if time_match:
        try:
            created = datetime.strptime(f"{time_match.group(1)} {time_match.group(2)}", "%Y-%m-%d %H:%M")
        except:
            pass
    if not created:
        date_match = re.search(r"(\d{4}-\d{2}-\d{2})", md_file.stem)
        if date_match:
            try:
                created = datetime.strptime(date_match.group(1), "%Y-%m-%d")
            except:
                pass

    dialogue_match = re.search(r"## 对话记录\n(.*?)(?=\n## |$)", text, re.DOTALL)
    dialogue = dialogue_match.group(1).strip() if dialogue_match else ""

    decisions_match = re.search(r"## 关键决策\n(.*?)(?=\n## |$)", text, re.DOTALL)
    decisions = decisions_match.group(1).strip() if decisions_match else ""

    content_parts = [f"# {title}"]
    if project:
        content_parts.append(f"项目: {project}")
    if dialogue:
        content_parts.append(f"\n## 对话记录\n{dialogue}")
    if decisions:
        content_parts.append(f"\n## 关键决策\n{decisions}")
    content = "\n".join(content_parts)

    entities_found = extract_entities(text)

    mem = save_memory(
        "episodic", title, content, "normal",
        project=project, entities=entities_found, created_at=created,
    )
    imported_sessions.add(md_file.stem)
    ent_str = ", ".join(entities_found[:5]) if entities_found else "-"
    print(f"  [{md_file.stem}] {title[:50]} | 实体:{ent_str}")


# ============================================================
# 3. topics/*.md → semantic (知识积累)
# ============================================================
print("\n=== 3. 导入 topics/ 知识库 ===")

topics_dir = MEMORY_BASE / "topics"
for md_file in sorted(topics_dir.glob("*.md")):
    if md_file.name == "INDEX.md":
        continue

    text = md_file.read_text(encoding="utf-8")
    title_match = re.match(r"#\s+(.+)", text)
    title = title_match.group(1) if title_match else md_file.stem

    status_match = re.search(r"\*\*状态\*\*:\s*(.+?)[\s|]", text)
    status = status_match.group(1).strip() if status_match else ""

    update_match = re.search(r"\*\*更新\*\*:\s*(\d{4}-\d{2}-\d{2})", text)
    created = None
    if update_match:
        try:
            created = datetime.strptime(update_match.group(1), "%Y-%m-%d")
        except:
            pass

    entities_found = extract_entities(text)

    save_memory(
        "semantic", title, text, "high",
        entities=entities_found, created_at=created,
    )
    print(f"  [{md_file.stem}] {title} | 状态:{status}")


# ============================================================
# 4. agent-transcripts/*.jsonl → 补充未被 agents/ 覆盖的会话
# ============================================================
print("\n=== 4. 导入 JSONL 聊天记录（补充） ===")

PROJECT_MAP = {
    "home-tsdl-ssd-code-projects-ingo": "ingo",
    "home-tsdl-ssd-temp-projects-test": "test",
    "home-tsdl-code-ingo": "ingo-old",
    "home-tsdl-ssd-code-aosp12": "aosp12",
    "home-tsdl-ssd-ingo-backup": "ingo-backup",
    "home-tsdl-ssd-temp-mcp": "mcp",
    "home-tsdl-ssd-temp-calendar": "calendar",
    "home-tsdl-code-private-MSPIME": "MSPIME",
}


def parse_jsonl(jsonl_path):
    user_msgs = []
    assistant_msgs = []
    try:
        with open(jsonl_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    continue
                role = entry.get("role", "")
                msg = entry.get("message", {})
                content = msg.get("content", "")

                texts = []
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, dict) and part.get("type") == "text":
                            t = part.get("text", "")
                            if "<user_query>" in t:
                                t = t.split("<user_query>")[-1].split("</user_query>")[0].strip()
                            elif t.startswith("<"):
                                continue
                            if t.strip():
                                texts.append(t.strip())
                elif isinstance(content, str) and content.strip():
                    texts.append(content.strip())

                combined = "\n".join(texts)
                if not combined:
                    continue
                if role == "user" and len(combined) > 3:
                    user_msgs.append(combined)
                elif role == "assistant" and len(combined) > 10:
                    assistant_msgs.append(combined)
    except Exception as e:
        return None, None
    return user_msgs, assistant_msgs


for at_dir in sorted(TRANSCRIPT_BASE.glob("*/agent-transcripts")):
    project_dir = at_dir.parent.name
    project_name = PROJECT_MAP.get(project_dir, project_dir.replace("tmp-cursor-proxy-", "proxy-"))

    for session_dir in sorted(at_dir.iterdir(), key=lambda d: d.stat().st_mtime):
        session_id = session_dir.name
        jsonl_files = list(session_dir.glob("*.jsonl"))
        if not jsonl_files:
            continue

        user_msgs, assistant_msgs = parse_jsonl(jsonl_files[0])
        if not user_msgs:
            continue

        file_time = datetime.fromtimestamp(jsonl_files[0].stat().st_mtime)

        content_parts = []
        content_parts.append("## 用户请求")
        for i, msg in enumerate(user_msgs, 1):
            content_parts.append(f"\n### {i}. 用户")
            content_parts.append(msg[:500])

        content_parts.append("\n## AI 回复摘要")
        for i, msg in enumerate(assistant_msgs[:5], 1):
            clean_msg = msg[:400]
            content_parts.append(f"\n### {i}. AI")
            content_parts.append(clean_msg)

        content = "\n".join(content_parts)
        if len(content) > 5000:
            content = content[:5000] + "\n\n...(内容过长，已截断)"

        summary = user_msgs[0][:100]
        full_text = " ".join(user_msgs) + " " + " ".join(assistant_msgs[:5])
        entities_found = extract_entities(full_text)

        save_memory(
            "episodic", summary, content, "normal",
            project=project_name, session_id=session_id,
            entities=entities_found, created_at=file_time,
        )
        ent_str = ", ".join(entities_found[:5]) if entities_found else "-"
        print(f"  [{project_name}] [{session_id[:8]}] {summary[:50]} | U:{len(user_msgs)} A:{len(assistant_msgs)} | 实体:{ent_str}")


# ============================================================
# 5. 建立实体关系
# ============================================================
print("\n=== 5. 建立实体关系 ===")

relation_rules = [
    ("ingo", "IME", "contains"),
    ("ingo", "InputMethod", "contains"),
    ("ingo", "IMMS", "contains"),
    ("ingo", "ABBA", "contains"),
    ("ingo", "ZPPB-14002", "contains"),
    ("ingo", "AOSP", "depends_on"),
    ("ingo", "Android", "depends_on"),
    ("AI Memory", "SQLite", "depends_on"),
    ("AI Memory", "MCP", "depends_on"),
    ("AI Memory", "PyQt5", "depends_on"),
    ("AI Memory", "Catppuccin", "depends_on"),
    ("FastPanel", "PyQt5", "depends_on"),
    ("FastPanel", "Qt", "depends_on"),
    ("CursorShare", "MCP", "depends_on"),
    ("qt-style-showcase", "PyQt5", "depends_on"),
    ("qt-style-showcase", "Catppuccin", "depends_on"),
    ("icon-picker", "PyQt5", "depends_on"),
    ("PyQt5", "Qt", "relates_to"),
    ("PyQt5", "Catppuccin", "relates_to"),
    ("IME", "InputMethod", "relates_to"),
    ("IME", "IMMS", "relates_to"),
    ("死锁", "ABBA", "relates_to"),
    ("ABBA", "IMMS", "relates_to"),
    ("模糊", "blur", "relates_to"),
]

rel_count = 0
for src, tgt, rel in relation_rules:
    if src in entity_cache and tgt in entity_cache:
        entity_store.add_relation(entity_cache[src].id, entity_cache[tgt].id, rel)
        rel_count += 1

print(f"  建立 {rel_count} 条关系")

# ============================================================
# 统计
# ============================================================
print(f"\n{'='*50}")
print(f"导入完成:")
print(f"  情景记忆 (episodic): {stats['episodic']}")
print(f"  语义知识 (semantic): {stats['semantic']}")
print(f"  偏好规则 (procedural): {stats['procedural']}")
print(f"  总计: {sum(stats.values())}")
print(f"  实体: {len(entity_cache)}")
print(f"  关系: {rel_count}")
