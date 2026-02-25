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
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header. Register at POST /auth/register",
        )

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
