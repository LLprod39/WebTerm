# WebTerm v0.2 release checklist

Status: release candidate until the protected `test` commit, `v0.2.1` tag workflow, published-image smoke and signed assets are all verified.

## Protected candidate gates

- Runtime and documentation contracts: `python scripts/verify_runtime_contract.py`, `python scripts/verify_release_identity.py`, `python scripts/verify_docs_contract.py`.
- Architecture: `python scripts/check_architecture_sizes.py --strict-new` and `lint-imports --config .importlinter`.
- Backend: `ruff check .`, `ruff format --check .`, the full PostgreSQL pytest suite and coverage ratchet.
- Django: normal checks, migration drift and production `check --deploy`.
- Frontend: `npm ci`, `npm run typecheck`, lint, unit coverage and production build budgets.
- Browser: `npm run test:e2e:smoke`, accessibility, `npm run performance:budget` and `npm run test:e2e:performance`.
- Production: `./docker/production-install-smoke.sh`, isolated backup/restore, and upgrade/rollback from the frozen v0.1 fixtures.
- Security: dependency audits, secrets-never tests, SBOM and provenance checks.
- Pilot evidence remains independently verifiable with `python scripts/verify_pilot_ux_results.py` and is never fabricated by CI.
- Evidence collection remains non-approving: `python scripts/collect_release_evidence.py`.

## v0.2-specific gates

- Approval requests: token redaction, authenticated GET confirmation page, CSRF POST, TTL, replay resistance and approver/requester separation.
- Command execution: fail-closed classifier and at least 50 compound-command bypass cases.
- Production isolation: non-root backend, filtered Playbook and agent Docker APIs, immutable runner images and resource limits.
- PostgreSQL queues: four concurrent `skip_locked` claims, retry ceiling, fencing and global-capacity preservation.
- Project tenancy: membership activation and cross-project resource/link rejection.
- Mutation preview: every registered mutating SSH/ops node declares dry-run support and returns a redacted diff without mutation.
- Observability: queue metrics plus one trace from HTTP enqueue through the worker to the ephemeral SSH command.
- Release contents: `mcp-demo` is absent from production Compose, installer, image matrix, manifest and release environment.

## Publication gates

1. Tag `v0.2.1` must resolve to the exact protected `test` candidate and match `VERSION`.
2. Every image job must publish an immutable digest and GitHub provenance attestation.
3. Published-digest production and Playwright smoke must pass before the release job starts.
4. `SHA256SUMS.txt` must validate every uploaded asset.
5. `release-manifest.json`, install archives, SBOMs and image digests must have verifiable GitHub attestations.
6. Only then may GitHub Release `v0.2.1` be marked latest.
