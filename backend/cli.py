#!/usr/bin/env python3
"""ai-memory CLI - 通过命令行操作记忆系统，替代 MCP 调用"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path


class _Encoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, datetime):
            return o.isoformat()
        return super().default(o)


def _json(obj, **kw):
    return json.dumps(obj, cls=_Encoder, ensure_ascii=False, **kw)


def _init_db():
    from ai_memory.config import load_config
    from ai_memory.storage.database import Database
    cfg = load_config()
    db = Database(cfg.db_path)
    db.initialize()
    return db


def _init_store(db):
    from ai_memory.storage.memory_store import MemoryStore
    return MemoryStore(db)


def _init_assets(db):
    from ai_memory.asset.registry import AssetRegistry
    return AssetRegistry(db)


def _memory_to_dict(m):
    return {
        "id": m.id,
        "type": m.type.value if hasattr(m.type, "value") else str(m.type),
        "content": m.content,
        "summary": m.summary,
        "strength": m.strength,
        "project": m.project,
        "entities": m.entities,
        "tags": getattr(m, "tags", []),
        "created_at": m.created_at,
        "updated_at": m.updated_at,
    }


def _asset_to_dict(a):
    return {
        "id": a.id,
        "name": a.name,
        "type": a.type.value if hasattr(a.type, "value") else str(a.type),
        "artifact_path": a.artifact_path,
        "source_path": getattr(a, "source_path", None),
        "description": getattr(a, "description", None),
        "tags": getattr(a, "tags", []),
        "project": getattr(a, "project", None),
        "valid": getattr(a, "valid", True),
        "use_count": getattr(a, "use_count", 0),
    }


def cmd_remember(args):
    from ai_memory.core.memory import Memory
    db = _init_db()
    store = _init_store(db)
    m = Memory.create(
        content=args.content,
        type=args.type,
        importance=args.importance or "normal",
        summary=args.summary,
        project=args.project,
        entities=args.entities.split(",") if args.entities else None,
    )
    # 处理 tags
    if args.tags:
        m.tags = args.tags.split(",")
    store.save(m)
    print(_json({"status": "ok", "id": m.id, "type": args.type}))


def cmd_recall(args):
    db = _init_db()
    store = _init_store(db)

    try:
        from ai_memory.config import load_config
        from ai_memory.index.fts import FTSIndex
        from ai_memory.index.graph import GraphIndex
        from ai_memory.index.temporal import TemporalIndex
        from ai_memory.index.fusion import FusionRetriever
        from ai_memory.storage.entity_store import EntityStore

        cfg = load_config()
        fts = FTSIndex(db)
        es = EntityStore(db)
        graph = GraphIndex(db, es)
        temporal = TemporalIndex(db)
        retriever = FusionRetriever(fts, graph, temporal, store, cfg)
        results = retriever.retrieve(
            query=args.query,
            memory_type=args.type,
            project=args.project,
            top_k=args.limit or 10,
        )
        memories = []
        for r in results:
            m = store.get(r.memory_id)
            if m:
                d = _memory_to_dict(m)
                d["score"] = round(r.score, 4)
                memories.append(d)
    except Exception:
        memories_raw = store.list_active(
            types=[args.type] if args.type else None,
            project=args.project,
            limit=args.limit or 10,
        )
        memories = [_memory_to_dict(m) for m in memories_raw]

    print(_json(memories, indent=2))


def cmd_working(args):
    db = _init_db()
    store = _init_store(db)

    prefs = store.list_active(types=["procedural"], limit=20)
    recent = store.list_active(limit=10)

    output = {
        "preferences": [{"summary": m.summary, "content": m.content} for m in prefs],
        "recent_activity": [
            {"type": m.type.value if hasattr(m.type, "value") else str(m.type),
             "summary": m.summary,
             "created_at": m.created_at}
            for m in recent
        ],
    }
    print(_json(output, indent=2))


def cmd_update(args):
    db = _init_db()
    store = _init_store(db)
    m = store.get(args.id)
    if not m:
        print(_json({"status": "error", "message": f"记忆 {args.id} 不存在"}))
        return
    
    # 处理 append 模式
    if args.append and args.content:
        m.content = m.content + "\n\n" + args.content
    elif args.content:
        m.content = args.content
    
    if args.summary:
        m.summary = args.summary

    if args.entities:
        entity_list = [item.strip() for item in args.entities.split(",") if item.strip()]
        if args.append_entities:
            existing_entities = list(m.entities) if getattr(m, "entities", None) else []
            seen = {entity.casefold() for entity in existing_entities if isinstance(entity, str)}
            for entity in entity_list:
                key = entity.casefold()
                if key in seen:
                    continue
                seen.add(key)
                existing_entities.append(entity)
            m.entities = existing_entities
        else:
            m.entities = entity_list
    
    # 处理 tags
    if args.tags:
        if args.append_tags:
            # 追加标签
            existing_tags = list(m.tags) if hasattr(m, 'tags') and m.tags else []
            new_tags = args.tags.split(",")
            m.tags = list(set(existing_tags + new_tags))
        else:
            m.tags = args.tags.split(",")
    
    if args.strength is not None:
        m.strength = max(0.0, min(10.0, args.strength))
    
    store.save(m)
    print(_json({"status": "ok", "id": m.id}))


def cmd_forget(args):
    db = _init_db()
    store = _init_store(db)
    store.delete(args.id)
    print(_json({"status": "ok", "deleted": args.id}))


def cmd_link(args):
    db = _init_db()
    try:
        from ai_memory.storage.entity_store import EntityStore
        es = EntityStore(db)
        es.add_relation(args.source, args.target, args.relation)
        print(_json({"status": "ok", "source": args.source, "target": args.target, "relation": args.relation}))
    except Exception as e:
        print(_json({"status": "error", "message": str(e)}))


def cmd_asset_register(args):
    from ai_memory.asset.registry import Asset
    from ai_memory.core.types import AssetType
    db = _init_db()
    reg = _init_assets(db)
    a = Asset(
        name=args.name,
        type=AssetType(args.type),
        artifact_path=args.path,
        source_path=args.source_path,
        description=args.description,
        tags=args.tags.split(",") if args.tags else [],
        project=args.project,
    )
    reg.register(a)
    print(_json({"status": "ok", "id": a.id, "name": a.name}))


def cmd_asset_lookup(args):
    db = _init_db()
    reg = _init_assets(db)
    results = reg.lookup(
        query=args.query,
        asset_type=args.type,
        project=args.project,
        tags=args.tags.split(",") if args.tags else None,
    )
    print(_json([_asset_to_dict(a) for a in results], indent=2))


def cmd_asset_use(args):
    db = _init_db()
    reg = _init_assets(db)
    reg.use(args.id)
    print(_json({"status": "ok", "id": args.id}))


def cmd_asset_invalidate(args):
    db = _init_db()
    reg = _init_assets(db)
    reg.invalidate(args.id, reason=args.reason)
    print(_json({"status": "ok", "id": args.id}))


def cmd_stats(args):
    db = _init_db()
    store = _init_store(db)
    stats = store.get_stats()
    print(_json(stats, indent=2))


def cmd_rebuild_graph(args):
    db = _init_db()
    from ai_memory.tools.graph_rebuild import GraphRebuilder

    rebuilder = GraphRebuilder(db)
    if args.dry_run:
        preview = rebuilder.preview(
            include_archived=args.include_archived,
            limit=args.limit,
        )
        print(_json({"status": "preview", **preview}, indent=2))
        return

    stats = rebuilder.rebuild(
        include_archived=args.include_archived,
        limit=args.limit,
    )
    print(_json({"status": "ok", **stats.to_dict()}, indent=2))


def main():
    parser = argparse.ArgumentParser(description="ai-memory CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    # remember
    p = sub.add_parser("remember", help="存储新记忆")
    p.add_argument("--content", required=True)
    p.add_argument("--type", required=True, choices=["episodic", "semantic", "procedural"])
    p.add_argument("--importance", default="normal", choices=["low", "normal", "high", "critical"])
    p.add_argument("--summary")
    p.add_argument("--project")
    p.add_argument("--entities", help="逗号分隔的实体列表")
    p.add_argument("--tags", help="逗号分隔的标签列表")

    # recall
    p = sub.add_parser("recall", help="检索记忆")
    p.add_argument("--query", required=True)
    p.add_argument("--type", choices=["episodic", "semantic", "procedural"])
    p.add_argument("--project")
    p.add_argument("--limit", type=int, default=10)

    # working
    sub.add_parser("working", help="获取工作记忆（偏好+最近活动）")

    # update
    p = sub.add_parser("update", help="更新记忆")
    p.add_argument("--id", required=True)
    p.add_argument("--content")
    p.add_argument("--summary")
    p.add_argument("--strength", type=float, help="强度值 (0.0~10.0)")
    p.add_argument("--append", action="store_true", help="追加内容而非替换")
    p.add_argument("--entities", help="实体，逗号分隔")
    p.add_argument("--append-entities", action="store_true", help="追加实体而非替换")
    p.add_argument("--tags", help="标签，逗号分隔")
    p.add_argument("--append-tags", action="store_true", help="追加标签而非替换")

    # forget
    p = sub.add_parser("forget", help="删除记忆")
    p.add_argument("--id", required=True)

    # link
    p = sub.add_parser("link", help="建立实体关联")
    p.add_argument("--source", required=True)
    p.add_argument("--target", required=True)
    p.add_argument("--relation", required=True)

    # asset-register
    p = sub.add_parser("asset-register", help="注册资产")
    p.add_argument("--name", required=True)
    p.add_argument("--type", required=True, choices=["app", "script", "tool", "data", "document", "config"])
    p.add_argument("--path", required=True, help="artifact_path")
    p.add_argument("--source-path")
    p.add_argument("--description")
    p.add_argument("--tags", help="逗号分隔")
    p.add_argument("--project")

    # asset-lookup
    p = sub.add_parser("asset-lookup", help="查找资产")
    p.add_argument("--query")
    p.add_argument("--type", choices=["app", "script", "tool", "data", "document", "config"])
    p.add_argument("--project")
    p.add_argument("--tags", help="逗号分隔")

    # asset-use
    p = sub.add_parser("asset-use", help="标记使用资产")
    p.add_argument("--id", required=True)

    # asset-invalidate
    p = sub.add_parser("asset-invalidate", help="标记资产失效")
    p.add_argument("--id", required=True)
    p.add_argument("--reason")

    # stats
    sub.add_parser("stats", help="系统统计")

    # rebuild-graph
    p = sub.add_parser("rebuild-graph", help="从现有记忆重建实体与关系图谱")
    p.add_argument("--include-archived", action="store_true", help="包含已归档记忆")
    p.add_argument("--limit", type=int, help="只处理最近 N 条记忆")
    p.add_argument("--dry-run", action="store_true", help="仅预览重建结果，不写入数据库")

    args = parser.parse_args()
    globals()[f"cmd_{args.command.replace('-', '_')}"](args)


if __name__ == "__main__":
    main()
