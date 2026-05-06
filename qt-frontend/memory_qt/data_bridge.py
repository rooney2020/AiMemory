"""数据层封装 — 桥接 ai_memory 模块到 Qt 界面"""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional

from ai_memory.config import Config, load_config, save_config
from ai_memory.core.memory import Memory
from ai_memory.core.types import AssetType, MemoryType
from ai_memory.storage.database import Database
from ai_memory.storage.memory_store import MemoryStore
from ai_memory.storage.entity_store import EntityStore
from ai_memory.asset.registry import AssetRegistry, Asset
from ai_memory.index.fts import FTSIndex
from ai_memory.index.graph import GraphIndex
from ai_memory.index.temporal import TemporalIndex
from ai_memory.index.fusion import FusionRetriever
from ai_memory.sync.github_device_flow import (
    GitHubDeviceFlowError,
    fetch_github_user,
    poll_device_flow,
    start_device_flow,
)
from ai_memory.sync.git_worktree_sync import run_sync_cycle as run_git_worktree_sync_cycle
from ai_memory.sync.github_sync import _evaluate_sync_path_rules, _iter_session_files, _parse_iso, run_sync_cycle


class DataBridge:
    """Qt 前端的数据访问接口"""

    def __init__(self, db_path: str | Path | None = None):
        self.config = load_config()
        actual_path = Path(db_path).expanduser() if db_path else self.config.db_path

        self.db = Database(actual_path)
        self.db.initialize()

        self.memory_store = MemoryStore(self.db)
        self.entity_store = EntityStore(self.db)
        self.asset_registry = AssetRegistry(self.db)

        self.fts = FTSIndex(self.db)
        self.graph = GraphIndex(self.db, self.entity_store)
        self.temporal = TemporalIndex(self.db)
        self.retriever = FusionRetriever(
            fts_index=self.fts,
            graph_index=self.graph,
            temporal_index=self.temporal,
            memory_store=self.memory_store,
            config=self.config,
        )

    def get_sync_config(self) -> dict:
        sync = self.config.sync
        return {
            "enabled": sync.enabled,
            "provider": sync.provider,
            "repo_owner": sync.repo_owner,
            "repo_name": sync.repo_name,
            "branch": sync.branch,
            "remote_url": sync.remote_url,
            "auth_mode": sync.auth_mode,
            "oauth_client_id": sync.oauth_client_id,
            "access_token": sync.access_token,
            "token_type": sync.token_type,
            "token_scope": sync.token_scope,
            "github_user": sync.github_user,
            "machine_id": sync.machine_id,
            "sync_mode": sync.sync_mode,
            "sync_interval_minutes": sync.sync_interval_minutes,
            "upload_sessions": sync.upload_sessions,
            "upload_assets": sync.upload_assets,
            "upload_sensitive_sessions": sync.upload_sensitive_sessions,
            "upload_size_limit_mb": sync.upload_size_limit_mb,
            "oversize_action": sync.oversize_action,
            "asset_size_scope": sync.asset_size_scope,
            "compress_upload": sync.compress_upload,
            "whitelist_first": sync.whitelist_first,
            "skip_blacklist_matches": sync.skip_blacklist_matches,
            "whitelist_patterns": list(sync.whitelist_patterns),
            "blacklist_patterns": list(sync.blacklist_patterns),
            "device_notes": dict(sync.device_notes),
            "worktree_path": sync.worktree_path,
            "last_sync_at": sync.last_sync_at,
            "last_synced_change_id": sync.last_synced_change_id,
        }

    def update_sync_config(self, **kwargs) -> dict:
        sync = self.config.sync
        for key, value in kwargs.items():
            if hasattr(sync, key):
                setattr(sync, key, value)
        save_config(self.config)
        return self.get_sync_config()

    def start_github_device_flow(self) -> dict:
        client_id = self.config.sync.oauth_client_id.strip()
        if not client_id:
            raise GitHubDeviceFlowError("请先填写 GitHub OAuth Client ID")
        flow = start_device_flow(client_id=client_id, scope=self.config.sync.token_scope)
        return {
            "device_code": flow.device_code,
            "user_code": flow.user_code,
            "verification_uri": flow.verification_uri,
            "expires_in": flow.expires_in,
            "interval": flow.interval,
        }

    def complete_github_device_flow(self, device_code: str) -> dict:
        client_id = self.config.sync.oauth_client_id.strip()
        if not client_id:
            raise GitHubDeviceFlowError("请先填写 GitHub OAuth Client ID")
        token = poll_device_flow(client_id=client_id, device_code=device_code)
        user = fetch_github_user(token.access_token)
        sync = self.update_sync_config(
            access_token=token.access_token,
            token_type=token.token_type,
            token_scope=token.scope,
            github_user=(user.get("login") or "").strip(),
        )
        sync["github_user"] = user.get("login") or ""
        return sync

    def logout_github(self) -> dict:
        return self.update_sync_config(
            access_token="",
            github_user="",
        )

    def run_sync_cycle(self, progress_callback=None, runtime_options: dict | None = None) -> dict:
        self.config._memory_store = self.memory_store  # type: ignore[attr-defined]
        self.config._asset_registry = self.asset_registry  # type: ignore[attr-defined]
        self.config._sync_runtime_options = runtime_options or {}  # type: ignore[attr-defined]
        if self.config.sync.provider == "git_worktree":
            result = run_git_worktree_sync_cycle(self.config, progress_callback=progress_callback)
        else:
            result = run_sync_cycle(self.config, progress_callback=progress_callback)
        self.config = load_config()
        return result

    def append_sync_history(self, content: str, result: str, event_type: str = "info", created_at: str | None = None) -> dict:
        entry = {
            "created_at": created_at or datetime.now().astimezone().isoformat(),
            "content": content.strip(),
            "result": result.strip(),
            "event_type": event_type.strip() or "info",
            "provider": self.config.sync.provider,
            "repo": f"{self.config.sync.repo_owner}/{self.config.sync.repo_name}".strip("/"),
            "machine_id": self.config.sync.machine_id,
        }
        history_path = self._sync_history_path()
        history_path.parent.mkdir(parents=True, exist_ok=True)
        with history_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def list_sync_history(self, limit: int = 12) -> list[dict]:
        records: list[dict] = []
        records.extend(self._read_local_sync_history(limit * 3))
        records.extend(self._read_git_sync_history(limit * 3))

        if not records and self.config.sync.last_sync_at:
            records.append({
                "created_at": self.config.sync.last_sync_at,
                "content": "最近一次同步已完成。",
                "result": "成功",
                "event_type": "success",
            })

        deduped: list[dict] = []
        seen_keys: set[tuple[str, str, str]] = set()
        for item in sorted(records, key=self._sync_history_sort_key, reverse=True):
            dedupe_key = (
                str(item.get("created_at") or ""),
                str(item.get("content") or ""),
                str(item.get("result") or ""),
            )
            if dedupe_key in seen_keys:
                continue
            seen_keys.add(dedupe_key)
            deduped.append({
                "created_at": str(item.get("created_at") or ""),
                "content": str(item.get("content") or "").strip() or "同步记录",
                "result": str(item.get("result") or "-").strip() or "-",
                "event_type": str(item.get("event_type") or "info"),
            })
            if len(deduped) >= limit:
                break
        return deduped

    def preview_sync_workload(self) -> dict:
        since = self._normalize_datetime(_parse_iso(self.config.sync.last_sync_at))
        memories_count = 0
        memories_bytes = 0
        for memory in self._iter_sync_memories(since):
            memories_count += 1
            memories_bytes += self._estimate_memory_sync_bytes(memory)

        sessions_count = 0
        sessions_bytes = 0
        if self.config.sync.upload_sessions:
            for session_file in _iter_session_files(since):
                rule_flags = _evaluate_sync_path_rules(self.config.sync, str(session_file))
                if rule_flags["blocked"]:
                    continue
                sessions_count += 1
                try:
                    sessions_bytes += session_file.stat().st_size
                except OSError:
                    continue

        assets_count = 0
        assets_bytes = 0
        if self.config.sync.upload_assets:
            for asset in self.asset_registry.lookup(valid_only=False):
                created_at = self._normalize_datetime(asset.created_at)
                if since and created_at and created_at <= since:
                    continue
                rule_flags = _evaluate_sync_path_rules(self.config.sync, asset.artifact_path)
                if rule_flags["blocked"]:
                    continue
                assets_count += 1
                assets_bytes += self._estimate_asset_bytes(asset)

        return {
            "first_sync": not bool(self.config.sync.last_sync_at),
            "last_sync_at": self.config.sync.last_sync_at,
            "memories": {
                "count": memories_count,
                "bytes": memories_bytes,
            },
            "sessions": {
                "count": sessions_count,
                "bytes": sessions_bytes,
            },
            "assets": {
                "count": assets_count,
                "bytes": assets_bytes,
            },
            "total_items": memories_count + sessions_count + assets_count,
            "total_bytes": memories_bytes + sessions_bytes + assets_bytes,
        }

    def preview_sync_entries(self, limit: int = 12) -> list[dict]:
        since = self._normalize_datetime(_parse_iso(self.config.sync.last_sync_at))
        entries: list[dict] = []

        for memory in self._iter_sync_memories(since):
            entries.append({
                "kind": "memory",
                "memory_type": memory.type.value,
                "name": (memory.summary or memory.id or "未命名记忆").strip(),
                "path": memory.project or memory.id,
                "size": self._estimate_memory_sync_bytes(memory),
            })
            if len(entries) >= limit:
                return entries

        if self.config.sync.upload_sessions:
            for session_file in _iter_session_files(since):
                rule_flags = _evaluate_sync_path_rules(self.config.sync, str(session_file))
                if rule_flags["blocked"]:
                    continue
                try:
                    size = session_file.stat().st_size
                except OSError:
                    size = 0
                entries.append({
                    "kind": "session",
                    "name": session_file.name,
                    "path": str(session_file),
                    "size": size,
                    "whitelisted": rule_flags["whitelisted"],
                    "blacklisted": rule_flags["blacklisted"],
                })
                if len(entries) >= limit:
                    return entries

        if self.config.sync.upload_assets:
            for asset in self.asset_registry.lookup(valid_only=False):
                created_at = self._normalize_datetime(asset.created_at)
                if since and created_at and created_at <= since:
                    continue
                rule_flags = _evaluate_sync_path_rules(self.config.sync, asset.artifact_path)
                if rule_flags["blocked"]:
                    continue
                entries.append({
                    "kind": "asset",
                    "name": asset.name,
                    "path": asset.artifact_path,
                    "size": self._estimate_asset_bytes(asset),
                    "whitelisted": rule_flags["whitelisted"],
                    "blacklisted": rule_flags["blacklisted"],
                })
                if len(entries) >= limit:
                    return entries

        return entries

    def mark_sync_baseline_now(self) -> dict:
        return self.update_sync_config(
            last_sync_at=datetime.now().astimezone().isoformat(),
            last_synced_change_id="",
        )

    def list_sync_devices(self) -> list[dict]:
        notes = dict(self.config.sync.device_notes or {})
        devices: dict[str, dict] = {}

        def touch(machine_id: str, source: str, last_seen: datetime | None = None, is_current: bool = False):
            if not machine_id:
                return
            entry = devices.setdefault(
                machine_id,
                {
                    "machine_id": machine_id,
                    "sources": [],
                    "last_seen": None,
                    "is_current": False,
                    "note": notes.get(machine_id, ""),
                },
            )
            if source and source not in entry["sources"]:
                entry["sources"].append(source)
            if last_seen and (entry["last_seen"] is None or last_seen > entry["last_seen"]):
                entry["last_seen"] = last_seen
            if is_current:
                entry["is_current"] = True
            entry["note"] = notes.get(machine_id, entry.get("note", ""))

        current_machine_id = (self.config.sync.machine_id or "").strip()
        touch(
            current_machine_id,
            "当前配置",
            self._normalize_datetime(_parse_iso(self.config.sync.last_sync_at)),
            is_current=True,
        )

        worktree = Path(self.config.sync.worktree_path).expanduser()
        if (worktree / ".git").exists():
            result = subprocess.run(
                ["git", "-C", str(worktree), "log", "--format=%s\t%cI", "-n", "300"],
                text=True,
                capture_output=True,
                check=False,
            )
            if result.returncode == 0:
                for line in result.stdout.splitlines():
                    subject, _, committed_at = line.partition("\t")
                    if not subject.startswith("sync(") or "):" not in subject:
                        continue
                    machine_id = subject[len("sync("):subject.index("):")].strip()
                    touch(
                        machine_id,
                        "git 工作区提交",
                        self._normalize_datetime(_parse_iso(committed_at)),
                        is_current=(machine_id == current_machine_id),
                    )

        synced_sessions_root = self.config.readable_path / "synced-sessions"
        if synced_sessions_root.exists():
            for framework_dir in synced_sessions_root.iterdir():
                if not framework_dir.is_dir():
                    continue
                for machine_dir in framework_dir.iterdir():
                    if not machine_dir.is_dir():
                        continue
                    last_seen = self._normalize_datetime(
                        datetime.fromtimestamp(machine_dir.stat().st_mtime).astimezone()
                    )
                    touch(
                        machine_dir.name,
                        f"同步会话缓存/{framework_dir.name}",
                        last_seen,
                        is_current=(machine_dir.name == current_machine_id),
                    )

        synced_asset_meta_root = self.config.readable_path / "synced-assets" / "meta"
        if synced_asset_meta_root.exists():
            for meta_file in synced_asset_meta_root.glob("*.json"):
                try:
                    payload = json.loads(meta_file.read_text(encoding="utf-8"))
                except (OSError, json.JSONDecodeError):
                    continue
                machine_id = str(payload.get("machine_id") or "").strip()
                if not machine_id:
                    continue
                last_seen = self._normalize_datetime(_parse_iso(payload.get("created_at")))
                if last_seen is None:
                    last_seen = self._normalize_datetime(datetime.fromtimestamp(meta_file.stat().st_mtime).astimezone())
                touch(
                    machine_id,
                    "同步资产缓存",
                    last_seen,
                    is_current=(machine_id == current_machine_id),
                )

        ordered = sorted(
            devices.values(),
            key=lambda item: (
                not item["is_current"],
                -(item["last_seen"].timestamp() if item["last_seen"] else 0),
                item["machine_id"],
            ),
        )
        for item in ordered:
            last_seen = item.get("last_seen")
            item["last_seen"] = last_seen.strftime("%Y-%m-%d %H:%M:%S") if last_seen else "-"
            item["source_summary"] = "、".join(item.get("sources") or []) or "未知来源"
        return ordered

    def update_sync_device_note(self, machine_id: str, note: str) -> dict:
        cleaned_machine_id = machine_id.strip()
        notes = dict(self.config.sync.device_notes or {})
        cleaned_note = note.strip()
        if cleaned_note:
            notes[cleaned_machine_id] = cleaned_note
        else:
            notes.pop(cleaned_machine_id, None)
        self.config.sync.device_notes = notes
        save_config(self.config)
        self.config = load_config()
        return {
            "machine_id": cleaned_machine_id,
            "note": self.config.sync.device_notes.get(cleaned_machine_id, ""),
        }

    def _sync_history_path(self) -> Path:
        return self.config.readable_path / "sync-history" / "events.jsonl"

    def _read_local_sync_history(self, limit: int) -> list[dict]:
        history_path = self._sync_history_path()
        if not history_path.exists():
            return []

        try:
            lines = history_path.read_text(encoding="utf-8").splitlines()
        except OSError:
            return []

        records: list[dict] = []
        for line in reversed(lines[-limit:]):
            line = line.strip()
            if not line:
                continue
            try:
                payload = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(payload, dict):
                continue
            records.append(payload)
        return records

    def _read_git_sync_history(self, limit: int) -> list[dict]:
        worktree = Path(self.config.sync.worktree_path).expanduser()
        if not (worktree / ".git").exists():
            return []

        result = subprocess.run(
            ["git", "-C", str(worktree), "log", "--format=%cI\t%s", "-n", str(max(limit, 1))],
            text=True,
            capture_output=True,
            check=False,
        )
        if result.returncode != 0:
            return []

        records: list[dict] = []
        for line in result.stdout.splitlines():
            created_at, _, subject = line.partition("\t")
            subject = subject.strip()
            if not subject.startswith("sync("):
                continue
            records.append({
                "created_at": created_at.strip(),
                "content": self._summarize_sync_commit_subject(subject),
                "result": "成功",
                "event_type": "success",
            })
        return records

    @staticmethod
    def _summarize_sync_commit_subject(subject: str) -> str:
        machine_match = re.match(r"sync\((?P<machine>[^)]+)\):\s*(?P<rest>.+)", subject)
        if not machine_match:
            return f"git 工作区同步完成：{subject}"

        machine_id = machine_match.group("machine").strip()
        rest = machine_match.group("rest").strip()
        count_match = re.match(r"(?P<memories>\d+) memories,\s*(?P<sessions>\d+) sessions,\s*(?P<assets>\d+) assets", rest)
        if count_match:
            return (
                f"{machine_id} 完成同步：记忆 {count_match.group('memories')} 条，"
                f"原始会话 {count_match.group('sessions')} 份，资产 {count_match.group('assets')} 项。"
            )
        return f"{machine_id} 完成同步：{rest}"

    @staticmethod
    def _sync_history_sort_key(item: dict) -> float:
        parsed = DataBridge._parse_datetime(str(item.get("created_at") or ""))
        if parsed is None:
            return 0.0
        normalized = DataBridge._normalize_datetime(parsed)
        if normalized is None:
            return 0.0
        return normalized.timestamp()

    def close(self):
        self.db.close()

    def _iter_sync_memories(self, since: datetime | None):
        rows = self.memory_store.db.execute("SELECT * FROM memories ORDER BY updated_at DESC").fetchall()
        for row in rows:
            memory = self.memory_store._row_to_memory(row)
            updated_at = self._normalize_datetime(memory.updated_at)
            if since and updated_at and updated_at <= since:
                continue
            yield memory

    @staticmethod
    def _estimate_memory_sync_bytes(memory: Memory) -> int:
        payload = {
            "id": memory.id,
            "type": memory.type.value,
            "summary": memory.summary,
            "content": memory.content,
            "project": memory.project,
            "session_id": memory.session_id,
            "entities": list(memory.entities or []),
            "tags": list(memory.tags or []),
        }
        return len(json.dumps(payload, ensure_ascii=False).encode("utf-8"))

    def _estimate_asset_bytes(self, asset: Asset) -> int:
        if asset.artifact_size and asset.artifact_size > 0:
            return int(asset.artifact_size)

        artifact_path = Path(asset.artifact_path)
        if not artifact_path.exists():
            return 0
        if artifact_path.is_file():
            try:
                return artifact_path.stat().st_size
            except OSError:
                return 0

        total_size = 0
        try:
            for child in artifact_path.rglob("*"):
                if child.is_file():
                    total_size += child.stat().st_size
        except OSError:
            return total_size
        return total_size

    @staticmethod
    def _normalize_datetime(value: datetime | None):
        if value is None:
            return None
        local_tz = datetime.now().astimezone().tzinfo
        if value.tzinfo is None:
            return value.replace(tzinfo=local_tz)
        return value.astimezone(local_tz)

    def get_stats(self) -> dict:
        return self.memory_store.get_stats()

    def list_memories(
        self,
        types: list[str] | None = None,
        project: str | None = None,
        min_strength: float | None = None,
        limit: int | None = None,
    ) -> list[Memory]:
        return self.memory_store.list_active(
            types=types, project=project,
            min_strength=min_strength, limit=limit,
        )

    def get_memory(self, memory_id: str) -> Memory | None:
        return self.memory_store.get(memory_id)

    def update_memory(self, memory_id: str, **kwargs):
        """更新记忆字段：content, summary, status ('archived') 等"""
        mem = self.memory_store.get(memory_id)
        if not mem:
            return
        if "content" in kwargs:
            mem.content = kwargs["content"]
        if "summary" in kwargs:
            mem.summary = kwargs["summary"]
        if "strength" in kwargs:
            mem.strength = max(0.0, min(10.0, kwargs["strength"]))
        if "entities" in kwargs:
            mem.entities = list(kwargs["entities"] or [])
        if kwargs.get("append_entities"):
            existing_entities = list(mem.entities) if mem.entities else []
            seen = {entity.casefold() for entity in existing_entities if isinstance(entity, str)}
            for entity in kwargs["append_entities"]:
                if not isinstance(entity, str):
                    continue
                name = entity.strip()
                if not name:
                    continue
                key = name.casefold()
                if key in seen:
                    continue
                seen.add(key)
                existing_entities.append(name)
            mem.entities = existing_entities
        if "status" in kwargs and kwargs["status"] == "archived":
            mem.archived = True
        self.memory_store.save(mem)

    def search(self, query: str, top_k: int = 10, project: str | None = None):
        return self.retriever.retrieve(query=query, top_k=top_k, project=project)

    def list_entities(self) -> list:
        return self.entity_store.list_all()

    def get_entity_names(self) -> list[str]:
        return self.entity_store.get_all_names()

    def get_related_memories(self, entity_name: str) -> list[str]:
        return self.entity_store.get_related_memories(entity_name)

    def get_entity_neighbors(self, entity_id: str, depth: int = 2) -> list[str]:
        return self.entity_store.get_entity_neighbors(entity_id, depth)

    def get_relations(self) -> list[dict]:
        rows = self.db.execute("""
            SELECT r.source_id, r.target_id, r.relation, r.weight,
                   e1.name as source_name, e2.name as target_name
            FROM relations r
            JOIN entities e1 ON e1.id = r.source_id
            JOIN entities e2 ON e2.id = r.target_id
        """).fetchall()
        return [dict(row) for row in rows]

    def list_assets(self, valid_only: bool = True) -> list[Asset]:
        assets = self.asset_registry.lookup(valid_only=valid_only)
        seen_ids = {asset.id for asset in assets}
        synced_root = self.config.readable_path / "synced-assets" / "meta"
        if not synced_root.exists():
            return assets

        for meta_file in sorted(synced_root.glob("*.json"), reverse=True):
            synced_asset = self._load_synced_asset(meta_file)
            if synced_asset is None:
                continue
            if valid_only and not synced_asset.valid:
                continue
            if synced_asset.id in seen_ids:
                continue
            assets.append(synced_asset)
            seen_ids.add(synced_asset.id)

        return assets

    def _load_synced_asset(self, meta_file: Path) -> Asset | None:
        try:
            payload = json.loads(meta_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None

        asset_type_raw = payload.get("type") or "data"
        try:
            asset_type = AssetType(asset_type_raw)
        except ValueError:
            asset_type = AssetType.DATA

        managed_blob_path = payload.get("managed_blob_path")
        local_blob = None
        if isinstance(managed_blob_path, str) and managed_blob_path:
            local_blob = self.config.readable_path / "synced-assets" / Path(managed_blob_path).name

        artifact_path = str(local_blob) if local_blob else str(meta_file)
        valid = bool(local_blob and local_blob.exists())
        invalid_reason = None if valid else "同步元数据已存在，本地 blob 尚未缓存"

        created_at = self._parse_datetime(payload.get("created_at")) or datetime.now()
        last_used_at = self._parse_datetime(payload.get("last_used_at"))

        asset = Asset(
            id=str(payload.get("id") or meta_file.stem),
            name=str(payload.get("name") or meta_file.stem),
            type=asset_type,
            description=payload.get("description"),
            artifact_path=artifact_path,
            source_hash=payload.get("source_hash"),
            source_path=payload.get("source_path"),
            artifact_size=payload.get("artifact_size"),
            tool_name=payload.get("tool_name"),
            tool_version=payload.get("tool_version"),
            tags=list(payload.get("tags") or []),
            project=payload.get("project"),
            session_id=payload.get("session_id"),
            created_at=created_at,
            last_used_at=last_used_at,
            use_count=int(payload.get("use_count") or 0),
            valid=valid,
            invalid_reason=invalid_reason,
        )
        asset.remote_synced = True
        asset.remote_machine_id = payload.get("machine_id") or "remote"
        asset.remote_meta_path = str(meta_file)
        return asset

    @staticmethod
    def _parse_datetime(value: str | None):
        if not value:
            return None
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None

    def validate_asset(self, asset_id: str) -> dict:
        return self.asset_registry.validate(asset_id)

    def validate_assets(self, asset_ids: list[str]) -> dict:
        summary = {
            "total": 0,
            "valid": 0,
            "invalid": 0,
            "results": [],
        }

        for asset_id in asset_ids:
            result = self.asset_registry.validate(asset_id)
            summary["total"] += 1
            if result.get("valid"):
                summary["valid"] += 1
            else:
                summary["invalid"] += 1
            summary["results"].append({"asset_id": asset_id, **result})

        return summary

    def delete_asset(self, asset_id: str):
        self.db.execute("DELETE FROM assets WHERE id = ?", (asset_id,))
        self.db.commit()

    def import_memory(self, mem) -> str:
        """导入记忆。返回 'new'/'skipped'"""
        existing = self.memory_store.get(mem.id)
        if existing:
            return "skipped"
        self.memory_store.save(mem)
        return "new"

    def import_asset(self, asset) -> str:
        """导入资产。返回 'new'/'skipped'"""
        existing = self.asset_registry.get(asset.id)
        if existing:
            return "skipped"
        self.asset_registry.register(asset)
        return "new"

    def batch_archive(self, memory_ids: list[str]):
        for mid in memory_ids:
            mem = self.memory_store.get(mid)
            if mem:
                mem.archived = True
                self.memory_store.save(mem)

    def batch_add_tag(self, memory_ids: list[str], tag: str):
        for mid in memory_ids:
            mem = self.memory_store.get(mid)
            if mem:
                tags = set(mem.tags) if mem.tags else set()
                tags.add(tag)
                mem.tags = list(tags)
                self.memory_store.save(mem)

    def add_entity(self, name: str, entity_type: str = "technology"):
        return self.entity_store.get_or_create(name, entity_type)

    def add_relation(self, source_id: str, target_id: str, relation: str, weight: float = 1.0):
        return self.entity_store.add_relation(source_id, target_id, relation, weight)

    def delete_entity(self, entity_id: str):
        self.db.execute("DELETE FROM memory_entities WHERE entity_id = ?", (entity_id,))
        self.db.execute("DELETE FROM relations WHERE source_id = ? OR target_id = ?", (entity_id, entity_id))
        self.db.execute("DELETE FROM entities WHERE id = ?", (entity_id,))
        self.db.commit()

    def delete_relation(self, source_id: str, target_id: str, relation: str):
        self.db.execute(
            "DELETE FROM relations WHERE source_id = ? AND target_id = ? AND relation = ?",
            (source_id, target_id, relation),
        )
        self.db.commit()

    def get_projects(self) -> list[str]:
        rows = self.db.execute(
            "SELECT DISTINCT project FROM memories WHERE project IS NOT NULL AND archived=0"
        ).fetchall()
        return [row["project"] for row in rows]
