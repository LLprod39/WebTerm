# WebTerm v0.1 release checklist

Status: final pass is established by the signed `v0.1.0` Release workflow
Target: production release

All commands run from a clean Linux/WSL2 checkout at the release-candidate commit. Activate `.venv-wsl`, install `requirements-dev.lock` with hashes, and use Node 22.23.1/npm 10.9.8. The release is production-ready only when the tag workflow publishes immutable images and the signed release assets after its published-digest production and Playwright smoke succeeds.

Published evidence anchors:

- Tag `v0.1.0` resolves to commit [`4317126`](https://github.com/LLprod39/WebTerm/commit/4317126fd5cb325bb076d63952a9b5fe14caaa59), whose protected required checks completed successfully on 2026-07-24.
- [Release workflow run 30103632944](https://github.com/LLprod39/WebTerm/actions/runs/30103632944) built and attested six immutable images, passed the published-digest production and Playwright smoke, and published the signed assets.
- [GitHub Release `v0.1.0`](https://github.com/LLprod39/WebTerm/releases/tag/v0.1.0) contains install bundles, checksums, manifest, provenance, attestations and CycloneDX SBOMs.
- Changes after `v0.1.0`, including the 2026-07-29 security hardening, are promoted through the protected [hardening pull request](https://github.com/LLprod39/WebTerm/pull/26) and the separate [v0.2 release checklist](V0_2_RELEASE_CHECKLIST.md). This file remains the historical evidence contract for `v0.1.0`.

| Gate | Exact command | Expected artifact | Current state |
|---|---|---|---|
| Runtime contract | `python scripts/verify_runtime_contract.py` | successful command record | `v0.1.0`: passed required `Runtime Contract`; current candidate must pass it again. |
| Release identity | `python scripts/verify_release_identity.py` | synchronized brand/version command record | `v0.1.0`: passed required `Documentation Contract`; current candidate must pass it again. |
| Documentation contract | `python scripts/verify_docs_contract.py` | link and required-document report | `v0.1.0`: passed required `Documentation Contract`; current candidate must pass it again. |
| Public API contract | `python -m pytest tests/test_public_api_v0_1_contract.py` | route inventory test report | `v0.1.0`: passed in the required backend suite; current candidate must pass it again. |
| Locked Python install | `python -m pip install --require-hashes -r requirements-dev.lock` | installer log and tool versions | `v0.1.0`: locked installs passed across required Python jobs. |
| Locked frontend install | `cd frontend && npm ci` | installer log | `v0.1.0`: passed `Frontend Lock`, unit, build and Playwright jobs. |
| Architecture sizes | `python scripts/check_architecture_sizes.py --strict-new` | command log/report | `v0.1.0`: passed required `Architecture No Regression`; current candidate must pass it again. |
| Import boundaries | `lint-imports --config .importlinter` | command log | `v0.1.0`: passed required `God-file & Import Boundary Checks`; current candidate must pass it again. |
| Backend lint | `ruff check .` and `ruff format --check .` | machine-readable lint artifact or log | `v0.1.0`: passed required `Python Quality`; current candidate must pass it again. |
| Backend tests | `python -m pytest --junitxml=.ci-artifacts/backend-junit.xml` | `backend-junit.xml`, zero failures/errors | `v0.1.0`: passed required `Backend Unit and Coverage`; current candidate must pass it again. |
| Backend coverage | `python -m pytest --cov=app --cov=core_ui --cov=servers --cov=studio --cov=kubernetes_ops --cov=plugin_marketplace --cov=mars --cov=web_ui --cov-report=xml:.ci-artifacts/backend-coverage.xml --cov-fail-under=80` | `backend-coverage.xml` | `v0.1.0`: passed the 80% required coverage gate; current candidate must pass it again. |
| Django system check | `python manage.py check` | command log | `v0.1.0`: passed required `Django Checks`; current candidate must pass it again. |
| Production deploy check | `DJANGO_SETTINGS_MODULE=web_ui.settings.production python manage.py check --deploy` with CI-only strong secrets and explicit hosts | command log, zero errors | `v0.1.0`: passed required `Production Checks`; current candidate must pass it again. |
| Clean production install | `./docker/production-install-smoke.sh` on the `Production Install Smoke` Ubuntu runner | exact SHA/host versions, Compose state/images/logs, migration/deploy/readiness/worker/Celery/runtime smoke artifacts | `v0.1.0`: clean-install smoke passed before tagging and again against published image digests. |
| Playbook durable worker | `python manage.py run_playbook_execution_plane --once --worker-key release-check` plus restart/cancel/lease tests | queue claim, heartbeat, terminal cleanup and no-auto-replay evidence | `v0.1.0`: lifecycle tests and production runtime smoke passed; later workspace changes remain unreleased. |
| Playbook isolated runtime | controller-policy exploit tests, `tests/test_ansible_docker_runtime.py`, `tests/test_ansible_validator_server.py`, and Compose validator/runner smoke | immutable image/runtime digest parity, exact claim labels and daemon cleanup, bounded networkless validator without supplementary root groups, crash-artifact scavenging, hardened per-run container and strict host keys | `v0.1.0`: validator/runtime tests, immutable image publication and production smoke passed. |
| Playbook private bundle storage | Set `PLAYBOOK_BUNDLE_STORAGE_ROOT` to a dedicated shared volume outside `MEDIA_ROOT`; mount it only into backend and playbook workers; prove `/media/` cannot retrieve a stored bundle | inaccessible HTTP probe plus backend/worker read-write smoke and backup evidence | `v0.1.0`: storage-boundary tests, clean install and isolated recovery passed. |
| Frontend lint | `cd frontend && npm run lint` | lint log, zero errors | `v0.1.0`: passed required `Frontend Typecheck and Lint`; current candidate must pass it again. |
| Frontend typecheck | `cd frontend && npm run typecheck` | typecheck log | `v0.1.0`: passed required `Frontend Typecheck and Lint`; current candidate must pass it again. |
| Frontend unit tests | `cd frontend && npm run test:coverage` | JUnit and coverage artifact | `v0.1.0`: passed required `Frontend Unit and Coverage`; current candidate must pass it again. |
| Frontend build | `cd frontend && npm run build:budget` | build log, budget artifact and `dist` manifest/hash | `v0.1.0`: passed required `Frontend Production Build`; current candidate must pass it again. |
| Browser E2E | `cd frontend && npm run test:e2e:smoke` | Playwright HTML report, traces on failure | `v0.1.0`: passed required `Playwright Smoke` and the published-digest release flow. |
| Accessibility | `cd frontend && npm run test:e2e:a11y` | Playwright/axe report with zero serious/critical WCAG 2 A/AA violations | `v0.1.0`: passed inside required `Playwright Smoke`; current candidate must pass it again. |
| Performance | `cd frontend && npm run build:budget && npm run performance:budget && npm run test:e2e:performance` | bundle, Lighthouse and interaction-latency JSON artifacts | `v0.1.0`: passed inside required frontend build and `Playwright Smoke`; current candidate must pass them again. |
| UX release evidence | Release workflow published-digest Playwright flow plus `npm run test:e2e:a11y`, Lighthouse and production runtime smoke; post-release cohort evidence remains verifiable with `python scripts/verify_pilot_ux_results.py path/to/pilot-results.json --output .ci-artifacts/pilot-ux-verification.json` | authenticated readiness/navigation proof, WCAG report, performance budget and guarded runtime trace | Automated release evidence passed for `v0.1.0`; the human cohort remains explicitly post-release product feedback, not fabricated release evidence. |
| Security scan | repository-wide approved scanner command from F-03/F-10 | SARIF/report and finding ledger | `v0.1.0`: dependency audits, secrets/security tests and supply-chain checks passed. The later 2026-07-29 sealed review and remediation belong to the v0.2 evidence set. |
| Dependency inventory | SBOM command frozen in F-10 | CycloneDX or SPDX SBOM | `v0.1.0`: CycloneDX source, container and per-image SBOMs are published release assets. |
| Backup/restore | `./docker/production-recovery-smoke.sh` on the `Production Recovery Smoke` Ubuntu runner | archive checksums/sizes, source/restored/restarted integrity manifests, Redis recovery and exact-SHA summary; no secret artifacts | `v0.1.0`: required `Isolated Backup Restore and Restart Recovery` passed on the release commit. |
| Upgrade/rollback | `./docker/production-upgrade-rollback-smoke.sh` for frozen `b8924ee` and `v0.1.0-rc.1` fixtures | immutable migration report, migration plans, application rollback health/integrity and separate DB restore integrity | `v0.1.0`: both frozen-fixture upgrade/rollback jobs passed on the release commit. |
| Primary demo | terminal/pipeline/agent production runtime smoke in F-13a; human script in `docs/pilot/PILOT_UX_SCRIPT_V1.md` | install → add server → guarded action → audit trace | `v0.1.0`: automated production and published-digest flows passed; real pilot observations remain post-release evidence. |

## Evidence bundle

CI writes a JSON file with actual command names, exact command strings, integer exit codes and tool versions. Example:

```json
{
  "commands": [
    {
      "name": "runtime-contract",
      "command": "python scripts/verify_runtime_contract.py",
      "exit_code": 0,
      "tool_versions": {
        "python": "3.11.15"
      }
    }
  ]
}
```

After all commands have run on a clean commit, record the artifacts:

```bash
python scripts/collect_release_evidence.py \
  --command-results .ci-artifacts/command-results.json \
  --artifact backend-junit=.ci-artifacts/backend-junit.xml \
  --artifact backend-coverage=.ci-artifacts/backend-coverage.xml \
  --artifact playwright-report=frontend/playwright-report/index.html \
  --config runtime-lock=requirements.lock \
  --config dev-lock=requirements-dev.lock \
  --config frontend-lock=frontend/package-lock.json \
  --config release-scope=docs/releases/V0_1_RELEASE_SCOPE.md \
  --ci-run-url "$CI_RUN_URL"
```

The bundle always says `release_decision: NOT_EVALUATED`. A named reviewer must separately record the release decision after checking the bundle, security ledger, recovery proof and scope matrix.
