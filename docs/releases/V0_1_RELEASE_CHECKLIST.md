# WebTerm v0.1 release checklist

Status: not passed
Target: controlled internal pilot

All commands run from a clean Linux/WSL2 checkout at the release-candidate commit. Activate `.venv-wsl`, install `requirements-dev.lock` with hashes, and use Node 22.23.1/npm 10.9.8. Until every mandatory row has an artifact and reviewer, WebTerm must not be described as production-ready.

| Gate | Exact command | Expected artifact | Current state |
|---|---|---|---|
| Runtime contract | `python scripts/verify_runtime_contract.py` | successful command record | Implemented; CI wiring pending |
| Locked Python install | `python -m pip install --require-hashes -r requirements-dev.lock` | installer log and tool versions | Lock implemented; clean CI proof pending |
| Locked frontend install | `cd frontend && npm ci` | installer log | Pending proof |
| Architecture sizes | `python scripts/check_architecture_sizes.py --strict-new` | command log/report | Failing baseline; must reach zero |
| Import boundaries | `lint-imports --config .importlinter` | command log | Failing baseline; must reach zero |
| Backend lint | `ruff check .` | machine-readable lint artifact or log | Pending F-06 |
| Backend tests | `python -m pytest --junitxml=.ci-artifacts/backend-junit.xml` | `backend-junit.xml`, zero failures/errors | F-04 worktree proof: 2,175 passed, 3 integration skips; clean RC/CI proof pending |
| Backend coverage | `python -m pytest --cov=app --cov=core_ui --cov=servers --cov=studio --cov=kubernetes_ops --cov=plugin_marketplace --cov=mars --cov=web_ui --cov-report=xml:.ci-artifacts/backend-coverage.xml --cov-fail-under=80` | `backend-coverage.xml` | Pending F-06; scope follows matrix |
| Django system check | `python manage.py check` | command log | Locked worktree pass; clean RC/CI proof pending |
| Production deploy check | `DJANGO_SETTINGS_MODULE=web_ui.settings.production python manage.py check --deploy` with CI-only strong secrets and explicit hosts | command log, zero errors | Locked worktree pass; plugin routes/providers confirmed absent; clean RC/CI proof pending |
| Frontend lint | `cd frontend && npm run lint` | lint log, zero errors | Pending F-06 |
| Frontend typecheck | `cd frontend && npm run typecheck` | typecheck log | Locked worktree pass; clean RC/CI proof pending |
| Frontend unit tests | `cd frontend && npm test -- --coverage` | JUnit and coverage artifact | Coverage wiring pending F-06 |
| Frontend build | `cd frontend && npm run build` | build log and `dist` manifest/hash | Pending locked proof |
| Browser E2E | `cd frontend && npm run test:e2e` | Playwright HTML report, traces on failure | Pending F-05/F-11 |
| Accessibility | `cd frontend && npm run test:e2e:a11y` | Playwright/axe report | Pending F-11 |
| Security scan | repository-wide approved scanner command from F-03/F-10 | SARIF/report and finding ledger | Pending F-03/F-10 |
| Dependency inventory | SBOM command frozen in F-10 | CycloneDX or SPDX SBOM | Pending F-10 |
| Backup/restore | command set frozen in F-13b | restore log plus integrity checks | Pending F-13b |
| Upgrade/rollback | command set frozen in F-13c | migration, application rollback and DB recovery report | Pending F-13c |
| Primary demo | Playwright pilot flow frozen in F-13a | install → add server → guarded action → audit trace | Pending F-13a |

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
