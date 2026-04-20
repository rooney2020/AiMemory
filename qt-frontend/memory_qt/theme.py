"""主题系统 — QPalette + QSS 样式生成"""

from PyQt5.QtGui import QPalette, QColor
from PyQt5.QtWidgets import QApplication

from .constants import C, THEMES, FONT_CJK, FONT_MONO


def apply_theme(theme_name: str):
    """切换主题：更新 C 字典 + QPalette"""
    C.update(THEMES[theme_name])
    app = QApplication.instance()
    if app:
        _apply_palette(app)
        app.setStyleSheet(global_style())


def _apply_palette(app):
    pal = QPalette()
    pal.setColor(QPalette.Window, QColor(C["base"]))
    pal.setColor(QPalette.WindowText, QColor(C["text"]))
    pal.setColor(QPalette.Base, QColor(C["surface0"]))
    pal.setColor(QPalette.AlternateBase, QColor(C["mantle"]))
    pal.setColor(QPalette.Text, QColor(C["text"]))
    pal.setColor(QPalette.Button, QColor(C["surface0"]))
    pal.setColor(QPalette.ButtonText, QColor(C["text"]))
    pal.setColor(QPalette.Highlight, QColor(C["blue"]))
    pal.setColor(QPalette.HighlightedText, QColor(C["crust"]))
    pal.setColor(QPalette.ToolTipBase, QColor(C["surface0"]))
    pal.setColor(QPalette.ToolTipText, QColor(C["text"]))
    pal.setColor(QPalette.PlaceholderText, QColor(C["overlay0"]))
    app.setPalette(pal)


def _bg(color_key: str, opacity: float = 1.0) -> str:
    h = C[color_key]
    r, g, b = int(h[1:3], 16), int(h[3:5], 16), int(h[5:7], 16)
    return f"rgba({r},{g},{b},{opacity})"


def _panel_gradient(top_key: str = "base", bottom_key: str = "surface0", top_opacity: float = 0.96, bottom_opacity: float = 0.92) -> str:
    return (
        "qlineargradient(x1:0, y1:0, x2:0, y2:1, "
        f"stop:0 {_bg(top_key, top_opacity)}, "
        f"stop:1 {_bg(bottom_key, bottom_opacity)})"
    )


def _accent_gradient() -> str:
    return (
        "qlineargradient(x1:0, y1:0, x2:1, y2:1, "
        f"stop:0 {C['blue']}, stop:1 {C['teal']})"
    )


def scrollbar_style(width: int = 6) -> str:
    return f"""
    QScrollBar:vertical {{
        background: {_bg('surface1', 0.12)}; width: {width + 6}px; margin: 0;
        border-radius: {(width + 6) // 2}px;
    }}
    QScrollBar::handle:vertical {{
        background: {_accent_gradient()}; min-height: 28px;
        border-radius: {(width + 2) // 2}px;
        margin: 3px;
    }}
    QScrollBar::handle:vertical:hover {{ background: {C['lavender']}; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: transparent; }}
    QScrollBar:horizontal {{
        background: {_bg('surface1', 0.12)}; height: {width + 6}px; margin: 0;
        border-radius: {(width + 6) // 2}px;
    }}
    QScrollBar::handle:horizontal {{
        background: {_accent_gradient()}; min-width: 28px;
        border-radius: {(width + 2) // 2}px;
        margin: 3px;
    }}
    QScrollBar::handle:horizontal:hover {{ background: {C['lavender']}; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{ background: transparent; }}
    """


