# MCPHub API

MCP (Model Context Protocol) サーバーのディレクトリ＆稼働監視 API。

GitHub から公開 MCP サーバーを自動収集し、毎時ヘルスチェックした結果を REST API で提供します。

**本番 URL**: `https://mcphub-api-ycqe3vmjva-an.a.run.app`
- API ドキュメント: https://mcphub-api-ycqe3vmjva-an.a.run.app/docs
- ヘルスチェック: https://mcphub-api-ycqe3vmjva-an.a.run.app/health

## エンドポイント

| エンドポイント | 説明 |
|---|---|
| `GET /servers` | MCP サーバー一覧（カテゴリ・キーワード・ヘルス状態でフィルタ可） |
| `GET /servers/{id}` | サーバー詳細 |
| `GET /servers/{id}/health-history` | ヘルスチェック履歴 |

### クエリパラメータ（/servers）

| パラメータ | 説明 | 例 |
|---|---|---|
| `category` | カテゴリフィルタ | `database`, `browser`, `filesystem`, `code`, `productivity`, `api`, `search`, `other` |
| `q` | 名前・説明の部分一致検索 | `q=postgres` |
| `health` | ヘルス状態フィルタ | `up`, `down`, `unknown` |
| `sort` | ソート項目 | `stars` (default), `name`, `last_crawled_at` |
| `page` | ページ番号 | `1` |
| `per_page` | 1ページの件数（最大100） | `20` |

## ローカル開発

```bash
# 1. リポジトリをクローン
git clone https://github.com/Tenormusica2024/mcphub-api.git
cd mcphub-api

# 2. 仮想環境を作成
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate

# 3. 依存パッケージをインストール
pip install -r requirements.txt

# 4. 環境変数を設定
cp env.example .env
# .env を編集して Supabase URL/キー・GitHub トークンを設定

# 5. Supabase スキーマを適用
# Supabase ダッシュボード → SQL Editor → supabase/schema.sql を実行

# 6. サーバー起動
uvicorn app.main:app --reload

# 7. クローラー実行（初回データ収集）
python scripts/crawl.py --max 100
```

## 料金プラン

| プラン | 月額 | 月間リクエスト |
|---|---|---|
| Free | $0 | 100 |
| Basic | $9 | 5,000 |
| Pro | $19 | 30,000 + ヘルスアラート |
| Enterprise | $49 | 無制限 + SLA + 専用サポート |

## 技術スタック

- **API**: FastAPI + Uvicorn
- **DB**: Supabase (PostgreSQL)
- **クローラー**: httpx 非同期 + GitHub GraphQL API
- **デプロイ**: Cloud Run + GitHub Actions CI/CD
