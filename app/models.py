"""Pydantic レスポンスモデル定義"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel


class HealthStatus(BaseModel):
    status: str           # "up" | "down" | "unknown"
    response_time_ms: Optional[int] = None
    checked_at: Optional[datetime] = None


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
    readme_summary: Optional[str] = None
    is_active: bool = True
    health_check_opt_in: bool = True
    last_crawled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # ヘルスチェック情報（ビューから取得）
    health_status: Optional[str] = None
    last_response_time_ms: Optional[int] = None
    last_health_check_at: Optional[datetime] = None


class MCPServerList(BaseModel):
    total: int
    page: int
    per_page: int
    items: list[MCPServer]


class HealthCheckResult(BaseModel):
    server_id: str
    server_name: str
    repo_url: str
    status: str
    response_time_ms: Optional[int] = None
    http_status: Optional[int] = None
    error_message: Optional[str] = None
    checked_at: datetime


class CrawlResult(BaseModel):
    total_found: int
    new_servers: int
    updated_servers: int
    duration_sec: float
