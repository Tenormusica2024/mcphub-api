-- tool_type カラム追加: 'mcp'（デフォルト）または 'claude_skill'
-- 既存レコードは全て 'mcp' として扱う
ALTER TABLE mcp_servers ADD COLUMN tool_type TEXT NOT NULL DEFAULT 'mcp';

CREATE INDEX idx_mcp_servers_tool_type ON mcp_servers(tool_type);
