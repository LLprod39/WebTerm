# WebTerm v0.1.0

First production release of the Stage 1 foundation: durable Ansible Playbook Workspace, guarded execution, recovery-safe PostgreSQL upgrades, hardened production Compose, and signed supply-chain evidence.

## Install

1. Download and unpack `webterm-v0.1.0-install.tar.gz` or `.zip`.
2. Copy `.env.production.example` to `.env.production`, fill the required secrets and deployment hosts, then append the exact contents of `release-images.env`.
3. Run `./docker/install-production.sh --env-file .env.production --compose-file docker-compose.production.yml --pull --no-build`.

The exact commit and immutable GHCR references are in `release-manifest.json`. The release workflow runs the production runtime smoke and Playwright against those digest references before this release is created.

## Verify

```bash
sha256sum --check SHA256SUMS.txt
gh attestation verify release-manifest.json --repo LLprod39/WebTerm
gh attestation verify webterm-v0.1.0-install.tar.gz --repo LLprod39/WebTerm
gh attestation verify oci://ghcr.io/llprod39/webterm-backend@sha256:<digest> --repo LLprod39/WebTerm
syft ghcr.io/llprod39/webterm-backend@sha256:<digest> -o cyclonedx-json
```

Repeat the image attestation command for every digest in `release-manifest.json`. CycloneDX SBOMs for the Python, frontend, container inventory, and every published image are attached to the release.

## Operational scope

Read the bundled support matrix, operations runbook, upgrade/rollback policy, and release scope before production deployment. Plugin Marketplace remains fail-closed in the v0.1 production profile unless explicitly enabled by a later supported release.
