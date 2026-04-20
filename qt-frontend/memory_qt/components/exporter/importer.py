"""导入功能 — 从 JSON ZIP 文件导入记忆和资产"""

import json

from PyQt5.QtWidgets import QWidget

_DIR_TO_MEM_TYPE = {"会话摘要": "episodic", "笔记": "semantic", "偏好": "procedural"}


def _parse_memory_from_json(data: dict):
    """从 JSON dict 重建 Memory 对象"""
    from ai_memory.core.memory import Memory
    from ai_memory.core.types import MemoryType
    from datetime import datetime

    return Memory(
        id=data["id"],
        type=MemoryType(data["type"]),
        content=data["content"],
        summary=data.get("summary"),
        project=data.get("project"),
        entities=data.get("entities", []),
        tags=data.get("tags", []),
        strength=data.get("strength", 1.0),
        access_count=data.get("access_count", 0),
        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
        updated_at=datetime.now(),
    )


def _parse_asset_from_json(data: dict):
    """从 JSON dict 重建 Asset 对象"""
    from ai_memory.asset.registry import Asset
    from ai_memory.core.types import AssetType
    from datetime import datetime

    return Asset(
        id=data["id"],
        name=data["name"],
        type=AssetType(data["type"]),
        artifact_path=data.get("artifact_path", ""),
        source_path=data.get("source_path"),
        description=data.get("description"),
        project=data.get("project"),
        tags=data.get("tags", []),
        valid=data.get("valid", True),
        created_at=datetime.fromisoformat(data["created_at"]) if data.get("created_at") else datetime.now(),
    )


def parse_import_zip(zip_path: str) -> dict:
    """解析 ZIP 文件，返回可导入的记忆和资产列表。
    仅支持 JSON 格式文件。"""
    import zipfile

    result = {
        "memories": [],
        "assets": [],
        "session_count": 0,
        "format": "unknown",
        "errors": [],
    }

    with zipfile.ZipFile(zip_path, "r") as zf:
        names = zf.namelist()
        json_files = [n for n in names if n.endswith(".json")]
        html_files = [n for n in names if n.endswith(".html")]

        if json_files:
            result["format"] = "JSON"
        elif html_files:
            result["format"] = "HTML"
            result["errors"].append("HTML 格式不支持导入，请使用 JSON 格式导出后再导入")
            return result
        else:
            md_files = [n for n in names if n.endswith(".md") or n.endswith(".txt")]
            if md_files:
                result["format"] = "Markdown/TXT"
                result["errors"].append("Markdown/TXT 格式不支持导入，请使用 JSON 格式导出后再导入")
                return result
            result["errors"].append("ZIP 中未找到可识别的文件")
            return result

        for name in json_files:
            parts = name.split("/")
            if not parts:
                continue
            dir_name = parts[0]

            try:
                raw = zf.read(name).decode("utf-8")
                data = json.loads(raw)
            except Exception as e:
                result["errors"].append(f"{name}: {e}")
                continue

            if dir_name in _DIR_TO_MEM_TYPE:
                if isinstance(data, dict) and "id" in data and "content" in data:
                    try:
                        mem = _parse_memory_from_json(data)
                        result["memories"].append(mem)
                    except Exception as e:
                        result["errors"].append(f"{name}: {e}")
            elif dir_name == "资产":
                if isinstance(data, list):
                    for item in data:
                        try:
                            asset = _parse_asset_from_json(item)
                            result["assets"].append(asset)
                        except Exception as e:
                            result["errors"].append(f"资产: {e}")
                elif isinstance(data, dict) and "id" in data:
                    try:
                        asset = _parse_asset_from_json(data)
                        result["assets"].append(asset)
                    except Exception as e:
                        result["errors"].append(f"资产: {e}")
            elif dir_name == "会话记录":
                result["session_count"] += 1

    return result


def do_import(bridge, memories: list, assets: list, parent: QWidget = None) -> dict:
    """执行导入，返回结果统计"""
    from PyQt5.QtWidgets import QProgressDialog, QApplication

    total = len(memories) + len(assets)
    stats = {"mem_new": 0, "mem_skipped": 0, "asset_new": 0, "asset_skipped": 0, "errors": []}

    if total == 0:
        return stats

    progress = QProgressDialog("导入中...", "取消", 0, total, parent)
    progress.setWindowTitle("导入数据")
    progress.setMinimumDuration(0)
    progress.show()
    QApplication.processEvents()

    for i, mem in enumerate(memories):
        if progress.wasCanceled():
            break
        progress.setValue(i)
        progress.setLabelText(f"导入记忆 ({i+1}/{len(memories)})")
        QApplication.processEvents()
        try:
            status = bridge.import_memory(mem)
            if status == "new":
                stats["mem_new"] += 1
            else:
                stats["mem_skipped"] += 1
        except Exception as e:
            stats["errors"].append(f"记忆 {mem.id[:12]}: {e}")

    offset = len(memories)
    for i, asset in enumerate(assets):
        if progress.wasCanceled():
            break
        progress.setValue(offset + i)
        progress.setLabelText(f"导入资产 ({i+1}/{len(assets)})")
        QApplication.processEvents()
        try:
            status = bridge.import_asset(asset)
            if status == "new":
                stats["asset_new"] += 1
            else:
                stats["asset_skipped"] += 1
        except Exception as e:
            stats["errors"].append(f"资产 {asset.name}: {e}")

    progress.close()
    return stats
