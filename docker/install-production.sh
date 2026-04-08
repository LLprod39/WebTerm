#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_TEMPLATE="$ROOT_DIR/.env.production.example"
ENV_FILE="$ROOT_DIR/.env.production"
COMPOSE_FILE="$ROOT_DIR/docker-compose.production.yml"
PROJECT_NAME="webtrerm-prod"
WITH_MCP=1
DO_BUILD=1
DO_PULL=0
GENERATE_SECRETS=0
VALIDATE_ONLY=0
SKIP_HEALTHCHECKS=0
CREATE_SUPERUSER=0
SUPERUSER_USERNAME=""
SUPERUSER_EMAIL=""
SUPERUSER_PASSWORD=""

print_help() {
  cat <<'EOF'
Usage: ./docker/install-production.sh [options]

Safe production bootstrap for the Docker Compose stack.
The script will:
  1. create .env.production from .env.production.example when missing
  2. optionally generate missing secrets
  3. validate required production env values
  4. validate docker compose config
  5. start/update the production stack
  6. wait for service health checks
  7. run Django checks inside the backend container
  8. optionally create a Django superuser
  9. start bundled MCP services (demo + keycloak) by default

Options:
  --env-file PATH              Path to env file (default: .env.production)
  --compose-file PATH          Path to compose file (default: docker-compose.production.yml)
  --project-name NAME          Docker compose project name (default: webtrerm-prod)
  --with-mcp                   Backward-compatible no-op: MCP services are already enabled by default
  --pull                       Pull newer images before startup
  --no-build                   Do not build local images during startup
  --generate-secrets           Auto-fill placeholder DJANGO_SECRET_KEY/POSTGRES_PASSWORD
  --skip-healthchecks          Skip waiting for service health
  --validate-only              Only validate env + compose config, do not start services
  --create-superuser           Create Django superuser after stack startup
  --superuser-username USER    Superuser username for --create-superuser
  --superuser-email EMAIL      Superuser email for --create-superuser
  --superuser-password PASS    Superuser password for --create-superuser
  -h, --help                   Show this help

Examples:
  ./docker/install-production.sh --generate-secrets
  ./docker/install-production.sh --pull --generate-secrets
  ./docker/install-production.sh --create-superuser \
    --superuser-username admin \
    --superuser-email admin@example.com \
    --superuser-password 'ChangeMe123!'
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      ENV_FILE="${2:-}"
      shift 2
      ;;
    --compose-file)
      COMPOSE_FILE="${2:-}"
      shift 2
      ;;
    --project-name)
      PROJECT_NAME="${2:-}"
      shift 2
      ;;
    --with-mcp)
      WITH_MCP=1
      shift
      ;;
    --pull)
      DO_PULL=1
      shift
      ;;
    --no-build)
      DO_BUILD=0
      shift
      ;;
    --generate-secrets)
      GENERATE_SECRETS=1
      shift
      ;;
    --skip-healthchecks)
      SKIP_HEALTHCHECKS=1
      shift
      ;;
    --validate-only)
      VALIDATE_ONLY=1
      shift
      ;;
    --create-superuser)
      CREATE_SUPERUSER=1
      shift
      ;;
    --superuser-username)
      SUPERUSER_USERNAME="${2:-}"
      shift 2
      ;;
    --superuser-email)
      SUPERUSER_EMAIL="${2:-}"
      shift 2
      ;;
    --superuser-password)
      SUPERUSER_PASSWORD="${2:-}"
      shift 2
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      print_help >&2
      exit 1
      ;;
  esac
done

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: required command not found: $cmd" >&2
    exit 1
  fi
}

compose() {
  local args=(
    compose
    --project-name "$PROJECT_NAME"
    --env-file "$ENV_FILE"
    -f "$COMPOSE_FILE"
  )
  docker "${args[@]}" "$@"
}

copy_env_if_missing() {
  if [[ -f "$ENV_FILE" ]]; then
    return 0
  fi
  if [[ ! -f "$ENV_TEMPLATE" ]]; then
    echo "Error: env template not found: $ENV_TEMPLATE" >&2
    exit 1
  fi
  cp "$ENV_TEMPLATE" "$ENV_FILE"
  echo "[ok] created env file: $ENV_FILE"
}

