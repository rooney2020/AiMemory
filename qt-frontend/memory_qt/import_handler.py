"""导入处理 — 从 ZIP 文件导入记忆和资产的统一入口"""

from PyQt5.QtWidgets import QWidget, QFileDialog, QMessageBox

from .components.exporter import parse_import_zip, do_import

_TYPE_CN = {"episodic": "会话摘要", "semantic": "笔记", "procedural": "偏好"}


def _build_confirm_message(parsed: dict) -> str:
    """构建导入确认对话框的消息文本"""
    mem_count = len(parsed["memories"])
    asset_count = len(parsed["assets"])
    session_count = parsed["session_count"]

    msg_parts = ["检测到以下内容：\n"]
    if mem_count:
        types_count = {}
        for m in parsed["memories"]:
            t = m.type.value
            types_count[t] = types_count.get(t, 0) + 1
        for t, c in types_count.items():
            msg_parts.append(f"  - {_TYPE_CN.get(t, t)}: {c} 条")
    if asset_count:
        msg_parts.append(f"  - 资产: {asset_count} 项")
    if session_count:
        msg_parts.append(f"  - 会话记录: {session_count} 个 (不导入)")
    if parsed["errors"]:
        msg_parts.append(f"\n[警告] 解析警告: {len(parsed['errors'])} 条")
    msg_parts.append("\n已存在的记录将自动跳过。确认导入？")
    return "\n".join(msg_parts)


def _build_result_message(stats: dict) -> str:
    """构建导入结果消息"""
    parts = ["导入完成："]
    if stats["mem_new"]:
        parts.append(f"  新增记忆: {stats['mem_new']} 条")
    if stats["mem_skipped"]:
        parts.append(f"  跳过已存在记忆: {stats['mem_skipped']} 条")
    if stats["asset_new"]:
        parts.append(f"  新增资产: {stats['asset_new']} 项")
    if stats["asset_skipped"]:
        parts.append(f"  跳过已存在资产: {stats['asset_skipped']} 项")
    if stats["errors"]:
        parts.append(f"  错误: {len(stats['errors'])} 条")
        for e in stats["errors"][:5]:
            parts.append(f"    - {e}")
    return "\n".join(parts)


def import_from_path(bridge, path: str, parent: QWidget = None) -> bool:
    """从指定路径执行导入流程，返回是否成功执行"""
    parsed = parse_import_zip(path)

    if parsed["errors"]:
        for err in parsed["errors"]:
            if "不支持导入" in err:
                QMessageBox.warning(parent, "格式不支持", err)
                return False

    mem_count = len(parsed["memories"])
    asset_count = len(parsed["assets"])

    if mem_count == 0 and asset_count == 0:
        QMessageBox.information(parent, "无可导入内容", "ZIP 中没有找到可导入的记忆或资产。")
        return False

    confirm_msg = _build_confirm_message(parsed)
    reply = QMessageBox.question(
        parent, "确认导入", confirm_msg,
        QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes,
    )
    if reply != QMessageBox.Yes:
        return False

    stats = do_import(bridge, parsed["memories"], parsed["assets"], parent)
    result_msg = _build_result_message(stats)
    QMessageBox.information(parent, "导入结果", result_msg)
    return True


def import_from_dialog(bridge, parent: QWidget = None) -> bool:
    """打开文件对话框选择 ZIP 并导入，返回是否成功执行"""
    path, _ = QFileDialog.getOpenFileName(
        parent, "选择导入文件", "", "ZIP 压缩文件 (*.zip)"
    )
    if not path:
        return False
    return import_from_path(bridge, path, parent)
