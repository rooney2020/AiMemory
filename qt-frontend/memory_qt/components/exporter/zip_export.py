"""ZIP 导出 — 全量数据打包导出（含 HTML 导航页）"""

import json
import re
import zipfile
from typing import Optional

from PyQt5.QtWidgets import QWidget, QFileDialog

from .formatters import (
    FORMATS, _EXT_MAP, _TYPE_CN,
    _render_md, _html_wrap,
    format_memory, format_session, format_assets,
    session_meta_txt,
)


def _safe_filename(name: str, max_len: int = 60) -> str:
    """将字符串转为安全的文件名"""
    name = re.sub(r'[\\/:*?"<>|\n\r\t]', '_', name).strip()
    if len(name) > max_len:
        name = name[:max_len]
    return name or "未命名"


def _build_navigator_html(memories_by_type: dict, assets: list, sessions: list) -> str:
    """生成带分类导航的单页 HTML 应用"""
    import html as _h

    all_data = {"categories": []}

    type_info = {
        "episodic": {"label": "会话摘要", "icon": "", "color": "#94e2d5"},
        "semantic": {"label": "笔记", "icon": "", "color": "#89b4fa"},
        "procedural": {"label": "偏好", "icon": "", "color": "#cba6f7"},
    }

    _type_dir = {"episodic": "会话摘要", "semantic": "笔记", "procedural": "偏好"}

    for mem_type, mems in memories_by_type.items():
        info = type_info.get(mem_type, {"label": mem_type, "icon": "", "color": "#cdd6f4"})
        dir_name = _type_dir.get(mem_type, mem_type)
        items = []
        for idx, m in enumerate(mems, 1):
            body = _render_md(m.content)
            fname = _safe_filename(m.summary or m.id[:12])
            items.append({
                "title": m.summary or "(无摘要)",
                "meta": f"强度 {m.strength:.1f} | 访问 {m.access_count} | {m.project or '无项目'}",
                "time": m.created_at.strftime("%Y-%m-%d %H:%M") if m.created_at else "",
                "body": body,
                "file": f"{dir_name}/{idx:03d}_{fname}.html",
            })
        all_data["categories"].append({
            "key": mem_type, "label": info["label"], "icon": info["icon"],
            "color": info["color"], "count": len(items), "items": items,
        })

    if assets:
        items = []
        for a in assets:
            atype = a.type.value if hasattr(a.type, "value") else str(a.type)
            status = "有效" if a.valid else "失效"
            items.append({
                "title": a.name,
                "meta": f"{atype} | {status} | {a.artifact_path}",
                "time": a.created_at.strftime("%Y-%m-%d %H:%M") if a.created_at else "",
                "body": f"<p>{_h.escape(a.description or '无描述')}</p>"
                        f"<p><strong>路径:</strong> <code>{_h.escape(a.artifact_path)}</code></p>"
                        + (f"<p><strong>项目:</strong> {_h.escape(a.project)}</p>" if a.project else "")
                        + (f"<p><strong>标签:</strong> {', '.join(a.tags)}</p>" if a.tags else ""),
                "file": "资产/资产列表.html",
            })
        all_data["categories"].append({
            "key": "assets", "label": "资产", "icon": "",
            "color": "#fab387", "count": len(items), "items": items,
        })

    if sessions:
        _PRV = 8
        _TRUNC = 400
        _role_cn = {"user": "用户", "assistant": "AI", "tool": "工具", "system": "系统"}
        _role_clr = {"user": "#89b4fa", "assistant": "#cdd6f4", "tool": "#585b70", "system": "#a6adc8"}
        items = []
        for idx, s in enumerate(sessions, 1):
            msgs = (s.messages or [])[:_PRV]
            if msgs:
                parts = []
                for msg in msgs:
                    rl = _role_cn.get(msg.role, msg.role)
                    clr = _role_clr.get(msg.role, "#cdd6f4")
                    if msg.role == "tool":
                        first_line = msg.content.strip().split("\n", 1)[0][:80]
                        parts.append(
                            f'<div style="margin:2px 0;padding:4px 10px;border-radius:4px;'
                            f'border-left:2px solid #f9e2af;color:#585b70;font-size:11px">'
                            f'[{rl}] {_h.escape(first_line)} …</div>'
                        )
                        continue
                    txt = msg.content
                    if len(txt) > _TRUNC:
                        txt = txt[:_TRUNC] + " ..."
                    txt = _h.escape(txt).replace("\n", "<br>")
                    bg = "#313244" if msg.role == "user" else "transparent"
                    parts.append(
                        f'<div style="margin:4px 0;padding:6px 10px;border-radius:6px;background:{bg}">'
                        f'<span style="color:{clr};font-weight:600;font-size:11px">[{rl}]</span> '
                        f'<span style="font-size:12px;line-height:1.5">{txt}</span></div>'
                    )
                total = len(s.messages or [])
                if total > _PRV:
                    parts.append(
                        f'<div style="color:#585b70;text-align:center;padding:6px;font-size:11px">'
                        f'... 共 {total} 条消息，显示前 {_PRV} 条 ...</div>'
                    )
                body = "".join(parts)
            else:
                body = f'<p style="color:#585b70">暂无消息内容（{s.message_count} 条消息元数据）</p>'
            fname = _safe_filename(s.display_title or s.id[:12])
            fw = s.framework.value
            items.append({
                "title": s.display_title,
                "meta": f"{fw} | {s.message_count} 条消息"
                        + (f" | {s.workspace}" if s.workspace else ""),
                "time": s.display_time or "",
                "body": body,
                "file": f"会话记录/{fw}/{idx:03d}_{fname}.html",
            })
        all_data["categories"].append({
            "key": "sessions", "label": "会话记录", "icon": "",
            "color": "#f9e2af", "count": len(items), "items": items,
        })

    data_json = json.dumps(all_data, ensure_ascii=False)
    from datetime import datetime
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    total = sum(c["count"] for c in all_data["categories"])

    return f"""<!DOCTYPE html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>AI Memory 导出 — {now_str}</title>
<style>
:root {{
  --bg:#1e1e2e;--mantle:#181825;--crust:#11111b;
  --s0:#313244;--s1:#45475a;--s2:#585b70;
  --text:#cdd6f4;--sub0:#a6adc8;--sub1:#bac2de;
  --blue:#89b4fa;--teal:#94e2d5;--green:#a6e3a1;
  --mauve:#cba6f7;--peach:#fab387;--yellow:#f9e2af;--red:#f38ba8;
}}
*{{margin:0;padding:0;box-sizing:border-box}}
body{{font-family:'Noto Sans CJK SC','Microsoft YaHei',sans-serif;background:var(--bg);color:var(--text);height:100vh;overflow:hidden}}
#app{{display:flex;flex-direction:column;height:100vh}}
header{{background:var(--mantle);padding:12px 24px;display:flex;align-items:center;gap:16px;border-bottom:1px solid var(--s0)}}
header h1{{font-size:18px;color:var(--blue);font-weight:700}}
header .stats{{color:var(--sub0);font-size:13px;margin-left:auto}}
.main{{display:flex;flex:1;overflow:hidden}}
nav{{width:200px;background:var(--mantle);border-right:1px solid var(--s0);padding:12px 8px;overflow-y:auto;flex-shrink:0}}
nav button{{width:100%;text-align:left;background:transparent;color:var(--sub0);border:none;border-radius:8px;padding:10px 12px;font-size:13px;cursor:pointer;display:flex;align-items:center;gap:8px;margin-bottom:2px}}
nav button:hover{{background:var(--s0)}}
nav button.active{{background:var(--s0);color:var(--text);font-weight:600}}
nav .icon{{font-size:16px}}
nav .badge{{margin-left:auto;background:var(--s1);color:var(--sub0);border-radius:10px;padding:1px 8px;font-size:11px}}
.content{{flex:1;display:flex;overflow:hidden}}
.list-panel{{width:360px;border-right:1px solid var(--s0);overflow-y:auto;padding:8px}}
.search-box{{width:100%;background:var(--s0);border:1px solid var(--s1);border-radius:8px;padding:8px 12px;color:var(--text);font-size:13px;margin-bottom:8px;outline:none}}
.search-box:focus{{border-color:var(--blue)}}
.card{{background:var(--s0);border-radius:10px;padding:12px 14px;margin-bottom:6px;cursor:pointer;transition:background .15s}}
.card:hover{{background:var(--s1)}}
.card.active{{background:var(--s1);border-left:3px solid var(--blue)}}
.card-title{{font-size:13px;font-weight:600;margin-bottom:4px;line-height:1.4}}
.card-meta{{font-size:11px;color:var(--sub0)}}
.card-time{{font-size:11px;color:var(--s2);margin-top:2px}}
.detail-panel{{flex:1;overflow-y:auto;padding:24px 32px}}
.detail-panel h1{{font-size:20px;color:var(--blue);margin-bottom:12px;border-bottom:2px solid var(--s1);padding-bottom:8px}}
.detail-panel .meta-bar{{background:var(--mantle);padding:10px 14px;border-radius:8px;font-size:12px;color:var(--sub0);margin-bottom:16px}}
.detail-panel .body{{line-height:1.7;font-size:14px}}
.detail-panel .body code{{background:var(--s0);padding:2px 6px;border-radius:4px;font-family:monospace;font-size:13px}}
.detail-panel .body pre{{background:var(--crust);border:1px solid var(--s1);border-radius:8px;padding:14px;overflow-x:auto;font-size:13px;line-height:1.4;margin:8px 0}}
.detail-panel .body pre code{{background:transparent;padding:0}}
.detail-panel .body table{{border-collapse:collapse;width:100%;margin:8px 0}}
.detail-panel .body th,.detail-panel .body td{{border:1px solid var(--s1);padding:8px 12px;text-align:left}}
.detail-panel .body th{{background:var(--mantle);font-weight:600}}
.detail-panel .body ul,.detail-panel .body ol{{padding-left:24px;margin:6px 0}}
.detail-panel .body h2{{color:var(--teal);font-size:16px;margin:16px 0 8px}}
.detail-panel .body h3{{color:var(--green);font-size:15px;margin:12px 0 6px}}
.detail-panel .body strong{{color:var(--peach)}}
.detail-panel .body a{{color:var(--blue)}}
.detail-panel .body blockquote{{border-left:3px solid var(--blue);padding-left:12px;color:var(--sub0);margin:8px 0}}
.empty{{color:var(--sub0);text-align:center;padding:60px 20px;font-size:14px}}
@media(max-width:900px){{nav{{width:56px}} nav button span,.badge{{display:none}} .list-panel{{width:260px}}}}
</style></head><body>
<div id="app">
<header><h1>AI Memory</h1><span class="stats">{total} 条记录 · 导出于 {now_str}</span></header>
<div class="main">
<nav id="nav"></nav>
<div class="content">
<div class="list-panel" id="list"><input class="search-box" id="search" placeholder="搜索..."><div id="cards"></div></div>
<div class="detail-panel" id="detail"><div class="empty">← 选择一条记录查看详情</div></div>
</div></div></div>
<script>
const D={data_json};
let cur=null,curIdx=-1,filtered=[];
const $=s=>document.querySelector(s);
function init(){{
  const nav=$('#nav');
  D.categories.forEach((c,i)=>{{
    const b=document.createElement('button');
    b.innerHTML=`<span class="icon">${{c.icon}}</span><span>${{c.label}}</span><span class="badge">${{c.count}}</span>`;
    b.onclick=()=>select(i);
    if(i===0)b.classList.add('active');
    nav.appendChild(b);
  }});
  if(D.categories.length)select(0);
  $('#search').addEventListener('input',e=>filter(e.target.value));
}}
function select(i){{
  cur=D.categories[i];curIdx=i;
  document.querySelectorAll('nav button').forEach((b,j)=>b.classList.toggle('active',j===i));
  $('#search').value='';
  filter('');
  $('#detail').innerHTML='<div class="empty">← 选择一条记录查看详情</div>';
}}
function filter(q){{
  q=q.toLowerCase();
  filtered=cur?cur.items.filter(it=>!q||it.title.toLowerCase().includes(q)||it.meta.toLowerCase().includes(q)):[];
  renderList();
}}
function renderList(){{
  const box=$('#cards');box.innerHTML='';
  if(!filtered.length){{box.innerHTML='<div class="empty">无匹配记录</div>';return;}}
  filtered.forEach((it,i)=>{{
    const d=document.createElement('div');d.className='card';
    d.innerHTML=`<div class="card-title">${{esc(it.title)}}</div><div class="card-meta">${{esc(it.meta)}}</div>`+(it.time?`<div class="card-time">${{it.time}}</div>`:'');
    d.onclick=()=>showDetail(it,d);
    box.appendChild(d);
  }});
}}
function showDetail(it,el){{
  document.querySelectorAll('.card').forEach(c=>c.classList.remove('active'));
  if(el)el.classList.add('active');
  let h=`<h1>${{esc(it.title)}}</h1><div class="meta-bar">${{esc(it.meta)}}`+(it.time?` · ${{it.time}}`:'')+`</div><div class="body">${{it.body}}</div>`;
  if(it.file)h+=`<div style="margin-top:16px;padding:10px 14px;background:var(--mantle);border-radius:8px;font-size:13px"><a href="${{it.file}}" style="color:var(--blue);text-decoration:none">查看完整内容 → ${{it.file}}</a></div>`;
  $('#detail').innerHTML=h;
}}
function esc(s){{const d=document.createElement('div');d.textContent=s;return d.innerHTML;}}
init();
</script></body></html>"""