read_env_value() {
  local key="$1"
  python3 - "$ENV_FILE" "$key" <<'PY'
import pathlib
import sys

env_path = pathlib.Path(sys.argv[1])
target_key = sys.argv[2]

for raw_line in env_path.read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        continue
    key, value = line.split("=", 1)
    if key.strip() == target_key:
        print(value.strip())
        break
PY
}

upsert_env_value() {
  local key="$1"
  local value="$2"
  python3 - "$ENV_FILE" "$key" "$value" <<'PY'
import pathlib
import sys

env_path = pathlib.Path(sys.argv[1])
target_key = sys.argv[2]
target_value = sys.argv[3]

lines = env_path.read_text(encoding="utf-8").splitlines()
updated = False
result = []
for raw_line in lines:
    line = raw_line.strip()
    if not line or line.startswith("#") or "=" not in line:
        result.append(raw_line)
        continue
    key, _value = raw_line.split("=", 1)
    if key.strip() == target_key:
      result.append(f"{target_key}={target_value}")
      updated = True
    else:
      result.append(raw_line)

if not updated:
    result.append(f"{target_key}={target_value}")

env_path.write_text("\n".join(result) + "\n", encoding="utf-8")
PY
}

is_placeholder_value() {
  local key="$1"
  local value="$2"
  if [[ -z "$value" ]]; then
    return 0
  fi
  case "$value" in
    replace-*|changeme|ChangeMe*|example|example.com|*example.com*)
      return 0
      ;;
  esac
  if [[ "$key" == "DJANGO_SECRET_KEY" && "$value" == *"replace-with-a-long-random-secret"* ]]; then
    return 0
  fi
  return 1
}

random_string() {
  local length="$1"
  LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$length"
  printf '\n'
}

generate_secret_if_needed() {
  local key="$1"
  local length="$2"
  local current_value
  current_value="$(read_env_value "$key")"
  if ! is_placeholder_value "$key" "$current_value"; then
    return 0
  fi
  local new_value
  new_value="$(random_string "$length")"
  upsert_env_value "$key" "$new_value"
  echo "[ok] generated $key in $(basename "$ENV_FILE")"
}

validate_required_env() {
  local required_keys=(
    DJANGO_SECRET_KEY
    SITE_URL
    FRONTEND_APP_URL
    ALLOWED_HOSTS
    CSRF_TRUSTED_ORIGINS
    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD
  )
  local key value
  for key in "${required_keys[@]}"; do
    value="$(read_env_value "$key")"
    if is_placeholder_value "$key" "$value"; then
      echo "Error: env key $key is missing or still uses a placeholder value in $ENV_FILE" >&2
      exit 1
    fi
  done
}

ensure_superuser_args() {
  if [[ "$CREATE_SUPERUSER" -eq 0 ]]; then
    return 0
  fi
  if [[ -z "$SUPERUSER_USERNAME" || -z "$SUPERUSER_PASSWORD" ]]; then
    echo "Error: --create-superuser requires --superuser-username and --superuser-password" >&2
    exit 1
  fi
}

service_container_id() {
  compose ps -q "$1" | head -n 1
}

wait_for_service() {
  local service="$1"
  local timeout_seconds="${2:-240}"
  local started_at
  started_at="$(date +%s)"
  while true; do
    local container_id status
    container_id="$(service_container_id "$service")"
    if [[ -z "$container_id" ]]; then
      echo "[wait] $service container is not created yet"
    else
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
      case "$status" in
        healthy|running)
          echo "[ok] service ready: $service ($status)"
          return 0
          ;;
        exited|dead)
          echo "Error: service failed during startup: $service ($status)" >&2
          docker logs "$container_id" --tail 120 >&2 || true
          exit 1
          ;;
      esac
      echo "[wait] $service status: ${status:-unknown}"
    fi
    sleep 3
    if (( $(date +%s) - started_at >= timeout_seconds )); then
      echo "Error: timed out waiting for service: $service" >&2
      if [[ -n "$container_id" ]]; then
        docker logs "$container_id" --tail 120 >&2 || true
      fi
      exit 1
    fi
  done
}

