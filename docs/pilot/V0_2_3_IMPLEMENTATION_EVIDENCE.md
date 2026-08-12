# WebTerm v0.2.3 pilot implementation evidence

Date: 2026-08-11
Base HEAD: `91b7c531a0f9ead6e30002782046e46ce612e859`
Target: controlled single-host Linux pilot for 15-20 internal users.

## Current verdict

**NO-GO for opening the pilot.** The local candidate implementation and all
available non-deployment gates are green, including the complete Linux Python
suite and real temporary PostgreSQL/Redis concurrency tests. GO still requires
one immutable candidate commit, protected CI on that exact SHA, a clean Linux
Docker install with real Codex/Grok pilot accounts, the 20-user load scenario,
recovery/rollback evidence, the 24-hour technical canary and cohort UX
acceptance. Validation was completed before publication; commit and push to the
existing `test` branch were separately authorized on 2026-08-12. No tag,
release, pull request or deployment is implied by that authorization.

The preserved local candidate contains 304 modified tracked files and 101 new
files: 405 files total, with 22,131 insertions and 3,207 deletions in the staged
candidate. The pre-implementation inventory remains recorded separately so
these changes can be reviewed without losing or misattributing the user's
earlier work.

## Safety invariants

- Pilot users cannot auto-run agents or enable mutating tools.
- New servers and agent runs are read-only by default.
- Script materials pass the same command gate and explicit approval boundary as direct commands.
- Subscription credentials never enter the database, browser payloads, prompts, or logs.
- Provider leases are fenced; a worker that loses ownership cannot persist more events.
- Disabled optional profiles are hidden and fail closed without making core startup circular.
- Excess agent work queues durably above the 10-execution global limit.

## Traceability matrix

| Area | Required proof | Current result |
|---|---|---|
| Worktree preservation | Full tracked/untracked baseline inventory | Captured in `V0_2_3_WORKTREE_BASELINE.md` |
| Agent safety | Read-only defaults, save-only creation, script/direct SSH/SFTP/Terminal gates | Implemented and covered by the complete backend suite plus HTTP, WS, SFTP, sudo, tunnel and command-classifier regressions; only exact `pilot_operator` with `automation` can mutate a writable disposable target |
| Provider durability | Replay, fencing, cancellation, session reset | Durable terminal result/event cursor, scoped idempotency, fencing, cancel-on-lease-loss and binding reset pass SQLite and PostgreSQL regression suites |
| Provider auth | Non-blocking API, worker heartbeat, revoke/offline cleanup | `202` flow, fenced workers, fail-closed heartbeat exceptions, atomic device-code update, revoke/offline cleanup and privacy regressions pass; real provider account lifecycle remains a Linux canary gate |
| RBAC/UI | Shared capability registry and denied-request tests | Shared route/navigation registry, narrow Chat/personal/admin AI capabilities and direct-route/API denial tests pass; ordinary users do not request admin pools |
| Accessibility | WCAG AA labels, keyboard/focus, terminal screen-reader mode | Automated Axe/keyboard/reflow/navigation 11/11 and flow-dark visual baselines 30/30 pass; the terminal shows an accessible RU/EN notice for its Enter-time read-only command gate; manual NVDA/VoiceOver acceptance remains pending |
| Dependencies | Python audit with no fixable high/critical findings | All four hashed planes (`requirements.lock`, `requirements-dev.lock`, AI CLI manager and provider locks) pass isolated Linux Python 3.11 installed-environment audits with pip 26.2.1: no known vulnerabilities |
| Leaked Telegram token | Token revoked, alert resolved, integration disabled by default | Verified official Bot API rejects the exposed token with HTTP 401; GitHub alert #1 resolved as `revoked` on 2026-08-11 |
| Linux packaging | Immutable provider images and installer/profile smoke | Both expanded Compose profile configs and static installer/smoke contracts pass; live Linux builds, health, credential-volume and rollback smoke remain pending |
| Observability | Metrics, logs, traces, alerts, retention | Static metric/config contracts and six immutable image scans pass; Linux dashboard, datasource, plugin, login, trace, notification and retention smoke remains required |
| Data | PostgreSQL migrations, backup/restore, rollback | Fresh and repeat PostgreSQL 16.14 migrations/check/drift pass; encrypted backup/restore contracts pass, but live isolated full restore and application rollback remain pending |
| Capacity | 20 users, 40 submissions, 10 active, durable fair queue | Real PostgreSQL/Redis tests prove five users x two claims, global cap 10, `skip_locked`, audit/fencing and weighted routing; the required 20-user/40-job four-minute production-like load remains pending |
| UX cohort | 15-20 users, at least 90% key-task success | Pending pilot cohort |

## Release decision rule

`GO` requires a clean candidate SHA, all protected checks green on that exact SHA,
no open critical/high pilot defect, successful Linux install/recovery/load evidence,
closed leaked-token alert, and completed pilot UX acceptance. Missing external or
production-like evidence remains `NO-GO`; it is never converted to a pass by a
local SQLite or mocked-provider test.