def global_style() -> str:
    return f"""
    * {{ font-family: {FONT_CJK}; }}
    QMainWindow {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {C['mantle']}, stop:0.55 {C['base']}, stop:1 {C['crust']});
        color: {C['text']};
    }}
    QWidget#app_shell {{ background: transparent; }}
    QFrame#shell_sidebar,
    QFrame#shell_topbar,
    QFrame#section_banner,
    QFrame#workspace_canvas,
    QFrame#command_card,
    QFrame#overview_hero,
    QFrame[bannerMetric="true"],
    QFrame[heroMetric="true"] {{
        background: {_panel_gradient()};
        border: 1px solid {_bg('surface2', 0.55)};
        border-radius: 24px;
    }}
    QFrame#shell_sidebar {{
        min-width: 108px;
        max-width: 108px;
    }}
    QFrame#workspace_canvas {{
        border-radius: 28px;
    }}
    QLabel#brand_mark {{
        background: {_accent_gradient()};
        color: white;
        border-radius: 18px;
        font-size: 22px;
        font-weight: 800;
        padding: 10px 0;
    }}
    QLabel#brand_title {{
        color: {C['text']};
        font-size: 14px;
        font-weight: 800;
        letter-spacing: 0.08em;
    }}
    QLabel#brand_subtitle,
    QLabel#sidebar_footer,
    QLabel#command_subtitle,
    QLabel#section_kicker,
    QLabel#section_subtitle,
    QLabel#metric_label,
    QLabel#hero_kicker,
    QLabel#hero_desc {{
        color: {C['subtext0']};
        background: transparent;
        border: none;
    }}
    QLabel#command_badge,
    QLabel#hero_kicker {{
        background: {_bg('blue', 0.14)};
        color: {C['blue']};
        border: 1px solid {_bg('blue', 0.18)};
        border-radius: 999px;
        font-family: {FONT_MONO};
        font-size: 12px;
        font-weight: 700;
        padding: 5px 10px;
    }}
    QLabel#command_title {{
        color: {C['text']};
        background: transparent;
        border: none;
        font-size: 15px;
        font-weight: 800;
    }}
    QLabel#section_title,
    QLabel#hero_title {{
        color: {C['text']};
        background: transparent;
        border: none;
        font-size: 26px;
        font-weight: 800;
    }}
    QLabel#hero_desc {{
        font-size: 13px;
        line-height: 1.6;
    }}
    QLabel#metric_value {{
        color: {C['text']};
        background: transparent;
        border: none;
        font-size: 22px;
        font-weight: 800;
    }}
    QToolTip {{
        background: {_panel_gradient('base', 'surface0', 0.98, 0.96)}; color: {C['text']};
        border: 1px solid {_bg('surface2', 0.6)}; border-radius: 10px;
        padding: 6px 10px; font-size: 12px;
    }}
    {scrollbar_style(6)}
    QMenu {{
        background: {_panel_gradient('base', 'surface0', 0.98, 0.94)}; color: {C['text']};
        border: 1px solid {_bg('surface2', 0.55)}; border-radius: 12px;
        padding: 6px 4px; font-size: 13px;
    }}
    QMenu::item {{
        padding: 8px 28px 8px 16px; border-radius: 4px; margin: 1px 4px;
    }}
    QMenu::item:selected {{ background: {_bg('blue', 0.12)}; color: {C['text']}; }}
    QMenu::separator {{ height: 1px; background: {_bg('surface2', 0.45)}; margin: 4px 8px; }}
    QMenuBar {{
        background: transparent; color: {C['text']};
        border: none; font-size: 13px; padding: 2px;
    }}
    QMenuBar::item {{ padding: 6px 12px; border-radius: 10px; }}
    QMenuBar::item:selected {{ background: {_bg('surface0', 0.65)}; }}
    QComboBox {{
        background: {_panel_gradient('base', 'surface0', 0.96, 0.92)}; color: {C['text']};
        border: 1px solid {_bg('surface2', 0.6)}; border-radius: 14px;
        padding: 7px 12px; font-size: 13px;
    }}
    QComboBox:hover {{ border-color: {_bg('blue', 0.75)}; }}
    QComboBox::drop-down {{
        border: none; width: 20px;
    }}
    QComboBox QAbstractItemView {{
        background: {_panel_gradient('base', 'surface0', 0.98, 0.96)}; color: {C['text']};
        border: 1px solid {_bg('surface2', 0.55)}; border-radius: 12px;
        selection-background-color: {_bg('blue', 0.12)};
        selection-color: {C['text']};
        outline: none;
    }}
    QTabWidget::pane {{
        background: transparent;
        border: none;
    }}
    QTabBar {{
        background: transparent;
        border: none;
    }}
    QTabBar::tab {{
        background: transparent;
        color: {C['subtext0']};
        border: 1px solid transparent;
        border-radius: 14px;
        padding: 8px 18px;
        margin-right: 6px;
        font-size: 12px;
        font-weight: 700;
    }}
    QTabBar::tab:hover {{
        background: {_bg('surface0', 0.68)};
        color: {C['text']};
        border-color: {_bg('surface2', 0.45)};
    }}
    QTabBar::tab:selected {{
        background: {_accent_gradient()};
        color: white;
        border-color: transparent;
    }}
    QSplitter::handle {{
        background: transparent;
    }}
    QSplitter::handle:horizontal {{
        width: 12px;
        margin: 10px 0;
    }}
    QSplitter::handle:vertical {{
        height: 12px;
        margin: 0 10px;
    }}
    QStatusBar {{
        background: {_panel_gradient('base', 'surface0', 0.98, 0.94)};
        color: {C['subtext0']};
        border-top: 1px solid {_bg('surface2', 0.45)};
    }}
    QStatusBar::item {{ border: none; }}
    """


