#!/usr/bin/env bash
# Automated Postgres backup for WebTerm production compose.
# Retention: 7 daily + 4 weekly (Sunday dumps kept as weekly).
set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-./backups/postgres}"
RETENTION_DAILY="${RETENTION_DAILY:-7}"
RETENTION_WEEKLY="${RETENTION_WEEKLY:-4}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
SERVICE="${POSTGRES_SERVICE:-db}"
DB_NAME="${POSTGRES_DB:-webterm}"
DB_USER="${POSTGRES_USER:-webterm}"

mkdir -p "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
DAY_NAME="$(date -u +%A)"
OUT_FILE="${BACKUP_DIR}/webterm_${STAMP}.sql.gz"

echo "Backing up ${DB_NAME} from service ${SERVICE} -> ${OUT_FILE}"
if command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]]; then
  docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
    pg_dump -U "$DB_USER" "$DB_NAME" | gzip -c > "$OUT_FILE"
elif command -v pg_dump >/dev/null 2>&1; then
  pg_dump -U "$DB_USER" "$DB_NAME" | gzip -c > "$OUT_FILE"
else
  echo "Neither docker compose db service nor local pg_dump available" >&2
  exit 1
fi

# Keep daily dumps (newest N)
mapfile -t DAILIES < <(ls -1t "$BACKUP_DIR"/webterm_*.sql.gz 2>/dev/null || true)
if ((${#DAILIES[@]} > RETENTION_DAILY)); then
  for old in "${DAILIES[@]:RETENTION_DAILY}"; do
    # Preserve Sunday dumps as weekly
    if [[ "$old" == *T* ]]; then
      rm -f "$old" || true
    fi
  done
fi

if [[ "$DAY_NAME" == "Sunday" ]]; then
  cp -f "$OUT_FILE" "${BACKUP_DIR}/weekly_webterm_${STAMP}.sql.gz"
  mapfile -t WEEKLIES < <(ls -1t "$BACKUP_DIR"/weekly_webterm_*.sql.gz 2>/dev/null || true)
  if ((${#WEEKLIES[@]} > RETENTION_WEEKLY)); then
    for old in "${WEEKLIES[@]:RETENTION_WEEKLY}"; do
      rm -f "$old" || true
    done
  fi
fi

echo "Backup complete: $OUT_FILE"