## Observability image security evidence

The pilot Compose defaults and Security CI matrix use the same six immutable
references. Trivy `0.73.0` scanned each reference remotely with
`--scanners vuln --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1` on
2026-08-11. No skip-file, skip-directory or vulnerability exception is used.

| Component | Candidate image | Fixable high/critical |
|---|---|---:|
| OTel Collector | `otel/opentelemetry-collector-contrib:0.158.0@sha256:c5918f78992ee73b0d6f0e599423ac5ec52dd5d9726733114d6eca53d5a32ed5` | 0 |
| Prometheus | `prom/prometheus:v3.13.2-distroless@sha256:64f71bb84e03c855948418b0fc5dea53e9543d8e3fc9931598f583805507f05e` | 0 |
| Alertmanager | `quay.io/prometheus/alertmanager:main@sha256:a42c3e2e8f7cd4fd3a0ce1bd593ca5abe965c97b993476007d6f69c4a2aa33b5` | 0 |
| Grafana | `grafana/grafana:nightly-distroless-slim@sha256:b2c2fd5391216bd57e6bad74c0dce05f8e275479e1153ab57149a4f019a3dceb` | 0 |
| Tempo | `grafana/tempo:main-1a8b052-2010-1@sha256:78dc87894e9eb054b0229980ac3e7f099b437aec07a8731612373fc09b7f8ba0` | 0 |
| Loki | `grafana/loki:3.7.6@sha256:efd47c67f9bac88ca29bcf8cb997d9ab29d1848bd0aff579282295542a745952` | 0 |

Grafana and Tempo are reviewed immutable upstream snapshots, not stable release
tags. Their digests cannot drift, but this choice adds compatibility risk. They
are pilot candidates only after a real Linux smoke proves Grafana startup,
login, dashboard and datasource provisioning, the required built-in plugins,
Tempo ingestion/query and the 14-day retention configuration. A clean scan is
not a substitute for that runtime gate.

The latest compatible stable Grafana candidate was explicitly rejected, not
excepted: `grafana/grafana:13.1.3@sha256:ab5cb380e3ff3172d6c8bd2e7cfd31cce977d2881b260e1f5bc089bf0b759b43`
contained 14 fixable HIGH findings:

| Target/package | Installed | Finding | Fixed |
|---|---|---|---|
| Grafana / `github.com/grafana/tempo` | `v1.5.1-0.20260427112133-525d1bab07e0` | `CVE-2026-21728` | `2.8.4`, `2.9.2`, `2.10.2` |
| Grafana / `github.com/grafana/tempo` | same | `CVE-2026-28377` | `2.10.3` |
| Elasticsearch plugin / Go stdlib | `v1.26.3` | `CVE-2026-27145` | `1.25.11`, `1.26.4` |
| Elasticsearch plugin / Go stdlib | `v1.26.3` | `CVE-2026-39822` | `1.25.12`, `1.26.5`, `1.27.0-rc.2` |
| Elasticsearch plugin / Go stdlib | `v1.26.3` | `CVE-2026-42504` | `1.25.11`, `1.26.4` |
| Zipkin plugin / `golang.org/x/net` | `v0.49.0` | `CVE-2026-25681`, `CVE-2026-27136` | `0.55.0` |
| Zipkin plugin / `golang.org/x/net` | `v0.49.0` | `CVE-2026-33814` | `0.53.0` |
| Zipkin plugin / `golang.org/x/net` | `v0.49.0` | `CVE-2026-39821` | `0.55.0` |
| Zipkin plugin / `golang.org/x/text` | `v0.33.0` | `CVE-2026-56852` | `0.39.0` |
| Zipkin plugin / `google.golang.org/grpc` | `v1.79.3` | `GHSA-hrxh-6v49-42gf` | `1.82.1` |
| Zipkin plugin / Go stdlib | `v1.26.3` | `CVE-2026-27145`, `CVE-2026-42504` | `1.25.11`, `1.26.4` |
| Zipkin plugin / Go stdlib | `v1.26.3` | `CVE-2026-39822` | `1.25.12`, `1.26.5`, `1.27.0-rc.2` |

The Grafana binary embedded
`github.com/grafana/tempo v1.5.1-0.20260427112133-525d1bab07e0`
(`CVE-2026-21728`, fixed in `2.8.4`/`2.9.2`/`2.10.2`, and
`CVE-2026-28377`, fixed in `2.10.3`). Its bundled Elasticsearch and Zipkin
plugins also contained fixable Go standard-library findings
`CVE-2026-27145`, `CVE-2026-39822`, `CVE-2026-42504`; Zipkin additionally
contained `CVE-2026-25681`, `CVE-2026-27136`, `CVE-2026-33814`,
`CVE-2026-39821`, `CVE-2026-56852` and `GHSA-hrxh-6v49-42gf` in outdated
`x/net`, `x/text` and `grpc` libraries. The exact reproducer is:

