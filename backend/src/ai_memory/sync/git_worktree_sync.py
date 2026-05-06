from __future__ import annotations

import base64
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from typing import Any, Callable

from ai_memory.config import Config, save_config
from ai_memory.sync.github_sync import (
    _MAX_SYNC_FILE_BYTES,
    _evaluate_sync_path_rules,
    _format_bytes,
    _iter_local_memories,
    _iter_session_files,
)


class GitWorktreeSyncError(RuntimeError):
    pass


@dataclass
class GitWorktreeRunResult:
    ok: bool
    mode: str
    repo: str
    branch: str
    phases: list[str]
    materialized_items: int = 0
    committed: bool = False
    pushed: bool = False
    message: str = ""
    synced_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def run_sync_cycle(config: Config, progress_callback: Callable[[str], None] | None = None) -> dict[str, Any]:
    sync = config.sync
    _emit(progress_callback, "正在准备 git 工作区同步...")
    _ensure_sync_ready(sync.enabled, sync.repo_owner, sync.repo_name, sync.access_token)

    worktree = Path(sync.worktree_path).expanduser()
    repo = f"{sync.repo_owner}/{sync.repo_name}"
    phases = ["prepare"]

    _ensure_git_available()
    _ensure_worktree_repo(worktree, sync, progress_callback)

    phases.append("materialize")
    plan = _materialize_sync_workspace(config, worktree, progress_callback)

    phases.append("commit")
    committed = _commit_worktree(worktree, sync, plan, progress_callback)

    phases.append("push")
    pushed = False
    if committed:
        _push_worktree(worktree, sync, progress_callback)
        pushed = True

    synced_at = datetime.now(timezone.utc).isoformat()
    sync.last_sync_at = synced_at
    save_config(config)

    message = "git 工作区同步完成"
    if not committed:
        message = "git 工作区已更新，但没有新的文件变化可提交。"
    skipped_large_files = list(plan.get("skipped_large_files") or [])
    if skipped_large_files:
        preview = "、".join(skipped_large_files[:3])
        if len(skipped_large_files) > 3:
            preview = f"{preview} 等 {len(skipped_large_files)} 个文件"
        message = f"git 工作区同步完成，但已跳过 GitHub 不支持的大文件：{preview}。"

    return GitWorktreeRunResult(
        ok=True,
        mode="git_worktree",
        repo=repo,
        branch=sync.branch,
        phases=phases,
        materialized_items=plan["summary"]["total_items"],
        committed=committed,
        pushed=pushed,
        message=message,
        synced_at=synced_at,
    ).to_dict()


def _emit(progress_callback: Callable[[str], None] | None, message: str):
    if progress_callback is not None:
        progress_callback(message)


def _ensure_sync_ready(enabled: bool, repo_owner: str, repo_name: str, access_token: str):
    if not enabled:
        raise GitWorktreeSyncError("同步总开关未启用")
    if not repo_owner or not repo_name:
        raise GitWorktreeSyncError("请先配置 GitHub 仓库所有者和仓库名称")
    if not access_token:
        raise GitWorktreeSyncError("请先完成 GitHub 登录")


