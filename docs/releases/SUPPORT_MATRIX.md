# WebTerm support matrix

Last reviewed: 2026-07-29

This matrix describes the intended support boundary for the first controlled internal pilot. WebTerm is not yet declared ready for public production use.

## Runtime

| Component | Supported | Compatibility only | Unsupported for release evidence |
|---|---|---|---|
| Host development | WSL2/Linux x86_64 | Native Windows backend helper | Shared Windows/WSL virtual environment |
| Python | 3.11.15 canonical; 3.12 source-compatibility lane | — | 3.10, 3.13, 3.14 |
| Django | 5.2.16 | — | Django 6.x |
| Node.js | 22.23.1 | — | Node 20, 24 or an unpinned version |
| npm | 10.9.8 | — | `npm install` output or an unpinned npm |
| PostgreSQL | Major 16 (`postgres:16-alpine@sha256:57c72fd2a128e416c7fcc499958864df5301e940bca0a56f58fddf30ffc07777`) | — | SQLite, another major, or a tag-only image for production |
| Redis | Major 7 (`redis:7-alpine@sha256:e7723ff73d963f5cc6d9c4643ea3d989527a402a319239054e9472a7fb9219a2`) | — | In-memory channels/cache or a tag-only image for production |
| nginx | 1.27 Alpine (`nginx:1.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10`) | — | A tag-only reverse-proxy image for production |
| Browser | Chromium from Playwright 1.58.2 | Current Chrome/Edge manual checks | A manual browser check as the only evidence |

Production Compose keeps the human-readable compatibility tag but resolves PostgreSQL, Redis and nginx by the exact multi-architecture manifest digest above. Updating one of these images requires a reviewed change that resolves the official tag again, updates both Compose and this matrix, and passes the production install plus upgrade/rollback recovery smokes before release. Tag-only image references are compatibility hints and must never replace the release-bound digests.

The exact decision and enforcement rules are in [ADR-0001](../architecture/adr/0001-primary-runtime-and-toolchain.md).

## Deployment

| Shape | Pilot status | Conditions |
|---|---|---|
| Single Linux host, Docker Compose, PostgreSQL and Redis | Target supported shape | All v0.1 checklist gates, TLS reverse proxy, backup/restore proof and operator runbook |
| WSL2 local development | Supported for development | `.venv-wsl`, pinned locks, local-only endpoints |
| Native Windows backend | Compatibility only | Separate `.venv-windows`; not release evidence |
| SQLite | Development/test only | Never a production claim |
| Multi-worker / high availability | Not supported in v0.1 | Requires concurrency, failover and recovery qualification |
| Kubernetes deployment of WebTerm itself | Not supported in v0.1 | The Kubernetes Ops feature does not imply WebTerm deployment support on Kubernetes |
| Public multi-tenant SaaS | Not supported | Requires tenancy isolation, abuse controls, SLOs and a separate threat model |

## Pilot operating boundary

- Audience: a controlled internal group with named operators.
- Infrastructure: operator-owned servers and clusters only.
- Scale: established by load evidence before release; no scale number is claimed yet.
- Secrets: production encryption key and strong Django secret are mandatory.
- Recovery: database backup/restore and Redis/session recovery evidence are mandatory.
- Optional domains marked `preview` carry no availability guarantee.
- Domains marked `disabled` must be inaccessible in both navigation and backend policy, not merely hidden in the UI.
