"""主题常量 — 支持从外部 JSON 加载主题配置"""

from __future__ import annotations

import json
from pathlib import Path


_BUILTIN_THEME_CONFIG = {
    "default_theme": "科技清爽·夜航",
    "themes": {
        "科技清爽·夜航": {
            "rosewater": "#dff6ff", "flamingo": "#8cecdf", "pink": "#9ea4ff",
            "mauve": "#8b7dff", "red": "#ff7d79", "maroon": "#dc6676",
            "peach": "#ffb16a", "yellow": "#f0b95f", "green": "#31d0a2",
            "teal": "#34d2c8", "sky": "#7ad9ff", "sapphire": "#4ca9e8",
            "blue": "#5dc5ff", "lavender": "#a4b6ff",
            "text": "#eef5ff", "subtext1": "#c6d4ea", "subtext0": "#9fb2cb",
            "overlay2": "#7b90ad", "overlay1": "#5e7395", "overlay0": "#445b7b",
            "surface2": "#314a6d", "surface1": "#1e3554", "surface0": "#13233b",
            "base": "#0f172a", "mantle": "#08101d", "crust": "#050b14",
        },
        "科技清爽·暖雾": {
            "rosewater": "#f3ddd2", "flamingo": "#d2b6ab", "pink": "#b89fb8",
            "mauve": "#927f97", "red": "#c8786e", "maroon": "#a9655d",
            "peach": "#d49b63", "yellow": "#b99358", "green": "#6b9986",
            "teal": "#7ba79e", "sky": "#92a4b9", "sapphire": "#7f91a6",
            "blue": "#6d829a", "lavender": "#a79ab2",
            "text": "#332d28", "subtext1": "#5f5650", "subtext0": "#80766f",
            "overlay2": "#9a8f87", "overlay1": "#aba19a", "overlay0": "#beb4ad",
            "surface2": "#d8cdc3", "surface1": "#e8dfd6", "surface0": "#f3ece4",
            "base": "#fbf7f2", "mantle": "#f4eee7", "crust": "#ece4db",
        },
        "科技清爽·森林绿": {
            "rosewater": "#dcebdc", "flamingo": "#a7d2b1", "pink": "#8fb7a4",
            "mauve": "#6e9a86", "red": "#c47063", "maroon": "#9d5a53",
            "peach": "#d39d66", "yellow": "#bea05d", "green": "#4e9b6f",
            "teal": "#5aa68a", "sky": "#7aa8a0", "sapphire": "#678f88",
            "blue": "#5f8478", "lavender": "#93a892",
            "text": "#21352b", "subtext1": "#466154", "subtext0": "#68806f",
            "overlay2": "#859889", "overlay1": "#9eaea0", "overlay0": "#b8c4b8",
            "surface2": "#c7d8c8", "surface1": "#dce8dd", "surface0": "#edf4ee",
            "base": "#f5faf5", "mantle": "#eef6ee", "crust": "#e4eee4",
        },
        "科技清爽·天空蓝": {
            "rosewater": "#d7ecff", "flamingo": "#8dc8ff", "pink": "#77b4ff",
            "mauve": "#5aa4ff", "red": "#cf7b72", "maroon": "#aa615e",
            "peach": "#d89a67", "yellow": "#c3a261", "green": "#68aa8e",
            "teal": "#58b9d8", "sky": "#4eb7ff", "sapphire": "#3fa7ff",
            "blue": "#3399FF", "lavender": "#7eaef0",
            "text": "#173a60", "subtext1": "#3d648d", "subtext0": "#5a82ab",
            "overlay2": "#7698bb", "overlay1": "#91afcf", "overlay0": "#adc7e1",
            "surface2": "#b8d9f6", "surface1": "#d1e9fb", "surface0": "#e7f4ff",
            "base": "#f2f9ff", "mantle": "#e3f2ff", "crust": "#d4eaff",
        },
        "科技清爽·梦幻粉": {
            "rosewater": "#ffdce5", "flamingo": "#f6b2c0", "pink": "#ED8A9F",
            "mauve": "#dc7391", "red": "#d76382", "maroon": "#b94c6d",
            "peach": "#f2a57f", "yellow": "#dda16b", "green": "#8dc2aa",
            "teal": "#84c7bf", "sky": "#b6b4f0", "sapphire": "#9e9ce0",
            "blue": "#9d99d6", "lavender": "#d29fd6",
            "text": "#4b2234", "subtext1": "#7a4c61", "subtext0": "#9b7083",
            "overlay2": "#b58d9e", "overlay1": "#cca8b7", "overlay0": "#e0c1cc",
            "surface2": "#f2cad7", "surface1": "#f9dde6", "surface0": "#fff0f5",
            "base": "#fff8fb", "mantle": "#ffeef4", "crust": "#f9dfe8",
        },
        "科技清爽·中国红": {
            "rosewater": "#f7e3d5", "flamingo": "#e9cdbd", "pink": "#d97f6b",
            "mauve": "#c94b3a", "red": "#C3272B", "maroon": "#7b1017",
            "peach": "#D4AF37", "yellow": "#FFD700", "green": "#9f8a56",
            "teal": "#c98910", "sky": "#dcb546", "sapphire": "#c98910",
            "blue": "#C3272B", "lavender": "#f1d17a",
            "text": "#fff7ef", "subtext1": "#f3dcc7", "subtext0": "#e6bba8",
            "overlay2": "#d9a07d", "overlay1": "#b85242", "overlay0": "#8e261e",
            "surface2": "#cc4a4d", "surface1": "#ab2430", "surface0": "#8f1522",
            "base": "#7d0e1a", "mantle": "#650814", "crust": "#43040c",
        },
    },
}

