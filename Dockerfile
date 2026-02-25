FROM python:3.12-slim

WORKDIR /app

# 依存パッケージをインストール
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# アプリケーションをコピー
COPY app/ ./app/

# 非rootユーザーで実行（コンテナ侵害時の権限昇格を防ぐ）
RUN useradd --no-create-home --shell /bin/false appuser
USER appuser

# Cloud Run は PORT 環境変数を使用する
ENV PORT=8080
EXPOSE 8080

CMD uvicorn app.main:app --host 0.0.0.0 --port ${PORT}
