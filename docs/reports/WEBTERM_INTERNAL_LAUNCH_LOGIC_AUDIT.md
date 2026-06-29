# WebTrerm Internal Launch Logic Audit

Date: 2026-06-29
Scope: product behavior after the stack is already running. This is not a Docker/deployment audit; it covers settings, secrets, access, onboarding, and operational UX for the first internal company rollout.

## Implementation Progress

Completed in this audit pass:

- Production/runtime env hardening: `MODEL_CONFIG_PATH`, `NOTIFICATION_CONFIG_PATH`, runtime config volume, required production secret placeholders, SSL/LDAP placeholder handling.
- Settings/admin guards: access-management APIs and model refresh are staff-protected.
- Domain auth read path: web-saved SSO settings now honor `MODEL_CONFIG_PATH`.
- Notification secret storage: Telegram bot token and SMTP password now write to `ManagedSecret`; notification JSON keeps only non-secret values.
- First-run web readiness: added `/api/settings/readiness/` and `/settings/readiness`.
- Settings notifications entrypoint: added `/settings/notifications`, while keeping `/studio/notifications`.
- Server secret UX logic: managed server secrets can be revealed by the owner without requiring legacy `MASTER_PASSWORD`; server details expose storage mode.
- LDAP env/startup status is visible on the SSO settings page and in readiness.
- `/servers` frontend routes now use the same `servers` feature gate as the backend API.
- Pilot access profiles were added: `operator_server_only`, `operator_studio_runner`, `team_admin_no_secrets`, `platform_admin`; staff toggles now warn about broad default access.
- `/api/settings/check/` now checks selected provider routing instead of hard-coded Gemini/Grok keys.
- Added a safe dry-run-first command for legacy server secret migration into `ManagedSecret`.
- Added audit logging presets: Pilot, Strict, Debug.
- Added admin-tunable runtime limits and LLM budget settings under `/settings/limits`.
- Added browser-visible frontend demo-mode readiness check.

Known follow-ups after this pass:

- Per-team/group budgets and usage graphs after the pilot has real traffic.
- Marketplace mode UX (`local-only`, `private-catalog`, `remote-install-enabled`).

## Executive Summary

WebTrerm is close to usable for an internal pilot, but the current setup still expects too much knowledge from the first admin. The product already has the right primitives: feature access gates, `ManagedSecret`, AI provider settings, Studio notifications, audit logs, and readiness checks. The missing layer is a clear "first-run control plane" in the web UI that says what is configured, what is missing, and which values are safe to edit after deployment.

The strongest direction is: keep only infrastructure-critical values in env, then move product/integration secrets into web-managed encrypted storage. In practice, `.env.production` should bootstrap the app with database, Redis, host/security, `DJANGO_SECRET_KEY`, and `MANAGED_SECRET_KEY`; after that, admins should configure AI keys, notification channels, SSO/domain behavior, server credentials, MCP secrets, and plugin secrets from the web UI.

## Recommended Settings Model

Keep in env only:

- `DJANGO_SECRET_KEY`, `MANAGED_SECRET_KEY`
- database and Redis connection settings
- public host/origin/security settings: `SITE_URL`, `ALLOWED_HOSTS`, `CSRF_TRUSTED_ORIGINS`, HTTPS/proxy flags
- low-level runtime topology: worker limits, bind ports, filesystem paths, Docker/MARS runtime switches
- optional external infrastructure endpoints that must exist before Django starts

Move or keep in web settings:

- LLM provider API keys and provider routing
- SMTP and Telegram notification credentials
- SSO/domain behavior that does not require process-level auth backend changes
- server SSH passwords, sudo passwords, private key passphrases
- MCP secret env values
- plugin secret bindings
- budgets, quotas, retention, audit flags, and user-facing limits

Do not move to ordinary web settings:

- `MANAGED_SECRET_KEY` itself. If this changes, existing encrypted records can become unreadable.
- `DJANGO_SECRET_KEY`.
- database password and Redis URL.
- production hostname/security flags that Django needs before serving requests.

## Problem Zones

### P1 - Domain Auth Read Path Was Inconsistent

Status: fixed in this audit.

`core_ui.domain_auth` loaded `.model_config.json` directly, while production now uses `MODEL_CONFIG_PATH`. That meant SSO settings saved through the web UI could be written to one file while middleware read another. I changed the middleware to load through `model_manager`, so it honors `MODEL_CONFIG_PATH`.

