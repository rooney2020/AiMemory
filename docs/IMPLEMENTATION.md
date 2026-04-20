# AI Memory 实现总览

> 本文档描述当前仓库中已经存在的主要实现入口与模块职责。早期未落地的旧结构和旧接入方式已移除。

---

## 一、当前目录结构

```text
AI/AiMemory/
├── README.md
├── backend/
│   ├── cli.py
│   ├── pyproject.toml
│   ├── config.yaml
│   ├── src/ai_memory/
│   │   ├── __main__.py
│   │   ├── cli.py
│   │   ├── config.py
│   │   ├── core/
│   │   ├── storage/
│   │   ├── index/
│   │   ├── lifecycle/
│   │   ├── readable/
│   │   ├── asset/
│   │   └── tools/
│   └── tests/
├── docs/
└── qt-frontend/
```

---

## 二、实际入口

### 1. 健康检查

```bash
cd backend
python -m ai_memory --check
```

用途：

- 验证配置与数据库是否可用
- 输出基础统计信息
- 用于快速排查环境问题

### 2. 实际操作 CLI

```bash
cd backend
python cli.py --help
```

这是当前项目面向 AI 助手和终端用户的主要入口。

### 3. Qt 前端

Qt 工作台位于 `qt-frontend/`，用于人工浏览、搜索、管理记忆与会话记录。

---

## 三、后端模块职责

| 模块 | 作用 |
|---|---|
| `core/` | 记忆、类型与基础数据模型 |
| `storage/` | SQLite 连接、表结构、记忆与实体持久化 |
| `index/` | 全文、图谱、时间等检索相关逻辑 |
| `lifecycle/` | 去重、强化、衰减等生命周期逻辑 |
| `readable/` | 可读层同步与降级浏览支持 |
| `asset/` | 资产注册、查找、失效标记、哈希计算 |
| `tools/` | 图谱重建等辅助逻辑 |

---

## 四、CLI 子命令

当前主要子命令包括：

- `working`
- `remember`
- `recall`
- `update`
- `forget`
- `link`
- `asset-register`
- `asset-lookup`
- `asset-use`
- `asset-invalidate`
- `stats`
- `rebuild-graph`

说明：

1. `working` 适合会话开始时提取工作记忆。
2. `remember` 与 `update` 是落库主路径。
3. `asset-*` 用于可复用成果管理。
4. `rebuild-graph` 用于从已有记忆重建实体和关系。

---

## 五、当前实现特征

### 1. 结构化记忆

当前实现支持在记忆层携带 `summary`、`project`、`entities`、`tags` 等信息，便于：

- 检索过滤
- 图谱构建
- 工作记忆压缩
- 规则与前端展示

### 2. 图谱增强

图谱重建逻辑位于 `tools/graph_rebuild.py`，它会：

- 扫描现有记忆
- 抽取或补齐实体
- 重建实体关联和关系表
- 输出预览或正式重建统计

### 3. 资产闭环

资产实现位于 `asset/registry.py`，当前提供：

- 注册资产
- 按项目、标签、关键词查找资产
- 标记使用次数
- 标记失效原因

### 4. 降级可读层

数据库之外仍保留可读层，便于：

- 手动浏览
- 在工具不可用时继续访问记忆
- 快速核对数据是否已落盘

---

## 六、建议阅读顺序

1. 先看根 README 了解仓库角色划分。
2. 再看 backend/README.md 了解命令入口和运行方式。
3. 再看 docs/AI_INTEGRATION.md 了解 AI 助手应如何接入。
4. 如果需要规则迁移，再看 docs/cursor-integration/。

---

## 七、维护原则

当代码入口、目录结构或命令发生变化时，应优先更新本文件和相关 README，避免文档再次落回“旧结构还在、当前实现已经变了”的状态。
