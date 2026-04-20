-- AI Memory System Schema v1

-- 主记忆表
CREATE TABLE IF NOT EXISTS memories (
    id          TEXT PRIMARY KEY,
    type        TEXT NOT NULL CHECK(type IN ('episodic', 'semantic', 'procedural')),
    content     TEXT NOT NULL,
    summary     TEXT,
    embedding   BLOB,

    project     TEXT,
    session_id  TEXT,
    entities    TEXT,              -- JSON array of entity names
    created_at  TEXT NOT NULL,     -- ISO8601
    updated_at  TEXT NOT NULL,

    strength    REAL NOT NULL DEFAULT 1.0,
    access_count INTEGER NOT NULL DEFAULT 0,
    last_accessed TEXT,
    decay_rate  REAL NOT NULL DEFAULT 0.1,

    archived    INTEGER NOT NULL DEFAULT 0
);

-- FTS5 全文搜索
CREATE VIRTUAL TABLE IF NOT EXISTS memories_fts USING fts5(
    content, summary,
    content=memories,
    content_rowid=rowid,
    tokenize='unicode61'
);

-- FTS 同步触发器
CREATE TRIGGER IF NOT EXISTS memories_ai AFTER INSERT ON memories BEGIN
    INSERT INTO memories_fts(rowid, content, summary)
    VALUES (new.rowid, new.content, new.summary);
END;

CREATE TRIGGER IF NOT EXISTS memories_ad AFTER DELETE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, summary)
    VALUES ('delete', old.rowid, old.content, old.summary);
END;

CREATE TRIGGER IF NOT EXISTS memories_au AFTER UPDATE ON memories BEGIN
    INSERT INTO memories_fts(memories_fts, rowid, content, summary)
    VALUES ('delete', old.rowid, old.content, old.summary);
    INSERT INTO memories_fts(rowid, content, summary)
    VALUES (new.rowid, new.content, new.summary);
END;

-- 实体表
CREATE TABLE IF NOT EXISTS entities (
    id      TEXT PRIMARY KEY,
    name    TEXT NOT NULL UNIQUE,
    type    TEXT,
    attrs   TEXT,
    created_at TEXT NOT NULL
);

-- 关系表
CREATE TABLE IF NOT EXISTS relations (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source_id   TEXT NOT NULL REFERENCES entities(id),
    target_id   TEXT NOT NULL REFERENCES entities(id),
    relation    TEXT NOT NULL,
    weight      REAL NOT NULL DEFAULT 1.0,
    created_at  TEXT NOT NULL,
    UNIQUE(source_id, target_id, relation)
);

-- 记忆-实体关联
CREATE TABLE IF NOT EXISTS memory_entities (
    memory_id   TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    entity_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    role        TEXT,
    PRIMARY KEY (memory_id, entity_id)
);

-- 记忆贡献的实体关系，用于聚合自动关系边
CREATE TABLE IF NOT EXISTS memory_relations (
    memory_id   TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    source_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    target_id   TEXT NOT NULL REFERENCES entities(id) ON DELETE CASCADE,
    relation    TEXT NOT NULL,
    weight      REAL NOT NULL DEFAULT 1.0,
    created_at  TEXT NOT NULL,
    PRIMARY KEY (memory_id, source_id, target_id, relation)
);

-- 资产表
CREATE TABLE IF NOT EXISTS assets (
    id              TEXT PRIMARY KEY,
    type            TEXT NOT NULL CHECK(type IN ('decompile', 'tool', 'app', 'script', 'data')),
    name            TEXT NOT NULL,
    description     TEXT,

    source_hash     TEXT,
    source_path     TEXT,

    artifact_path   TEXT NOT NULL,
    artifact_size   INTEGER,
    tool_name       TEXT,
    tool_version    TEXT,

    tags            TEXT,              -- JSON array
    project         TEXT,
    session_id      TEXT,

    created_at      TEXT NOT NULL,
    last_used_at    TEXT,
    use_count       INTEGER DEFAULT 0,
    valid           INTEGER DEFAULT 1,
    invalid_reason  TEXT
);

-- 访问日志
CREATE TABLE IF NOT EXISTS access_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    memory_id   TEXT NOT NULL REFERENCES memories(id) ON DELETE CASCADE,
    accessed_at TEXT NOT NULL,
    context     TEXT
);

-- 索引
CREATE INDEX IF NOT EXISTS idx_memories_type ON memories(type);
CREATE INDEX IF NOT EXISTS idx_memories_project ON memories(project);
CREATE INDEX IF NOT EXISTS idx_memories_created ON memories(created_at);
CREATE INDEX IF NOT EXISTS idx_memories_strength ON memories(strength);
CREATE INDEX IF NOT EXISTS idx_memories_archived ON memories(archived);
CREATE INDEX IF NOT EXISTS idx_relations_source ON relations(source_id);
CREATE INDEX IF NOT EXISTS idx_relations_target ON relations(target_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_memory ON memory_relations(memory_id);
CREATE INDEX IF NOT EXISTS idx_memory_relations_pair ON memory_relations(source_id, target_id, relation);
CREATE INDEX IF NOT EXISTS idx_assets_type ON assets(type);
CREATE INDEX IF NOT EXISTS idx_assets_source_hash ON assets(source_hash);
CREATE INDEX IF NOT EXISTS idx_assets_project ON assets(project);
CREATE INDEX IF NOT EXISTS idx_assets_valid ON assets(valid);
CREATE INDEX IF NOT EXISTS idx_access_log_memory ON access_log(memory_id);