Files:

- `core_ui/domain_auth.py`
- `app/core/model_config.py`
- `tests/test_settings_admin_guards.py`

### P1 - No Single First-Run Readiness Screen

Status: fixed in this audit.

Current state after fix:

- `/settings` now redirects to `/settings/readiness`.
- Backend endpoint: `GET /api/settings/readiness/`.
- The readiness report is staff-only and `settings`-gated.
- It checks deployment mode, placeholder secrets, managed-secret health, persisted config paths, selected AI providers, notifications, SSO, server secret storage, access admins, runtime limits, Studio workers, and Plugin Marketplace deploy checks.

Files:

- `core_ui/views/settings_readiness_views.py`
- `core_ui/urls.py`
- `frontend/src/pages/settings/SettingsReadinessPage.tsx`
- `frontend/src/api/settings.ts`
- `frontend/src/components/settings/settings-nav-items.ts`
- `frontend/src/App.tsx`
- `frontend/src/lib/api-demo-server-admin.ts`

Remaining improvement:

- Add a real browser-visible `VITE_ENABLE_DEMO_MODE` status. Backend cannot reliably see Vite build env at runtime.
- Add last successful test timestamps for AI, SMTP, Telegram, LDAP, and Marketplace external services.

### P1 - Notification Secrets Are File-Based, Not ManagedSecret-Based

Status: fixed in this audit.

Current state after fix:

- AI keys use `ManagedSecret`.
- Server passwords use `ManagedSecret`.
- MCP env secrets use `ManagedSecret`.
- Studio notification secrets now use `ManagedSecret` namespace `notification_secret`.
- `telegram_bot_token` and `smtp_password` are no longer written to notification JSON.
- Legacy JSON secrets are still read as fallback; the next web save removes them from the JSON file.
- `NOTIFICATION_CONFIG_PATH` was added for persistent non-secret notification config.

Files:

- `core_ui/managed_secrets.py`
- `core_ui/services/notification_config.py`
- `tests/test_studio_api_smoke.py`
- `.dockerignore`
- `.env.production.example`
- `docker-compose.production.yml`

Remaining improvement:

- Consider moving non-secret notification config from JSON into a first-class DB settings model later.

### P1 - Master Password Is Now Legacy, But UI Still Treats It As Central

Status: partially fixed in this audit.

Current state after fix:

- New server auth/sudo secrets are stored in `ManagedSecret`.
- Legacy encrypted fields still use `MASTER_PASSWORD`.
- Terminal connection can resolve managed server secrets without master password.
- Password reveal endpoint now requires `MASTER_PASSWORD` only for legacy `encrypted_password` records.
- Server details now expose `password_storage_mode` and `sudo_password_storage_mode`: `managed`, `legacy_master_password`, or `none`.
- Added `python manage.py migrate_legacy_server_secrets` for dry-run/apply migration from legacy encrypted fields into `ManagedSecret`.

Files:

- `servers/secret_utils.py`
- `servers/views/server_crud.py`
- `servers/management/commands/migrate_legacy_server_secrets.py`
- `frontend/src/api/servers.ts`

Remaining improvement:

- Add a small UI hint in the server security tab when a server is still in legacy master-password mode.

### P1 - Settings Surface Is Split Across Settings And Studio

Status: fixed in this audit.

Current state after fix:

- AI is under `/settings/ai`.
- Access/SSO/audit/plugins are under `/settings`.
- Notifications are available under `/settings/notifications`.
- Existing `/studio/notifications` deep link is preserved.

Files:

- `frontend/src/App.tsx`
- `frontend/src/components/settings/settings-nav-items.ts`
- `frontend/src/pages/NotificationsSettingsPage.tsx`

### P2 - SSO Page Mentions LDAP, But LDAP Is Env-Only

Status: fixed in this audit.

Current state after fix:

- `SettingsSSOPage` configures header-based domain auth.
- LDAP backend settings remain env-only in `web_ui/settings/auth.py`.
- `GET /api/settings/` returns a redacted `ldap_status`.
- `GET /api/settings/readiness/` includes `ldap_login`.
- SSO page shows a read-only LDAP Login panel: enabled/backend loaded/server/search base/bind credentials/TLS policy/missing env.

Files:

