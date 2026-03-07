"""スコア更新バッチ: 全アクティブレコードの quality_score を再計算する

実行タイミング（GitHub Actions で毎日 22:00 UTC）:
  POST /admin/update-scores

処理フロー:
  1. mcp_servers から全アクティブレコードを取得
  2. velocity_7d を「7日あたりのスター増加数」に正規化
     raw = stars - stars_7d_ago（前回更新時との差分）
     days = 前回 score_updated_at からの経過日数（初回は velocity=0）
     velocity_7d = round(raw / max(1, days) * 7)
  3. scorer.calc_scores() で quality_score と score_breakdown を計算
  4. 各レコードを更新（stars_7d_ago = stars も上書き → 次回計算用）
  5. カテゴリ別に rank_in_category を付与
  6. score_history に週次スナップショットを保存
"""

import asyncio
import logging
from datetime import datetime, timezone

from app.db import get_supabase
from app.services.scorer import calc_scores

logger = logging.getLogger(__name__)

# 週次スナップショット: この日数おきに score_history に記録する
_SNAPSHOT_INTERVAL_DAYS = 7


async def update_all_scores() -> dict:
    """全アクティブレコードのスコアを再計算して DB を更新する

    Returns:
        {"updated": N, "skipped": M, "errors": K, "duration_sec": float}
    """
    import time
    start = time.time()
    db = get_supabase()

    # is_active なレコードを全件取得（ページネーションでサーバー上限(1000)を回避）
    rows: list[dict] = []
    page_size = 1000
    offset = 0
    try:
        while True:
            result = (
                db.table("mcp_servers")
                .select(
                    "id, stars, fork_count, open_issues, stars_7d_ago, "
                    "pushed_at, created_at, score_breakdown, quality_score, score_updated_at"
                )
                .eq("is_active", True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            page = result.data or []
            rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
    except Exception as e:
        logger.error("Failed to fetch mcp_servers for scoring: %s", e, exc_info=True)
        return {"updated": 0, "skipped": 0, "errors": 1, "duration_sec": 0.0}
    logger.info("Scoring %d active records", len(rows))

    updated = 0
    skipped = 0
    errors = 0
    updates: list[dict] = []

    for row in rows:
        try:
            stars       = row.get("stars") or 0
            fork_count  = row.get("fork_count") or 0
            open_issues = row.get("open_issues") or 0
            stars_7d    = row.get("stars_7d_ago") or 0

            # velocity_7d: 前回更新からの経過日数で割り「7日あたり」に正規化する。
            # 初回採点（score_updated_at が NULL）は基準が不明なため 0 とする。
            raw_velocity = max(0, stars - stars_7d)
            prev_updated_at = _parse_dt(row.get("score_updated_at"))
            if prev_updated_at is None:
                velocity_7d = 0
            else:
                days_since = max(1, (datetime.now(timezone.utc) - prev_updated_at).days)
                velocity_7d = round(raw_velocity / days_since * 7)

            pushed_at  = _parse_dt(row.get("pushed_at"))
            created_at = _parse_dt(row.get("created_at"))

            # 前回の content_quality を引き継ぐ（Claude評価は週次で別途更新）
            prev_breakdown = row.get("score_breakdown") or {}
            content_quality = float(prev_breakdown.get("content_quality", 0.0))

            scores = calc_scores(
                stars=stars,
                fork_count=fork_count,
                velocity_7d=velocity_7d,
                open_issues=open_issues,
                pushed_at=pushed_at,
                created_at=created_at,
                content_quality=content_quality,
            )

            updates.append({
                "id":               row["id"],
                "quality_score":    scores["quality_score"],
                "score_breakdown":  scores["score_breakdown"],
                "velocity_7d":      velocity_7d,
                "stars_7d_ago":     stars,  # 次回の velocity 計算に使う
                "score_updated_at": datetime.now(timezone.utc).isoformat(),
            })
            updated += 1

        except Exception as e:
            logger.warning("Score calc failed for id=%s: %s", row.get("id"), e)
            errors += 1

    # 個別 update（upsert は default_to_null=True で NOT NULL 制約に抵触するため使わない）
    for record in updates:
        try:
            record_id = record["id"]
            score_fields = {k: v for k, v in record.items() if k != "id"}
            db.table("mcp_servers").update(score_fields).eq("id", record_id).execute()
        except Exception as e:
            logger.warning("Score update failed for id=%s: %s", record.get("id"), e)
            errors += 1
            updated -= 1

    # カテゴリ別 rank_in_category を付与
    await _update_ranks(db)

    # 週次スナップショット
    await _save_snapshot_if_needed(db)

    duration = round(time.time() - start, 2)
    logger.info(
        "Score update done: updated=%d skipped=%d errors=%d (%.2fs)",
        updated, skipped, errors, duration,
    )
    return {"updated": updated, "skipped": skipped, "errors": errors, "duration_sec": duration}


async def _update_ranks(db) -> None:
    """カテゴリ × tool_type ごとに quality_score 降順で rank_in_category を付与する"""
    # 全件取得（ページネーションでサーバー上限を回避）
    all_rows: list[dict] = []
    page_size = 1000
    offset = 0
    try:
        while True:
            result = (
                db.table("mcp_servers")
                .select("id, category, tool_type, quality_score")
                .eq("is_active", True)
                .order("quality_score", desc=True)
                .range(offset, offset + page_size - 1)
                .execute()
            )
            page = result.data or []
            all_rows.extend(page)
            if len(page) < page_size:
                break
            offset += page_size
    except Exception as e:
        logger.warning("rank fetch failed: %s", e)
        return

    # カテゴリ × tool_type グループごとにランクを計算
    group_counters: dict[tuple, int] = {}
    rank_updates: list[dict] = []

    for row in all_rows:
        key = (row.get("category") or "other", row.get("tool_type") or "")
        group_counters[key] = group_counters.get(key, 0) + 1
        rank_updates.append({"id": row["id"], "rank_in_category": group_counters[key]})

    for record in rank_updates:
        try:
            db.table("mcp_servers").update(
                {"rank_in_category": record["rank_in_category"]}
            ).eq("id", record["id"]).execute()
        except Exception as e:
            logger.warning("rank update failed for id=%s: %s", record.get("id"), e)


async def _save_snapshot_if_needed(db) -> None:
    """直近のスナップショットが _SNAPSHOT_INTERVAL_DAYS 以上前なら記録する"""
    try:
        latest = (
            db.table("score_history")
            .select("recorded_at")
            .order("recorded_at", desc=True)
            .limit(1)
            .execute()
        )
        if latest.data:
            last_dt = _parse_dt(latest.data[0]["recorded_at"])
            if last_dt:
                days_since = (datetime.now(timezone.utc) - last_dt).days
                if days_since < _SNAPSHOT_INTERVAL_DAYS:
                    logger.debug("Snapshot skipped (last: %d days ago)", days_since)
                    return
    except Exception as e:
        logger.warning("snapshot check failed: %s", e)

    # スナップショット保存（ページネーションで全件取得）
    try:
        snap_rows: list[dict] = []
        offset = 0
        while True:
            result = (
                db.table("mcp_servers")
                .select("id, quality_score, rank_in_category")
                .eq("is_active", True)
                .range(offset, offset + 999)
                .execute()
            )
            page = result.data or []
            snap_rows.extend(page)
            if len(page) < 1000:
                break
            offset += 1000
        snapshots = [
            {
                "server_id":        row["id"],
                "quality_score":    row.get("quality_score") or 0,
                "rank_in_category": row.get("rank_in_category"),
                "recorded_at":      datetime.now(timezone.utc).isoformat(),
            }
            for row in snap_rows
        ]
        for i in range(0, len(snapshots), 100):
            db.table("score_history").insert(snapshots[i:i + 100]).execute()
        logger.info("Snapshot saved: %d records", len(snapshots))
    except Exception as e:
        logger.warning("snapshot save failed: %s", e)


def _parse_dt(value) -> datetime | None:
    """文字列または datetime を UTC aware な datetime に変換する"""
    if value is None:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        return None


if __name__ == "__main__":
    import sys
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(update_all_scores())
