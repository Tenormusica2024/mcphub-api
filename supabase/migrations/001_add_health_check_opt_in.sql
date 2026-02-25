-- マイグレーション: health_check_opt_in カラムを追加
-- 公開GitHubリポジトリへのHEAD確認はデフォルトで許可（true）
ALTER TABLE mcp_servers
    ADD COLUMN IF NOT EXISTS health_check_opt_in BOOLEAN DEFAULT true;

-- 既存レコードを全て opt-in 状態に更新
UPDATE mcp_servers SET health_check_opt_in = true WHERE health_check_opt_in IS NULL;

-- インデックス: opt-in サーバーの効率的な取得用
CREATE INDEX IF NOT EXISTS idx_mcp_servers_health_check_opt_in
    ON mcp_servers(health_check_opt_in);
