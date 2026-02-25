"""Supabase クライアント初期化

NOTE: グローバルシングルトンを使用しているため単体テストでのモックが困難。
      将来的には FastAPI の lifespan + Depends に移行して DI 可能にすること。
"""

from supabase import create_client, Client
from app.config import settings

_client: Client | None = None


def get_supabase() -> Client:
    """Supabaseクライアントを返す（遅延初期化）"""
    global _client
    if _client is None:
        _client = create_client(settings.supabase_url, settings.supabase_service_key)
    return _client
