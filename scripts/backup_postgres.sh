#!/usr/bin/env bash
# Consistent, age-encrypted PostgreSQL and important-volume backup for Compose.
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${BACKUP_DIR:-$ROOT_DIR/backups/postgres}"
BACKUP_STATUS_DIR="${BACKUP_STATUS_DIR:-$ROOT_DIR/backups/status}"
AGE_RECIPIENT_FILE="${BACKUP_AGE_RECIPIENT_FILE:-}"
RETENTION_DAILY="${RETENTION_DAILY:-7}"
RETENTION_WEEKLY="${RETENTION_WEEKLY:-4}"
COMPOSE_FILE="${COMPOSE_FILE:-$ROOT_DIR/docker-compose.production.yml}"
COMPOSE_OVERRIDE_FILE="${COMPOSE_OVERRIDE_FILE:-}"
ENV_FILE="${ENV_FILE:-$ROOT_DIR/.env.production}"
PROJECT_NAME="${PROJECT_NAME:-mini-prod}"
SERVICE="${POSTGRES_SERVICE:-postgres}"
VOLUME_SERVICE="${VOLUME_BACKUP_SERVICE:-backend}"
DB_TMP_FILE=""
VOLUME_TMP_FILE=""
VALIDATION_FIFO=""
VALIDATOR_PID=""
BACKUP_SUCCEEDED=0
PUBLISHED_FILES=()

write_status() {
  local kind="$1" status_file status_tmp
  [[ "$kind" == "success" || "$kind" == "failure" ]] || return 1
  mkdir -p "$BACKUP_STATUS_DIR"
  chmod 755 "$BACKUP_STATUS_DIR"
  status_file="$BACKUP_STATUS_DIR/last_${kind}.unixtime"
  status_tmp="$BACKUP_STATUS_DIR/.last_${kind}.$$.tmp"
  umask 022
  date -u +%s >"$status_tmp"
  chmod 644 "$status_tmp"
  mv -f -- "$status_tmp" "$status_file"
}

