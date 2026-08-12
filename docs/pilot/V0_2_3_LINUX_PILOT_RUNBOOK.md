# WebTerm v0.2.3 Linux pilot runbook

This runbook targets one dedicated Linux host with only disposable or
snapshot-capable SSH targets. Keep production servers outside the pilot.

## Install

1. Install Docker Compose and `age`, place this exact candidate under
   `/opt/webterm`, then copy `.env.production.example` to `.env.production`.
   Set the public URL, database values and immutable release image references.
2. Put the reviewed HTTPS Grok artifact URL and its lowercase SHA-256 in
   `GROK_BUILD_URL` / `GROK_BUILD_SHA256` only when building locally. Published
   digest images do not need these build inputs on the pilot host.
3. Provision the mandatory fail-closed SSH boundary. Set
   `PILOT_RESTRICTED_MODE=true`; fill `PILOT_SSH_ALLOWED_HOSTS` with only exact
   lowercase disposable-host names/IPs, `PILOT_SSH_ALLOWED_CIDRS` with the
   strict test-network CIDRs that contain every resolved address, and
   `PILOT_SSH_ALLOWED_PORTS` with `22` and/or `2222`. Empty lists deny all.
   `localhost`, metadata, backend, PostgreSQL, Redis and other internal service
   destinations remain denied even when named accidentally. Pilot SSH accounts
   must be unprivileged, have no sudo rights and exist only on snapshot-capable
   test hosts.
4. Generate an age identity without printing its contents and derive the
   public recipient file. Keep the identity offline from all running WebTerm
   containers and escrow a protected copy separately:

   ```bash
   sudo install -d -m 0750 -o webterm -g webterm /etc/webterm
   sudo -u webterm age-keygen -o /etc/webterm/backup.age.identity >/dev/null 2>&1
   sudo -u webterm sh -c \
     'age-keygen -y /etc/webterm/backup.age.identity > /etc/webterm/backup.age.recipient'
   sudo chmod 0600 /etc/webterm/backup.age.identity
   sudo chmod 0644 /etc/webterm/backup.age.recipient
   ```

   Set `BACKUP_AGE_RECIPIENT_FILE=/etc/webterm/backup.age.recipient`,
   `BACKUP_DIR=/opt/webterm/backups/postgres` and
   `BACKUP_STATUS_DIR=/opt/webterm/backups/status` in `.env.production`.
5. Provision the Alertmanager notification URL as a one-line HTTPS secret
   owned by the container's unprivileged UID. It must not be placed directly
   in `.env.production`, Compose output or shell history:

   ```bash
   sudo install -o 65534 -g 65534 -m 0600 /dev/null \
     /etc/webterm/alertmanager.webhook-url
   read -rsp 'Pilot alert HTTPS webhook URL: ' WEBTERM_ALERT_WEBHOOK_URL; echo
   printf '%s\n' "$WEBTERM_ALERT_WEBHOOK_URL" \
     | sudo tee /etc/webterm/alertmanager.webhook-url >/dev/null
   unset WEBTERM_ALERT_WEBHOOK_URL
   sudo chown 65534:65534 /etc/webterm/alertmanager.webhook-url
   sudo chmod 0600 /etc/webterm/alertmanager.webhook-url
   ```

   Set `ALERTMANAGER_WEBHOOK_URL_FILE=/etc/webterm/alertmanager.webhook-url`.
6. Keep the pilot capacity contract at
   `AGENT_EXECUTION_GLOBAL_CONCURRENCY=10`,
   `AGENT_EXECUTION_PER_USER_CONCURRENCY=2`, five replicas and two local slots
   per replica. The installer rejects a global value other than 10, a per-user
   value other than 2 or a worker pool with fewer than 10 slots; the shared
   PostgreSQL claim cap remains authoritative even if more local slots exist.
7. Start the complete pilot plane. The installer refuses AI CLI without the
   restricted SSH allowlist and refuses observability without `age` and the
   public backup recipient or notification secret:

   ```bash
   ./docker/install-production.sh \
     --with-ai-cli \
     --with-observability \
     --generate-secrets
   ```

Grafana binds to `127.0.0.1:3000`. Reach it through an SSH/VPN tunnel or put an
operator-managed TLS reverse proxy in front of that loopback address. Do not
publish Prometheus, Alertmanager, Loki, Tempo, the collector or the runner
manager.

The candidate intentionally pins reviewed immutable Grafana nightly and Tempo
main snapshots because the current compatible stable images failed the
fixable-HIGH container gate. They are not stable releases. Before GO, run a
fresh Linux smoke against the exact digests and prove Grafana startup, admin
login, dashboard and all three datasource provisioning paths, required plugin
availability, Prometheus/Loki/Tempo queries, trace ingestion and the configured
14/30-day retention. Any failure means NO-GO; do not replace a digest with a
mutable `latest`, `main` or `nightly` reference.

