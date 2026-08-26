# Third-Party Notices

Last reviewed: 2026-08-25
Plan ID: F-10 (GER-19)

This file records third-party software notices for WebTerm **before any RoutineOps / upstream agent-plane reuse** (competitive plan D0 / F-10 gate).

It is a **governance record**, not a substitute for full license texts shipped with dependencies, container layers, or future Go agent binaries.

## Project license

WebTerm source in this repository is licensed under the **Apache License 2.0**. See root `LICENSE`.

## How notices are maintained

| Layer | Inventory source | SBOM generator |
| --- | --- | --- |
| Python backend | `requirements-mini.txt`, `requirements-dev.lock` | `scripts/generate_sbom.py` → CycloneDX JSON |
| Frontend (npm) | `frontend/package.json`, `frontend/package-lock.json` | `scripts/generate_sbom.py` → CycloneDX JSON |
| Containers | Dockerfiles under `docker/` | Optional Syft/CycloneDX in CI when images are built |
| Future Go agent | Not vendored in Stage 1 | Deferred until agent code is introduced |

Release builds must attach the generated SBOMs and checksums (see `SECURITY.md` and `.github/workflows/security.yml`).

## Major third-party components (summary)

The lists below are **representative** runtime/build components. Complete component lists live in generated SBOMs; do not treat this table as exhaustive.

### Backend (Python)

| Component | Typical use | License (as commonly published) |
| --- | --- | --- |
| Django | Web framework | BSD-3-Clause |
| Django Channels / Daphne | ASGI / WebSockets | BSD-3-Clause |
| channels-redis | Channel layer | BSD-3-Clause |
| psycopg | PostgreSQL driver | LGPL-3.0 (binary) / LGPL |
| Redis client stack | Cache / broker | MIT |
| Celery | Background tasks | BSD-3-Clause |
| cryptography | Crypto primitives | Apache-2.0 / BSD |
| asyncssh | SSH client | EPL-2.0 |
| pydantic | Schemas | MIT |
| httpx / requests | HTTP clients | BSD-3-Clause / Apache-2.0 |
| ruff / pytest (dev) | Lint / tests | MIT |

Exact versions and hashes: `requirements-dev.lock` (production-ish install uses the locked graph in CI).

### Frontend (npm)

| Component | Typical use | License (as commonly published) |
| --- | --- | --- |
| React / React DOM | UI | MIT |
| Vite | Build | MIT |
| TypeScript | Types | Apache-2.0 |
| Tailwind CSS | Styling | MIT |
| Radix UI primitives | Accessible widgets | MIT |
| TanStack Query | Data fetching | MIT |
| CodeMirror packages | Editors | MIT |
| xterm.js addons | Terminal | MIT |
| ESLint / Vitest / Playwright (dev) | Quality / e2e | MIT |

Exact versions: `frontend/package-lock.json`.

### Self-hosted frontend fonts

These font files are vendored as static WOFF2 assets for the opt-in `enterprise-light` UI style. Their license texts are shipped beside the assets.

| Component | Version / distribution | Typical use | License | Local license text |
| --- | --- | --- | --- | --- |
| IBM Plex Sans (`@ibm/plex`) | 6.4.1 | Interface and display typography | SIL Open Font License 1.1 (OFL-1.1) | `frontend/public/fonts/ibm-plex-sans/OFL.txt` |
| JetBrains Mono | 2.304 | Technical values and monospace UI | SIL Open Font License 1.1 (OFL-1.1) | `frontend/public/fonts/jetbrains-mono/OFL.txt` |

### Containers and system packages

Container images built from `docker/*.Dockerfile` also include OS packages from the base image distribution. Those packages are covered by their distribution licenses and must appear in the **container SBOM** for a published release image. Stage 1 scaffolding generates application-layer SBOMs first; image-layer SBOMs are required for the `v0.1.0` artifact gate.

## RoutineOps / competitive upstream

No RoutineOps (or related private/upstream agent) source is vendored in this tree as of this notice date.

Before any code reuse:

1. Record provenance in this file (source URI, commit/tag, license).
2. Keep license text copies where required by the upstream license.
3. Do not treat enterprise-only seams in external trees as available for copy without legal review (see competitive plan D0).

## Attribution obligation

If you redistribute WebTerm binaries, images, or install bundles, include:

- this `THIRD_PARTY_NOTICES.md` (or a generated equivalent);
- Apache-2.0 `LICENSE` for WebTerm itself;
- the bundled font license texts under `frontend/public/fonts/` when those font assets are included;
- the release SBOM set and checksum file for that build.

## Updates

Update this file when:

- adding a dependency with a **non-Apache / non-MIT / non-BSD** license;
- adding or replacing a self-hosted font or other redistributed static asset;
- vendoring external source trees;
- publishing the first container release that includes new base OS packages.

Automated SBOM generation does **not** remove the need to review license compatibility for new major dependencies.
