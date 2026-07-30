#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ENV="$ROOT_DIR/.env.production"
RESTORE_ENV="$ROOT_DIR/.env.production.restore"
COMPOSE_FILE="$ROOT_DIR/docker-compose.production.yml"
SMOKE_COMPOSE_FILE="$ROOT_DIR/docker-compose.production.smoke.yml"
RECOVERY_COMPOSE_FILE="$ROOT_DIR/docker-compose.production.recovery.yml"
ARTIFACT_DIR="${F13B_ARTIFACT_DIR:-$ROOT_DIR/.ci-artifacts/production-recovery-smoke}"
SOURCE_PROJECT="${F13B_SOURCE_PROJECT:-webterm-f13b-source}"
RESTORE_PROJECT="${F13B_RESTORE_PROJECT:-webterm-f13b-restore}"
AUTH_USERNAME="smoke-user-01"
AUTH_PASSWORD="F13aUserPass123!"
MARKER="f13b-${GITHUB_SHA:-$(git -C "$ROOT_DIR" rev-parse HEAD)}"
STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
SENSITIVE_DIR="$(mktemp -d)"
SOURCE_STARTED=0
RESTORE_CREATED=0
SOURCE_ENV_EXISTED=0
TLS_CERT_EXISTED=0
TLS_KEY_EXISTED=0
TLS_CERT="$ROOT_DIR/docker/nginx/ssl/mini-prod-selfsigned.crt"
TLS_KEY="$ROOT_DIR/docker/nginx/ssl/mini-prod-selfsigned.key"

[[ -e "$SOURCE_ENV" ]] && SOURCE_ENV_EXISTED=1
[[ -e "$TLS_CERT" ]] && TLS_CERT_EXISTED=1
[[ -e "$TLS_KEY" ]] && TLS_KEY_EXISTED=1

mkdir -p "$ARTIFACT_DIR"
exec > >(tee "$ARTIFACT_DIR/production-recovery-smoke.log") 2>&1

source_compose() {
  docker compose \
    --project-name "$SOURCE_PROJECT" \
    --env-file "$SOURCE_ENV" \
    -f "$COMPOSE_FILE" \
    -f "$SMOKE_COMPOSE_FILE" \
    "$@"
}

restore_compose() {
  docker compose \
    --project-name "$RESTORE_PROJECT" \
    --env-file "$RESTORE_ENV" \
    -f "$COMPOSE_FILE" \
    -f "$RECOVERY_COMPOSE_FILE" \
    "$@"
}

collect_evidence() {
  set +e
  if [[ "$RESTORE_CREATED" -eq 1 ]]; then
    restore_compose ps --format json >"$ARTIFACT_DIR/restore-compose-ps.json" 2>&1
  fi
  set -e
}

cleanup() {
  local exit_code=$?
  trap - EXIT
  collect_evidence
  set +e
  if [[ "$RESTORE_CREATED" -eq 1 ]]; then
    restore_compose down -v --remove-orphans
  fi
  if [[ "$SOURCE_STARTED" -eq 1 ]]; then
    source_compose down -v --remove-orphans
  fi
  rm -f "$RESTORE_ENV"
  if [[ "$SOURCE_ENV_EXISTED" -eq 0 ]]; then
    rm -f "$SOURCE_ENV"
  fi
  if [[ "$TLS_CERT_EXISTED" -eq 0 ]]; then
    rm -f "$TLS_CERT"
  fi
  if [[ "$TLS_KEY_EXISTED" -eq 0 ]]; then
    rm -f "$TLS_KEY"
  fi
  rm -rf -- "$SENSITIVE_DIR"
  set -e
  exit "$exit_code"
}
trap cleanup EXIT

require_command() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

