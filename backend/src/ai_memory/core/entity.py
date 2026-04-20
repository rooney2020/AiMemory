from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
import uuid


@dataclass
class Entity:
    name: str
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    type: Optional[str] = None
    attrs: Optional[dict] = None
    created_at: datetime = field(default_factory=datetime.now)


@dataclass
class Relation:
    source_id: str
    target_id: str
    relation: str
    id: Optional[int] = None
    weight: float = 1.0
    created_at: datetime = field(default_factory=datetime.now)
