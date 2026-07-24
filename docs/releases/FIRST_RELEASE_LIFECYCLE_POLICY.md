# v0.1 first-release upgrade and rollback policy

Status: controlled-pilot release gate. This policy does not authorize a public release.

## Frozen fixtures

| Fixture | Immutable commit | Purpose |
|---|---|---|
| Schema/data snapshot | `b8924eeb1bcfd0647e80615eaa8c7684828e517a` | Proves the longest supported first-release migration path from the plan baseline. |
| `v0.1.0-rc.1` | `5c522e3d34ecdeb85d31853e9e16b7f0134532af` | Proves the final RC-to-target lifecycle and prevents a moving branch from being used as a fixture. |

The tag must resolve to the exact commit above. `scripts/verify_migration_history.py` rejects modifications, deletions or renames of numbered migrations already present in either fixture; only new numbered migration files are allowed.

## Required pre-upgrade state

1. Freeze new mutations and record the start time, current image IDs/digests and exact Git SHA.
2. Run the readiness and worker checks for the currently deployed fixture.
3. Create and validate a custom-format PostgreSQL dump with `scripts/backup_postgres.sh`.
4. Back up the matching secret environment, config/media volumes and retained plugin package bytes. Keep these secret artifacts outside CI artifacts and ordinary logs.
5. Do not start the upgrade if the backup checksum or archive validation fails.

## Upgrade decision

Apply migrations forward with the target application image. The migration plan, command result and privacy-safe business integrity manifest are retained as evidence. Authentication, managed-secret decryptability, server inventory and pipelines must remain intact.

Historical migration files are immutable after they enter either fixture. A behavior or state change that would otherwise require editing one is represented by a new migration. Data migrations must provide a data-preserving reverse function or be classified as restore/forward-fix only before merge.

## Application rollback versus database recovery

These are separate actions:

- **Application rollback** redeploys the previous application image against the already-upgraded database. It is allowed only when that exact image passes health, authentication, managed-secret and critical-object checks against the upgraded schema.
- **Database recovery** restores the pre-upgrade dump and matching secret/config/media set. It is mandatory when the previous application cannot safely use the upgraded schema, when an irreversible/data-loss migration ran, or when post-upgrade integrity differs.
- **Automatic reverse migration is disabled for v0.1.** Do not use an ad-hoc `migrate <old target>` as rollback evidence. A reverse migration may be introduced later only after an explicit data-preservation review and a dedicated restore rehearsal.
- **Forward fix** is preferred after a successful, compatible schema upgrade when the current application defect can be corrected without risking stored data. The failed image remains blocked until the fix passes the same lifecycle workflow.

The automated drill first deploys the fixture application against the upgraded schema and proves its health and business integrity. It then separately restores the pre-upgrade database and proves the fixture state again. This ordering demonstrates that application rollback never silently pretends to reverse database changes.

## Evidence and commands

Repository proof:

```bash
F13C_FIXTURE_NAME=schema-snapshot-b8924ee \
F13C_FIXTURE_REF=b8924eeb1bcfd0647e80615eaa8c7684828e517a \
F13C_EXPECTED_FIXTURE_SHA=b8924eeb1bcfd0647e80615eaa8c7684828e517a \
./docker/production-upgrade-rollback-smoke.sh
```

CI runs the same command for both frozen fixtures. It retains exact fixture/target SHAs, local image IDs, migration history and plans, upgrade/restore timings, health results and matching integrity manifests. Database dumps, secret environments, credentials and volume archives are always temporary and are deleted during cleanup.

The drill proves lifecycle correctness but does not establish an RTO/RPO. A production target requires a separately approved timed disaster-recovery exercise.
