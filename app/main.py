"""MCPHub API - メインアプリケーション"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import servers, admin, auth
from app.db import get_supabase

APP_VERSION = "0.1.0"

app = FastAPI(
    title="MCPHub API",
    description=(
        "MCP (Model Context Protocol) サーバーのディレクトリ＆稼働監視 API。\n\n"
        "GitHub から公開 MCP サーバーを自動収集し、毎時ヘルスチェックした結果を提供します。\n\n"
        "## はじめかた\n"
        "1. `POST /auth/register` にメールアドレスを送信してAPIキーを取得\n"
        "2. 各リクエストに `X-API-Key: <your_key>` ヘッダーを付与\n\n"
        "**料金プラン**\n"
        "- Free: 月 100 リクエスト\n"
        "- Basic ($9/月): 月 5,000 リクエスト\n"
        "- Pro ($19/月): 月 30,000 リクエスト + ヘルスアラート\n"
        "- Enterprise ($49/月): 無制限 + SLA + 専用サポート"
    ),
    version=APP_VERSION,
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS設定（APIキーはAuthorizationヘッダーで送信するためCookie不要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["X-API-Key", "Content-Type"],
)

# ルーター登録
app.include_router(auth.router)
app.include_router(servers.router)
app.include_router(admin.router)


@app.get("/", summary="API 情報")
async def root():
    return {
        "name": "MCPHub API",
        "version": APP_VERSION,
        "description": "MCP Server Directory & Health Check API",
        "docs": "/docs",
        "get_started": "POST /auth/register to get your free API key",
        "endpoints": {
            "register": "POST /auth/register",
            "usage": "GET /auth/usage",
            "servers": "GET /servers",
            "server_detail": "GET /servers/{id}",
            "health_history": "GET /servers/{id}/health-history",
        },
    }


@app.get("/health", summary="サービスヘルスチェック")
async def health():
    """API サーバーと Supabase の疎通を確認します。DB 障害時は 503 を返します。"""
    db = get_supabase()
    try:
        db.table("api_keys").select("id", count="exact", head=True).execute()
    except Exception:
        return {"status": "degraded", "db": "unreachable"}, 503
    return {"status": "ok", "db": "reachable"}
