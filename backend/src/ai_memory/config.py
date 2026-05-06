from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os
import platform
import re
import yaml


@dataclass
class ChannelConfig:
    enabled: bool = True
    weight: float = 0.25


@dataclass
class RetrievalConfig:
    channels: dict[str, ChannelConfig] = field(default_factory=lambda: {
        "fts": ChannelConfig(True, 0.25),
        "vector": ChannelConfig(True, 0.35),
        "graph": ChannelConfig(True, 0.20),
        "temporal": ChannelConfig(True, 0.20),
    })
    top_k: int = 10
    rrf_k: int = 60


@dataclass
class DecayConfig:
    enabled: bool = True
    check_interval_hours: int = 24
    protection_days: int = 30
    min_strength: float = 0.1
    core_threshold: float = 5.0
    procedural_rate_factor: float = 0.5


@dataclass
class WorkingMemoryConfig:
    max_tokens: int = 2000
    fixed_section_tokens: int = 300
    dynamic_section_tokens: int = 1500
    recent_section_tokens: int = 200
    recent_sessions: int = 3


@dataclass
class ConsolidationConfig:
    on_access: bool = True
    spacing_bonus_max: float = 3.0
    co_retrieval_bonus: float = 0.05


@dataclass
class EmbeddingConfig:
    model: str = "BAAI/bge-small-zh-v1.5"
    device: str = "cpu"
    cache_dir: str = "~/.local/share/ai-memory/models/"
    lazy_load: bool = True


@dataclass
class AssetConfig:
    auto_hash: bool = True
    validate_on_lookup: bool = False


@dataclass
class MemoryConfig:
    db_path: str = "~/.local/share/ai-memory/db/memory.db"
    readable_path: str = "~/.local/share/ai-memory/readable/"


def _default_machine_id() -> str:
    hostname = platform.node().strip().lower() or "machine"
    system_name = platform.system().strip().lower() or "unknown"
    safe_host = re.sub(r"[^a-z0-9._-]+", "-", hostname).strip("-._") or "machine"
    safe_system = re.sub(r"[^a-z0-9._-]+", "-", system_name).strip("-._") or "unknown"
    return f"{safe_host}-{safe_system}"


@dataclass
class SyncConfig:
    enabled: bool = False
    provider: str = "github"
    repo_owner: str = ""
    repo_name: str = ""
    branch: str = "main"
    remote_url: str = ""
    auth_mode: str = "oauth"
    oauth_client_id: str = ""
    access_token: str = ""
    token_type: str = "bearer"
    token_scope: str = "repo"
    github_user: str = ""
    machine_id: str = field(default_factory=_default_machine_id)
    sync_mode: str = "manual"
    sync_interval_minutes: int = 30
    upload_sessions: bool = False
    upload_assets: bool = False
    upload_sensitive_sessions: bool = False
    upload_size_limit_mb: int = 512
    oversize_action: str = "prompt"
    asset_size_scope: str = "asset_directory"
    compress_upload: bool = True
    chunk_large_files: bool = True
    chunk_size_mb: int = 32
    whitelist_first: bool = False
    skip_blacklist_matches: bool = True
    whitelist_patterns: list[str] = field(default_factory=list)
    blacklist_patterns: list[str] = field(default_factory=list)
    device_notes: dict[str, str] = field(default_factory=dict)
    worktree_path: str = "~/.local/share/ai-memory/sync-worktree"
    last_sync_at: Optional[str] = None
    last_synced_change_id: Optional[str] = None


@dataclass
class Config:
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    decay: DecayConfig = field(default_factory=DecayConfig)
    working_memory: WorkingMemoryConfig = field(default_factory=WorkingMemoryConfig)
    consolidation: ConsolidationConfig = field(default_factory=ConsolidationConfig)
    asset: AssetConfig = field(default_factory=AssetConfig)
    sync: SyncConfig = field(default_factory=SyncConfig)

    @property
    def db_path(self) -> Path:
        return Path(self.memory.db_path).expanduser()

    @property
    def readable_path(self) -> Path:
        return Path(self.memory.readable_path).expanduser()


def load_config(path: Optional[str] = None) -> Config:
    if path is None:
        path = os.environ.get(
            "AI_MEMORY_CONFIG",
            os.path.expanduser("~/.local/share/ai-memory/config.yaml"),
        )

    config_path = Path(path)
    if not config_path.exists():
        return Config()

    with open(config_path) as f:
        raw = yaml.safe_load(f) or {}

    return _parse_config(raw)


def save_config(config: Config, path: Optional[str] = None) -> Path:
    if path is None:
        path = os.environ.get(
            "AI_MEMORY_CONFIG",
            os.path.expanduser("~/.local/share/ai-memory/config.yaml"),
        )

    config_path = Path(path)
    config_path.parent.mkdir(parents=True, exist_ok=True)
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(_config_to_raw(config), f, allow_unicode=True, sort_keys=False)
    return config_path


