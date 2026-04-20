"""记忆详情格式化 — CSS 样式、Markdown 预处理、关键词高亮"""

import re

from ..constants import C, FONT_CJK, FONT_MONO

_TYPE_LABELS_CN = {"episodic": "会话摘要", "semantic": "笔记", "procedural": "偏好"}


def _rgba(hex_color: str, opacity: float) -> str:
    hex_color = hex_color.lstrip("#")
    red = int(hex_color[0:2], 16)
    green = int(hex_color[2:4], 16)
    blue = int(hex_color[4:6], 16)
    return f"rgba({red}, {green}, {blue}, {opacity})"


def detail_css() -> str:
    return f"""
    body {{
        background-color: transparent;
        color: {C['text']};
        font-family: {FONT_CJK};
        font-size: 13px;
        line-height: 1.6;
        margin: 0;
        padding: 18px 20px;
    }}
    h1 {{
        color: {C['text']};
        font-size: 22px;
        font-weight: 800;
        padding-bottom: 10px;
        margin: 0 0 14px 0;
        border-bottom: 1px solid {_rgba(C['surface2'], 0.45)};
    }}
    h2 {{
        color: {C['lavender']};
        font-size: 15px;
        font-weight: 800;
        margin: 16px 0 8px 0;
    }}
    h3 {{
        color: {C['sapphire']};
        font-size: 14px;
        font-weight: 800;
        margin: 12px 0 6px 0;
    }}
    p {{
        margin: 6px 0;
    }}
    strong {{
        color: {C['peach']};
    }}
    code {{
        background: {_rgba(C['surface0'], 0.88)};
        color: {C['green']};
        padding: 2px 6px;
        border-radius: 6px;
        font-family: {FONT_MONO};
        font-size: 12px;
    }}
    pre {{
        background: {_rgba(C['mantle'], 0.96)};
        border: 1px solid {_rgba(C['surface2'], 0.35)};
        border-radius: 14px;
        padding: 14px;
        overflow-x: auto;
        font-family: {FONT_MONO};
        font-size: 12px;
        line-height: 1.4;
    }}
    pre code {{
        background: transparent;
        padding: 0;
    }}
    ul, ol {{
        margin: 6px 0;
        padding-left: 24px;
    }}
    li {{
        margin: 3px 0;
    }}
    hr {{
        border: none;
        border-top: 1px solid {_rgba(C['surface2'], 0.45)};
        margin: 12px 0;
    }}
    a {{
        color: {C['blue']};
        text-decoration: none;
    }}
    a:hover {{
        text-decoration: underline;
    }}
    table {{
        border-collapse: collapse;
        width: 100%;
        margin: 8px 0;
    }}
    th {{
        background: {_rgba(C['surface0'], 0.78)};
        color: {C['text']};
        padding: 8px 12px;
        text-align: left;
        font-weight: bold;
        border-bottom: 1px solid {_rgba(C['surface2'], 0.42)};
    }}
    td {{
        padding: 6px 12px;
        border-bottom: 1px solid {_rgba(C['surface0'], 0.4)};
    }}
    .meta-block {{
        background: {_rgba(C['surface0'], 0.72)};
        border: 1px solid {_rgba(C['surface2'], 0.35)};
        border-radius: 16px;
        padding: 12px 14px;
        margin-bottom: 14px;
        font-size: 12px;
        color: {C['subtext0']};
        line-height: 1.8;
    }}
    .meta-block strong {{
        color: {C['subtext1']};
    }}
    .badge {{
        display: inline-block;
        padding: 4px 10px;
        border-radius: 999px;
        font-size: 11px;
        font-weight: 800;
    }}
    .badge-episodic {{ background: {_rgba(C['teal'], 0.16)}; color: {C['teal']}; border: 1px solid {_rgba(C['teal'], 0.24)}; }}
    .badge-semantic {{ background: {_rgba(C['blue'], 0.16)}; color: {C['blue']}; border: 1px solid {_rgba(C['blue'], 0.24)}; }}
    .badge-procedural {{ background: {_rgba(C['mauve'], 0.16)}; color: {C['mauve']}; border: 1px solid {_rgba(C['mauve'], 0.24)}; }}
    .highlight {{
        background: {_rgba(C['yellow'], 0.22)};
        color: {C['text']};
        padding: 1px 4px;
        border-radius: 4px;
        font-weight: 800;
    }}
    """


