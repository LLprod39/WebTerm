# Governance contracts — frontend next

Verified against backend source on 2026-09-02. This document records current contracts, not the previous frontend. No historical frontend or Git history was inspected. All paths below include their mount prefix and trailing slash.

## Session and authentication

Source: `core_ui/views/auth_views.py`, `core_ui/auth_throttle.py`, `web_ui/settings/auth.py`, `web_ui/settings/security.py`.

| Method / path | Input | Response / behavior |
| --- | --- | --- |
| GET `/api/auth/csrf/` | none | `{csrfToken:string}` and CSRF cookie |
| GET `/api/auth/session/` | session cookie | `{authenticated:boolean,user:SessionUser|null}`; anonymous is HTTP 200 |
| POST `/api/auth/login/` | `{username,password,auth_mode?:"auto"|"local"}` | `{success:true,authenticated:true,next_url,user:SessionUser}`; missing fields 400, invalid password 401, inactive user 403, unavailable enforced LDAP 503 |
| POST `/api/auth/logout/` | `{}` | `{success:true,authenticated:false,user:null}` |

`SessionUser`: `id:number`, `username`, `email`, `is_staff:boolean`, `can_manage_ai_routing:boolean`, `ai_cli_runtime_enabled:boolean`, `access_profile:string`, `permission_sources:Record<string,string>`, `features:Record<string,boolean>`, `active_project:{id:UUID,name,slug}|null`, `project_count:number`.

Use cookie authentication with `credentials: "include"` and `X-CSRFToken` on mutations. Refresh CSRF after login because Django rotates it. Send the token returned by the CSRF endpoint; no bearer token/localStorage auth scheme exists. Session is the source of truth for route and action visibility. A `login_required` API may redirect to `/login/`, which redirects to the frontend login route: treat an unexpected redirect/login HTML as session loss, rather than attempting JSON parsing. A 403 is forbidden unless the response specifically indicates CSRF failure. Login throttling returns 429 `{success:false,error,code:"login_throttled"}` and `Retry-After`; cache failure yields the same envelope at 503. Do not automatically retry non-idempotent mutations.

SSO is reverse-proxy identity headers (trusted proxies/shared secret) and optional LDAP password authentication. There is no OIDC/SAML registration or browser SSO-provider API. An existing proxy session is discovered by `/api/auth/session/`. `auth_mode:"local"` supports explicit local login, except that `LDAP_PASSWORD_LOGIN_ENFORCED` permits local authentication only for configured local admin usernames and routes other identities to LDAP. Do not let UI header settings imply that the proxy trust boundary can be bypassed.

## Features and roles

Source: `core_ui/models/access.py`, `core_ui/access.py`, `core_ui/ai_model_policy.py`.

Feature names: `servers`, `dashboard`, `agents`, `chat`, `automation`, `ai_connections_personal`, `ai_connections_admin`, `studio`, `studio_pipelines`, `studio_runs`, `studio_agents`, `studio_skills`, `studio_mcp`, `studio_notifications`, `kubernetes`, `kubernetes_admin_read`, `kubernetes_admin_write`, `kubernetes_break_glass`, `kubernetes_secret_read`, `mars`, `settings`, `orchestrator`, `knowledge_base`, `web_research`. Session adds release capability `plugins`.

Precedence: deployment disable → staff requirement if defined → user explicit value → group explicit value (deny wins between groups) → supported legacy fallback → explicit-opt-in denial → staff default allow → ordinary default. The current staff-only feature set is empty. Nonstaff defaults: servers, agents, dashboard, chat. Explicit opt-in applies even to staff for Kubernetes capabilities, mars, web_research and ai_connections_admin. Do not recompute this policy in the frontend: consume session `features` and access API effective permissions.

Profiles: `pilot_user`, `pilot_operator`, `server_only`, `operator_server_only`, `operator_studio_runner`, `team_admin_no_secrets`, `admin_full`, `platform_admin`, `reset_defaults`, `custom`. Assigning a predefined profile materializes overrides and may change `is_staff`. `reset_defaults` removes user overrides. `custom` makes no changes. Overrides are tri-state: `true` allow, `false` deny, `null` or empty string removes the override and restores inheritance.

