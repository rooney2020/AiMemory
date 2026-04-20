# 安装部署指南

## 环境要求

| 项目 | 最低版本 |
|------|----------|
| Python | 3.10+ |
| pip | 22.0+ |
| 操作系统 | Ubuntu 20.04+ / Windows 10+ / macOS 12+ |

### Linux 额外依赖

Ubuntu/Debian 系统需要安装 Qt 运行库：

```bash
sudo apt-get install -y python3-pyqt5 libxcb-xinerama0 libxkbcommon-x11-0
```

### macOS 额外说明

macOS 下 PyQt5 通过 pip 安装即可，无需额外系统依赖。

### Windows 额外说明

Windows 下 PyQt5 通过 pip 安装即可。建议使用 Python 官方安装器，勾选 "Add Python to PATH"。

---

## 手动安装

### 1. 安装后端（ai-memory）

```bash
cd backend
pip install -e .

# 如需向量检索功能
pip install -e ".[vector]"

# 安装所有可选依赖
pip install -e ".[all]"
```

### 2. 安装前端依赖

```bash
cd qt-frontend
pip install -r requirements.txt
```

### 3. 初始化数据库

```bash
python -m ai_memory --check
```

### 4. 运行前端

```bash
cd qt-frontend
python3 main.py
```

---

## 一键部署

### Ubuntu / macOS

```bash
cd qt-frontend
chmod +x scripts/deploy.sh
./scripts/deploy.sh
```

脚本会自动：
1. 检测 Python 版本
2. 创建虚拟环境（`venv/`）
3. 安装后端和前端依赖
4. 初始化数据库
5. 创建桌面快捷方式（Ubuntu）/ 启动脚本（macOS）

### Windows (PowerShell)

```powershell
cd qt-frontend
.\scripts\deploy.ps1
```

脚本会自动：
1. 检测 Python 版本
2. 创建虚拟环境（`venv\`）
3. 安装后端和前端依赖
4. 初始化数据库
5. 创建桌面快捷方式

---

## 虚拟环境管理

部署脚本默认在 `qt-frontend/venv/` 创建虚拟环境。手动使用：

```bash
# 激活虚拟环境
source venv/bin/activate  # Linux/macOS
.\venv\Scripts\Activate    # Windows

# 运行
python main.py

# 退出虚拟环境
deactivate
```

---

## 配置

### 数据库路径

默认路径：`~/.local/share/ai-memory/db/memory.db`

通过命令行参数指定：

```bash
python3 main.py --db /custom/path/memory.db
```

### 后端配置

后端配置文件：`backend/config.yaml`

```yaml
database:
  path: ~/.local/share/ai-memory/db/memory.db

embedding:
  model: all-MiniLM-L6-v2    # 或 bge-small-zh（中文优化）
  device: cpu

readable:
  enabled: true
  path: ~/.local/share/ai-memory/readable/
```

---

## 故障排除

### Qt 平台插件错误

```
qt.qpa.plugin: Could not find the Qt platform plugin "xcb"
```

解决：安装 Qt 运行库

```bash
sudo apt-get install -y libxcb-xinerama0 libxkbcommon-x11-0
```

### 数据库锁定

如果提示数据库被锁定，确保没有其他进程正在使用同一个数据库文件。MCP Server 和 QT 前端可以同时访问同一数据库（SQLite WAL 模式）。

### Python 版本不匹配

确保使用 Python 3.10+：

```bash
python3 --version
```

如系统默认 Python 版本过低，可使用 pyenv 或 conda 管理 Python 版本。
