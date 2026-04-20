from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional

from ..config import Config
from ..storage.memory_store import MemoryStore
from .fts import FTSIndex
from .graph import GraphIndex
from .temporal import TemporalIndex


@dataclass
class RetrievalResult:
    memory_id: str
    score: float
    channels: dict[str, float] = field(default_factory=dict)


class FusionRetriever:
    """4通道检索 + RRF 融合 + 强度加权"""

    def __init__(
        self,
        fts_index: FTSIndex,
        graph_index: GraphIndex,
        temporal_index: TemporalIndex,
        memory_store: MemoryStore,
        config: Config,
        vector_index=None,
    ):
        self.fts = fts_index
        self.vector = vector_index
        self.graph = graph_index
        self.temporal = temporal_index
        self.store = memory_store
        self.config = config

    def retrieve(
        self,
        query: str,
        project: Optional[str] = None,
        memory_type: Optional[str] = None,
        time_range: Optional[tuple[datetime, datetime]] = None,
        top_k: int = 10,
    ) -> list[RetrievalResult]:
        channel_results: dict[str, list[tuple[str, float]]] = {}
        channels_cfg = self.config.retrieval.channels

        fts_cfg = channels_cfg.get("fts")
        if fts_cfg and fts_cfg.enabled:
            channel_results["fts"] = self.fts.search(query, top_k=top_k * 3)

        vector_cfg = channels_cfg.get("vector")
        if vector_cfg and vector_cfg.enabled and self.vector is not None:
            channel_results["vector"] = self.vector.search(
                query, top_k=top_k * 3, project=project
            )

        graph_cfg = channels_cfg.get("graph")
        if graph_cfg and graph_cfg.enabled:
            entities = self._extract_query_entities(query)
            if entities:
                channel_results["graph"] = self.graph.traverse(
                    entities, max_depth=2, top_k=top_k * 3
                )

        temporal_cfg = channels_cfg.get("temporal")
        if temporal_cfg and temporal_cfg.enabled and time_range:
            channel_results["temporal"] = self.temporal.query(
                time_range, project=project, top_k=top_k * 3
            )

        rrf_scores = self._rrf_fuse(channel_results, k=self.config.retrieval.rrf_k)

        results = []
        for memory_id, rrf_score, ch_scores in rrf_scores:
            memory = self.store.get(memory_id)
            if memory and not memory.archived:
                if project and memory.project and memory.project != project:
                    continue
                if memory_type and memory.type.value != memory_type:
                    continue

                eff = self._effective_strength(memory)
                final_score = rrf_score * (eff ** 0.3)
                results.append(RetrievalResult(
                    memory_id=memory_id,
                    score=final_score,
                    channels=ch_scores,
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _rrf_fuse(
        self,
        channel_results: dict[str, list[tuple[str, float]]],
        k: int = 60,
    ) -> list[tuple[str, float, dict[str, float]]]:
        scores: dict[str, dict] = defaultdict(lambda: {"score": 0.0, "channels": {}})
        channels_cfg = self.config.retrieval.channels

        for channel_name, hits in channel_results.items():
            ch_cfg = channels_cfg.get(channel_name)
            weight = ch_cfg.weight if ch_cfg else 0.25
            reverse = channel_name != "vector"
            sorted_hits = sorted(hits, key=lambda x: x[1], reverse=reverse)

            for rank, (mid, raw_score) in enumerate(sorted_hits, start=1):
                rrf_contribution = weight / (k + rank)
                scores[mid]["score"] += rrf_contribution
                scores[mid]["channels"][channel_name] = raw_score

        result = [
            (mid, data["score"], data["channels"])
            for mid, data in scores.items()
        ]
        result.sort(key=lambda x: x[1], reverse=True)
        return result

    def _effective_strength(self, memory) -> float:
        if not memory.last_accessed:
            return memory.strength

        elapsed = (datetime.now() - memory.last_accessed).days
        if memory.strength >= self.config.decay.core_threshold:
            return memory.strength
        if elapsed <= self.config.decay.protection_days:
            return memory.strength

        lambda_ = memory.decay_rate / (1 + math.log(memory.strength + 1))
        return memory.strength * math.exp(-lambda_ * elapsed)

    def _extract_query_entities(self, query: str) -> list[str]:
        known = self.graph.get_all_entity_names()
        found = []
        query_lower = query.lower()
        for name in known:
            if name.lower() in query_lower:
                found.append(name)
        return found