`can_manage_ai_routing` requires effective settings permission AND superuser or an explicit user/group settings grant. Staff-default settings alone is insufficient. AI connection features are suppressed in the session when this predicate is false. `ai_cli_runtime_enabled` comes from `AI_CLI_SUBSCRIPTIONS_ENABLED`. Plugins require `is_staff` and an enabled release profile; disabled deployments omit the entire plugin URL tree. Kubernetes deployment disable is folded into session feature permissions.

| Surface | Required capability |
| --- | --- |
| Global settings read | settings |
| Users, groups, permission management; settings audit; readiness | settings AND is_staff |
| Model/provider routing, key rotation, model discovery | can_manage_ai_routing |
| CLI connection management | runtime enabled AND can_manage_ai_routing AND ai_connections_personal |
| Workspace CLI connections/pools/grants/defaults | above plus ai_connections_admin |
| Admin dashboard/activity/sessions | dashboard AND is_staff |
| Projects list/create/activate | authenticated |
| Project membership mutations | project owner/admin; owner immutable |
| Plugin management | release enabled AND settings AND is_staff |

## Users, access groups, permissions

Source: `core_ui/views/access_views.py`, `core_ui/views/access_group_views.py`. All require authentication + settings + staff. Lists are unpaginated; local search/sort/pagination is appropriate until backend pagination exists.

`AccessUser`: id, username, email, is_staff, is_active, is_superuser (read payload), date_joined (read payload), groups:[{id,name}], access_profile, effective_permissions, explicit_permissions, group_permissions, group_permission_sources:{feature:[{group_id,group_name,allowed}]}, permission_sources. `FeatureChoice` is `{value,label}`.

| Method / path | Input / output |
| --- | --- |
| GET `/api/access/users/` | `{users:AccessUser[],features:FeatureChoice[]}` |
| POST `/api/access/users/` | `{username,password,email?,is_staff?,is_active?,groups?:number[],access_profile?,explicit_permissions?}` → `{success,user}`; defaults to pilot_user |
| GET `/api/access/users/{id}/` | `{user}` |
| PUT `/api/access/users/{id}/` | changed username/email/is_staff/is_active/groups/access_profile/explicit_permissions → `{success,user}` |
| DELETE `/api/access/users/{id}/` | `{success,message}`; own user prohibited 400, superuser prohibited 403 |
| POST `/api/access/users/{id}/password/` | `{password}` → `{success,message}`; backend minimum four characters |
| POST `/api/access/users/{id}/profile/` | `{profile}` → updated user/access payload |
| GET `/api/access/groups/` | `{groups:[{id,name,members:[{id,username}],member_count,explicit_permissions}],features}` |
| POST `/api/access/groups/` | `{name,members?:number[],explicit_permissions?}` → `{success,group}` |
| GET `/api/access/groups/{id}/` | `{group:{id,name,members,explicit_permissions}}` |
| PUT `/api/access/groups/{id}/` | `{name?,members?:number[],explicit_permissions?}` → `{success,group}` |
| DELETE `/api/access/groups/{id}/` | `{success,message}` |
| POST or DELETE `/api/access/groups/{id}/members/` | `{user_id}` adds/removes member; `{success,message}` |
| GET `/api/access/permissions/` | `{permissions:[{id,user_id,username,feature,feature_display,allowed}],group_permissions:[{id,group_id,group_name,feature,feature_display,allowed}],features}` |
| POST `/api/access/permissions/` | `{user_id,feature,allowed}` → `{success,created,permission}` upsert |
| PUT `/api/access/permissions/{id}/` | `{allowed}` → `{success,permission}` |
| DELETE `/api/access/permissions/{id}/` | removes override, restores inheritance |
| GET `/api/access/group-permissions/` | `{permissions:[group permission],features}` |
| POST `/api/access/group-permissions/` | `{group_id,feature,allowed}` → `{success,created,permission}` |
| PUT or DELETE `/api/access/group-permissions/{id}/` | `{allowed}` for PUT; same semantics as user override |

