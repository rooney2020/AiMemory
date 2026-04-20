"""主题常量 — 科技清爽情报台三态主题"""

THEMES = {
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
    "科技清爽·晴空": {
        "rosewater": "#ffe5dc", "flamingo": "#79dacc", "pink": "#8d7bff",
        "mauve": "#6f62ff", "red": "#d95d5d", "maroon": "#bf4955",
        "peach": "#ee8f3c", "yellow": "#db931d", "green": "#1fa473",
        "teal": "#11b8b0", "sky": "#5ca9ff", "sapphire": "#4186d9",
        "blue": "#2876e2", "lavender": "#7e8cff",
        "text": "#10243e", "subtext1": "#3d5877", "subtext0": "#5e7696",
        "overlay2": "#6d84a4", "overlay1": "#7c93b0", "overlay0": "#8ca1bb",
        "surface2": "#d6e4f3", "surface1": "#e8f0f8", "surface0": "#f3f8fc",
        "base": "#ffffff", "mantle": "#f9fcff", "crust": "#ecf5fb",
    },
    "科技清爽·薄雾": {
        "rosewater": "#f9dce7", "flamingo": "#86dccc", "pink": "#b88cff",
        "mauve": "#a56cff", "red": "#df6b73", "maroon": "#c55964",
        "peach": "#f0a758", "yellow": "#d5962d", "green": "#1da383",
        "teal": "#14b8a6", "sky": "#7fa9ff", "sapphire": "#668de5",
        "blue": "#4c7fff", "lavender": "#a783ff",
        "text": "#19293c", "subtext1": "#44576b", "subtext0": "#647890",
        "overlay2": "#7b8fa6", "overlay1": "#8698aa", "overlay0": "#93a2b5",
        "surface2": "#d7dee8", "surface1": "#e8edf4", "surface0": "#f4f7fb",
        "base": "#ffffff", "mantle": "#f8f9fc", "crust": "#f2f4f9",
    },
}

DEFAULT_THEME = "科技清爽·夜航"

C: dict[str, str] = dict(THEMES[DEFAULT_THEME])

FONT_MONO = "'JetBrains Mono', 'Fira Code', 'Consolas', monospace"
FONT_CJK = "'Plus Jakarta Sans', 'Noto Sans CJK SC', 'Noto Sans SC', 'Microsoft YaHei', sans-serif"
FONT_DEFAULT = f"{FONT_CJK}"

APP_NAME = "AI Memory Manager"
APP_VERSION = "0.1.0"
DB_PATH_DEFAULT = "~/.local/share/ai-memory/db/memory.db"
