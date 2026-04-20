#!/usr/bin/env python3
"""AI Memory Manager — Qt Frontend"""

import fcntl
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

_LOCK_FILE = Path.home() / ".cache" / "ai-memory-manager.lock"


def _acquire_lock():
    """单实例锁：保证全局只有一个进程"""
    _LOCK_FILE.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(_LOCK_FILE), os.O_CREAT | os.O_RDWR)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except (IOError, OSError):
        with open(str(_LOCK_FILE), "r") as f:
            pid = f.read().strip()
        if pid:
            try:
                os.kill(int(pid), signal.SIGUSR1)
            except (ProcessLookupError, ValueError):
                pass
        print(f"AI Memory Manager 已在运行 (PID {pid})，已发送前台信号", file=sys.stderr)
        sys.exit(0)
    os.ftruncate(fd, 0)
    os.write(fd, str(os.getpid()).encode())
    return fd


def main():
    try:
        from setproctitle import setproctitle
        setproctitle("AI Memory Manager")
    except ImportError:
        pass

    lock_fd = _acquire_lock()

    db_path = None
    for i, arg in enumerate(sys.argv[1:], 1):
        if arg == "--db" and i < len(sys.argv) - 1:
            db_path = sys.argv[i + 1]

    qt_im_module = os.environ.get("QT_IM_MODULE", "").strip().lower()
    if qt_im_module in {"", "fcitx", "fcitx5"}:
        os.environ["QT_IM_MODULE"] = "ibus"

    from memory_qt.app import create_app
    from memory_qt.data_bridge import DataBridge
    from memory_qt.main_window import MainWindow

    app = create_app()
    bridge = DataBridge(db_path)
    window = MainWindow(bridge)

    def _bring_to_front(*_args):
        window._show_window()

    signal.signal(signal.SIGUSR1, _bring_to_front)

    import socket as _sock
    _timer = __import__("PyQt5.QtCore", fromlist=["QTimer"]).QTimer()
    _timer.timeout.connect(lambda: None)
    _timer.start(500)

    window.show()

    code = app.exec_()
    bridge.close()
    os.close(lock_fd)
    try:
        _LOCK_FILE.unlink()
    except OSError:
        pass
    sys.exit(code)


if __name__ == "__main__":
    main()