Other users' superuser accounts cannot be edited or have password/permission/profile changes. Show role, source and effective result together; never represent inherited permission as an explicit allow. Refresh session if current user's permissions/groups are changed. Destructive confirmation must name the actual user/group. Group membership input replaces the set on PUT.

## Projects and team boundary

Source: `core_ui/views/project_views.py`, `core_ui/projects.py`.

`Project`: `{id:UUID,name,slug,role,is_active,is_default,member_count,can_manage,created_at}`. `ProjectMember`: `{user_id,username,email,role,is_active,joined_at}`.

| Method / path | Contract |
| --- | --- |
| GET `/api/projects/` | `{projects:Project[],active_project_id:UUID|null}` |
| POST `/api/projects/` | `{name,activate?:boolean=true}` → 201 `{project}` |
| POST `/api/projects/{UUID}/activate/` | `{}` → `{success,project}` |
| GET `/api/projects/{UUID}/members/` | `{members:ProjectMember[]}` |
| POST `/api/projects/{UUID}/members/` | `{username?:string,email?:string,role:"admin"|"operator"|"viewer"}` → `{member}` at 201/200; existing active user required |
| PATCH `/api/projects/{UUID}/members/{user_id}/` | `{role}` → `{member}` |
| DELETE `/api/projects/{UUID}/members/{user_id}/` | `{success}`; owner protected with 409 |

Activate must invalidate project-scoped query caches and refresh session. Project UUIDs differ from internal integer project IDs used by AI grants/preferences; do not pass UUID to the integer grant API. There is no project delete endpoint in this URL surface. Membership creation is not an invitation/email workflow.

## Settings, identity, logging and readiness

Source: `core_ui/views/settings_config_views.py`, `core_ui/services/settings_status.py`, `web_ui/views/settings_readiness_views.py`.

GET `/api/settings/` → `{success,config,api_keys,providers,ldap_status}`. POST same path accepts a partial flat config object plus optional `api_keys:{gemini?,grok?,openai?,claude?,ollama?}` / `clear_api_keys:string[]`, returns `{success,message}`. Read never returns key values. Empty new keys are ignored; clearing requires explicit array. Clearing managed key may reveal environment fallback, so refresh the boolean status after clearing.

Important config groups:

- Provider routing: default_provider, internal_llm_provider, chat_llm_provider/model, agent_llm_provider/model, orchestrator_llm_provider/model; chat_model_gemini/grok/openai/claude/ollama; agent_model_gemini/grok/openai/ollama; rag_model; provider_enabled flags; openai_reasoning_effort.
- Ollama: ollama_base_url, ollama_runtime_mode(auto/local/cloud), ollama_cloud_enabled, ollama_cloud_base_url, ollama_think_mode(empty/off/on/low/medium/high).
- SSO: domain_auth_enabled, domain_auth_header, domain_auth_auto_create, domain_auth_lowercase_usernames, domain_auth_default_profile. Staff mutation gate. LDAP settings are environment-at-startup and read-only here.
- Audit: log_terminal_commands, log_ai_assistant, log_agent_runs, log_pipeline_runs, log_auth_events, log_server_changes, log_settings_changes, log_file_operations, log_mcp_calls, log_http_requests, retention_days(1..3650), export_format(json/csv/syslog). Staff mutation gate.
- Runtime limits: fields supplied by `app/runtime_limit_config.py`, staff mutation gate. Use exact schema rather than inventing settings.

`ldap_status`: enabled,status(disabled/misconfigured/enabled),severity,backend_loaded,server_configured,search_base_configured,bind_dn_configured,bind_password_configured,start_tls,ignore_cert,ca_cert_configured,missing:string[],config_source:"env_startup".

