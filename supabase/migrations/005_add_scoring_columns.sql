-- Migration 005: スコアリング用カラムの追加
-- mcp_servers にスコアリングデータを追加し、score_history テーブルを新設する

ALTER TABLE mcp_servers
  -- GitHub API から取得できる追加メトリクス
  ADD COLUMN IF NOT EXISTS fork_count        INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS open_issues       INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS pushed_at         TIMESTAMPTZ,

  -- velocity 計算用（前回クロール時のスター数を記録）
  ADD COLUMN IF NOT EXISTS stars_7d_ago      INTEGER DEFAULT 0,
  ADD COLUMN IF NOT EXISTS velocity_7d       INTEGER DEFAULT 0,

  -- スコアリング結果
  ADD COLUMN IF NOT EXISTS quality_score     NUMERIC(6,2) DEFAULT 0,
  ADD COLUMN IF NOT EXISTS score_breakdown   JSONB,        -- 4次元スコアの詳細
  ADD COLUMN IF NOT EXISTS score_updated_at  TIMESTAMPTZ,
  ADD COLUMN IF NOT EXISTS rank_in_category  INTEGER;      -- カテゴリ内相対順位

-- quality_score/velocity でのソートを高速化
CREATE INDEX IF NOT EXISTS idx_mcp_servers_quality_score
  ON mcp_servers(quality_score DESC);
CREATE INDEX IF NOT EXISTS idx_mcp_servers_velocity_7d
  ON mcp_servers(velocity_7d DESC);

-- スコア時系列テーブル（週次スナップショット → 「先週比+X位」等の算出に使用）
CREATE TABLE IF NOT EXISTS score_history (
    id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id        UUID NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    quality_score    NUMERIC(6,2) NOT NULL,
    rank_in_category INTEGER,
    recorded_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_score_history_server_id
  ON score_history(server_id);
CREATE INDEX IF NOT EXISTS idx_score_history_recorded_at
  ON score_history(recorded_at DESC);