run_backend_checks() {
  compose exec -T backend python manage.py check
  compose exec -T backend python manage.py check --deploy
}

create_superuser_if_requested() {
  if [[ "$CREATE_SUPERUSER" -eq 0 ]]; then
    return 0
  fi
  compose exec -T \
    -e DJANGO_SUPERUSER_USERNAME="$SUPERUSER_USERNAME" \
    -e DJANGO_SUPERUSER_EMAIL="$SUPERUSER_EMAIL" \
    -e DJANGO_SUPERUSER_PASSWORD="$SUPERUSER_PASSWORD" \
    backend python - <<'PY'
import os
from django.contrib.auth import get_user_model

User = get_user_model()
username = os.environ["DJANGO_SUPERUSER_USERNAME"]
email = os.environ.get("DJANGO_SUPERUSER_EMAIL", "")
password = os.environ["DJANGO_SUPERUSER_PASSWORD"]

user, created = User.objects.get_or_create(
    username=username,
    defaults={
        "email": email,
        "is_staff": True,
        "is_superuser": True,
        "is_active": True,
    },
)
if created:
    user.set_password(password)
    user.save()
    print(f"Created superuser: {username}")
else:
    changed = False
    if email and user.email != email:
        user.email = email
        changed = True
    if not user.is_staff:
        user.is_staff = True
        changed = True
    if not user.is_superuser:
        user.is_superuser = True
        changed = True
    if not user.is_active:
        user.is_active = True
        changed = True
    if changed:
        user.save(update_fields=["email", "is_staff", "is_superuser", "is_active"])
    print(f"Superuser already exists: {username}")
PY
}

main() {
  require_cmd docker
  require_cmd python3
  if ! docker compose version >/dev/null 2>&1; then
    echo "Error: docker compose v2 plugin is required" >&2
    exit 1
  fi
  if [[ ! -f "$COMPOSE_FILE" ]]; then
    echo "Error: compose file not found: $COMPOSE_FILE" >&2
    exit 1
  fi

  copy_env_if_missing
  ensure_superuser_args

  if [[ "$GENERATE_SECRETS" -eq 1 ]]; then
    generate_secret_if_needed "DJANGO_SECRET_KEY" 64
    generate_secret_if_needed "POSTGRES_PASSWORD" 32
  fi

  validate_required_env

  echo "==> Validating docker compose config"
  compose config >/dev/null

  if [[ "$VALIDATE_ONLY" -eq 1 ]]; then
    echo "[done] Validation successful: $COMPOSE_FILE with $ENV_FILE"
    exit 0
  fi

  if [[ "$DO_PULL" -eq 1 ]]; then
    echo "==> Pulling images"
    compose pull --ignore-pull-failures
  fi

  local up_args=(up -d)
  if [[ "$DO_BUILD" -eq 1 ]]; then
    up_args+=(--build)
  fi

  echo "==> Starting production stack"
  compose "${up_args[@]}"

  if [[ "$SKIP_HEALTHCHECKS" -eq 0 ]]; then
    echo "==> Waiting for service health"
    wait_for_service postgres 180
    wait_for_service redis 120
    wait_for_service mcp-demo 120
    wait_for_service mcp-keycloak 180
    wait_for_service backend 240
    wait_for_service frontend 180
    wait_for_service nginx 180
  fi

  echo "==> Running backend validation"
  run_backend_checks

  echo "==> Superuser bootstrap"
  create_superuser_if_requested

  cat <<EOF

[done] Production stack is up.

Stack:
  compose file: $COMPOSE_FILE
  env file:     $ENV_FILE
  project:      $PROJECT_NAME

Useful commands:
  docker compose --project-name $PROJECT_NAME --env-file $ENV_FILE -f $COMPOSE_FILE ps
  docker compose --project-name $PROJECT_NAME --env-file $ENV_FILE -f $COMPOSE_FILE logs -f backend nginx
  docker compose --project-name $PROJECT_NAME --env-file $ENV_FILE -f $COMPOSE_FILE exec backend python manage.py createsuperuser

Next checks:
  1. Open SITE_URL and verify login.
  2. Run one terminal connection, one agent, and one pipeline.
  3. Confirm admin-only activity logs and health endpoints.
EOF
}

main
