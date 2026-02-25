"""管理者向け API（クローラー起動・ヘルスチェック起動）"""

from fastapi import APIRouter, Depends, HTTPException, Header
from app.config import settings
from app.services.crawler import crawl_mcp_servers
from app.services.health_check import run_health_checks
from app.models import CrawlResult

router = APIRouter(prefix="/admin", tags=["admin"])


def verify_admin_key(x_admin_key: str = Header(..., alias="X-Admin-Key")):
    """管理者APIキー認証"""
    if x_admin_key != settings.admin_api_key:
        raise HTTPException(status_code=401, detail="Invalid admin key")
    return x_admin_key


@router.post("/crawl", summary="GitHub APIクローラー起動（管理者専用）")
async def trigger_crawl(
    max_servers: int = 500,
    _: str = Depends(verify_admin_key),
):
    """GitHub から MCP サーバーを収集して DB に保存する"""
    result = await crawl_mcp_servers(max_servers=max_servers)
    return result


@router.post("/health-check", summary="ヘルスチェック起動（管理者専用）")
async def trigger_health_check(_: str = Depends(verify_admin_key)):
    """全サーバーのヘルスチェックを並列実行する"""
    result = await run_health_checks()
    return result
