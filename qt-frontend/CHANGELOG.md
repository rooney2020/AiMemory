# Changelog

本文件记录 AI Memory Manager Qt Frontend 的所有版本变更。

格式遵循 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.1.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [0.1.0] - 2026-04-09

### 新增
- 会话记录浏览：支持 Cursor、OpenClaw、Toder、Copilot 四种框架的会话扫描与展示
- 记忆管理：会话摘要（episodic）、笔记（semantic）、偏好（procedural）三种类型的增删改查
- 资产管理：资产注册、查看、搜索、有效性检测
- 全局搜索：跨记忆和会话的关键词搜索，支持搜索结果高亮与导航
- 知识图谱：自动提取实体和关系，可视化展示知识网络
- 数据分析：记忆类型分布、时间趋势、实体频率等图表
- 导出功能：支持 JSON、Markdown、HTML、ZIP 多种格式导出
- 导入功能：支持从 JSON ZIP 文件导入记忆和资产数据
- 会话对比：两个会话的并排对比查看
- 会话收藏：收藏重要会话并快速筛选
- 批量操作：多选记忆后批量打标签、归档
- 系统托盘：最小化到托盘，右键菜单支持显示/退出
- 单实例运行：文件锁保证全局只有一个进程
- 进程标识：使用 setproctitle 设置可识别的进程名

### 技术细节
- 基于 PyQt5 构建，使用 Catppuccin Mocha 主题
- 模块化架构：tabs/ 按 Tab 页拆分，components/ 存放可复用组件
- 后台线程处理耗时操作（会话扫描、消息加载），避免 UI 卡顿
- Markdown 渲染支持代码高亮、表格、换行等扩展