wait_for_restore_service() {
  local service="$1"
  local started_at
  started_at="$(date +%s)"
  while true; do
    local container_id status
    container_id="$(restore_compose ps -q "$service" | head -n 1)"
    status=""
    if [[ -n "$container_id" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
    fi
    if [[ "$status" == "healthy" ]]; then
      echo "[ok] restored $service is healthy"
      return 0
    fi
    if [[ "$status" == "exited" || "$status" == "dead" ]]; then
      echo "Restored $service failed with state $status" >&2
      return 1
    fi
    if (( $(date +%s) - started_at >= 180 )); then
      echo "Timed out waiting for restored $service (last state: ${status:-missing})" >&2
      return 1
    fi
    sleep 3
  done
}

assert_restore_target_absent() {
  if docker ps -a --format '{{.Names}}' | grep -Eq '^webterm-f13b-restore-(postgres|redis)$'; then
    echo "Refusing to reuse existing F-13b restore containers" >&2
    exit 1
  fi
  if docker volume ls \
    --filter "label=com.docker.compose.project=$RESTORE_PROJECT" \
    --quiet | grep -q .; then
    echo "Refusing to reuse existing F-13b restore volumes" >&2
    exit 1
  fi
}

write_restore_environment() {
  cp "$SENSITIVE_DIR/production.env" "$RESTORE_ENV"
  python3 - "$RESTORE_ENV" <<'PY'
from pathlib import Path
import sys

path = Path(sys.argv[1])
replacements = {
    "PUBLIC_BIND_HOST": "127.0.0.1",
    "PUBLIC_HTTP_PORT": "28080",
    "PUBLIC_HTTPS_PORT": "28443",
    "FRONTEND_PORT": "28081",
    "DJANGO_BIND_HOST": "127.0.0.1",
    "DJANGO_HOST_PORT": "29000",
    "POSTGRES_BIND_HOST": "127.0.0.1",
    "POSTGRES_HOST_PORT": "25432",
    "REDIS_BIND_HOST": "127.0.0.1",
    "REDIS_HOST_PORT": "26379",
}
lines = path.read_text(encoding="utf-8").splitlines()
seen = set()
output = []
for line in lines:
    if line and not line.lstrip().startswith("#") and "=" in line:
        key = line.split("=", 1)[0].strip()
        if key in replacements:
            output.append(f"{key}={replacements[key]}")
            seen.add(key)
            continue
    output.append(line)
for key, value in replacements.items():
    if key not in seen:
        output.append(f"{key}={value}")
path.write_text("\n".join(output) + "\n", encoding="utf-8")
PY
  chmod 600 "$RESTORE_ENV"
}

write_integrity_manifest() {
  local target="$1"
  shift
  "$@" exec -T \
    -e "RECOVERY_AUTH_PASSWORD=$AUTH_PASSWORD" \
    backend python scripts/recovery_integrity_manifest.py \
    --auth-username "$AUTH_USERNAME" >"$target"
}

verify_redis_markers() {
  local phase="$1"
  local queue_marker channel_marker
  queue_marker="$(restore_compose exec -T redis redis-cli --raw -n 0 GET f13b:queue)"
  channel_marker="$(restore_compose exec -T redis redis-cli --raw -n 1 GET f13b:channel)"
  if [[ "$queue_marker" != "$MARKER" || "$channel_marker" != "$MARKER" ]]; then
    echo "Redis persistence markers are missing during $phase" >&2
    exit 1
  fi
  printf '%s=ok\n' "$phase" >>"$ARTIFACT_DIR/redis-recovery.txt"
}

require_command docker
require_command git
require_command python3
require_command sha256sum
assert_restore_target_absent

echo "==> Building the source state through the proven F-13a install path"
F13A_PROJECT_NAME="$SOURCE_PROJECT" \
F13A_ARTIFACT_DIR="$SENSITIVE_DIR/f13a-source-evidence" \
F13A_KEEP_UP=1 \
  "$ROOT_DIR/docker/production-install-smoke.sh"
SOURCE_STARTED=1
REDIS_IMAGE="$(source_compose images -q redis | head -n 1)"
if [[ -z "$REDIS_IMAGE" ]]; then
  echo "Unable to resolve the source Redis image" >&2
  exit 1
fi

echo "==> Seeding persistent config/media/playbook-bundle and Redis recovery markers"
source_compose exec -T backend sh -ec \
  "printf '%s\\n' '$MARKER' > /workspace/config_runtime/f13b-config-marker.txt; printf '%s\\n' '$MARKER' > /workspace/media/f13b-media-marker.txt; printf '%s\\n' '$MARKER' > /workspace/private/playbook_bundles/f13b-playbook-bundle-marker.txt"
source_compose exec -T redis redis-cli -n 0 SET f13b:queue "$MARKER" >/dev/null
source_compose exec -T redis redis-cli -n 1 SET f13b:channel "$MARKER" >/dev/null

echo "==> Capturing privacy-safe source integrity"
write_integrity_manifest "$ARTIFACT_DIR/source-integrity.json" source_compose

echo "==> Backing up PostgreSQL, secret configuration, persistent volumes and Redis"
mkdir -p "$SENSITIVE_DIR/postgres"
BACKUP_DIR="$SENSITIVE_DIR/postgres" \
PROJECT_NAME="$SOURCE_PROJECT" \
ENV_FILE="$SOURCE_ENV" \
COMPOSE_FILE="$COMPOSE_FILE" \
RETENTION_DAILY=1 \
RETENTION_WEEKLY=0 \
  "$ROOT_DIR/scripts/backup_postgres.sh"
DUMP_PATH="$(find "$SENSITIVE_DIR/postgres" -maxdepth 1 -type f -name 'webterm_*.dump' | head -n 1)"
if [[ -z "$DUMP_PATH" ]]; then
  echo "PostgreSQL backup was not created" >&2
  exit 1
fi

cp "$SOURCE_ENV" "$SENSITIVE_DIR/production.env"
chmod 600 "$SENSITIVE_DIR/production.env"
source_compose exec -T backend tar -C /workspace/config_runtime -czf - . >"$SENSITIVE_DIR/config.tar.gz"
source_compose exec -T backend tar -C /workspace/media -czf - . >"$SENSITIVE_DIR/media.tar.gz"
source_compose exec -T backend tar -C /workspace/private/playbook_bundles -czf - . >"$SENSITIVE_DIR/playbook-bundles.tar.gz"
source_compose exec -T redis sh -ec '
  redis-cli BGREWRITEAOF >/dev/null 2>&1 || true
  attempts=0
  while [ "$attempts" -lt 120 ]; do
    info="$(redis-cli INFO persistence | tr -d "\r")"
    in_progress="$(printf "%s\n" "$info" | sed -n "s/^aof_rewrite_in_progress:\([0-9]*\)$/\1/p")"
    status="$(printf "%s\n" "$info" | sed -n "s/^aof_last_bgrewrite_status:\([^[:space:]]*\)$/\1/p")"
    if [ "$in_progress" = "0" ] && [ "$status" = "ok" ]; then
      exit 0
    fi
    attempts=$((attempts + 1))
    sleep 1
  done
  echo "Timed out waiting for a consistent Redis AOF rewrite" >&2
  exit 1
'
source_compose stop redis
SOURCE_REDIS_VOLUME="$(docker volume ls \
  --filter "label=com.docker.compose.project=$SOURCE_PROJECT" \
  --filter 'label=com.docker.compose.volume=mini_prod_redis_data' \
  --quiet | head -n 1)"
if [[ -z "$SOURCE_REDIS_VOLUME" ]]; then
  echo "Unable to resolve the source Redis volume" >&2
  exit 1
fi
docker run --rm \
  --volume "$SOURCE_REDIS_VOLUME:/source:ro" \
  "$REDIS_IMAGE" sh -ec 'tar -C /source -czf - .' >"$SENSITIVE_DIR/redis.tar.gz"

(
  cd "$SENSITIVE_DIR"
  sha256sum production.env config.tar.gz media.tar.gz playbook-bundles.tar.gz redis.tar.gz "postgres/$(basename "$DUMP_PATH")"
) >"$ARTIFACT_DIR/backup-inventory.sha256"
(
  cd "$SENSITIVE_DIR"
  wc -c production.env config.tar.gz media.tar.gz playbook-bundles.tar.gz redis.tar.gz "postgres/$(basename "$DUMP_PATH")"
) >"$ARTIFACT_DIR/backup-sizes.txt"

echo "==> Creating an isolated restore project and restoring Redis persistence"
write_restore_environment
export F13B_BACKEND_IMAGE
F13B_BACKEND_IMAGE="$(source_compose images -q backend | head -n 1)"
if [[ -z "$F13B_BACKEND_IMAGE" || -z "$REDIS_IMAGE" ]]; then
  echo "Unable to resolve source release images" >&2
  exit 1
fi

RESTORE_CREATED=1
restore_compose create postgres redis >/dev/null
RESTORE_REDIS_VOLUME="$(docker volume ls \
  --filter "label=com.docker.compose.project=$RESTORE_PROJECT" \
  --filter 'label=com.docker.compose.volume=mini_prod_redis_data' \
  --quiet | head -n 1)"
if [[ -z "$RESTORE_REDIS_VOLUME" ]]; then
  echo "Unable to resolve the isolated Redis volume" >&2
  exit 1
fi
cat "$SENSITIVE_DIR/redis.tar.gz" | docker run --rm -i \
  --volume "$RESTORE_REDIS_VOLUME:/restore" \
  "$REDIS_IMAGE" sh -ec 'tar -xzf - -C /restore'

restore_compose up -d postgres redis
wait_for_restore_service postgres
wait_for_restore_service redis

echo "==> Restoring the logical PostgreSQL archive"
RESTORE_CONFIRM=RESTORE_WEBTERM \
PROJECT_NAME="$RESTORE_PROJECT" \
ENV_FILE="$RESTORE_ENV" \
COMPOSE_FILE="$COMPOSE_FILE" \
COMPOSE_OVERRIDE_FILE="$RECOVERY_COMPOSE_FILE" \
  "$ROOT_DIR/scripts/restore_postgres.sh" "$DUMP_PATH"

echo "==> Restoring config, media and private playbook bundles into project-scoped volumes"
cat "$SENSITIVE_DIR/config.tar.gz" | restore_compose run --rm --no-deps -T backend \
  tar -C /workspace/config_runtime -xzf -
cat "$SENSITIVE_DIR/media.tar.gz" | restore_compose run --rm --no-deps -T backend \
  tar -C /workspace/media -xzf -
cat "$SENSITIVE_DIR/playbook-bundles.tar.gz" | restore_compose run --rm --no-deps -T backend \
  tar -C /workspace/private/playbook_bundles -xzf -

echo "==> Comparing database, authentication, managed-secret and volume integrity"
restore_compose run --rm --no-deps -T \
  -e "RECOVERY_AUTH_PASSWORD=$AUTH_PASSWORD" \
  backend python scripts/recovery_integrity_manifest.py \
  --auth-username "$AUTH_USERNAME" >"$ARTIFACT_DIR/restored-integrity.json"
cmp "$ARTIFACT_DIR/source-integrity.json" "$ARTIFACT_DIR/restored-integrity.json"
verify_redis_markers redis-restore

echo "==> Proving PostgreSQL restart recovery"
restore_compose restart postgres
wait_for_restore_service postgres
restore_compose run --rm --no-deps -T \
  -e "RECOVERY_AUTH_PASSWORD=$AUTH_PASSWORD" \
  backend python scripts/recovery_integrity_manifest.py \
  --auth-username "$AUTH_USERNAME" >"$ARTIFACT_DIR/postgres-restart-integrity.json"
cmp "$ARTIFACT_DIR/source-integrity.json" "$ARTIFACT_DIR/postgres-restart-integrity.json"

echo "==> Proving Redis DB0/DB1 persistence after restart"
restore_compose restart redis
wait_for_restore_service redis
verify_redis_markers redis-restart

{
  echo "commit_sha=$(git -C "$ROOT_DIR" rev-parse HEAD)"
  echo "started_at_utc=$STARTED_AT_UTC"
  echo "completed_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "source_project=$SOURCE_PROJECT"
  echo "restore_project=$RESTORE_PROJECT"
  echo "postgres_restore=ok"
  echo "postgres_restart=ok"
  echo "redis_restore=ok"
  echo "redis_restart=ok"
  echo "integrity_match=ok"
  echo "secret_artifacts_uploaded=false"
} >"$ARTIFACT_DIR/recovery-summary.txt"

echo "F13B_PRODUCTION_RECOVERY_SMOKE_OK"
