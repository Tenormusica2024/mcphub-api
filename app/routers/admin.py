"""管理者向け API（クローラー起動・ヘルスチェック起動）"""

import hmac
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from app.config import settings
from app.constants import VALID_CRAWL_TARGETS
from app.services.crawler import crawl_mcp_servers, crawl_claude_skills
from app.services.health_check import run_health_checks
from app.models import CrawlResult, HealthCheckResult

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/admin", tags=["admin"])


def verify_admin_key(x_admin_key: Optional[str] = Header(None, alias="X-Admin-Key")):
    """管理者APIキー認証（タイミング攻撃対策: hmac.compare_digest使用）"""
    if not x_admin_key:
        raise HTTPException(status_code=401, detail="Missing X-Admin-Key header")
    if not hmac.compare_digest(x_admin_key, settings.admin_api_key):
        raise HTTPException(status_code=401, detail="Invalid admin key")
    return x_admin_key


@router.post("/crawl", summary="GitHub APIクローラー起動（管理者専用）", response_model=CrawlResult)
async def trigger_crawl(
    max_servers: int = Query(default=500, ge=1, le=1000, description="クロール最大件数"),
    tool_type: str = Query(default="all", description="クロール対象 (all/mcp/claude_skill)"),
    _: str = Depends(verify_admin_key),
):
    """GitHub から MCP サーバー・Claude Skills を収集して DB に保存する"""
    if tool_type not in VALID_CRAWL_TARGETS:
        raise HTTPException(status_code=400, detail=f"Invalid tool_type. Valid: {sorted(VALID_CRAWL_TARGETS)}")

    mcp_result = None
    skills_result = None

    # 各クローラーを個別に try/catch: 片方失敗でも他方の結果を返せるようにする
    if tool_type in {"all", "mcp"}:
        try:
            mcp_result = await crawl_mcp_servers(max_servers=max_servers)
        except Exception as e:
            logger.error("MCP crawl failed: %s", e, exc_info=True)
    if tool_type in {"all", "claude_skill"}:
        try:
            skills_result = await crawl_claude_skills(max_skills=max_servers)
        except Exception as e:
            logger.error("Claude Skills crawl failed: %s", e, exc_info=True)

    # 両方失敗した場合はエラー
    if mcp_result is None and skills_result is None:
        raise HTTPException(status_code=503, detail="All crawlers failed")

    # tool_type=all のとき両結果を合算して返す
    if mcp_result is not None and skills_result is not None:
        return CrawlResult(
            total_found=mcp_result["total_found"] + skills_result["total_found"],
            new_servers=mcp_result["new_servers"] + skills_result["new_servers"],
            updated_servers=mcp_result["updated_servers"] + skills_result["updated_servers"],
            total_in_db=mcp_result["total_in_db"] + skills_result["total_in_db"],
            duration_sec=round(mcp_result["duration_sec"] + skills_result["duration_sec"], 2),
        )
    result = mcp_result if mcp_result is not None else skills_result
    return CrawlResult(**result)


@router.post("/health-check", summary="ヘルスチェック起動（管理者専用）", response_model=HealthCheckResult)
async def trigger_health_check(_: str = Depends(verify_admin_key)):
    """全サーバーのヘルスチェックを並列実行する"""
    result = await run_health_checks()
    return result
