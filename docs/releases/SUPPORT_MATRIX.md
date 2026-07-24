# WebTerm support matrix

Last reviewed: 2026-07-22

This matrix describes the intended support boundary for the first controlled internal pilot. WebTerm is not yet declared ready for public production use.

## Runtime

| Component | Supported | Compatibility only | Unsupported for release evidence |
|---|---|---|---|
| Host development | WSL2/Linux x86_64 | Native Windows backend helper | Shared Windows/WSL virtual environment |
| Python | 3.11.15 canonical; 3.12 source-compatibility lane | — | 3.10, 3.13, 3.14 |
| Django | 5.2.16 | — | Django 6.x |
| Node.js | 22.23.1 | — | Node 20, 24 or an unpinned version |
| npm | 10.9.8 | — | `npm install` output or an unpinned npm |
| PostgreSQL | Major 16 (`postgres:16-alpine`) | — | SQLite or another major for production |
| Redis | Major 7 (`redis:7-alpine`) | — | In-memory channels/cache for production |
| Browser | Chromium from Playwright 1.58.2 | Current Chrome/Edge manual checks | A manual browser check as the only evidence |

The PostgreSQL and Redis tags still float within their major Alpine lines. Digest pinning and an explicit upgrade policy are mandatory before F-13 release closure; their current entries define compatibility, not a reproducible image identity.

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
