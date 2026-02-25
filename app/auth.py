"""APIキー認証・レート制限ユーティリティ"""

import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional

from fastapi import HTTPException, Header

from app.db import get_supabase


def generate_api_key() -> str:
    """mhub_ プレフィックス付きAPIキーを生成"""
    return f"mhub_{secrets.token_urlsafe(32)}"


def hash_api_key(raw_key: str) -> str:
    """APIキーをSHA256でハッシュ化してDBに保存する形式に変換"""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _is_new_month(last_reset_at: str) -> bool:
    """last_reset_at から月が変わっているか確認"""
    last = datetime.fromisoformat(last_reset_at.replace("Z", "+00:00"))
    now = datetime.now(timezone.utc)
    return (now.year, now.month) != (last.year, last.month)


async def verify_api_key(x_api_key: Optional[str] = Header(None, alias="X-API-Key")) -> dict:
    """
    APIキー認証 + レート制限チェック（FastAPI Depends用）。
    月が変わっていれば req_count をリセットしてからチェックする。
    """
    if not x_api_key:
        raise HTTPException(
            status_code=401,
            detail="Missing X-API-Key header. Register at POST /auth/register",
        )
    db = get_supabase()
    key_hash = hash_api_key(x_api_key)

    result = (
        db.table("api_keys")
        .select("*")
        .eq("key_hash", key_hash)
        .eq("is_active", True)
        .execute()
    )
    if not result.data:
        raise HTTPException(
            status_code=401,
            detail="Invalid or inactive API key. Register at POST /auth/register",
        )

    record = result.data[0]

    # 月次リセット（月が変わっていれば req_count を 0 に戻す）
    if _is_new_month(record["last_reset_at"]):
        db.table("api_keys").update({
            "req_count": 0,
            "last_reset_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", record["id"]).execute()
        record["req_count"] = 0

    # レート制限チェック
    if record["req_count"] >= record["req_limit"]:
        raise HTTPException(
            status_code=429,
            detail=(
                f"Monthly request limit reached ({record['req_limit']} requests). "
                "Upgrade your plan at https://mcphub-api-ycqe3vmjva-an.a.run.app/docs"
            ),
        )

    # リクエストカウントを加算
    db.table("api_keys").update(
        {"req_count": record["req_count"] + 1}
    ).eq("id", record["id"]).execute()

    return record
