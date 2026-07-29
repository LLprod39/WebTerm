#!/usr/bin/env bash
set -euo pipefail

# One-command Linux server installer for WebTerm.
# It can be run from an existing checkout or with --repo to clone/update first.

DEFAULT_REPO_URL="https://github.com/LLprod39/WebTerm.git"
ORIGINAL_ARGS=("$@")
PROJECT_DIR=""
REPO_URL=""
BRANCH="test"
PROJECT_NAME="webtrerm-prod"
PUBLIC_HOST=""
PUBLIC_SCHEME="http"
PUBLIC_HTTP_PORT="80"
FRONTEND_PORT="8080"
PUBLIC_HTTPS_PORT="443"
ADMIN_USERNAME="admin"
ADMIN_EMAIL="admin@example.local"
ADMIN_PASSWORD=""
ADMIN_PROFILE="admin_full"
PULL_IMAGES=0
NO_BUILD=0
WITH_TELEGRAM_BOT=0
SKIP_DOCKER_INSTALL=0
SKIP_HEALTHCHECKS=0
SKIP_SMOKE=0
ONLY_PREPARE=0

print_help() {
  cat <<'EOF'
Usage:
  ./install-server.sh [options]

What it does (full platform install):
  1. installs Docker + Docker Compose plugin when missing
  2. clones or updates the project when --repo/--dir is used
  3. creates .env.production with generated secrets
  4. sets host/URL/security values for the server
  5. builds and starts the full Docker Compose production stack:
       postgres, redis, backend, frontend, nginx,
       mcp-demo,
       ops-supervisor (agent execution + watchers + memory),
       scheduled-agents, scheduled-pipelines, monitor,
       kubernetes-ops-sync, celery-worker
  6. runs migrations, pipeline templates, Django checks
  7. creates/updates platform admin (admin_full features incl. Kubernetes)
  8. smoke-checks /api/health/
  9. prints the URL, login, and useful maintenance commands

Common examples:
  chmod +x install-server.sh
  ./install-server.sh --host 10.0.0.15
  ./install-server.sh --host webterm.example.com --https
  ./install-server.sh --repo https://github.com/LLprod39/WebTerm.git --dir /opt/webtrerm --host webterm.example.com --https
  ./install-server.sh --host 10.0.0.15 --with-telegram-bot --pull

Options:
  --repo URL                 Git repo to clone/update when not running inside the repo
  --dir PATH                 Project directory (default: current repo or /opt/webtrerm)
  --branch NAME              Git branch for clone/update (default: test)
  --host HOST                Public DNS name or IP users will open
  --http                     Use plain HTTP app URLs (default; easiest first-server mode)
  --https                    Use HTTPS app URLs and secure cookies
  --http-port PORT           Public HTTP port mapped by nginx (default: 80)
  --frontend-port PORT       Extra public nginx HTTP port (default: 8080)
  --https-port PORT          Public HTTPS port mapped by nginx (default: 443)
  --admin-user USER          Admin username (default: admin)
  --admin-email EMAIL        Admin email (default: admin@example.local)
  --admin-password PASS      Admin password; generated if omitted
  --admin-profile NAME       Access profile for admin (default: admin_full)
  --project-name NAME        Docker Compose project name (default: webtrerm-prod)
  --pull                     Pull base images before start
  --no-build                 Start without rebuilding local images
  --with-telegram-bot        Also start telegram-bot service (needs TELEGRAM_BOT_TOKEN)
  --skip-docker-install      Do not install Docker; fail if Docker is missing
  --skip-healthchecks        Do not wait for Docker health checks
  --skip-smoke               Do not smoke-check HTTP health endpoints
  --only-prepare             Install Docker, prepare repo/env, but do not start containers
  -h, --help                 Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --repo) REPO_URL="${2:-}"; shift 2 ;;
    --dir) PROJECT_DIR="${2:-}"; shift 2 ;;
    --branch) BRANCH="${2:-}"; shift 2 ;;
    --host) PUBLIC_HOST="${2:-}"; shift 2 ;;
    --http) PUBLIC_SCHEME="http"; shift ;;
    --https) PUBLIC_SCHEME="https"; shift ;;
    --http-port) PUBLIC_HTTP_PORT="${2:-}"; shift 2 ;;
    --frontend-port) FRONTEND_PORT="${2:-}"; shift 2 ;;
    --https-port) PUBLIC_HTTPS_PORT="${2:-}"; shift 2 ;;
    --admin-user) ADMIN_USERNAME="${2:-}"; shift 2 ;;
    --admin-email) ADMIN_EMAIL="${2:-}"; shift 2 ;;
    --admin-password) ADMIN_PASSWORD="${2:-}"; shift 2 ;;
    --admin-profile) ADMIN_PROFILE="${2:-admin_full}"; shift 2 ;;
    --project-name) PROJECT_NAME="${2:-}"; shift 2 ;;
    --pull) PULL_IMAGES=1; shift ;;
    --no-build) NO_BUILD=1; shift ;;
    --with-telegram-bot) WITH_TELEGRAM_BOT=1; shift ;;
    --skip-docker-install) SKIP_DOCKER_INSTALL=1; shift ;;
    --skip-healthchecks) SKIP_HEALTHCHECKS=1; shift ;;
    --skip-smoke) SKIP_SMOKE=1; shift ;;
    --only-prepare) ONLY_PREPARE=1; shift ;;
    -h|--help) print_help; exit 0 ;;
    *) echo "Unknown argument: $1" >&2; print_help >&2; exit 1 ;;
  esac
