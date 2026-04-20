"""Qt runtime environment bootstrap."""

from __future__ import annotations

import importlib.util
import os
from pathlib import Path


def _prepend_env_path(name: str, path: Path) -> None:
    current = os.environ.get(name, "")
    parts = [item for item in current.split(os.pathsep) if item]
    value = str(path)
    if value in parts:
        return
    os.environ[name] = os.pathsep.join([value, *parts]) if parts else value


def _runtime_pyqt_plugin_root() -> Path | None:
    spec = importlib.util.find_spec("PyQt5")
    if not spec or not spec.submodule_search_locations:
        return None

    package_root = Path(next(iter(spec.submodule_search_locations)))
    plugin_root = package_root / "Qt5" / "plugins"
    return plugin_root if plugin_root.is_dir() else None


def _repo_pyqt_plugin_root(repo_root: Path) -> Path | None:
    for env_name in ("venv", ".venv"):
        lib_root = repo_root / env_name / "lib"
        if not lib_root.exists():
            continue
        plugin_root = next(
            (candidate for candidate in sorted(lib_root.glob("python*/site-packages/PyQt5/Qt5/plugins")) if candidate.is_dir()),
            None,
        )
        if plugin_root:
            return plugin_root
    return None


def bootstrap_qt_env() -> None:
    repo_root = Path(__file__).resolve().parent.parent
    plugin_root = _runtime_pyqt_plugin_root() or _repo_pyqt_plugin_root(repo_root)

    if plugin_root:
        _prepend_env_path("QT_PLUGIN_PATH", plugin_root)
        platform_root = plugin_root / "platforms"
        if platform_root.is_dir():
            os.environ.setdefault("QT_QPA_PLATFORM_PLUGIN_PATH", str(platform_root))

    qt_im_module = os.environ.get("QT_IM_MODULE", "").strip().lower()
    if qt_im_module in {"", "fcitx", "fcitx5"}:
        os.environ["QT_IM_MODULE"] = "ibus"