#!/usr/bin/env bash
set -e

# 環境変数でスキップ可能
: "${DJANGO_SKIP_MIGRATIONS:=false}"
: "${DJANGO_COLLECTSTATIC:=true}"

# DBマイグレーション（SQLiteでも安全に実行）
if [ "$DJANGO_SKIP_MIGRATIONS" != "true" ]; then
  echo "Apply database migrations"
  python manage.py migrate --noinput
fi

# 静的ファイル収集
if [ "$DJANGO_COLLECTSTATIC" = "true" ]; then
  echo "Collect static files"
  python manage.py collectstatic --noinput
fi

# 引数が与えられていればそれを実行（例: runworker 等）
if [ "$#" -gt 0 ]; then
  exec "$@"
else
  # デフォルトは daphne を CMD で起動（Dockerfile の CMD と整合）
  exec daphne -b 0.0.0.0 -p 8000 sosuke.asgi:application
fi
