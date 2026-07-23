# Security Policy

Last reviewed: 2026-07-23  
Plan ID: F-10 (GER-19)

This document is the formal security process for WebTerm / WebTrerm Stage 1.

## Supported versions

| Version / channel | Supported for security fixes | Notes |
| --- | --- | --- |
| `main` (pre-`v0.1.0`) | Yes | Active development line for Stage 1 |
| GitHub Release `v0.1.x` (when published) | Yes | Only tagged releases receive backported Critical/High fixes |
| Unreleased feature branches | Best-effort | Fix on the branch or after merge; no SLA |
| Forks / private copies | No | Operators of forks own their patch process |

Until the first public `v0.1.0` tag exists, treat **the latest `main` commit that passes required CI** as the only supported pre-release line.

## Reporting a vulnerability

**Do not** open a public GitHub issue for exploitable vulnerabilities.

Prefer one of:

1. **Private GitHub Security Advisory** on [LLprod39/WebTerm](https://github.com/LLprod39/WebTerm) (preferred when available).
2. **Email** the maintainers listed in the repository owner org / `CODEOWNERS` (when present) with:
   - affected version or commit SHA;
   - impact and attack scenario;
   - minimal reproduction steps;
   - whether you plan public disclosure and on what timeline.

Include only the minimum sensitive data needed for triage. Never send production secrets, customer data, or live credentials.

## Response SLA

Target response times from **confirmed receipt** of a valid report:

| Severity | First response | Status update | Fix or formal risk acceptance |
| --- | --- | --- | --- |
| Critical | 2 business days | every 3 business days | 14 calendar days |
| High | 3 business days | weekly | 30 calendar days |
| Medium | 5 business days | bi-weekly | next minor release window |
| Low / informational | 10 business days | as needed | backlog |

Severity uses common sense CVSS-like impact on confidentiality, integrity, and availability for a **self-hosted internal ops** deployment (not multi-tenant public SaaS — see `docs/releases/SUPPORT_MATRIX.md` when present, otherwise support assumptions in the competitive plan).

If a Critical/High finding cannot be fixed inside the SLA, it must be recorded as a **formal risk acceptance** with:

- owner;
- expiry date;
- compensating control;
- release-scope decision (in-scope High cannot ship unresolved without acceptance, and acceptance does **not** make an out-of-scope feature GA).

Ledger: `security/FINDINGS_LEDGER.md`.

## Security scope for Stage 1

In release scope we care about:

- authentication / session / CSRF boundaries;
- SSH host-key trust and command execution policy;
- WebSocket authorization;
- agent and Studio pipeline execution policy;
- MCP egress and redaction;
- plugin trust and sandbox;
- managed secrets never appearing in frontend payloads, logs, reports, memory, or LLM prompts;
- Kubernetes admin mode fail-closed controls;
- dependency Critical/High findings (npm / Python);
- release artifact SBOM, checksums, and provenance attestations.

Out-of-scope High findings require formal risk acceptance (owner + expiry + control).

## Coordinated disclosure

We ask reporters to:

- give us time consistent with the SLA above before public disclosure;
- avoid testing against systems you do not operate;
- not exfiltrate data beyond what is needed to prove impact.

We will credit reporters who want credit, unless anonymity is requested.

## Development security rules (summary)

- Never commit secrets, private keys, or production `.env` files.
- Prefer redaction helpers: `app/egress_redaction.py`, `app/core/redacted_logging.py`.
- Mutation APIs need authorization plus negative tests (denied permission, wrong owner, redaction, audit, approval, idempotent retry, timeout/error, rollback where applicable).
- See also: `security/THREAT_MODEL.md`, `security/FINDINGS_LEDGER.md`, and local-only notes under `docs/local/` when present.

## Verification commands

```bash
# Python dependency audit (CI security job uses the same idea)
python -m pip install pip-audit
python -m pip_audit --local

# Frontend dependency audit
cd frontend && npm ci && npm audit --audit-level=high

# SBOM + checksums + provenance (local = unsigned scaffold)
python scripts/generate_sbom.py --output-dir .ci-artifacts/sbom
# Optional image-layer SBOM when Syft/Trivy is installed:
# python scripts/generate_sbom.py --output-dir .ci-artifacts/sbom --image ghcr.io/org/app@sha256:…
python scripts/generate_release_checksums.py --input-dir .ci-artifacts/sbom --output .ci-artifacts/checksums/SHA256SUMS.txt
python scripts/generate_provenance.py --artifacts-dir .ci-artifacts/sbom --checksums .ci-artifacts/checksums --output .ci-artifacts/provenance/provenance.intoto.json
```

CI (`.github/workflows/security.yml`) additionally signs SBOM/checksum/provenance subjects with **GitHub artifact attestations** (Sigstore). After a green run:

```bash
gh attestation verify .ci-artifacts/sbom/sbom-backend.cdx.json --repo <owner/repo>
```

Generated artifacts under `.ci-artifacts/` are evidence, not a release approval.
