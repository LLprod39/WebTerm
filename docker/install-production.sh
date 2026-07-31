#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_TEMPLATE="$ROOT_DIR/.env.production.example"
ENV_FILE="$ROOT_DIR/.env.production"
COMPOSE_FILE="$ROOT_DIR/docker-compose.production.yml"
PROJECT_NAME="webtrerm-prod"
WITH_MCP=1
WITH_TELEGRAM_BOT=0
DO_BUILD=1
DO_PULL=0
GENERATE_SECRETS=0
VALIDATE_ONLY=0
SKIP_HEALTHCHECKS=0
SKIP_SMOKE=0
CREATE_SUPERUSER=0
SUPERUSER_USERNAME=""
SUPERUSER_EMAIL=""
SUPERUSER_PASSWORD=""
SUPERUSER_PASSWORD_SOURCE=""
SUPERUSER_PASSWORD_FILE=""
ADMIN_PROFILE="admin_full"

print_help() {
  cat <<'EOF'
Usage: ./docker/install-production.sh [options]

Full production bootstrap for the Docker Compose stack.
The script will:
  1. create .env.production from .env.production.example when missing
  2. optionally generate missing secrets
  3. validate required production env values
  4. validate docker compose config
  5. generate self-signed nginx TLS certs when missing
  6. start the full stack (API, SPA, nginx, MCP, workers, celery)
  7. wait for core + background worker readiness
  8. run Django migrate/checks inside the backend container
  9. optionally create a platform admin (superuser + admin_full features)
 10. smoke-check HTTP health endpoints
 11. print login URL and maintenance commands

Default stack services:
  postgres, redis, backend, frontend, nginx,
  mcp-runner,
  scheduled-pipelines, scheduled-agents, monitor,
  ops-supervisor (agent execution + watchers + memory dreams),
  kubernetes-ops-sync, celery-worker
  optional profiles: telegram-bot, mars-agent

Options:
  --env-file PATH              Path to env file (default: .env.production)
  --compose-file PATH          Path to compose file (default: docker-compose.production.yml)
  --project-name NAME          Docker compose project name (default: webtrerm-prod)
  --with-mcp                   Backward-compatible no-op: MCP services are already enabled by default
  --with-telegram-bot          Also start the telegram-bot profile service
  --pull                       Pull newer images before startup
  --no-build                   Do not build local images during startup
  --generate-secrets           Auto-fill placeholder DJANGO_SECRET_KEY/POSTGRES_PASSWORD
  --skip-healthchecks          Skip waiting for service health
  --skip-smoke                 Skip post-start HTTP health smoke checks
  --validate-only              Only validate env + compose config, do not start services
  --create-superuser           Create Django superuser after stack startup
  --superuser-username USER    Superuser username for --create-superuser
  --superuser-email EMAIL      Superuser email for --create-superuser
  --superuser-password-stdin   Read the superuser password from one stdin line
  --superuser-password-file P  Read it from a non-symlink file with mode 600
  --admin-profile NAME         Access profile for superuser (default: admin_full)
  -h, --help                   Show this help

Examples:
  ./docker/install-production.sh --generate-secrets
  ./docker/install-production.sh --pull --generate-secrets
  ./docker/install-production.sh --create-superuser \
    --superuser-username admin \
    --superuser-email admin@example.com
  printf '%s\n' "$ADMIN_PASSWORD" | ./docker/install-production.sh \
    --create-superuser --superuser-username admin --superuser-password-stdin
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
    --with-telegram-bot)
      WITH_TELEGRAM_BOT=1
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
    --skip-smoke)
      SKIP_SMOKE=1
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
    --superuser-password-stdin)
      [[ -z "$SUPERUSER_PASSWORD_SOURCE" ]] || {
        echo "Error: choose only one superuser password source" >&2
        exit 1
      }
      SUPERUSER_PASSWORD_SOURCE="stdin"
      shift
      ;;
    --superuser-password-file)
      [[ -z "$SUPERUSER_PASSWORD_SOURCE" ]] || {
        echo "Error: choose only one superuser password source" >&2
        exit 1
      }
      SUPERUSER_PASSWORD_SOURCE="file"
      SUPERUSER_PASSWORD_FILE="${2:-}"
      shift 2
      ;;
    --admin-profile)
      ADMIN_PROFILE="${2:-admin_full}"
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
  if [[ "${WITH_TELEGRAM_BOT:-0}" -eq 1 ]]; then
    args+=(--profile telegram-bot)
  fi
  docker "${args[@]}" "$@"
}

