"""MCP サーバーのヘルスチェックサービス（並列実行対応）"""

import asyncio
import logging
import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.db import get_supabase

logger = logging.getLogger(__name__)

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
    結果を health_checks テーブルに保存し、mcp_servers.is_active を更新する。
    - up → is_active = True
    - down → is_active = False
    - unknown → 変更しない（一時的なエラーでアクティブ状態を失わせない）
    """
    db = get_supabase()
    concurrency = settings.health_check_concurrency
    timeout = settings.health_check_timeout_sec

    # 対象サーバーを取得（health_check_opt_in=true のサーバーのみ）
    query = db.table("mcp_servers").select("id,name,repo_url").eq("health_check_opt_in", True)
    if server_ids:
        query = query.in_("id", server_ids)
    else:
        query = query.eq("is_active", True)

    try:
        servers = query.execute().data or []
    except Exception as e:
        logger.error("health_check server list query failed: %s", e, exc_info=True)
        return {"checked": 0, "up": 0, "down": 0, "unknown": 0}

    if not servers:
        return {"checked": 0, "up": 0, "down": 0, "unknown": 0}

    semaphore = asyncio.Semaphore(concurrency)

    async def bounded_check(client: httpx.AsyncClient, server: dict) -> dict:
        async with semaphore:
            return await _check_single_server(client, server)

    async with httpx.AsyncClient(timeout=timeout) as client:
        tasks = [bounded_check(client, s) for s in servers]
        raw_results = await asyncio.gather(*tasks, return_exceptions=True)

    # 正常な結果のみ抽出（server_id が None のレコードも除外）
    valid_results = [
        r for r in raw_results if isinstance(r, dict) and r.get("server_id")
    ]

    # health_checks テーブルに一括保存
    if valid_results:
        try:
            db.table("health_checks").insert(valid_results).execute()
        except Exception as e:
            logger.error("health_checks INSERT failed: %s", e, exc_info=True)

    # mcp_servers.is_active を更新（up/down のみ、unknown は現状維持）
    up_ids = [r["server_id"] for r in valid_results if r["status"] == "up"]
    down_ids = [r["server_id"] for r in valid_results if r["status"] == "down"]
    try:
        if up_ids:
            db.table("mcp_servers").update({"is_active": True}).in_("id", up_ids).execute()
        if down_ids:
            db.table("mcp_servers").update({"is_active": False}).in_("id", down_ids).execute()
    except Exception as e:
        logger.error("mcp_servers is_active UPDATE failed: %s", e, exc_info=True)

    # サマリー集計
    up = len(up_ids)
    down = len(down_ids)
    unknown = sum(1 for r in valid_results if r["status"] == "unknown")

    return {
        "checked": len(valid_results),
        "up": up,
        "down": down,
        "unknown": unknown,
    }
