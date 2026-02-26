"""APIキー発行・利用状況確認エンドポイント"""

import logging
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr

from app.auth import generate_api_key, hash_api_key, verify_api_key_readonly
from app.db import get_supabase
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["auth"])

PLAN_LIMITS = {
    "free": 100,
    "basic": 5000,
    "pro": 30000,
    "enterprise": 0,  # 無制限（0 = 上限なし）
}


class RegisterRequest(BaseModel):
    email: EmailStr


@router.post("/register", summary="APIキー発行（無料）")
async def register(body: RegisterRequest):
    """
    メールアドレスを登録してAPIキーを発行します。
    APIキーは一度しか表示されません。紛失した場合は再登録が必要です。
    """
    db = get_supabase()

    # 同一メールアドレスの既存キーチェック
    existing = (
        db.table("api_keys")
        .select("id")
        .eq("user_email", body.email)
        .eq("is_active", True)
        .execute()
    )
    if existing.data:
        raise HTTPException(
            status_code=409,
            detail="This email is already registered. If you lost your key, contact support.",
        )

    raw_key = generate_api_key()
    try:
        db.table("api_keys").insert({
            "user_email": body.email,
            "key_hash": hash_api_key(raw_key),
            "plan": "free",
            "req_count": 0,
            "req_limit": PLAN_LIMITS["free"],
            "last_reset_at": datetime.now(timezone.utc).isoformat(),
            "is_active": True,
        }).execute()
    except Exception as e:
        logger.error("Failed to insert api_key for %s: %s", body.email, e, exc_info=True)
        raise HTTPException(status_code=503, detail="Failed to create API key. Please try again.")

    return {
        "api_key": raw_key,
        "plan": "free",
        "monthly_limit": PLAN_LIMITS["free"],
        "warning": "Save this API key - it will NOT be shown again.",
        "usage": "Add header: X-API-Key: <your_key>",
    }


@router.get("/usage", summary="API利用状況確認")
async def get_usage(record: dict = Depends(verify_api_key_readonly)):
    """現在のプランと今月の利用状況を返します。"""
    return {
        "email": record["user_email"],
        "plan": record["plan"],
        "req_count": record["req_count"],
        "req_limit": record["req_limit"],
        "last_reset_at": record["last_reset_at"],
        "created_at": record["created_at"],
    }
