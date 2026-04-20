"""格式化函数 — 记忆/会话/资产的纯文本/HTML/JSON/Markdown 格式化"""

import json

FORMATS = ("Markdown", "TXT", "JSON", "HTML")
_EXT_MAP = {"Markdown": ".md", "TXT": ".txt", "JSON": ".json", "HTML": ".html"}
_TYPE_CN = {"episodic": "会话摘要", "semantic": "笔记", "procedural": "偏好"}


def _preprocess_md(text: str) -> str:
    """确保表格、列表等块级元素前有空行，避免 markdown 库忽略它们。
    关键：不在同类型连续行之间插入空行（如表格行之间）。"""
    lines = text.split('\n')
    result = []
    for i, line in enumerate(lines):
        s = line.strip()
        if i > 0 and result:
            prev = result[-1].strip()
            if prev:
                is_table = s.startswith('|')
                prev_table = prev.startswith('|')
                is_ul = bool(s) and s[0] in '-*+' and len(s) > 1 and s[1] == ' '
                prev_ul = bool(prev) and prev[0] in '-*+' and len(prev) > 1 and prev[1] == ' '
                is_ol = bool(s) and s[0].isdigit() and '. ' in s[:5]
                prev_ol = bool(prev) and prev[0].isdigit() and '. ' in prev[:5]
                is_code = s.startswith('```')

                if (is_table and not prev_table) or \
                   (is_ul and not prev_ul) or \
                   (is_ol and not prev_ol) or \
                   is_code:
                    result.append('')
        result.append(line)
    return '\n'.join(result)


def _render_md(text: str, extensions=None) -> str:
    """统一的 Markdown 渲染入口，带预处理"""
    import html as _h
    if extensions is None:
        extensions = ["tables", "fenced_code"]
    try:
        import markdown
        return markdown.markdown(_preprocess_md(text), extensions=extensions)
    except ImportError:
        return f"<pre>{_h.escape(text)}</pre>"


def _raw_type(mem) -> str:
    return mem.type.value if hasattr(mem.type, "value") else str(mem.type)


def _type_cn(mem) -> str:
    return _TYPE_CN.get(_raw_type(mem), _raw_type(mem))


# ── single memory ──────────────────────────────────────────

def _mem_to_dict(mem) -> dict:
    return {
        "id": mem.id,
        "type": _raw_type(mem),
        "summary": mem.summary,
        "content": mem.content,
        "strength": mem.strength,
        "access_count": mem.access_count,
        "project": mem.project,
        "entities": list(mem.entities) if mem.entities else [],
        "created_at": mem.created_at.isoformat() if mem.created_at else None,
    }


def _mem_to_md(mem) -> str:
    lines = [f"# {mem.summary or '(无摘要)'}", ""]
    lines.append(f"- **类型**: {_type_cn(mem)}")
    lines.append(f"- **ID**: `{mem.id}`")
    lines.append(f"- **强度**: {mem.strength:.1f} | **访问**: {mem.access_count}")
    if mem.project:
        lines.append(f"- **项目**: {mem.project}")
    if mem.entities:
        lines.append(f"- **实体**: {', '.join(mem.entities)}")
    if mem.created_at:
        lines.append(f"- **创建**: {mem.created_at.strftime('%Y-%m-%d %H:%M')}")
    lines.extend(["", "---", "", mem.content])
    return "\n".join(lines)


def _mem_to_txt(mem) -> str:
    lines = [
        f"[{_type_cn(mem)}] {mem.summary or '(无摘要)'}",
        f"ID: {mem.id}  |  强度: {mem.strength:.1f}  |  访问: {mem.access_count}",
    ]
    if mem.project:
        lines.append(f"项目: {mem.project}")
    if mem.created_at:
        lines.append(f"创建: {mem.created_at.strftime('%Y-%m-%d %H:%M')}")
    lines.extend(["", "=" * 60, "", mem.content])
    return "\n".join(lines)


def _html_wrap(title: str, body_html: str) -> str:
    import html as _h
    return f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>{_h.escape(title)}</title>
