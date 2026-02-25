# MCPHub API - Claude Code Instructions

## 概要参照先（必読）
このプロジェクトの全体方針・法的リスク・GTM戦略は以下を参照:
```
D:\antigravity_projects\VaultD\Projects\Monetization\monetization-brainstorm-master.md
```
セクション「EVAL-3 → READY: MCPHub API」→「⚠️ 実装前要確認事項」を必ず確認すること。

---

## 🚨 法的リスク（実装前に必ず確認）

### リスク①: GitHub メタデータ商用販売 → CONDITIONAL（低〜中リスク）
- 公式APIエンドポイントのみ使用・レート制限遵守
- **個人情報（コントリビューターのメール等）を収集・保存・販売しないこと**

### リスク②: 第三者MCPサーバーへのヘルスチェック → **設計変更必須**
- **Opt-in方式のみ許可**（サーバー運営者が自分で登録したサーバーのみをping）
- 未登録サーバーへの自動ping = 米国CFAA違反リスク（17,900件×毎時 ≒ 43万リクエスト/日）
- robots.txt 尊重・User-Agent に "MCPHub-Healthcheck" を設定・拒否応答はスキップ

### リスク③: mcpserverhub.net ToS → PASS（無関係）
- 競合サービスの規約であり、メタデータ収集には無関係

---

## アーキテクチャ方針

### MVP（現フェーズ）
- **検索APIのみリリース**（ヘルスチェックはOpt-in登録済みサーバーのみ）
- 有料ユーザー5人獲得で継続判断

### Phase 2（将来）
- Claude Skills も対象に含めた「AI Agent Tooling Registry API」へ拡張
- データモデルは最初から「AIツール全般」に抽象化しておくと良い（ピボット容易化）

---

## 技術スタック
- **API**: FastAPI（非同期）
- **DB**: Supabase（PostgreSQL + RLS）
- **クローラー**: httpx 非同期 + GitHub GraphQL API
- **デプロイ**: Cloud Run（asia-northeast1）+ GitHub Actions CI/CD

## 本番 URL
```
https://mcphub-api-ycqe3vmjva-an.a.run.app
```

---

## 開発ルール

### 絶対禁止
- Opt-in未登録サーバーへの自動ヘルスチェック実行
- コントリビューターのメールアドレス収集・保存
- GitHub APIレート制限の無視（5,000 req/h）

### git push の前に確認
- health_check.py が Opt-in フラグを参照しているか
- crawler.py が個人情報をフィルタしているか

---

## TODO

### 🔴 実装（GTM前に必要）
- [ ] **APIキー発行フロー** - ユーザーが自分でAPIキーを取得できるエンドポイント実装
  - `POST /auth/register`（メールアドレス → APIキー発行）
  - `api_keys` テーブルはあるが発行ロジックがまだない
  - 有料プランへのアップグレード導線も必要

### 🟡 GTM（マーケティング）
- [ ] **r/mcp（Reddit）投稿** - ベータユーザー募集。ゴール: 200人獲得
- [ ] **MCP Discord 投稿** - `#show-and-tell` にデモ投稿。ゴール: 200人獲得
- [ ] **X/Twitter スレッド** - `#MCP #AIAgents` タグで発信。毎日投稿へ

### 🟢 任意・改善
- [ ] **GH_TOKENS 設定** - GitHub PAT を登録するとクローラーのレート制限が5倍に向上（現在: 60 req/h → 5,000 req/h）
- [ ] **smithery.ai 連携打診** - 相互紹介・提携検討（Month 2〜3 目標）
