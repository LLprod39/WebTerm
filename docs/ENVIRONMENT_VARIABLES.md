# Production environment variables

Generated from `.env.production.example` by `scripts/env_contract.py`. Do not edit this table by hand.

Total variables: **374**.

## Required

| Variable | Purpose | Default |
|---|---|---|
| `PUBLIC_BIND_HOST` | Public URLs and ports | `0.0.0.0` |
| `PUBLIC_HTTP_PORT` | Public URLs and ports | `80` |
| `PUBLIC_HTTPS_PORT` | Public URLs and ports | `443` |
| `FRONTEND_BIND_HOST` | Public URLs and ports | `127.0.0.1` |
| `FRONTEND_PORT` | Public URLs and ports | `8080` |
| `DJANGO_BIND_HOST` | Public URLs and ports | `127.0.0.1` |
| `DJANGO_HOST_PORT` | Public URLs and ports | `9000` |
| `POSTGRES_BIND_HOST` | Public URLs and ports | `127.0.0.1` |
| `POSTGRES_HOST_PORT` | Public URLs and ports | `5432` |
| `REDIS_BIND_HOST` | Public URLs and ports | `127.0.0.1` |
| `REDIS_HOST_PORT` | Public URLs and ports | `6379` |
| `TZ` | Public URLs and ports | `Asia/Qyzylorda` |
| `SITE_URL` | Public URLs and ports | `https://webterm.example.com` |
| `FRONTEND_APP_URL` | Public URLs and ports | `https://webterm.example.com` |
| `ALLOWED_HOSTS` | Public URLs and ports | `webterm.example.com` |
| `CSRF_TRUSTED_ORIGINS` | Public URLs and ports | `https://webterm.example.com` |
| `WEU_BUILD` | Django / app mode | `prod` |
| `DJANGO_DEBUG` | Django / app mode | `false` |
| `DJANGO_SECRET_KEY` | Django / app mode | `placeholder; replace` |
| `MANAGED_SECRET_KEY` | Django / app mode | `placeholder; replace` |
| `MANAGED_SECRET_KEY_ID` | Optional stable label. If blank, a non-secret id is derived from MANAGED_SECRET_KEY. | `operator supplied` |
| `MANAGED_SECRET_PREVIOUS_KEYS` | JSON object of old key ids to old keys, used only during zero-downtime rotation. | `placeholder; replace` |
| `MODEL_CONFIG_PATH` | JSON object of old key ids to old keys, used only during zero-downtime rotation. | `/workspace/config_runtime/model_config.json` |
| `NOTIFICATION_CONFIG_PATH` | JSON object of old key ids to old keys, used only during zero-downtime rotation. | `/workspace/config_runtime/notification_config.json` |
| `CHANNEL_REDIS_URL` | JSON object of old key ids to old keys, used only during zero-downtime rotation. | `redis://redis:6379/1` |
| `CELERY_BROKER_URL` | JSON object of old key ids to old keys, used only during zero-downtime rotation. | `redis://redis:6379/0` |
| `CELERY_RESULT_BACKEND` | JSON object of old key ids to old keys, used only during zero-downtime rotation. | `redis://redis:6379/0` |
| `DOCKER_SOCKET_GID` | receives this group; the playbook worker never mounts the host socket. | `empty` |
| `WEBTERM_PLAYBOOK_DOCKER_PROXY_IMAGE` | receives this group; the playbook worker never mounts the host socket. | `webterm-playbook-docker-proxy:latest` |
| `WEBTERM_AGENT_COMMAND_DOCKER_PROXY_IMAGE` | receives this group; the playbook worker never mounts the host socket. | `webterm-agent-command-docker-proxy:latest` |
| `WEBTERM_BACKEND_MEMORY` | receives this group; the playbook worker never mounts the host socket. | `1g` |
| `WEBTERM_BACKEND_CPUS` | receives this group; the playbook worker never mounts the host socket. | `2.0` |
| `WEBTERM_BACKEND_PIDS_LIMIT` | receives this group; the playbook worker never mounts the host socket. | `512` |
| `WEBTERM_BACKEND_WORKER_MEMORY` | receives this group; the playbook worker never mounts the host socket. | `768m` |
| `WEBTERM_BACKEND_WORKER_CPUS` | receives this group; the playbook worker never mounts the host socket. | `1.0` |
| `WEBTERM_BACKEND_WORKER_PIDS_LIMIT` | receives this group; the playbook worker never mounts the host socket. | `256` |
| `PLUGIN_MARKETPLACE_RELEASE_MODE` | is provisioned. "disabled" removes backend routes/providers and frontend UI. | `disabled` |
| `POSTGRES_HOST` | PostgreSQL | `postgres` |
| `POSTGRES_PORT` | PostgreSQL | `5432` |
| `POSTGRES_DB` | PostgreSQL | `weu_platform` |
| `POSTGRES_USER` | PostgreSQL | `weu` |
| `POSTGRES_PASSWORD` | PostgreSQL | `placeholder; replace` |
| `POSTGRES_CONN_MAX_AGE_SECONDS` | PostgreSQL | `60` |
| `SECURE_SSL_REDIRECT` | Security / cookies / headers | `true` |
| `TRUST_X_FORWARDED_PROTO` | Security / cookies / headers | `true` |
| `TRUSTED_PROXY_HOPS` | nginx is the single trusted hop in the bundled production topology. | `1` |
| `AUTH_LOGIN_FAILURE_LIMIT` | nginx is the single trusted hop in the bundled production topology. | `10` |
| `AUTH_LOGIN_FAILURE_WINDOW_SECONDS` | nginx is the single trusted hop in the bundled production topology. | `900` |
| `AUTH_LOGIN_USERNAME_SOFT_LIMIT` | nginx is the single trusted hop in the bundled production topology. | `50` |
| `AUTH_LOGIN_USERNAME_WINDOW_SECONDS` | nginx is the single trusted hop in the bundled production topology. | `3600` |
| `AUTH_LOGIN_USERNAME_BASE_DELAY_MS` | nginx is the single trusted hop in the bundled production topology. | `125` |
| `AUTH_LOGIN_USERNAME_MAX_DELAY_MS` | nginx is the single trusted hop in the bundled production topology. | `2000` |
| `USE_X_FORWARDED_HOST` | nginx is the single trusted hop in the bundled production topology. | `true` |
| `SESSION_COOKIE_SECURE` | nginx is the single trusted hop in the bundled production topology. | `true` |
| `CSRF_COOKIE_SECURE` | nginx is the single trusted hop in the bundled production topology. | `true` |
| `SECURE_HSTS_SECONDS` | nginx is the single trusted hop in the bundled production topology. | `31536000` |
| `SECURE_HSTS_INCLUDE_SUBDOMAINS` | nginx is the single trusted hop in the bundled production topology. | `true` |
| `SECURE_HSTS_PRELOAD` | nginx is the single trusted hop in the bundled production topology. | `true` |