cleanup() {
  local exit_code=$?
  trap - EXIT
  if [[ -n "$VALIDATOR_PID" ]]; then
    kill "$VALIDATOR_PID" >/dev/null 2>&1 || true
    wait "$VALIDATOR_PID" >/dev/null 2>&1 || true
  fi
  [[ -z "$DB_TMP_FILE" ]] || rm -f -- "$DB_TMP_FILE"
  [[ -z "$VOLUME_TMP_FILE" ]] || rm -f -- "$VOLUME_TMP_FILE"
  [[ -z "$VALIDATION_FIFO" ]] || rm -f -- "$VALIDATION_FIFO"
  if [[ "$exit_code" -ne 0 && "$BACKUP_SUCCEEDED" -ne 1 ]]; then
    if ((${#PUBLISHED_FILES[@]})); then
      rm -f -- "${PUBLISHED_FILES[@]}"
    fi
    write_status failure >/dev/null 2>&1 || true
  fi
  exit "$exit_code"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

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
if ! command -v age >/dev/null 2>&1; then
  echo "age is required for encrypted PostgreSQL and volume backups" >&2
  exit 1
fi
if ! command -v tar >/dev/null 2>&1; then
  echo "tar is required for important-volume backups" >&2
  exit 1
fi
if [[ -z "$AGE_RECIPIENT_FILE" || ! -f "$AGE_RECIPIENT_FILE" ]]; then
  echo "BACKUP_AGE_RECIPIENT_FILE must reference a provisioned age recipient file" >&2
  exit 1
fi
if ! [[ "$RETENTION_DAILY" =~ ^[0-9]+$ && "$RETENTION_WEEKLY" =~ ^[0-9]+$ ]] \
  || ((RETENTION_DAILY < 1)); then
  echo "Daily retention must be positive and weekly retention must be a non-negative integer" >&2
  exit 1
fi

mkdir -p "$BACKUP_DIR"
chmod 700 "$BACKUP_DIR"
STAMP="$(date -u +%Y%m%dT%H%M%SZ)"
OUT_FILE="$BACKUP_DIR/webterm_${STAMP}.dump.age"
DB_TMP_FILE="$OUT_FILE.partial"
VOLUME_OUT_FILE="$BACKUP_DIR/webterm_volumes_${STAMP}.tar.gz.age"
VOLUME_TMP_FILE="$VOLUME_OUT_FILE.partial"
VALIDATION_FIFO="$BACKUP_DIR/.webterm_${STAMP}.validation.fifo"

container_id="$(compose ps -q "$SERVICE" | head -n 1)"
if [[ -z "$container_id" ]]; then
  echo "PostgreSQL service is not running: $SERVICE" >&2
  exit 1
fi

echo "Creating a consistent encrypted PostgreSQL custom-format dump from service $SERVICE"
mkfifo -m 600 "$VALIDATION_FIFO"
compose exec -T "$SERVICE" pg_restore --list <"$VALIDATION_FIFO" >/dev/null &
VALIDATOR_PID=$!
set +e
compose exec -T "$SERVICE" sh -ec \
  'exec pg_dump --format=custom --compress=6 --no-owner --no-privileges --username="$POSTGRES_USER" --dbname="$POSTGRES_DB"' \
  | tee "$VALIDATION_FIFO" \
  | age --encrypt --recipients-file "$AGE_RECIPIENT_FILE" --output "$DB_TMP_FILE"
pipeline_status=$?
wait "$VALIDATOR_PID"
validator_status=$?
VALIDATOR_PID=""
set -e
rm -f -- "$VALIDATION_FIFO"
VALIDATION_FIFO=""

if [[ "$pipeline_status" -ne 0 || "$validator_status" -ne 0 ]]; then
  echo "PostgreSQL dump, archive validation or encryption failed" >&2
  exit 1
fi

if [[ ! -s "$DB_TMP_FILE" ]]; then
  echo "PostgreSQL produced an empty encrypted dump" >&2
  exit 1
fi
if [[ "$(head -n 1 "$DB_TMP_FILE")" != "age-encryption.org/v1" ]]; then
  echo "Encrypted backup header validation failed" >&2
  exit 1
fi

volume_container_id="$(compose ps -q "$VOLUME_SERVICE" | head -n 1)"
if [[ -z "$volume_container_id" ]]; then
  echo "Important-volume backup service is not running: $VOLUME_SERVICE" >&2
  exit 1
fi

echo "Creating an encrypted archive of media, runtime config and playbook bundles"
VALIDATION_FIFO="$BACKUP_DIR/.webterm_volumes_${STAMP}.validation.fifo"
mkfifo -m 600 "$VALIDATION_FIFO"
tar -tzf - <"$VALIDATION_FIFO" >/dev/null &
VALIDATOR_PID=$!
set +e
compose exec -T "$VOLUME_SERVICE" sh -ec '
  set -eu
  for root in media config_runtime private/playbook_bundles; do
    test -d "/workspace/$root"
    if find "/workspace/$root" -xdev ! -type f ! -type d -print -quit | grep -q .; then
      echo "Important volume contains a non-regular entry; refusing backup" >&2
      exit 1
    fi
  done
  exec tar --format=pax --numeric-owner --one-file-system \
    -C /workspace -czf - media config_runtime private/playbook_bundles
' \
  | tee "$VALIDATION_FIFO" \
  | age --encrypt --recipients-file "$AGE_RECIPIENT_FILE" --output "$VOLUME_TMP_FILE"
pipeline_status=$?
wait "$VALIDATOR_PID"
validator_status=$?
VALIDATOR_PID=""
set -e
rm -f -- "$VALIDATION_FIFO"
VALIDATION_FIFO=""

if [[ "$pipeline_status" -ne 0 || "$validator_status" -ne 0 ]]; then
  echo "Important-volume archive, validation or encryption failed" >&2
  exit 1
fi
if [[ ! -s "$VOLUME_TMP_FILE" ]]; then
  echo "Important-volume backup produced an empty encrypted archive" >&2
  exit 1
fi
if [[ "$(head -n 1 "$VOLUME_TMP_FILE")" != "age-encryption.org/v1" ]]; then
  echo "Encrypted important-volume archive header validation failed" >&2
  exit 1
fi

# Publish the database dump and matching volume archive only after both streams
# have been validated. A failed run therefore never advertises a partial set.
mv "$DB_TMP_FILE" "$OUT_FILE"
DB_TMP_FILE=""
PUBLISHED_FILES+=("$OUT_FILE" "$OUT_FILE.sha256")
mv "$VOLUME_TMP_FILE" "$VOLUME_OUT_FILE"
VOLUME_TMP_FILE=""
PUBLISHED_FILES+=("$VOLUME_OUT_FILE" "$VOLUME_OUT_FILE.sha256")
chmod 600 "$OUT_FILE"
chmod 600 "$VOLUME_OUT_FILE"
(
  cd "$BACKUP_DIR"
  sha256sum "$(basename "$OUT_FILE")"
) >"$OUT_FILE.sha256"
chmod 600 "$OUT_FILE.sha256"
(
  cd "$BACKUP_DIR"
  sha256sum "$(basename "$VOLUME_OUT_FILE")"
) >"$VOLUME_OUT_FILE.sha256"
chmod 600 "$VOLUME_OUT_FILE.sha256"

mapfile -t daily_files < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'webterm_*.dump.age' -printf '%T@ %p\n' | sort -rn | cut -d' ' -f2-)
if ((${#daily_files[@]} > RETENTION_DAILY)); then
  for old_file in "${daily_files[@]:RETENTION_DAILY}"; do
    rm -f -- "$old_file" "$old_file.sha256"
  done
fi

mapfile -t volume_daily_files < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'webterm_volumes_*.tar.gz.age' -printf '%T@ %p\n' | sort -rn | cut -d' ' -f2-)
if ((${#volume_daily_files[@]} > RETENTION_DAILY)); then
  for old_file in "${volume_daily_files[@]:RETENTION_DAILY}"; do
    rm -f -- "$old_file" "$old_file.sha256"
  done
fi

if [[ "$(date -u +%u)" == "7" ]]; then
  weekly_file="$BACKUP_DIR/weekly_webterm_${STAMP}.dump.age"
  weekly_volume_file="$BACKUP_DIR/weekly_webterm_volumes_${STAMP}.tar.gz.age"
  PUBLISHED_FILES+=("$weekly_file" "$weekly_file.sha256" "$weekly_volume_file" "$weekly_volume_file.sha256")
  cp -- "$OUT_FILE" "$weekly_file"
  cp -- "$VOLUME_OUT_FILE" "$weekly_volume_file"
  (
    cd "$BACKUP_DIR"
    sha256sum "$(basename "$weekly_file")"
  ) >"$weekly_file.sha256"
  (
    cd "$BACKUP_DIR"
    sha256sum "$(basename "$weekly_volume_file")"
  ) >"$weekly_volume_file.sha256"
  chmod 600 "$weekly_file" "$weekly_file.sha256" "$weekly_volume_file" "$weekly_volume_file.sha256"
  mapfile -t weekly_files < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'weekly_webterm_*.dump.age' -printf '%T@ %p\n' | sort -rn | cut -d' ' -f2-)
  if ((${#weekly_files[@]} > RETENTION_WEEKLY)); then
    for old_file in "${weekly_files[@]:RETENTION_WEEKLY}"; do
      rm -f -- "$old_file" "$old_file.sha256"
    done
  fi
  mapfile -t weekly_volume_files < <(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'weekly_webterm_volumes_*.tar.gz.age' -printf '%T@ %p\n' | sort -rn | cut -d' ' -f2-)
  if ((${#weekly_volume_files[@]} > RETENTION_WEEKLY)); then
    for old_file in "${weekly_volume_files[@]:RETENTION_WEEKLY}"; do
      rm -f -- "$old_file" "$old_file.sha256"
    done
  fi
fi

write_status success
BACKUP_SUCCEEDED=1
echo "Backup complete: $OUT_FILE"
printf '%s\n' "$OUT_FILE"
printf '%s\n' "$VOLUME_OUT_FILE"