- `core_ui/services/settings_status.py`
- `core_ui/views/settings_config_views.py`
- `web_ui/services/settings_readiness_config.py`
- `frontend/src/pages/settings/LdapStatusPanel.tsx`
- `frontend/src/pages/settings/SettingsSSOPage.tsx`

Remaining improvement:

- Add an actual LDAP bind/search test button later, but keep enable/disable env-only until there is a safe restart story.

### P2 - Feature Routing Has One UI/Backend Mismatch

Status: fixed in this audit.

Current state after fix:

- Backend gates server APIs with `require_feature("servers")`.
- Frontend routes `/servers`, `/servers/hub`, and `/servers/:id/terminal` are wrapped in `FeatureGate feature="servers"`.

Files:

- `frontend/src/App.tsx`

### P2 - Staff Defaults Are Broad

Status: partially fixed in this audit.

Current state after fix:

- Staff users get every feature by default except explicit opt-in features (`mars`, `kubernetes`).
- Access-management endpoints now require staff.
- Built-in pilot profiles exist:
  - `operator_server_only`
  - `operator_studio_runner`
  - `team_admin_no_secrets`
  - `platform_admin`
- Create/edit user UI warns when `is_staff` is enabled.
- Domain SSO auto-created users use the same profile semantics as the Settings UI.

Files:

- `core_ui/access.py`
- `core_ui/views/access_views.py`
- `core_ui/domain_auth.py`
- `core_ui/views/settings_config_views.py`
- `frontend/src/lib/accessUiText.ts`
- `frontend/src/pages/settings-users/CreateUserSidebar.tsx`
- `frontend/src/pages/settings-users/UserDirectory.tsx`
- `frontend/src/pages/settings-users/userValidation.ts`
- `frontend/src/pages/settings/SettingsSSOPage.tsx`

Remaining improvement:

- Keep `is_staff` for platform admins, not as a general "manager" flag.

### P2 - AI Provider Setup Is Good, But Needs A Safer Default Flow

Status: partially fixed in this audit.

Current state after fix:

- Web UI can save LLM API keys into `ManagedSecret`.
- Provider routing can set chat/agent/orchestrator providers separately.
- Model refresh is now staff/settings-only.
- `GET /api/settings/check/` now checks selected `default`, `internal`, `chat`, `agent`, and `orchestrator` providers.
- The new readiness page also shows selected provider readiness.

Problems:

- There is no guided "choose one working provider" flow.
- Some defaults are environment/company-specific, for example FAIR base URL.

Remaining improvement:

- In UI, show one primary action: "Configure first AI provider", then advanced routing.
- Keep env keys as fallback, but make managed UI keys the preferred source.

### P2 - Plugin Marketplace Should Stay Locked Until Policy Is Real

Status: partially fixed in this audit.

Current state after fix:

- Plugin settings and lifecycle have many policy knobs in env.
- Runtime defaults are strict in production for signing/scanning, but UI can still expose plugin management surfaces.
- Readiness page runs `plugin_marketplace_deploy_check` and surfaces the first blocking marketplace policy error with details.

Problem:

For an internal first launch, plugins are a high-blast-radius area: dynamic frontend bundles, backend packages, remote catalogs, egress, secret bindings.

Recommendation:

- Add a visible "Marketplace mode" status:
  - `local-only`
  - `private-catalog`
  - `remote-install-enabled`
- In first launch, keep remote install and dynamic bundles disabled.
- Require readiness checks before enabling install from remote catalog:
  - signing provider configured
  - scanner configured or explicitly waived
  - host allowlists configured
  - egress deny/allow policy configured
  - package retention configured

### P2 - Worker/Runtime Limits Needed Web Control

Status: fixed in this audit.

Current state after fix:

- Env still provides startup defaults/fallbacks for runtime limits.
- Web UI now exposes `/settings/limits`.
- `GET /api/settings/` returns effective runtime limit values.
- `POST /api/settings/` saves staff-only runtime limit updates into the web-managed model config.
- Runtime enforcement now reads web-managed overrides for:
  - active agent runs per user/global
  - active pipeline runs per user/global
  - SSH terminal sessions per user/global
  - stale run/session thresholds
  - per-user daily LLM token budget
  - MCP stdio/HTTP timeouts and retry attempts
- Readiness includes `runtime_limits` and links to `/settings/limits`.