def _ensure_git_available():
    try:
        subprocess.run(["git", "--version"], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    except Exception as exc:
        raise GitWorktreeSyncError("当前环境没有可用的 git 命令") from exc


def _git_auth_args(sync) -> list[str]:
    token = (sync.access_token or "").strip()
    if not token:
        return []
    raw = f"x-access-token:{token}".encode("utf-8")
    header = base64.b64encode(raw).decode("ascii")
    return ["-c", f"http.extraheader=AUTHORIZATION: basic {header}"]


def _git_run(worktree: Path, sync, args: list[str], progress_callback: Callable[[str], None] | None = None, check: bool = True) -> subprocess.CompletedProcess:
    command = ["git", *_git_auth_args(sync), *args]
    result = subprocess.run(
        command,
        cwd=str(worktree),
        text=True,
        capture_output=True,
        check=False,
    )
    if check and result.returncode != 0:
        detail = (result.stderr or result.stdout or "").strip()
        raise GitWorktreeSyncError(detail or f"git {' '.join(args)} 执行失败")
    if progress_callback and (result.stdout or result.stderr):
        output = (result.stdout or result.stderr).strip().splitlines()
        if output:
            progress_callback(output[-1])
    return result


def _ensure_worktree_repo(worktree: Path, sync, progress_callback: Callable[[str], None] | None = None):
    worktree.mkdir(parents=True, exist_ok=True)
    remote_url = (getattr(sync, "remote_url", "") or "").strip() or f"https://github.com/{sync.repo_owner}/{sync.repo_name}.git"

    if not (worktree / ".git").exists():
        _emit(progress_callback, f"正在初始化同步工作区 {worktree}...")
        _git_run(worktree, sync, ["init", "-b", sync.branch], check=True)

    current_remote = _git_run(worktree, sync, ["remote", "get-url", "origin"], check=False)
    if current_remote.returncode != 0:
        _git_run(worktree, sync, ["remote", "add", "origin", remote_url], check=True)
    elif (current_remote.stdout or "").strip() != remote_url:
        _git_run(worktree, sync, ["remote", "set-url", "origin", remote_url], check=True)

    ls_remote = _git_run(worktree, sync, ["ls-remote", "--heads", "origin", sync.branch], check=False)
    if (ls_remote.stdout or "").strip():
        _emit(progress_callback, f"正在同步远端分支 {sync.branch} 到本地工作区...")
        _git_run(worktree, sync, ["fetch", "origin", sync.branch], check=True)
        _git_run(worktree, sync, ["checkout", "-B", sync.branch, "FETCH_HEAD"], check=True)
    else:
        _git_run(worktree, sync, ["checkout", "-B", sync.branch], check=True)


def _materialize_sync_workspace(config: Config, worktree: Path, progress_callback: Callable[[str], None] | None = None) -> dict[str, Any]:
    root_dirs = [
        worktree / "memories",
        worktree / "sessions",
        worktree / "assets",
        worktree / "rules",
        worktree / "state",
        worktree / ".aimemory",
    ]
    for directory in root_dirs:
        directory.mkdir(parents=True, exist_ok=True)

    memory_count = _materialize_memories(config, worktree, progress_callback)
    session_count, skipped_sessions = _materialize_sessions(config, worktree, progress_callback)
    asset_count, skipped_assets = _materialize_assets(config, worktree, progress_callback)

    _write_rules(config, worktree)

    summary = {
        "memories": memory_count,
        "sessions": session_count,
        "assets": asset_count,
        "total_items": memory_count + session_count + asset_count,
    }
    manifest = {
        "version": 1,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "machine_id": config.sync.machine_id,
        "provider": "git_worktree",
        "repo_owner": config.sync.repo_owner,
        "repo_name": config.sync.repo_name,
        "branch": config.sync.branch,
        "summary": summary,
        "rules": {
            "whitelist_patterns": list(config.sync.whitelist_patterns or []),
            "blacklist_patterns": list(config.sync.blacklist_patterns or []),
            "upload_size_limit_mb": config.sync.upload_size_limit_mb,
            "compress_upload": config.sync.compress_upload,
            "chunk_large_files": config.sync.chunk_large_files,
            "chunk_size_mb": config.sync.chunk_size_mb,
        },
    }
    sync_plan = {
        "generated_at": manifest["generated_at"],
        "machine_id": config.sync.machine_id,
        "summary": summary,
    }

    (worktree / ".aimemory" / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    (worktree / "state" / "sync-plan.json").write_text(json.dumps(sync_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    (worktree / "README.md").write_text(
        "# AI Memory Sync Worktree\n\n此目录由 AI Memory 自动维护，用于 git 工作区同步。\n",
        encoding="utf-8",
    )
    return {
        "summary": summary,
        "skipped_large_files": [*skipped_sessions, *skipped_assets],
    }


def _materialize_memories(config: Config, worktree: Path, progress_callback: Callable[[str], None] | None = None) -> int:
    target_root = worktree / "memories"
    count = 0
    active_paths: set[Path] = set()
    memories = list(_iter_local_memories(config, None))
    total = len(memories)
    if total:
        _emit(progress_callback, f"正在写入记忆快照 0/{total}...")
    for index, memory in enumerate(memories, start=1):
        kind_dir = target_root / memory.type.value
        kind_dir.mkdir(parents=True, exist_ok=True)
        payload = {
            "id": memory.id,
            "type": memory.type.value,
            "summary": memory.summary,
            "content": memory.content,
            "project": memory.project,
            "session_id": memory.session_id,
            "entities": list(memory.entities or []),
            "tags": list(memory.tags or []),
            "created_at": memory.created_at.isoformat() if memory.created_at else None,
            "updated_at": memory.updated_at.isoformat() if memory.updated_at else None,
            "archived": bool(memory.archived),
        }
        target_path = kind_dir / f"{memory.id}.json"
        _write_text_if_changed(target_path, json.dumps(payload, ensure_ascii=False, indent=2))
        active_paths.add(target_path)
        count += 1
        if index == 1 or index == total or index % 50 == 0:
            _emit(progress_callback, f"正在写入记忆快照 {index}/{total}...")
    _prune_tree(target_root, active_paths)
    return count


def _materialize_sessions(config: Config, worktree: Path, progress_callback: Callable[[str], None] | None = None) -> tuple[int, list[str]]:
    if not config.sync.upload_sessions:
        return 0, []
    target_root = worktree / "sessions" / "raw"
    target_root.mkdir(parents=True, exist_ok=True)
    session_files = list(_iter_session_files(None))
    total = len(session_files)
    count = 0
    active_paths: set[Path] = set()
    skipped_large_files: list[str] = []
    if total:
        _emit(progress_callback, f"正在写入原始会话 0/{total}...")
    for index, session_file in enumerate(session_files, start=1):
        rule_flags = _evaluate_sync_path_rules(config.sync, str(session_file))
        if rule_flags["blocked"]:
            continue
        try:
            session_size = session_file.stat().st_size
        except OSError:
            session_size = 0
        if _should_skip_due_to_size(
            config,
            entry_path=str(session_file),
            entry_name=session_file.name,
            size_bytes=session_size,
            progress_callback=progress_callback,
            scope_label="原始会话",
            allow_chunking=True,
        ):
            skipped_large_files.append(f"会话 {session_file.name}")
            continue
        if _should_chunk_large_file(config, session_size):
            chunk_paths = _materialize_chunked_file(
                source=session_file,
                target_root=target_root,
                chunk_size_bytes=_chunk_size_bytes(config),
                compress_chunks=bool(config.sync.compress_upload),
            )
            active_paths.update(chunk_paths)
            count += 1
            _emit(
                progress_callback,
                f"已将大文件会话切片写入 {session_file.name}（{len(chunk_paths) - 1} 个文件对象）。",
            )
            continue
        target_path = target_root / session_file.name
        _copy_file_if_needed(session_file, target_path)
        active_paths.add(target_path)
        count += 1
        if index == 1 or index == total or index % 20 == 0:
            _emit(progress_callback, f"正在写入原始会话 {index}/{total}...")
    _prune_tree(target_root, active_paths)
    return count, skipped_large_files


def _materialize_assets(config: Config, worktree: Path, progress_callback: Callable[[str], None] | None = None) -> tuple[int, list[str]]:
    if not config.sync.upload_assets:
        return 0, []
    files_root = worktree / "assets" / "files"
    index_root = worktree / "assets" / "index"
    files_root.mkdir(parents=True, exist_ok=True)
    index_root.mkdir(parents=True, exist_ok=True)

    assets = list(config._asset_registry.lookup(valid_only=False))  # type: ignore[attr-defined]
    total = len(assets)
    count = 0
    active_asset_dirs: set[Path] = set()
    active_index_files: set[Path] = set()
    skipped_large_files: list[str] = []
    if total:
        _emit(progress_callback, f"正在写入资产快照 0/{total}...")
    for index, asset in enumerate(assets, start=1):
        rule_flags = _evaluate_sync_path_rules(config.sync, asset.artifact_path)
        if rule_flags["blocked"]:
            continue
        estimated_size = int(asset.artifact_size or 0)
        if estimated_size <= 0:
            estimated_size = _estimate_path_size(Path(asset.artifact_path))
        if _should_skip_due_to_size(
            config,
            entry_path=asset.artifact_path,
            entry_name=asset.name,
            size_bytes=estimated_size,
            progress_callback=progress_callback,
            scope_label="托管资产",
        ):
            skipped_large_files.append(f"资产 {asset.name}")
            continue
        artifact_path = Path(asset.artifact_path)
        asset_target = files_root / asset.id
        if artifact_path.exists():
            _sync_path_if_needed(artifact_path, asset_target)
        active_asset_dirs.add(asset_target)
        meta = {
            "id": asset.id,
            "name": asset.name,
            "type": getattr(asset.asset_type, "value", str(asset.asset_type)),
            "artifact_path": asset.artifact_path,
            "artifact_size": asset.artifact_size,
            "mime_type": asset.mime_type,
            "created_at": asset.created_at.isoformat() if asset.created_at else None,
            "valid": asset.valid,
        }
        index_path = index_root / f"{asset.id}.json"
        _write_text_if_changed(index_path, json.dumps(meta, ensure_ascii=False, indent=2))
        active_index_files.add(index_path)
        count += 1
        if index == 1 or index == total or index % 10 == 0:
            _emit(progress_callback, f"正在写入资产快照 {index}/{total}...")
    _prune_tree(files_root, active_asset_dirs)
    _prune_tree(index_root, active_index_files)
    return count, skipped_large_files


def _write_rules(config: Config, worktree: Path):
    rules_root = worktree / "rules"
    (rules_root / "include.txt").write_text("\n".join(config.sync.whitelist_patterns or []), encoding="utf-8")
    (rules_root / "exclude.txt").write_text("\n".join(config.sync.blacklist_patterns or []), encoding="utf-8")


def _commit_worktree(worktree: Path, sync, plan: dict[str, Any], progress_callback: Callable[[str], None] | None = None) -> bool:
    _git_run(worktree, sync, ["add", "-A"], progress_callback=None, check=True)
    status = _git_run(worktree, sync, ["status", "--porcelain"], check=True)
    if not (status.stdout or "").strip():
        _emit(progress_callback, "同步工作区没有新的文件变化。")
        return False
    summary = plan["summary"]
    message = (
        f"sync({sync.machine_id}): "
        f"{summary['memories']} memories, {summary['sessions']} sessions, {summary['assets']} assets"
    )
    _emit(progress_callback, "正在提交本地同步工作区变化...")
    _git_run(worktree, sync, ["commit", "-m", message], check=True)
    return True


def _push_worktree(worktree: Path, sync, progress_callback: Callable[[str], None] | None = None):
    _emit(progress_callback, f"正在推送 git 工作区到 {sync.repo_owner}/{sync.repo_name}/{sync.branch}...")
    _git_run(worktree, sync, ["push", "-u", "origin", sync.branch], check=True)


def _write_text_if_changed(target: Path, content: str):
    if target.exists():
        try:
            if target.read_text(encoding="utf-8") == content:
                return
        except OSError:
            pass
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(content, encoding="utf-8")


def _copy_file_if_needed(source: Path, target: Path):
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        try:
            source_stat = source.stat()
            target_stat = target.stat()
            if source_stat.st_size == target_stat.st_size and int(source_stat.st_mtime) == int(target_stat.st_mtime):
                return
        except OSError:
            pass
    shutil.copy2(source, target)


def _write_bytes_if_changed(target: Path, content: bytes):
    if target.exists():
        try:
            if target.read_bytes() == content:
                return
        except OSError:
            pass
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_bytes(content)


def _chunk_size_bytes(config: Config) -> int:
    configured = max(1, int(getattr(config.sync, "chunk_size_mb", 32) or 32)) * 1024 * 1024
    return min(configured, _MAX_SYNC_FILE_BYTES)


def _should_chunk_large_file(config: Config, size_bytes: int) -> bool:
    return bool(getattr(config.sync, "chunk_large_files", True)) and size_bytes > _MAX_SYNC_FILE_BYTES


def _materialize_chunked_file(
    source: Path,
    target_root: Path,
    chunk_size_bytes: int,
    compress_chunks: bool,
) -> set[Path]:
    manifest_path = target_root / f"{source.name}.manifest.json"
    chunks_root = target_root / f"{source.name}.parts"
    chunks_root.mkdir(parents=True, exist_ok=True)

    active_paths: set[Path] = set()
    chunk_items: list[dict[str, object]] = []
    whole_file_hash = hashlib.sha256()
    compression = "gzip" if compress_chunks else "none"

    with source.open("rb") as handle:
        chunk_index = 1
        while True:
            raw_chunk = handle.read(chunk_size_bytes)
            if not raw_chunk:
                break
            whole_file_hash.update(raw_chunk)
            stored_chunk = gzip.compress(raw_chunk) if compress_chunks else raw_chunk
            chunk_name = f"{source.name}.part-{chunk_index:04d}{'.gz' if compress_chunks else ''}"
            chunk_path = chunks_root / chunk_name
            _write_bytes_if_changed(chunk_path, stored_chunk)
            active_paths.add(chunk_path)
            chunk_items.append(
                {
                    "index": chunk_index,
                    "file_name": chunk_name,
                    "relative_path": str(chunk_path.relative_to(target_root)),
                    "raw_size": len(raw_chunk),
                    "stored_size": len(stored_chunk),
                    "raw_sha256": hashlib.sha256(raw_chunk).hexdigest(),
                    "stored_sha256": hashlib.sha256(stored_chunk).hexdigest(),
                }
            )
            chunk_index += 1

    manifest_payload = {
        "version": 1,
        "kind": "chunked-file",
        "compression": compression,
        "original_file_name": source.name,
        "original_size": source.stat().st_size,
        "original_sha256": whole_file_hash.hexdigest(),
        "original_path": str(source),
        "chunk_size_bytes": chunk_size_bytes,
        "chunk_count": len(chunk_items),
        "chunks": chunk_items,
    }
    _write_text_if_changed(manifest_path, json.dumps(manifest_payload, ensure_ascii=False, indent=2))
    active_paths.add(manifest_path)
    return active_paths


def _sync_path_if_needed(source: Path, target: Path):
    if source.is_file():
        if target.exists() and target.is_dir():
            shutil.rmtree(target)
        _copy_file_if_needed(source, target / source.name if target.suffix == "" else target)
        return

    if target.exists() and target.is_file():
        target.unlink()
    target.mkdir(parents=True, exist_ok=True)
    active_children: set[Path] = set()
    for child in source.iterdir():
        child_target = target / child.name
        _sync_path_if_needed(child, child_target)
        active_children.add(child_target)
    _prune_tree(target, active_children)


def _estimate_path_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        try:
            return path.stat().st_size
        except OSError:
            return 0
    total = 0
    for child in path.rglob("*"):
        if not child.is_file():
            continue
        try:
            total += child.stat().st_size
        except OSError:
            continue
    return total


def _should_skip_due_to_size(
    config: Config,
    entry_path: str,
    entry_name: str,
    size_bytes: int,
    progress_callback: Callable[[str], None] | None,
    scope_label: str,
    allow_chunking: bool = False,
) -> bool:
    runtime_options = getattr(config, "_sync_runtime_options", {}) or {}
    skip_paths = {str(path) for path in runtime_options.get("skip_paths") or []}
    force_upload_paths = {str(path) for path in runtime_options.get("force_upload_paths") or []}
    limit_bytes = max(0, int(config.sync.upload_size_limit_mb or 0)) * 1024 * 1024
    oversize_action = (config.sync.oversize_action or "prompt").strip()
    rule_flags = _evaluate_sync_path_rules(config.sync, entry_path)

    if size_bytes > _MAX_SYNC_FILE_BYTES:
        if allow_chunking and _should_chunk_large_file(config, size_bytes):
            return False
        _emit(
            progress_callback,
            f"跳过超大{scope_label} {entry_name}（{_format_bytes(size_bytes)}），超过 GitHub 单文件限制 {_format_bytes(_MAX_SYNC_FILE_BYTES)}。",
        )
        return True

    if rule_flags["whitelisted"]:
        return False
    if limit_bytes <= 0 or size_bytes <= limit_bytes:
        return False
    if entry_path in force_upload_paths:
        return False
    if entry_path in skip_paths or oversize_action == "skip":
        _emit(
            progress_callback,
            f"跳过超限{scope_label} {entry_name}（{_format_bytes(size_bytes)}，限制 {_format_bytes(limit_bytes)}）。",
        )
        return True
    if oversize_action == "prompt":
        _emit(
            progress_callback,
            f"跳过待确认的超限{scope_label} {entry_name}（{_format_bytes(size_bytes)}，限制 {_format_bytes(limit_bytes)}）。",
        )
        return True
    return False


def _prune_tree(root: Path, active_paths: set[Path]):
    if not root.exists():
        return
    for candidate in sorted(root.iterdir(), key=lambda item: item.name):
        if candidate in active_paths:
            continue
        if candidate.is_dir():
            nested_active = {path for path in active_paths if candidate in path.parents}
            if nested_active:
                _prune_tree(candidate, nested_active)
                try:
                    next(candidate.iterdir())
                except StopIteration:
                    candidate.rmdir()
                continue
            shutil.rmtree(candidate)
            continue
        candidate.unlink()