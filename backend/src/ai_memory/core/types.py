from enum import Enum


class MemoryType(str, Enum):
    EPISODIC = "episodic"
    SEMANTIC = "semantic"
    PROCEDURAL = "procedural"


class Importance(str, Enum):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


IMPORTANCE_STRENGTH: dict[Importance, float] = {
    Importance.LOW: 0.5,
    Importance.NORMAL: 1.0,
    Importance.HIGH: 2.0,
    Importance.CRITICAL: 5.0,
}


class AssetType(str, Enum):
    DECOMPILE = "decompile"
    TOOL = "tool"
    APP = "app"
    SCRIPT = "script"
    DATA = "data"


class RelationType(str, Enum):
    CAUSES = "causes"
    FIXES = "fixes"
    RELATES_TO = "relates_to"
    CONTAINS = "contains"
    DEPENDS_ON = "depends_on"
