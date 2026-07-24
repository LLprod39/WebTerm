#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FIXTURE_REF="${F13C_FIXTURE_REF:?Set F13C_FIXTURE_REF}"
EXPECTED_FIXTURE_SHA="${F13C_EXPECTED_FIXTURE_SHA:?Set F13C_EXPECTED_FIXTURE_SHA}"
FIXTURE_NAME="${F13C_FIXTURE_NAME:-fixture}"
SLUG="$(printf '%s' "$FIXTURE_NAME" | tr -cs '[:alnum:]' '-' | tr '[:upper:]' '[:lower:]' | sed 's/^-//;s/-$//')"
PROJECT_NAME="webterm-f13c-${SLUG}"
COMPOSE_FILE="$ROOT_DIR/docker-compose.production.yml"
RECOVERY_COMPOSE_FILE="$ROOT_DIR/docker-compose.production.recovery.yml"
ENV_FILE="$ROOT_DIR/.env.production"
RESTORE_ENV="$ROOT_DIR/.env.production.restore"
ARTIFACT_DIR="${F13C_ARTIFACT_DIR:-$ROOT_DIR/.ci-artifacts/production-lifecycle/$SLUG}"
SENSITIVE_DIR="$(mktemp -d)"
FIXTURE_DIR="$SENSITIVE_DIR/fixture-source"
BACKUP_DIR="$SENSITIVE_DIR/postgres"
FIXTURE_IMAGE="webterm-f13c-${SLUG}-fixture:local"
CURRENT_IMAGE="webterm-f13c-${SLUG}-current:local"
ROLLBACK_CONTAINER="webterm-f13c-${SLUG}-rollback"
AUTH_USERNAME="lifecycle-user-01"
AUTH_PASSWORD="F13cLifecyclePass123!"
STARTED_AT_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
COMPOSE_STARTED=0

mkdir -p "$ARTIFACT_DIR" "$FIXTURE_DIR" "$BACKUP_DIR"
exec > >(tee "$ARTIFACT_DIR/production-upgrade-rollback-smoke.log") 2>&1

compose() {
  docker compose \
    --project-name "$PROJECT_NAME" \
    --env-file "$RESTORE_ENV" \
    -f "$COMPOSE_FILE" \
    -f "$RECOVERY_COMPOSE_FILE" \
    "$@"
}

