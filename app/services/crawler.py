"""GitHub API を使った MCP サーバークローラー"""

import asyncio
import logging
import time
from datetime import datetime, timezone
from typing import TypedDict

import httpx

from app.config import settings
from app.db import get_supabase

logger = logging.getLogger(__name__)

# MCPサーバーを発見するためのGitHub検索クエリ群
SEARCH_QUERIES = [
    "topic:mcp-server",
    "topic:model-context-protocol",
    "mcp server in:name,description",
    "model context protocol server in:name,description",
    "mcp-server in:name",
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
                if retries_on_403 > max_retries_on_403:
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
    if any(w in text for w in ["browser", "playwright", "puppeteer", "selenium", "web"]):
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


async def crawl_mcp_servers(max_servers: int | None = None) -> dict:
    """GitHub APIからMCPサーバーを収集してSupabaseに保存"""
    max_servers = max_servers or settings.crawl_max_servers
    start_time = time.time()
    db = get_supabase()

    all_repos: dict[str, RepoData] = {}  # repo_url → repo_data（重複排除）

    async with httpx.AsyncClient(timeout=30.0) as client:
        for i, query in enumerate(SEARCH_QUERIES):
            repos = await _search_repos(
                client,
                query,
                max_results=max_servers,
                token_index=i,
            )
            for repo in repos:
                url = repo.get("html_url", "")
                if url and url not in all_repos:
                    all_repos[url] = repo
            if len(all_repos) >= max_servers:
                break
            await asyncio.sleep(1)

    repos_to_process = list(all_repos.values())[:max_servers]

    # upsert前の件数を取得（head=True でデータ転送なし・カウントのみ）
    count_before = (
        db.table("mcp_servers").select("*", count="exact", head=True).execute().count or 0
    )

    # 全レコードを先にリスト化
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
            "category": _classify_category(topics, name, description),
            "stars": repo.get("stargazers_count", 0),
            "owner": owner,
            "repo_name": name,
            "topics": topics,
            "is_active": not repo.get("archived", False),
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

    # upsert後の件数で新規追加数を算出（head=True でデータ転送なし）
    count_after = (
        db.table("mcp_servers").select("*", count="exact", head=True).execute().count or 0
    )
    new_count = max(count_after - count_before, 0)
    updated_count = len(repos_to_process) - new_count
    duration = time.time() - start_time

    return {
        "total_found": len(repos_to_process),
        "new_servers": new_count,
        "updated_servers": updated_count,
        "total_in_db": count_after,
        "duration_sec": round(duration, 2),
    }