GET `/api/settings/check/` → `{configured,missing:string[],providers:[{role,provider,enabled,configured,ready}]}`.

GET `/api/settings/readiness/` (settings+staff) → `{success,status:"ready"|"warning"|"error",summary:{ready,warning,error,total},checks:[{key,title,status,severity,message,action_path,action_label,details}]}`. Checks cover deployment, placeholders, managed secrets, paths, AI, notifications, proxy SSO, LDAP, server secret storage, access policy, limits, workers, Ansible, plugins. Show actual severities and details, not derived "production ready" marketing claims.

GET `/api/models/` (AI routing admin) → provider model arrays (`gemini`,`grok`,`openai`,`claude`,`ollama`,`ollama_local`,`ollama_cloud`), rag_defaults, current. POST `/api/models/refresh/` `{provider:"gemini"|"grok"|"openai"|"claude"|"ollama"}` → `{success,provider,models,count}`; performs remote model lookup and can fail if key absent.

## Audit and sessions

GET `/api/settings/activity/` (settings+staff). Query: limit(1..200,default50), offset(default0), days(1..365,default14), user_id, category, action, status, search, format(csv/syslog). JSON → `{success,events,summary,user_stats,users,paging:{limit,offset,total,has_more}}`.

`AuditEvent`: id,created_at,user_id,username,category,action,status,description,entity_type,entity_id,entity_name,ip_address,user_agent,metadata. Summary: total_events,total_users,login_count,assistant_requests,server_connections,server_changes. `user_stats` has user_id,username,events_total,logins,ai_requests,server_connections,server_changes. `users` supplies filter options. CSV/syslog response is a file, capped at 5000 rows, and honors filters. Keep active filters in the URL and provide clear export format/cap feedback.

GET `/api/admin/users/activity/` (dashboard+staff): limit<=200,offset,days<=90,user_id,category,search → `{success,total,events}` with shortened descriptions and fewer fields. GET `/api/admin/users/sessions/` → `{success,online_count,total_registered,active_today,sessions:[{user_id,username,email,is_staff,last_action,last_category,last_activity,active_terminals,today_actions}]}`. This is activity within five minutes, not a revocable session registry; do not invent "end session" controls.

## Subscription CLI providers

Source: `core_ui/views/ai_provider_views.py`, `core_ui/models/ai_providers.py`. Base `/api/ai/providers/`. Feature-disabled produces 404 code feature_disabled; forbidden produces 403 permission_denied. Validation may include field errors. All require runtime flag, AI routing permission and personal connection feature; admin surfaces additionally require ai_connections_admin.

| Method / relative path | Input / output |
| --- | --- |
| GET `catalog/` | `{success,targets:[{id,label,auth?,kind}],purposes,scopes,models_by_target}`; model choices/reasoning lists must come from this response |
| GET `connections/` | `{success,connections:Connection[]}` |
| POST `connections/` | `{target_id:"codex_subscription"|"grok_subscription",scope:"personal"|"workspace",name,concurrency_limit?:1..8}` → 201 `{success,connection}` |
| GET/PATCH `connections/{id}/` | PATCH name/enabled/concurrency_limit → `{success,connection}`; manageable owner/admin |
| DELETE `connections/{id}/` | `{success,revoked:true}` OR 202 `{success:true,revoked:false,cleanup_pending:true,code:"provider_credential_cleanup_pending"}`; latter is pending, not completed revoke |
| POST `connections/{id}/auth/` | `{}` → 202 `{success,auth_flow}`; unavailable transport 503 |
| POST `connections/{id}/verify/` | `{}` → 202 `{success,auth_flow}`; no credentials 409 provider_auth_required |
| GET `auth-flows/{UUID}/` | `{success,auth_flow}`; owner/admin |
| GET/POST `pools/` | GET `{success,pools}`; POST `{name,target_id,members:[{connection_id,weight:1..100,enabled}]}` → 201 `{success,pool}`; members must reference workspace connections for same target |
| GET/PATCH/DELETE `pools/{id}/` | PATCH name/enabled/members; DELETE `{success}` |
| POST `grants/` | `{connection_id, exactly one of user_id/group_id/project_id, project_role?, allow_interactive?:true,allow_unattended?:false}` → 201 `{success,grant}`; only workspace connections |
| DELETE `grants/{id}/` | `{success}` |
| GET `preferences/` | `{success,preferences,workspace_defaults}` |
| PUT `preferences/` | `{purpose,workspace_default?:false,project_scoped?:true,require_unattended?:false,binding:{target_id,connection_id?,pool_id?,model_id?,reasoning_effort?}}` → `{success,preference}` |
| DELETE `preferences/` | `{purpose,workspace_default?,project_scoped?}` → `{success}` restores inheritance |