copy_env_if_missing() {
  umask 077
  if [[ -L "$ENV_FILE" ]]; then
    echo "Error: refusing symbolic-link env file: $ENV_FILE" >&2
    exit 1
  fi
  if [[ -f "$ENV_FILE" ]]; then
    chmod 600 "$ENV_FILE"
    return 0
  fi
  if [[ ! -f "$ENV_TEMPLATE" ]]; then
    echo "Error: env template not found: $ENV_TEMPLATE" >&2
    exit 1
  fi
  cp "$ENV_TEMPLATE" "$ENV_FILE"
  chmod 600 "$ENV_FILE"
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
    replace-*|change-me*|change_me*|changeme|ChangeMe*|example|example.com|*example.com*)
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

ensure_nginx_ssl_files() {
  local ssl_dir="$ROOT_DIR/docker/nginx/ssl"
  local cert_file="$ssl_dir/mini-prod-selfsigned.crt"
  local key_file="$ssl_dir/mini-prod-selfsigned.key"

  if [[ -f "$cert_file" && -f "$key_file" ]]; then
    return 0
  fi

  require_cmd openssl
  mkdir -p "$ssl_dir"

  local common_name
  common_name="$(read_env_value "ALLOWED_HOSTS" | cut -d',' -f1 | xargs)"
  if [[ -z "$common_name" ]]; then
    common_name="localhost"
  fi

  openssl req \
    -x509 \
    -nodes \
    -newkey rsa:2048 \
    -days 365 \
    -keyout "$key_file" \
    -out "$cert_file" \
    -subj "/CN=$common_name" >/dev/null 2>&1
  chmod 600 "$key_file" 2>/dev/null || true
  echo "[ok] generated self-signed nginx certificate: $cert_file"
}

validate_required_env() {
  local required_keys=(
    DJANGO_SECRET_KEY
    MANAGED_SECRET_KEY
    SITE_URL
    FRONTEND_APP_URL
    ALLOWED_HOSTS
    CSRF_TRUSTED_ORIGINS
    POSTGRES_DB
    POSTGRES_USER
    POSTGRES_PASSWORD
    AGENT_COMMAND_RUNNER_IMAGE
  )
  local key value
  for key in "${required_keys[@]}"; do
    value="$(read_env_value "$key")"
    if is_placeholder_value "$key" "$value"; then
      echo "Error: env key $key is missing or still uses a placeholder value in $ENV_FILE" >&2
      exit 1
    fi
  done
  local runner_image
  runner_image="$(read_env_value "AGENT_COMMAND_RUNNER_IMAGE")"
  if [[ ! "$runner_image" =~ ^(sha256:[0-9a-f]{64}|[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64})$ ]]; then
    echo "Error: AGENT_COMMAND_RUNNER_IMAGE must be an immutable sha256 image ID or repository digest" >&2
    exit 1
  fi
}

