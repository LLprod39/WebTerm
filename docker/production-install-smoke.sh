#!/usr/bin/env bash
set -Eeuo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT_DIR/.env.production"
COMPOSE_FILE="$ROOT_DIR/docker-compose.production.yml"
SMOKE_COMPOSE_FILE="$ROOT_DIR/docker-compose.production.smoke.yml"
ARTIFACT_DIR="${F13A_ARTIFACT_DIR:-$ROOT_DIR/.ci-artifacts/production-install-smoke}"
PROJECT_NAME="${F13A_PROJECT_NAME:-webterm-f13a-smoke}"
KEEP_UP="${F13A_KEEP_UP:-0}"
RELEASE_IMAGES="${F13A_RELEASE_IMAGES:-0}"
HTTPS_PORT="${F13A_HTTPS_PORT:-18443}"
ADMIN_USERNAME="f13a-admin"
ADMIN_PASSWORD="F13aSmokePass123!"
SMOKE_PASSWORD="F13aUserPass123!"
BASE_URL="https://127.0.0.1:${HTTPS_PORT}"
COOKIE_JAR="$ARTIFACT_DIR/admin-cookies.txt"
LOGIN_PAYLOAD="$ARTIFACT_DIR/admin-login-request.json"
STARTED=0
ENV_CREATED=0
TLS_CREATED=0
TLS_CERT="$ROOT_DIR/docker/nginx/ssl/mini-prod-selfsigned.crt"
TLS_KEY="$ROOT_DIR/docker/nginx/ssl/mini-prod-selfsigned.key"

mkdir -p "$ARTIFACT_DIR"
exec > >(tee "$ARTIFACT_DIR/production-install-smoke.log") 2>&1

compose() {
  docker compose \
    --project-name "$PROJECT_NAME" \
    --env-file "$ENV_FILE" \
    -f "$COMPOSE_FILE" \
    "$@"
}

smoke_compose() {
  docker compose \
    --project-name "$PROJECT_NAME" \
    --env-file "$ENV_FILE" \
    -f "$COMPOSE_FILE" \
    -f "$SMOKE_COMPOSE_FILE" \
    "$@"
}

collect_runtime_evidence() {
  set +e
  if [[ "$STARTED" -eq 1 ]]; then
    compose ps --format json >"$ARTIFACT_DIR/compose-ps.json" 2>&1
    compose images --format json >"$ARTIFACT_DIR/compose-images.json" 2>&1
    compose logs --no-color --timestamps --tail 400 >"$ARTIFACT_DIR/compose-logs.txt" 2>&1
  fi
  set -e
}

cleanup() {
  local exit_code=$?
  local retained=0
  trap - EXIT
  collect_runtime_evidence
  rm -f "$COOKIE_JAR" "$LOGIN_PAYLOAD"
  if [[ "$STARTED" -eq 1 && "$exit_code" -eq 0 && "$KEEP_UP" == "1" ]]; then
    retained=1
    echo "Retaining the successful F-13a stack for a parent recovery drill"
  elif [[ "$STARTED" -eq 1 ]]; then
    set +e
    smoke_compose down -v --remove-orphans
    set -e
  fi
  if [[ "$ENV_CREATED" -eq 1 && "$retained" -eq 0 ]]; then
    rm -f "$ENV_FILE"
  fi
  if [[ "$TLS_CREATED" -eq 1 && "$retained" -eq 0 ]]; then
    rm -f "$TLS_CERT" "$TLS_KEY"
  fi
  exit "$exit_code"
}
trap cleanup EXIT

require_command() {
  local command_name="$1"
  if ! command -v "$command_name" >/dev/null 2>&1; then
    echo "Missing required command: $command_name" >&2
    exit 1
  fi
}

assert_fresh_host() {
  local reserved_names=(
    mini-prod-postgres mini-prod-redis mini-prod-backend mini-prod-frontend mini-prod-nginx
    mini-prod-mcp-runner mini-prod-scheduled-pipelines mini-prod-pipeline-execution mini-prod-scheduled-agents
    mini-prod-history-pruner mini-prod-monitor mini-prod-ops-supervisor mini-prod-kubernetes-ops-sync mini-prod-celery-worker
    mini-prod-playbook-docker-proxy-smoke
    mini-prod-ssh-target-smoke
  )
  local existing_names
  existing_names="$(docker ps -a --format '{{.Names}}')"
  local name
  for name in "${reserved_names[@]}"; do
    if grep -Fqx "$name" <<<"$existing_names"; then
      echo "Refusing to reuse a host with an existing WebTerm container: $name" >&2
      exit 1
    fi
  done
}