```bash
trivy image --image-src remote --scanners vuln \
  --severity HIGH,CRITICAL --ignore-unfixed --exit-code 1 \
  grafana/grafana:13.1.3@sha256:ab5cb380e3ff3172d6c8bd2e7cfd31cce977d2881b260e1f5bc089bf0b759b43
```

Stable Tempo `3.0.2@sha256:cda87c212d8c584dc0b89e337e7ed648a5100feb657e5d528480ee4fa03dbbe3`
was likewise rejected with five fixable HIGH findings in `x/text`, `grpc` and
the Go standard library. Security CI repeats the uncompromised gate for every
candidate digest and will fail closed if the database or images change.

## Local verification snapshot

The following non-deployment checks passed on 2026-08-11 without touching live
services:

- isolated Linux Python 3.11 installed-environment audits for runtime,
  development, AI manager and AI provider locks: four times
  `No known vulnerabilities found` (pip `26.2.1`);
- complete Linux Python `3.11.15` / Django `5.2.16` backend suite:
  `2982 passed, 8 skipped` in 246 seconds with `-W error`; no warning or test
  failure remained;
- real temporary PostgreSQL `16.14` plus Redis concurrency verification:
  `46 passed, 0 skipped, 0 warnings`, followed after the final provider
  security fixes by `34 passed, 0 warnings`; fresh/repeat migrations, Django
  check and migration drift passed, the test database was removed, Redis DB 15
  was empty and the temporary server was stopped;
- provider/agent security regressions include cancel-on-heartbeat-exception,
  numeric-only usage persistence, atomic revoke/device-code fencing, binding
  session reset, direct HTTP/SFTP/Terminal denial, strict bastion validation,
  no-sudo for ordinary users and curl/nginx write-option classification;
- clean WSL frontend install on Node `22.23.1` / npm `10.9.8`: `npm ci`,
  typecheck, lint, dependency audit, `252/252` coverage tests and production
  build pass; bundle headroom is 7.376% total JS, 60.125% largest chunk and
  5.150% CSS;
- Playwright: flow-dark visual `30/30` after recording the intentional
  desktop/mobile read-only terminal notice, accessibility/navigation `11/11`,
  Agent flow `4/4` and smoke `4/4`;
- Python quality: all `1655` files pass `ruff format --check`; `ruff check`,
  Django check, migration drift, OpenAPI freshness and `git diff --check` pass;
- strict Trivy `0.73.0` scan of all six exact observability digests: zero
  fixable HIGH/CRITICAL findings;
- focused ops/backend contract tests: `52 passed`;
- production Compose config with both `ai-cli` and `observability`, and the
  corresponding smoke overlay: both pass interpolation and schema validation;
- environment contract: `360 variables`; documentation contract: `25
  documents`; release identity: `WebTerm 0.2.3`;
- CycloneDX SBOM generation: backend 115 components, frontend 774, AI manager
  14, AI provider 7 and container inventory 15;
- checksum-verified OTel Collector `0.158.0` config validation and Prometheus
  `3.13.2` config plus 19 alert rules: pass;
- scoped Ruff, Bash syntax and whitespace checks: pass.

GitHub governance was rechecked on 2026-08-11: the leaked Telegram alert is
resolved as `revoked`, `main` has strict branch protection, admin enforcement
is enabled and all 18 required check contexts are configured. The local
candidate has no commit SHA, so those checks have not yet run on this exact
tree and the stability ledger cannot start.

Docker Desktop's Linux engine was not running on this workstation
(`npipe:////./pipe/dockerDesktopLinuxEngine` was absent), so these checks do not
claim image build, inherited HEALTHCHECK, UID 10001 credential-volume restart,
Grafana/Tempo snapshot compatibility, alert delivery, encrypted backup restore,
upgrade or rollback evidence. Those remain mandatory on the dedicated Linux
stand before GO.

## Remaining mandatory GO gates

- Create a reviewed immutable candidate commit only after separate permission,
  then run all 18 required checks and the new pilot gates on that exact SHA.
- On the dedicated Linux host, build/pull every pinned image and prove inherited
  healthchecks, manager ordering, UID 10001 credential-volume write/restart/
  cleanup, egress denial and Grafana/Tempo snapshot compatibility.
- Use separate Codex and Grok pilot accounts for login, reconnect, restart,
  cancel, quota/outage, revoke and emergency offline cleanup.
- Run 20 users x two 60-second jobs with at most 10 active executions, no loss
  or duplicate, control API p95 <=500 ms and queue drain <=4 minutes.
- Prove notification delivery, end-to-end trace, encrypted full restore,
  upgrade and rollback; then complete the 24-hour operator canary.
- Complete the 15-20 participant UX script with at least 90% key-task success
  and manual screen-reader acceptance before changing this verdict to GO.
