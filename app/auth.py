"""APIキー認証・レート制限ユーティリティ"""

import hashlib
import logging
import secrets
from typing import Optional

from fastapi import HTTPException, Header

from app.config import settings
from app.db import get_supabase

logger = logging.getLogger(__name__)


def generate_api_key() -> str:
    """mhub_ プレフィックス付きAPIキーを生成"""
    return f"mhub_{secrets.token_urlsafe(32)}"


def _require_api_key(x_api_key: Optional[str]) -> None:
    """APIキーヘッダーの存在チェック（両verify関数で共用）"""
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header. Register at POST /auth/register",
        )


def hash_api_key(raw_key: str) -> str:
    """APIキーをSHA256でハッシュ化してDBに保存する形式に変換"""
    return hashlib.sha256(raw_key.encode()).hexdigest()


async def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> dict:
    """
    APIキー認証 + レート制限チェック（FastAPI Depends用）。

    Supabase RPC `increment_api_key_usage` で以下を1トランザクションで実行:
      - キーの有効性チェック
      - 月次リセット（月が変わっていれば req_count を 0 に戻す）
      - レート制限チェック
      - req_count のアトミックなインクリメント
    """
    _require_api_key(x_api_key)

    key_hash = hash_api_key(x_api_key)

    try:
        result = get_supabase().rpc(
            "increment_api_key_usage", {"p_key_hash": key_hash}
        ).execute()
    except Exception as e:
        logger.error("RPC increment_api_key_usage failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    data = result.data

    if data is None:
        raise HTTPException(
            status_code=401,
            detail="Invalid or inactive API key. Register at POST /auth/register",
        )

    if data.get("status") == "rate_limited":
        raise HTTPException(
            status_code=429,
            detail=(
                f"Monthly request limit reached ({data['req_limit']} requests). "
                f"Upgrade your plan at {settings.api_base_url}/docs"
            ),
        )

    return data


async def verify_api_key_readonly(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> dict:
    """
    APIキー認証のみ（req_count をインクリメントしない）。
    GET /auth/usage など「確認系」エンドポイント専用。
    """
    _require_api_key(x_api_key)

    key_hash = hash_api_key(x_api_key)

    try:
        result = get_supabase().table("api_keys").select(
            "user_email,plan,req_count,req_limit,last_reset_at,created_at"
        ).eq("key_hash", key_hash).eq("is_active", True).execute()
    except Exception as e:
        logger.error("api_keys lookup failed: %s", e, exc_info=True)
        raise HTTPException(status_code=503, detail="Service temporarily unavailable")

    if not result.data:
        raise HTTPException(
            status_code=401,
            detail="Invalid or inactive API key. Register at POST /auth/register",
        )

    return result.data[0]