wait_for_service() {
  local service="$1"
  local timeout_seconds="${2:-180}"
  local started_at
  started_at="$(date +%s)"
  while true; do
    local container_id status
    container_id="$(smoke_compose ps -q "$service" | head -n 1)"
    status=""
    if [[ -n "$container_id" ]]; then
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container_id" 2>/dev/null || true)"
    fi
    if [[ "$status" == "healthy" || "$status" == "running" ]]; then
      echo "[ok] $service is $status"
      return 0
    fi
    if [[ "$status" == "exited" || "$status" == "dead" ]]; then
      echo "$service failed with state $status" >&2
      return 1
    fi
    if (( $(date +%s) - started_at >= timeout_seconds )); then
      echo "Timed out waiting for $service (last state: ${status:-missing})" >&2
      return 1
    fi
    sleep 3
  done
}

write_environment() {
  if [[ -e "$ENV_FILE" ]]; then
    echo "Refusing to overwrite existing production environment: $ENV_FILE" >&2
    exit 1
  fi
  if [[ -e "$TLS_CERT" && ! -e "$TLS_KEY" ]] || [[ ! -e "$TLS_CERT" && -e "$TLS_KEY" ]]; then
    echo "Refusing to replace an incomplete existing TLS certificate pair" >&2
    exit 1
  fi
  if [[ ! -e "$TLS_CERT" && ! -e "$TLS_KEY" ]]; then
    TLS_CREATED=1
  fi
  cp "$ROOT_DIR/.env.production.example" "$ENV_FILE"
  ENV_CREATED=1
  python3 - "$ENV_FILE" "$HTTPS_PORT" <<'PY'
from __future__ import annotations

import secrets
import os
import sys
from pathlib import Path

path = Path(sys.argv[1])
https_port = sys.argv[2]
values = {
    "PUBLIC_BIND_HOST": "127.0.0.1",
    "PUBLIC_HTTP_PORT": "18080",
    "PUBLIC_HTTPS_PORT": https_port,
    "FRONTEND_PORT": "18081",
    "DJANGO_BIND_HOST": "127.0.0.1",
    "DJANGO_HOST_PORT": "19000",
    "POSTGRES_BIND_HOST": "127.0.0.1",
    "POSTGRES_HOST_PORT": "15432",
    "REDIS_BIND_HOST": "127.0.0.1",
    "REDIS_HOST_PORT": "16379",
    "SITE_URL": f"https://127.0.0.1:{https_port}",
    "FRONTEND_APP_URL": f"https://127.0.0.1:{https_port}",
    "ALLOWED_HOSTS": "127.0.0.1,localhost,nginx,backend",
    "CSRF_TRUSTED_ORIGINS": (
        f"https://127.0.0.1:{https_port},https://localhost:{https_port},https://nginx:8443"
    ),
    "DJANGO_SECRET_KEY": secrets.token_urlsafe(64),
    "MANAGED_SECRET_KEY": secrets.token_urlsafe(64),
    "POSTGRES_PASSWORD": secrets.token_urlsafe(32),
    "STUDIO_MCP_RUNNER_TOKEN": secrets.token_urlsafe(48),
    "AGENT_COMMAND_RUNNER_IMAGE": os.environ.get("AGENT_COMMAND_RUNNER_IMAGE", ""),
    "PLUGIN_MARKETPLACE_RELEASE_MODE": "disabled",
    "SMOKE_SSH_USERNAME": "smoke",
    "SMOKE_SSH_PASSWORD": "smoke-password",
}

lines = path.read_text(encoding="utf-8").splitlines()
seen: set[str] = set()
result: list[str] = []
for raw_line in lines:
    stripped = raw_line.strip()
    if stripped and not stripped.startswith("#") and "=" in raw_line:
        key = raw_line.split("=", 1)[0].strip()
        if key in values:
            result.append(f"{key}={values[key]}")
            seen.add(key)
            continue
    result.append(raw_line)
for key, value in values.items():
    if key not in seen:
        result.append(f"{key}={value}")
path.write_text("\n".join(result) + "\n", encoding="utf-8")
PY
  chmod 600 "$ENV_FILE"
}