`Connection`: id,public_id,target_id,scope,owner_id,name,status,enabled,runtime_version,auth_revision,concurrency_limit,health,limits,last_error_code,last_verified_at,access:{interactive,unattended},manageable,created_at,updated_at; admin response may include grants. Status: pending_auth,connected,auth_required,limited,degraded,disabled,revoked.

`AuthFlow`: id(UUID),connection_id,status(pending/completed/expired/cancelled/failed),verification_uri,user_code,error_code,expires_at,created_at,completed_at. Start flow, show code/link, poll only while pending, preserve user's browser-controlled device login, then refresh connection. Successful queue submission is not authentication success.

`Pool`: id,public_id,name,target_id,enabled,manageable,members:[{id,connection_id,connection_name,status,enabled,weight,access}]. `Grant`: id,connection_id,user:{id,username}|null,group:{id,name}|null,project:{id,name}|null,project_role,allow_interactive,allow_unattended. `Preference`: id,user_id,project_id,purpose,binding. Purposes: assistant,agents,terminal,internal. Workspace default cannot bind personal connection; personal route requires usable binding. Model/reasoning validity is backend-checked.

## Plugins

Source: `plugin_marketplace/urls.py`, `views/`, `services/serialization.py`, `services/settings_service.py`. Base `/api/plugins/`. Hide when session.features.plugins is false. Disabled release has no URL surface. Most management endpoints require settings+staff; catalog reads require settings. Empty catalog is an empty state, not synthetic sample data.

`Package`: id,plugin_id,version,name,slug,publisher:{id,name},source,package_hash,signature_payload,provenance,attestations,sbom,dependency_scan,sandbox_policy,attestation_policy,risk_tier,review_status,signature_status,created_at,updated_at,manifest.

`Installation`: id,plugin_id,status,package,settings,scope,health_status,health_failure_count,last_error,installed_at,enabled_at,disabled_at,quarantined_at.