cleanup() {
  local exit_code=$?
  trap - EXIT
  set +e
  docker rm -f "$ROLLBACK_CONTAINER" >/dev/null 2>&1
  if [[ "$COMPOSE_STARTED" -eq 1 ]]; then
    compose ps --format json >"$ARTIFACT_DIR/compose-ps.json" 2>&1
    compose down -v --remove-orphans
  fi
  rm -f "$ENV_FILE" "$RESTORE_ENV"
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

wait_for_service() {
  local service="$1"
  local started_at
  started_at="$(date +%s)"
  while true; do
    local container_id status
    container_id="$(compose ps -q "$service" | head -n 1)"
    status=""
    if [[ -n "$container_id" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
    fi
    if [[ "$status" == "healthy" ]]; then
      echo "[ok] $service is healthy"
      return 0
    fi
    if [[ "$status" == "exited" || "$status" == "dead" ]]; then
      echo "$service failed with state $status" >&2
      return 1
    fi
    if (( $(date +%s) - started_at >= 180 )); then
      echo "Timed out waiting for $service (last state: ${status:-missing})" >&2
      return 1
    fi
    sleep 3
  done
}

write_environment() {
  if [[ -e "$ENV_FILE" || -e "$RESTORE_ENV" ]]; then
    echo "Refusing to overwrite an existing production environment" >&2
    exit 1
  fi
  cp "$ROOT_DIR/.env.production.example" "$ENV_FILE"
  python3 - "$ENV_FILE" <<'PY'
from pathlib import Path
import secrets
import sys

path = Path(sys.argv[1])
values = {
    "PUBLIC_BIND_HOST": "127.0.0.1",
    "PUBLIC_HTTP_PORT": "38080",
    "PUBLIC_HTTPS_PORT": "38443",
    "FRONTEND_PORT": "38081",
    "DJANGO_BIND_HOST": "127.0.0.1",
    "DJANGO_HOST_PORT": "39000",
    "POSTGRES_BIND_HOST": "127.0.0.1",
    "POSTGRES_HOST_PORT": "35432",
    "REDIS_BIND_HOST": "127.0.0.1",
    "REDIS_HOST_PORT": "36379",
    "SITE_URL": "https://127.0.0.1:38443",
    "FRONTEND_APP_URL": "https://127.0.0.1:38443",
    "ALLOWED_HOSTS": "127.0.0.1,localhost,backend",
    "CSRF_TRUSTED_ORIGINS": "https://127.0.0.1:38443,https://localhost:38443",
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
    "MANAGED_SECRET_KEY": secrets.token_urlsafe(64),
    "MASTER_PASSWORD": secrets.token_urlsafe(48),
    "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
    "STUDIO_MCP_RUNNER_TOKEN": secrets.token_urlsafe(48),
    "PLUGIN_MARKETPLACE_RELEASE_MODE": "disabled",
}
lines = path.read_text(encoding="utf-8").splitlines()
seen = set()
output = []
for line in lines:
    if line and not line.lstrip().startswith("#") and "=" in line:
        key = line.split("=", 1)[0].strip()
        if key in values:
            output.append(f"{key}={values[key]}")
            seen.add(key)
            continue
    output.append(line)
for key, value in values.items():
    if key not in seen:
        output.append(f"{key}={value}")
path.write_text("\n".join(output) + "\n", encoding="utf-8")
PY
  cp "$ENV_FILE" "$RESTORE_ENV"
  chmod 600 "$ENV_FILE" "$RESTORE_ENV"
}

resolve_network() {
  docker network ls \
    --filter "label=com.docker.compose.project=$PROJECT_NAME" \
    --filter 'label=com.docker.compose.network=default' \
    --format '{{.Name}}' | head -n 1
}

run_image() {
  local image="$1"
  shift
  docker run --rm \
    --network "$COMPOSE_NETWORK" \
    --env-file "$ENV_FILE" \
    -e DJANGO_SETTINGS_MODULE=web_ui.settings.production \
    "$image" "$@"
}

write_probe() {
  local image="$1"
  local target="$2"
  docker run --rm \
    --network "$COMPOSE_NETWORK" \
    --env-file "$ENV_FILE" \
    -e DJANGO_SETTINGS_MODULE=web_ui.settings.production \
    -e "LIFECYCLE_AUTH_USERNAME=$AUTH_USERNAME" \
    -e "LIFECYCLE_AUTH_PASSWORD=$AUTH_PASSWORD" \
    --volume "$ROOT_DIR/scripts/release_lifecycle_probe.py:/tmp/release_lifecycle_probe.py:ro" \
    "$image" python /tmp/release_lifecycle_probe.py >"$target"
}

require_command curl
require_command docker
require_command git
require_command python3
require_command tar

ACTUAL_FIXTURE_SHA="$(git -C "$ROOT_DIR" rev-parse --verify "$FIXTURE_REF^{commit}")"
if [[ "$ACTUAL_FIXTURE_SHA" != "$EXPECTED_FIXTURE_SHA" ]]; then
  echo "Fixture $FIXTURE_REF resolved to $ACTUAL_FIXTURE_SHA, expected $EXPECTED_FIXTURE_SHA" >&2
  exit 1
fi
CURRENT_SHA="$(git -C "$ROOT_DIR" rev-parse HEAD)"
if ! git -C "$ROOT_DIR" merge-base --is-ancestor "$ACTUAL_FIXTURE_SHA" "$CURRENT_SHA"; then
  echo "Fixture $FIXTURE_REF is not an ancestor of the target commit" >&2
  exit 1
fi

echo "==> Verifying migration immutability from $FIXTURE_REF"
python3 "$ROOT_DIR/scripts/verify_migration_history.py" \
  --repo "$ROOT_DIR" \
  --from-ref "$FIXTURE_REF" \
  --to-ref "$CURRENT_SHA" \
  --output "$ARTIFACT_DIR/migration-history.json"
git -C "$ROOT_DIR" diff --name-status "$ACTUAL_FIXTURE_SHA..$CURRENT_SHA" -- '*/migrations/*.py' \
  >"$ARTIFACT_DIR/migration-diff.txt"

echo "==> Exporting the immutable fixture and building both application images"
git -C "$ROOT_DIR" archive "$ACTUAL_FIXTURE_SHA" | tar -x -C "$FIXTURE_DIR"
docker build --file "$FIXTURE_DIR/docker/backend.Dockerfile" --tag "$FIXTURE_IMAGE" "$FIXTURE_DIR"
docker build --file "$ROOT_DIR/docker/backend.Dockerfile" --tag "$CURRENT_IMAGE" "$ROOT_DIR"
FIXTURE_IMAGE_ID="$(docker image inspect "$FIXTURE_IMAGE" --format '{{.Id}}')"
CURRENT_IMAGE_ID="$(docker image inspect "$CURRENT_IMAGE" --format '{{.Id}}')"

write_environment
export F13B_BACKEND_IMAGE="$CURRENT_IMAGE"
COMPOSE_STARTED=1
compose up -d postgres redis
wait_for_service postgres
wait_for_service redis
COMPOSE_NETWORK="$(resolve_network)"
if [[ -z "$COMPOSE_NETWORK" ]]; then
  echo "Unable to resolve the lifecycle Compose network" >&2
  exit 1
fi

echo "==> Applying the fixture migration graph and seeding business data"
run_image "$FIXTURE_IMAGE" python manage.py migrate --noinput \
  | tee "$ARTIFACT_DIR/fixture-migrate.txt"
run_image "$FIXTURE_IMAGE" python manage.py showmigrations --plan \
  >"$ARTIFACT_DIR/fixture-migration-plan.txt"
run_image "$FIXTURE_IMAGE" python manage.py seed_multi_user_smoke \
  --users 1 \
  --password "$AUTH_PASSWORD" \
  --prefix lifecycle-user \
  --ssh-host lifecycle.invalid \
  --ssh-port 22 \
  --ssh-username lifecycle \
  --ssh-password fixture-only \
  --json >"$SENSITIVE_DIR/fixture-seed.json"
write_probe "$FIXTURE_IMAGE" "$ARTIFACT_DIR/fixture-integrity.json"

echo "==> Taking the mandatory pre-upgrade database backup"
BACKUP_DIR="$BACKUP_DIR" \
PROJECT_NAME="$PROJECT_NAME" \
ENV_FILE="$RESTORE_ENV" \
COMPOSE_FILE="$COMPOSE_FILE" \
COMPOSE_OVERRIDE_FILE="$RECOVERY_COMPOSE_FILE" \
RETENTION_DAILY=1 \
RETENTION_WEEKLY=0 \
  "$ROOT_DIR/scripts/backup_postgres.sh"
DUMP_PATH="$(find "$BACKUP_DIR" -maxdepth 1 -type f -name 'webterm_*.dump' | head -n 1)"
if [[ -z "$DUMP_PATH" ]]; then
  echo "Pre-upgrade backup was not created" >&2
  exit 1
fi
(
  cd "$BACKUP_DIR"
  sha256sum "$(basename "$DUMP_PATH")"
) >"$ARTIFACT_DIR/pre-upgrade-backup.sha256"

echo "==> Upgrading the fixture database with the target application image"
UPGRADE_STARTED="$(date +%s)"
run_image "$CURRENT_IMAGE" python manage.py migrate --noinput \
  | tee "$ARTIFACT_DIR/target-migrate.txt"
run_image "$CURRENT_IMAGE" python manage.py makemigrations --check --dry-run \
  | tee "$ARTIFACT_DIR/target-migration-drift.txt"
run_image "$CURRENT_IMAGE" python manage.py showmigrations --plan \
  >"$ARTIFACT_DIR/target-migration-plan.txt"
write_probe "$CURRENT_IMAGE" "$ARTIFACT_DIR/target-integrity.json"
cmp "$ARTIFACT_DIR/fixture-integrity.json" "$ARTIFACT_DIR/target-integrity.json"
UPGRADE_SECONDS="$(( $(date +%s) - UPGRADE_STARTED ))"

echo "==> Deploying the fixture image against the upgraded schema (application rollback)"
docker run -d \
  --name "$ROLLBACK_CONTAINER" \
  --network "$COMPOSE_NETWORK" \
  --env-file "$ENV_FILE" \
  -e DJANGO_SETTINGS_MODULE=web_ui.settings.production \
  --publish 127.0.0.1:39090:9000 \
  "$FIXTURE_IMAGE" \
  python -m gunicorn web_ui.wsgi:application --bind 0.0.0.0:9000 --workers 1 --timeout 60 \
  >/dev/null
for _attempt in $(seq 1 60); do
  if curl --fail --silent --show-error \
    --header 'X-Forwarded-Proto: https' \
    --header 'Host: 127.0.0.1' \
    http://127.0.0.1:39090/api/health/ >"$ARTIFACT_DIR/application-rollback-health.json"; then
    break
  fi
  sleep 2
done
curl --fail --silent --show-error \
  --header 'X-Forwarded-Proto: https' \
  --header 'Host: 127.0.0.1' \
  http://127.0.0.1:39090/api/health/ >/dev/null
write_probe "$FIXTURE_IMAGE" "$ARTIFACT_DIR/application-rollback-integrity.json"
cmp "$ARTIFACT_DIR/fixture-integrity.json" "$ARTIFACT_DIR/application-rollback-integrity.json"
docker rm -f "$ROLLBACK_CONTAINER" >/dev/null

echo "==> Restoring the pre-upgrade database instead of reversing migrations"
RESTORE_STARTED="$(date +%s)"
RESTORE_CONFIRM=RESTORE_WEBTERM \
PROJECT_NAME="$PROJECT_NAME" \
ENV_FILE="$RESTORE_ENV" \
COMPOSE_FILE="$COMPOSE_FILE" \
COMPOSE_OVERRIDE_FILE="$RECOVERY_COMPOSE_FILE" \
  "$ROOT_DIR/scripts/restore_postgres.sh" "$DUMP_PATH" \
  | tee "$ARTIFACT_DIR/database-restore.txt"
write_probe "$FIXTURE_IMAGE" "$ARTIFACT_DIR/restored-fixture-integrity.json"
cmp "$ARTIFACT_DIR/fixture-integrity.json" "$ARTIFACT_DIR/restored-fixture-integrity.json"
RESTORE_SECONDS="$(( $(date +%s) - RESTORE_STARTED ))"

{
  echo "fixture_name=$FIXTURE_NAME"
  echo "fixture_ref=$FIXTURE_REF"
  echo "fixture_sha=$ACTUAL_FIXTURE_SHA"
  echo "target_sha=$CURRENT_SHA"
  echo "fixture_image_id=$FIXTURE_IMAGE_ID"
  echo "target_image_id=$CURRENT_IMAGE_ID"
  echo "started_at_utc=$STARTED_AT_UTC"
  echo "completed_at_utc=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "upgrade_seconds=$UPGRADE_SECONDS"
  echo "database_restore_seconds=$RESTORE_SECONDS"
  echo "application_rollback_on_upgraded_schema=ok"
  echo "database_reverse_migrations_attempted=false"
  echo "database_restore=ok"
  echo "business_integrity=ok"
  echo "secret_artifacts_uploaded=false"
} >"$ARTIFACT_DIR/lifecycle-summary.txt"

echo "F13C_PRODUCTION_UPGRADE_ROLLBACK_SMOKE_OK"