record_host_metadata() {
  local actual_sha expected_sha
  actual_sha="$(git -C "$ROOT_DIR" rev-parse HEAD)"
  expected_sha="${GITHUB_SHA:-$actual_sha}"
  if [[ "$actual_sha" != "$expected_sha" ]]; then
    echo "Checked-out SHA $actual_sha does not match expected SHA $expected_sha" >&2
    exit 1
  fi
  if [[ -n "$(git -C "$ROOT_DIR" status --porcelain --untracked-files=no)" ]]; then
    echo "Tracked working tree must be clean before production smoke" >&2
    git -C "$ROOT_DIR" status --short >&2
    exit 1
  fi

  {
    echo "commit_sha=$actual_sha"
    echo "version=$(tr -d '\r\n' <"$ROOT_DIR/VERSION")"
    echo "runner_os=${RUNNER_OS:-unknown}"
    echo "runner_image=${ImageOS:-unknown}"
    echo "kernel=$(uname -srmo)"
    echo "python=$(python3 --version 2>&1)"
    echo "docker=$(docker version --format '{{.Server.Version}}')"
    echo "compose=$(docker compose version --short)"
  } >"$ARTIFACT_DIR/host-metadata.txt"
}

probe_authenticated_readiness() {
  local csrf_token
  curl --insecure --fail --silent --show-error \
    --cookie-jar "$COOKIE_JAR" \
    "$BASE_URL/api/auth/csrf/" >"$ARTIFACT_DIR/csrf.json"
  csrf_token="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1], encoding="utf-8"))["csrfToken"])' "$ARTIFACT_DIR/csrf.json")"

  printf '%s\n' "$ADMIN_PASSWORD" | python3 -c '
import json
import sys
from pathlib import Path

password = sys.stdin.readline().removesuffix("\n").removesuffix("\r")
if not password or sys.stdin.read(1):
    raise SystemExit("admin password stdin must contain exactly one non-empty line")
Path(sys.argv[1]).write_text(
    json.dumps({"username": sys.argv[2], "password": password, "auth_mode": "local"}),
    encoding="utf-8",
)
' "$LOGIN_PAYLOAD" "$ADMIN_USERNAME"
  chmod 600 "$LOGIN_PAYLOAD"
  curl --insecure --fail --silent --show-error \
    --cookie "$COOKIE_JAR" \
    --cookie-jar "$COOKIE_JAR" \
    --header "Content-Type: application/json" \
    --header "X-CSRFToken: $csrf_token" \
    --header "Origin: $BASE_URL" \
    --header "Referer: $BASE_URL/" \
    --data-binary "@$LOGIN_PAYLOAD" \
    "$BASE_URL/api/auth/login/" >"$ARTIFACT_DIR/admin-login-response.json"

  curl --insecure --fail --silent --show-error \
    --cookie "$COOKIE_JAR" \
    "$BASE_URL/api/settings/readiness/" >"$ARTIFACT_DIR/readiness.json"

  python3 - "$ARTIFACT_DIR/readiness.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload.get("success") is True, payload
checks = {item["key"]: item for item in payload.get("checks", [])}
for key in (
    "deployment_mode",
    "secret_placeholders",
    "managed_secret_key",
    "runtime_config_paths",
    "access_policy",
    "plugin_marketplace",
):
    assert checks.get(key, {}).get("severity") == "ready", (key, checks.get(key))

runtime_workers = checks.get("runtime_workers") or {}
worker_rows = {
    item.get("worker"): item
    for item in (runtime_workers.get("details", {}).get("workers") or [])
}
for worker in ("scheduled-pipelines", "pipeline-execution", "monitor"):
    assert worker_rows.get(worker, {}).get("ready") is True, (worker, worker_rows.get(worker))
print(json.dumps(payload.get("summary", {}), sort_keys=True))
PY
}

capture_worker_heartbeats() {
  compose exec -T backend python - <<'PY' >"$ARTIFACT_DIR/worker-heartbeats.json"
import json
import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "web_ui.settings.production")
import django

django.setup()

from django.utils import timezone
from servers.models import BackgroundWorkerState

