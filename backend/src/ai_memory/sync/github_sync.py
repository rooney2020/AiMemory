from __future__ import annotations

import base64
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
import fnmatch
import hashlib
import json
from pathlib import Path
import tempfile
from typing import Any, Callable
from urllib import error, parse, request
import uuid
import zipfile

from ai_memory.config import Config, save_config
from ai_memory.core.memory import Memory
from ai_memory.core.types import AssetType, MemoryType


_EMPTY_TREE_SHA = "4b825dc642cb6eb9a060e54bf8d69288fbee4904"
_LOCAL_TIMEZONE = datetime.now().astimezone().tzinfo or timezone.utc
_MAX_SYNC_FILE_BYTES = 90 * 1024 * 1024


class GitHubSyncError(RuntimeError):
    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code


@dataclass
class SyncRunResult:
    ok: bool
    mode: str
    repo: str
    branch: str
    phases: list[str]
    pulled_changes: int = 0
    applied_changes: int = 0
    pushed_changes: int = 0
    message: str = ""
    synced_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_sync_cycle(config: Config, progress_callback: Callable[[str], None] | None = None) -> dict[str, Any]:
    sync = config.sync
    _emit_progress(progress_callback, "正在检查同步配置...")
    _ensure_sync_ready(sync.enabled, sync.repo_owner, sync.repo_name, sync.access_token)

    repo = f"{sync.repo_owner}/{sync.repo_name}"
    phases = ["preflight"]
    _emit_progress(progress_callback, f"正在连接 GitHub 仓库 {repo}/{sync.branch}...")
    repo_payload = _github_get_json(f"https://api.github.com/repos/{repo}", sync.access_token)
    try:
        branch_payload = _github_get_json(f"https://api.github.com/repos/{repo}/branches/{sync.branch}", sync.access_token)
    except GitHubSyncError as exc:
        if exc.status_code == 404 and _repo_needs_bootstrap(repo_payload):
            phases.append("bootstrap")
            _github_bootstrap_empty_branch(repo, sync.branch, sync.access_token)
            branch_payload = _github_get_json(f"https://api.github.com/repos/{repo}/branches/{sync.branch}", sync.access_token)
        else:
            raise
    tree_items = _github_list_tree(repo, sync.branch, sync.access_token, branch_payload)

    phases.append("pull")
    last_sync_at = _parse_iso(sync.last_sync_at)
    pulled_changes = 0
    applied_changes = 0
    remote_changes = _pull_remote_changes(
        config=config,
        repo=repo,
        branch=sync.branch,
        access_token=sync.access_token,
        tree_items=tree_items,
        since=last_sync_at,
        progress_callback=progress_callback,
    )
    pulled_changes = len(remote_changes)

    phases.append("apply")
    applied_changes = _apply_remote_changes(config, remote_changes, progress_callback=progress_callback)

    if sync.sync_mode != "pull_only":
        phases.append("push")
        _emit_progress(progress_callback, "正在准备本地变更并上传到 GitHub...")
        pushed_changes, skipped_large_files = _push_local_objects(
            config=config,
            repo=repo,
            branch=sync.branch,
            access_token=sync.access_token,
            since=last_sync_at,
            progress_callback=progress_callback,
        )
    else:
        pushed_changes = 0
        skipped_large_files = []

    synced_at = datetime.now(timezone.utc).isoformat()
    sync.last_sync_at = synced_at
    if remote_changes:
        sync.last_synced_change_id = remote_changes[-1]["change_id"]
    save_config(config)

    message = "同步已完成：changes 已真实 pull/push，sessions 与 assets 已支持上传并缓存到本地同步目录。"
    if skipped_large_files:
        preview = "、".join(skipped_large_files[:3])
        if len(skipped_large_files) > 3:
            preview = f"{preview} 等 {len(skipped_large_files)} 个文件"
        message = f"同步已完成，但已跳过超大文件：{preview}。请改用外链、拆分资产或关闭资产上传后再补传。"

    result = SyncRunResult(
        ok=True,
        mode=sync.sync_mode,
        repo=repo,
        branch=sync.branch,
        phases=phases,
        pulled_changes=pulled_changes,
        applied_changes=applied_changes,
        pushed_changes=pushed_changes,
        message=message,
        synced_at=synced_at,
    )
    _emit_progress(progress_callback, f"同步完成：拉取 {pulled_changes} 项，应用 {applied_changes} 项，推送 {pushed_changes} 项。")
    return result.to_dict()


