"""Pydantic レスポンスモデル定義"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class MCPServer(BaseModel):
    id: str
    name: str
    repo_url: str
    description: Optional[str] = None
    category: Optional[str] = None
    stars: int = 0
    owner: Optional[str] = None
    repo_name: Optional[str] = None
    topics: list[str] = []
    readme_summary: Optional[str] = None  # 将来機能（クローラー未実装・DB列は存在）
    is_active: bool = True
    health_check_opt_in: bool = False
    last_crawled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # ヘルスチェック情報（mcp_servers_with_health ビューから取得）
    health_status: Optional[str] = None
    last_response_time_ms: Optional[int] = None
    last_health_check_at: Optional[datetime] = None


class MCPServerList(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[MCPServer]


class CrawlResult(BaseModel):
    total_found: int
    new_servers: int
    updated_servers: int
    total_in_db: int
    duration_sec: float
