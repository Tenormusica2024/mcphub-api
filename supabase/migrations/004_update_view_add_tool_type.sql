-- mcp_servers_with_health ビューに tool_type カラムを追加
-- PostgreSQL では既存カラムの順序を変えずに末尾に追加なら CREATE OR REPLACE VIEW 使用可能

CREATE OR REPLACE VIEW mcp_servers_with_health AS
SELECT
    s.id,
    s.name,
    s.repo_url,
    s.description,
    s.category,
    s.stars,
    s.owner,
    s.repo_name,
    s.topics,
    s.readme_summary,
    s.is_active,
    s.last_crawled_at,
    s.created_at,
    s.updated_at,
    hc.health_status,
    hc.last_response_time_ms,
    hc.last_health_check_at,
    s.tool_type
FROM mcp_servers s
LEFT JOIN (
    SELECT DISTINCT ON (server_id)
        server_id,
        status AS health_status,
        response_time_ms AS last_response_time_ms,
        checked_at AS last_health_check_at
    FROM health_checks
    ORDER BY server_id, checked_at DESC
) hc ON s.id = hc.server_id;
