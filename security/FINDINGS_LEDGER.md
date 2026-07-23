# Security Findings Ledger

Last reviewed: 2026-07-24  
Plan ID: F-10 (GER-19)  
Related: F-03 (GER-5) initial scan gate

This ledger tracks **repository-wide** security findings for Stage 1 release scope.  
Unresolved **Critical/High in release scope** block release. Out-of-scope High requires formal risk acceptance.

## Severity model

| Level | Meaning |
| --- | --- |
| Critical | Remote exploit or credential compromise with high blast radius |
| High | Significant confidentiality/integrity impact under realistic attacker model |
| Medium | Limited impact or hard preconditions |
| Low | Defense-in-depth / hygiene |

## Status values

`open` · `fixed` · `accepted` · `out_of_scope` · `false_positive`

## Formal risk acceptance fields (required when status=`accepted`)

- **owner**
- **expiry** (ISO date)
- **compensating_control**
- **release_impact** (`blocks_ga` | `feature_not_ga` | `documented_only`)

---

## Dependency scans (F-10 baseline)

### Scan commands

```bash
# Authoritative: project env after hashed lock install (not global site-packages)
python -m pip install --require-hashes -r requirements-dev.lock
python -m pip_audit --local
cd frontend && npm ci && npm audit --audit-level=high
```

### Record — 2026-07-23 (re-verified 2026-07-24)

| ID | Source | Finding | Severity | Status | Owner | Notes |
| --- | --- | --- | --- | --- | --- | --- |
| DEP-NPM-001 | npm audit | `brace-expansion` GHSA-3jxr-9vmj-r5cp (DoS) | High | **fixed** | platform | Fixed via `npm audit fix` → brace-expansion 1.1.16 / 2.1.2 |
| DEP-NPM-002 | npm audit | `form-data` GHSA-hmw2-7cc7-3qxx (CRLF injection) | High | **fixed** | platform | Fixed via form-data 4.0.6 (jsdom transitive) |
| DEP-NPM-003 | npm audit | `js-yaml` GHSA-52cp-r559-cp3m (ReDoS-ish CPU) | High | **fixed** | platform | Fixed via js-yaml 4.3.0 (eslint transitive) |
| DEP-PY-001 | pip-audit --local | (none at F-10 baseline after hashed install of app lock) | — | **fixed** / clean | platform | CI installs `requirements-dev.lock` then `pip-audit --local`; global/user site-packages are not release evidence |
| DEP-PY-002 | pip-audit --local (CI runner) | `setuptools` 79.0.1 PYSEC-2026-3447 (runner bootstrap, not app lock) | High | **fixed** | platform | Not in `requirements-dev.lock`. CI `security.yml` upgrades `setuptools>=83.0.0` before audit |
| DEP-NPM-004 | npm audit | `react-router` / `react-router-dom` GHSA-wrjc-x8rr-h8h6, GHSA-337j-9hxr-rhxg | Medium | **open** | platform | Fixed only in 7.18.x major line; staying on `^6.30.1` until deliberate RR v7 migration. CI gate is `--audit-level=high` (does not fail Stage 1) |

**Post-remediation verification**

| Command | Result | When |
| --- | --- | --- |
| `cd frontend && npm audit --audit-level=high` | 0 high/critical (2 moderate react-router — DEP-NPM-004) | 2026-07-24 |
| `.venv` / CI `python -m pip_audit --local` after lock install | No known vulnerabilities found (authoritative path) | 2026-07-24 |
| Global `python -m pip_audit --local` (user site-packages) | **Not release evidence** — may report hundreds of unrelated findings | 2026-07-24 |

> Note: `pip-audit -r requirements-dev.lock` may fail in `--require-hashes` dry-run mode when transitive extras are incomplete. CI uses `pip install --require-hashes` then `pip-audit --local` (or equivalent installed-set audit) for a deterministic signal.

---

## Application / process findings (from F-03 / security Q&A)

