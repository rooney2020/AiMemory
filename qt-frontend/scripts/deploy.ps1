#Requires -Version 5.1
<#
.SYNOPSIS
    AI Memory Manager 一键部署脚本 (Windows)
.DESCRIPTION
    自动创建虚拟环境、安装依赖、生成桌面快捷方式
#>

$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$ProjectDir = Split-Path -Parent $ScriptDir
$BackendDir = Join-Path (Split-Path -Parent $ProjectDir) "backend"
$VenvDir = Join-Path $ProjectDir "venv"

function Write-Info($msg) { Write-Host "[INFO] $msg" -ForegroundColor Green }
function Write-Warn($msg) { Write-Host "[WARN] $msg" -ForegroundColor Yellow }
function Write-Err($msg) { Write-Host "[ERROR] $msg" -ForegroundColor Red; exit 1 }

Write-Info "=== AI Memory Manager 一键部署 ==="
Write-Info "前端目录: $ProjectDir"
Write-Info "后端目录: $BackendDir"

$Python = $null
foreach ($cmd in @("python3", "python")) {
    try {
        $ver = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')" 2>$null
        if ($ver) {
            $parts = $ver.Split(".")
            if ([int]$parts[0] -ge 3 -and [int]$parts[1] -ge 10) {
                $Python = $cmd
                Write-Info "Python: $Python ($ver)"
                break
            }
        }
    } catch {}
}
if (-not $Python) { Write-Err "未找到 Python 3.10+，请先安装" }

if (-not (Test-Path $VenvDir)) {
    Write-Info "创建虚拟环境: $VenvDir"
    & $Python -m venv $VenvDir
} else {
    Write-Info "虚拟环境已存在: $VenvDir"
}

$ActivateScript = Join-Path $VenvDir "Scripts\Activate.ps1"
. $ActivateScript
Write-Info "已激活虚拟环境"

Write-Info "升级 pip..."
pip install --upgrade pip -q

if (Test-Path $BackendDir) {
    Write-Info "安装后端 (ai-memory)..."
    pip install -e $BackendDir -q
    try {
        pip install -e "$BackendDir[vector]" -q
    } catch {
        Write-Warn "向量检索依赖安装失败（可选功能）"
    }
} else {
    Write-Warn "后端目录不存在: $BackendDir，跳过后端安装"
}

Write-Info "安装前端依赖..."
pip install PyQt5 -q

Write-Info "验证安装..."
& "$VenvDir\Scripts\python.exe" -c @"
import PyQt5
print('  PyQt5:', PyQt5.QtCore.PYQT_VERSION_STR)
try:
    import ai_memory
    print('  ai-memory: OK')
except ImportError:
    print('  ai-memory: 未安装')
"@

$LauncherBat = Join-Path $ProjectDir "run.bat"
@"
@echo off
call "$VenvDir\Scripts\activate.bat"
cd /d "$ProjectDir"
python main.py %*
"@ | Set-Content $LauncherBat -Encoding ASCII
Write-Info "启动脚本: $LauncherBat"

$DesktopPath = [Environment]::GetFolderPath("Desktop")
if (Test-Path $DesktopPath) {
    $ShortcutPath = Join-Path $DesktopPath "AI Memory Manager.lnk"
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = $LauncherBat
    $Shortcut.WorkingDirectory = $ProjectDir
    $Shortcut.Description = "AI 记忆系统可视化管理工具"
    $Shortcut.Save()
    Write-Info "桌面快捷方式: $ShortcutPath"
}

Write-Host ""
Write-Info "=== 部署完成 ==="
Write-Info "运行方式:"
Write-Info "  1. 双击 $LauncherBat"
Write-Info "  2. cd $ProjectDir && .\venv\Scripts\Activate && python main.py"
Write-Host ""
