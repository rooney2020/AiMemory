# AI Memory Backend

AI Memory 的本地后端引擎，负责记忆存储、检索、资产管理和图谱重建。当前仓库里最稳定、可直接执行的入口是健康检查和 CLI；面向 AI Agent 的集成方式与行为约束放在根目录 `docs/` 中说明。

## 当前目录结构

```
backend/
├── cli.py                    # 命令行入口
├── config.yaml               # 本地配置
├── pyproject.toml            # 包定义与依赖
├── tests/                    # 后端测试
└── src/ai_memory/
    ├── __main__.py           # 健康检查入口
    ├── config.py             # 配置加载
    ├── core/                 # 记忆、实体、类型模型
    ├── storage/              # SQLite、Schema、MemoryStore、EntityStore
    ├── index/                # 全文、图谱、时间、融合检索
    ├── embedding/            # 本地嵌入模型适配
    ├── lifecycle/            # 衰减、固化、去重
    ├── readable/             # 可读层同步
    ├── asset/                # 资产注册与校验
    └── tools/
        └── graph_rebuild.py  # 基于现有记忆回抽实体并重建图谱
```

## 核心能力

- 三类记忆的本地 CRUD：会话摘要、笔记、偏好
- 工作记忆输出：偏好 + 最近活动
- 检索通道：全文、图谱、时间，以及可选向量检索
- 资产操作：注册、查询、标记使用、标记失效
- 实体增强：记忆可直接写入 `entities`，并支持追加实体
- 图谱重建：从历史记忆重新抽取实体与关系，刷新 `entities`、`memory_entities`、`relations`

## 安装

```bash
cd backend
pip install -e .
```

如需启用向量检索或开发依赖：

```bash
pip install -e ".[vector]"
pip install -e ".[dev]"
pip install -e ".[all]"
```

## 入口说明

### 健康检查

```bash
cd backend
python -m ai_memory --check
```

这个入口会检查配置、初始化数据库并输出当前统计信息。

### CLI 子命令

```bash
cd backend
python cli.py --help
```

常用子命令如下：

| 子命令 | 说明 |
| --- | --- |
| `working` | 输出工作记忆，包含偏好与近期活动 |
| `remember` | 创建记忆，支持类型、摘要、项目、实体、标签 |
| `recall` | 检索记忆，优先走融合检索，失败时回退到存储层 |
| `update` | 更新摘要、正文、强度、标签和实体，支持追加模式 |
| `forget` | 删除记忆 |
| `link` | 建立实体关系 |
| `stats` | 输出系统统计 |
| `asset-register` | 注册资产 |
| `asset-lookup` | 查找资产 |
| `asset-use` | 记录一次资产使用 |
| `asset-invalidate` | 标记资产失效 |
| `rebuild-graph` | 从现有记忆回抽实体并重建关系图谱 |

### 更新命令的增强参数

`update` 当前支持的重点参数：

- `--append`：正文追加而不是替换
- `--strength`：更新强度，范围 `0.0~10.0`
- `--entities`：替换实体列表
- `--append-entities`：向现有实体列表追加实体
- `--tags`：替换标签列表
- `--append-tags`：追加标签列表

### 图谱重建命令

```bash
cd backend
python cli.py rebuild-graph --dry-run
python cli.py rebuild-graph --include-archived
```

这个命令适合在你批量补全了历史记忆、实体或标签之后运行，用于把旧数据重新同步到实体与关系图谱里。

## 配置

配置文件位于 `backend/config.yaml`。常见配置关注点：

- 数据库路径
- 嵌入模型与设备
- 检索返回数量
- 衰减策略与核心阈值
- 可读层输出路径

如果你要把前端和后端接到同一个数据库，优先保持数据库路径一致。

## 测试

```bash
cd backend
pytest tests -v
```

当前测试覆盖存储、索引、向量检索、资产操作和图谱重建等核心路径。文档中不再写死测试条数，避免后续变更后 README 再次过期。

## 说明

- `pyproject.toml` 暴露的 `ai-memory` 是 CLI 入口，不是健康检查入口。
- 健康检查入口仍然是 `python -m ai_memory --check`。
- 根目录 `docs/AI_INTEGRATION.md` 描述的是 AI 侧接入方式与约束，当前推荐入口仍然是本目录下的 CLI 与健康检查命令。