def export_all_html_zip(
    memories_by_type: dict,
    assets: list,
    sessions: list,
    scanner,
    parent: QWidget = None,
) -> Optional[str]:
    """导出全部为 HTML ZIP (index.html + 分类子目录 + 各记录独立文件)"""
    from datetime import datetime
    from PyQt5.QtWidgets import QProgressDialog, QApplication

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_name = f"AI_Memory_导出_{timestamp}.zip"

    path, _ = QFileDialog.getSaveFileName(
        parent, "导出全部 (HTML)", default_name, "ZIP 压缩文件 (*.zip)"
    )
    if not path:
        return None

    total_steps = len(sessions) + 2
    progress = QProgressDialog("准备导出...", "取消", 0, total_steps, parent)
    progress.setWindowTitle("HTML 导出")
    progress.setMinimumDuration(0)
    progress.show()
    QApplication.processEvents()

    loaded_sessions = []
    for i, session in enumerate(sessions):
        if progress.wasCanceled():
            return None
        progress.setValue(i)
        title_short = (session.display_title or "")[:40]
        progress.setLabelText(f"加载会话 ({i+1}/{len(sessions)}): {title_short}")
        QApplication.processEvents()

        if not session.messages and scanner:
            try:
                session = scanner.load_messages(session)
            except Exception:
                pass
        loaded_sessions.append(session)

    progress.setLabelText("生成 HTML 文件...")
    progress.setValue(len(sessions))
    QApplication.processEvents()

    type_dir_map = {"episodic": "会话摘要", "semantic": "笔记", "procedural": "偏好"}

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for mem_type, mems in memories_by_type.items():
            dir_name = type_dir_map.get(mem_type, mem_type)
            for i, mem in enumerate(mems, 1):
                name = _safe_filename(mem.summary or mem.id[:12])
                filename = f"{dir_name}/{i:03d}_{name}.html"
                content = format_memory(mem, "HTML")
                zf.writestr(filename, content.encode("utf-8"))

        if assets:
            content = format_assets(assets, "HTML")
            zf.writestr("资产/资产列表.html", content.encode("utf-8"))

        for i, s in enumerate(loaded_sessions, 1):
            name = _safe_filename(s.display_title or s.id[:12])
            fw = s.framework.value
            filename = f"会话记录/{fw}/{i:03d}_{name}.html"
            if s.messages:
                content = format_session(s, "HTML")
            else:
                content = session_meta_txt(s, "HTML")
            zf.writestr(filename, content.encode("utf-8"))

        progress.setLabelText("生成导航页 index.html...")
        progress.setValue(len(sessions) + 1)
        QApplication.processEvents()

        index_html = _build_navigator_html(memories_by_type, assets, loaded_sessions)
        zf.writestr("index.html", index_html.encode("utf-8"))

    progress.close()
    return path


