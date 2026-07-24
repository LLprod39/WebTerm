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

- Back up PostgreSQL with a consistent database dump and back up persistent media/config volumes separately.
- Store encryption material and managed-secret keys in an access-controlled secret system; a database backup without the matching keys may be unusable.
- Test restoration into an isolated environment. Validate row counts, authentication, server inventory and audit chronology.
- Never overwrite the only backup during a restore test.

## Disaster recovery

1. Declare the incident and freeze automated actions.
2. Recreate a supported host from pinned infrastructure configuration.
3. Restore secrets, database and persistent volumes; deploy recorded image digests.
4. Rotate credentials that may have been exposed.
5. Run the release smoke flow and reconcile queued/running operations before reopening access.

Recovery-time and recovery-point objectives are not claimed until F-13c completes a timed restore drill with retained evidence.

## Troubleshooting

- `docker compose ... config --quiet` failing: compare `.env.production` with the example and remove unresolved placeholders.
- Health failing: inspect backend, PostgreSQL and Redis health before restarting; preserve logs and timestamps.
- Login works but features are denied: inspect the server-generated access payload and role assignments.
- Terminal or guarded action failing: verify host reachability, host-key policy, approval state and audit event creation.
- Upgrade regression: stop new writes and follow rollback; do not run ad-hoc schema edits.

Escalation, known limitations and final sign-off live in [the release checklist](V0_1_RELEASE_CHECKLIST.md).