def _emit_progress(progress_callback: Callable[[str], None] | None, message: str):
    if progress_callback is not None:
        progress_callback(message)


def _sync_path_candidates(path: str) -> list[str]:
    normalized = path.replace("\\", "/")
    candidates = {normalized, Path(normalized).name}
    parts = [part for part in normalized.split("/") if part]
    if parts:
        candidates.add("/".join(parts[-2:]))
    return [candidate for candidate in candidates if candidate]


def _matches_sync_patterns(path: str, patterns: list[str] | None) -> bool:
    if not patterns:
        return False
    candidates = _sync_path_candidates(path)
    for pattern in patterns:
        cleaned = (pattern or "").strip()
        if not cleaned:
            continue
        normalized_pattern = cleaned.replace("\\", "/")
        for candidate in candidates:
            if fnmatch.fnmatch(candidate, normalized_pattern):
                return True
    return False


def _evaluate_sync_path_rules(sync, path: str) -> dict[str, bool]:
    whitelisted = _matches_sync_patterns(path, list(getattr(sync, "whitelist_patterns", []) or []))
    blacklisted = _matches_sync_patterns(path, list(getattr(sync, "blacklist_patterns", []) or []))
    blocked = False
    if blacklisted and bool(getattr(sync, "skip_blacklist_matches", True)):
        blocked = not (whitelisted and bool(getattr(sync, "whitelist_first", False)))
    return {
        "whitelisted": whitelisted,
        "blacklisted": blacklisted,
        "blocked": blocked,
    }


def _should_report_progress(index: int, total: int, step: int) -> bool:
    return index == 1 or index == total or index % step == 0


def _ensure_sync_ready(enabled: bool, repo_owner: str, repo_name: str, access_token: str):
    if not enabled:
        raise GitHubSyncError("同步总开关未启用")
    if not repo_owner or not repo_name:
        raise GitHubSyncError("请先配置 GitHub 仓库所有者和仓库名称")
    if not access_token:
        raise GitHubSyncError("请先完成 GitHub 登录")


def _github_get_json(url: str, access_token: str) -> dict[str, Any]:
    req = request.Request(
        url,
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "ai-memory-qt",
        },
        method="GET",
    )
    try:
        with request.urlopen(req, timeout=20) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GitHubSyncError(detail or f"GitHub API 请求失败: HTTP {exc.code}", status_code=exc.code) from exc
    except error.URLError as exc:
        raise GitHubSyncError(f"无法连接 GitHub: {exc.reason}") from exc


def _github_request_json(url: str, access_token: str, method: str, payload: dict[str, Any]) -> dict[str, Any]:
    req = request.Request(
        url,
        data=json.dumps(payload).encode("utf-8"),
        headers={
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {access_token}",
            "User-Agent": "ai-memory-qt",
            "Content-Type": "application/json",
        },
        method=method,
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="ignore")
        raise GitHubSyncError(detail or f"GitHub API 请求失败: HTTP {exc.code}", status_code=exc.code) from exc
    except error.URLError as exc:
        raise GitHubSyncError(f"无法连接 GitHub: {exc.reason}") from exc


