"""MCP サーバー一覧・検索 API エンドポイント"""

import logging
import re
from typing import Optional
from uuid import UUID
from fastapi import APIRouter, Query, HTTPException, Depends
from app.auth import verify_api_key
from app.constants import VALID_TOOL_TYPES
from app.db import get_supabase
from app.models import MCPServer, MCPServerList

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/servers", tags=["servers"])

VALID_CATEGORIES = {"database", "browser", "filesystem", "code", "productivity", "api", "search", "other"}
VALID_SORT = {"stars", "name", "last_crawled_at", "quality_score", "velocity_7d"}
VALID_HEALTH = {"up", "down", "unknown"}


@router.get("", response_model=MCPServerList, summary="MCP サーバー・Claude Skills 一覧取得")
async def list_servers(
    category: Optional[str] = Query(None, description="カテゴリフィルタ"),
    q: Optional[str] = Query(None, description="名前・説明の部分一致検索"),
    health: Optional[str] = Query(None, description="ヘルスステータスフィルタ (up/down/unknown)"),
    tool_type: Optional[str] = Query(None, description="ツールタイプフィルタ (mcp/claude_skill)"),
    sort: str = Query("stars", description="ソート項目 (stars/name/last_crawled_at)"),
    page: int = Query(1, ge=1, description="ページ番号"),
    per_page: int = Query(20, ge=1, le=100, description="1ページの件数"),
    _: dict = Depends(verify_api_key),
):
    if category and category not in VALID_CATEGORIES:
        raise HTTPException(status_code=400, detail=f"Invalid category. Valid: {sorted(VALID_CATEGORIES)}")
    if sort not in VALID_SORT:
        raise HTTPException(status_code=400, detail=f"Invalid sort. Valid: {sorted(VALID_SORT)}")
    if health and health not in VALID_HEALTH:
        raise HTTPException(status_code=400, detail=f"Invalid health. Valid: {sorted(VALID_HEALTH)}")
    if tool_type and tool_type not in VALID_TOOL_TYPES:
        raise HTTPException(status_code=400, detail=f"Invalid tool_type. Valid: {sorted(VALID_TOOL_TYPES)}")

    db = get_supabase()
    offset = (page - 1) * per_page

    # mcp_servers_with_health ビューから取得
    query = db.table("mcp_servers_with_health").select("*", count="exact").eq("is_active", True)

    if tool_type:
        query = query.eq("tool_type", tool_type)
    if category:
        query = query.eq("category", category)
    if q:
        # 英数字・スペース・ハイフン・アンダースコアのみ許可（PostgREST構文バイパス防止）
        q_safe = re.sub(r"[^\w\s\-]", "", q.strip())[:100]
        # ILIKE の _ は「任意の1文字」ワイルドカードのため、リテラルとしてエスケープ
        q_safe = q_safe.replace("_", r"\_")
        if q_safe:
            query = query.or_(f"name.ilike.%{q_safe}%,description.ilike.%{q_safe}%")
    if health:
        query = query.eq("health_status", health)

    # ソート（数値系は降順、名前系は昇順）
    desc_sorts = {"stars", "quality_score", "velocity_7d"}
    query = query.order(sort, desc=(sort in desc_sorts))

    # ページネーション
    query = query.range(offset, offset + per_page - 1)

    try:
        result = query.execute()
    except Exception as e:
        logger.error("mcp_servers_with_health query failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    items = [MCPServer(**row) for row in (result.data or [])]

    return MCPServerList(
        total=result.count or 0,
        page=page,
        per_page=per_page,
        items=items,
    )


@router.get("/{server_id}", response_model=MCPServer, summary="MCP サーバー詳細取得")
async def get_server(
    server_id: UUID,
    _: dict = Depends(verify_api_key),
):
    db = get_supabase()
    try:
        result = db.table("mcp_servers_with_health").select("*").eq("id", str(server_id)).execute()
    except Exception as e:
        logger.error("mcp_servers_with_health lookup failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    if not result.data:
        raise HTTPException(status_code=404, detail="Server not found")
    return MCPServer(**result.data[0])


@router.get("/{server_id}/health-history", summary="ヘルスチェック履歴取得")
async def get_health_history(
    server_id: UUID,
    limit: int = Query(50, ge=1, le=200, description="取得件数"),
    _: dict = Depends(verify_api_key),
):
    db = get_supabase()
    # サーバー存在確認
    try:
        server = db.table("mcp_servers").select("id").eq("id", str(server_id)).execute()
    except Exception as e:
        logger.error("mcp_servers lookup failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    if not server.data:
        raise HTTPException(status_code=404, detail="Server not found")

    try:
        history = (
            db.table("health_checks")
            .select("*")
            .eq("server_id", str(server_id))
            .order("checked_at", desc=True)
            .limit(limit)
            .execute()
        )
    except Exception as e:
        logger.error("health_checks query failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")
    return {"server_id": str(server_id), "history": history.data or []}
