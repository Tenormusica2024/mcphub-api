"""GitHub API を使った MCP サーバー・Claude Skills クローラー"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import TypedDict

import httpx
from supabase import Client

from app.config import settings
from app.constants import TOOL_TYPE_MCP, TOOL_TYPE_CLAUDE_SKILL, ToolType
from app.db import get_supabase

logger = logging.getLogger(__name__)

# MCPサーバーを発見するためのGitHub検索クエリ群
MCP_SEARCH_QUERIES = [
    "topic:mcp-server",
    "topic:model-context-protocol",
    "mcp server in:name,description",
    "model context protocol server in:name,description",
    "mcp-server in:name",
]

# Claude Skillsを発見するためのGitHub検索クエリ群
CLAUDE_SKILLS_QUERIES = [
    "topic:claude-skill",
    "topic:claude-code-skill",
    "topic:claude-code-skills",
    "claude code skill in:name,description",
    "claude-code skill in:name",
]

GITHUB_API_BASE = "https://api.github.com"
HEADERS_BASE = {
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}


class RepoData(TypedDict):
    """GitHub Search API のリポジトリデータ"""
    html_url: str
    name: str
    description: str | None
    stargazers_count: int
    topics: list[str]
    archived: bool
    owner: dict


def _get_rotating_token(index: int) -> str | None:
    """インデックスに応じてGitHubトークンをローテーション"""
    tokens = settings.github_token_list()
    if not tokens:
        return None
    return tokens[index % len(tokens)]


def _make_headers(token_index: int = 0) -> dict:
    headers = dict(HEADERS_BASE)
    token = _get_rotating_token(token_index)
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


async def _search_repos(
    client: httpx.AsyncClient,
    query: str,
    max_results: int,
    token_index: int,
) -> list[RepoData]:
    """GitHub Search APIでリポジトリを検索して返す"""
    repos: list[RepoData] = []
    page = 1
    per_page = 100
    # トークン数 + 2: 全トークンを試した上でさらに2回バッファを持たせる
    max_retries_on_403 = max(len(settings.github_token_list()), 1) + 2
    retries_on_403 = 0

    while len(repos) < max_results:
        url = f"{GITHUB_API_BASE}/search/repositories"
        params = {
            "q": query,
            "sort": "stars",
            "order": "desc",
            "per_page": per_page,
            "page": page,
        }
        try:
            resp = await client.get(url, headers=_make_headers(token_index), params=params)
            if resp.status_code == 403:
                # レート制限 → 別トークンでリトライ（上限を超えたら中断）
                retries_on_403 += 1
                if retries_on_403 >= max_retries_on_403:
                    logger.warning("GitHub 403 rate limit exceeded after %d retries, stopping query: %s", retries_on_403, query)
                    break
                token_index += 1
                await asyncio.sleep(2)
                continue
            resp.raise_for_status()
            data = resp.json()
            items = data.get("items", [])
            if not items:
                break
            repos.extend(items)
            if len(items) < per_page or len(repos) >= max_results:
                break
            page += 1
            await asyncio.sleep(0.5)  # レート制限対策
        except httpx.HTTPStatusError as e:
            logger.warning("GitHub API HTTP error for query '%s': %s", query, e)
            break
        except Exception as e:
            logger.error("Unexpected error during GitHub search for query '%s': %s", query, e, exc_info=True)
            break

    return repos[:max_results]


def _classify_category(topics: list[str], name: str, description: str) -> str:
    """トピック・名前・説明からカテゴリを推定"""
    text = " ".join(topics + [name, description or ""]).lower()
    if any(w in text for w in ["database", "db", "postgres", "sqlite", "mysql", "supabase"]):
        return "database"
    # "web" は汎用すぎるため除外。ブラウザ自動化ツール固有のキーワードのみを使用
    if any(w in text for w in ["browser", "playwright", "puppeteer", "selenium", "headless", "screenshot"]):
        return "browser"
    if any(w in text for w in ["filesystem", "file", "disk", "storage", "s3"]):
        return "filesystem"
    if any(w in text for w in ["github", "gitlab", "git", "code", "repo"]):
        return "code"
    if any(w in text for w in ["slack", "discord", "email", "gmail", "notion", "calendar"]):
        return "productivity"
    if any(w in text for w in ["api", "rest", "http", "openapi"]):
        return "api"
    if any(w in text for w in ["search", "bing", "google", "brave"]):
        return "search"
    return "other"


async def _crawl_and_save(
    queries: list[str],
    tool_type: ToolType,
    max_count: int,
    db: Client,
) -> dict:
    """共通クロール＆Supabase保存ロジック（MCP・Claude Skills で共用）"""
    start_time = time.time()
    all_repos: dict[str, RepoData] = {}  # repo_url → repo_data（重複排除）

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, query in enumerate(queries):
            repos = await _search_repos(
                client,
                query,
                max_results=max_count,
                token_index=i,
            )
            for repo in repos:
                url = repo.get("html_url", "")
                if url and url not in all_repos:
                    all_repos[url] = repo
            if len(all_repos) >= max_count:
                break
            await asyncio.sleep(1)

    repos_to_process = list(all_repos.values())[:max_count]

    # upsert前の件数を tool_type でフィルタして取得
    try:
        count_before = (
            db.table("mcp_servers")
            .select("*", count="exact", head=True)
            .eq("tool_type", tool_type)
            .execute()
            .count or 0
        )
    except Exception as e:
        logger.warning("count_before query failed, defaulting to 0: %s", e)
        count_before = 0

    records = []
    for repo in repos_to_process:
        topics = repo.get("topics", [])
        name = repo.get("name", "")
        description = repo.get("description") or ""
        owner = repo.get("owner", {}).get("login", "")
        repo_url = repo.get("html_url", "")

        records.append({
            "name": name,
            "repo_url": repo_url,
            "description": description[:500] if description else None,  # 500文字制限
            # claude_skill は MCP 向け分類器が "code" に偏重するため "other" で固定
            "category": _classify_category(topics, name, description) if tool_type == TOOL_TYPE_MCP else "other",
            "stars": repo.get("stargazers_count", 0),
            "owner": owner,
            "repo_name": name,
            "topics": topics,
            "is_active": not repo.get("archived", False),
            "tool_type": tool_type,
            "last_crawled_at": datetime.now(timezone.utc).isoformat(),
        })

    # 100件チャンクでバルクupsert（500個別往復 → 最大5往復に削減）
    for i in range(0, len(records), 100):
        chunk = records[i:i + 100]
        try:
            db.table("mcp_servers").upsert(chunk, on_conflict="repo_url").execute()
        except Exception as e:
            logger.warning(
                "DB bulk upsert failed for chunk %d-%d: %s: %s",
                i, i + len(chunk) - 1, type(e).__name__, e, exc_info=True,
            )

    # upsert後の件数で新規追加数を算出
    try:
        count_after = (
            db.table("mcp_servers")
            .select("*", count="exact", head=True)
            .eq("tool_type", tool_type)
            .execute()
            .count or 0
        )
    except Exception as e:
        logger.warning("count_after query failed, defaulting to count_before: %s", e)
        count_after = count_before

    new_count = max(count_after - count_before, 0)
    # 並走クローラーによる count 乖離で負値にならないよう max(0, ...) でガード
    updated_count = max(len(repos_to_process) - new_count, 0)
    duration = time.time() - start_time

    return {
        "total_found": len(repos_to_process),
        "new_servers": new_count,
        "updated_servers": updated_count,
        "total_in_db": count_after,
        "duration_sec": round(duration, 2),
    }


async def crawl_mcp_servers(max_servers: int | None = None) -> dict:
    """GitHub APIからMCPサーバーを収集してSupabaseに保存"""
    max_servers = max_servers or settings.crawl_max_servers
    db = get_supabase()
    return await _crawl_and_save(MCP_SEARCH_QUERIES, TOOL_TYPE_MCP, max_servers, db)


async def crawl_claude_skills(max_skills: int | None = None) -> dict:
    """GitHub APIからClaude Skillsを収集してSupabaseに保存"""
    max_skills = max_skills or settings.crawl_max_servers
    db = get_supabase()
    return await _crawl_and_save(CLAUDE_SKILLS_QUERIES, TOOL_TYPE_CLAUDE_SKILL, max_skills, db)
