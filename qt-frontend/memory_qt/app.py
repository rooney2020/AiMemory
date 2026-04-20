"""QApplication 初始化"""

import sys
from pathlib import Path

from .bootstrap import bootstrap_qt_env

bootstrap_qt_env()

from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication, QStyleFactory

from .constants import DEFAULT_THEME
from .theme import apply_theme

_ICON_PATH = Path(__file__).parent.parent / "assets" / "icon.svg"


def create_app() -> QApplication:
    app = QApplication(sys.argv)
    app.setApplicationName("AI Memory Manager")
    app.setStyle(QStyleFactory.create("Fusion"))
    if _ICON_PATH.exists():
        app.setWindowIcon(QIcon(str(_ICON_PATH)))
    apply_theme(DEFAULT_THEME)
    return app
