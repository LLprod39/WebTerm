#!/usr/bin/env bash
# Restore a WebTerm Postgres dump created by backup_postgres.sh.
# Dry-run: RESTORE_DRY_RUN=1 ./scripts/restore_postgres.sh path/to.dump.sql.gz
set -euo pipefail

DUMP_PATH="${1:-}"
COMPOSE_FILE="${COMPOSE_FILE:-docker-compose.production.yml}"
SERVICE="${POSTGRES_SERVICE:-db}"
DB_NAME="${POSTGRES_DB:-webterm}"
DB_USER="${POSTGRES_USER:-webterm}"
DRY_RUN="${RESTORE_DRY_RUN:-0}"

if [[ -z "$DUMP_PATH" || ! -f "$DUMP_PATH" ]]; then
  echo "Usage: $0 /path/to/webterm_YYYYMMDD.sql.gz" >&2
  exit 1
fi

echo "Restore source: $DUMP_PATH"
echo "Target db: $DB_NAME via service $SERVICE"
if [[ "$DRY_RUN" == "1" ]]; then
  echo "DRY RUN only — validating gzip integrity"
  gzip -t "$DUMP_PATH"
  echo "gzip ok; restore not applied"
  exit 0
fi

echo "WARNING: this will overwrite database $DB_NAME"
if command -v docker >/dev/null 2>&1 && [[ -f "$COMPOSE_FILE" ]]; then
  gunzip -c "$DUMP_PATH" | docker compose -f "$COMPOSE_FILE" exec -T "$SERVICE" \
    psql -U "$DB_USER" -d "$DB_NAME"
else
  gunzip -c "$DUMP_PATH" | psql -U "$DB_USER" -d "$DB_NAME"
fi
echo "Restore finished"