## Frequently changed

| Variable | Purpose | Default |
|---|---|---|
| `APP_LOG_FILE` | Logging | `/workspace/logs/webtrerm.log` |
| `APP_LOG_LEVEL` | Logging | `INFO` |
| `APP_LOG_ROTATION` | Logging | `50 MB` |
| `APP_LOG_RETENTION` | Logging | `14 days` |
| `APP_LOG_SYSLOG_ENABLED` | Logging | `false` |
| `APP_LOG_SYSLOG_ADDRESS` | Logging | `localhost:514` |
| `APP_LOG_SYSLOG_PROTOCOL` | Logging | `udp` |
| `APP_LOG_SYSLOG_FACILITY` | Logging | `LOG_USER` |
| `GEMINI_API_KEY` | LLM providers | `operator supplied` |
| `OPENAI_API_KEY` | LLM providers | `operator supplied` |
| `CODEX_API_KEY` | LLM providers | `operator supplied` |
| `ANTHROPIC_API_KEY` | LLM providers | `operator supplied` |
| `GROK_API_KEY` | LLM providers | `operator supplied` |
| `WEB_SEARCH_API_KEY` | Optional Operator public web research (Brave Search API) | `operator supplied` |
| `LLM_GROK_STREAM_TIMEOUT_SECONDS` | Optional Operator public web research (Brave Search API) | `3600` |
| `LLM_GROK_REASONING_EFFORT` | Optional Operator public web research (Brave Search API) | `none` |
| `OLLAMA_BASE_URL` | Optional Operator public web research (Brave Search API) | `empty` |
| `OLLAMA_API_KEY` | Optional Operator public web research (Brave Search API) | `operator supplied` |
| `OLLAMA_CLOUD_BASE_URL` | Optional Operator public web research (Brave Search API) | `https://ollama.com` |
| `CURSOR_API_KEY` | Cursor / CLI runtime | `operator supplied` |
| `CURSOR_CLI_HTTP_1` | Cursor / CLI runtime | `1` |
| `CURSOR_CLI_EXTRA_ENV` | Cursor / CLI runtime | `empty` |
| `CLI_RUNTIME_TIMEOUT_SECONDS` | Cursor / CLI runtime | `600` |
| `CLI_FIRST_OUTPUT_TIMEOUT_SECONDS` | Cursor / CLI runtime | `120` |
| `EMAIL_BACKEND` | Email / Telegram notifications | `django.core.mail.backends.smtp.EmailBackend` |
| `EMAIL_HOST` | Email / Telegram notifications | `empty` |
| `EMAIL_PORT` | Email / Telegram notifications | `587` |
| `EMAIL_USE_TLS` | Email / Telegram notifications | `true` |
| `EMAIL_HOST_USER` | Email / Telegram notifications | `empty` |
| `EMAIL_HOST_PASSWORD` | Email / Telegram notifications | `operator supplied` |
| `DEFAULT_FROM_EMAIL` | Email / Telegram notifications | `empty` |
| `PIPELINE_NOTIFY_EMAIL` | Email / Telegram notifications | `empty` |
| `TELEGRAM_BOT_TOKEN` | Email / Telegram notifications | `operator supplied` |
| `TELEGRAM_CHAT_ID` | Other services may send through TELEGRAM_BOT_TOKEN but cannot call getUpdates. | `empty` |

## Expert tuning