Files:

- `app/core/model_config.py`
- `app/runtime_limit_config.py`
- `app/runtime_limits.py`
- `core_ui/services/llm_budget.py`
- `core_ui/views/settings_config_views.py`
- `studio/mcp_client.py`
- `web_ui/services/settings_readiness_runtime.py`
- `frontend/src/pages/settings/SettingsLimitsPage.tsx`
- `frontend/src/components/settings/settings-nav-items.ts`
- `frontend/src/App.tsx`
- `tests/test_settings_admin_guards.py`

Remaining improvement:

- Add per-team/group LLM budgets after groups and billing ownership are settled.
- Add current usage charts once there is enough pilot traffic.

### P3 - Audit Settings Are Web-Configurable, But Need Presets

Status: fixed in this audit.

Current state after fix:

- Audit flags and retention are in web settings and staff-only.
- Audit logging tab has presets:
  - `Pilot`: core events on, noisy HTTP logging off.
  - `Strict`: more categories on, longer retention.
  - `Debug`: HTTP/file logging on with short retention.

Files:

- `frontend/src/pages/settings-audit/auditSettingsModel.ts`
- `frontend/src/pages/settings-audit/AuditLoggingTab.tsx`
- `frontend/src/pages/settings/SettingsAuditPage.tsx`

Remaining improvement:

- Add estimated event-volume impact once there is enough historical usage data.

### P3 - Demo Mode Must Be Explicitly Off In Internal Production

Status: fixed in this audit.

Current state after fix:

- Frontend can fall back to demo mode only when `VITE_ENABLE_DEMO_MODE=true`.
- `/settings/readiness` now adds a browser-side `Frontend demo mode` check because the backend cannot reliably see Vite build env at runtime.

Problem:

This is likely fine, but for a company pilot it should be visible in readiness. If demo mode accidentally ships enabled, users can see mock data instead of a clear backend failure.

Files:

- `frontend/src/pages/settings/SettingsReadinessPage.tsx`
- `frontend/src/lib/api-demo-server-admin.ts`

## First-Run Web Setup Flow

Recommended first-run wizard after admin login:

1. `Platform Identity`
   - set display name/site URL if not already from env
   - show host/security status as read-only

2. `Secret Storage`
   - verify `MANAGED_SECRET_KEY`
   - encrypt/decrypt test secret
   - warn if fallback to `DJANGO_SECRET_KEY` is used

3. `AI Provider`
   - choose one provider
   - paste API key
   - refresh models
   - select model
   - run test prompt

4. `Notifications`
   - configure Telegram and/or SMTP
   - send test message/email
   - set public approval URL

5. `Access`
   - create or confirm platform admin
   - choose default profile for new users/domain users
   - create pilot group

6. `Servers`
   - add one test server
   - verify SSH
   - verify secret storage mode
   - verify terminal connect

7. `Studio`
   - check workers
   - run validate-only pipeline readiness
   - keep notifications optional unless used

8. `Plugins`
   - show locked/local-only status
   - do not enable remote install until policy checks pass

## Suggested Implementation Backlog

1. Done: add `Settings -> System Readiness` dashboard.
2. Done: move notification secrets from `.notification_config.json` to `ManagedSecret`.
3. Done: add `NOTIFICATION_CONFIG_PATH` as a short-term persistent config path.
4. Done: make `MASTER_PASSWORD` legacy-only in reveal flow for managed secrets.
5. Done: add Settings nav route for Notifications.
6. Done: split SSO page into live Header SSO and read-only LDAP status.
7. Done: gate `/servers` frontend routes with the `servers` feature.
8. Done: replace `/api/settings/check/` with selected-provider readiness.
9. Done: add access profiles for pilot roles and warnings around `is_staff`.
10. Partial: add plugin marketplace readiness status; still needs a clear Marketplace mode UX.
11. Done: add admin-tunable soft limits and LLM budgets.
12. Done: add audit presets.

## Do Before Giving Access To People

- Configure only one primary LLM provider first and test it from web UI.
- Keep MARS/Kubernetes hidden unless explicitly granted.
- Keep remote plugin install disabled.
- Create pilot users through groups, not one-off permissions.
- Verify notification test if pipelines will send approvals.
- Verify at least one server can connect without users entering secrets repeatedly.
- Run a readiness page/checklist before inviting non-admin users.
