"""MCPHub API - メインアプリケーション"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import servers, admin

app = FastAPI(
    title="MCPHub API",
    description=(
        "MCP (Model Context Protocol) サーバーのディレクトリ＆稼働監視 API。\n\n"
        "GitHub から公開 MCP サーバーを自動収集し、毎時ヘルスチェックした結果を提供します。\n\n"
        "**料金プラン**\n"
        "- Free: 月 100 リクエスト\n"
        "- Basic ($9/月): 月 5,000 リクエスト\n"
        "- Pro ($19/月): 月 30,000 リクエスト + ヘルスアラート\n"
        "- Enterprise ($49/月): 無制限 + SLA + 専用サポート"
    ),
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

# CORS設定（APIキーはAuthorizationヘッダーで送信するためCookie不要）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ルーター登録
app.include_router(servers.router)
app.include_router(admin.router)


@app.get("/", summary="API 情報")
async def root():
    return {
        "name": "MCPHub API",
        "version": "0.1.0",
        "description": "MCP Server Directory & Health Check API",
        "docs": "/docs",
        "endpoints": {
            "servers": "/servers",
            "server_detail": "/servers/{id}",
            "health_history": "/servers/{id}/health-history",
        },
    }


@app.get("/health", summary="サービスヘルスチェック")
async def health():
    return {"status": "ok"}