def export_all_as_zip(
    memories_by_type: dict,
    assets: list,
    sessions: list,
    fmt: str,
    parent: QWidget = None,
) -> Optional[str]:
    """全局导出：每条记录一个文件，分目录，zip 打包。"""
    from datetime import datetime

    ext = _EXT_MAP.get(fmt, ".txt")
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    default_name = f"AI_Memory_导出_{timestamp}.zip"

    path, _ = QFileDialog.getSaveFileName(
        parent, "导出全部", default_name, "ZIP 压缩文件 (*.zip)"
    )
    if not path:
        return None

    type_dir_map = {
        "episodic": "会话摘要",
        "semantic": "笔记",
        "procedural": "偏好",
    }

    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as zf:
        for mem_type, mems in memories_by_type.items():
            dir_name = type_dir_map.get(mem_type, mem_type)
            for i, mem in enumerate(mems, 1):
                name = _safe_filename(mem.summary or mem.id[:12])
                filename = f"{dir_name}/{i:03d}_{name}{ext}"
                content = format_memory(mem, fmt)
                zf.writestr(filename, content.encode("utf-8"))

        if assets:
            content = format_assets(assets, fmt)
            zf.writestr(f"资产/资产列表{ext}", content.encode("utf-8"))

        if sessions:
            for i, s in enumerate(sessions, 1):
                name = _safe_filename(s.display_title or s.id[:12])
                fw = s.framework.value
                filename = f"会话记录/{fw}/{i:03d}_{name}{ext}"
                content = format_session(s, fmt) if s.messages else session_meta_txt(s, fmt)
                zf.writestr(filename, content.encode("utf-8"))

    return path