required = {
    "studio_scheduled_pipelines",
    "studio_pipeline_execution",
    "studio_monitor",
    "scheduled_agents",
    "memory_dreams",
    "agent_execution",
    "watchers",
    "kubernetes_ops_sync",
}
rows = []
healthy = set()
now = timezone.now()
for state in BackgroundWorkerState.objects.all().order_by("worker_kind", "worker_key"):
    lease_current = bool(state.lease_expires_at and state.lease_expires_at > now)
    rows.append(
        {
            "worker_kind": state.worker_kind,
            "worker_key": state.worker_key,
            "status": state.status,
            "heartbeat_at": state.heartbeat_at.isoformat() if state.heartbeat_at else None,
            "lease_expires_at": state.lease_expires_at.isoformat() if state.lease_expires_at else None,
            "lease_current": lease_current,
            "last_error": state.last_error,
        }
    )
    if state.status == BackgroundWorkerState.STATUS_RUNNING and lease_current:
        healthy.add(state.worker_kind)

missing = sorted(required - healthy)
print(json.dumps({"healthy": sorted(healthy), "missing": missing, "workers": rows}, indent=2))
if missing:
    raise SystemExit(f"Missing current worker heartbeats: {', '.join(missing)}")
PY
}

require_command docker
require_command git
require_command curl
require_command python3
require_command openssl
require_command timeout
docker compose version >/dev/null
record_host_metadata
assert_fresh_host
write_environment

echo "==> Running the production installer on a fresh Linux host"
STARTED=1
install_args=(
  --env-file "$ENV_FILE"
  --compose-file "$COMPOSE_FILE"
  --project-name "$PROJECT_NAME"
  --create-superuser
  --superuser-username "$ADMIN_USERNAME"
  --superuser-email "f13a-admin@example.test"
  --superuser-password-stdin
)
if [[ "$RELEASE_IMAGES" == "1" ]]; then
  install_args+=(--pull --no-build)
fi
printf '%s\n' "$ADMIN_PASSWORD" | bash "$ROOT_DIR/docker/install-production.sh" "${install_args[@]}"

echo "==> Verifying agent commands have only the filtered Docker API"
compose exec -T backend sh -lc \
  'test "$DOCKER_HOST" = "tcp://agent-command-docker-proxy:2375" && test ! -S /var/run/docker.sock'
set +e
agent_privileged_output="$(
  compose exec -T backend sh -lc '
    docker run --pull=never --rm \
      --name webterm-agent-command-00000000000000000000000000000000 \
      --user 10001:10001 \
      --read-only \
      --cgroupns private \
      --network "$AGENT_COMMAND_DOCKER_NETWORK" \
      --cap-drop ALL \
      --security-opt no-new-privileges:true \
      --tmpfs /tmp:rw,noexec,nosuid,nodev,size=32m \
      --label webtrerm.runtime=agent-command \
      --cpus "$AGENT_COMMAND_DOCKER_CPUS" \
      --memory "$AGENT_COMMAND_DOCKER_MEMORY" \
      --pids-limit "$AGENT_COMMAND_DOCKER_PIDS_LIMIT" \
      --privileged \
      "$AGENT_COMMAND_RUNNER_IMAGE"
' 2>&1
)"
agent_privileged_status=$?
set -e
printf '%s\n' "$agent_privileged_output" | tee "$ARTIFACT_DIR/agent-command-proxy-privileged-denial.txt"
if [[ "$agent_privileged_status" -eq 0 ]] || ! grep -Fq "privileged containers are forbidden" <<<"$agent_privileged_output"; then
  echo "Agent command filtered Docker API did not reject a privileged container" >&2
  exit 1
fi
echo "AGENT_COMMAND_DOCKER_PROXY_PRIVILEGED_BLOCK_OK"

echo "==> Verifying the playbook worker has only the filtered Docker API"
compose exec -T playbook-execution-worker sh -lc \
  'test "$DOCKER_HOST" = "tcp://playbook-docker-proxy:2375" && test ! -S /var/run/docker.sock'
