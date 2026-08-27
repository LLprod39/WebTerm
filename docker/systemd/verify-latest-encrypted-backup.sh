#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="${WEBTERM_ROOT_DIR:-/opt/webterm}"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups/postgres}"

latest="$({
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'webterm_*.dump.age' -printf '%T@ %p\n' 2>/dev/null || true
} | sort -rn | head -n 1 | cut -d' ' -f2-)"
if [[ -z "$latest" || ! -f "$latest" ]]; then
  echo "No encrypted PostgreSQL backup is available for restore validation" >&2
  exit 1
fi

latest_volumes="$({
  find "$BACKUP_DIR" -maxdepth 1 -type f -name 'webterm_volumes_*.tar.gz.age' -printf '%T@ %p\n' 2>/dev/null || true
} | sort -rn | head -n 1 | cut -d' ' -f2-)"
if [[ -z "$latest_volumes" || ! -f "$latest_volumes" ]]; then
  echo "No encrypted important-volume backup is available for restore validation" >&2
  exit 1
fi

RESTORE_DRY_RUN=1 bash "$ROOT_DIR/scripts/restore_postgres.sh" "$latest"
RESTORE_DRY_RUN=1 bash "$ROOT_DIR/scripts/restore_important_volumes.sh" "$latest_volumes"
