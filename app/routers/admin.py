"""管理者向け API（クローラー起動・ヘルスチェック起動）"""

import asyncio
import hmac
import logging
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Header, Query
from app.config import settings
from app.constants import TOOL_TYPE_MCP, TOOL_TYPE_CLAUDE_SKILL, VALID_CRAWL_TARGETS
from app.services.crawler import crawl_mcp_servers, crawl_claude_skills
from app.services.health_check import run_health_checks
from app.services.scorer_updater import update_all_scores
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
    tool_type: str = Query(
        default="all",
        description=f"クロール対象 ({'/'.join(sorted(VALID_CRAWL_TARGETS))})",
    ),
    _: str = Depends(verify_admin_key),
):
    """GitHub から MCP サーバー・Claude Skills を収集して DB に保存する"""
    if tool_type not in VALID_CRAWL_TARGETS:
        raise HTTPException(status_code=400, detail=f"Invalid tool_type. Valid: {sorted(VALID_CRAWL_TARGETS)}")

    # 実行するクローラーを決定
    labels: list[str] = []
    coros = []
    if tool_type in {"all", TOOL_TYPE_MCP}:
        labels.append(TOOL_TYPE_MCP)
        coros.append(crawl_mcp_servers(max_servers=max_servers))
    if tool_type in {"all", TOOL_TYPE_CLAUDE_SKILL}:
        labels.append(TOOL_TYPE_CLAUDE_SKILL)
        coros.append(crawl_claude_skills(max_skills=max_servers))

    # 両クローラーを並列実行（return_exceptions=True で片方失敗でも継続）
    raw = await asyncio.gather(*coros, return_exceptions=True)

    mcp_result = None
    skills_result = None
    for label, result in zip(labels, raw):
        if isinstance(result, Exception):
            logger.error("%s crawl failed: %s", label, result, exc_info=result)
        elif label == TOOL_TYPE_MCP:
            mcp_result = result
        else:
            skills_result = result

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


@router.post("/update-scores", summary="スコア再計算（管理者専用）")
async def trigger_score_update(_: str = Depends(verify_admin_key)):
    """全アクティブレコードの quality_score を再計算する。
    毎日クロール後に Task Scheduler から呼び出すことを想定している。
    """
    result = await update_all_scores()
    return result
