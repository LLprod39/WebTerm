# WebTerm competitive engineering baseline

Captured: 2026-07-22
WebTerm commit: `b8924eeb1bcfd0647e80615eaa8c7684828e517a` (`test`)
RoutineOps comparison commit: `8453023fd248e538b81abcd0203b7cdbc9879833`

This report freezes the starting point for `WEBTERM_ROUTINEOPS_COMPETITIVE_PLAN.md`. It is not a release-readiness certificate. Results obtained from an unpinned or unsupported local runtime are marked provisional.

## Starting position

| Area | Frozen observation | Evidence class | Required closure |
|---|---|---|---|
| Product breadth | WebTerm contains SSH/SFTP, inventory, monitoring, playbooks, agents, Studio pipelines, MCP, plugins, Kubernetes and MARS domains | repository inspection | Preserve breadth while freezing v0.1 scope |
| Architecture | Strict size guard reports 28 violations; import boundary check reports 11 forbidden `core_ui -> servers` paths | live repository guard | Zero violations without raising baselines |
| Backend tests | Observed run: 2,159 passed and 7 failed | provisional; old WSL environment was not clean/pinned | Re-run from Python 3.11 dev lock; zero failures/errors |
| Frontend dependency install | `npm ci` was blocked by package/lock drift at baseline | live baseline | Keep package/lock synchronized and prove clean install |
| Frontend dependency audit | Pinned npm 10.9.8 reports 3 transitive High findings (`brace-expansion`, `form-data`, `js-yaml`), 0 Critical | clean pinned F-01 environment | Remediate and record audit/SBOM evidence in F-10 |
| CI | Existing workflows did not provide the complete backend/frontend/lint/coverage gate set; recent architecture and browser checks were not green | repository/GitHub inspection | Hardened CI plus required branch checks |
| Production checks | Plugin marketplace production checks were known blockers | live deploy-check history | Fail closed or provide real signing/scanning/isolation prerequisites |
| Release process | No frozen scope matrix, support matrix, evidence bundle or published v0.1 release | repository inspection | Implement F-01 through F-13c |
| Runtime contract | Python range, Docker images, local environments and Node/npm were inconsistent | repository inspection | ADR-0001 and automatic verifier |

## F-01 changes from the baseline

- Python compatibility is `>=3.11,<3.13`; the canonical image is Python 3.11.15 and Django is locked to 5.2.16.
- Node.js/npm are pinned to 22.23.1/10.9.8 across package metadata, Docker and the browser workflow.
- A clean `npm ci` now succeeds with the pinned Node/npm pair; dependency security findings remain open and are not hidden by that success.
- Production and development dependency locks are separated; the dev lock is constrained to the exact production runtime.
- WSL and native Windows use different virtual environments; only the locked Linux/WSL path can provide release evidence.
- The v0.1 scope and support boundary are explicit.
- Release evidence collection refuses a dirty tree and cannot approve a release.

## F-02 measured CI baseline

The first pinned frontend CI rehearsal produced these reproducible results on Node 22.23.1/npm 10.9.8:

| Gate | Result |
|---|---|
| Clean `npm ci` | PASS; 662 packages installed |
| TypeScript `tsc --noEmit` | PASS |
| ESLint `--max-warnings 0` | FAIL; 69 warnings, 0 errors |
| Vitest with coverage | FAIL; 3 files failed, 8 tests failed, 100 passed, 6 unhandled errors |
| Production Vite build | PASS; 4,429 modules transformed |
| Frozen bundle budget | PASS; 4,687,999 JavaScript bytes total, largest chunk 979,344 bytes, 219,798 CSS bytes |
| npm dependency audit | FAIL; 3 transitive High, 0 Critical |

The backend system check and migration-drift check pass in the locked Python 3.11.15 environment. The complete backend suite, PostgreSQL/Redis lane and production deploy check remain separate CI evidence gates; they are not inferred from these focused checks.

## F-04/F-04b closure evidence

- The complete locked backend suite now collects 2,178 tests and finishes with
  2,175 passed, 3 explicitly environment-gated integration tests skipped, and
  zero failures/errors. JUnit is written to
  `.ci-artifacts/f04-backend-junit.xml`.
- Monitoring status/dashboard now share the configured 300-second metrics trust
  contract. A configured-but-unavailable Redis client correctly falls back to
  the Django cache for both writes and reads.
- Unknown terminal execution modes fail safe to `step`; known Nova/agent aliases
  remain explicit. Ollama JSON/free-text option precedence and Grok system prompt
  forwarding have direct contract tests.
- The v0.1 production profile defaults
  `PLUGIN_MARKETPLACE_RELEASE_MODE=disabled`. In this mode plugin execution
  providers and `/api/plugins/` routes are absent and the UI capability is false.
  `manage.py check --deploy` passes with zero issues without fake plugin signing,
  scanner or allowlist configuration.

These are implementation/worktree results, not clean release-candidate evidence.
The PostgreSQL/Redis integration lane, CI run and later security/release gates
remain mandatory.

## Truthful current conclusion

WebTerm is still a stabilization candidate with broader functionality than RoutineOps, not yet the stronger released product. F-01 makes the comparison measurable and prevents unsupported local results from being presented as readiness. The competitive conclusion changes only after later stages close CI, test, architecture, security, UX, recovery and release gates with reproducible evidence.
