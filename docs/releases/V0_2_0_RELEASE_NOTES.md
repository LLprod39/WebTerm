# WebTerm v0.2.0

WebTerm v0.2.0 hardens command execution, approvals, secrets, queues and production isolation while adding project boundaries, durable Playbook execution, dry-run previews and end-to-end observability.

## Highlights

- Human approvals are authenticated, CSRF-protected, single-use, time-bounded and separated from the requester.
- AI shell execution is fail-closed and read-only by default; compound-command bypasses are covered by a dedicated regression corpus.
- Agent SSH commands and Playbook containers run through separate filtered Docker API proxies with immutable runner identities and resource limits.
- PostgreSQL queue claims use `skip_locked`, retry ceilings and fencing identities; history pruning runs outside HTTP requests.
- Managed secrets support authenticated key identifiers, HKDF derivation and online rotation.
- Project membership and active-project boundaries isolate servers, agents, playbooks, pipelines and durable runs.
- The local `mcp-demo` fixture is no longer part of the production stack or published release images.

## Install or upgrade

For a new installation, download and unpack `webterm-v0.2.0-install.tar.gz` or `.zip`, copy `.env.production.example` to `.env.production`, configure the required secrets and hosts, then append the exact contents of `release-images.env`.

For an upgrade from v0.1.0, first create and verify a PostgreSQL backup. Follow `docs-releases/OPERATIONS_RUNBOOK.md`, use the immutable image references from this release, run migrations, and keep the v0.1.0 images plus backup until the post-upgrade readiness and guarded-action checks pass.

## Verify the release

```bash
sha256sum --check SHA256SUMS.txt
gh attestation verify release-manifest.json --repo LLprod39/WebTerm
gh attestation verify webterm-v0.2.0-install.tar.gz --repo LLprod39/WebTerm
```

Repeat attestation verification for every image digest in `release-manifest.json`. CycloneDX SBOMs for Python, frontend, the container inventory and every published image are attached to the GitHub Release.

## Scope

The supported deployment remains a controlled single-host Docker Compose pilot with PostgreSQL and Redis. Project isolation is an authorization boundary, not a claim of public multi-tenant SaaS or high-availability support. Plugin Marketplace remains fail-closed, Kubernetes Ops remains frozen to the read-only release boundary, and MARS remains disabled unless its separately documented prerequisites are met.
