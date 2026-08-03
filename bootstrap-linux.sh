#!/usr/bin/env bash
set -euo pipefail

# bootstrap-linux.sh
# One-command setup for Linux hosts:
# - create local config files from templates
# - start Docker services (Postgres + MCP demo)
# - create an OS-specific Python venv and install the locked dev environment
# - run Django migrations
# - optionally install frontend dependencies

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

USE_FULL_REQUIREMENTS=0
SKIP_FRONTEND=0
NO_DOCKER=0
FORCE_CONFIG=0
COMPOSE_FILE="docker-compose.yml"
PYTHON_BIN_OVERRIDE=""
VENV_DIR="${WEBTERM_VENV_DIR:-.venv-wsl}"

print_help() {
  cat <<'EOF'
Usage: ./bootstrap-linux.sh [options]

Options:
  --full               Compatibility flag; current full profile equals the locked mini runtime
  --skip-frontend      Skip npm install in frontend
  --no-docker          Do not run docker compose
  --compose-file FILE  Compose file to use (default: docker-compose.yml)
  --python-bin BIN     Python interpreter to use (must be 3.11 or 3.12)
  --force-config       Overwrite existing .env/.notification_config.json from templates
  -h, --help           Show this help

Examples:
  ./bootstrap-linux.sh
  ./bootstrap-linux.sh --full
  ./bootstrap-linux.sh --compose-file docker-compose.postgres-mcp.yml
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --full)
      USE_FULL_REQUIREMENTS=1
      shift
      ;;
    --skip-frontend)
      SKIP_FRONTEND=1
      shift
      ;;
    --no-docker)
      NO_DOCKER=1
      shift
      ;;
    --compose-file)
      COMPOSE_FILE="${2:-}"
      if [[ -z "$COMPOSE_FILE" ]]; then
        echo "Error: --compose-file requires a value" >&2
        exit 1
      fi
      shift 2
      ;;
    --python-bin)
      PYTHON_BIN_OVERRIDE="${2:-}"
      if [[ -z "$PYTHON_BIN_OVERRIDE" ]]; then
        echo "Error: --python-bin requires a value" >&2
        exit 1
      fi
      shift 2
      ;;
    --force-config)
      FORCE_CONFIG=1
      shift
      ;;
    -h|--help)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      print_help
      exit 1
      ;;
  esac
done

require_cmd() {
  local cmd="$1"
  if ! command -v "$cmd" >/dev/null 2>&1; then
    echo "Error: command not found: $cmd" >&2
    exit 1
  fi
}

python_version_ok() {
  local py_bin="$1"
  "$py_bin" - <<'PY' >/dev/null 2>&1
import sys
sys.exit(0 if (3, 11) <= sys.version_info[:2] < (3, 13) else 1)
PY
}

python_version_text() {
  local py_bin="$1"
  "$py_bin" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")
PY
}

select_python_bin() {
  if [[ -n "$PYTHON_BIN_OVERRIDE" ]]; then
    if ! command -v "$PYTHON_BIN_OVERRIDE" >/dev/null 2>&1; then
      echo "Error: --python-bin not found: $PYTHON_BIN_OVERRIDE" >&2
      exit 1
    fi
    if ! python_version_ok "$PYTHON_BIN_OVERRIDE"; then
      echo "Error: $PYTHON_BIN_OVERRIDE is $(python_version_text "$PYTHON_BIN_OVERRIDE"), but Python 3.11 or 3.12 is required." >&2
      exit 1
    fi
    echo "$PYTHON_BIN_OVERRIDE"
    return 0
  fi

  local candidates=(python3.11 python3.12 python3 python)
  local candidate
  for candidate in "${candidates[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1 && python_version_ok "$candidate"; then
      echo "$candidate"
      return 0
    fi
  done

  echo "Error: Python 3.11/3.12 not found." >&2
  echo "Install Python 3.11 and rerun, or pass --python-bin /path/to/python3.11" >&2
  echo "Example (Ubuntu): sudo apt-get update && sudo apt-get install -y python3.11 python3.11-venv" >&2
  exit 1
}

copy_template_if_needed() {
  local template_path="$1"
  local target_path="$2"

  if [[ ! -f "$template_path" ]]; then
    echo "[skip] template not found: $template_path"
    return
  fi

  if [[ -f "$target_path" && "$FORCE_CONFIG" -ne 1 ]]; then
    echo "[skip] exists: $target_path (use --force-config to overwrite)"
    return
  fi

  cp "$template_path" "$target_path"
  echo "[ok] created: $target_path"
}

wait_for_container_health() {
  local container="$1"
  local timeout_seconds="${2:-120}"
  local elapsed=0

  while true; do
    if ! docker inspect "$container" >/dev/null 2>&1; then
      echo "[wait] container not found yet: $container"
    else
      local status
      status="$(docker inspect --format '{{if .State.Health}}{{.State.Health.Status}}{{else}}{{.State.Status}}{{end}}' "$container" 2>/dev/null || true)"
      if [[ "$status" == "healthy" || "$status" == "running" ]]; then
        echo "[ok] container ready: $container ($status)"
        return 0
      fi
      echo "[wait] $container status: ${status:-unknown}"
    fi

    sleep 2
    elapsed=$((elapsed + 2))
    if (( elapsed >= timeout_seconds )); then
      echo "Error: timeout waiting for container: $container" >&2
      return 1
    fi
  done
}

echo "==> Preparing configuration files"
copy_template_if_needed ".env.example" ".env"
copy_template_if_needed ".notification_config.example.json" ".notification_config.json"

echo "==> Preparing Python environment"
PYTHON_BIN="$(select_python_bin)"
echo "[ok] using Python: $PYTHON_BIN ($(python_version_text "$PYTHON_BIN"))"

"$PYTHON_BIN" -m venv --clear "$VENV_DIR"
VENV_PYTHON="$ROOT_DIR/$VENV_DIR/bin/python"

"$VENV_PYTHON" -m pip install --require-hashes -r requirements-dev.lock
echo "[ok] installed requirements-dev.lock into $VENV_DIR"
if [[ "$USE_FULL_REQUIREMENTS" -eq 1 ]]; then
  echo "[note] --full currently adds no packages; requirements-full.txt equals the mini runtime."
fi

if [[ "$NO_DOCKER" -eq 0 ]]; then
  echo "==> Starting Docker services from $COMPOSE_FILE"
  require_cmd docker
  if ! docker compose version >/dev/null 2>&1; then
    echo "Error: docker compose plugin is not available." >&2
    echo "Install Docker Compose v2 (docker compose) and rerun." >&2
    exit 1
  fi
  docker compose -f "$COMPOSE_FILE" up -d --build postgres mcp-demo

  wait_for_container_health "mini-prod-postgres" 180
  wait_for_container_health "mini-prod-mcp-demo" 180
fi

echo "==> Running Django migrations"
"$VENV_PYTHON" manage.py migrate
"$VENV_PYTHON" manage.py migrate_ssh_private_keys --apply

if [[ "$SKIP_FRONTEND" -eq 0 ]]; then
  echo "==> Installing frontend dependencies"
  require_cmd npm
  (cd frontend && npm ci)
fi

cat <<EOF

[done] Bootstrap complete.

Next steps:
  1) Fill real secrets in .env and .notification_config.json
  2) Start backend:
       source "$VENV_DIR/bin/activate"
       python manage.py runserver
  3) Start frontend (in another shell):
       cd frontend
       npm run dev

Notes:
  - Do NOT commit .env or .notification_config.json with real secrets.
  - Release evidence requires the pinned runtime from this script.
EOF
