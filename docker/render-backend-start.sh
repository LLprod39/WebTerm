#!/bin/sh
set -eu

export PORT="${PORT:-9000}"
export DJANGO_PORT="${DJANGO_PORT:-$PORT}"

python manage.py migrate --noinput
python manage.py load_pipeline_templates --force
python manage.py collectstatic --noinput

exec daphne -b 0.0.0.0 -p "$PORT" web_ui.asgi:application