def tab_bar_style() -> str:
    return f"""
    QTabWidget::pane {{
        background: transparent;
        border: none;
        padding: 0px;
        margin: 0px;
    }}
    QTabBar {{
        background: transparent;
        border: none;
        qproperty-drawBase: 0;
    }}
    QTabBar::tab {{
        background: transparent; color: {C['subtext0']};
        border: 1px solid transparent; border-radius: 14px;
        padding: 8px 20px; font-size: 12px; font-weight: bold;
        min-width: 60px;
        margin-right: 6px;
    }}
    QTabBar::tab:hover {{
        background: {_bg('surface0', 0.68)}; color: {C['text']};
        border-color: {_bg('surface2', 0.4)};
    }}
    QTabBar::tab:selected {{
        background: {_accent_gradient()}; color: white;
        border-color: transparent;
    }}
    """


def card_style() -> str:
    return f"""
    QFrame[card="true"] {{
        background: {_panel_gradient('base', 'surface0', 0.96, 0.9)};
        border: 1px solid {_bg('surface2', 0.45)};
        border-radius: 18px;
    }}
    QFrame[card="true"]:hover {{ border-color: {_bg('blue', 0.58)}; }}
    """


def lineedit_style() -> str:
    return f"""
    QLineEdit {{
        background: {_panel_gradient('base', 'surface0', 0.98, 0.94)}; color: {C['text']};
        border: 1px solid {_bg('surface2', 0.55)}; border-radius: 14px;
        padding: 8px 14px; font-size: 13px;
        selection-background-color: {C['blue']};
        selection-color: white;
    }}
    QLineEdit:hover {{ border-color: {_bg('blue', 0.55)}; }}
    QLineEdit:focus {{ border: 1px solid {_bg('blue', 0.82)}; }}
    """


def table_style() -> str:
    return f"""
    QTableWidget {{
        background: {_panel_gradient('base', 'surface0', 0.98, 0.92)}; color: {C['text']};
        border: 1px solid {_bg('surface2', 0.45)}; border-radius: 16px;
        gridline-color: {_bg('surface2', 0.24)}; font-size: 13px;
        selection-background-color: {_bg('blue', 0.2)};
        selection-color: {C['text']};
        outline: none;
    }}
    QTableWidget::item {{ padding: 6px 10px; }}
    QTableWidget::item:hover {{ background: {_bg('surface0', 0.72)}; }}
    QHeaderView::section {{
        background: {_panel_gradient('surface0', 'surface1', 0.92, 0.88)}; color: {C['subtext0']};
        border: none; border-bottom: 1px solid {_bg('surface2', 0.35)};
        padding: 8px 10px; font-size: 12px; font-weight: bold;
    }}
    QTableCornerButton::section {{ background: {_panel_gradient('surface0', 'surface1', 0.92, 0.88)}; border: none; }}
    """


