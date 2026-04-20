"""AI Memory CLI 入口点 - 健康检查模式"""

import sys


def main():
    """健康检查入口，实际操作通过 cli.py 完成"""
    if "--check" in sys.argv or len(sys.argv) == 1:
        from .config import load_config
        from .storage.database import Database
        from .storage.memory_store import MemoryStore

        config = load_config()
        print(f"配置文件: {config.db_path}")

        try:
            db = Database(config.db_path)
            db.initialize()
            stats = MemoryStore(db).get_stats()
            print(f"数据库状态: ✅ 正常")
            print(f"  记忆: {stats['total']} (活跃: {stats['active']})")
            print(f"  资产: {stats['assets_total']} (有效: {stats['assets_valid']})")
            db.close()
        except Exception as e:
            print(f"数据库状态: ❌ {e}")
            sys.exit(1)
        return

    print("使用 cli.py 进行操作:")
    print("  python cli.py working       # 会话开始")
    print("  python cli.py remember      # 记忆")
    print("  python cli.py recall        # 检索")
    print("  python cli.py --help        # 帮助")


if __name__ == "__main__":
    main()
