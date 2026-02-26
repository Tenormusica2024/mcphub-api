"""アプリケーション設定"""

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_key: str
    gh_tokens: str = ""              # カンマ区切り複数トークン（GH_TOKENS 環境変数）
    admin_api_key: str               # 必須・デフォルト値なし（本番は必ず環境変数で設定すること）
    api_base_url: str = "https://mcphub-api-ycqe3vmjva-an.a.run.app"
    crawl_max_servers: int = 500
    health_check_timeout_sec: int = 10
    health_check_concurrency: int = 20

    model_config = {"env_file": ".env", "case_sensitive": False}

    def github_token_list(self) -> list[str]:
        """GitHubトークンをリストとして返す"""
        return [t.strip() for t in self.gh_tokens.split(",") if t.strip()]


settings = Settings()
