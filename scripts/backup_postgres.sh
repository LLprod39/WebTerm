#!/usr/bin/env bash
# Consistent PostgreSQL backup for the WebTerm production Compose stack.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups/postgres}"
RETENTION_DAILY="${RETENTION_DAILY:-7}"
RETENTION_WEEKLY="${RETENTION_WEEKLY:-4}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.production.yml}"
COMPOSE_OVERRIDE_FILE="${COMPOSE_OVERRIDE_FILE:-}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.production}"
PROJECT_NAME="${PROJECT_NAME:-mini-prod}"
SERVICE="${POSTGRES_SERVICE:-postgres}"

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

if [[ ! -f "$COMPOSE_FILE" ]]; then
  echo "Compose file not found: $COMPOSE_FILE" >&2
  exit 1
fi
if [[ -n "$COMPOSE_OVERRIDE_FILE" && ! -f "$COMPOSE_OVERRIDE_FILE" ]]; then
  echo "Compose override not found: $COMPOSE_OVERRIDE_FILE" >&2
  exit 1
fi
if [[ ! -f "$ENV_FILE" ]]; then
  echo "Production environment not found: $ENV_FILE" >&2
  exit 1
fi
if ! [[ "$RETENTION_DAILY" =~ ^[0-9]+$ && "$RETENTION_WEEKLY" =~ ^[0-9]+$ ]]; then
  echo "Retention values must be non-negative integers" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="$BACKUP_DIR/webterm_${STAMP}.dump"
TMP_FILE="$OUT_FILE.partial"
trap 'rm -f "$TMP_FILE"' EXIT

container_id="$(compose ps -q "$SERVICE" | head -n 1)"
if [[ -z "$container_id" ]]; then
  echo "PostgreSQL service is not running: $SERVICE" >&2
  exit 1
fi

echo "Creating a consistent PostgreSQL custom-format dump from service $SERVICE"
compose exec -T "$SERVICE" sh -ec \
  'exec pg_dump --format=custom --compress=6 --no-owner --no-privileges --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  >"$TMP_FILE"

if [[ ! -s "$TMP_FILE" ]]; then
  echo "PostgreSQL produced an empty dump" >&2
  exit 1
fi
cat "$TMP_FILE" | compose exec -T "$SERVICE" pg_restore --list - >/dev/null
mv "$TMP_FILE" "$OUT_FILE"
chmod 600 "$OUT_FILE"
(
  cd "$BACKUP_DIR"
  sha256sum "$(basename "$OUT_FILE")"
) >"$OUT_FILE.sha256"
chmod 600 "$OUT_FILE.sha256"

mapfile -t daily_files < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'webterm_*.dump' -printf '%T@ %p\n' | sort -rn | cut -d' ' -f2-)
if ((${#daily_files[@]} > RETENTION_DAILY)); then
  for old_file in "${daily_files[@]:RETENTION_DAILY}"; do
    rm -f -- "$old_file" "$old_file.sha256"
  done
fi

if [[ "$(date -u +%u)" == "7" ]]; then
  weekly_file="$BACKUP_DIR/weekly_webterm_${STAMP}.dump"
  cp -- "$OUT_FILE" "$weekly_file"
  (
    cd "$BACKUP_DIR"
    sha256sum "$(basename "$weekly_file")"
  ) >"$weekly_file.sha256"
  mapfile -t weekly_files < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'weekly_webterm_*.dump' -printf '%T@ %p\n' | sort -rn | cut -d' ' -f2-)
  if ((${#weekly_files[@]} > RETENTION_WEEKLY)); then
    for old_file in "${weekly_files[@]:RETENTION_WEEKLY}"; do
      rm -f -- "$old_file" "$old_file.sha256"
    done
  fi
fi

echo "Backup complete: $OUT_FILE"
printf '%s\n' "$OUT_FILE"
