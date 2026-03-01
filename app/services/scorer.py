"""スコアリングサービス: ツールの quality_score を4次元で計算する

スコア設計（壁打ちで確定した仕様）:
  popularity      (25%): stars + forks の人気度
  velocity        (25%): 直近7日のスター増加 + 最終プッシュ日からの鮮度
  maintenance     (25%): open_issues の少なさ（少ないほど高得点）
  content_quality (25%): Claude Code によるSKILL.md品質評価（初期値 0）

newcomer_boost:
  登録30日以内のツールは velocity スコアを 1.5 倍（上限 100）にする。
  新規ツールが stars 不足で不当に低評価になる「冷え問題」への対策。
"""

import math
from datetime import datetime, timezone

# 正規化基準値（「この値で 50 点」となる目安）
# Claude Skills は stars=50 前後が現実的な主戦場なので小さめに設定
_STAR_MIDPOINT    = 50    # 50 stars で 50 点、100 stars で ~80 点
_FORK_MIDPOINT    = 20    # 20 forks で 50 点
_VELOCITY_MAX     = 50    # 直近7日で +50 stars = 100 点
_FRESHNESS_MAX    = 30    # 30 日以内プッシュ = 100 点（30 日超は線形減衰）

# newcomer boost
_NEWCOMER_DAYS         = 30
_NEWCOMER_MULTIPLIER   = 1.5

# 重み（合計 1.0）
_WEIGHTS = {
    "popularity":       0.25,
    "velocity":         0.25,
    "maintenance":      0.25,
    "content_quality":  0.25,
}


def _normalize(value: float, max_val: float) -> float:
    """線形正規化: 0〜max_val を 0〜100 に変換（max_val 超はクリップ）"""
    if max_val <= 0:
        return 0.0
    return min(100.0, (value / max_val) * 100.0)


def _sigmoid(value: float, midpoint: float) -> float:
    """シグモイド正規化: midpoint の値が 50 点になるよう設計
    外れ値（超人気リポジトリ）の影響を抑えるために使用する。
    """
    if midpoint <= 0:
        return 0.0
    k = math.log(99) / midpoint  # 0→100 の急峻さ
    return round(100.0 / (1.0 + math.exp(-k * (value - midpoint))), 2)


def _popularity_score(stars: int, fork_count: int) -> float:
    """人気スコア: stars (70%) + forks (30%)
    stars はシグモイドで外れ値を抑制する。
    """
    star_score = _sigmoid(stars, _STAR_MIDPOINT)
    fork_score = _sigmoid(fork_count, _FORK_MIDPOINT)
    return star_score * 0.7 + fork_score * 0.3


def _velocity_score(
    velocity_7d: int,
    pushed_at: datetime | None,
    created_at: datetime | None,
) -> float:
    """速度スコア: velocity_7d (60%) + プッシュ鮮度 (40%) + newcomer boost

    Args:
        velocity_7d: 直近7日のスター増加数（前回クロール値との差分）
        pushed_at: 最終コードプッシュ日時
        created_at: リポジトリ作成日時（newcomer boost 判定に使用）
    """
    now = datetime.now(timezone.utc)

    # velocity_7d スコア（線形正規化）
    v_score = _normalize(velocity_7d, _VELOCITY_MAX)

    # プッシュ鮮度スコア: 30 日以内なら高得点、それ以上は減衰
    if pushed_at:
        pushed_at_utc = pushed_at if pushed_at.tzinfo else pushed_at.replace(tzinfo=timezone.utc)
        days_since_push = max(0, (now - pushed_at_utc).days)
        freshness = _normalize(_FRESHNESS_MAX - days_since_push, _FRESHNESS_MAX)
    else:
        freshness = 0.0

    base = v_score * 0.6 + freshness * 0.4

    # newcomer boost: 登録 30 日以内は velocity を 1.5 倍
    if created_at:
        created_utc = created_at if created_at.tzinfo else created_at.replace(tzinfo=timezone.utc)
        days_since_created = (now - created_utc).days
        if days_since_created <= _NEWCOMER_DAYS:
            base = min(100.0, base * _NEWCOMER_MULTIPLIER)

    return base


def _maintenance_score(open_issues: int) -> float:
    """保守スコア: open_issues が少ないほど高得点
    個人開発・小規模プロジェクトを想定した分母設計:
      issues =  0: 100 点
      issues =  5:  80 点
      issues = 10:  67 点
      issues = 20:  50 点
      issues = 50:  29 点
      issues = 100: 17 点に漸近
    """
    if open_issues <= 0:
        return 100.0
    # 反比例関数: 100 / (1 + issues/20)
    return min(100.0, 100.0 / (1.0 + open_issues / 20.0))


def calc_scores(
    stars: int,
    fork_count: int,
    velocity_7d: int,
    open_issues: int,
    pushed_at: datetime | None,
    created_at: datetime | None,
    content_quality: float = 0.0,
) -> dict:
    """全スコアを計算してDBに保存する形式の辞書を返す

    Returns:
        {
          "quality_score": 78.5,
          "score_breakdown": {
              "popularity": 65.0,
              "velocity": 92.0,
              "maintenance": 80.0,
              "content_quality": 0.0
          }
        }
    """
    popularity  = _popularity_score(stars, fork_count)
    velocity    = _velocity_score(velocity_7d, pushed_at, created_at)
    maintenance = _maintenance_score(open_issues)

    total = (
        popularity       * _WEIGHTS["popularity"] +
        velocity         * _WEIGHTS["velocity"] +
        maintenance      * _WEIGHTS["maintenance"] +
        content_quality  * _WEIGHTS["content_quality"]
    )

    return {
        "quality_score": round(total, 2),
        "score_breakdown": {
            "popularity":      round(popularity, 1),
            "velocity":        round(velocity, 1),
            "maintenance":     round(maintenance, 1),
            "content_quality": round(content_quality, 1),
        },
    }
