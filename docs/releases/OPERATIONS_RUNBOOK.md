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

### Managed-secret key rotation

Managed secrets use `v2:<key_id>:<ciphertext>` envelopes. New writes use `MANAGED_SECRET_KEY`; `MANAGED_SECRET_PREVIOUS_KEYS` is a JSON object containing only the old keys needed during a bounded rotation window. Never pass encryption keys as command arguments.

1. With the old configuration still active, record its non-secret key id: `docker compose --env-file .env.production -f docker-compose.production.yml exec backend python manage.py rotate_managed_secrets --dry-run`.
2. Generate a new random `MANAGED_SECRET_KEY` and choose a unique `MANAGED_SECRET_KEY_ID`. Set the new values as current and set `MANAGED_SECRET_PREVIOUS_KEYS={"<old-key-id>":"<old-key>"}` in the protected environment.
3. Recreate backend and every worker with that same keyring. Confirm readiness before rotating data; mixed process keyrings are not allowed.
4. Run `docker compose --env-file .env.production -f docker-compose.production.yml exec backend python manage.py rotate_managed_secrets --expect-key-id <new-key-id>`.
5. Run the command again with `--dry-run`; require `rotate=0`, then confirm authenticated readiness reports no undecryptable secrets.
6. After all old processes are gone and the new-key backup is protected, remove `MANAGED_SECRET_PREVIOUS_KEYS`, recreate backend/workers and verify readiness again.

The command preflights every row, locks updates in bounded batches and verifies that no stale or undecryptable envelope remains. If preflight fails, restore the complete prior keyring; do not overwrite or delete the affected rows.

### Playbook execution worker

Ansible runs are claimed from a durable database queue by `playbook-execution-worker`; the web process only validates and enqueues them. Syntax checks go through the networkless `playbook-validator` Unix-socket service, so the production web process never receives the Docker socket. Actual runs use one hardened, read-only runner container per claim and a per-run subdirectory in `PLAYBOOK_RUNTIME_VOLUME_NAME`.

Keep `PLAYBOOK_EXECUTION_LEASE_SECONDS` longer than the expected heartbeat interval. `PLAYBOOK_EXECUTION_GLOBAL_CONCURRENCY` is the cluster-wide safety cap and `PLAYBOOK_EXECUTION_PER_USER_CONCURRENCY` prevents one user from consuming every slot. Additional replicas can be started with `docker compose --env-file .env.production -f docker-compose.production.yml up -d --scale playbook-execution-worker=N`. Each replica derives a unique worker key from its container hostname.

After an unclean worker stop, an expired mutating run is marked interrupted/failed and is never replayed automatically. Inspect the run, target state and audit trail before requesting an explicit rerun. Per-run variables and the optional master password are encrypted while queued and deleted after every terminal execution path.

Build `ansible-runner` and `playbook-validator` from the same `WEBTERM_ANSIBLE_IMAGE`, then force-recreate the validator after every image rebuild. Validation records the image runtime digest; execution resolves the configured reference to an immutable Docker image ID, uses `--pull=never`, and fails before remote mutation when the digest differs. The validator healthcheck performs a real Unix-socket `GET /health` and verifies this digest rather than checking only that a socket inode exists.

Every execution container is named and labeled from `(run_id, dispatch_id, attempt_count)`. Cancel, lost-lease recovery and worker shutdown remove only that exact daemon job. At worker startup, `WEBTERM_ANSIBLE_RUNTIME_ROOT` is scavenged for exact runtime directories older than `WEBTERM_ANSIBLE_RUNTIME_TTL_SECONDS` (minimum 600 seconds); symlinks, malformed names and jobs whose daemon cleanup cannot be confirmed are preserved. Treat preserved artifacts as an incident: stop new playbook claims, inspect the matching dispatch/container labels, then remove the exact container before deleting its directory.

Project-bundle upload is a release blocker whenever the bundle root resolves inside `MEDIA_ROOT`, because `/media/` is an HTTP-served namespace. Production Compose pins `PLAYBOOK_BUNDLE_STORAGE_ROOT` to the private `playbook_bundles` mount in only the backend and playbook execution worker; nginx never mounts it. The deploy check fails closed on an in-media override, and the protected backup/restore set must include this volume.

## Upgrade

1. Read `CHANGELOG.md`, migrations and support-matrix changes.
2. Export the database and persistent volumes; verify the backup is readable.
3. Pull immutable images for the target tag and record their digests.
4. Run migration and Compose-model checks in a staging copy.
5. Apply the upgrade during a declared window, run health/readiness and the primary smoke flow, then retain the previous images and backup.

### Playbook workspace migration 0047 gate

Migration `servers.0047_playbook_workspace` is a forward-only, atomic schema and data cutover. It updates historical terminal runs in one statement and performs several writes per existing playbook while creating revisions, drafts, pointers and legacy sharing grants. Do not run it as an unmeasured rolling migration on a populated database.