THEME_CONFIG_PATH = Path(__file__).resolve().with_name("themes.json")
_BUILTIN_THEMES = _BUILTIN_THEME_CONFIG["themes"]
_BUILTIN_DEFAULT_THEME = _BUILTIN_THEME_CONFIG["default_theme"]
_REQUIRED_THEME_KEYS = set(next(iter(_BUILTIN_THEMES.values())).keys())
_SEMANTIC_THEME_KEY_MAP = {
    "accent_tint_soft": "rosewater",
    "accent_tint_warm": "flamingo",
    "accent_highlight": "pink",
    "accent_highlight_deep": "mauve",
    "accent_danger": "red",
    "accent_danger_deep": "maroon",
    "accent_warm": "peach",
    "accent_warning": "yellow",
    "accent_success": "green",
    "accent_secondary": "teal",
    "accent_info": "sky",
    "accent_info_deep": "sapphire",
    "accent_primary": "blue",
    "accent_soft": "lavender",
    "text_primary": "text",
    "text_secondary": "subtext1",
    "text_muted": "subtext0",
    "border_strong": "overlay2",
    "border_medium": "overlay1",
    "border_weak": "overlay0",
    "panel_border": "surface2",
    "panel_elevated": "surface1",
    "panel_base": "surface0",
    "background_base": "base",
    "background_layer": "mantle",
    "background_deep": "crust",
}
_THEME_KEY_ALIASES = {legacy_key: legacy_key for legacy_key in _REQUIRED_THEME_KEYS}
_THEME_KEY_ALIASES.update(_SEMANTIC_THEME_KEY_MAP)


def _clone_themes(themes: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    return {theme_name: dict(palette) for theme_name, palette in themes.items()}


def _normalize_themes(raw_themes: object) -> dict[str, dict[str, str]]:
    if not isinstance(raw_themes, dict):
        return _clone_themes(_BUILTIN_THEMES)

    themes: dict[str, dict[str, str]] = {}
    for theme_name, palette in raw_themes.items():
        if not isinstance(theme_name, str) or not isinstance(palette, dict):
            continue
        normalized_palette: dict[str, str] = {}
        for key, value in palette.items():
            target_key = _THEME_KEY_ALIASES.get(key)
            if target_key is None:
                continue
            normalized_palette[target_key] = str(value)
        if not _REQUIRED_THEME_KEYS.issubset(normalized_palette.keys()):
            continue
        themes[theme_name] = {key: normalized_palette[key] for key in _REQUIRED_THEME_KEYS}

    return themes or _clone_themes(_BUILTIN_THEMES)


def _load_theme_config() -> tuple[dict[str, dict[str, str]], str]:
    if not THEME_CONFIG_PATH.exists():
        return _clone_themes(_BUILTIN_THEMES), str(_BUILTIN_DEFAULT_THEME)

    try:
        payload = json.loads(THEME_CONFIG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return _clone_themes(_BUILTIN_THEMES), str(_BUILTIN_DEFAULT_THEME)

    themes = _normalize_themes(payload.get("themes")) if isinstance(payload, dict) else _clone_themes(_BUILTIN_THEMES)
    default_theme = payload.get("default_theme") if isinstance(payload, dict) else _BUILTIN_DEFAULT_THEME
    if not isinstance(default_theme, str) or default_theme not in themes:
        default_theme = next(iter(themes))
    return themes, default_theme


def save_default_theme(theme_name: str) -> bool:
    if not isinstance(theme_name, str) or theme_name not in THEMES:
        return False

    payload: dict[str, object] = {}
    if THEME_CONFIG_PATH.exists():
        try:
            loaded = json.loads(THEME_CONFIG_PATH.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            loaded = {}
        if isinstance(loaded, dict):
            payload = loaded

    payload["default_theme"] = theme_name

    try:
        THEME_CONFIG_PATH.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
    except OSError:
        return False
    return True


def reload_theme_config(preferred_theme: str | None = None) -> str:
    global DEFAULT_THEME

    themes, default_theme = _load_theme_config()
    THEMES.clear()
    THEMES.update(themes)
    DEFAULT_THEME = default_theme

    selected_theme = preferred_theme if isinstance(preferred_theme, str) and preferred_theme in THEMES else DEFAULT_THEME
    C.clear()
    C.update(THEMES[selected_theme])
    return selected_theme


THEMES, DEFAULT_THEME = _load_theme_config()

C: dict[str, str] = dict(THEMES[DEFAULT_THEME])

FONT_MONO = "'JetBrains Mono', 'Fira Code', 'Consolas', monospace"
FONT_CJK = "'Plus Jakarta Sans', 'Noto Sans CJK SC', 'Noto Sans SC', 'Microsoft YaHei', sans-serif"
FONT_DEFAULT = f"{FONT_CJK}"

APP_NAME = "AI Memory Manager"
APP_VERSION = "0.1.0"
DB_PATH_DEFAULT = "~/.local/share/ai-memory/db/memory.db"
