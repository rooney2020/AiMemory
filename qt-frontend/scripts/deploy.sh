#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"
BACKEND_DIR="$(dirname "$PROJECT_DIR")/backend"
VENV_DIR="$PROJECT_DIR/venv"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[INFO]${NC} $*"; }
warn()  { echo -e "${YELLOW}[WARN]${NC} $*"; }
error() { echo -e "${RED}[ERROR]${NC} $*"; exit 1; }

info "=== AI Memory Manager 一键部署 ==="
info "前端目录: $PROJECT_DIR"
info "后端目录: $BACKEND_DIR"

PYTHON=""
for cmd in python3.12 python3.11 python3.10 python3; do
    if command -v "$cmd" &>/dev/null; then
        ver=$("$cmd" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')")
        major=$(echo "$ver" | cut -d. -f1)
        minor=$(echo "$ver" | cut -d. -f2)
        if [ "$major" -ge 3 ] && [ "$minor" -ge 10 ]; then
            PYTHON="$cmd"
            info "Python: $PYTHON ($ver)"
            break
        fi
    fi
done
[ -z "$PYTHON" ] && error "未找到 Python 3.10+，请先安装"

if [ "$(uname)" = "Linux" ]; then
    info "检查 Linux 系统依赖..."
    missing=()
    for pkg in python3-venv; do
        if ! dpkg -l "$pkg" &>/dev/null 2>&1; then
            missing+=("$pkg")
        fi
    done
    if [ ${#missing[@]} -gt 0 ]; then
        warn "缺少系统包: ${missing[*]}"
        info "尝试安装..."
        sudo apt-get install -y "${missing[@]}" || warn "安装失败，请手动安装: sudo apt-get install -y ${missing[*]}"
    fi
fi

if [ ! -d "$VENV_DIR" ]; then
    info "创建虚拟环境: $VENV_DIR"
    "$PYTHON" -m venv "$VENV_DIR"
else
    info "虚拟环境已存在: $VENV_DIR"
fi

source "$VENV_DIR/bin/activate"
info "已激活虚拟环境"

info "升级 pip..."
pip install --upgrade pip -q

if [ -d "$BACKEND_DIR" ]; then
    info "安装后端 (ai-memory)..."
    pip install -e "$BACKEND_DIR" -q 2>/dev/null || warn "后端安装失败"
    info "向量检索依赖为可选，跳过（如需安装: pip install -e '$BACKEND_DIR[vector]'）"
else
    warn "后端目录不存在: $BACKEND_DIR，跳过后端安装"
fi

info "安装前端依赖..."
pip install -r "$PROJECT_DIR/requirements.txt" -q 2>/dev/null || warn "部分依赖安装失败"

info "验证安装..."
"$VENV_DIR/bin/python" -c "
import PyQt5
print('  PyQt5:', PyQt5.QtCore.PYQT_VERSION_STR)
try:
    import ai_memory
    print('  ai-memory: OK')
except ImportError:
    print('  ai-memory: 未安装（需手动安装后端）')
" 2>/dev/null || warn "验证跳过"

LAUNCHER="$PROJECT_DIR/run.sh"
cat > "$LAUNCHER" << 'LAUNCHER_EOF'
#!/usr/bin/env bash
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
source "$SCRIPT_DIR/venv/bin/activate"
cd "$SCRIPT_DIR"
python main.py "$@"
LAUNCHER_EOF
chmod +x "$LAUNCHER"
info "启动脚本: $LAUNCHER"

ICON_SVG="$PROJECT_DIR/memory_qt/resources/icon.svg"
ICON_PNG="$PROJECT_DIR/memory_qt/resources/icon.png"
if [ -f "$ICON_SVG" ] && [ ! -f "$ICON_PNG" ]; then
    info "生成 PNG 图标..."
    "$VENV_DIR/bin/python" -c "
import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QPixmap, QPainter
from PyQt5.QtSvg import QSvgRenderer
from PyQt5.QtCore import QSize, Qt
app = QApplication(sys.argv)
r = QSvgRenderer('$ICON_SVG')
for size in [256, 128, 64, 48]:
    p = QPixmap(QSize(size, size))
    p.fill(Qt.transparent)
    painter = QPainter(p)
    r.render(painter)
    painter.end()
    if size == 256:
        p.save('$ICON_PNG')
    p.save('${PROJECT_DIR}/memory_qt/resources/icon-' + str(size) + '.png')
print('PNG icons generated')
" 2>/dev/null || warn "PNG 图标生成失败（不影响使用）"
fi

ICON_PATH="$ICON_PNG"
[ ! -f "$ICON_PATH" ] && ICON_PATH="$ICON_SVG"

if [ "$(uname)" = "Linux" ]; then
    APP_DIR="$HOME/.local/share/applications"
    mkdir -p "$APP_DIR"
    DESKTOP_FILE="$APP_DIR/ai-memory-manager.desktop"
    cat > "$DESKTOP_FILE" << EOF
[Desktop Entry]
Type=Application
Name=AI Memory Manager
Comment=AI 记忆系统可视化管理工具
Exec=$LAUNCHER
Icon=$ICON_PATH
Terminal=false
Categories=Development;Utility;
StartupWMClass=AI Memory Manager
EOF
    chmod +x "$DESKTOP_FILE"
    info "应用快捷方式: $DESKTOP_FILE"

    if [ -d "$HOME/Desktop" ]; then
        cp "$DESKTOP_FILE" "$HOME/Desktop/ai-memory-manager.desktop"
        chmod +x "$HOME/Desktop/ai-memory-manager.desktop"
        info "桌面快捷方式: $HOME/Desktop/ai-memory-manager.desktop"
    fi

    update-desktop-database "$APP_DIR" 2>/dev/null || true
    info "应用列表已更新"
fi

COMMAND_NAME="ai-memory-qt"
BIN_DIR="$HOME/.local/bin"
mkdir -p "$BIN_DIR"
ln -sf "$LAUNCHER" "$BIN_DIR/$COMMAND_NAME"
info "命令行启动: $COMMAND_NAME"

if [[ ":$PATH:" != *":$BIN_DIR:"* ]]; then
    warn "$BIN_DIR 不在 PATH 中，请添加到 ~/.bashrc: export PATH=\"\$HOME/.local/bin:\$PATH\""
fi

echo ""
info "=== 部署完成 ==="
info "启动方式:"
info "  1. 应用列表搜索 'AI Memory Manager'"
info "  2. 命令行: $COMMAND_NAME"
info "  3. 直接运行: $LAUNCHER"
echo ""