def tree_style() -> str:
    return f"""
    QTreeWidget {{
        background: {_panel_gradient('base', 'surface0', 0.98, 0.92)}; color: {C['text']};
        border: 1px solid {_bg('surface2', 0.45)}; border-radius: 16px;
        outline: none; font-size: 13px;
    }}
    QTreeWidget::item {{ padding: 4px 8px; }}
    QTreeWidget::item:hover {{ background: {_bg('surface0', 0.7)}; }}
    QTreeWidget::item:selected {{
        background: {_bg('blue', 0.2)}; color: {C['text']};
    }}
    QTreeWidget::branch:selected,
    QTreeWidget::branch:has-siblings:selected,
    QTreeWidget::branch:!has-siblings:selected {{
        background: {_bg('blue', 0.2)};
    }}
    """


def list_style() -> str:
    return f"""
    QListWidget {{
        background: {_panel_gradient('base', 'surface0', 0.98, 0.92)}; color: {C['text']};
        border: 1px solid {_bg('surface2', 0.45)}; border-radius: 16px;
        outline: none; font-size: 13px; padding: 4px;
    }}
    QListWidget::item {{
        padding: 8px 12px; border-radius: 10px; margin: 2px;
    }}
    QListWidget::item:hover {{ background: {_bg('surface0', 0.72)}; }}
    QListWidget::item:selected {{
        background: {_bg('blue', 0.2)}; color: {C['text']};
    }}
    """


def primary_btn_style() -> str:
    return f"""
    QPushButton {{
        background: {_accent_gradient()}; color: white;
        border: 1px solid transparent; border-radius: 14px;
        padding: 9px 18px; font-size: 13px; font-weight: bold;
    }}
    QPushButton:hover {{ border-color: {_bg('blue', 0.3)}; }}
    QPushButton:pressed {{ background: {C['sapphire']}; }}
    QPushButton:disabled {{ background: {C['surface1']}; color: {C['overlay0']}; }}
    """


def secondary_btn_style() -> str:
    return f"""
    QPushButton {{
        background: {_panel_gradient('base', 'surface0', 0.98, 0.92)}; color: {C['text']};
        border: 1px solid {_bg('surface2', 0.45)}; border-radius: 14px;
        padding: 8px 16px; font-size: 13px; font-weight: 700;
    }}
    QPushButton:hover {{ border-color: {_bg('blue', 0.46)}; background: {_bg('surface0', 0.76)}; }}
    QPushButton:pressed {{ background: {_bg('surface1', 0.88)}; }}
    """


def danger_btn_style() -> str:
    return f"""
    QPushButton {{
        background: qlineargradient(x1:0, y1:0, x2:1, y2:1,
            stop:0 {C['red']}, stop:1 {C['maroon']});
        color: white;
        border: 1px solid transparent; border-radius: 14px;
        padding: 8px 16px; font-size: 13px; font-weight: bold;
    }}
    QPushButton:hover {{ border-color: {_bg('red', 0.28)}; }}
    """


def badge_style(color_key: str = "blue") -> str:
    return f"""
    QLabel {{
        background: {_bg(color_key, 0.14)}; color: {C[color_key]};
        border: 1px solid {_bg(color_key, 0.18)};
        border-radius: 999px; font-size: 11px; font-weight: bold;
        padding: 4px 10px;
    }}
    """


def text_edit_style() -> str:
    return f"""
    QTextEdit, QPlainTextEdit {{
        background: {_panel_gradient('base', 'surface0', 0.98, 0.92)}; color: {C['text']};
        border: 1px solid {_bg('surface2', 0.45)}; border-radius: 16px;
        padding: 8px; font-size: 13px;
        selection-background-color: {C['blue']};
        selection-color: white;
    }}
    QTextEdit:focus, QPlainTextEdit:focus {{ border-color: {_bg('blue', 0.78)}; }}
    """
