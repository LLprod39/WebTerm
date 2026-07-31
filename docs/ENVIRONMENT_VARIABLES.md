# Production environment variables

Generated from `.env.production.example` by `scripts/env_contract.py`. Do not edit this table by hand.

Total variables: **304**.

## Required

| Variable | Purpose | Default |
|---|---|---|
| `PUBLIC_BIND_HOST` | Public URLs and ports | `0.0.0.0` |
| `PUBLIC_HTTP_PORT` | Public URLs and ports | `80` |
| `PUBLIC_HTTPS_PORT` | Public URLs and ports | `443` |
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
| `DOMAIN_AUTH_DEFAULT_PROFILE` | Domain auth / SSO | `server_only` |
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
| `APP_RATE_LIMIT_ASSISTANT_PER_MINUTE` | Production background workers | `30` |
| `APP_RATE_LIMIT_PIPELINE_RUNS_PER_MINUTE` | Production background workers | `10` |
| `APP_RATE_LIMIT_AGENT_RUNS_PER_MINUTE` | Production background workers | `10` |
| `SSH_POOL_IDLE_TTL_SECONDS` | Production background workers | `60` |
| `SSH_POOL_MAX_PER_SERVER` | Production background workers | `4` |
| `SSH_POOL_MAX_CONNECTIONS` | Production background workers | `50` |
| `WEBHOOK_SIGNATURE_TOLERANCE_SECONDS` | Production background workers | `300` |
| `SCHEDULED_AGENTS_INTERVAL` | Production background workers | `60` |
| `SCHEDULED_AGENTS_LIMIT` | Production background workers | `100` |
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
| `OTEL_EXPORTER_OTLP_PROTOCOL` | reachable, then enable both the SDK and the deploy gate. | `http/protobuf` |
| `AGENT_COMMAND_RUNNER_IMAGE` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `empty` |
| `AGENT_COMMAND_DOCKER_NETWORK` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `bridge` |
| `AGENT_COMMAND_DOCKER_CPUS` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `0.5` |
| `AGENT_COMMAND_DOCKER_MEMORY` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `256m` |
| `AGENT_COMMAND_DOCKER_PIDS_LIMIT` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `64` |
| `AGENT_COMMAND_TIMEOUT_SECONDS` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `120` |
| `AGENT_COMMAND_OUTPUT_MAX_CHARS` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `100000` |
| `WEBTERM_ANSIBLE_DOCKER_NETWORK` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `bridge` |
| `WEBTERM_ANSIBLE_DOCKER_CPUS` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `1.0` |
| `WEBTERM_ANSIBLE_DOCKER_MEMORY` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `512m` |
| `WEBTERM_ANSIBLE_RUNTIME_TTL_SECONDS` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `7200` |
| `ANSIBLE_VALIDATOR_MAX_CONCURRENCY` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `4` |
| `ANSIBLE_VALIDATOR_READ_TIMEOUT_SECONDS` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `10` |
| `MONITOR_QUICK_INTERVAL` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `300` |
| `MONITOR_DEEP_INTERVAL` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `600` |
| `MONITOR_CONCURRENCY` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `5` |
| `MEMORY_DREAM_INTERVAL` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `300` |
| `AGENT_EXECUTION_INTERVAL` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `5` |
| `WATCHERS_INTERVAL` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `120` |
| `WATCHERS_LIMIT` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `100` |
| `SERVER_BULK_WORKER_INTERVAL_SECONDS` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `2` |
| `SERVER_BULK_WORKER_LEASE_SECONDS` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `90` |
| `CELERY_LOG_LEVEL` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `info` |
| `CELERY_WORKER_CONCURRENCY` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `2` |
| `KUBERNETES_OPS_SYNC_INTERVAL_SECONDS` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `300` |
| `KUBERNETES_OPS_SYNC_MAX_BACKOFF_SECONDS` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `1800` |
| `KUBERNETES_OPS_STALE_AFTER_SECONDS` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `900` |
| `KUBERNETES_OPS_AUDIT_RETENTION_DAYS` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `365` |
| `KUBERNETES_OPS_READY_FOR_SIDEBAR` | OTEL_EXPORTER_OTLP_HEADERS=authorization=Bearer%20replace-me | `false` |
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
| `KUBERNETES_ADMIN_SECRET_READ_ENABLED` | Closed pilot: waive production-only release_scope evidence (still need READY_FOR_SIDEBAR=true + runtime checks) | `placeholder; replace` |
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
