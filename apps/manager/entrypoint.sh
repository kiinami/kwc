#!/bin/sh
set -eu

: "${DJANGO_SETTINGS_MODULE:=manager.settings}"
: "${PORT:=8000}"
: "${WEB_CONCURRENCY:=2}"
: "${TIMEOUT:=60}"

export DJANGO_SETTINGS_MODULE PORT WEB_CONCURRENCY TIMEOUT

python manage.py migrate --noinput

exec gunicorn manager.wsgi:application \
  --bind "0.0.0.0:${PORT}" \
  --workers "${WEB_CONCURRENCY}" \
  --timeout "${TIMEOUT}" \
  --access-logfile - \
  --error-logfile - \
  --log-level info \
  --preload
