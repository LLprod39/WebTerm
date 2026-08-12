# WebTerm v0.2.3

`v0.2.3` is a local controlled-pilot candidate for a dedicated Linux Docker
Compose host. It has not been tagged, published, deployed or approved for GO,
and it does not claim public multi-tenant availability or HA.

## Pilot changes

- Codex and Grok subscription runners are separate, immutable release images.
- The AI CLI profile is disabled by default and requires explicit installer
  enablement, a private manager token and five digest-pinned images.
- Fresh credential volumes are initialized for UID/GID `10001:10001`; the
  release smoke verifies write, restart and cleanup behavior.
- The backend container healthcheck uses core readiness, avoiding a startup
  dependency cycle while the default readiness endpoint still gates enabled AI
  workers and the runner manager.
- The optional observability profile bundles OpenTelemetry Collector,
  Prometheus, Alertmanager, Grafana, Tempo and Loki. Metrics retain 30 days;
  traces, alerts and sanitized metadata-only logs retain 14 days. The
  notification webhook is supplied through a protected file, never Compose
  environment output.
- Grafana and Tempo use reviewed immutable upstream snapshots because their
  compatible stable images failed the fixable-HIGH image gate. They remain
  pilot-only and require dashboard, datasource, plugin, login, trace and
  retention smoke on Linux before GO.
- Nightly age-encrypted backups cover PostgreSQL plus media, runtime config and
  private playbook bundles. AI credentials and telemetry are excluded and the
  weekly timer validates both encrypted restore streams without changing data.
- Telegram remains disabled unless the installer is invoked with an explicitly
  provisioned token and `--with-telegram-bot`.
- Python locks include the security fixes in `aiohttp 3.14.3` and
  `cryptography 50.0.0`.

## Required release evidence

The tag is eligible only after the exact candidate SHA passes Security,
backend/frontend, Playwright, production install, AI CLI profile, recovery and
upgrade/rollback checks. Real Codex/Grok device authentication, provider quota
behavior and the 20-user/40-job load scenario remain staging gates and cannot
be inferred from the image smoke.
