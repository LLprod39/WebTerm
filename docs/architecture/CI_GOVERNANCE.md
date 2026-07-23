# CI and Git governance

Last reviewed: 2026-07-22

## Current rollout state

The repository now defines complete backend/frontend/architecture/browser CI skeletons. Known-red jobs stay visible and non-required while F-04 through F-10 close their baselines. Early branch protection may require only these no-regression jobs after they have passed on the branch head:

- `Runtime Contract`
- `Documentation Contract`
- `Frontend Lock`
- `Architecture No Regression`

The full architecture job remains intentionally red until the 28 size violations and 11 forbidden import edges are removed. Its failures must not be hidden with `continue-on-error` or a larger baseline.

## Promotion path

1. Feature branches merge into `test` through pull requests.
2. `test` accumulates the complete evidence bundle and stabilization history.
3. `main` accepts only a promotion pull request from `test` with the release-scope matrix and evidence bundle linked.
4. At F-11, all product, E2E and security jobs become required and start the 14-day/30-unique-SHA stability clock.

## Protection bootstrap

`config/github-governance.json` is the versioned policy. Audit without changing GitHub:

```bash
python scripts/github_governance.py
```

Apply only after the audit is ready:

```bash
python scripts/github_governance.py --apply
```

The command refuses to protect branches until every proposed required check has succeeded on each branch head and at least two push-capable collaborators exist. This prevents a single-maintainer review deadlock. The current repository had no branch protection when F-02 started; protection is therefore not claimed until the apply command succeeds and a follow-up audit records it.

The policy enforces PR-only changes, one code-owner review, stale-review dismissal, last-push approval, conversation resolution, linear history, administrator enforcement, and disabled force pushes/deletions. There is no permanent admin bypass. A future break-glass procedure must create a durable incident record, name the reason/approver/expiry, and restore protection immediately after recovery.

## AI workflow isolation

Scheduled Gemini triage runs weekly on Monday and remains manually dispatchable. It no longer runs hourly or on workflow-file pushes/PRs. Product CI check names are independent of AI automation, so AI activity cannot satisfy or obscure release gates.