done

log() {
  printf '\n==> %s\n' "$*"
}

ok() {
  printf '[ok] %s\n' "$*"
}

fail() {
  echo "Error: $*" >&2
  exit 1
}

have_cmd() {
  command -v "$1" >/dev/null 2>&1
}

sudo_cmd() {
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    "$@"
  else
    sudo "$@"
  fi
}

maybe_reexec_with_sudo() {
  if [[ "${WEBTRERM_INSTALLER_NO_SUDO_REEXEC:-}" == "1" || "${EUID:-$(id -u)}" -eq 0 ]]; then
    return 0
  fi
  if command -v docker >/dev/null 2>&1 && docker info >/dev/null 2>&1; then
    return 0
  fi
  if command -v sudo >/dev/null 2>&1; then
    export WEBTRERM_INSTALLER_NO_SUDO_REEXEC=1
    exec sudo -E bash "$0" "${ORIGINAL_ARGS[@]}"
  fi
}

require_cmd() {
  have_cmd "$1" || fail "required command not found: $1"
}

random_string() {
  local length="$1"
  if have_cmd openssl; then
    openssl rand -base64 "$length" | tr -d '\n=+/' | cut -c "1-$length"
    printf '\n'
    return 0
  fi
  LC_ALL=C tr -dc 'A-Za-z0-9' </dev/urandom | head -c "$length"
  printf '\n'
}

detect_public_host() {
  if [[ -n "$PUBLIC_HOST" ]]; then
    return 0
  fi
  if have_cmd hostname; then
    PUBLIC_HOST="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
  fi
  if [[ -z "$PUBLIC_HOST" ]] && have_cmd ip; then
    PUBLIC_HOST="$(ip -4 route get 1.1.1.1 2>/dev/null | awk '{for (i=1;i<=NF;i++) if ($i=="src") {print $(i+1); exit}}' || true)"
  fi
  if [[ -z "$PUBLIC_HOST" ]]; then
    PUBLIC_HOST="localhost"
  fi
}

install_base_packages() {
  if have_cmd apt-get; then
    sudo_cmd apt-get update
    sudo_cmd apt-get install -y ca-certificates curl gnupg git openssl lsb-release python3
    return 0
  fi
  if have_cmd dnf; then
    sudo_cmd dnf install -y ca-certificates curl git openssl python3
    return 0
  fi
  if have_cmd yum; then
    sudo_cmd yum install -y ca-certificates curl git openssl python3
    return 0
  fi
  if have_cmd apk; then
    sudo_cmd apk add --no-cache ca-certificates curl git openssl python3
    return 0
  fi
  fail "unsupported Linux package manager; install curl git openssl python3 docker manually and rerun with --skip-docker-install"
}

