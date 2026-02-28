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

### Phase 2（READY → 実装計画中）
- **製品: AIエージェント向けキュレーションAPI**（MCP + Claude Skills を品質スコア順で返すAPI）
- **コンセプト**: AIエージェントが「コードレビューに最適なSkillを取得して」と指示するだけで、品質スコア順の最適ツールが返ってくる。現状のweb検索の当たり外れをなくす
- **ポジション**: Anthropic Tool Search Tool（Claude内蔵）を補完する「質の高いカタログ」。競合ゼロ確認済み（2026-02-28）
- **スコープ**: MVP = MCP + Claude Skills（npm AI CLIは混在するとノイズになるため除外）
- **スコアリング**: GitHubスター + 更新頻度 + smithery.ai使用回数 + タスク意図一致度embedding
- **戦略**: ステルス開発 → Lv3（蓄積データが模倣困難な資産）到達後に公開
- **詳細**: `monetization-brainstorm-master.md` Round 5 参照

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

### 🟢 実装完了
- [x] **APIキー発行フロー** - `POST /auth/register`, `GET /auth/usage`, 全エンドポイントで `X-API-Key` 認証

### 🟡 GTM（マーケティング）
- [ ] **r/mcp（Reddit）投稿** - ベータユーザー募集。ゴール: 200人獲得
- [ ] **MCP Discord 投稿** - `#show-and-tell` にデモ投稿。ゴール: 200人獲得
- [ ] **X/Twitter スレッド** - `#MCP #AIAgents` タグで発信。毎日投稿へ

### 🟢 任意・改善
- [ ] **GH_TOKENS 設定** - GitHub PAT を登録するとクローラーのレート制限が5倍に向上（現在: 60 req/h → 5,000 req/h）
- [ ] **smithery.ai 連携打診** - 相互紹介・提携検討（Month 2〜3 目標）