<style>
body {{ font-family: 'Noto Sans CJK SC',sans-serif; max-width: 900px; margin: 40px auto; padding: 0 24px; color: #333; line-height: 1.7; }}
h1 {{ color: #2563eb; border-bottom: 2px solid #e5e7eb; padding-bottom: 8px; }}
h2 {{ color: #6366f1; margin-top: 28px; }}
.meta {{ background: #f3f4f6; padding: 12px 16px; border-radius: 8px; margin-bottom: 16px; font-size: 13px; }}
.meta strong {{ color: #555; }}
code {{ background: #f3f4f6; padding: 2px 6px; border-radius: 4px; font-family: 'Fira Code',monospace; font-size: 13px; }}
pre {{ background: #1e1e2e; color: #cdd6f4; padding: 14px; border-radius: 8px; overflow-x: auto; font-size: 13px; line-height: 1.5; }}
pre code {{ background: transparent; padding: 0; }}
ul, ol {{ padding-left: 24px; margin: 6px 0; }}
blockquote {{ border-left: 3px solid #6366f1; padding-left: 12px; color: #666; margin: 8px 0; }}
details {{ margin: 4px 0; }}
summary {{ cursor: pointer; }}
table {{ border-collapse: collapse; width: 100%; margin: 8px 0; }}
th, td {{ border: 1px solid #ddd; padding: 8px 12px; text-align: left; }}
th {{ background: #f3f4f6; font-weight: bold; }}
hr {{ border: none; border-top: 1px solid #e5e7eb; margin: 24px 0; }}
.card {{ border: 1px solid #e5e7eb; border-radius: 12px; padding: 20px; margin-bottom: 20px; }}
</style></head><body>
{body_html}
</body></html>"""


def _mem_to_html(mem) -> str:
    import html as _h
    body = _render_md(mem.content)

    meta = (
        f'<div class="meta">'
        f'<strong>类型:</strong> {_type_cn(mem)} &nbsp; '
        f'<strong>ID:</strong> <code>{mem.id[:12]}</code> &nbsp; '
        f'<strong>强度:</strong> {mem.strength:.1f} &nbsp; '
        f'<strong>访问:</strong> {mem.access_count}次'
    )
    if mem.project:
        meta += f'<br><strong>项目:</strong> {mem.project}'
    if mem.created_at:
        meta += f' &nbsp; <strong>创建:</strong> {mem.created_at.strftime("%Y-%m-%d %H:%M")}'
    meta += "</div>"

    return _html_wrap(
        mem.summary or "导出",
        f"<h1>{_h.escape(mem.summary or '(无摘要)')}</h1>{meta}{body}",
    )


def format_memory(mem, fmt: str) -> str:
    if fmt == "JSON":
        return json.dumps(_mem_to_dict(mem), ensure_ascii=False, indent=2)
    if fmt == "Markdown":
        return _mem_to_md(mem)
    if fmt == "HTML":
        return _mem_to_html(mem)
    return _mem_to_txt(mem)


# ── multiple memories ──────────────────────────────────────

def format_memories(memories, fmt: str, title: str = "记忆导出") -> str:
    if fmt == "JSON":
        return json.dumps([_mem_to_dict(m) for m in memories], ensure_ascii=False, indent=2)
    if fmt == "Markdown":
        return ("\n\n---\n\n").join(_mem_to_md(m) for m in memories)
    if fmt == "HTML":
        import html as _h
        cards = []
        for m in memories:
            body = _render_md(m.content)
            cards.append(
                f'<div class="card"><h2>{_h.escape(m.summary or "(无摘要)")}</h2>'
                f'<div class="meta"><strong>{_type_cn(m)}</strong> | '
                f'强度 {m.strength:.1f} | {m.project or "无项目"}</div>{body}</div>'
            )
        return _html_wrap(title, f"<h1>{_h.escape(title)}</h1>" + "\n".join(cards))
    return ("\n\n" + "=" * 60 + "\n\n").join(_mem_to_txt(m) for m in memories)


# ── session ────────────────────────────────────────────────

def _session_to_dict(session) -> dict:
    msgs = []
    for m in (session.messages or []):
        msgs.append({
            "role": m.role,
            "content": m.content,
            "timestamp": m.timestamp.isoformat() if m.timestamp else None,
        })
    return {
        "id": session.id,
        "title": session.title,
        "framework": session.framework.value,
        "workspace": session.workspace,
        "message_count": session.message_count,
        "created_at": session.created_at.isoformat() if session.created_at else None,
        "updated_at": session.updated_at.isoformat() if session.updated_at else None,
        "messages": msgs,
    }


def format_session(session, fmt: str) -> str:
    role_cn = {"user": "用户", "assistant": "AI", "tool": "工具"}

    if fmt == "JSON":
        return json.dumps(_session_to_dict(session), ensure_ascii=False, indent=2)

    if fmt == "Markdown":
        lines = [f"# {session.display_title}", ""]
        lines.append(f"- **框架**: {session.framework.value}")
        if session.workspace:
            lines.append(f"- **工作区**: {session.workspace}")
        lines.append(f"- **消息数**: {session.message_count}")
        if session.display_time:
            lines.append(f"- **时间**: {session.display_time}")
        lines.extend(["", "---", ""])
        for msg in (session.messages or []):
            prefix = role_cn.get(msg.role, msg.role)
            lines.append(f"### [{prefix}]")
            lines.append(msg.content)
            lines.append("")
        return "\n".join(lines)

    if fmt == "HTML":
        import html as _h

        msgs_html = []
        for msg in (session.messages or []):
            prefix = role_cn.get(msg.role, msg.role)
            color = {"user": "#2563eb", "assistant": "#333", "tool": "#9ca3af"}.get(msg.role, "#333")
            bg = {"user": "#eff6ff", "tool": "#f9fafb"}.get(msg.role, "transparent")
            if msg.role == "tool":
                first_line = _h.escape(msg.content.strip().split("\n", 1)[0][:120])
                tool_body = _render_md(msg.content)
                msgs_html.append(
                    f'<details style="background:{bg};border-radius:8px;padding:4px 12px;margin:4px 0;'
                    f'border-left:3px solid #e5c07b;font-size:13px;color:#9ca3af">'
                    f'<summary style="cursor:pointer;padding:6px 0"><strong style="color:{color}">[{prefix}]</strong> '
                    f'{first_line} …</summary>'
                    f'<div style="padding:8px 0;border-top:1px solid #e5e7eb;margin-top:4px">{tool_body}</div>'
                    f'</details>'
                )
            elif msg.role == "user":
                content = _h.escape(msg.content).replace("\n", "<br>")
                msgs_html.append(
                    f'<div style="background:{bg};border-radius:8px;padding:12px;margin:8px 0;">'
                    f'<strong style="color:{color}">[{prefix}]</strong><br>{content}</div>'
                )
            else:
                rendered = _render_md(msg.content)
                msgs_html.append(
                    f'<div style="background:{bg};border-radius:8px;padding:12px;margin:8px 0;">'
                    f'<strong style="color:{color}">[{prefix}]</strong>{rendered}</div>'
                )
        meta = f"{session.framework.value} | {session.message_count} 条消息"
        if session.workspace:
            meta += f" | {session.workspace}"
        return _html_wrap(
            session.display_title,
            f'<h1>{_h.escape(session.display_title)}</h1>'
            f'<div class="meta">{meta}</div>'
            + "\n".join(msgs_html),
        )

    lines = [
        session.display_title,
        f"框架: {session.framework.value} | 消息: {session.message_count}",
        "=" * 60,
        "",
    ]
    for msg in (session.messages or []):
        prefix = role_cn.get(msg.role, msg.role)
        lines.append(f"[{prefix}]")
        lines.append(msg.content)
        lines.append("")
    return "\n".join(lines)


# ── assets ─────────────────────────────────────────────────

def _asset_to_dict(asset) -> dict:
    return {
        "id": asset.id,
        "name": asset.name,
        "type": asset.type.value if hasattr(asset.type, "value") else str(asset.type),
        "artifact_path": str(asset.artifact_path),
        "source_path": str(asset.source_path) if asset.source_path else None,
        "description": asset.description,
        "project": asset.project,
        "tags": list(asset.tags) if asset.tags else [],
        "valid": asset.valid,
        "created_at": asset.created_at.isoformat() if asset.created_at else None,
    }


def format_assets(assets, fmt: str) -> str:
    if fmt == "JSON":
        return json.dumps([_asset_to_dict(a) for a in assets], ensure_ascii=False, indent=2)
    if fmt == "Markdown":
        lines = ["# 资产列表", "", f"共 {len(assets)} 项", ""]
        for a in assets:
            status = "[有效]" if a.valid else "[失效]"
            atype = a.type.value if hasattr(a.type, "value") else str(a.type)
            lines.append(f"## {status} {a.name}")
            lines.append(f"- **类型**: {atype}")
            lines.append(f"- **路径**: `{a.artifact_path}`")
            if a.description:
                lines.append(f"- **描述**: {a.description}")
            if a.project:
                lines.append(f"- **项目**: {a.project}")
            lines.append("")
        return "\n".join(lines)
    if fmt == "HTML":
        import html as _h
        cards = []
        for a in assets:
            status = "[有效]" if a.valid else "[失效]"
            atype = a.type.value if hasattr(a.type, "value") else str(a.type)
            desc = _h.escape(a.description or "无描述")
            cards.append(
                f'<div class="card">'
                f'<h2>{status} {_h.escape(a.name)}</h2>'
                f'<div class="meta"><strong>{atype}</strong> | '
                f'<code>{_h.escape(str(a.artifact_path))}</code></div>'
                f'<p>{desc}</p></div>'
            )
        return _html_wrap("资产列表", f"<h1>资产列表（{len(assets)} 项）</h1>" + "\n".join(cards))
    lines = [f"资产列表 ({len(assets)} 项)", "=" * 60, ""]
    for a in assets:
        status = "[有效]" if a.valid else "[失效]"
        atype = a.type.value if hasattr(a.type, "value") else str(a.type)
        lines.append(f"{status} {a.name} ({atype})")
        lines.append(f"  路径: {a.artifact_path}")
        if a.description:
            lines.append(f"  描述: {a.description}")
        lines.append("")
    return "\n".join(lines)


# ── session list / meta ────────────────────────────────────

def format_session_list(sessions, fmt: str) -> str:
    """导出会话列表（元信息，不含完整消息）"""
    if fmt == "JSON":
        data = []
        for s in sessions:
            data.append({
                "id": s.id, "title": s.title, "framework": s.framework.value,
                "workspace": s.workspace, "message_count": s.message_count,
                "created_at": s.created_at.isoformat() if s.created_at else None,
                "updated_at": s.updated_at.isoformat() if s.updated_at else None,
                "file_path": str(s.file_path),
            })
        return json.dumps(data, ensure_ascii=False, indent=2)

    if fmt == "Markdown":
        lines = [f"# 会话记录（{len(sessions)} 个）", ""]
        for s in sessions:
            t = s.display_time or ""
            lines.append(f"## {s.display_title}")
            lines.append(f"- **框架**: {s.framework.value}")
            if s.workspace:
                lines.append(f"- **工作区**: {s.workspace}")
            lines.append(f"- **消息数**: {s.message_count}")
            if t:
                lines.append(f"- **时间**: {t}")
            lines.append("")
        return "\n".join(lines)

    if fmt == "HTML":
        import html as _h
        rows = []
        for s in sessions:
            rows.append(
                f"<tr><td>{_h.escape(s.display_title)}</td>"
                f"<td>{s.framework.value}</td>"
                f"<td>{s.workspace or ''}</td>"
                f"<td>{s.message_count}</td>"
                f"<td>{s.display_time}</td></tr>"
            )
        table = (
            '<table><thead><tr><th>标题</th><th>框架</th><th>工作区</th>'
            '<th>消息数</th><th>时间</th></tr></thead><tbody>'
            + "\n".join(rows) + "</tbody></table>"
        )
        return _html_wrap("会话记录", f"<h1>会话记录（{len(sessions)} 个）</h1>{table}")

    lines = [f"会话记录 ({len(sessions)} 个)", "=" * 60, ""]
    for s in sessions:
        lines.append(f"[{s.framework.value}] {s.display_title}")
        lines.append(f"  消息: {s.message_count} | 时间: {s.display_time}")
        if s.workspace:
            lines.append(f"  工作区: {s.workspace}")
        lines.append("")
    return "\n".join(lines)


def session_meta_txt(session, fmt: str) -> str:
    """仅导出会话元信息（未加载完整消息时）"""
    if fmt == "JSON":
        return json.dumps({
            "id": session.id, "title": session.title,
            "framework": session.framework.value,
            "workspace": session.workspace,
            "message_count": session.message_count,
            "created_at": session.created_at.isoformat() if session.created_at else None,
            "file_path": str(session.file_path),
        }, ensure_ascii=False, indent=2)
    if fmt == "Markdown":
        lines = [f"# {session.display_title}", "",
                 f"- **框架**: {session.framework.value}",
                 f"- **消息数**: {session.message_count}",
                 f"- **文件**: `{session.file_path}`"]
        if session.workspace:
            lines.insert(3, f"- **工作区**: {session.workspace}")
        return "\n".join(lines)
    if fmt == "HTML":
        import html as _h
        return _html_wrap(session.display_title,
                          f"<h1>{_h.escape(session.display_title)}</h1>"
                          f'<div class="meta">{session.framework.value} | '
                          f'{session.message_count} 条消息</div>')
    return f"{session.display_title}\n框架: {session.framework.value}\n消息: {session.message_count}"