def _parse_config(raw: dict) -> Config:
    cfg = Config()

    if "memory" in raw:
        m = raw["memory"]
        cfg.memory = MemoryConfig(
            db_path=m.get("db_path", cfg.memory.db_path),
            readable_path=m.get("readable_path", cfg.memory.readable_path),
        )

    if "embedding" in raw:
        e = raw["embedding"]
        cfg.embedding = EmbeddingConfig(
            model=e.get("model", cfg.embedding.model),
            device=e.get("device", cfg.embedding.device),
            cache_dir=e.get("cache_dir", cfg.embedding.cache_dir),
            lazy_load=e.get("lazy_load", cfg.embedding.lazy_load),
        )

    if "retrieval" in raw:
        r = raw["retrieval"]
        if "channels" in r:
            channels = {}
            for name, ch in r["channels"].items():
                channels[name] = ChannelConfig(
                    enabled=ch.get("enabled", True),
                    weight=ch.get("weight", 0.25),
                )
            cfg.retrieval.channels = channels
        cfg.retrieval.top_k = r.get("top_k", cfg.retrieval.top_k)
        cfg.retrieval.rrf_k = r.get("rrf_k", cfg.retrieval.rrf_k)

    if "decay" in raw:
        d = raw["decay"]
        cfg.decay = DecayConfig(
            enabled=d.get("enabled", cfg.decay.enabled),
            check_interval_hours=d.get("check_interval_hours", cfg.decay.check_interval_hours),
            protection_days=d.get("protection_days", cfg.decay.protection_days),
            min_strength=d.get("min_strength", cfg.decay.min_strength),
            core_threshold=d.get("core_threshold", cfg.decay.core_threshold),
            procedural_rate_factor=d.get("procedural_rate_factor", cfg.decay.procedural_rate_factor),
        )

    if "working_memory" in raw:
        w = raw["working_memory"]
        cfg.working_memory = WorkingMemoryConfig(
            max_tokens=w.get("max_tokens", cfg.working_memory.max_tokens),
            fixed_section_tokens=w.get("fixed_section_tokens", cfg.working_memory.fixed_section_tokens),
            dynamic_section_tokens=w.get("dynamic_section_tokens", cfg.working_memory.dynamic_section_tokens),
            recent_section_tokens=w.get("recent_section_tokens", cfg.working_memory.recent_section_tokens),
            recent_sessions=w.get("recent_sessions", cfg.working_memory.recent_sessions),
        )

    if "consolidation" in raw:
        c = raw["consolidation"]
        cfg.consolidation = ConsolidationConfig(
            on_access=c.get("on_access", cfg.consolidation.on_access),
            spacing_bonus_max=c.get("spacing_bonus_max", cfg.consolidation.spacing_bonus_max),
            co_retrieval_bonus=c.get("co_retrieval_bonus", cfg.consolidation.co_retrieval_bonus),
        )

    if "asset" in raw:
        a = raw["asset"]
        cfg.asset = AssetConfig(
            auto_hash=a.get("auto_hash", cfg.asset.auto_hash),
            validate_on_lookup=a.get("validate_on_lookup", cfg.asset.validate_on_lookup),
        )

    if "sync" in raw:
        s = raw["sync"]
        cfg.sync = SyncConfig(
            enabled=s.get("enabled", cfg.sync.enabled),
            provider=s.get("provider", cfg.sync.provider),
            repo_owner=s.get("repo_owner", cfg.sync.repo_owner),
            repo_name=s.get("repo_name", cfg.sync.repo_name),
            branch=s.get("branch", cfg.sync.branch),
            remote_url=s.get("remote_url", cfg.sync.remote_url),
            auth_mode=s.get("auth_mode", cfg.sync.auth_mode),
            oauth_client_id=s.get("oauth_client_id", cfg.sync.oauth_client_id),
            access_token=s.get("access_token", cfg.sync.access_token),
            token_type=s.get("token_type", cfg.sync.token_type),
            token_scope=s.get("token_scope", cfg.sync.token_scope),
            github_user=s.get("github_user", cfg.sync.github_user),
            machine_id=s.get("machine_id", cfg.sync.machine_id) or _default_machine_id(),
            sync_mode=s.get("sync_mode", cfg.sync.sync_mode),
            sync_interval_minutes=s.get("sync_interval_minutes", cfg.sync.sync_interval_minutes),
            upload_sessions=s.get("upload_sessions", cfg.sync.upload_sessions),
            upload_assets=s.get("upload_assets", cfg.sync.upload_assets),
            upload_sensitive_sessions=s.get("upload_sensitive_sessions", cfg.sync.upload_sensitive_sessions),
            upload_size_limit_mb=s.get("upload_size_limit_mb", cfg.sync.upload_size_limit_mb),
            oversize_action=s.get("oversize_action", cfg.sync.oversize_action),
            asset_size_scope=s.get("asset_size_scope", cfg.sync.asset_size_scope),
            compress_upload=s.get("compress_upload", cfg.sync.compress_upload),
            chunk_large_files=s.get("chunk_large_files", cfg.sync.chunk_large_files),
            chunk_size_mb=s.get("chunk_size_mb", cfg.sync.chunk_size_mb),
            whitelist_first=s.get("whitelist_first", cfg.sync.whitelist_first),
            skip_blacklist_matches=s.get("skip_blacklist_matches", cfg.sync.skip_blacklist_matches),
            whitelist_patterns=list(s.get("whitelist_patterns", cfg.sync.whitelist_patterns) or []),
            blacklist_patterns=list(s.get("blacklist_patterns", cfg.sync.blacklist_patterns) or []),
            device_notes=dict(s.get("device_notes", cfg.sync.device_notes) or {}),
            worktree_path=s.get("worktree_path", cfg.sync.worktree_path),
            last_sync_at=s.get("last_sync_at", cfg.sync.last_sync_at),
            last_synced_change_id=s.get("last_synced_change_id", cfg.sync.last_synced_change_id),
        )

    return cfg


