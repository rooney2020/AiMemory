# AI 记忆系统 — CLI 操作指南

通过命令行操作记忆系统。所有操作通过 Shell 执行 Python CLI 脚本完成。

## CLI 路径

```
CLI=/home/tsdl/ssd/temp/projects/AI/AiMemory/backend/cli.py
```

所有命令格式：`python3 $CLI <子命令> [参数]`

## 命令速查

### 获取工作记忆（会话开始时调用）

```bash
python3 $CLI working
```

返回 JSON：`preferences`（用户偏好列表）+ `recent_activity`（最近活动）

### 存储记忆

```bash
python3 $CLI remember \
  --content "记忆内容" \
  --type episodic \
  --importance high \
  --summary "简短摘要" \
  --project "项目名" \
  --entities "实体1,实体2" \
  --tags "标签1,标签2"
```

参数：
- `--type`：`episodic`（事件）| `semantic`（知识）| `procedural`（偏好）
- `--importance`：`low` | `normal`（默认）| `high` | `critical`
- `--summary`：简短标签（5-15字）
- `--project`：项目名（可选）
- `--entities`：逗号分隔的实体列表（可选）
- `--tags`：逗号分隔的标签列表（可选）

### 检索记忆

```bash
python3 $CLI recall --query "搜索关键词" --type episodic --project "项目名" --limit 5
```

参数：
- `--query`：搜索关键词（必需）
- `--type`：记忆类型（可选）
- `--project`：项目名过滤（可选）
- `--limit`：返回数量限制（可选）

### 更新记忆

```bash
# 替换内容
python3 $CLI update --id "记忆ID" --content "新内容" --summary "新摘要"

# 追加内容
python3 $CLI update --id "记忆ID" --content "追加的内容" --append

# 更新强度
python3 $CLI update --id "记忆ID" --strength 8.5

# 替换实体
python3 $CLI update --id "记忆ID" --entities "实体1,实体2"

# 追加实体
python3 $CLI update --id "记忆ID" --entities "新增实体" --append-entities

# 更新标签
python3 $CLI update --id "记忆ID" --tags "新标签1,新标签2"

# 追加标签
python3 $CLI update --id "记忆ID" --tags "额外标签" --append-tags
```

参数：
- `--id`：记忆 ID（必需）
- `--content`：新内容（可选）
- `--summary`：新摘要（可选）
- `--strength`：强度值 0.0~10.0（可选）
- `--append`：追加内容而非替换（可选）
- `--entities`：实体，逗号分隔（可选）
- `--append-entities`：追加实体而非替换（可选）
- `--tags`：标签，逗号分隔（可选）
- `--append-tags`：追加标签而非替换（可选）

### 删除记忆

```bash
python3 $CLI forget --id "记忆ID"
```

### 建立实体关联

```bash
python3 $CLI link --source "实体A" --target "实体B" --relation "关系描述"
```

### 资产操作

```bash
# 注册
python3 $CLI asset-register \
  --name "名称" \
  --type script \
  --path "/路径" \
  --source-path "/源码路径" \
  --description "描述" \
  --tags "标签1,标签2" \
  --project "项目"

# 查找
python3 $CLI asset-lookup --query "关键词" --type app --project "项目" --tags "标签"

# 标记使用
python3 $CLI asset-use --id "资产ID"

# 标记失效
python3 $CLI asset-invalidate --id "资产ID" --reason "原因"
```

资产类型：`app` | `script` | `tool` | `data` | `document` | `config`

参数说明：
- `--path`：资产路径（必需）
- `--source-path`：源码路径（可选）
- `--tags`：逗号分隔的标签（可选）
- `--project`：项目名（可选）

### 系统统计

```bash
python3 $CLI stats
```

### 图谱重建

```bash
# 仅预览
python3 $CLI rebuild-graph --dry-run

# 正式重建
python3 $CLI rebuild-graph

# 包含已归档记忆
python3 $CLI rebuild-graph --include-archived
```

---

## 使用时机

按照 `ai-memory.mdc` 规则中的指引决定何时调用上述命令。

### 会话生命周期

| 时机 | 操作 |
|---|---|
| 会话开始 | `working` + `recall`（相关主题） |
| 每轮对话后 | 检查是否需要 `remember`（见下方清单） |
| 完成阶段性工作 | `remember --type episodic` |
| 会话结束前 | `remember --type episodic`（会话摘要） |

### 每轮对话后的记忆检查清单（重要！）

**不要等到会话结束才保存记忆——会话随时可能中断。** 每次收到用户回复（包括 feedback 工具）后，检查以下项目：

- [ ] 用户是否表达了新偏好/习惯？ → `remember --type procedural --importance high`
- [ ] 是否做出了重要技术决策？ → `remember --type semantic --importance high`
- [ ] 是否发现了新的技术知识/规律？ → `remember --type semantic`
- [ ] 是否完成了一个功能开发/Bug修复？ → `remember --type episodic`
- [ ] 用户是否提供了重要的项目信息？ → `remember --type episodic`

如果以上任一项为"是"，立即保存，不要推迟。

### 实体抽取要求

当准备记录重要记忆时，优先判断是否需要同时写入 `entities`：

- 技术方案、Bug 根因、模块改造、架构讨论：默认抽取 2 到 6 个稳定实体
- 实体优先级：项目名、模块名、组件名、工具名、框架名、关键功能名
- 纯流程性提醒、纯礼貌对话、无明确对象的简单状态同步：可以不传 `entities`
- 需要补齐老记忆实体时，优先使用 `update --entities` 或 `--append-entities`
- 大量补齐实体后，可考虑执行 `rebuild-graph` 同步图谱

### 检索时机

- **需要技术方案** → `recall --type semantic`
- **不确定偏好** → `recall --type procedural`
- **创建新资产前** → `asset-lookup`
- **复用已有成果** → `asset-lookup`

---

## 常用组合示例

### 记录会话摘要

```bash
python3 $CLI remember \
  --type episodic \
  --summary "AI Memory 搜索高亮实现" \
  --content "在 Qt 前端实现搜索结果高亮：
1. _highlight_html() 返回 (HTML, match_count)
2. 每个匹配添加唯一 ID 用于导航
3. 导航栏显示当前/总数
4. 智能截断：关键词位置±750字符

修改文件：search_tab.py, detail_panel.py" \
  --importance high \
  --entities "AI Memory,Qt,search_tab,detail_panel" \
  --tags "AI Memory,Qt,搜索"
```

### 追加更新已有记录

```bash
# 首次记录
python3 $CLI remember --type procedural --summary "UI 风格偏好" --content "暗色主题" --tags "UI,主题"

# 后续追加（使用 update --append）
python3 $CLI update --id <ID> --content "\n- 新增偏好：图标用 SVG" --append
python3 $CLI update --id <ID> --tags "图标" --append-tags
```

### 按项目检索

```bash
python3 $CLI recall --query "bug" --project "CopilotBar" --limit 10
```

### 按标签检索资产

```bash
python3 $CLI asset-lookup --tags "反编译,APK"
```

---

## 注意事项

- 所有输出为 JSON 格式
- `--content` 参数中如有特殊字符（引号、换行等），使用 heredoc 或转义
- CLI 直接操作 SQLite 数据库，无需额外桥接层，执行链路更直接
- **记忆保存的及时性比完整性更重要**：宁可多存几条简短记忆，也不要因等待"完美时机"而丢失所有记忆
- **summary 是标签不是摘要**：简短（5-15字），详细内容放 content
- **同一主题用 `--append` 更新**，避免碎片化

---

## 数据库路径

- **默认**：`~/.local/share/ai-memory/db/memory.db`