def _github_list_tree(repo: str, branch: str, access_token: str, branch_payload: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    branch_payload = branch_payload or _github_get_json(f"https://api.github.com/repos/{repo}/branches/{branch}", access_token)
    tree_sha = branch_payload.get("commit", {}).get("commit", {}).get("tree", {}).get("sha")
    if not tree_sha or tree_sha == _EMPTY_TREE_SHA:
        return []
    try:
        tree_payload = _github_get_json(f"https://api.github.com/repos/{repo}/git/trees/{tree_sha}?recursive=1", access_token)
    except GitHubSyncError as exc:
        if exc.status_code == 404 and tree_sha == _EMPTY_TREE_SHA:
            return []
        raise
    tree = tree_payload.get("tree")
    return tree if isinstance(tree, list) else []


def _github_get_file(repo: str, path: str, access_token: str, ref: str | None = None) -> dict[str, Any]:
    encoded_path = parse.quote(path, safe="/")
    url = f"https://api.github.com/repos/{repo}/contents/{encoded_path}"
    if ref:
        url += f"?ref={parse.quote(ref)}"
    return _github_get_json(url, access_token)


def _github_put_file(repo: str, branch: str, path: str, content: bytes, access_token: str, message: str):
    url = f"https://api.github.com/repos/{repo}/contents/{parse.quote(path, safe='/')}"
    payload: dict[str, Any] = {
        "message": message,
        "content": base64.b64encode(content).decode("ascii"),
        "branch": branch,
    }
    try:
        existing = _github_get_file(repo, path, access_token, ref=branch)
        if existing.get("sha"):
            payload["sha"] = existing["sha"]
    except GitHubSyncError as exc:
        if exc.status_code != 404:
            raise
    _github_request_json(url, access_token, "PUT", payload)


def _serialize_memory(memory: Memory) -> dict[str, Any]:
    return {
        "id": memory.id,
        "type": memory.type.value,
        "content": memory.content,
        "summary": memory.summary,
        "project": memory.project,
        "session_id": memory.session_id,
        "entities": list(memory.entities or []),
        "tags": list(memory.tags or []),
        "strength": memory.strength,
        "access_count": memory.access_count,
        "last_accessed": memory.last_accessed.isoformat() if memory.last_accessed else None,
        "decay_rate": memory.decay_rate,
        "created_at": memory.created_at.isoformat(),
        "updated_at": memory.updated_at.isoformat(),
        "archived": memory.archived,
    }


def _deserialize_memory(payload: dict[str, Any]) -> Memory:
    return Memory(
        id=payload["id"],
        type=MemoryType(payload["type"]),
        content=payload["content"],
        summary=payload.get("summary"),
        project=payload.get("project"),
        session_id=payload.get("session_id"),
        entities=list(payload.get("entities") or []),
        tags=list(payload.get("tags") or []),
        strength=float(payload.get("strength", 1.0)),
        access_count=int(payload.get("access_count", 0)),
        last_accessed=_parse_iso(payload.get("last_accessed")),
        decay_rate=float(payload.get("decay_rate", 0.1)),
        created_at=_parse_iso(payload.get("created_at")) or datetime.now(),
        updated_at=_parse_iso(payload.get("updated_at")) or datetime.now(),
        archived=bool(payload.get("archived", False)),
    )


def _serialize_asset(asset) -> dict[str, Any]:
    return {
        "id": asset.id,
        "name": asset.name,
        "type": asset.type.value,
        "description": asset.description,
        "artifact_path": asset.artifact_path,
        "source_hash": asset.source_hash,
        "source_path": asset.source_path,
        "artifact_size": asset.artifact_size,
        "tool_name": asset.tool_name,
        "tool_version": asset.tool_version,
        "tags": list(asset.tags or []),
        "project": asset.project,
        "session_id": asset.session_id,
        "created_at": asset.created_at.isoformat(),
        "last_used_at": asset.last_used_at.isoformat() if asset.last_used_at else None,
        "use_count": asset.use_count,
        "valid": asset.valid,
        "invalid_reason": asset.invalid_reason,
    }


def _change_path(change: dict[str, Any]) -> str:
    timestamp = _parse_iso(change["timestamp"]) or datetime.now(timezone.utc)
    return f"changes/{timestamp:%Y}/{timestamp:%m}/{change['change_id']}.json"


def _object_path(change: dict[str, Any]) -> str:
    object_type = change["object_type"]
    object_id = change["object_id"]
    if object_type == "memory":
        return f"objects/memories/{object_id}.json"
    if object_type == "asset":
        return f"assets/meta/{object_id}.json"
    raise GitHubSyncError(f"未知对象类型: {object_type}")


def _build_memory_change(memory: Memory, machine_id: str) -> dict[str, Any]:
    payload = _serialize_memory(memory)
    timestamp = payload["updated_at"]
    return {
        "change_id": str(uuid.uuid4()),
        "machine_id": machine_id,
        "object_type": "memory",
        "object_id": memory.id,
        "op": "upsert",
        "timestamp": timestamp,
        "payload": payload,
    }


def _build_asset_change(asset, machine_id: str, blob_path: str | None = None) -> dict[str, Any]:
    payload = _serialize_asset(asset)
    payload["machine_id"] = machine_id
    if blob_path:
        payload["managed_blob_path"] = blob_path
    return {
        "change_id": str(uuid.uuid4()),
        "machine_id": machine_id,
        "object_type": "asset",
        "object_id": asset.id,
        "op": "upsert",
        "timestamp": payload["created_at"],
        "payload": payload,
    }


def _build_session_change(session_file: Path, machine_id: str) -> dict[str, Any]:
    stat = session_file.stat()
    timestamp = datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat()
    sha256 = _hash_bytes(session_file.read_bytes())
    framework = _detect_session_framework(session_file)
    source_key = _hash_bytes(str(session_file).encode("utf-8"))[:16]
    stored_name = f"{source_key}-{session_file.name}"
    remote_path = f"sessions/{framework}/{machine_id}/{stored_name}"
    return {
        "change_id": str(uuid.uuid4()),
        "machine_id": machine_id,
        "object_type": "session",
        "object_id": f"{framework}:{source_key}",
        "op": "upsert",
        "timestamp": timestamp,
        "payload": {
            "framework": framework,
            "machine_id": machine_id,
            "file_name": stored_name,
            "source_key": source_key,
            "original_file_name": session_file.name,
            "local_path": str(session_file),
            "sha256": sha256,
            "size": stat.st_size,
            "remote_path": remote_path,
            "captured_at": timestamp,
        },
    }


def _pull_remote_changes(
    config: Config,
    repo: str,
    branch: str,
    access_token: str,
    tree_items: list[dict[str, Any]],
    since: datetime | None,
    progress_callback: Callable[[str], None] | None = None,
) -> list[dict[str, Any]]:
    change_paths = sorted(
        item["path"]
        for item in tree_items
        if item.get("type") == "blob" and isinstance(item.get("path"), str) and item["path"].startswith("changes/") and item["path"].endswith(".json")
    )
    remote_changes: list[dict[str, Any]] = []
    total_paths = len(change_paths)
    if total_paths:
        _emit_progress(progress_callback, f"正在拉取远端变更 0/{total_paths}...")
    else:
        _emit_progress(progress_callback, "远端没有需要拉取的 changes。")
    for index, path in enumerate(change_paths, start=1):
        if _should_report_progress(index, total_paths, 10):
            _emit_progress(progress_callback, f"正在拉取远端变更 {index}/{total_paths}...")
        payload = _github_get_file(repo, path, access_token, ref=branch)
        content = payload.get("content")
        if not isinstance(content, str):
            continue
        decoded = base64.b64decode(content.encode("ascii")).decode("utf-8")
        change = json.loads(decoded)
        if change.get("machine_id") == config.sync.machine_id:
            continue
        timestamp = _parse_iso(change.get("timestamp"))
        if since and timestamp and timestamp <= since:
            continue
        remote_changes.append(change)
    remote_changes.sort(key=lambda item: item.get("timestamp") or "")
    return remote_changes


def _apply_remote_changes(
    config: Config,
    changes: list[dict[str, Any]],
    progress_callback: Callable[[str], None] | None = None,
) -> int:
    applied = 0
    total_changes = len(changes)
    if total_changes:
        _emit_progress(progress_callback, f"正在应用远端变更 0/{total_changes}...")
    for index, change in enumerate(changes, start=1):
        if total_changes and _should_report_progress(index, total_changes, 10):
            _emit_progress(progress_callback, f"正在应用远端变更 {index}/{total_changes}...")
        object_type = change.get("object_type")
        payload = change.get("payload") or {}
        if object_type == "memory":
            memory = _deserialize_memory(payload)
            config._memory_store.save(memory, preserve_timestamps=True)  # type: ignore[attr-defined]
            applied += 1
            continue
        if object_type == "session":
            _cache_remote_session(config, payload)
            applied += 1
            continue
        if object_type == "asset":
            _cache_remote_asset(config, payload)
            applied += 1
            continue
    return applied


def _push_local_objects(
    config: Config,
    repo: str,
    branch: str,
    access_token: str,
    since: datetime | None,
    progress_callback: Callable[[str], None] | None = None,
) -> tuple[int, list[str]]:
    pushed = 0
    pending_files: dict[str, bytes] = {}
    skipped_large_files: list[str] = []
    runtime_options = getattr(config, "_sync_runtime_options", {}) or {}
    skip_paths = {str(path) for path in runtime_options.get("skip_paths") or []}
    force_upload_paths = {str(path) for path in runtime_options.get("force_upload_paths") or []}
    limit_bytes = max(0, int(config.sync.upload_size_limit_mb or 0)) * 1024 * 1024
    oversize_action = (config.sync.oversize_action or "prompt").strip()

    def _skip_for_custom_limit(entry_path: str, entry_name: str, size_bytes: int) -> bool:
        rule_flags = _evaluate_sync_path_rules(config.sync, entry_path)
        if rule_flags["whitelisted"]:
            return False
        if limit_bytes <= 0 or size_bytes <= limit_bytes:
            return False
        if entry_path in force_upload_paths:
            return False
        if entry_path in skip_paths or oversize_action == "skip":
            _emit_progress(
                progress_callback,
                f"跳过超限内容 {entry_name}（{_format_bytes(size_bytes)}，限制 {_format_bytes(limit_bytes)}）。",
            )
            return True
        if oversize_action == "prompt":
            _emit_progress(
                progress_callback,
                f"跳过待确认的超限内容 {entry_name}（{_format_bytes(size_bytes)}，限制 {_format_bytes(limit_bytes)}）。",
            )
            return True
        return False

    memories = list(_iter_local_memories(config, since))
    total_memories = len(memories)
    if total_memories:
        _emit_progress(progress_callback, f"正在整理记忆变更 0/{total_memories}...")
    for index, memory in enumerate(memories, start=1):
        if total_memories and _should_report_progress(index, total_memories, 25):
            _emit_progress(progress_callback, f"正在整理记忆变更 {index}/{total_memories}...")
        change = _build_memory_change(memory, config.sync.machine_id)
        pending_files[_object_path(change)] = _json_bytes(change["payload"])
        pending_files[_change_path(change)] = _json_bytes(change)
        pushed += 1

    if config.sync.upload_sessions:
        session_files = list(_iter_session_files(since))
        total_sessions = len(session_files)
        if total_sessions:
            _emit_progress(progress_callback, f"正在整理原始会话 0/{total_sessions}...")
        for index, session_file in enumerate(session_files, start=1):
            if total_sessions and _should_report_progress(index, total_sessions, 5):
                _emit_progress(progress_callback, f"正在整理原始会话 {index}/{total_sessions}: {session_file.name}")
            rule_flags = _evaluate_sync_path_rules(config.sync, str(session_file))
            if rule_flags["blocked"]:
                _emit_progress(progress_callback, f"跳过命中黑名单的原始会话 {session_file.name}。")
                continue
            session_size = session_file.stat().st_size
            if _skip_for_custom_limit(str(session_file), session_file.name, session_size):
                continue
            if session_size > _MAX_SYNC_FILE_BYTES:
                skipped_large_files.append(f"会话 {session_file.name}")
                _emit_progress(
                    progress_callback,
                    f"跳过超大原始会话 {session_file.name}（{_format_bytes(session_size)}），避免 GitHub 上传超时。",
                )
                continue
            change = _build_session_change(session_file, config.sync.machine_id)
            pending_files[change["payload"]["remote_path"]] = session_file.read_bytes()
            pending_files[_change_path(change)] = _json_bytes(change)
            pushed += 1

    if config.sync.upload_assets:
        since_normalized = _normalize_datetime(since)
        asset_candidates = []
        for asset in config._asset_registry.lookup(valid_only=False):  # type: ignore[attr-defined]
            created_at = _normalize_datetime(asset.created_at)
            if since_normalized and created_at and created_at <= since_normalized:
                continue
            asset_candidates.append(asset)

        total_assets = len(asset_candidates)
        if total_assets:
            _emit_progress(progress_callback, f"正在整理托管资产 0/{total_assets}...")
        for index, asset in enumerate(asset_candidates, start=1):
            if total_assets and _should_report_progress(index, total_assets, 2):
                _emit_progress(progress_callback, f"正在整理托管资产 {index}/{total_assets}: {asset.name}")
            rule_flags = _evaluate_sync_path_rules(config.sync, asset.artifact_path)
            if rule_flags["blocked"]:
                _emit_progress(progress_callback, f"跳过命中黑名单的托管资产 {asset.name}。")
                continue
            estimated_size = _estimate_asset_sync_size(asset)
            if _skip_for_custom_limit(asset.artifact_path, asset.name, estimated_size):
                continue
            if estimated_size > _MAX_SYNC_FILE_BYTES:
                skipped_large_files.append(f"资产 {asset.name}")
                _emit_progress(
                    progress_callback,
                    f"跳过超大托管资产 {asset.name}（约 {_format_bytes(estimated_size)}），避免 GitHub 上传超时。",
                )
                continue
            managed_blob_path, managed_blob_bytes = _materialize_asset_blob(config, asset)
            if managed_blob_bytes is not None and len(managed_blob_bytes) > _MAX_SYNC_FILE_BYTES:
                skipped_large_files.append(f"资产 {asset.name}")
                _emit_progress(
                    progress_callback,
                    f"跳过超大托管资产 {asset.name}（实际包体 {_format_bytes(len(managed_blob_bytes))}），避免 GitHub 上传超时。",
                )
                continue
            change = _build_asset_change(asset, config.sync.machine_id, managed_blob_path)
            if managed_blob_path and managed_blob_bytes is not None:
                pending_files[managed_blob_path] = managed_blob_bytes
            pending_files[_object_path(change)] = _json_bytes(change["payload"])
            pending_files[_change_path(change)] = _json_bytes(change)
            pushed += 1

    if pending_files:
        _emit_progress(progress_callback, f"正在向 GitHub 提交 {len(pending_files)} 个文件...")
        _github_commit_files(
            repo=repo,
            branch=branch,
            access_token=access_token,
            files=pending_files,
            message=f"sync: push {len(pending_files)} files",
            progress_callback=progress_callback,
        )
    else:
        _emit_progress(progress_callback, "本地没有需要推送的新变更。")

    return pushed, skipped_large_files


def _iter_local_memories(config: Config, since: datetime | None):
    rows = config._memory_store.db.execute("SELECT * FROM memories").fetchall()  # type: ignore[attr-defined]
    since_normalized = _normalize_datetime(since)
    for row in rows:
        memory = config._memory_store._row_to_memory(row)  # type: ignore[attr-defined]
        updated_at = _normalize_datetime(memory.updated_at)
        if since_normalized and updated_at and updated_at <= since_normalized:
            continue
        yield memory


def _iter_local_assets(config: Config, since: datetime | None):
    since_normalized = _normalize_datetime(since)
    for asset in config._asset_registry.lookup(valid_only=False):  # type: ignore[attr-defined]
        created_at = _normalize_datetime(asset.created_at)
        if since_normalized and created_at and created_at <= since_normalized:
            continue
        managed_path, managed_bytes = _materialize_asset_blob(config, asset)
        yield asset, managed_path, managed_bytes


def _iter_session_files(since: datetime | None):
    search_specs = [
        (
            Path.home() / ".config" / "Code" / "User" / "workspaceStorage",
            ["**/chatSessions/*.jsonl", "**/transcripts/*.jsonl"],
        ),
        (
            Path.home() / ".cursor" / "projects",
            ["**/agent-transcripts/*.jsonl", "**/agent-transcripts/*.txt"],
        ),
        (
            Path.home() / ".openclaw" / "agents",
            ["**/sessions/*.jsonl"],
        ),
        (
            Path.home() / ".config" / "Code" / "User" / "globalStorage" / "thundersoft.toder" / "tasks",
            ["**/*.json"],
        ),
    ]
    seen: set[Path] = set()
    for root, patterns in search_specs:
        if not root.exists():
            continue
        for pattern in patterns:
            for file_path in root.glob(pattern):
                if file_path in seen or not file_path.is_file():
                    continue
                seen.add(file_path)
                if since and datetime.fromtimestamp(file_path.stat().st_mtime, tz=timezone.utc) <= since:
                    continue
                yield file_path


def _materialize_asset_blob(config: Config, asset) -> tuple[str | None, bytes | None]:
    artifact_path = Path(asset.artifact_path)
    if not artifact_path.exists():
        return None, None
    managed_root = config.readable_path / "sync-assets"
    managed_root.mkdir(parents=True, exist_ok=True)

    if artifact_path.is_file():
        blob_bytes = artifact_path.read_bytes()
        suffix = artifact_path.suffix or ".bin"
        blob_name = asset.source_hash or _hash_bytes(blob_bytes)
        managed_path = f"assets/blobs/{blob_name}{suffix}"
        local_blob = managed_root / f"{blob_name}{suffix}"
        local_blob.write_bytes(blob_bytes)
        return managed_path, blob_bytes

    archive_name = f"{asset.id}.zip"
    local_archive = managed_root / archive_name
    if local_archive.exists():
        latest_source_mtime = max(
            (child.stat().st_mtime for child in artifact_path.rglob("*") if child.is_file()),
            default=artifact_path.stat().st_mtime,
        )
        if local_archive.stat().st_mtime >= latest_source_mtime:
            archive_bytes = local_archive.read_bytes()
            return f"assets/blobs/{archive_name}", archive_bytes

    with zipfile.ZipFile(local_archive, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for child in artifact_path.rglob("*"):
            if child.is_file():
                zf.write(child, arcname=str(child.relative_to(artifact_path)))
    archive_bytes = local_archive.read_bytes()
    return f"assets/blobs/{archive_name}", archive_bytes


def _estimate_asset_sync_size(asset) -> int:
    if getattr(asset, "artifact_size", None):
        return int(asset.artifact_size or 0)

    artifact_path = Path(asset.artifact_path)
    if not artifact_path.exists():
        return 0
    if artifact_path.is_file():
        return artifact_path.stat().st_size

    total_size = 0
    for child in artifact_path.rglob("*"):
        if child.is_file():
            total_size += child.stat().st_size
    return total_size


def _cache_remote_session(config: Config, payload: dict[str, Any]):
    remote_path = payload.get("remote_path")
    if not isinstance(remote_path, str):
        return
    repo = f"{config.sync.repo_owner}/{config.sync.repo_name}"
    file_payload = _github_get_file(repo, remote_path, config.sync.access_token, ref=config.sync.branch)
    content = file_payload.get("content")
    if not isinstance(content, str):
        return
    decoded = base64.b64decode(content.encode("ascii"))
    local_root = config.readable_path / "synced-sessions" / payload.get("framework", "unknown") / payload.get("machine_id", "remote")
    local_root.mkdir(parents=True, exist_ok=True)
    target = local_root / payload.get("file_name", Path(remote_path).name)
    target.write_bytes(decoded)
    _write_sidecar_metadata(target.with_suffix(target.suffix + ".meta.json"), payload)


def _cache_remote_asset(config: Config, payload: dict[str, Any]):
    managed_blob_path = payload.get("managed_blob_path")
    local_root = config.readable_path / "synced-assets"
    local_root.mkdir(parents=True, exist_ok=True)
    asset_id = payload.get("id") or payload.get("name") or "remote-asset"
    _write_sidecar_metadata(local_root / "meta" / f"{asset_id}.json", payload)

    if not isinstance(managed_blob_path, str):
        return

    repo = f"{config.sync.repo_owner}/{config.sync.repo_name}"
    file_payload = _github_get_file(repo, managed_blob_path, config.sync.access_token, ref=config.sync.branch)
    content = file_payload.get("content")
    if not isinstance(content, str):
        return
    decoded = base64.b64decode(content.encode("ascii"))
    target = local_root / Path(managed_blob_path).name
    target.write_bytes(decoded)


def _github_put_json(repo: str, branch: str, path: str, payload: dict[str, Any], access_token: str, message: str):
    _github_put_file(repo, branch, path, json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8"), access_token, message)


def _github_commit_files(
    repo: str,
    branch: str,
    access_token: str,
    files: dict[str, bytes],
    message: str,
    progress_callback: Callable[[str], None] | None = None,
):
    if not files:
        return

    branch_payload = _github_get_json(f"https://api.github.com/repos/{repo}/branches/{branch}", access_token)
    base_commit_sha = branch_payload.get("commit", {}).get("sha")
    base_tree_sha = branch_payload.get("commit", {}).get("commit", {}).get("tree", {}).get("sha")
    if not base_commit_sha or not base_tree_sha:
        raise GitHubSyncError("批量提交失败：无法解析当前分支的 commit/tree")

    tree_entries = []
    total_files = len(files)
    for index, (path, content) in enumerate(files.items(), start=1):
        if _should_report_progress(index, total_files, 10):
            _emit_progress(progress_callback, f"正在上传 GitHub 文件 {index}/{total_files}: {Path(path).name}")
        blob = _github_request_json(
            f"https://api.github.com/repos/{repo}/git/blobs",
            access_token,
            "POST",
            {
                "content": base64.b64encode(content).decode("ascii"),
                "encoding": "base64",
            },
        )
        blob_sha = blob.get("sha")
        if not blob_sha:
            raise GitHubSyncError(f"批量提交失败：无法为 {path} 创建 blob")
        tree_entries.append(
            {
                "path": path,
                "mode": "100644",
                "type": "blob",
                "sha": blob_sha,
            }
        )

    tree = _github_request_json(
        f"https://api.github.com/repos/{repo}/git/trees",
        access_token,
        "POST",
        {
            "base_tree": base_tree_sha,
            "tree": tree_entries,
        },
    )
    tree_sha = tree.get("sha")
    if not tree_sha:
        raise GitHubSyncError("批量提交失败：无法创建 tree")

    commit = _github_request_json(
        f"https://api.github.com/repos/{repo}/git/commits",
        access_token,
        "POST",
        {
            "message": message,
            "tree": tree_sha,
            "parents": [base_commit_sha],
        },
    )
    commit_sha = commit.get("sha")
    if not commit_sha:
        raise GitHubSyncError("批量提交失败：无法创建 commit")

    _github_request_json(
        f"https://api.github.com/repos/{repo}/git/refs/heads/{parse.quote(branch)}",
        access_token,
        "PATCH",
        {
            "sha": commit_sha,
            "force": False,
        },
    )


def _json_bytes(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")


def _repo_needs_bootstrap(repo_payload: dict[str, Any]) -> bool:
    size = repo_payload.get("size")
    return isinstance(size, int) and size == 0


def _github_bootstrap_empty_branch(repo: str, branch: str, access_token: str):
    bootstrap_path = ".ai-memory/README.md"
    bootstrap_content = (
        "# AI Memory Sync Repository\n\n"
        "This repository was initialized automatically by AI Memory so the first sync can create the default branch and store sync data.\n"
    )
    _github_request_json(
        f"https://api.github.com/repos/{repo}/contents/{parse.quote(bootstrap_path, safe='/')}",
        access_token,
        "PUT",
        {
            "message": "chore: initialize AI Memory sync repository",
            "content": base64.b64encode(bootstrap_content.encode("utf-8")).decode("ascii"),
        },
    )


def _write_sidecar_metadata(path: Path, payload: dict[str, Any]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _normalize_datetime(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=_LOCAL_TIMEZONE)
    return value.astimezone(_LOCAL_TIMEZONE)


def _hash_bytes(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _format_bytes(value: int) -> str:
    size = float(max(0, value))
    units = ["B", "KB", "MB", "GB", "TB"]
    for unit in units:
        if size < 1024.0 or unit == units[-1]:
            return f"{size:.1f} {unit}" if unit != "B" else f"{int(size)} B"
        size /= 1024.0
    return f"{size:.1f} TB"


def _detect_session_framework(session_file: Path) -> str:
    path_text = str(session_file).lower()
    if "chatsessions" in path_text:
        return "copilot"
    if "transcripts" in path_text and "github.copilot-chat" in path_text:
        return "copilot"
    if "agent-transcripts" in path_text:
        return "cursor"
    if "openclaw" in path_text:
        return "openclaw"
    if "thundersoft.toder" in path_text or "/tasks/" in path_text:
        return "toder"
    return "generic"