def _config_to_raw(config: Config) -> dict:
    return {
        "memory": {
            "db_path": config.memory.db_path,
            "readable_path": config.memory.readable_path,
        },
        "embedding": {
            "model": config.embedding.model,
            "device": config.embedding.device,
            "cache_dir": config.embedding.cache_dir,
            "lazy_load": config.embedding.lazy_load,
        },
        "retrieval": {
            "channels": {
                name: {
                    "enabled": channel.enabled,
                    "weight": channel.weight,
                }
                for name, channel in config.retrieval.channels.items()
            },
            "top_k": config.retrieval.top_k,
            "rrf_k": config.retrieval.rrf_k,
        },
        "decay": {
            "enabled": config.decay.enabled,
            "check_interval_hours": config.decay.check_interval_hours,
            "protection_days": config.decay.protection_days,
            "min_strength": config.decay.min_strength,
            "core_threshold": config.decay.core_threshold,
            "procedural_rate_factor": config.decay.procedural_rate_factor,
        },
        "working_memory": {
            "max_tokens": config.working_memory.max_tokens,
            "fixed_section_tokens": config.working_memory.fixed_section_tokens,
            "dynamic_section_tokens": config.working_memory.dynamic_section_tokens,
            "recent_section_tokens": config.working_memory.recent_section_tokens,
            "recent_sessions": config.working_memory.recent_sessions,
        },
        "consolidation": {
            "on_access": config.consolidation.on_access,
            "spacing_bonus_max": config.consolidation.spacing_bonus_max,
            "co_retrieval_bonus": config.consolidation.co_retrieval_bonus,
        },
        "asset": {
            "auto_hash": config.asset.auto_hash,
            "validate_on_lookup": config.asset.validate_on_lookup,
        },
        "sync": {
            "enabled": config.sync.enabled,
            "provider": config.sync.provider,
            "repo_owner": config.sync.repo_owner,
            "repo_name": config.sync.repo_name,
            "branch": config.sync.branch,
            "remote_url": config.sync.remote_url,
            "auth_mode": config.sync.auth_mode,
            "oauth_client_id": config.sync.oauth_client_id,
            "access_token": config.sync.access_token,
            "token_type": config.sync.token_type,
            "token_scope": config.sync.token_scope,
            "github_user": config.sync.github_user,
            "machine_id": config.sync.machine_id,
            "sync_mode": config.sync.sync_mode,
            "sync_interval_minutes": config.sync.sync_interval_minutes,
            "upload_sessions": config.sync.upload_sessions,
            "upload_assets": config.sync.upload_assets,
            "upload_sensitive_sessions": config.sync.upload_sensitive_sessions,
            "upload_size_limit_mb": config.sync.upload_size_limit_mb,
            "oversize_action": config.sync.oversize_action,
            "asset_size_scope": config.sync.asset_size_scope,
            "compress_upload": config.sync.compress_upload,
            "chunk_large_files": config.sync.chunk_large_files,
            "chunk_size_mb": config.sync.chunk_size_mb,
            "whitelist_first": config.sync.whitelist_first,
            "skip_blacklist_matches": config.sync.skip_blacklist_matches,
            "whitelist_patterns": list(config.sync.whitelist_patterns),
            "blacklist_patterns": list(config.sync.blacklist_patterns),
            "device_notes": dict(config.sync.device_notes),
            "worktree_path": config.sync.worktree_path,
            "last_sync_at": config.sync.last_sync_at,
            "last_synced_change_id": config.sync.last_synced_change_id,
        },
    }
