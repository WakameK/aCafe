# Dockerfile
FROM python:3.14-slim

# 環境変数
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV POETRY_VIRTUALENVS_CREATE=false

# 作業ディレクトリ
WORKDIR /app

# システム依存パッケージ（必要に応じて調整）
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 依存関係をコピーしてインストール
# requirements.txt をプロジェクトルートに置いておく想定
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip
RUN pip install -r /app/requirements.txt

# アプリケーションコードをコピー
COPY . /app

# 非rootユーザー作成（セキュリティ向上）
RUN useradd --create-home appuser && chown -R appuser:appuser /app
USER appuser

# エントリポイントとデフォルトコマンド
COPY ./docker/entrypoint.sh /app/docker/entrypoint.sh
RUN chmod +x /app/docker/entrypoint.sh

# SQLite 用データディレクトリ（ボリュームで永続化推奨）
VOLUME ["/app/db.sqlite3", "/app/static"]

# daphne を使って ASGI を起動する想定
EXPOSE 8000

ENTRYPOINT ["/app/docker/entrypoint.sh"]
CMD ["daphne", "-b", "0.0.0.0", "-p", "8000", "sosuke.asgi:application"]
