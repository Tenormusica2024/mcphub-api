"""GitHub API を使った MCP サーバークローラー"""

import asyncio
import itertools
import time
from datetime import datetime, timezone

import httpx

from app.config import settings
from app.db import get_supabase

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
) -> list[dict]:
    """GitHub Search APIでリポジトリを検索して返す"""
    repos = []
    page = 1
    per_page = 100

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
                # レート制限 → 別トークンでリトライ
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
        except httpx.HTTPStatusError:
            break
        except Exception:
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

    all_repos: dict[str, dict] = {}  # repo_url → repo_data（重複排除）

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

    # Supabaseに保存
    new_count = 0
    updated_count = 0
    repos_to_process = list(all_repos.values())[:max_servers]

    for repo in repos_to_process:
        topics = repo.get("topics", [])
        name = repo.get("name", "")
        description = repo.get("description") or ""
        owner = repo.get("owner", {}).get("login", "")
        repo_url = repo.get("html_url", "")

        server_data = {
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
        }

        try:
            # upsert（既存ならupdate、なければinsert）
            result = db.table("mcp_servers").upsert(
                server_data,
                on_conflict="repo_url",
            ).execute()

            # 新規 or 更新を判別（supabaseはupsertで両方返す）
            if result.data:
                existing = db.table("mcp_servers").select("id").eq("repo_url", repo_url).execute()
                if len(existing.data) == 1:
                    # 既存レコードかどうかはcreated_atで判別しにくいのでとりあえずupdatedとして計上
                    updated_count += 1
        except Exception:
            pass

    # 実際の新規/更新数はupsertでは分離困難なため概算
    total_in_db = db.table("mcp_servers").select("id", count="exact").execute()
    duration = time.time() - start_time

    return {
        "total_found": len(repos_to_process),
        "new_servers": new_count,
        "updated_servers": updated_count,
        "total_in_db": total_in_db.count or 0,
        "duration_sec": round(duration, 2),
    }
