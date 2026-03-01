"""Pydantic レスポンスモデル定義"""

from datetime import datetime
from typing import Optional
from pydantic import BaseModel, EmailStr
from app.constants import TOOL_TYPE_MCP


class ScoreBreakdown(BaseModel):
    """quality_score の4次元内訳（0〜100）"""
    popularity:      float = 0.0  # stars + forks
    velocity:        float = 0.0  # 直近7日スター増加 + プッシュ鮮度
    maintenance:     float = 0.0  # open_issues の少なさ
    content_quality: float = 0.0  # Claude Code によるSKILL.md品質評価


class MCPServer(BaseModel):
    id: str
    name: str
    repo_url: str
    description: Optional[str] = None
    category: Optional[str] = None
    stars: int = 0
    fork_count: int = 0
    open_issues: int = 0
    owner: Optional[str] = None
    repo_name: Optional[str] = None
    topics: list[str] = []
    readme_summary: Optional[str] = None  # 将来機能（クローラー未実装・DB列は存在）
    tool_type: str = TOOL_TYPE_MCP  # 'mcp' または 'claude_skill'
    is_active: bool = True
    health_check_opt_in: bool = False
    pushed_at: Optional[datetime] = None
    last_crawled_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
    # スコアリング（scorer_updater.py が毎日更新）
    quality_score: float = 0.0
    velocity_7d: int = 0           # 直近7日のスター増加数
    score_breakdown: Optional[ScoreBreakdown] = None
    rank_in_category: Optional[int] = None
    score_updated_at: Optional[datetime] = None
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


class HealthCheckResult(BaseModel):
    checked: int
    up: int
    down: int
    unknown: int


class RegisterResponse(BaseModel):
    api_key: str
    plan: str
    monthly_limit: int
    warning: str
    usage: str


class UsageResponse(BaseModel):
    email: EmailStr
    plan: str
    req_count: int
    req_limit: int
    last_reset_at: Optional[datetime] = None
    created_at: Optional[datetime] = None
