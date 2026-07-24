# WebTerm v0.1 release checklist

Status: not passed
Target: controlled internal pilot

All commands run from a clean Linux/WSL2 checkout at the release-candidate commit. Activate `.venv-wsl`, install `requirements-dev.lock` with hashes, and use Node 22.23.1/npm 10.9.8. Until every mandatory row has an artifact and reviewer, WebTerm must not be described as production-ready.

| Gate | Exact command | Expected artifact | Current state |
|---|---|---|---|
| Runtime contract | `python scripts/verify_runtime_contract.py` | successful command record | Implemented; green on `test` commit `389c6ac`, RC proof pending |
| Release identity | `python scripts/verify_release_identity.py` | synchronized brand/version command record | Green on `test` commit `695c6d8`; RC proof pending |
| Documentation contract | `python scripts/verify_docs_contract.py` | link and required-document report | Green on `test` commit `695c6d8`; RC proof pending |
| Public API contract | `python -m pytest tests/test_public_api_v0_1_contract.py` | route inventory test report | Green on `test` commit `695c6d8`; RC proof pending |
| Locked Python install | `python -m pip install --require-hashes -r requirements-dev.lock` | installer log and tool versions | Lock implemented; clean CI proof pending |
| Locked frontend install | `cd frontend && npm ci` | installer log | Pending proof |
| Architecture sizes | `python scripts/check_architecture_sizes.py --strict-new` | command log/report | Zero violations; green on `test` commit `389c6ac`, RC proof pending |
| Import boundaries | `lint-imports --config .importlinter` | command log | Green on `test` commit `389c6ac`, RC proof pending |
| Backend lint | `ruff check .` | machine-readable lint artifact or log | Green on `test` commit `389c6ac`, RC proof pending |
| Backend tests | `python -m pytest --junitxml=.ci-artifacts/backend-junit.xml` | `backend-junit.xml`, zero failures/errors | F-04 worktree proof: 2,175 passed, 3 integration skips; clean RC/CI proof pending |
| Backend coverage | `python -m pytest --cov=app --cov=core_ui --cov=servers --cov=studio --cov=kubernetes_ops --cov=plugin_marketplace --cov=mars --cov=web_ui --cov-report=xml:.ci-artifacts/backend-coverage.xml --cov-fail-under=80` | `backend-coverage.xml` | Pending F-06; scope follows matrix |
| Django system check | `python manage.py check` | command log | Locked worktree pass; clean RC/CI proof pending |
| Production deploy check | `DJANGO_SETTINGS_MODULE=web_ui.settings.production python manage.py check --deploy` with CI-only strong secrets and explicit hosts | command log, zero errors | Locked worktree pass; plugin routes/providers confirmed absent; clean RC/CI proof pending |
| Clean production install | `./docker/production-install-smoke.sh` on the `Production Install Smoke` Ubuntu runner | exact SHA/host versions, Compose state/images/logs, migration/deploy/readiness/worker/Celery/runtime smoke artifacts | Green on `test` commit `3e98e6c`; RC proof pending |
| Playbook durable worker | `python manage.py run_playbook_execution_plane --once --worker-key release-check` plus restart/cancel/lease tests | queue claim, heartbeat, terminal cleanup and no-auto-replay evidence | Implemented in worktree; clean RC/CI proof pending |
| Frontend lint | `cd frontend && npm run lint` | lint log, zero errors | Green on `test` commit `389c6ac`, RC proof pending |
| Frontend typecheck | `cd frontend && npm run typecheck` | typecheck log | Green on `test` commit `389c6ac`, RC proof pending |
| Frontend unit tests | `cd frontend && npm run test:coverage` | JUnit and coverage artifact | 115 tests green on `test` commit `695c6d8`; Stage 1 coverage target pending |
| Frontend build | `cd frontend && npm run build:budget` | build log, budget artifact and `dist` manifest/hash | Green on `test` commit `695c6d8`, RC proof pending |
| Browser E2E | `cd frontend && npm run test:e2e:smoke` | Playwright HTML report, traces on failure | Four smoke flows green on `test` commit `695c6d8`; production terminal/pipeline/agent runtime smoke is enforced separately by F-13a |
| Accessibility | `cd frontend && npm run test:e2e:a11y` | Playwright/axe report with zero serious/critical WCAG 2 A/AA violations | Seven critical flows green on `test` commit `695c6d8`; RC proof pending |
| Performance | `cd frontend && npm run build:budget && npm run performance:budget && npm run test:e2e:performance` | bundle, Lighthouse and interaction-latency JSON artifacts | Implemented in F-12 worktree; CI proof pending |
| Pilot UX | `python scripts/verify_pilot_ux_results.py path/to/pilot-results.json --output .ci-artifacts/pilot-ux-verification.json` | privacy-safe participant results and derived gate report | Validator implemented; real >=10-participant evidence pending |
| Security scan | repository-wide approved scanner command from F-03/F-10 | SARIF/report and finding ledger | Pending F-03/F-10 |
| Dependency inventory | SBOM command frozen in F-10 | CycloneDX or SPDX SBOM | Pending F-10 |
| Backup/restore | `./docker/production-recovery-smoke.sh` on the `Production Recovery Smoke` Ubuntu runner | archive checksums/sizes, source/restored/restarted integrity manifests, Redis recovery and exact-SHA summary; no secret artifacts | F-13b workflow implemented; first green run and RC proof pending |
| Upgrade/rollback | `./docker/production-upgrade-rollback-smoke.sh` for frozen `b8924ee` and `v0.1.0-rc.1` fixtures | immutable migration report, migration plans, application rollback health/integrity and separate DB restore integrity | F-13c workflow implemented; first green two-fixture run and RC proof pending |
| Primary demo | terminal/pipeline/agent production runtime smoke in F-13a; human script in `docs/releases/V0_1_PILOT_UX_SCRIPT.md` | install → add server → guarded action → audit trace | Automated production flow green on `test` commit `3e98e6c`; real pilot evidence pending |

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
