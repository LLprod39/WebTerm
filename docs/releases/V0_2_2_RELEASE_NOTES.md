# WebTerm v0.2.2

WebTerm v0.2.2 restores the complete production install and recovery path, hardens durable operator and Studio execution, and brings the protected release gates back within their frozen architecture and frontend budgets.

## Highlights

- The production installer now starts `pipeline-execution`, waits for it, and verifies its authenticated heartbeat before completing.
- Studio readiness recognizes any healthy hostname-keyed worker replica, so production and horizontally scaled workers no longer appear missing.
- Durable operator and pipeline dispatch use PostgreSQL-safe claims, retries, reconciliation, fencing identities and execution telemetry.
- Production API, proxy, secret, worker and plugin-runner boundaries include the production-audit remediations.
- Server AI write access is explicit, while generated service-health commands remain compatible with the read-only execution policy.
- The Ashita frontend stays below the frozen CSS budget and the architecture fan-in baseline remains unchanged.
- Kubernetes Ops remains disabled in the supported production profile and frozen to its reviewed read-only boundary.

## Install or upgrade

For a new installation, download and unpack `webterm-v0.2.2-install.tar.gz` or `.zip`, copy `.env.production.example` to `.env.production`, configure the required secrets and hosts, then append the exact contents of `release-images.env`.

For an upgrade, first create and verify a PostgreSQL backup. Follow `docs-releases/OPERATIONS_RUNBOOK.md`, use the immutable image references from this release, run migrations, and keep the previous images plus backup until readiness, the pipeline worker heartbeat and guarded-action checks pass.

## Verify the release

```bash
sha256sum --check SHA256SUMS.txt
gh attestation verify release-manifest.json --repo LLprod39/WebTerm
gh attestation verify webterm-v0.2.2-install.tar.gz --repo LLprod39/WebTerm
```

Repeat attestation verification for every image digest in `release-manifest.json`. CycloneDX SBOMs for Python, frontend, the container inventory and every published image are attached to the GitHub Release.

## Scope

The supported deployment remains a controlled single-host Docker Compose pilot with PostgreSQL and Redis. Project isolation is an authorization boundary, not a claim of public multi-tenant SaaS or high-availability support. Plugin Marketplace remains fail-closed, Kubernetes Ops remains disabled and frozen to the read-only boundary, and MARS remains disabled unless its separately documented prerequisites are met.
