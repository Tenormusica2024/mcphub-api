"""アプリケーション設定"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str
    github_tokens: str = ""          # カンマ区切り複数トークン
    api_secret_key: str = "dev-secret"
    admin_api_key: str = "dev-admin"
    crawl_max_servers: int = 500
    health_check_interval_min: int = 60
    health_check_timeout_sec: int = 10
    health_check_concurrency: int = 20

    model_config = {"env_file": ".env", "case_sensitive": False}

    def github_token_list(self) -> list[str]:
        """GitHubトークンをリストとして返す"""
        return [t.strip() for t in self.github_tokens.split(",") if t.strip()]


settings = Settings()