runner_image_id="$(docker image inspect --format '{{.Id}}' "${WEBTERM_ANSIBLE_IMAGE:-webterm-ansible:latest}")"
set +e
privileged_output="$(
  compose exec -T -e SMOKE_RUNNER_IMAGE_ID="$runner_image_id" playbook-execution-worker \
    sh -lc 'docker run --pull=never --rm --name webterm-pb-r999-d999-a1 --privileged "$SMOKE_RUNNER_IMAGE_ID" --version' 2>&1
)"
privileged_status=$?
set -e
printf '%s\n' "$privileged_output" | tee "$ARTIFACT_DIR/docker-proxy-privileged-denial.txt"
if [[ "$privileged_status" -eq 0 ]] || ! grep -Fq "privileged containers are forbidden" <<<"$privileged_output"; then
  echo "Filtered Docker API did not explicitly reject a privileged container" >&2
  exit 1
fi
echo "PLAYBOOK_DOCKER_PROXY_PRIVILEGED_BLOCK_OK"

echo "==> Verifying migration drift and the strict production profile"
compose exec -T backend python manage.py makemigrations --check --dry-run \
  | tee "$ARTIFACT_DIR/migration-drift.txt"
compose exec -T backend python manage.py check --deploy \
  | tee "$ARTIFACT_DIR/deploy-check.txt"

echo "==> Verifying the public health response over HTTPS"
curl --insecure --fail --silent --show-error "$BASE_URL/api/health/" \
  >"$ARTIFACT_DIR/health.json"
python3 - "$ARTIFACT_DIR/health.json" <<'PY'
import json
import sys
from pathlib import Path

payload = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
assert payload.get("status") in {"ok", "degraded"}, payload
assert payload.get("services", {}).get("django") == "ok", payload
PY

echo "==> Verifying authenticated readiness and fail-closed Plugins"
probe_authenticated_readiness
plugin_status="$(curl --insecure --silent --output /dev/null --write-out '%{http_code}' "$BASE_URL/api/plugins/installed/")"
printf 'plugin_route_status=%s\n' "$plugin_status" | tee "$ARTIFACT_DIR/plugin-fail-closed.txt"
if [[ "$plugin_status" != "404" ]]; then
  echo "Plugin API must be absent when the v0.1 release profile is disabled" >&2
  exit 1
fi

echo "==> Verifying scheduler and worker heartbeats"
capture_worker_heartbeats
compose exec -T backend python -m celery -A web_ui inspect ping --timeout 10 \
  | tee "$ARTIFACT_DIR/celery-ping.txt"
grep -qi "pong" "$ARTIFACT_DIR/celery-ping.txt"

echo "==> Starting the isolated SSH target"
smoke_compose up -d --build ssh-target
wait_for_service ssh-target 180
SMOKE_SSH_FINGERPRINT="$(
  smoke_compose exec -T ssh-target \
    ssh-keygen -lf //etc/ssh/ssh_host_ed25519_key.pub -E sha256 \
    | awk '{print $2}'
)"
if [[ ! "$SMOKE_SSH_FINGERPRINT" =~ ^SHA256: ]]; then
  echo "Unable to read the isolated SSH target fingerprint" >&2
  exit 1
fi

echo "==> Seeding and running HTTPS/WebSocket terminal, pipeline and agent smoke"
compose exec -T backend sh -lc \
  "python manage.py seed_multi_user_smoke --users 1 --password '$SMOKE_PASSWORD' --ssh-host ssh-target --ssh-port 2222 --ssh-username smoke --ssh-password smoke-password --ssh-host-key-fingerprint '$SMOKE_SSH_FINGERPRINT' --json > /tmp/f13a-seed.json"
timeout --signal=TERM --kill-after=15s 300s \
  docker compose \
  --project-name "$PROJECT_NAME" \
  --env-file "$ENV_FILE" \
  -f "$COMPOSE_FILE" \
  exec -T backend python docker/multi_user_load_smoke.py \
  --base-url https://nginx:8443 \
  --insecure-tls \
  --seed-file /tmp/f13a-seed.json \
  --users 1 \
  --terminal-sessions-per-user 1 \
  --pipeline-runs-per-user 1 \
  --agent-runs-per-user 1 \
  | tee "$ARTIFACT_DIR/runtime-smoke.json"

compose ps --format json >"$ARTIFACT_DIR/compose-ps.json"
compose images --format json >"$ARTIFACT_DIR/compose-images.json"
echo "F13A_PRODUCTION_INSTALL_SMOKE_OK"
