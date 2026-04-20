# AI 侧集成指南

> 适用于任何支持 Shell、外部工具或工作流规则的 AI 助手。当前项目以 CLI、本地 SQLite、可读层和配套规则文档为准，不再维护旧的桥接式接入说明。

---

## 一、推荐接入方式

### 1. CLI 优先

当前仓库最稳定的接入方式是直接调用 [backend/cli.py](../backend/cli.py)。建议先在终端中验证以下命令：

```bash
cd backend
python cli.py working
python cli.py recall --query "关键词"
python cli.py stats
```

常用子命令：

- `working`：获取当前工作记忆，适合会话开始时注入上下文
- `remember`：写入新记忆
- `recall`：检索历史记忆
- `update`：补充正文、实体、标签或强度
- `forget`：删除记忆
- `asset-register` / `asset-lookup` / `asset-use` / `asset-invalidate`：管理可复用资产
- `rebuild-graph`：从现有记忆重建实体与关系图谱

### 2. 可读层兜底

如果 AI 助手无法直接执行 CLI，可以退回到可读层：

```text
~/.local/share/ai-memory/
├── readable/
│   ├── memories/
│   ├── assets/
│   └── entities/
├── INDEX.json
└── db/memory.db
```

这种方式适合只读检索、人工排查或在工具受限环境下做降级恢复。

### 3. 自定义工具封装

如果你的 AI 框架支持自定义 tool schema，可以把 CLI 子命令封装成自己的外部工具，但参数设计应以现有 CLI 为准，而不是另起一套命名。

---

## 二、AI 行为规范

以下内容适合写入 system prompt、rules、instructions 或 agent workflow。

### 2.1 会话开始

```text
会话开始时：
1. 执行 python cli.py working 获取工作记忆
2. 如果用户提到“继续”“上次”“之前”，优先执行 recall 检索相关历史
3. 如果用户正在某个固定项目中，检索时尽量补上 --project
```

### 2.2 何时记忆

| 触发场景 | 记忆类型 | 重要程度 |
|----------|----------|----------|
| 用户表达偏好、规则、禁用项 | procedural | high |
| 重要技术决策、根因分析、方案确认 | semantic | normal~high |
| 完成操作并有明确结果 | episodic | normal |
| 用户通过反馈工具补充关键事实 | 按内容判断 | normal~high |
| 会话结束前形成阶段总结 | episodic | normal |

不要记住临时试错过程、纯寒暄内容、未确认的推测，以及工作记忆里已有且没有变化的信息。

### 2.3 何时检索

| 触发场景 | 建议命令 |
|----------|----------|
| 用户提到之前讨论过的话题 | `python cli.py recall --query "关键词"` |
| 需要某个项目的历史结论 | `python cli.py recall --query "问题" --project "项目名"` |
| 需要用户偏好或长期规则 | `python cli.py recall --query "领域关键词" --type procedural` |
| 只想看最近若干条结果 | `python cli.py recall --query "关键词" --limit 5` |

### 2.4 资产复用

```text
执行操作前：
1. 先用 asset-lookup 查已有成果
2. 只复用 valid 为 true 的资产
3. 复用后可调用 asset-use 更新使用计数

执行操作后：
1. 对有复用价值的脚本、工具、报告、产物执行 asset-register
2. 如果确认资产已经失效，调用 asset-invalidate 标记原因
```

### 2.5 会话结束

```text
会话结束前：
1. 回顾本次会话的关键决策、验证结果和新增规则
2. 用 remember 写入 1 到 3 条会话摘要
3. 新的偏好或长期约束写入 procedural
4. 如有图谱相关内容，补齐 entities
```

### 2.6 结构化字段要求

为了让记忆可检索、可聚合、可进入图谱，建议写入时优先补齐以下字段：

| 字段 | 用途 | 建议 |
|----------|----------|----------|
| `summary` | 列表短标签 | 5 到 15 字，避免写成长段总结 |
| `content` | 完整正文 | 写清背景、证据、结论、动作 |
| `project` | 项目过滤 | 只填稳定项目名 |
| `entities` | 实体图谱输入 | 默认抽取 2 到 6 个稳定实体 |
| `tags` | 粗粒度筛选 | 使用短词，不写整句 |

