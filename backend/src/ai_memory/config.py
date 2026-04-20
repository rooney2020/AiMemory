from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional
import os
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


@dataclass
class Config:
    memory: MemoryConfig = field(default_factory=MemoryConfig)
    embedding: EmbeddingConfig = field(default_factory=EmbeddingConfig)
    retrieval: RetrievalConfig = field(default_factory=RetrievalConfig)
    decay: DecayConfig = field(default_factory=DecayConfig)
    working_memory: WorkingMemoryConfig = field(default_factory=WorkingMemoryConfig)
    consolidation: ConsolidationConfig = field(default_factory=ConsolidationConfig)
    asset: AssetConfig = field(default_factory=AssetConfig)

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

    return cfg