| Variable | Purpose | Default |
|---|---|---|
| `DOMAIN_AUTH_ENABLED` | Domain auth / SSO | `false` |
| `DOMAIN_AUTH_HEADER` | Domain auth / SSO | `REMOTE_USER` |
| `DOMAIN_AUTH_HEADER_ALIASES` | Domain auth / SSO | `empty` |
| `DOMAIN_AUTH_AUTO_CREATE` | Domain auth / SSO | `true` |
| `DOMAIN_AUTH_LOWERCASE_USERNAMES` | Domain auth / SSO | `true` |
| `DOMAIN_AUTH_DEFAULT_PROFILE` | Domain auth / SSO | `pilot_user` |
| `LOCAL_ADMIN_USERNAMES` | LDAP / AD | `admin` |
| `LDAP_PASSWORD_LOGIN_ENFORCED` | LDAP / AD | `true` |
| `LDAP_ENABLED` | LDAP / AD | `false` |
| `LDAP_SERVER` | LDAP / AD | `empty` |
| `LDAP_PORT` | LDAP / AD | `empty` |
| `LDAP_BIND_DN` | LDAP / AD | `empty` |
| `LDAP_BIND_PASSWORD` | LDAP / AD | `operator supplied` |
| `LDAP_SEARCH_BASE` | LDAP / AD | `empty` |
| `LDAP_FILTER` | LDAP / AD | `(objectClass=user)` |
| `LDAP_USERNAME_ATTRIBUTE` | LDAP / AD | `sAMAccountName` |
| `LDAP_EMAIL_ATTRIBUTE` | LDAP / AD | `mail` |
| `LDAP_FULL_NAME_ATTRIBUTE` | LDAP / AD | `cn` |
| `LDAP_START_TLS` | LDAP / AD | `false` |
| `LDAP_IGNORE_CERT` | LDAP / AD | `false` |
| `LDAP_NETWORK_TIMEOUT_SECONDS` | LDAP / AD | `3` |
| `LDAP_CA_CERT_FILE` | LDAP_CA_CERT_FILE=/etc/webtrerm/ldap/company-ca.pem | `empty` |
| `LDAP_CA_CERT_DIR` | LDAP_CA_CERT_FILE=/etc/webtrerm/ldap/company-ca.pem | `empty` |
| `STUDIO_MCP_SSE_TRUSTED_PRIVATE_HOSTS` | narrow: runtime requests pin the validated address and never follow redirects. | `empty` |
| `STUDIO_MCP_RUNNER_URL` | backend can reach the runner: e.g. `openssl rand -hex 32`. | `http://mcp-runner:9000` |
| `STUDIO_MCP_RUNNER_TOKEN` | backend can reach the runner: e.g. `openssl rand -hex 32`. | `operator supplied` |
| `MCP_RUNNER_SESSION_TTL_SECONDS` | Optional runner tuning | `300` |
| `MCP_RUNNER_MAX_SESSIONS` | Optional runner tuning | `50` |
| `MCP_RUNNER_REQUEST_TIMEOUT_SECONDS` | Optional runner tuning | `120` |
| `PIPELINE_SCHEDULER_INTERVAL` | Production background workers | `60` |
| `PIPELINE_EXECUTION_INTERVAL_SECONDS` | Production background workers | `5` |
| `PIPELINE_EXECUTION_LEASE_SECONDS` | Production background workers | `180` |
| `PIPELINE_EXECUTION_GLOBAL_CONCURRENCY` | Production background workers | `4` |
| `PIPELINE_EXECUTION_PER_USER_CONCURRENCY` | Production background workers | `2` |
| `PIPELINE_EXECUTION_MAX_ATTEMPTS` | Production background workers | `3` |
| `AGENT_EXECUTION_REPLICAS` | database caps remain authoritative across every replica and process. | `5` |
| `AGENT_EXECUTION_WORKER_CONCURRENCY` | database caps remain authoritative across every replica and process. | `2` |
| `AGENT_EXECUTION_GLOBAL_CONCURRENCY` | database caps remain authoritative across every replica and process. | `10` |
| `AGENT_EXECUTION_PER_USER_CONCURRENCY` | database caps remain authoritative across every replica and process. | `2` |
| `AGENT_EXECUTION_INTERVAL` | database caps remain authoritative across every replica and process. | `2` |
| `AGENT_EXECUTION_LEASE_SECONDS` | database caps remain authoritative across every replica and process. | `180` |
| `AGENT_ACTIVE_RUNS_PER_USER_LIMIT` | database caps remain authoritative across every replica and process. | `5` |
| `AGENT_ACTIVE_RUNS_GLOBAL_LIMIT` | database caps remain authoritative across every replica and process. | `25` |
| `APP_RATE_LIMIT_ASSISTANT_PER_MINUTE` | database caps remain authoritative across every replica and process. | `30` |
| `APP_RATE_LIMIT_PIPELINE_RUNS_PER_MINUTE` | database caps remain authoritative across every replica and process. | `10` |
| `APP_RATE_LIMIT_AGENT_RUNS_PER_MINUTE` | database caps remain authoritative across every replica and process. | `10` |
| `SSH_POOL_IDLE_TTL_SECONDS` | database caps remain authoritative across every replica and process. | `60` |
| `SSH_POOL_MAX_PER_SERVER` | database caps remain authoritative across every replica and process. | `4` |
| `SSH_POOL_MAX_CONNECTIONS` | database caps remain authoritative across every replica and process. | `50` |
| `WEBHOOK_SIGNATURE_TOLERANCE_SECONDS` | database caps remain authoritative across every replica and process. | `300` |
| `SCHEDULED_AGENTS_INTERVAL` | database caps remain authoritative across every replica and process. | `60` |
| `SCHEDULED_AGENTS_LIMIT` | database caps remain authoritative across every replica and process. | `100` |
| `PLAYBOOK_EXECUTION_INTERVAL_SECONDS` | replica shares this database-enforced global claim limit. | `5` |
| `PLAYBOOK_EXECUTION_LEASE_SECONDS` | replica shares this database-enforced global claim limit. | `180` |
| `PLAYBOOK_EXECUTION_GLOBAL_CONCURRENCY` | replica shares this database-enforced global claim limit. | `4` |
| `PLAYBOOK_EXECUTION_PER_USER_CONCURRENCY` | replica shares this database-enforced global claim limit. | `2` |
| `PLAYBOOK_RUNTIME_VOLUME_NAME` | replica shares this database-enforced global claim limit. | `mini_prod_playbook_runtime` |
| `WEBTERM_ANSIBLE_IMAGE` | replica shares this database-enforced global claim limit. | `webterm-ansible:latest` |
| `WEBTERM_BACKEND_IMAGE` | replica shares this database-enforced global claim limit. | `webterm-backend:latest` |
| `WEBTERM_FRONTEND_IMAGE` | replica shares this database-enforced global claim limit. | `webterm-frontend:latest` |
| `WEBTERM_MCP_RUNNER_IMAGE` | replica shares this database-enforced global claim limit. | `webterm-mcp-runner:latest` |
| `MARS_AGENT_DOCKER_IMAGE` | enable it, set an exact registry reference: repository@sha256:<64 hex>. | `empty` |
| `AGENT_COMMAND_RUNTIME` | installer fills a local sha256 image ID automatically when builds are enabled. | `docker` |
| `WEBTERM_OTEL_REQUIRED` | reachable, then enable both the SDK and the deploy gate. | `false` |
| `OTEL_SDK_DISABLED` | reachable, then enable both the SDK and the deploy gate. | `true` |
| `OTEL_SERVICE_NAME` | reachable, then enable both the SDK and the deploy gate. | `webterm` |
| `WEBTERM_ENVIRONMENT` | reachable, then enable both the SDK and the deploy gate. | `production` |
| `OTEL_EXPORTER_OTLP_PROTOCOL` | reachable, then enable both the SDK and the deploy gate. | `http/protobuf` |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | reachable, then enable both the SDK and the deploy gate. | `http://otel-collector:4318` |
| `OTEL_METRIC_EXPORT_INTERVAL` | reachable, then enable both the SDK and the deploy gate. | `30000` |
| `WEBTERM_OTEL_COLLECTOR_IMAGE` | images are digest-pinned and require the full Linux observability smoke before GO. | `otel/opentelemetry-collector-contrib:0.158.0@sha256:c5918f78992ee73b0d6f0e599423ac5ec52dd5d9726733114d6eca53d5a32ed5` |
| `WEBTERM_PROMETHEUS_IMAGE` | images are digest-pinned and require the full Linux observability smoke before GO. | `prom/prometheus:v3.13.2-distroless@sha256:64f71bb84e03c855948418b0fc5dea53e9543d8e3fc9931598f583805507f05e` |
| `WEBTERM_ALERTMANAGER_IMAGE` | images are digest-pinned and require the full Linux observability smoke before GO. | `quay.io/prometheus/alertmanager:main@sha256:a42c3e2e8f7cd4fd3a0ce1bd593ca5abe965c97b993476007d6f69c4a2aa33b5` |
| `WEBTERM_GRAFANA_IMAGE` | images are digest-pinned and require the full Linux observability smoke before GO. | `grafana/grafana:nightly-distroless-slim@sha256:b2c2fd5391216bd57e6bad74c0dce05f8e275479e1153ab57149a4f019a3dceb` |
| `WEBTERM_TEMPO_IMAGE` | images are digest-pinned and require the full Linux observability smoke before GO. | `grafana/tempo:main-1a8b052-2010-1@sha256:78dc87894e9eb054b0229980ac3e7f099b437aec07a8731612373fc09b7f8ba0` |
| `WEBTERM_LOKI_IMAGE` | images are digest-pinned and require the full Linux observability smoke before GO. | `grafana/loki:3.7.6@sha256:efd47c67f9bac88ca29bcf8cb997d9ab29d1848bd0aff579282295542a745952` |
| `PROMETHEUS_RETENTION` | images are digest-pinned and require the full Linux observability smoke before GO. | `30d` |
| `ALERTMANAGER_RETENTION` | images are digest-pinned and require the full Linux observability smoke before GO. | `336h` |
| `LOKI_RETENTION_PERIOD` | images are digest-pinned and require the full Linux observability smoke before GO. | `336h` |
| `TEMPO_RETENTION` | images are digest-pinned and require the full Linux observability smoke before GO. | `336h` |
| `ALERTMANAGER_WEBHOOK_URL_FILE` | stays out of Compose environment/log output and is read by Alertmanager only. | `/etc/webterm/alertmanager.webhook-url` |
| `GRAFANA_ADMIN_USER` | Grafana access | `webterm-admin` |
| `GRAFANA_ADMIN_PASSWORD` | Grafana access | `operator supplied` |
| `GRAFANA_BIND_HOST` | Grafana access | `127.0.0.1` |
| `GRAFANA_PORT` | Grafana access | `3000` |
| `GRAFANA_ROOT_URL` | Grafana access | `https://grafana.webterm.example.com` |
| `GRAFANA_COOKIE_SECURE` | Grafana access | `true` |
| `AGENT_COMMAND_RUNNER_IMAGE` | Agent command runner | `empty` |
| `AGENT_COMMAND_DOCKER_NETWORK` | Agent command runner | `bridge` |
| `AGENT_COMMAND_DOCKER_CPUS` | Agent command runner | `0.5` |
| `AGENT_COMMAND_DOCKER_MEMORY` | Agent command runner | `256m` |
| `AGENT_COMMAND_DOCKER_PIDS_LIMIT` | Agent command runner | `64` |
| `AGENT_COMMAND_TIMEOUT_SECONDS` | Agent command runner | `120` |
| `AGENT_COMMAND_OUTPUT_MAX_CHARS` | Agent command runner | `100000` |
| `AGENT_MATERIAL_RUNNER_ENABLED` | Agent material runner | `false` |
| `AGENT_MATERIAL_RUNNER_IMAGE` | Agent material runner | `empty` |
| `AGENT_MATERIAL_RUNNER_DOCKER_COMMAND` | Agent material runner | `docker` |
| `AGENT_MATERIAL_RUNNER_DOCKER_NETWORK` | Agent material runner | `bridge` |
| `AGENT_MATERIAL_RUNNER_CPUS` | Agent material runner | `0.25` |
| `AGENT_MATERIAL_RUNNER_MEMORY` | Agent material runner | `128m` |
| `AGENT_MATERIAL_RUNNER_PIDS_LIMIT` | Agent material runner | `32` |
| `AGENT_MATERIAL_RUNNER_INPUT_MAX_BYTES` | Agent material runner | `64000` |
| `AGENT_MATERIAL_RUNNER_OUTPUT_MAX_CHARS` | Agent material runner | `50000` |
| `AI_CLI_SUBSCRIPTIONS_ENABLED` | Subscription CLI providers | `false` |
| `AI_CLI_RUNNER_MANAGER_TOKEN` | Subscription CLI providers | `operator supplied` |
| `AI_CLI_CODEX_RUNNER_IMAGE` | Subscription CLI providers | `empty` |
| `AI_CLI_GROK_RUNNER_IMAGE` | Subscription CLI providers | `empty` |
| `AI_CLI_RUNNER_MANAGER_URL` | Subscription CLI providers | `http://ai-cli-runner-manager:9000` |
| `AI_CLI_DOCKER_NETWORK` | Subscription CLI providers | `webterm-ai-cli-egress` |
| `AI_CLI_CREDENTIAL_VOLUME_PREFIX` | Subscription CLI providers | `webterm-ai-cli-cred-` |
| `AI_CLI_EGRESS_PROXY_URL` | Subscription CLI providers | `http://ai-cli-egress-proxy:3128` |
| `AI_CLI_UPSTREAM_PROXY_URL` | Optional parent proxy used by the isolated egress proxy on restricted hosts. | `empty` |
| `AI_CLI_DOCKER_CPUS` | Optional parent proxy used by the isolated egress proxy on restricted hosts. | `1.0` |
| `AI_CLI_DOCKER_MEMORY` | Optional parent proxy used by the isolated egress proxy on restricted hosts. | `1g` |
| `AI_CLI_DOCKER_PIDS_LIMIT` | Optional parent proxy used by the isolated egress proxy on restricted hosts. | `128` |
| `AI_CLI_REQUEST_TIMEOUT_SECONDS` | Optional parent proxy used by the isolated egress proxy on restricted hosts. | `900` |
| `AI_CLI_OUTPUT_LIMIT_BYTES` | Optional parent proxy used by the isolated egress proxy on restricted hosts. | `2097152` |
| `AI_CLI_INTERACTIVE_CAPACITY_WAIT_SECONDS` | Optional parent proxy used by the isolated egress proxy on restricted hosts. | `30` |
| `AI_CLI_UNATTENDED_CAPACITY_WAIT_SECONDS` | Optional parent proxy used by the isolated egress proxy on restricted hosts. | `300` |
| `AI_CLI_AUTH_WORKER_INTERVAL_SECONDS` | Optional parent proxy used by the isolated egress proxy on restricted hosts. | `2` |
| `AI_CLI_AUTH_WORKER_CONCURRENCY` | AI CLI authentication worker and image pins | `4` |
| `WEBTERM_AI_CLI_DOCKER_PROXY_IMAGE` | AI CLI authentication worker and image pins | `empty` |
| `WEBTERM_AI_CLI_EGRESS_PROXY_IMAGE` | AI CLI authentication worker and image pins | `empty` |
| `WEBTERM_AI_CLI_RUNNER_MANAGER_IMAGE` | AI CLI authentication worker and image pins | `empty` |
| `GROK_BUILD_URL` | Grok build inputs | `empty` |
| `GROK_BUILD_SHA256` | Grok build inputs | `empty` |
| `PILOT_RESTRICTED_MODE` | Set true only when intentionally recreating the old closed-pilot boundary. | `false` |
| `PILOT_SSH_ALLOWED_HOSTS` | These legacy allowlists are consulted only when the restricted switch is on. | `empty` |
| `PILOT_SSH_ALLOWED_CIDRS` | These legacy allowlists are consulted only when the restricted switch is on. | `empty` |
| `PILOT_SSH_ALLOWED_PORTS` | These legacy allowlists are consulted only when the restricted switch is on. | `22` |
| `BACKUP_AGE_RECIPIENT_FILE` | repository and production env. | `/etc/webterm/backup.age.recipient` |
| `BACKUP_DIR` | repository and production env. | `./backups/postgres` |
| `BACKUP_STATUS_DIR` | repository and production env. | `./backups/status` |
| `WEBTERM_ANSIBLE_DOCKER_NETWORK` | repository and production env. | `bridge` |
| `WEBTERM_ANSIBLE_DOCKER_CPUS` | repository and production env. | `1.0` |
| `WEBTERM_ANSIBLE_DOCKER_MEMORY` | repository and production env. | `512m` |
| `WEBTERM_ANSIBLE_RUNTIME_TTL_SECONDS` | repository and production env. | `7200` |
| `ANSIBLE_VALIDATOR_MAX_CONCURRENCY` | repository and production env. | `4` |
| `ANSIBLE_VALIDATOR_READ_TIMEOUT_SECONDS` | repository and production env. | `10` |
| `MONITOR_QUICK_INTERVAL` | repository and production env. | `300` |
| `MONITOR_DEEP_INTERVAL` | repository and production env. | `600` |
| `MONITOR_CONCURRENCY` | repository and production env. | `5` |
| `MEMORY_DREAM_INTERVAL` | repository and production env. | `300` |
| `WATCHERS_INTERVAL` | repository and production env. | `120` |
| `WATCHERS_LIMIT` | repository and production env. | `100` |
| `SERVER_BULK_WORKER_INTERVAL_SECONDS` | repository and production env. | `2` |
| `SERVER_BULK_WORKER_LEASE_SECONDS` | repository and production env. | `90` |
| `CELERY_LOG_LEVEL` | repository and production env. | `info` |
| `CELERY_WORKER_CONCURRENCY` | repository and production env. | `2` |
| `KUBERNETES_OPS_ENABLED` | the `kubernetes-ops` Compose profile only when that surface is intentionally deployed. | `false` |
| `KUBERNETES_OPS_SYNC_INTERVAL_SECONDS` | the `kubernetes-ops` Compose profile only when that surface is intentionally deployed. | `300` |
| `KUBERNETES_OPS_SYNC_MAX_BACKOFF_SECONDS` | the `kubernetes-ops` Compose profile only when that surface is intentionally deployed. | `1800` |
| `KUBERNETES_OPS_STALE_AFTER_SECONDS` | the `kubernetes-ops` Compose profile only when that surface is intentionally deployed. | `900` |
| `KUBERNETES_OPS_AUDIT_RETENTION_DAYS` | the `kubernetes-ops` Compose profile only when that surface is intentionally deployed. | `365` |
| `KUBERNETES_OPS_READY_FOR_SIDEBAR` | the `kubernetes-ops` Compose profile only when that surface is intentionally deployed. | `false` |
| `KUBERNETES_OPS_PILOT_SIDEBAR` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_OPS_RELEASE_ENVIRONMENT` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `local` |
| `KUBERNETES_OPS_PRODUCTION_APPROVAL_REF` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `empty` |
| `KUBERNETES_OPS_PRODUCTION_EVIDENCE_REF` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `empty` |
| `KUBERNETES_OPS_IDENTITY_RUNTIME_EVIDENCE_REF` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `empty` |
| `KUBERNETES_OPS_LIVE_PROVIDER_EVIDENCE_REF` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `empty` |
| `KUBERNETES_OPS_READONLY_RBAC_EVIDENCE_REF` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `empty` |
| `KUBERNETES_OPS_KUBERNETES_MCP_EVIDENCE_REF` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `empty` |
| `KUBERNETES_OPS_PRODUCTION_ROLLBACK_EVIDENCE_REF` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `empty` |
| `KUBERNETES_OPS_PRODUCTION_NATIVE_VERIFICATION_EVIDENCE_REF` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `empty` |
| `KUBERNETES_OPS_RELEASE_EVIDENCE_MAX_AGE_SECONDS` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `86400` |
| `KUBERNETES_ADMIN_MODE_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ACTION_REQUEST_NATIVE_EXECUTION_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_NATIVE_APPLY_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_BREAK_GLASS_APPLY_BYPASS_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_DRY_RUN_PROOF_MAX_AGE_SECONDS` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `1800` |
| `KUBERNETES_ADMIN_SECRET_READ_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_NATIVE_PATCH_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_PATCH_MAX_BODY_BYTES` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `65536` |
| `KUBERNETES_ADMIN_NATIVE_SCALE_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_NATIVE_RESTART_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_SCALE_MAX_REPLICAS` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `100` |
| `KUBERNETES_ADMIN_NATIVE_DELETE_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_DELETE_PROTECTED_NAMESPACES` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `kube-system,kube-public,kube-node-lease,cattle-system,cattle-fleet-system,cattle-fleet-local-system,cert-manager,ingress-nginx,devtroncd,argocd,monitoring,logging,local` |
| `KUBERNETES_ADMIN_NATIVE_NODE_MAINTENANCE_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_NODE_DRAIN_EXECUTION_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_NATIVE_EXEC_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_EXEC_STREAMING_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_EXEC_RECORDING_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_EXEC_PROTECTED_NAMESPACES` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `kube-system,kube-public,kube-node-lease,cattle-system,cattle-fleet-system,cattle-fleet-local-system,cert-manager,ingress-nginx,devtroncd,argocd,monitoring,logging,local` |
| `KUBERNETES_ADMIN_EXEC_ALLOWED_COMMANDS` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `/bin/sh,/bin/bash,sh,bash,env,printenv,ls,cat,curl,wget,tail,head,grep,sed,awk,ps,df,du,whoami,hostname,uname,stat` |
| `KUBERNETES_ADMIN_EXEC_DENIED_COMMANDS` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `kubectl,helm,sudo,su,nsenter,mount,umount,chroot,iptables,ip6tables,nft,ssh,scp,nc,netcat,socat,docker,crictl,ctr,nerdctl,apk,apt,apt-get,yum,dnf,rpm,pip,pip3,python,python3,perl,ruby,node,npm,npx,yarn,pnpm,dd,mkfs,reboot,shutdown,kill,killall` |
| `KUBERNETES_ADMIN_NATIVE_PORT_FORWARD_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_PORT_FORWARD_TUNNEL_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_PORT_FORWARD_RECORDING_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_PORT_FORWARD_PROTECTED_NAMESPACES` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `kube-system,kube-public,kube-node-lease,cattle-system,cattle-fleet-system,cattle-fleet-local-system,cert-manager,ingress-nginx,devtroncd,argocd,monitoring,logging,local` |
| `KUBERNETES_ADMIN_PORT_FORWARD_ALLOWED_TARGETS` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `empty` |
| `KUBERNETES_ADMIN_PORT_FORWARD_MAX_DURATION_SECONDS` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `900` |
| `KUBERNETES_ADMIN_PORT_FORWARD_NETWORK_POLICY_EVIDENCE_REF` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `empty` |
| `KUBERNETES_ADMIN_CLUSTER_TERMINAL_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_CLUSTER_TERMINAL_RECORDING_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_NODE_DEBUG_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_NODE_DEBUG_RECORDING_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_RESTRICTED_CREDENTIAL_EVIDENCE_REF` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `empty` |
| `KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_EVIDENCE_REF` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `empty` |
| `KUBERNETES_ADMIN_INTERACTIVE_LIVE_SMOKE_REQUIRED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `false` |
| `KUBERNETES_ADMIN_INTERACTIVE_METADATA_RETENTION_DAYS` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `365` |
| `KUBERNETES_ADMIN_INTERACTIVE_TRANSCRIPT_RETENTION_DAYS` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `30` |
| `KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_CHARS` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `2000` |
| `KUBERNETES_ADMIN_TRANSCRIPT_EVENT_MAX_COUNT` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `2000` |
| `HISTORY_PRUNE_INTERVAL_SECONDS` | High-volume history retention (background history-pruner, never HTTP) | `86400` |
| `HISTORY_PRUNE_BATCH_SIZE` | High-volume history retention (background history-pruner, never HTTP) | `1000` |
| `HISTORY_RETENTION_PIPELINE_RUN_DAYS` | High-volume history retention (background history-pruner, never HTTP) | `90` |
| `HISTORY_RETENTION_PIPELINE_RUN_MAX_ROWS` | High-volume history retention (background history-pruner, never HTTP) | `100000` |
| `HISTORY_RETENTION_AGENT_RUN_DAYS` | High-volume history retention (background history-pruner, never HTTP) | `90` |
| `HISTORY_RETENTION_AGENT_RUN_MAX_ROWS` | High-volume history retention (background history-pruner, never HTTP) | `100000` |
| `HISTORY_RETENTION_SERVER_COMMAND_HISTORY_DAYS` | High-volume history retention (background history-pruner, never HTTP) | `90` |
| `HISTORY_RETENTION_SERVER_COMMAND_HISTORY_MAX_ROWS` | High-volume history retention (background history-pruner, never HTTP) | `500000` |
| `HISTORY_RETENTION_COMMAND_SNAPSHOT_DAYS` | High-volume history retention (background history-pruner, never HTTP) | `30` |
| `HISTORY_RETENTION_COMMAND_SNAPSHOT_MAX_ROWS` | High-volume history retention (background history-pruner, never HTTP) | `50000` |
| `COMMAND_SNAPSHOT_MAX_CONTENT_BYTES` | High-volume history retention (background history-pruner, never HTTP) | `1048576` |
| `HISTORY_RETENTION_SERVER_HEALTH_CHECK_DAYS` | High-volume history retention (background history-pruner, never HTTP) | `7` |
| `HISTORY_RETENTION_SERVER_HEALTH_CHECK_MAX_ROWS` | High-volume history retention (background history-pruner, never HTTP) | `1000000` |
| `HISTORY_RETENTION_RESOLVED_SERVER_ALERT_DAYS` | High-volume history retention (background history-pruner, never HTTP) | `30` |
| `HISTORY_RETENTION_RESOLVED_SERVER_ALERT_MAX_ROWS` | High-volume history retention (background history-pruner, never HTTP) | `500000` |
| `HISTORY_RETENTION_CHAT_ARTIFACT_DAYS` | High-volume history retention (background history-pruner, never HTTP) | `90` |
| `HISTORY_RETENTION_CHAT_ARTIFACT_MAX_ROWS` | High-volume history retention (background history-pruner, never HTTP) | `100000` |
| `HISTORY_RETENTION_USER_ACTIVITY_LOG_MAX_ROWS` | High-volume history retention (background history-pruner, never HTTP) | `500000` |
| `HISTORY_RETENTION_LLM_USAGE_LOG_MAX_ROWS` | High-volume history retention (background history-pruner, never HTTP) | `500000` |
| `PLUGIN_MARKETPLACE_ALLOW_SANDBOXED_CODE_PACKAGES` | Plugin extension trust boundaries | `false` |
| `PLUGIN_MARKETPLACE_BACKEND_SANDBOX_ENABLED` | Plugin extension trust boundaries | `false` |
| `PLUGIN_MARKETPLACE_BACKEND_SANDBOX_PROVIDER` | database, secret, and network privileges. Use disabled or an isolated external worker. | `external_worker` |
| `PLUGIN_BACKEND_RUNNER_IMAGE` | database, secret, and network privileges. Use disabled or an isolated external worker. | `empty` |
| `PLUGIN_BACKEND_DOCKER_EGRESS_NETWORK` | database, secret, and network privileges. Use disabled or an isolated external worker. | `empty` |
| `PLUGIN_BACKEND_DOCKER_CPUS` | database, secret, and network privileges. Use disabled or an isolated external worker. | `0.5` |
| `PLUGIN_BACKEND_DOCKER_MEMORY` | database, secret, and network privileges. Use disabled or an isolated external worker. | `128m` |
| `PLUGIN_BACKEND_DOCKER_PIDS_LIMIT` | database, secret, and network privileges. Use disabled or an isolated external worker. | `32` |
| `WEBTERM_PLUGIN_BACKEND_DOCKER_PROXY_IMAGE` | database, secret, and network privileges. Use disabled or an isolated external worker. | `webterm-plugin-backend-docker-proxy:latest` |
| `PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_ENDPOINT` | database, secret, and network privileges. Use disabled or an isolated external worker. | `https://sandbox.example.com/plugin-marketplace/execute` |
| `PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_AUTH_TOKEN` | database, secret, and network privileges. Use disabled or an isolated external worker. | `operator supplied` |
| `PLUGIN_MARKETPLACE_BACKEND_SANDBOX_TIMEOUT_SECONDS` | database, secret, and network privileges. Use disabled or an isolated external worker. | `10` |
| `PLUGIN_MARKETPLACE_BACKEND_SANDBOX_MAX_OUTPUT_BYTES` | database, secret, and network privileges. Use disabled or an isolated external worker. | `262144` |
| `PLUGIN_MARKETPLACE_FRONTEND_SANDBOX_ENABLED` | database, secret, and network privileges. Use disabled or an isolated external worker. | `false` |
| `PLUGIN_MARKETPLACE_ALLOW_DYNAMIC_FRONTEND_BUNDLES` | database, secret, and network privileges. Use disabled or an isolated external worker. | `false` |
| `PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_DISTRIBUTION_PROVIDER` | database, secret, and network privileges. Use disabled or an isolated external worker. | `external_artifact_host` |
| `PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_FRONTEND_BUNDLE_HOST` | database, secret, and network privileges. Use disabled or an isolated external worker. | `true` |
| `PLUGIN_MARKETPLACE_EXTERNAL_FRONTEND_BUNDLE_ENDPOINT` | database, secret, and network privileges. Use disabled or an isolated external worker. | `https://bundles.example.com/plugin-marketplace/readiness` |
| `PLUGIN_MARKETPLACE_EXTERNAL_FRONTEND_BUNDLE_AUTH_TOKEN` | database, secret, and network privileges. Use disabled or an isolated external worker. | `operator supplied` |
| `PLUGIN_MARKETPLACE_EXTERNAL_FRONTEND_BUNDLE_TIMEOUT_SECONDS` | database, secret, and network privileges. Use disabled or an isolated external worker. | `10` |
| `PLUGIN_MARKETPLACE_FRONTEND_BUNDLE_ALLOWED_HOSTS` | database, secret, and network privileges. Use disabled or an isolated external worker. | `cdn.example.com` |
| `PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_ISOLATION_MODE` | database, secret, and network privileges. Use disabled or an isolated external worker. | `subprocess_no_code` |
| `PLUGIN_MARKETPLACE_COMPATIBILITY_JOB_TIMEOUT_SECONDS` | database, secret, and network privileges. Use disabled or an isolated external worker. | `20` |
| `PLUGIN_MARKETPLACE_SANDBOX_DEPENDENCY_ALLOWLIST` | Explicit ecosystem:name entries only. Packages with undeclared dependencies are blocked. | `empty` |
| `PLUGIN_MARKETPLACE_REQUIRED_ATTESTATION_KINDS` | Optional hard gate: require recent passed attestations before catalog compatibility or enable. | `empty` |
| `PLUGIN_MARKETPLACE_ATTESTATION_MAX_AGE_DAYS` | Optional hard gate: require recent passed attestations before catalog compatibility or enable. | `0` |
| `PLUGIN_MARKETPLACE_ATTESTATION_RETENTION_LIMIT` | Optional hard gate: require recent passed attestations before catalog compatibility or enable. | `20` |
| `PLUGIN_MARKETPLACE_EGRESS_DENIED_HOSTS` | Optional hard gate: require recent passed attestations before catalog compatibility or enable. | `metadata.google.internal,169.254.169.254` |
| `PLUGIN_MARKETPLACE_REMOTE_PACKAGE_ALLOWED_HOSTS` | Optional hard gate: require recent passed attestations before catalog compatibility or enable. | `packages.example.com` |
| `PLUGIN_MARKETPLACE_CATALOG_SOURCE_ALLOWED_HOSTS` | Exact HTTPS hosts only. Empty disables remote catalog sync (fail-closed). | `catalog.example.com` |
| `PLAYBOOK_GITLAB_ALLOWED_HOSTS` | Allowlisted GitLab hosts for one-time Ansible project imports. | `gitlab.com` |
| `PLAYBOOK_GITLAB_TIMEOUT_SECONDS` | Allowlisted GitLab hosts for one-time Ansible project imports. | `15` |
| `PLUGIN_MARKETPLACE_SIGNING_PROVIDER` | Allowlisted GitLab hosts for one-time Ansible project imports. | `external_kms` |
| `PLUGIN_MARKETPLACE_SIGNING_KEYS` | Allowlisted GitLab hosts for one-time Ansible project imports. | `{}` |
| `PLUGIN_MARKETPLACE_DEFAULT_SIGNING_KEY_ID` | Allowlisted GitLab hosts for one-time Ansible project imports. | `replace-with-kms-key-alias` |
| `PLUGIN_MARKETPLACE_REQUIRE_CONFIGURED_SIGNING_KEYS` | Allowlisted GitLab hosts for one-time Ansible project imports. | `true` |
| `PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SIGNING_PROVIDER` | Allowlisted GitLab hosts for one-time Ansible project imports. | `true` |
| `PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_ENDPOINT` | Allowlisted GitLab hosts for one-time Ansible project imports. | `https://kms.example.com/plugin-marketplace/sign` |
| `PLUGIN_MARKETPLACE_EXTERNAL_VERIFY_ENDPOINT` | Allowlisted GitLab hosts for one-time Ansible project imports. | `https://kms.example.com/plugin-marketplace/verify` |
| `PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_AUTH_TOKEN` | Allowlisted GitLab hosts for one-time Ansible project imports. | `operator supplied` |
| `PLUGIN_MARKETPLACE_EXTERNAL_SIGNING_TIMEOUT_SECONDS` | Allowlisted GitLab hosts for one-time Ansible project imports. | `5` |
| `PLUGIN_MARKETPLACE_SECURITY_SCAN_PROVIDER` | Allowlisted GitLab hosts for one-time Ansible project imports. | `external` |
| `PLUGIN_MARKETPLACE_REQUIRE_EXTERNAL_SECURITY_SCANNER` | Allowlisted GitLab hosts for one-time Ansible project imports. | `true` |
| `PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_ENDPOINT` | Allowlisted GitLab hosts for one-time Ansible project imports. | `https://scanner.example.com/plugin-marketplace/scan` |
| `PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_AUTH_TOKEN` | Allowlisted GitLab hosts for one-time Ansible project imports. | `operator supplied` |
| `PLUGIN_MARKETPLACE_EXTERNAL_SECURITY_SCAN_TIMEOUT_SECONDS` | Allowlisted GitLab hosts for one-time Ansible project imports. | `20` |
| `PLUGIN_MARKETPLACE_SECURITY_SCAN_BLOCK_SEVERITIES` | Allowlisted GitLab hosts for one-time Ansible project imports. | `critical,high` |
| `PLUGIN_MARKETPLACE_SECURITY_SCAN_PASS_STATUSES` | Allowlisted GitLab hosts for one-time Ansible project imports. | `clean,ok,pass,passed,success` |
| `PLUGIN_MARKETPLACE_PACKAGE_RETENTION_DIR` | Allowlisted GitLab hosts for one-time Ansible project imports. | `empty` |
| `PLUGIN_MARKETPLACE_RETAINED_PACKAGE_MAX_AGE_DAYS` | Allowlisted GitLab hosts for one-time Ansible project imports. | `0` |
| `http_proxy` | Corporate proxies, only if needed | `empty` |
| `https_proxy` | Corporate proxies, only if needed | `empty` |
| `ftp_proxy` | Corporate proxies, only if needed | `empty` |
| `no_proxy` | Corporate proxies, only if needed | `localhost,127.0.0.1,::1,postgres,redis,backend,frontend,nginx,mcp-runner` |
| `HTTP_PROXY` | Corporate proxies, only if needed | `empty` |
| `HTTPS_PROXY` | Corporate proxies, only if needed | `empty` |
| `FTP_PROXY` | Corporate proxies, only if needed | `empty` |
| `NO_PROXY` | Corporate proxies, only if needed | `localhost,127.0.0.1,::1,postgres,redis,backend,frontend,nginx,mcp-runner` |
