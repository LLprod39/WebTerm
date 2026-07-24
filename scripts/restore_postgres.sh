#!/usr/bin/env bash
# Restore a custom-format dump created by backup_postgres.sh.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DUMP_PATH="${1:-}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.production.yml}"
COMPOSE_OVERRIDE_FILE="${COMPOSE_OVERRIDE_FILE:-}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.production}"
PROJECT_NAME="${PROJECT_NAME:-mini-prod}"
SERVICE="${POSTGRES_SERVICE:-postgres}"
DRY_RUN="${RESTORE_DRY_RUN:-0}"
CONFIRMATION="${RESTORE_CONFIRM:-}"

compose() {
  local compose_files=(-f "$COMPOSE_FILE")
  if [[ -n "$COMPOSE_OVERRIDE_FILE" ]]; then
    compose_files+=(-f "$COMPOSE_OVERRIDE_FILE")
  fi
  docker compose \
    --project-name "$PROJECT_NAME" \
    --env-file "$ENV_FILE" \
    "${compose_files[@]}" \
    "$@"
}

if [[ -z "$DUMP_PATH" || ! -f "$DUMP_PATH" ]]; then
  echo "Usage: $0 /path/to/webterm_YYYYMMDDTHHMMSSZ.dump" >&2
  exit 1
fi
if [[ ! -f "$COMPOSE_FILE" || ! -f "$ENV_FILE" ]]; then
  echo "Compose file and production environment are required" >&2
  exit 1
fi
if [[ -n "$COMPOSE_OVERRIDE_FILE" && ! -f "$COMPOSE_OVERRIDE_FILE" ]]; then
  echo "Compose override not found: $COMPOSE_OVERRIDE_FILE" >&2
  exit 1
fi

container_id="$(compose ps -q "$SERVICE" | head -n 1)"
if [[ -z "$container_id" ]]; then
  echo "PostgreSQL service is not running: $SERVICE" >&2
  exit 1
fi

echo "Validating PostgreSQL archive: $DUMP_PATH"
if [[ -f "$DUMP_PATH.sha256" ]]; then
  (
    cd "$(dirname "$DUMP_PATH")"
    sha256sum --check "$(basename "$DUMP_PATH").sha256"
  )
fi
cat "$DUMP_PATH" | compose exec -T "$SERVICE" pg_restore --list >/dev/null
if [[ "$DRY_RUN" == "1" ]]; then
  echo "Archive is valid; dry run did not change the database"
  exit 0
fi
if [[ "$CONFIRMATION" != "RESTORE_WEBTERM" ]]; then
  echo "Restore is destructive. Set RESTORE_CONFIRM=RESTORE_WEBTERM for the intended isolated target." >&2
  exit 1
fi

echo "Recreating the confirmed target database before restore"
compose exec -T "$SERVICE" sh -ec '
  dropdb --force --if-exists \
    --username="$POSTGRES_USER" \
    --maintenance-db=postgres \
    "$POSTGRES_DB"
  createdb \
    --username="$POSTGRES_USER" \
    --maintenance-db=postgres \
    --owner="$POSTGRES_USER" \
    "$POSTGRES_DB"
'

echo "Restoring the archive into PostgreSQL service $SERVICE"
cat "$DUMP_PATH" | compose exec -T "$SERVICE" sh -ec \
  'exec pg_restore --exit-on-error --no-owner --no-privileges --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"'
echo "Restore finished"