| Method / relative path | Contract |
| --- | --- |
| GET `catalog/` | `{success,plugins:[{id,name,slug,version,summary,description,publisher,categories,risk_tier,permissions,surfaces,actions,installation,review_status,signature_status,enabled}],summary:{registered,enabled,disabled}}` |
| GET `installed/` | `{success,installations}` |
| GET `installed/{id}/scope/` | `{success,scope,available_groups}` |
| POST `installed/{id}/scope/update/` | `{group_ids:number[]}` → `{success,installation_id,scope}` |
| POST `installed/{id}/enable/` or `disable/` | `{}` → `{success,installation_id,status}`; enabling can reject invalid state 409 |
| GET `installed/{id}/impact/` | `{success,impact}` for review before lifecycle actions |
| POST `installed/{id}/update-preview/` | `{package_id}` or `{manifest}` → `{success,impact}` |
| POST `installed/{id}/update-package/` | `{package_id}` → `{success,installation}` |
| POST `installed/{id}/soft-uninstall/` | `{revoke_permissions?:false,remove_secret_bindings?:false}` → `{success,installation}` |
| POST `installed/{id}/rollback/` | `{package_id?}` → `{success,installation}` |
| GET `installed/{id}/permissions/` | `{success,permissions}` |
| POST `installed/{id}/permissions/grant/` or `revoke/` | `{scope}` → `{success,scope,granted}` |
| GET `installed/{id}/settings/` | `{success,settings,schema,secrets:[{key,label,kind,required,bound,secret_ref:masked}]}` |
| POST `installed/{id}/settings/update/` | `{settings:object}` → `{success,settings}`; schema validated |
| POST `installed/{id}/secrets/bind/` | `{key,secret_ref}` → `{success,secrets}`; reference only, not raw secret |
| POST `packages/validate-path/` | `{path}` validates server-side path |
| POST `packages/install-local-upload/` | multipart upload; exact upload field comes from view |
| POST `packages/install-remote/` | `{url,expected_sha256}` → `{success,installation_id,status}` |
| GET/POST `packages/retention/` | GET inventory; POST `{dry_run?:true,max_age_days?}` → `{success,result}` |
| GET `review/packages/` | package review inventory |
| POST `review/packages/{id}/review/` | `{status,notes?,rejection_reason?,sign_when_verified?:true}` → `{success,package}` |
| POST `review/packages/{id}/sign/`, `verify-signature/`, `attest/`, `security-scan/`, `replay-provenance/` | `{}` → `{success,package}` |
| GET `review/packages/{id}/sbom/` | JSON SBOM |
| GET/POST `marketplace/sources/` | GET `{success,sources}`; POST `{name,source_url,is_enabled?:true}` → `{success,source}` |
| PATCH/POST `marketplace/sources/{id}/` | source fields → `{success,source}` |
| POST `marketplace/sources/{id}/sync/` / `sync-remote/` | manual payload / remote fetch; refresh source/catalog afterward |
| GET `marketplace/catalog/` / `{id}/` | `{success,items,summary:{available}}` / `{success,item}` |
| POST `marketplace/catalog/{id}/install/` | `{}` → `{success,installation_id,status}` |
| GET `marketplace/compatibility-matrix/` | compatibility report |
| GET/POST `marketplace/compatibility-jobs/` | compatibility job surface |
| POST `quarantine/` | `{plugin_id,reason}` → `{success,installation}` |

Source payload: id,name,source_url(redacted),sync_mode(remote/manual),federated,is_enabled,credentials_redacted,last_sync_at,last_error. Catalog item: id,source,plugin_id,version,manifest,package_url,compatibility,compatibility_report,review_status,signature_status,installed,installation_id,created_at,updated_at.

Additional backend plugin runtime surfaces exist: GET surfaces, plugin pages, connector health; POST connector ping, terminal action execute, hooks emit. They require their individual plugin permissions and bounded scopes. Never execute returned plugin markup as arbitrary application code or show unverified plugin health as connected.

## Product implementation constraints

Permission-dependent navigation must wait for a settled session. Loading, forbidden, deployment-disabled, empty and error are distinct states. Preserve inputs after failed saves; render server validation alongside fields; confirmations show exact entity and operation. Use returned schemas/catalogs for dynamic choices. Fresh API success plus refreshed data is the evidence for completion. Client-only health simulation or synthetic business data is not permitted.

Backend gaps relevant to a sellable enterprise UI: no SAML/OIDC config endpoints, no audit deletion endpoint, no revocable authentication-session registry, no access-user pagination, no project delete endpoint. LDAP runtime config is environment-owned. Expose these accurately without invented controls.

## Admin activity and usage

Source: `core_ui/views/admin_views.py`, `core_ui/views/admin_billing.py`, `servers/admin_metrics_provider.py`. All three endpoints require an authenticated staff user with feature `dashboard`; feature `settings` is not required. Data is platform-wide, not limited to the selected project. Frontend entry: `/governance/activity`.

