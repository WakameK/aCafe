#!/bin/sh
set -e

export OLLAMA_HOST="${OLLAMA_HOST:-http://host.docker.internal:11434}"
mkdir -p /app/data
if [ ! -f /app/data/db.sqlite3 ] && [ -f /app/db.sqlite3 ]; then
  cp /app/db.sqlite3 /app/data/db.sqlite3
fi

python manage.py migrate --noinput
python manage.py collectstatic --noinput

if [ -n "$DJANGO_SUPERUSER_USERNAME" ] && [ -n "$DJANGO_SUPERUSER_PASSWORD" ] && [ -n "$DJANGO_SUPERUSER_EMAIL" ]; then
  python manage.py createsuperuser --noinput || true
fi

exec "$@"
