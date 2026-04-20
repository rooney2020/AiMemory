from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid

from .types import MemoryType, Importance, IMPORTANCE_STRENGTH


@dataclass
class Memory:
    content: str
    type: MemoryType
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    summary: Optional[str] = None
    project: Optional[str] = None
    session_id: Optional[str] = None
    entities: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)

    strength: float = 1.0
    access_count: int = 0
    last_accessed: Optional[datetime] = None
    decay_rate: float = 0.1

    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    archived: bool = False

    embedding: Optional[list[float]] = field(default=None, repr=False)
    relevance_score: float = 0.0

    @classmethod
    def create(
        cls,
        content: str,
        type: MemoryType | str,
        importance: Importance | str = Importance.NORMAL,
        summary: Optional[str] = None,
        project: Optional[str] = None,
        session_id: Optional[str] = None,
        entities: Optional[list[str]] = None,
    ) -> Memory:
        if isinstance(type, str):
            type = MemoryType(type)
        if isinstance(importance, str):
            importance = Importance(importance)

        return cls(
            content=content,
            type=type,
            summary=summary or content[:100],
            project=project,
            session_id=session_id,
            entities=entities or [],
            strength=IMPORTANCE_STRENGTH[importance],
            decay_rate=0.05 if type == MemoryType.PROCEDURAL else 0.1,
        )