| Method / endpoint | Exact response and workflow |
| --- | --- |
| GET `/api/admin/users/sessions/` | `{success,online_count,total_registered,active_today,sessions:[{user_id,username,email,is_staff,last_action,last_category,last_activity,active_terminals,today_actions}]}`. Users having a UserActivityLog event in the past five minutes. No authentication-session identifier, expiry or revoke action. UI labels activity accurately and polls every 30 seconds while visible unless disabled. Click a user to filter events by user ID. |
| GET `/api/admin/users/activity/` | Filters `limit` (default 50, maximum 200), `offset` (nonnegative), `days` (default 7, maximum 90), `user_id`, `category`, `search`. Search covers username snapshot, action, description and entity name. Response `{success,total,events:[{id,user_id,username,category,action,status,description,entity_type,entity_name,ip_address,created_at}]}`. Description is truncated to 300 characters; metadata is not included. Frontend validates integer URL filters and uses server pagination. |
| GET `/api/admin/dashboard/` | `{success,data:{online_users,ai,terminals,agents,execution_queues,api_usage,api_calls_today,providers,servers,tasks,hourly_activity,top_users,recent_activity,fleet_health,active_alerts_count,alerts,app_version}}`. APIContractMiddleware adds `code:ok`; the shared API client unwraps its exact success/code/data envelope. This page consumes only usage, activity trends and terminal registry; server/alert overview remains in the main overview. |

`api_usage` is keyed by gemini, grok, claude, openai, ollama. Each value contains `calls,input_tokens,output_tokens,errors,estimated_cost_usd,actual_spend_usd,balance_usd,billing_source,billing_note,cost_usd`. Actual expense and balance are nullable; null is displayed as unavailable, not zero. Estimated expense uses fixed provider coefficients over local token counts for the server's day, not per-model price. Provider billing requests use UTC day and may include external account-wide spend. The actual aggregate explicitly shows how many provider accounts supplied data. Billing refresh is server-cached (default 600 seconds). UI never combines estimated and actual amounts into a single unlabeled total.

`providers[provider]={enabled,model}` is configured state, not live health. `hourly_activity=[{hour,count}]` contains available buckets in the last 24 hours. `top_users=[{username,total,ai_requests,terminal_sessions}]` is top ten by logged events over seven days; despite its name, `terminal_sessions` counts terminal-category events, so the UI labels it "События терминала". `terminals={active,connections:[{server,user,connected_at}]}` reads ServerConnection rows with status `connected`; it is a registry snapshot, not a liveness probe or a revocable session list.

## Personal dashboard layout

Source: `core_ui/views/dashboard_layout.py`, `core_ui/models/preferences.py`. Frontend entry `/settings/workspace` is available to every authenticated user, without the platform-settings feature. `DashboardSections` applies the saved values in the main overview, using real `servers`, `activity`, `alerts`, `tools` sections; summary metrics remain at the top.

| Method / endpoint | Contract |
| --- | --- |
| GET `/api/dashboard-custom/layout/{type}/` | `type=user` for any authenticated user; `type=admin` additionally requires staff. Invalid types return 400. Response `{success,layout:null}` if absent or `{success,layout:<JSON>}`. Current authenticated user's active layout only. |
| POST `/api/dashboard-custom/layout/{type}/` | Body `{layout:<non-null JSON>}`. Creates/updates the current user's row, sets `is_active=true`, returns `{success,created:boolean}`. No delete/reset endpoint or server-side JSON schema. CSRF required. |

Frontend Next uses `layout.frontend_next={version:1,overview:{columns:{main:SectionId[],side:SectionId[]},hidden:SectionId[]}}`. Defaults are main `[servers,activity]`, side `[alerts,tools]`, hidden `[]`. Unknown values and duplicate section IDs are ignored on read, missing sections are restored, unsupported schemas fall back to defaults. Save fetches the latest payload and merges only this namespace; unrelated object keys survive. A pre-existing non-object payload is preserved in `legacy_layout`. Reset restores the explicit default structure and requires Save. The editor guards unsaved navigation and page unload, preserves the draft on API failure, and only reports saved after POST success. Query keys include current user ID and dashboard type; successful saves update the same cache consumed by Overview. This layout is per account and dashboard type, not per project.