## Encrypted backup schedule

Create `/etc/webterm/backup.env` (mode `0600`, owner `webterm`) with only paths
and non-secret Compose settings:

```text
BACKUP_AGE_RECIPIENT_FILE=/etc/webterm/backup.age.recipient
BACKUP_DIR=/opt/webterm/backups/postgres
BACKUP_STATUS_DIR=/opt/webterm/backups/status
COMPOSE_FILE=/opt/webterm/docker-compose.production.yml
ENV_FILE=/opt/webterm/.env.production
PROJECT_NAME=webtrerm-prod
```

Create `/etc/webterm/backup-restore-test.env` separately with mode `0600` and
only `BACKUP_AGE_IDENTITY_FILE=/etc/webterm/backup.age.identity`. Do not put the
identity contents in either file, command arguments, logs or the repository.
Install the supplied nightly-backup and weekly restore-validation timers:

```bash
sudo install -m 0755 docker/systemd/verify-latest-encrypted-backup.sh \
  /opt/webterm/docker/systemd/verify-latest-encrypted-backup.sh
sudo install -m 0644 docker/systemd/webterm-postgres-backup.service \
  docker/systemd/webterm-postgres-backup.timer \
  docker/systemd/webterm-postgres-restore-test.service \
  docker/systemd/webterm-postgres-restore-test.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now webterm-postgres-backup.timer webterm-postgres-restore-test.timer
sudo systemctl start webterm-postgres-backup.service
sudo systemctl start webterm-postgres-restore-test.service
```

The backup pipeline streams PostgreSQL plus `mini_prod_media`,
`mini_prod_config` and `playbook_bundles` through archive validation and age
encryption; it never writes a plaintext dump or volume archive. AI credential,
log, Prometheus, Grafana, Tempo and Loki volumes are intentionally excluded.
Re-authenticate Codex and Grok after a restore. Prometheus receives only the
success/failure Unix timestamps, never archive, recipient or identity contents.
Run full restores only against an isolated disposable Compose project with
`RESTORE_CONFIRM=RESTORE_WEBTERM` for PostgreSQL and
`RESTORE_CONFIRM=RESTORE_WEBTERM_VOLUMES` for the important-volume archive.
The volume restore refuses to run while any Compose container mounts a target
path. The weekly timer performs both non-mutating archive/decryption validation
paths.

## Notification delivery test

After the observability profile is healthy, submit a short-lived synthetic
alert and confirm both its firing and resolved notifications arrive at the
provisioned operator receiver:

```bash
docker compose --project-name webtrerm-prod --env-file .env.production \
  -f docker-compose.production.yml --profile observability exec -T alertmanager \
  /bin/amtool --alertmanager.url=http://127.0.0.1:9093 alert add \
  alertname=WebTermPilotNotificationTest severity=warning service=pilot-test \
  --end "$(date -u -d '+2 minutes' +%Y-%m-%dT%H:%M:%SZ)"
```

Do not accept the alerting gate from rule evaluation alone: retain receiver-side
evidence of both notification states without recording the webhook URL.

## Mandatory evidence before users enter

- `/api/ready/` is HTTP 200 and every enabled component reports ready.
- `docker compose ... ps` shows the four AI services and six observability
  services running/healthy.
- Prometheus scrapes `webterm` and `otel-collector`; Grafana shows the WebTerm
  Pilot Overview dashboard. Agent queue/worker heartbeat, AI auth backlog,
  provider failures/quota, stale leases, PostgreSQL, Redis, host disk and
  encrypted-backup freshness are present; a test alert and trace are visible.
- Codex and Grok each pass login, one read-only request, cancellation, restart,
  quota/error handling and revoke cleanup using separate pilot accounts.
- The 20-user test submits 40 read-only 60-second jobs, holds the global active
  limit at 10, loses or duplicates none and drains the queue within four
  minutes.
- The nightly backup and weekly restore-test timers are enabled; an encrypted
  backup, checksum, dry restore validation, isolated full restore and application
  rollback have succeeded on this candidate.

## Emergency shutdown

First revoke connections in the application. If the manager is unavailable,
perform the explicit offline cleanup:

```bash
./docker/install-production.sh --cleanup-ai-cli-credentials
```

The command stops the AI CLI plane, removes only volumes under the configured
credential prefix, and sets `AI_CLI_SUBSCRIPTIONS_ENABLED=false`. Re-run the
installer without AI CLI until the incident is understood.