`entities` 推荐优先级：

1. 项目名
2. 模块名
3. 组件名
4. 工具名
5. 框架名
6. 问题名、流程名或关键功能名

涉及架构设计、Bug 根因、页面改造、工具链、交互规则时，尽量不要省略 `entities`。

### 2.7 图谱相关逻辑

`entities` 不只是附加标签，它会直接影响图谱与关系层：

- 保存记忆后，实体会进入 `memory_entities`
- 多实体共现会成为关系候选
- 更新时追加或替换 `entities` 会影响后续聚合结果
- 大量历史记忆缺实体时，应考虑执行 `rebuild-graph`

推荐流程：

1. 新记忆尽量在写入时带上 `--entities`
2. 发现老记忆缺实体时，用 `update --entities` 或 `update --append-entities` 补齐
3. 批量补齐后，先执行 `python cli.py rebuild-graph --dry-run`
4. 预览无误后再执行正式重建

---

## 三、记忆类型说明

### 情景记忆（episodic）

- 存什么：会话里发生了什么、做了什么、结果如何
- 适用：阶段总结、验证记录、任务完成情况

### 语义记忆（semantic）

- 存什么：事实、知识、根因、技术方案、设计约束
- 适用：可复用结论、项目知识、架构说明

### 程序记忆（procedural）

- 存什么：偏好、规则、流程、禁用项、固定操作习惯
- 适用：长期有效的用户要求和工作方式

---

## 四、降级策略

### 级别 1：CLI 模式

- 直接调用 [backend/cli.py](../backend/cli.py)
- 适合 Cursor、Copilot、VS Code Agent 或其他支持终端的助手

### 级别 2：可读层模式

- 读取 `readable/` 与 `INDEX.json`
- 适合无法执行 Python 命令但仍需要检索上下文的场景

### 级别 3：人工确认模式

- 当自动化工具全部不可用时，由 AI 明确告知用户当前限制
- 让用户决定是否继续人工提供关键词、路径或已有记忆 ID

---

## 五、多 AI 助手适配

### Cursor

仓库内已有两份可直接迁移的材料：

- [docs/cursor-integration/ai-memory.mdc](cursor-integration/ai-memory.mdc)
- [docs/cursor-integration/SKILL.md](cursor-integration/SKILL.md)

推荐做法：先跑通 CLI，再部署规则与 Skill。

### GitHub Copilot / VS Code Agent

Copilot 没有与 Cursor 完全一致的 rules/skills 目录约定，但可以保留同一套行为原则：

- 把本文中的行为规范迁移到用户级或仓库级 instructions
- 把 CLI 约定整理成固定 prompt 模板或 task 模板
- 把 `entities`、摘要规范、资产复用顺序写进 agent 说明

适配重点：

1. 会话开始先执行 `working`
2. 重要信息落库时补齐 `entities`
3. 复用成果前先 `asset-lookup`
4. 批量补实体后按需执行 `rebuild-graph`

### 其他 Agent

无论是 OpenClaw、自定义脚本还是其他工作流引擎，建议都遵循同一套底层约束：

- 统一用 CLI 命令名表达操作
- 统一使用 `summary`、`content`、`project`、`entities`、`tags`
- 统一把“先检索、后操作、再沉淀摘要”作为标准流程

---

## 六、工作记忆建议格式

如果你的助手会把 `working` 结果整理后注入上下文，建议呈现为：

```markdown
## 用户偏好
- 语言：中文
- 输出风格：简洁

## 近期活动
- [2 小时前] 修复了图谱页高亮问题
- [昨天] 补齐 Qt 前端文档

## 活跃项目
- AI Memory
- 相关前端或子工具项目
```

这样可以减少用户重复描述上下文的成本。

---

## 七、最佳实践

1. 先验证 CLI，再写复杂工作流。
2. 结构化记忆优先，尤其不要漏掉 `entities`。
3. 复用成果前先查资产，避免重复劳动。
4. 阶段收尾时写 1 到 3 条高质量摘要，而不是一长串流水账。
5. 多 AI 助手可以分开承载规则，但底层命令和字段约束应保持一致。