| ID | Area | Finding | Severity | Status | Owner | Expiry | Compensating control | Release impact |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| APP-001 | Server shares | Server share checks not fully capability-based (view/connect/execute/file-write/admin) | High | **accepted** | platform | 2026-10-23 | Ownership + feature permissions + explicit share records; new APIs must not broaden “any accessible server” | `feature_not_ga` for fine-grained multi-user share matrix |
| APP-002 | Execution policy | Execution policy not fully unified across terminal / agents / Studio | High | **accepted** | platform | 2026-10-23 | Safety classifiers + Studio policy engine + approvals on high-risk nodes; negative tests on k8s/agent mutations | `feature_not_ga` for full unified policy product claim |
| APP-003 | Egress redaction | Redaction not proven at every possible egress point | High | **accepted** | platform | 2026-10-23 | Canonical helpers `app/egress_redaction.py`; tests for AI events, activity logs, prompt sanitization, k8s redaction | `documented_only` + required tests for new egress |
| APP-004 | Secret encryption | Versioned credential encryption migration still recommended | Medium | open | platform | — | OS/file permissions; never log secrets; no secrets in frontend | does not alone block Stage 1 if DEP clean |
| APP-005 | MCP SSRF | Outbound MCP/webhook destination allowlist incomplete | Medium | open | platform | — | Admin-only MCP ops; network egress controls at deploy | operators must firewall |
| APP-006 | Live SSH | Live SSH cannot be fully validated by unit tests | Medium | **accepted** | platform | 2027-01-23 | Unit/integration mocks + manual smoke + production stack smoke scripts | `documented_only` |
| APP-007 | Supply chain docs | Missing formal SECURITY.md / SBOM / provenance (pre-F-10) | High | **fixed** | platform | — | SECURITY.md, THIRD_PARTY_NOTICES.md, SBOM/checksum/provenance scripts + security CI workflow | resolved by F-10 scaffold |
| SUPPLY-001 | Provenance signing | Release artifacts lacked signed provenance | High | **fixed** | platform | — | CI job `sbom-provenance` uses `actions/attest-build-provenance` (OIDC/Sigstore); local generators default to `unsigned_scaffold` | verify: `gh attestation verify` after CI |
| SUPPLY-002 | Image-layer SBOM | Only Dockerfile inventory, no layer SBOM on digests | Medium | **open** | platform | — | `generate_sbom.py --image` + `IMAGE_SBOM_REFS` repo var when Syft/Trivy available; release jobs should pass immutable digests | does not block Stage 1 app/deps gates |

---

## Mutation API negative-test matrix (release scope)

Representative suites (not exhaustive — add rows when new mutation surfaces ship):

| Surface | Denied perm | Wrong owner | Redaction | Audit | Approval | Idempotent retry | Timeout/error | Rollback |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| K8s action request lifecycle | yes (`test_kubernetes_ops_action_lifecycle`) | yes | yes | yes | yes | partial | partial | n/a / blocked execute |
| K8s admin actions | yes | yes (`non_owner_cannot_read…`) | yes | yes | policy | partial | partial | n/a |
| Core UI staff mutations | yes | n/a | activity redaction tests | yes | n/a | n/a | n/a | n/a |
| Agent/pipeline policy | policy deny | ownership via server share | egress redaction | policy audit metadata | approvals where configured | retry semantics in engine | error states | recovery paths partial |
| Secrets-never contract | — | — | `tests/test_security_secrets_never.py` | — | — | — | — | — |

Gaps marked **partial** are tracked as APP-002 / APP-003; they do not re-open fixed dependency Highs.

---

## How to add a finding

1. Assign `ID` (`DEP-*`, `APP-*`, `SUPPLY-*`).
2. Set severity and **release scope** (in / out).
3. If High/Critical and not fixed before release: fill risk acceptance fields.
4. Link verifying command or test path.
5. Never paste live secrets into this file.
