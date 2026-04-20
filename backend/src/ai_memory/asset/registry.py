from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Optional
import uuid

from ..core.types import AssetType
from ..storage.database import Database


@dataclass
class Asset:
    name: str
    type: AssetType
    artifact_path: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    description: Optional[str] = None

    source_hash: Optional[str] = None
    source_path: Optional[str] = None

    artifact_size: Optional[int] = None
    tool_name: Optional[str] = None
    tool_version: Optional[str] = None

    tags: list[str] = field(default_factory=list)
    project: Optional[str] = None
    session_id: Optional[str] = None

    created_at: datetime = field(default_factory=datetime.now)
    last_used_at: Optional[datetime] = None
    use_count: int = 0
    valid: bool = True
    invalid_reason: Optional[str] = None


class AssetRegistry:
    def __init__(self, db: Database):
        self.db = db

    def register(self, asset: Asset) -> Asset:
        if asset.source_path and not asset.source_hash:
            asset.source_hash = self.compute_hash(asset.source_path)

        if asset.artifact_path:
            path = Path(asset.artifact_path)
            if path.is_file():
                asset.artifact_size = path.stat().st_size
            elif path.is_dir():
                try:
                    asset.artifact_size = sum(
                        f.stat().st_size for f in path.rglob("*") if f.is_file()
                    )
                except OSError:
                    pass

        tags_json = json.dumps(asset.tags, ensure_ascii=False) if asset.tags else "[]"

        self.db.execute("""
            INSERT INTO assets (
                id, type, name, description,
                source_hash, source_path,
                artifact_path, artifact_size, tool_name, tool_version,
                tags, project, session_id,
                created_at, last_used_at, use_count, valid, invalid_reason
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            asset.id, asset.type.value, asset.name, asset.description,
            asset.source_hash, asset.source_path,
            asset.artifact_path, asset.artifact_size,
            asset.tool_name, asset.tool_version,
            tags_json, asset.project, asset.session_id,
            asset.created_at.isoformat(), None, 0, 1, None,
        ))
        self.db.commit()
        return asset

    def get(self, asset_id: str) -> Optional[Asset]:
        row = self.db.execute(
            "SELECT * FROM assets WHERE id = ?", (asset_id,)
        ).fetchone()
        return self._row_to_asset(row) if row else None

    def lookup(
        self,
        query: Optional[str] = None,
        source_hash: Optional[str] = None,
        asset_type: Optional[str] = None,
        tags: Optional[list[str]] = None,
        project: Optional[str] = None,
        valid_only: bool = True,
    ) -> list[Asset]:
        conditions: list[str] = []
        params: list = []

        if valid_only:
            conditions.append("valid = 1")

        if source_hash:
            conditions.append("source_hash = ?")
            params.append(source_hash)

        if asset_type:
            conditions.append("type = ?")
            params.append(asset_type)

        if project:
            conditions.append("project = ?")
            params.append(project)

        if query:
            conditions.append("(name LIKE ? OR description LIKE ?)")
            params.extend([f"%{query}%", f"%{query}%"])

        if tags:
            for tag in tags:
                conditions.append("tags LIKE ?")
                params.append(f'%"{tag}"%')

        where = " AND ".join(conditions) if conditions else "1=1"
        sql = f"SELECT * FROM assets WHERE {where} ORDER BY last_used_at DESC NULLS LAST"

        rows = self.db.execute(sql, tuple(params)).fetchall()
        return [self._row_to_asset(row) for row in rows]

    def validate(self, asset_id: str) -> dict:
        asset = self.get(asset_id)
        if not asset:
            return {"valid": False, "reason": "资产不存在", "checks": []}

        result: dict = {"valid": True, "checks": []}

        path = Path(asset.artifact_path)
        path_exists = path.exists()
        result["checks"].append({"check": "path_exists", "passed": path_exists})
        if not path_exists:
            result["valid"] = False
            self._mark_invalid(asset_id, "产物路径不存在")
            return result

        if asset.source_path and asset.source_hash:
            current_hash = self.compute_hash(asset.source_path)
            hash_match = current_hash == asset.source_hash
            result["checks"].append({"check": "source_hash_match", "passed": hash_match})
            if not hash_match:
                result["valid"] = False
                self._mark_invalid(asset_id, "源文件已变更")
                return result

        return result

    def use(self, asset_id: str):
        self.db.execute("""
            UPDATE assets
            SET use_count = use_count + 1, last_used_at = ?
            WHERE id = ?
        """, (datetime.now().isoformat(), asset_id))
        self.db.commit()

    def invalidate(self, asset_id: str, reason: Optional[str] = None):
        self._mark_invalid(asset_id, reason)

    def _mark_invalid(self, asset_id: str, reason: Optional[str] = None):
        self.db.execute(
            "UPDATE assets SET valid = 0, invalid_reason = ? WHERE id = ?",
            (reason, asset_id),
        )
        self.db.commit()

    @staticmethod
    def compute_hash(file_path: str) -> Optional[str]:
        path = Path(file_path)
        if not path.exists() or not path.is_file():
            return None
        sha256 = hashlib.sha256()
        with open(path, "rb") as f:
            for chunk in iter(lambda: f.read(8192), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    @staticmethod
    def _row_to_asset(row) -> Asset:
        tags = json.loads(row["tags"]) if row["tags"] else []
        last_used = (
            datetime.fromisoformat(row["last_used_at"])
            if row["last_used_at"]
            else None
        )
        return Asset(
            id=row["id"],
            type=AssetType(row["type"]),
            name=row["name"],
            description=row["description"],
            source_hash=row["source_hash"],
            source_path=row["source_path"],
            artifact_path=row["artifact_path"],
            artifact_size=row["artifact_size"],
            tool_name=row["tool_name"],
            tool_version=row["tool_version"],
            tags=tags,
            project=row["project"],
            session_id=row["session_id"],
            created_at=datetime.fromisoformat(row["created_at"]),
            last_used_at=last_used,
            use_count=row["use_count"],
            valid=bool(row["valid"]),
            invalid_reason=row["invalid_reason"],
        )