def split_terms(term: str) -> list[str]:
    """将搜索词拆分成多个关键词，用于高亮"""
    if not term:
        return []

    words = re.split(r'[\s,，。.!！?？;；:：、]+', term)

    terms = []
    for w in words:
        w = w.strip()
        if not w:
            continue

        if re.match(r'^[a-zA-Z0-9_-]+$', w):
            if len(w) >= 2:
                terms.append(w)
        elif re.match(r'^[\u4e00-\u9fff]+$', w):
            if len(w) >= 2:
                terms.append(w)
                if len(w) >= 3:
                    for i in range(len(w) - 1):
                        terms.append(w[i:i+2])
        else:
            if len(w) >= 2:
                terms.append(w)

    unique = []
    seen = set()
    for t in sorted(set(terms), key=len, reverse=True):
        if t not in seen:
            seen.add(t)
            unique.append(t)

    return unique if unique else [term]


def highlight_html(html: str, term: str) -> tuple[str, int]:
    """高亮关键词，返回 (高亮后的HTML, 匹配数)"""
    if not term:
        return html, 0

    terms = split_terms(term)
    if not terms:
        return html, 0

    tag_pattern = re.compile(r'(<[^>]+>)')
    parts = tag_pattern.split(html)
    result = []
    match_count = 0

    for part in parts:
        if part.startswith('<'):
            result.append(part)
        else:
            matches = []
            for kw in terms:
                escaped = re.escape(kw)
                for m in re.finditer(escaped, part, re.IGNORECASE):
                    matches.append((m.start(), m.end(), m.group(0)))

            matches.sort(key=lambda x: (x[0], -(x[1] - x[0])))

            non_overlapping = []
            last_end = 0
            for start, end, text in matches:
                if start >= last_end:
                    non_overlapping.append((start, end, text))
                    last_end = end

            for start, end, text in reversed(non_overlapping):
                match_count += 1
                match_id = f"match-{match_count}"
                part = part[:start] + f'<span class="highlight" id="{match_id}">{text}</span>' + part[end:]

            result.append(part)

    return ''.join(result), match_count


def preprocess_markdown(text: str) -> str:
    """在 markdown 块级元素前自动插入空行"""
    lines = text.split('\n')
    result = []
    for i, line in enumerate(lines):
        stripped = line.strip()
        if i > 0 and result:
            prev = result[-1].strip()
            need_blank = False
            if re.match(r'^[-*+]\s', stripped):
                if prev and not re.match(r'^[-*+]\s', prev) and not prev == '':
                    need_blank = True
            elif re.match(r'^\d+\.\s', stripped):
                if prev and not re.match(r'^\d+\.\s', prev):
                    need_blank = True
            elif stripped.startswith('|'):
                if prev and not prev.startswith('|'):
                    need_blank = True
            elif re.match(r'^#{1,6}\s', stripped):
                if prev:
                    need_blank = True
            if need_blank:
                result.append('')
        result.append(line)
    return '\n'.join(result)


def format_memory_html(mem, highlight_term: str = "") -> tuple[str, int]:
    """格式化记忆为 HTML，返回 (HTML, 匹配数)"""
    entities = ", ".join(mem.entities) if mem.entities else "无"
    raw_type = mem.type.value if hasattr(mem.type, 'value') else str(mem.type)
    badge_cls = f"badge-{raw_type}"
    type_val = _TYPE_LABELS_CN.get(raw_type, raw_type)

    meta = (
        f'<div class="meta-block">'
        f'<span class="badge {badge_cls}">{type_val}</span> &nbsp; '
        f'<strong>ID:</strong> <code>{mem.id[:12]}</code> &nbsp; '
        f'<strong>强度:</strong> {mem.strength:.1f} &nbsp; '
        f'<strong>访问:</strong> {mem.access_count}次<br>'
        f'<strong>项目:</strong> {mem.project or "无"} &nbsp; '
        f'<strong>创建:</strong> {mem.created_at.strftime("%Y-%m-%d %H:%M")} &nbsp; '
        f'<strong>实体:</strong> {entities}'
        f'</div>'
    )

    import markdown
    content_html = markdown.markdown(
        preprocess_markdown(mem.content),
        extensions=['tables', 'fenced_code', 'nl2br'],
    )

    match_count = 0
    if highlight_term:
        content_html, match_count = highlight_html(content_html, highlight_term)

    html = (
        f'<html><head><style>{detail_css()}</style></head><body>'
        f'<h1>{mem.summary or "(无摘要)"}</h1>'
        f'{meta}'
        f'{content_html}'
        f'</body></html>'
    )
    return html, match_count