ensure_runtime_tools() {
  # python3 is required by docker/install-production.sh env helpers
  if ! have_cmd python3; then
    log "Installing python3 (required by production installer)"
    install_base_packages
  fi
  require_cmd python3
  if ! have_cmd curl; then
    log "Installing curl (required for health smoke checks)"
    install_base_packages
  fi
  require_cmd curl
  if ! have_cmd openssl; then
    log "Installing openssl (required for nginx self-signed certs)"
    install_base_packages
  fi
  require_cmd openssl
}

ensure_docker_permissions() {
  if docker info >/dev/null 2>&1; then
    return 0
  fi
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    return 0
  fi
  if have_cmd usermod && getent group docker >/dev/null 2>&1; then
    log "Adding current user to docker group"
    sudo_cmd usermod -aG docker "$(id -un)" || true
    echo "[warn] You may need to re-login for docker group membership, or rerun with sudo."
  fi
  # Retry once via sudo docker if plain docker still fails
  if ! docker info >/dev/null 2>&1; then
    if have_cmd sudo && sudo docker info >/dev/null 2>&1; then
      ok "Docker is available via sudo"
      return 0
    fi
    fail "Docker is installed but not usable by this user. Re-login after group change or run installer with sudo."
  fi
}

install_docker_debian() {
  . /etc/os-release
  local docker_id="${ID}"
  if [[ "$docker_id" == "linuxmint" || "$docker_id" == "pop" ]]; then
    docker_id="ubuntu"
  fi
  local codename="${VERSION_CODENAME:-}"
  if [[ -z "$codename" ]] && have_cmd lsb_release; then
    codename="$(lsb_release -cs)"
  fi
  [[ -n "$codename" ]] || fail "could not detect Debian/Ubuntu codename for Docker repo"

  sudo_cmd install -m 0755 -d /etc/apt/keyrings
  curl -fsSL "https://download.docker.com/linux/${docker_id}/gpg" | sudo_cmd gpg --dearmor -o /etc/apt/keyrings/docker.gpg
  sudo_cmd chmod a+r /etc/apt/keyrings/docker.gpg

  local arch
  arch="$(dpkg --print-architecture)"
  echo "deb [arch=${arch} signed-by=/etc/apt/keyrings/docker.gpg] https://download.docker.com/linux/${docker_id} ${codename} stable" \
    | sudo_cmd tee /etc/apt/sources.list.d/docker.list >/dev/null
  sudo_cmd apt-get update
  sudo_cmd apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

install_docker_rhel() {
  if have_cmd dnf; then
    sudo_cmd dnf install -y dnf-plugins-core
    sudo_cmd dnf config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
    sudo_cmd dnf install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
    return 0
  fi
  sudo_cmd yum install -y yum-utils
  sudo_cmd yum-config-manager --add-repo https://download.docker.com/linux/centos/docker-ce.repo
  sudo_cmd yum install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
}

ensure_docker() {
  if have_cmd docker && docker compose version >/dev/null 2>&1; then
    ok "Docker and Docker Compose are already installed"
    return 0
  fi

  [[ "$SKIP_DOCKER_INSTALL" -eq 0 ]] || fail "Docker Compose v2 is missing and --skip-docker-install was used"

  log "Installing base packages"
  install_base_packages

  log "Installing Docker Engine and Compose plugin"
  if have_cmd apt-get; then
    install_docker_debian
  elif have_cmd dnf || have_cmd yum; then
    install_docker_rhel
  elif have_cmd apk; then
    sudo_cmd apk add --no-cache docker docker-cli-compose
  else
    fail "unsupported Linux distribution for automatic Docker install"
  fi

  if have_cmd systemctl; then
    sudo_cmd systemctl enable --now docker
  else
    sudo_cmd service docker start || true
  fi

  require_cmd docker
  docker compose version >/dev/null 2>&1 || fail "docker compose v2 plugin is still unavailable after installation"
  ok "Docker installed"
}

prepare_project_dir() {
  local cwd
  cwd="$(pwd)"

  if [[ -z "$PROJECT_DIR" && -f "$cwd/docker-compose.production.yml" ]]; then
    PROJECT_DIR="$cwd"
  fi
  if [[ -z "$PROJECT_DIR" ]]; then
    PROJECT_DIR="/opt/webtrerm"
  fi
  if [[ -z "$REPO_URL" ]]; then
    REPO_URL="$DEFAULT_REPO_URL"
  fi

  if [[ -f "$PROJECT_DIR/docker-compose.production.yml" ]]; then
    ok "Using project directory: $PROJECT_DIR"
    if [[ -d "$PROJECT_DIR/.git" ]]; then
      log "Updating existing git checkout"
      git -C "$PROJECT_DIR" fetch --all --prune
      git -C "$PROJECT_DIR" checkout "$BRANCH"
      git -C "$PROJECT_DIR" pull --ff-only || echo "[warn] git pull failed; continuing with current checkout"
    fi
    return 0
  fi

  require_cmd git
  log "Cloning project"
  sudo_cmd mkdir -p "$(dirname "$PROJECT_DIR")"
  if [[ "${EUID:-$(id -u)}" -eq 0 ]]; then
    git clone --branch "$BRANCH" "$REPO_URL" "$PROJECT_DIR"
  else
    sudo_cmd git clone --branch "$BRANCH" "$REPO_URL" "$PROJECT_DIR"
    sudo_cmd chown -R "$(id -u):$(id -g)" "$PROJECT_DIR" 2>/dev/null || true
  fi
}

env_get() {
  local key="$1"
  awk -F= -v k="$key" '
    /^[[:space:]]*#/ {next}
    NF >= 2 {
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", $1)
      if ($1 == k) {
        sub(/^[^=]*=/, "", $0)
        print $0
        exit
      }
    }
  ' "$PROJECT_DIR/.env.production" 2>/dev/null || true
}

env_set() {
  local key="$1"
  local value="$2"
  local env_file="$PROJECT_DIR/.env.production"
  local tmp_file="${env_file}.tmp.$$"
  awk -v target_key="$key" -v target_value="$value" '
    BEGIN { updated = 0 }
    {
      line = $0
      if (line ~ /^[[:space:]]*#/ || index(line, "=") == 0) {
        print line
        next
      }
      current_key = line
      sub(/=.*/, "", current_key)
      gsub(/^[[:space:]]+|[[:space:]]+$/, "", current_key)
      if (current_key == target_key) {
        print target_key "=" target_value
        updated = 1
      } else {
        print line
      }
    }
    END {
      if (!updated) {
        print target_key "=" target_value
      }
    }
  ' "$env_file" >"$tmp_file"
  mv "$tmp_file" "$env_file"
}

prepare_env() {
  local env_file="$PROJECT_DIR/.env.production"
  umask 077
  [[ ! -L "$env_file" ]] || fail "refusing symbolic-link env file: $env_file"
  if [[ ! -f "$env_file" ]]; then
    cp "$PROJECT_DIR/.env.production.example" "$env_file"
    ok "Created $env_file"
  fi
  chmod 600 "$env_file"

  detect_public_host
  local public_url="${PUBLIC_SCHEME}://${PUBLIC_HOST}"
  if [[ "$PUBLIC_SCHEME" == "http" && "$PUBLIC_HTTP_PORT" != "80" ]]; then
    public_url="${PUBLIC_SCHEME}://${PUBLIC_HOST}:${PUBLIC_HTTP_PORT}"
  fi
  if [[ "$PUBLIC_SCHEME" == "https" && "$PUBLIC_HTTPS_PORT" != "443" ]]; then
    public_url="${PUBLIC_SCHEME}://${PUBLIC_HOST}:${PUBLIC_HTTPS_PORT}"
  fi

  env_set PUBLIC_BIND_HOST "0.0.0.0"
  env_set PUBLIC_HTTP_PORT "$PUBLIC_HTTP_PORT"
  env_set FRONTEND_PORT "$FRONTEND_PORT"
  env_set PUBLIC_HTTPS_PORT "$PUBLIC_HTTPS_PORT"
  env_set SITE_URL "$public_url"
  env_set FRONTEND_APP_URL "$public_url"
  env_set ALLOWED_HOSTS "${PUBLIC_HOST},localhost,127.0.0.1"
  env_set CSRF_TRUSTED_ORIGINS "${public_url},http://localhost:${FRONTEND_PORT},http://127.0.0.1:${FRONTEND_PORT}"

  if [[ "$PUBLIC_SCHEME" == "https" ]]; then
    env_set SECURE_SSL_REDIRECT "true"
    env_set SESSION_COOKIE_SECURE "true"
    env_set CSRF_COOKIE_SECURE "true"
    env_set SECURE_HSTS_SECONDS "31536000"
    env_set SECURE_HSTS_INCLUDE_SUBDOMAINS "true"
  else
    env_set SECURE_SSL_REDIRECT "false"
    env_set SESSION_COOKIE_SECURE "false"
    env_set CSRF_COOKIE_SECURE "false"
    env_set SECURE_HSTS_SECONDS "0"
    env_set SECURE_HSTS_INCLUDE_SUBDOMAINS "false"
    env_set SECURE_HSTS_PRELOAD "false"
  fi

  if [[ -z "$(env_get DJANGO_SECRET_KEY)" || "$(env_get DJANGO_SECRET_KEY)" == replace-* ]]; then
    env_set DJANGO_SECRET_KEY "$(random_string 64)"
  fi
  if [[ -z "$(env_get MANAGED_SECRET_KEY)" || "$(env_get MANAGED_SECRET_KEY)" == replace-* ]]; then
    env_set MANAGED_SECRET_KEY "$(random_string 64)"
  fi
  if [[ -z "$(env_get MASTER_PASSWORD)" || "$(env_get MASTER_PASSWORD)" == change-* ]]; then
    env_set MASTER_PASSWORD "$(random_string 48)"
  fi
  if [[ -z "$(env_get POSTGRES_PASSWORD)" || "$(env_get POSTGRES_PASSWORD)" == change-* ]]; then
    env_set POSTGRES_PASSWORD "$(random_string 32)"
  fi

  # Worker / runtime defaults so first boot is complete without hand-editing env.
  [[ -n "$(env_get POSTGRES_DB)" ]] || env_set POSTGRES_DB "weu_platform"
  [[ -n "$(env_get POSTGRES_USER)" ]] || env_set POSTGRES_USER "weu"
  [[ -n "$(env_get WEU_BUILD)" ]] || env_set WEU_BUILD "prod"
  [[ -n "$(env_get DJANGO_DEBUG)" ]] || env_set DJANGO_DEBUG "false"
  [[ -n "$(env_get CHANNEL_REDIS_URL)" ]] || env_set CHANNEL_REDIS_URL "redis://redis:6379/1"
  [[ -n "$(env_get CELERY_BROKER_URL)" ]] || env_set CELERY_BROKER_URL "redis://redis:6379/0"
  [[ -n "$(env_get CELERY_RESULT_BACKEND)" ]] || env_set CELERY_RESULT_BACKEND "redis://redis:6379/0"
  [[ -n "$(env_get STUDIO_MCP_DEMO_URL)" ]] || env_set STUDIO_MCP_DEMO_URL "http://mcp-demo:8765/mcp"
  [[ -n "$(env_get AGENT_EXECUTION_INTERVAL)" ]] || env_set AGENT_EXECUTION_INTERVAL "5"
  [[ -n "$(env_get SCHEDULED_AGENTS_INTERVAL)" ]] || env_set SCHEDULED_AGENTS_INTERVAL "60"
  [[ -n "$(env_get PIPELINE_SCHEDULER_INTERVAL)" ]] || env_set PIPELINE_SCHEDULER_INTERVAL "60"
  [[ -n "$(env_get CELERY_WORKER_CONCURRENCY)" ]] || env_set CELERY_WORKER_CONCURRENCY "2"
  [[ -n "$(env_get TRUST_X_FORWARDED_PROTO)" ]] || env_set TRUST_X_FORWARDED_PROTO "true"
  [[ -n "$(env_get USE_X_FORWARDED_HOST)" ]] || env_set USE_X_FORWARDED_HOST "true"

  ok "Prepared production env for $public_url"
}

ensure_admin_password() {
  if [[ -z "$ADMIN_PASSWORD" ]]; then
    ADMIN_PASSWORD="$(random_string 24)"
  fi
}

run_stack_installer() {
  local installer="$PROJECT_DIR/docker/install-production.sh"
  [[ -f "$installer" ]] || fail "missing internal installer: $installer"
  chmod +x "$installer"

  local args=(
    --env-file "$PROJECT_DIR/.env.production"
    --compose-file "$PROJECT_DIR/docker-compose.production.yml"
    --project-name "$PROJECT_NAME"
    --generate-secrets
    --create-superuser
    --superuser-username "$ADMIN_USERNAME"
    --superuser-email "$ADMIN_EMAIL"
    --superuser-password "$ADMIN_PASSWORD"
    --admin-profile "$ADMIN_PROFILE"
  )
  [[ "$PULL_IMAGES" -eq 1 ]] && args+=(--pull)
  [[ "$NO_BUILD" -eq 1 ]] && args+=(--no-build)
  [[ "$WITH_TELEGRAM_BOT" -eq 1 ]] && args+=(--with-telegram-bot)
  [[ "$SKIP_HEALTHCHECKS" -eq 1 ]] && args+=(--skip-healthchecks)
  [[ "$SKIP_SMOKE" -eq 1 ]] && args+=(--skip-smoke)

  (cd "$PROJECT_DIR" && "$installer" "${args[@]}")
}

print_summary() {
  local site_url
  site_url="$(env_get SITE_URL)"
  cat <<EOF

WebTerm platform is installed and running.

URL:
  ${site_url}
  http://${PUBLIC_HOST}:${FRONTEND_PORT}
  Health: http://${PUBLIC_HOST}:${FRONTEND_PORT}/api/health/

Admin login:
  username: ${ADMIN_USERNAME}
  password: ${ADMIN_PASSWORD}
  profile:  ${ADMIN_PROFILE}

Project:
  ${PROJECT_DIR}

What is running:
  core     postgres redis backend frontend nginx
  mcp      mcp-demo
  workers  ops-supervisor scheduled-agents scheduled-pipelines
           monitor kubernetes-ops-sync celery-worker

Useful commands:
  cd ${PROJECT_DIR}
  docker compose --project-name ${PROJECT_NAME} --env-file .env.production -f docker-compose.production.yml ps
  docker compose --project-name ${PROJECT_NAME} --env-file .env.production -f docker-compose.production.yml logs -f backend ops-supervisor nginx
  docker compose --project-name ${PROJECT_NAME} --env-file .env.production -f docker-compose.production.yml restart ops-supervisor scheduled-agents celery-worker
  docker compose --project-name ${PROJECT_NAME} --env-file .env.production -f docker-compose.production.yml down
  docker compose --project-name ${PROJECT_NAME} --env-file .env.production -f docker-compose.production.yml up -d --build

After login:
  1. Settings → AI — add an LLM API key (Grok / OpenAI / etc.)
  2. Servers — add a host and open Terminal
  3. Agents — create Mini agent and Run (works without extra setup)
  4. Full/multi agents are served by ops-supervisor already running in Docker

Important:
  Save this admin password now. It is printed only by this installer run.
EOF
}

main() {
  [[ "$(uname -s)" == "Linux" ]] || fail "this installer is for Linux servers; use Docker Compose manually on other OS"
  maybe_reexec_with_sudo

  log "Preparing server"
  ensure_docker
  ensure_docker_permissions
  ensure_runtime_tools

  log "Preparing project"
  prepare_project_dir
  [[ -f "$PROJECT_DIR/docker-compose.production.yml" ]] || fail "project is missing docker-compose.production.yml"
  [[ -f "$PROJECT_DIR/.env.production.example" ]] || fail "project is missing .env.production.example"
  [[ -f "$PROJECT_DIR/docker/install-production.sh" ]] || fail "project is missing docker/install-production.sh"

  log "Preparing environment"
  prepare_env
  ensure_admin_password

  if [[ "$ONLY_PREPARE" -eq 1 ]]; then
    ok "Prepared project and env only; containers were not started"
    cat <<EOF

Project is prepared but not started.

Project:
  ${PROJECT_DIR}

Next command:
  cd ${PROJECT_DIR}
  ./docker/install-production.sh --env-file .env.production --compose-file docker-compose.production.yml --project-name ${PROJECT_NAME} --generate-secrets --create-superuser --superuser-username ${ADMIN_USERNAME} --superuser-email ${ADMIN_EMAIL} --superuser-password '<choose-password>' --admin-profile ${ADMIN_PROFILE}
EOF
    exit 0
  fi

  log "Starting WebTerm Docker stack (full platform)"
  run_stack_installer
  print_summary
}

main "$@"
