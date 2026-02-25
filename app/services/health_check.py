"""MCP サーバーのヘルスチェックサービス（並列実行対応）"""

import asyncio
import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.db import get_supabase

# MCPサーバーが提供する可能性のある標準エンドポイント一覧
# （まずGitHub APIのping、次にリポジトリの公開URLを確認）
HEALTH_CHECK_PATHS = ["/health", "/", "/ping", "/status"]


async def _check_single_server(
    client: httpx.AsyncClient,
    server: dict,
) -> dict:
    """1サーバーのヘルスチェックを実行"""
    repo_url = server.get("repo_url", "")
    server_id = server.get("id")

    # GitHub リポジトリへのアクセス確認（リポジトリ自体の生存確認）
    # repo_url 例: https://github.com/owner/repo
    start_ms = time.time() * 1000

    status = "unknown"
    response_time_ms = None
    http_status = None
    error_message = None

    try:
        resp = await client.head(repo_url, follow_redirects=True)
        elapsed = int(time.time() * 1000 - start_ms)
        http_status = resp.status_code
        response_time_ms = elapsed

        if resp.status_code < 400:
            status = "up"
        elif resp.status_code == 404:
            status = "down"
            error_message = "Repository not found (404)"
        elif resp.status_code == 451:
            status = "down"
            error_message = "Repository unavailable (451)"
        else:
            status = "unknown"
            error_message = f"Unexpected status: {resp.status_code}"
    except httpx.TimeoutException:
        status = "down"
        error_message = "Timeout"
    except httpx.ConnectError:
        status = "down"
        error_message = "Connection failed"
    except Exception as e:
        status = "unknown"
        error_message = str(e)[:200]

    return {
        "server_id": server_id,
        "status": status,
        "response_time_ms": response_time_ms,
        "http_status": http_status,
        "error_message": error_message,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


async def run_health_checks(server_ids: list[str] | None = None) -> dict:
    """
    全サーバー（または指定サーバー）のヘルスチェックを並列実行。
    結果をhealth_checksテーブルに保存し、mcp_serversのis_activeを更新する。
    """
    db = get_supabase()
    concurrency = settings.health_check_concurrency
    timeout = settings.health_check_timeout_sec

    # 対象サーバーを取得
    query = db.table("mcp_servers").select("id,name,repo_url")
    if server_ids:
        query = query.in_("id", server_ids)
    else:
        query = query.eq("is_active", True)

    servers = query.execute().data or []

    if not servers:
        return {"checked": 0, "up": 0, "down": 0, "unknown": 0}

    results = []
    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_check(client: httpx.AsyncClient, server: dict) -> dict:
        async with semaphore:
            return await _check_single_server(client, server)

    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [bounded_check(client, s) for s in servers]
        results = await asyncio.gather(*tasks, return_exceptions=True)

    # 正常な結果のみ抽出
    valid_results = [r for r in results if isinstance(r, dict)]

    # health_checks テーブルに一括保存
    if valid_results:
        db.table("health_checks").insert(valid_results).execute()

    # サマリー集計
    up = sum(1 for r in valid_results if r["status"] == "up")
    down = sum(1 for r in valid_results if r["status"] == "down")
    unknown = sum(1 for r in valid_results if r["status"] == "unknown")

    return {
        "checked": len(valid_results),
        "up": up,
        "down": down,
        "unknown": unknown,
    }
