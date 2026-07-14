#!/usr/bin/env bash
set -e

cd /app

: "${DJANGO_SKIP_MIGRATIONS:=false}"
: "${DJANGO_COLLECTSTATIC:=true}"

if [ "$DJANGO_SKIP_MIGRATIONS" != "true" ]; then
  echo "Apply database migrations"
  python manage.py migrate --noinput
fi

if [ "$DJANGO_COLLECTSTATIC" = "true" ]; then
  echo "Collect static files"
  python manage.py collectstatic --noinput
fi

if [ "$#" -gt 0 ]; then
  exec "$@"
else
  exec daphne -b 0.0.0.0 -p 8000 mysite.asgi:application
fi
