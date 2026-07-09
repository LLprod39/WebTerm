# Backup, restore drill, kill switch, alerts

## DB backup

Script: `scripts/backup_postgres.sh`

```bash
# From repo root with production compose stack running:
export COMPOSE_FILE=docker-compose.production.yml
export POSTGRES_SERVICE=db
./scripts/backup_postgres.sh
```

Retention defaults: **7 daily** dumps + **4 weekly** (Sunday copies).

Also back up volumes:

- `mini_prod_config` / model config (`.model_config.json`)
- `mini_prod_media` media uploads

Example volume archive:

```bash
docker run --rm -v mini_prod_config:/data -v "$(pwd)/backups:/out" alpine \
  tar czf /out/config_$(date -u +%Y%m%dT%H%M%SZ).tgz -C /data .
```

## Restore drill

Script: `scripts/restore_postgres.sh`

```bash
# Integrity-only dry run (no write):
RESTORE_DRY_RUN=1 ./scripts/restore_postgres.sh backups/postgres/webterm_....sql.gz

# Real restore (destructive):
./scripts/restore_postgres.sh backups/postgres/webterm_....sql.gz
```

Clean-machine drill checklist:

1. Install docker + compose, copy compose files + `.env.production`.
2. `docker compose -f docker-compose.production.yml up -d db`
3. Restore dump with script.
4. Start backend/workers and open login page.
5. Confirm pipelines and servers list load.

## Kill switch

Command: `python manage.py ops_kill_switch`

```bash
python manage.py ops_kill_switch --pause --reason "incident response" --actor ops
python manage.py ops_kill_switch --status
python manage.py ops_kill_switch --resume
```

Behavior:

- Scheduled pipelines skip ticks while paused (`run_scheduled_pipelines`).
- New `agent/react` / `agent/multi` node starts fail with a clear error.
- Flag file default: `runtime_logs/ops_kill_switch.json` (override `WEBTERM_OPS_KILL_SWITCH_PATH`).
- Env override: `WEBTERM_OPS_PAUSE_ALL=1`.

## Concurrency / LLM budget

Runtime limits live in `app/runtime_limit_config.py` / Settings:

- `AGENT_ACTIVE_RUNS_GLOBAL_LIMIT` (default 25)
- `AGENT_ACTIVE_RUNS_PER_USER_LIMIT` (default 5)
- `PIPELINE_ACTIVE_RUNS_GLOBAL_LIMIT` (default 40)
- `LLM_DAILY_TOKEN_LIMIT_PER_USER` (0 = disabled)

Tune via `.model_config.json` runtime limit overrides or Django settings.

## Platform alerts

Compose already supports:

- `TELEGRAM_BOT_TOKEN` / pipeline notification telegram defaults
- `PIPELINE_NOTIFY_EMAIL` / SMTP settings for email reports

Recommended: route failed scheduled pipeline runs to Telegram/email notification nodes or admin email.

## Upgrade / rollback

1. Tag images before deploy.
2. `docker compose -f docker-compose.production.yml pull && up -d`
3. Run migrations only after DB backup.
4. Rollback: redeploy previous image tags + restore dump if schema broke.
