-- MCPHub API - Supabase スキーマ定義
-- 適用: Supabase SQL Editor で実行

-- MCPサーバー一覧テーブル
CREATE TABLE IF NOT EXISTS mcp_servers (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name TEXT NOT NULL,
    repo_url TEXT NOT NULL UNIQUE,
    description TEXT,
    category TEXT,   -- 例: "database", "filesystem", "browser", "api", "other"
    stars INTEGER DEFAULT 0,
    owner TEXT,      -- GitHubオーナー名
    repo_name TEXT,  -- GitHubリポジトリ名
    topics TEXT[],   -- GitHubトピックタグ
    readme_summary TEXT,  -- READMEから抽出した概要
    is_active BOOLEAN DEFAULT true,
    last_crawled_at TIMESTAMPTZ,
    created_at TIMESTAMPTZ DEFAULT NOW(),
    updated_at TIMESTAMPTZ DEFAULT NOW()
);

-- ヘルスチェック履歴テーブル
CREATE TABLE IF NOT EXISTS health_checks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    server_id UUID NOT NULL REFERENCES mcp_servers(id) ON DELETE CASCADE,
    status TEXT NOT NULL,        -- "up", "down", "unknown"
    response_time_ms INTEGER,    -- レスポンスタイム（ミリ秒）
    http_status INTEGER,         -- HTTPステータスコード
    error_message TEXT,          -- エラー時のメッセージ
    checked_at TIMESTAMPTZ DEFAULT NOW()
);

-- APIキーテーブル
CREATE TABLE IF NOT EXISTS api_keys (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_email TEXT NOT NULL,
    key_hash TEXT NOT NULL UNIQUE,   -- ハッシュ化したAPIキー
    plan TEXT NOT NULL DEFAULT 'free',  -- "free", "basic", "pro", "enterprise"
    req_count INTEGER DEFAULT 0,        -- 今月の使用リクエスト数
    req_limit INTEGER DEFAULT 100,      -- プランの月間上限
    last_reset_at TIMESTAMPTZ DEFAULT NOW(),  -- カウントリセット日
    is_active BOOLEAN DEFAULT true,
    created_at TIMESTAMPTZ DEFAULT NOW()
);

-- インデックス作成
CREATE INDEX IF NOT EXISTS idx_mcp_servers_category ON mcp_servers(category);
CREATE INDEX IF NOT EXISTS idx_mcp_servers_stars ON mcp_servers(stars DESC);
CREATE INDEX IF NOT EXISTS idx_mcp_servers_is_active ON mcp_servers(is_active);
CREATE INDEX IF NOT EXISTS idx_health_checks_server_id ON health_checks(server_id);
CREATE INDEX IF NOT EXISTS idx_health_checks_checked_at ON health_checks(checked_at DESC);
CREATE INDEX IF NOT EXISTS idx_api_keys_key_hash ON api_keys(key_hash);

-- 最新ヘルスチェック状態を効率取得するビュー
CREATE OR REPLACE VIEW mcp_servers_with_health AS
SELECT
    s.*,
    h.status AS health_status,
    h.response_time_ms AS last_response_time_ms,
    h.checked_at AS last_health_check_at
FROM mcp_servers s
LEFT JOIN LATERAL (
    SELECT status, response_time_ms, checked_at
    FROM health_checks
    WHERE server_id = s.id
    ORDER BY checked_at DESC
    LIMIT 1
) h ON true;

-- updated_at 自動更新トリガー
CREATE OR REPLACE FUNCTION update_updated_at()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER mcp_servers_updated_at
    BEFORE UPDATE ON mcp_servers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at();
