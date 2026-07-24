# v0.1 installation, upgrade, rollback and recovery runbook

This runbook defines the operator procedure for the controlled v0.1 pilot. Commands are validated by the release checklist before a release is approved.

## Clean installation

1. Provision a supported Linux host and install Docker with Compose.
2. Clone the tagged WebTerm release; never deploy a moving branch as a release.
3. Copy `.env.production.example` to `.env.production` and replace every placeholder secret, host and URL.
4. Run `./install-server.sh --help`, select the explicit repository/tag, directory, host and HTTPS mode, then install.
5. Verify `docker compose -f docker-compose.production.yml ps`, `/api/health/`, login, readiness and audit access.
6. Record the image digests, commit SHA, configuration checksum and evidence bundle.

The repository-side F-13a proof runs `./docker/production-install-smoke.sh` on a fresh Ubuntu CI runner. It refuses hosts that already contain WebTerm containers, executes the real production installer, requires migration/deploy checks, verifies authenticated readiness and fail-closed Plugins, checks scheduler/worker heartbeats plus Celery, and exercises terminal, pipeline and agent runtime paths over HTTPS/WebSocket. The workflow uploads the exact SHA, host/tool versions, Compose state/images/logs and probe results from every run.

### Playbook execution worker

Ansible runs are claimed from a durable database queue by `playbook-execution-worker`; the web process only validates and enqueues them. Keep `PLAYBOOK_EXECUTION_LEASE_SECONDS` longer than the expected heartbeat interval and use `PLAYBOOK_EXECUTION_GLOBAL_CONCURRENCY` as the cluster-wide safety cap. Additional replicas can be started with `docker compose --env-file .env.production -f docker-compose.production.yml up -d --scale playbook-execution-worker=N`. Each replica derives a unique worker key from its container hostname.

After an unclean worker stop, an expired mutating run is marked interrupted/failed and is never replayed automatically. Inspect the run, target state and audit trail before requesting an explicit rerun. Per-run variables and the optional master password are encrypted while queued and deleted after every terminal execution path.

## Upgrade

1. Read `CHANGELOG.md`, migrations and support-matrix changes.
2. Export the database and persistent volumes; verify the backup is readable.
3. Pull immutable images for the target tag and record their digests.
4. Run migration and Compose-model checks in a staging copy.
5. Apply the upgrade during a declared window, run health/readiness and the primary smoke flow, then retain the previous images and backup.

## Rollback

1. Stop writes and record the failure time and affected operations.
2. If migrations are backward-compatible, redeploy the prior image digests.
3. If data was changed incompatibly, stop the stack and restore the pre-upgrade database/volumes before starting prior images.
4. Run health, login, inventory, terminal connection and audit checks. Document data loss or replay needs.

## Backup and restore

Create the PostgreSQL archive from the production project without placing a password on the command line:

```bash
BACKUP_DIR=/secure/webterm-backups \
PROJECT_NAME=mini-prod \
ENV_FILE=.env.production \
./scripts/backup_postgres.sh
```

The command emits a compressed custom-format dump plus a SHA-256 sidecar and validates the archive with `pg_restore --list` before publishing it. Back up `.env.production` and the `mini_prod_config` / `mini_prod_media` volumes into the same access-controlled backup set. The environment contains encryption material and must never be attached to CI, tickets or ordinary logs. Static assets are rebuilt from the release; operational logs follow the separate retention/export policy. Plugin trust metadata lives in PostgreSQL, while retained package bytes live under media; the dump plus media archive cover both parts.

Restore only into an isolated target first:

```bash
RESTORE_CONFIRM=RESTORE_WEBTERM \
PROJECT_NAME=webterm-restore-drill \
ENV_FILE=.env.production.restore \
COMPOSE_FILE=docker-compose.production.yml \
COMPOSE_OVERRIDE_FILE=docker-compose.production.recovery.yml \
./scripts/restore_postgres.sh /secure/webterm-backups/webterm_<UTC>.dump
```

The restore command is intentionally blocked unless the explicit confirmation is present. Restore the matching secret environment and config/media archives, then validate authentication, managed-secret decryptability, inventory, pipelines/runs, audit chronology and plugin-package hashes. Never restore over the only copy or reuse production volumes for a drill.

The repository-side F-13b proof is `./docker/production-recovery-smoke.sh`. On a fresh Linux runner it builds source state through the F-13a installer, creates a consistent PostgreSQL dump, captures secret/config/media/Redis state in a temporary mode-700 directory, restores into a distinct Compose project and volumes, compares privacy-safe integrity manifests, and restarts PostgreSQL and Redis. Only checksums, sizes, exact SHA, timestamps and pass/fail manifests are uploaded; the dump, environment, volume archives and credentials are deleted during cleanup.

## Disaster recovery

1. Declare the incident and freeze automated actions.
2. Recreate a supported host from pinned infrastructure configuration.
3. Restore secrets, database and persistent volumes; deploy recorded image digests.
4. Rotate credentials that may have been exposed.
5. Run the release smoke flow and reconcile queued/running operations before reopening access.

Recovery-time and recovery-point objectives are not claimed until a separately approved timed disaster-recovery drill has retained evidence. F-13b proves recoverability, not an RTO/RPO commitment.

## Troubleshooting

- `docker compose ... config --quiet` failing: compare `.env.production` with the example and remove unresolved placeholders.
- Health failing: inspect backend, PostgreSQL and Redis health before restarting; preserve logs and timestamps.
- Login works but features are denied: inspect the server-generated access payload and role assignments.
- Terminal or guarded action failing: verify host reachability, host-key policy, approval state and audit event creation.
- Playbook stays queued: verify `playbook-execution-worker` is running, then inspect its worker heartbeat and the dispatch lease; do not manually duplicate the queued row.
- Playbook is interrupted after a restart: review the partial remote changes and start an explicit rerun only when it is operationally safe.
- Upgrade regression: stop new writes and follow rollback; do not run ad-hoc schema edits.

Escalation, known limitations and final sign-off live in [the release checklist](V0_1_RELEASE_CHECKLIST.md).
