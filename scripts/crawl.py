"""
GitHub API クローラーをスタンドアロンで実行するスクリプト。
Cloud Scheduler や手動実行で使用する。

使い方:
    python scripts/crawl.py              # デフォルト（max 500件）
    python scripts/crawl.py --max 200    # 最大200件
    python scripts/crawl.py --health     # ヘルスチェックのみ実行
"""

import argparse
import asyncio
import sys
import os

# プロジェクトルートをパスに追加
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.services.crawler import crawl_mcp_servers
from app.services.health_check import run_health_checks


async def main():
    parser = argparse.ArgumentParser(description="MCPHub クローラー実行スクリプト")
    parser.add_argument("--max", type=int, default=500, help="収集する最大サーバー数")
    parser.add_argument("--health", action="store_true", help="ヘルスチェックのみ実行")
    args = parser.parse_args()

    if args.health:
        print("ヘルスチェック開始...")
        result = await run_health_checks()
        print(f"完了: {result}")
    else:
        print(f"クローリング開始（最大{args.max}件）...")
        result = await crawl_mcp_servers(max_servers=args.max)
        print(f"完了: {result}")
        print("\nヘルスチェック開始...")
        hc_result = await run_health_checks()
        print(f"完了: {hc_result}")


if __name__ == "__main__":
    asyncio.run(main())
