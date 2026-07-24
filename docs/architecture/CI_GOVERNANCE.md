# CI and Git governance

Last reviewed: 2026-07-24  
Policy version: **F-11**

## Goal

All product and severity CI jobs are **required** on protected branches (`test`, `main`). Merging with a red or missing required check is impossible for everyone, including administrators, unless a **logged break-glass** incident is opened and protection is restored afterward.

After required-check promotion is applied, the **F-11 protected release evidence** gate starts. It has no calendar waiting window and closes on a protected green release SHA.

## Required checks (F-11)

Exact GitHub check-run names (job `name:` fields):

### Backend CI
- `Runtime Contract`
- `Python Quality`
- `Django Checks`
- `Backend Unit and Coverage`
- `PostgreSQL and Redis Integration`
- `Production Checks`
- `Documentation Contract`

### Frontend CI
- `Frontend Lock`
- `Frontend Typecheck and Lint`
- `Frontend Unit and Coverage`
- `Frontend Production Build`

### Architecture Fitness
- `Architecture No Regression`
- `God-file & Import Boundary Checks`

### Playwright Smoke
- `Playwright Smoke` (runs on every PR/push to `test`/`main` — no path filter — so the required context always appears)

### Security baseline
- `Python dependency audit`
- `npm dependency audit`
- `SBOM, checksums, provenance`
- `Secrets-never and security unit tests`

Versioned source of truth: `config/github-governance.json`.

## Branch protection rules

Applied by `python scripts/github_governance.py --apply` only when safe:

| Rule | Value |
| --- | --- |
| PR required | yes |
| Approving reviews | 1 |
| CODEOWNERS review | required |
| Dismiss stale reviews | yes |
| Last push approval | yes |
| Conversation resolution | required |
| Linear history | required |
| Force pushes / deletions | denied |
| **Enforce admins** | **true** (no silent admin bypass of checks) |
| Required status checks | strict, full F-11 list above |

### Break-glass (admin merge without green checks)

There is **no permanent** admin bypass. Emergency path:

1. Log the incident first:
   ```bash
   python scripts/github_governance.py --break-glass \
     --reason "..." --approver "..." --expiry "..." \
     --incident-url "https://..." --opened-by "..."
   ```
2. Temporarily relax only what is needed in GitHub (admin).
3. Complete the emergency change.
4. Immediately restore policy:
   ```bash
   python scripts/github_governance.py --apply
   ```
5. Close the log entry with evidence:
   ```bash
   python scripts/github_governance.py --close-break-glass bg-0001 \
     --restored-evidence-url "https://..."
   ```

Durable log: `config/break-glass-log.json`.

## Protected release evidence (no calendar waiting window)

| Gate | Rule |
| --- | --- |
| Calendar | **0 days**; there is no artificial waiting window |
| Unique SHA | At least **1** protected release commit SHA with **all** required checks green |
| Reruns | Rerunning workflows on the **same SHA does not** increase the unique-SHA count |
| Eligible runs | merge-candidate / scheduled / push / PR / workflow_dispatch on `test` and `main` |
| Start moment | First successful `--apply` of F-11 protection; stored as `clock.startedAt` + `clock.startedCommit` |

Clock fields live in `config/github-governance.json` under `clock`.  
Unique-SHA ledger: `config/ci-stability-ledger.json`.

### Commands

```bash
# Audit heads + current protection (no GitHub mutation)
python scripts/github_governance.py

# Apply protection + start clock (refuses if required checks are not green on heads)
python scripts/github_governance.py --apply

# Release evidence status
python scripts/github_governance.py --clock-status
python scripts/ci_stability_clock.py

# Sync unique green SHAs from GitHub Actions (idempotent; reruns ignored)
python scripts/github_governance.py --sync-unique-shas

# Manually record one green SHA
python scripts/github_governance.py --record-sha <full_or_prefix_sha> --branch main --event push
```

### Closing GER-14 / F-11

Close Linear issue GER-14 when `readyToCloseF11` is true:

```text
calendarGateMet == true AND uniqueShaGateMet == true
```

The gate can close immediately after branch protection is applied and the release SHA is green; no calendar delay is required.

## CI duration budget

Stage 1 acceptance: CI **p95 ≤ 15 minutes** for merge-candidate product workflows (sharding allowed without dropping coverage). Measure from the last 30 merge-candidate runs after the clock starts; record in release evidence, not by disabling required checks.

## Promotion path

1. Feature branches → `test` via PR (all required checks green).
2. `test` produces green release evidence for the candidate SHA.
3. `main` accepts only a promotion PR from `test` with release-scope evidence.
4. F-11 required checks and release-SHA evidence must be green before Stage 2 and v0.1.0 gates that depend on it (F-12, F-13*).

## AI workflow isolation

Gemini triage/review workflows are **not** required product gates. Their check names must never replace backend/frontend/architecture/Playwright/security evidence.

## Bootstrap safety

`scripts/github_governance.py` refuses to apply protection when:

- fewer than two push-capable collaborators exist (review deadlock risk), or
- any required check has not succeeded on the current `test`/`main` head.

Until apply succeeds, branch protection must not be claimed as active.