Before approval, stop playbook mutation producers and require zero legacy `pending`/`running` runs. Record the playbook count, total YAML bytes and run-status cardinality from the production snapshot. Restore that snapshot into an isolated staging stack, run `python manage.py migrate servers 0047 --noinput`, and record elapsed time, peak lock wait, WAL/disk growth and the post-migration counts. At minimum, capture `count(*)` plus `sum(octet_length(source_yaml))` from `servers_playbook`, status counts from `servers_playbookrun`, and after migration a left join from `servers_playbook` to `servers_playbookdraft` that proves every playbook has non-null origin/published pointers and one draft. Block the release if the rehearsal exceeds the declared maintenance/lock budget or any postcondition fails. The production cutover uses the same stopped-writer window and cardinality checks. Because the reverse operation is intentionally a no-op, recovery is the validated pre-upgrade database plus matching persistent volumes, not `migrate 0046`.

For an installation that already has files below `MEDIA_ROOT/playbook_bundles`, copy them into the private volume after mounting the new release and before re-enabling playbook traffic:

```bash
docker compose --env-file .env.production -f docker-compose.production.yml \
  exec backend python manage.py migrate_playbook_bundle_storage
docker compose --env-file .env.production -f docker-compose.production.yml \
  exec backend python manage.py migrate_playbook_bundle_storage --verify-only
```

The command is idempotent, compares source and destination bytes, refuses to overwrite a different target and never deletes the legacy source. Keep the legacy copy until the private-volume backup and restore drill pass. Nginx denies the legacy `/media/playbook_bundles/` path throughout the transition.

The automated first-release proof runs `./docker/production-upgrade-rollback-smoke.sh` for the frozen `b8924ee` schema/data snapshot and `v0.1.0-rc.1`. Exact fixture identities and the decision rules are defined in [the first-release lifecycle policy](FIRST_RELEASE_LIFECYCLE_POLICY.md).

## Rollback

1. Stop writes and record the failure time and affected operations.
2. If migrations are backward-compatible, redeploy the prior image digests.
3. If data was changed incompatibly, stop the stack and restore the pre-upgrade database/volumes before starting prior images.
4. Run health, login, inventory, terminal connection and audit checks. Document data loss or replay needs.

Application rollback does not imply database rollback. For v0.1, automatic reverse migration is disabled: keep the upgraded database only if the previous application image passes the lifecycle checks against it; otherwise restore the validated pre-upgrade database and matching secret/config/media set.

## Backup and restore

Create the PostgreSQL archive from the production project without placing a password on the command line:

```bash
BACKUP_DIR=/secure/webterm-backups \
PROJECT_NAME=mini-prod \
ENV_FILE=.env.production \
./scripts/backup_postgres.sh
```

The command emits a compressed custom-format dump plus a SHA-256 sidecar and validates the archive with `pg_restore --list` before publishing it. Back up `.env.production` and the `mini_prod_config`, `mini_prod_media` and project-scoped `playbook_bundles` volumes into the same access-controlled backup set. The environment contains encryption material and must never be attached to CI, tickets or ordinary logs. Static assets are rebuilt from the release; operational logs follow the separate retention/export policy. Plugin trust metadata lives in PostgreSQL, retained plugin package bytes live under media, and private playbook source archives live in the separate bundle volume; all corresponding archives are required for a consistent restore.

Restore only into an isolated target first:

```bash
RESTORE_CONFIRM=RESTORE_WEBTERM \
PROJECT_NAME=webterm-restore-drill \
ENV_FILE=.env.production.restore \
COMPOSE_FILE=docker-compose.production.yml \
COMPOSE_OVERRIDE_FILE=docker-compose.production.recovery.yml \
./scripts/restore_postgres.sh /secure/webterm-backups/webterm_<UTC>.dump
```

The restore command is intentionally blocked unless the explicit confirmation is present. After confirmation it force-disconnects clients, drops and recreates the named target database, and restores into that empty database; this prevents dependencies from a newer schema from contaminating an older point-in-time restore. Stop application workers before a real restore. Restore the matching secret environment and config/media/private-playbook-bundle archives, then validate authentication, managed-secret decryptability, inventory, pipelines/runs, audit chronology, plugin-package hashes and playbook-bundle hashes. Never restore over the only copy or reuse production volumes for a drill.

The repository-side F-13b proof is `./docker/production-recovery-smoke.sh`. On a fresh Linux runner it builds source state through the F-13a installer, creates a consistent PostgreSQL dump, captures secret/config/media/private-playbook-bundle/Redis state in a temporary mode-700 directory, restores into a distinct Compose project and volumes, compares privacy-safe integrity manifests, and restarts PostgreSQL and Redis. Only checksums, sizes, exact SHA, timestamps and pass/fail manifests are uploaded; the dump, environment, volume archives and credentials are deleted during cleanup.

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
- Playbook validation is unavailable: verify `playbook-validator` is healthy and its Unix-socket volume is mounted only into trusted application services that can initiate playbooks; never publish the socket to the host.
- Playbook reports a runtime mismatch: rebuild/recreate `playbook-validator` and the runner from the same image reference, confirm the validator health payload, then validate the revision again; never bypass the digest gate.
- Playbook is interrupted after a restart: review the partial remote changes and start an explicit rerun only when it is operationally safe.
- Upgrade regression: stop new writes and follow rollback; do not run ad-hoc schema edits.

Escalation, known limitations and final sign-off live in [the release checklist](V0_1_RELEASE_CHECKLIST.md).