ensure_agent_command_runner_image() {
  local configured image_id
  configured="${AGENT_COMMAND_RUNNER_IMAGE:-$(read_env_value "AGENT_COMMAND_RUNNER_IMAGE")}"
  if [[ "$configured" =~ ^[a-z0-9][a-z0-9._:/-]*@sha256:[0-9a-f]{64}$ ]]; then
    upsert_env_value "AGENT_COMMAND_RUNNER_IMAGE" "$configured"
    if [[ "$VALIDATE_ONLY" -eq 0 ]] && ! docker image inspect "$configured" >/dev/null 2>&1; then
      echo "==> Pulling the pinned ephemeral agent command runner"
      docker pull "$configured"
    fi
    return 0
  fi
  if [[ "$configured" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    upsert_env_value "AGENT_COMMAND_RUNNER_IMAGE" "$configured"
    if [[ "$VALIDATE_ONLY" -eq 0 ]] && ! docker image inspect "$configured" >/dev/null 2>&1; then
      echo "Error: AGENT_COMMAND_RUNNER_IMAGE references a local image ID that is not present" >&2
      exit 1
    fi
    return 0
  fi
  if [[ "$DO_BUILD" -ne 1 ]]; then
    echo "Error: --no-build requires AGENT_COMMAND_RUNNER_IMAGE pinned by sha256 digest" >&2
    exit 1
  fi
  echo "==> Building the ephemeral agent command runner"
  docker build \
    --tag webterm-agent-command-runner:installer \
    --file "$ROOT_DIR/docker/agent-command-runner/Dockerfile" \
    "$ROOT_DIR"
  image_id="$(docker image inspect --format '{{.Id}}' webterm-agent-command-runner:installer)"
  if [[ ! "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]]; then
    echo "Error: built agent command runner did not produce an immutable image ID" >&2
    exit 1
  fi
  upsert_env_value "AGENT_COMMAND_RUNNER_IMAGE" "$image_id"
  echo "[ok] pinned agent command runner: $image_id"
}

configure_agent_command_network() {
  local configured
  configured="${AGENT_COMMAND_DOCKER_NETWORK:-$(read_env_value "AGENT_COMMAND_DOCKER_NETWORK")}"
  if [[ -z "$configured" || "$configured" == "bridge" ]]; then
    upsert_env_value "AGENT_COMMAND_DOCKER_NETWORK" "${PROJECT_NAME}_default"
    echo "[ok] agent command runner network: ${PROJECT_NAME}_default"
  else
    upsert_env_value "AGENT_COMMAND_DOCKER_NETWORK" "$configured"
  fi
}

configure_docker_socket_gid() {
  local configured
  configured="$(read_env_value "DOCKER_SOCKET_GID")"
  if [[ "$configured" =~ ^[0-9]+$ ]]; then
    export DOCKER_SOCKET_GID="$configured"
    return 0
  fi
  if [[ -S /var/run/docker.sock ]]; then
    export DOCKER_SOCKET_GID
    DOCKER_SOCKET_GID="$(stat -c '%g' /var/run/docker.sock)"
    echo "[ok] detected Docker socket group id: $DOCKER_SOCKET_GID"
    return 0
  fi
  export DOCKER_SOCKET_GID=0
  echo "[warn] /var/run/docker.sock is unavailable; playbook Docker proxy may not start" >&2
}

ensure_superuser_args() {
  if [[ "$CREATE_SUPERUSER" -eq 0 ]]; then
    return 0
  fi
  if [[ -z "$SUPERUSER_USERNAME" ]]; then
    echo "Error: --create-superuser requires --superuser-username" >&2
    exit 1
  fi
}

load_superuser_password() {
  if [[ "$CREATE_SUPERUSER" -eq 0 ]]; then
    return 0
  fi
  # shellcheck source=installer-secret-input.sh
  source "$ROOT_DIR/docker/installer-secret-input.sh"
  installer_read_secret \
    SUPERUSER_PASSWORD \
    "Superuser password" \
    "$SUPERUSER_PASSWORD_SOURCE" \
    "$SUPERUSER_PASSWORD_FILE"
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

run_backend_bootstrap() {
  echo "==> Validating the migrated backend"
  compose exec -T backend python manage.py check
  compose exec -T backend python manage.py check --deploy
}

create_superuser_if_requested() {
  if [[ "$CREATE_SUPERUSER" -eq 0 ]]; then
    return 0
  fi
  printf '%s\n' "$SUPERUSER_PASSWORD" | compose exec -T \
    backend python manage.py bootstrap_admin \
    --username "$SUPERUSER_USERNAME" \
    --email "$SUPERUSER_EMAIL" \
    --profile "$ADMIN_PROFILE" \
    --password-stdin
  unset SUPERUSER_PASSWORD
}

wait_for_stack() {
  echo "==> Waiting for core service health"
  wait_for_service postgres 180
  wait_for_service redis 120
  wait_for_service mcp-runner 120
  wait_for_service agent-command-docker-proxy 120
  wait_for_service backend 300
  wait_for_service frontend 240
  wait_for_service nginx 180

  echo "==> Waiting for background workers"
  # Workers usually have no Docker HEALTHCHECK — State.Status=running is enough.
  wait_for_service scheduled-pipelines 180
  wait_for_service operator-execution 180
  wait_for_service scheduled-agents 180
  wait_for_service monitor 180
  wait_for_service ops-supervisor 180
  wait_for_service kubernetes-ops-sync 180
  wait_for_service celery-worker 180
  if [[ "$WITH_TELEGRAM_BOT" -eq 1 ]]; then
    wait_for_service telegram-bot 180
  fi
}

smoke_check_http() {
  if [[ "$SKIP_SMOKE" -eq 1 ]]; then
    return 0
  fi
  echo "==> Smoke-checking public health endpoints"
  local site_url frontend_port http_port host
  site_url="$(read_env_value "SITE_URL")"
  frontend_port="$(read_env_value "FRONTEND_PORT")"
  http_port="$(read_env_value "PUBLIC_HTTP_PORT")"
  [[ -n "$frontend_port" ]] || frontend_port="8080"
  [[ -n "$http_port" ]] || http_port="80"
  host="$(read_env_value "ALLOWED_HOSTS" | cut -d',' -f1 | xargs)"
  [[ -n "$host" ]] || host="127.0.0.1"

  local candidates=()
  if [[ -n "$site_url" ]]; then
    candidates+=("${site_url%/}/api/health/")
  fi
  candidates+=("http://127.0.0.1:${frontend_port}/api/health/")
  candidates+=("http://127.0.0.1:${http_port}/api/health/")
  candidates+=("http://${host}:${frontend_port}/api/health/")

  local url ok=0
  for url in "${candidates[@]}"; do
    if curl -fsS --max-time 8 -H "Host: ${host}" "$url" >/dev/null 2>&1; then
      echo "[ok] health endpoint: $url"
      ok=1
      break
    fi
    echo "[wait] health not ready yet: $url"
  done
  if [[ "$ok" -ne 1 ]]; then
    echo "[warn] HTTP health smoke did not succeed yet; stack may still be finishing first boot"
    echo "       Try: curl -fsS http://127.0.0.1:${frontend_port}/api/health/"
  fi
}

print_runtime_summary() {
  local site_url frontend_port
  site_url="$(read_env_value "SITE_URL")"
  frontend_port="$(read_env_value "FRONTEND_PORT")"
  [[ -n "$frontend_port" ]] || frontend_port="8080"

  cat <<EOF

[done] Production stack is up and ready for use.

Stack:
  compose file: $COMPOSE_FILE
  env file:     $ENV_FILE
  project:      $PROJECT_NAME

Open:
  ${site_url:-http://127.0.0.1:${frontend_port}}
  http://127.0.0.1:${frontend_port}

Core services:
  postgres redis backend frontend nginx mcp-runner

Background workers (agents / studio / monitoring):
  ops-supervisor          # full/multi agent execution + watchers + memory dreams
  scheduled-agents        # cron/interval agent dispatch
  scheduled-pipelines     # Studio pipeline schedules
  operator-execution      # durable Operator Chat turns
  monitor                 # server monitoring cycles
  kubernetes-ops-sync       # Kubernetes inventory sync
  celery-worker           # async memory/tasks queue

Useful commands:
  docker compose --project-name $PROJECT_NAME --env-file $ENV_FILE -f $COMPOSE_FILE ps
  docker compose --project-name $PROJECT_NAME --env-file $ENV_FILE -f $COMPOSE_FILE logs -f backend ops-supervisor nginx
  docker compose --project-name $PROJECT_NAME --env-file $ENV_FILE -f $COMPOSE_FILE logs -f scheduled-agents celery-worker
  docker compose --project-name $PROJECT_NAME --env-file $ENV_FILE -f $COMPOSE_FILE restart ops-supervisor scheduled-agents
  docker compose --project-name $PROJECT_NAME --env-file $ENV_FILE -f $COMPOSE_FILE down
  docker compose --project-name $PROJECT_NAME --env-file $ENV_FILE -f $COMPOSE_FILE up -d --build

Optional profiles:
  # Telegram bot (needs TELEGRAM_BOT_TOKEN in env)
  docker compose --project-name $PROJECT_NAME --env-file $ENV_FILE -f $COMPOSE_FILE --profile telegram-bot up -d telegram-bot
  # MARS (disabled until MARS_AGENT_DOCKER_IMAGE is an exact release digest)
  docker compose --project-name $PROJECT_NAME --env-file $ENV_FILE -f $COMPOSE_FILE --profile mars-agent pull mars-agent
  docker compose --project-name $PROJECT_NAME --env-file $ENV_FILE -f $COMPOSE_FILE --profile mars-agent run --rm mars-agent

First login checklist:
  1. Sign in as admin
  2. Settings → AI: add at least one LLM API key
  3. Servers: add a host and open Terminal
  4. Agents: create a Mini agent and Run (no worker setup needed for mini)
  5. Full/multi agents use ops-supervisor automatically in this stack
EOF

  if [[ "$CREATE_SUPERUSER" -eq 1 ]]; then
    cat <<EOF

Admin account:
  username: $SUPERUSER_USERNAME
  password: supplied through private input and intentionally not displayed
  profile:  $ADMIN_PROFILE
EOF
  fi
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
  load_superuser_password

  if [[ "$GENERATE_SECRETS" -eq 1 ]]; then
    generate_secret_if_needed "DJANGO_SECRET_KEY" 64
    generate_secret_if_needed "MANAGED_SECRET_KEY" 64
    generate_secret_if_needed "POSTGRES_PASSWORD" 32
    generate_secret_if_needed "STUDIO_MCP_RUNNER_TOKEN" 64
  fi

  ensure_agent_command_runner_image
  configure_agent_command_network
  validate_required_env
  configure_docker_socket_gid

  echo "==> Validating docker compose config"
  compose config >/dev/null

  if [[ "$VALIDATE_ONLY" -eq 1 ]]; then
    echo "[done] Validation successful: $COMPOSE_FILE with $ENV_FILE"
    exit 0
  fi

  ensure_nginx_ssl_files

  if [[ "$DO_PULL" -eq 1 ]]; then
    echo "==> Pulling images"
    compose pull --ignore-pull-failures
  fi

  local up_args=(up -d)
  if [[ "$DO_BUILD" -eq 1 ]]; then
    up_args+=(--build)
  fi

  echo "==> Starting production stack (core + workers + MCP)"
  # Explicit service list starts the full runtime plane in one shot.
  local services=(
    postgres
    redis
    mcp-runner
    agent-command-docker-proxy
    playbook-docker-proxy
    backend
    playbook-execution-worker
    scheduled-pipelines
    operator-execution
    scheduled-agents
    monitor
    ops-supervisor
    kubernetes-ops-sync
    celery-worker
    frontend
    nginx
  )
  if [[ "$WITH_TELEGRAM_BOT" -eq 1 ]]; then
    services+=(telegram-bot)
  fi
  compose "${up_args[@]}" "${services[@]}"

  if [[ "$SKIP_HEALTHCHECKS" -eq 0 ]]; then
    wait_for_stack
  fi

  echo "==> Backend bootstrap / validation"
  run_backend_bootstrap

  echo "==> Superuser / admin bootstrap"
  create_superuser_if_requested

  smoke_check_http
  print_runtime_summary
}

main
