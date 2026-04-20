# AI Memory Manager — Qt 可视化前端

AI 记忆系统的桌面可视化管理工具，基于 PyQt5 构建，当前采用“科技清爽情报台”工作台布局和三态主题切换。

## 功能概览

| Tab | 功能 | 说明 |
|-----|------|------|
| 总览 | 统计仪表盘 | 记忆数量、类型分布、强度分布、最近活动 |
| 会话摘要 | 事件时间线 | 按日期浏览会话摘要记忆，详情面板，支持编辑/删除 |
| 笔记 | 知识库 | 按项目分组，支持编辑/删除 |
| 偏好 | 用户偏好 | 偏好与规则列表，按强度排序 |
| 资产 | 资产复用库 | 搜索/验证/打开目录，一键管理可复用成果物 |
| 图谱 | 实体关系图 | 交互式力导向图：缩放、点击节点查看关联记忆，连线显示关系标签 |
| 会话记录 | AI 框架会话 | 浏览 Cursor/OpenClaw/Toder 等 AI 框架的原始会话记录 |
| 搜索 | 全局搜索 | 多通道融合检索（FTS + 向量 + 图谱 + 时间）+ 会话记录全文搜索 |

### 当前界面重点

- **工作台壳层**：左侧导航、顶部命令条、中央工作区、右侧阅读区
- **会话记录浏览**：支持多框架切换，按最近活跃排序，并支持收藏、对比、工具消息过滤
- **融合搜索**：搜索结果同时展示记忆与会话，并支持高亮与定位
- **批量操作**：会话摘要、笔记、偏好支持多选与批量处理
- **图谱阅读**：实体关系图支持查看节点、关系和关联记忆

## 主题支持

支持 3 种主题，可在界面顶部实时切换，所有组件（包括图谱、表格、卡片）均跟随主题变化：

- **科技清爽·夜航**（默认）— 深色情报台
- **科技清爽·晴空** — 亮色工作台
- **科技清爽·薄雾** — 低对比雾面工作台

这些主题不是简单换色，而是统一影响工作台壳层、卡片、图谱、详情阅读区和顶部命令条。

## 环境要求

- Python 3.10+
- PyQt5 >= 5.15
- ai-memory 后端（本项目 `../backend/`）
- 操作系统：Ubuntu 20.04+ / Windows 10+ / macOS 12+

Linux 备注：前端入口默认优先使用项目环境内的 ibus Qt 输入法插件，避免系统 fcitx Qt 插件与 venv 中的 Qt 版本冲突。

## 安装与运行

### 方式一：手动安装

```bash
# 1. 安装后端
cd ../backend
pip install -e .

# 2. 安装前端依赖
cd ../qt-frontend
pip install -r requirements.txt

# 3. 运行
python3 main.py
```

如果你在 Linux 上遇到 Qt 插件冲突，优先使用：

```bash
./run.sh
```

### 方式二：一键部署脚本

```bash
# Ubuntu / macOS
chmod +x scripts/deploy.sh
./scripts/deploy.sh

# Windows (PowerShell)
.\scripts\deploy.ps1
```

详见 [DEPLOY.md](DEPLOY.md)

## 命令行参数

| 参数 | 说明 | 默认值 |
|------|------|--------|
| `--db <path>` | 指定数据库路径 | `~/.local/share/ai-memory/db/memory.db` |

```bash
# 使用自定义数据库
python3 main.py --db /path/to/memory.db
```

## 项目结构

```
qt-frontend/
├── main.py                  # 入口
├── run.sh                   # Linux 启动脚本（自动处理 QT_IM_MODULE）
├── requirements.txt         # Python 依赖
├── DEPLOY.md                # 安装部署文档
├── scripts/
│   ├── deploy.sh            # Ubuntu/macOS 一键部署
│   └── deploy.ps1           # Windows 一键部署
├── memory_qt/
│   ├── bootstrap.py         # Qt 运行时环境引导
│   ├── constants.py         # 主题色彩字典、全局配置
│   ├── theme.py             # QPalette + QSS 样式函数
│   ├── app.py               # QApplication 初始化（Fusion 风格）
│   ├── main_window.py       # 主窗口 + 左导航工作台壳层 + 顶部命令条
│   ├── data_bridge.py       # ai_memory 数据层封装
│   ├── import_handler.py    # 导入处理
│   ├── resources/           # 程序图标与静态资源
│   ├── components/
│   │   ├── search_bar.py    # 全局搜索栏
│   │   ├── stat_card.py     # 统计卡片（悬浮阴影效果）
│   │   ├── memory_card.py   # 记忆卡片
│   │   └── detail_panel.py  # 详情面板（HTML 渲染 + 自定义链接处理）
│   ├── sessions/            # AI 会话记录解析
│   │   ├── models.py        # 数据模型（FrameworkType, SessionInfo, Message）
│   │   ├── scanner.py       # 会话扫描器（异步检测 + 加载）
│   │   └── parsers/         # 框架解析器
│   │       ├── base.py      # 解析器基类
│   │       ├── cursor.py    # Cursor IDE 会话解析
│   │       ├── copilot.py   # GitHub Copilot 会话解析
│   │       ├── openclaw.py  # OpenClaw 会话解析（JSONL 格式）
│   │       └── toder.py     # Toder 会话解析
│   └── tabs/
│       ├── overview_tab.py  # 总览 Tab
│       ├── episodic_tab.py  # 会话摘要 Tab
│       ├── semantic_tab.py  # 笔记 Tab
│       ├── procedural_tab.py # 偏好 Tab（含 EditDialog 强度滑块）
│       ├── asset_tab.py     # 资产管理 Tab
│       ├── graph_tab.py     # 实体图谱 Tab（交互式力导向图 + 关系标签）
│       ├── session_tab.py   # 会话记录 Tab（多框架浏览）
│       ├── session_workers.py # 会话加载后台线程
│       └── search_tab.py    # 全局搜索 Tab（含会话记录搜索）
├── assets/                  # 图标资源与外层静态文件
└── tests/                   # 单元测试
```

## 技术实现

- **样式系统**：全局 QPalette + 组件级 QSS，围绕工作台壳层和三态主题统一控制
- **主窗口结构**：左导航 + 顶部命令条 + 右侧阅读区，不再使用旧的顶部 Tab 主布局
- **图谱可视化**：QGraphicsScene + 自定义视图缩放与节点交互
- **会话处理**：后台线程扫描与加载，支持多框架解析、内容搜索、对比阅读
- **链接处理**：QTextBrowser 自定义 `anchorClicked`，支持 http/https 与本地文件
- **数据桥接**：`DataBridge` 封装后端调用，前端不直接操作底层存储细节

## 更新记录

### v0.3.0 (2026-04-02)

- 新增「会话记录」Tab：多框架会话浏览（Cursor / OpenClaw / Toder）
- 新增 OpenClaw 解析器（JSONL 格式）
- 全局搜索增加会话记录搜索
- 编辑对话框增加强度调整滑块
- UI 全中文化（类型标签、角色标签、Tab 名称）
- 图谱修复（节点创建 + 关系标签）
- 工具结果默认折叠，滚动自动加载

### 当前补充说明

- 当前工作台主视觉已经切换为“科技清爽情报台”，旧 Catppuccin 主题描述不再适用于主界面现状
- 会话记录支持范围已扩展到 Copilot
- Linux 启动默认优先规避 fcitx Qt 插件冲突，推荐使用 `run.sh`
