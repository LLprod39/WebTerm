#!/bin/sh
set -eu

export PORT="${PORT:-9000}"
export DJANGO_PORT="${DJANGO_PORT:-$PORT}"

exec daphne -b 0.0.0.0 -p "$PORT" web_ui.asgi:application
