# Intelligence contracts — backend inspection, 2026-09-02

Scope: server agents and runs, Operator Chat, MARS, server memory, MCP, and AI provider administration. This research uses current Python routes/views/models/services only; no previous frontend source or Git history was inspected. These are source-confirmed contracts, not claims that a worker/provider is currently running.

## Cross-cutting integration rules

- Django session authentication and CSRF apply to REST mutations. WebSockets use the authenticated session cookie. Read server-side feature permissions; never infer availability from a successful login or from `is_staff` alone.
- Prefixes are registered in `web_ui/urls.py`: agents/memory `/servers/`, MCP `/api/studio/`, MARS `/api/mars/`, chat and providers root `/api/`.
- Response shapes differ: chat returns objects; agents/memory often return `{success,...}`; MCP list/templates return bare arrays; MARS returns `{workspace|session|run|events|projects:...}`. Treat HTTP failure plus an explicit `success:false` as failures; do not require `data` on success.
- Run lifecycle completion does not establish task success. Agent report v2 separately exposes `outcome`, `evidence_state`, `report_generation`, and `delivery`.
- Tenant switching invalidates all cached resources and closes live sockets. MCP is explicitly filtered by the active project; agents/chat/MARS are also constrained by owner checks, with server capabilities checked at launch.
- Confirmation controls must show the actual server-provided action input, blast radius, risk, and error. Never automatically confirm actions, silently retry non-idempotent starts, or execute external deliveries on page load.

## Server agents and AI runs

Sources: `servers/urls.py:249`, `servers/views/server_agents.py`, `servers/views/server_agent_runs.py`, `servers/views/server_agent_dashboard.py`, `servers/agents/agent_service.py`, `servers/agents/agent_run_report_v2.py`, `servers/models_agents.py`.

All routes below start with `/servers/api/agents/`. Require `agents` and authenticated ownership; schedule endpoints require `automation`. Agents are owned by the user. REST run access permits `run.user` or the agent owner. Creating/updating/launching checks `execute_command` on selected servers; launch may additionally reject restricted pilot policy or unavailable execution workers.

| Method and suffix | Input | Successful response / behavior |
|---|---|---|
| GET empty suffix | `?mode=mini|full|multi` optional | `{success,agents,worker_states,runtime_overview}` |
| GET `templates/` | — | `{success,templates}` |
| POST `create/` | Agent fields below | `{success:true,id}` |
| POST `{id}/update/` | Mutable fields below | `{success:true}` |
| POST `{id}/delete/` | `{}` | `{success:true}`; destructive |
| POST `{id}/run/` | `{server_id?,provider_binding?}` | `{success,run_id,status,runs}`; navigate to returned run |
| POST `{id}/stop/` | `{}` | Stops active run selected by agent; use live run stop for an exact run |
| GET `{id}/runs/` | `limit` default 20/max 100 | `{success,runs}` |
| GET `dashboard/` | — | `{success,active,recent}`; each capped at 10, not a full history index |
| GET `runs/{run}/` | — | `{success,run}` including plan, pending question, dispatch |
| GET `runs/{run}/report/v2/` | — | Compact canonical report, schema below |
| GET `runs/{run}/events/v2/` | `limit,cursor,direction=older|newer,severity,phase,category,event_type,important,q` | `{success,items,events,page,total,filters,event_high_watermark,integrity}` |
| GET `runs/{run}/activity/` | `limit,cursor,direction,kind,status` | `{success,items,page,total,counts,...}` |
| GET `runs/{run}/artifacts/` | — | Artifact index; download through returned URLs |
| GET `runs/{run}/report/document/` | `download=1` optional | Redacted Markdown, ETag, attachment/inline |
| GET `runs/{run}/artifacts/download-all/` | — | ZIP; 404 when no artifacts |
| GET `runs/{run}/artifacts/{artifact}/download/` | — | Attachment |
| GET `runs/{run}/audit-export/` | — | NDJSON; 409 if audit integrity check fails |
| POST `runs/{run}/report/deliver/` | `{}` | 202 `{accepted,attempt_id,delivery}`; 409 if blocked/already delivered, 503 if queue dispatch fails |
| POST `runs/{run}/reply/` | `{answer}` | `{success:true}`; only a waiting owned run |
| POST `runs/{run}/approve-plan/` | `{}` | `{success,run_id,status,runs}` |
| POST `runs/{run}/tasks/{task}/update/` | `{action:"update"|"delete",name?,description?}` | `{success,plan_tasks}`; only pending/failed/skipped tasks |
| POST `runs/{run}/tasks/{task}/ai-refine/` | `{instruction}` | `{success,task,plan_tasks}`; uses configured LLM |
| GET `schedules/` | `limit` | `{success,scheduled_agents,...,runtime_overview}` |
| POST `schedules/dispatch/` | `{agent_ids?,limit?}` | Dispatch result; real execution mutation |
| POST `runtime/cleanup-stale/` | `{limit?}` | `{success,cleanup,runtime_overview}` |
| POST `runs/{run}/cleanup-stale/` | `{}` | `{success,code,run_id,cleaned,canceled_dispatches,run}` or reason blocked |

Agent fields: `name`, `mode` (`mini|full|multi`, creation only), `agent_type` (template identifier, creation only), `server_ids:number[]`, `commands`, `ai_prompt`, `goal`, `system_prompt`, `is_enabled` (update), `max_iterations`, `allow_multi_server`, `tools_config`, `sudo_policy`, `stop_conditions`, `session_timeout_seconds`, `max_connections`, `schedule_minutes`, `schedule_config`, `skill_slugs`, `input_artifacts`, `report_delivery`, `provider_binding`. Mini agents require commands. Empty server scope is valid only when chosen capabilities do not require a server. Provider overrides are retained only for explicit platform settings administrators.

The list additionally returns `server_count`, `server_names`, `mode_display`, `agent_type_display`, `last_run_at/status/id`, `active_run_id/status/started_at/iterations/server_name/pending_question`, `execution_readiness`, `schedule_state`, `due_now`, `next_due_at`, `next_due_in_seconds`. Use this data for readiness/next scheduled run; do not invent green state.

Run statuses: `pending`, `running`, `paused`, `waiting`, `plan_review`, `completed`, `failed`, `stopped`. Dispatch has a separate `queued|claimed|completed|failed|canceled` state. Display pending question/plan review as actionable states.

Report v2 top-level fields: `success`, `code`, `data:null`, `schema_version`, `run`, `lifecycle`, `outcome`, `evidence_state`, `report_generation`, `delivery`, `indicators`, `findings`, `actions`, `phases`, `counts`, `report_revision`, `event_high_watermark`, `updated_at`, `document`, `evidence_links`. `run` has id, agent identity/mode/type, goal, and server identity. Fetch report compactly while active; fetch the full Markdown/activity/artifacts only when opened. Cursor `page` has `limit,direction,next_cursor,prev_cursor,has_more,returned,truncated`; cursors must be opaque to the client.

### Agent realtime

`/ws/agents/{run_id}/live/` emits initial `{type:"agent_init",run_id,agent_name,agent_mode,status,total_iterations,connected_servers,pending_question,iterations_count}`. Events: `agent_action`, `agent_observation`, `agent_console`, `agent_status`, `agent_report`, `agent_question`, `agent_plan`, `agent_pipeline_phase`, `agent_task_start|done|failed|iteration` (and a raw `agent_thought` stream which should not be rendered as user-facing hidden reasoning).

Client messages: `{type:"agent_stop"}`, `{type:"agent_pause"}`, `{type:"agent_resume"}`, `{type:"agent_reply",answer}`, `{type:"ping"}`. Restore state from REST after reconnect and invalidate report on relevant events. **Contract limitation:** WS access checks only `agent__user`, whereas REST permits an owned orphan run without an agent. Keep REST evidence access functional if that socket cannot connect.

## Operator Chat

Sources: `core_ui/urls.py:184`, `core_ui/views/assistant_chat_views.py`, `core_ui/services/assistant_chat.py`, `core_ui/consumers/operator_chat.py`, `core_ui/services/operator_turn_runtime.py`, `core_ui/services/operator_loop.py`.

Requires `chat`; every chat/action is current-user scoped. There is no public/shared chat listing.

| Method and full path | Input | Response |
|---|---|---|
| GET `/api/assistant/chats/` | — | `{chats:Chat[]}` |
| POST same | `{title?}` | 201 `Chat` with messages |
| GET `/api/assistant/chats/{id}/` | — | `Chat` with messages and active_turn |
| PATCH same | `{title?,pinned_context?,kind?,provider_binding?:{}|null}` | `Chat`; nonempty provider_binding rejected here |
| DELETE same | — | `{ok:true}` |
| POST `/api/assistant/chats/message/` | `{message,provider_binding?}` | 201 `{chat,user_message,assistant_message,actions}`; create-and-message REST fallback |
| POST `/api/assistant/chats/{id}/message/` | `{message,provider_binding?}` | same for existing chat |
| GET `/api/assistant/chats/{id}/artifacts/` | — | `{artifacts}` |
| POST same | `{kind,title,content,metadata?}` | 201 artifact |
| PATCH same | `{id,content?,title?,bump_version?}` | artifact |
| POST `/api/assistant/actions/{id}/confirm/` | `{typed_confirm?}` (`confirm_token` also accepted) | serialized Action; 202 if another worker owns execution; 400 for confirmation failure; 409 terminal action |
| POST `/api/assistant/actions/{id}/cancel/` | `{}` | serialized Action |
| GET `/api/assistant/duty/` | — | `Chat` plus `duty_enabled`; creates duty session if absent |
| POST same | `{enabled:boolean}` or `{brief_now:true}` or `{}` | Chat/state or `{ok,result,chat}` |

`Chat`: `id,title,kind(manual|duty|incident),pinned_context,total_usage,provider_binding,created_at,updated_at,messages?,active_turn?`. Message: `id,role,content,metadata,created_at`; metadata.actions is a list of serialized Actions. `active_turn`: `turn_id,status,iteration,busy,assistant_message_id,assistant_text,pending_action_id`.

`Action`: `id,chat_id,message_id,action_type,title,description,status,risk,required_feature,requires_confirmation,input,result,error,target_url,blast_radius,dry_run_preview,undo_payload,async_run_ref,created_at,updated_at,confirmed_at,completed_at`. Use `input` as the safe preview; do not reconstruct unsafe raw inputs.

Limits are source-defined: messages 12,000 characters, artifacts 256,000 characters. Invalid JSON commonly becomes an empty object; 413 is returned for large messages/artifacts. REST messages invoke the real operator and can take time; avoid timeout-driven blind retries.

### Chat realtime and recovery

Use `/ws/operator/{chat_id}/` after REST creation. Initial `ready` carries `chat_id,busy,health`. Reconnect may deliver **`turn_snapshot`** (underscore): `chat_id,turn_id,status,iteration,busy,assistant_message_id,assistant_text,user_message_id,user_text,pending_action,in_process`. An optional queued dispatch snapshot has the same conceptual fields. The socket does not own the turn: leaving the page must not mark the task stopped.

Send `chat.message` with `message` (optional thinking/provider_binding only where authorized), `turn.stop`, `action.confirm` with `action_id,typed_confirm?`, `action.cancel` with `action_id`, and `ping`. Server emits `turn_started`, `thinking` (show generic activity, not internal reasoning), `token{text}`, `tool_started`, `tool_*`, `confirm_required`, `action_update{action}`, `usage{usage,turn_id}`, `turn_done{status,turn_id}`, and `turn_complete{status,assistant_message_id,user_message_id,actions}`. On completion refresh canonical REST history and deduplicate by message/action ID. `error{message,code?}` is visible and actionable. Revoked permission emits `permission_revoked` and closes 4403.

## MARS — guided engineering work

Sources: `mars/urls.py`, `mars/views.py`, `mars/services.py:161`, `mars/project_serializers.py`, `mars/models.py`, `mars/consumers.py`.

Requires `mars`. User access is restricted to the existing personal workspace and owned session/run. A workspace is policy-generated; the API does not currently implement arbitrary workspace editing/deletion.

| Method and `/api/mars/` suffix | Input | Response |
|---|---|---|
| GET `workspaces/` | — | `{workspaces:[Workspace]}`; creates personal workspace if absent |
| POST `workspaces/` | `{}` | 201 `{workspace}` |
| GET/PATCH `workspaces/{id}/` | PATCH has no effective configuration fields | `{workspace}`; DELETE returns 405 |
| GET `projects/` | `limit` default 30/max 100 | `{projects:[{session,latest_run,run_count,recommended_skills:[]}]}` |
| POST `sessions/` | `{task_brief,workspace_id?,selected_skill_slugs?}` | 201 `{session,recommended_skills:[]}`; 503 `codex_interview_failed` if interviewer unavailable |
| GET `sessions/{id}/` | — | `{session,recommended_skills:[]}` |
| POST `sessions/{id}/answer/` | `{answers:{questionId:string},selected_skill_slugs?}` | `{session}` at `plan_ready` |
| POST `sessions/{id}/approve-plan/` | `{generated_plan?,selected_skill_slugs?}` | `{session}` at `approved` |
| POST `sessions/{id}/run/` | `{allow_dirty?,verification_profile?,test_command?}` | 201 `{run}`; 409 `plan_not_approved` or `dirty_worktree`, 400 `workspace_policy_error` |
| GET `runs/{id}/` | — | `{run}` |
| GET `runs/{id}/events/` | `after_id` default 0 | `{events}` in ascending ID; no reported pagination cap |
| POST `runs/{id}/stop/` | `{}` | `{run}` with stop_requested; queued run immediately stops |

Workspace: `id,name,root_path,read_allow_roots,write_allow_roots,deny_globs,enabled,created_at,updated_at`. Session: `id,workspace_id,workspace,task_brief,answers,interview_questions,selected_skill_slugs:[],generated_plan,status,created_at,updated_at`. Run: `id,session_id,workspace_id,workspace,cli_roles:{},status,runtime_control,allow_dirty,final_report,codex_summary,gemini_review,test_output,git_before,git_after,started_at,completed_at,created_at`. Runtime detail is intentionally narrowed by serializer; do not expose absent roles/skill selection as working features.

Session lifecycle `interview → plan_ready → approved → running → completed` (also cancelled); run lifecycle `queued → running → completed|failed|stopped`. Guided task flow must preserve interview answers and the editable generated plan before approval/run. Empty interview/project state is real, not demo content.

WS `/ws/mars/runs/{id}/live/` emits `{type:"mars_event",event:{id,run_id,event_type,message,payload,created_at}}`; send `{action:"stop"}` to receive `{type:"control_ack",action:"stop",ok:true}`. There is no initial run snapshot; load REST first and recover events using after_id. Close 4001 unauthenticated / 4003 unauthorized.

## MCP connections

Sources: `studio/urls.py:83`, `studio/views/mcp_views.py:174`, `studio/models.py`.

Feature `studio_mcp`. Listing is constrained to the active project and owner/shared access. Owner/admin can edit/test; admin can share. `can_edit` and `can_share` are returned and should directly drive controls.

| Method and `/api/studio/mcp/` suffix | Input | Response |
|---|---|---|
| GET empty suffix | — | bare `MCP[]` |
| POST empty suffix | `{name,description?,transport:stdio|sse,command?,args?:string[],env?:object,url?,headers?:object,is_shared?,shared_user_ids?}` | 201 MCP; 403 policy failure |
| GET `{id}/` | — | MCP |
| PUT `{id}/` | Same mutable connection fields | MCP |
| DELETE `{id}/` | — | `{ok:true}` |
| POST `{id}/test/` | `{}` | `{ok:boolean,error:string|null}` and persisted last test state |
| GET `{id}/tools/` | — | Live inspection payload; policy/connection errors are real |
| GET `templates/` | — | bare templates array; present as setup suggestions, not verified integrations |

MCP serialized fields: `id,name,description,transport,command,args,env,secret_env_keys,url,headers,is_shared,shared_user_ids,shared_users,owner,owner_username,is_owner,can_edit,can_share,access_mode,last_test_ok,last_test_at,last_test_error`. Read-only viewers get empty env/headers/secret key lists. Display secrets only in a deliberate connection editor; do not put env values into generic property grids/logs. Last_test_ok null means untested, not connected. Live tools inspection can launch a configured subprocess or connect to a server; invoke on explicit user action.

## Server memory

Sources: `servers/views/server_memory.py`, `servers/views/server_memory_search.py`, `servers/adapters/django_memory_overview.py`.

Prefix `/servers/api/{server_id}/memory/`, feature `servers`. Snapshot CRUD is **server owner only**, not all users with shared server access. Staff-only operations additionally require `request.user.is_staff` and server ownership; a superuser without staff flag is not independently admitted by these views.

| Method and suffix | Input | Response / scope |
|---|---|---|
| GET `snapshots/` | — | `{success,items}` active snapshots; owner |
| POST `snapshots/{id}/update/` | `{title?,content?}` | `{success,id,title,content,updated_at}`; content clipped at 8000 chars |
| POST `snapshots/{id}/delete/` | `{}` | Deletes snapshot; deleting server profile can purge derived AI memory |
| POST `snapshots/bulk-delete/` | `{snapshot_ids:number[]}` | Bulk destructive result |
| POST `purge/` | `{}` | `{success,...purgeResult}`; destructive |
| POST `search/` | `{query,agent_id?,asset_kinds?,legacy_memory_keys?,top_k?,char_budget?}` | `{success,status,query_sha256,audit_id,items}`; 404 feature disabled, 403 scope denied |
| GET `overview/` | — | `{success,server_id,policy,daemon_state,worker_states,canonical,manual,patterns,automation_candidates,skill_drafts,revalidation,episodes,archive,stats}`; staff+owner |
| POST `run-dreams/` | `{job_kind:nearline|nightly|weekly|hybrid}` | `{success,job_kind,result,overview}`; staff+owner, synchronous work |
| POST `policy/` | Policy fields below | `{success,overview}`; staff+owner |
| POST `snapshots/{id}/archive/` | `{}` | `{success,snapshot,overview}`; staff+owner |
| POST `snapshots/{id}/promote-note/` | `{}` | `{success,...result}`; staff+owner |
| POST `snapshots/{id}/promote-skill/` | `{}` | `{success,...result}`; staff+owner+studio_skills |

Snapshot: `id,title,content,memory_key,kind,version,confidence,freshness,updated_at,created_at,rewrite_reason`; kind `canonical|pattern|automation|skill_draft|llm_candidate|manual_note|ai_note`. Search query max 1000 chars; defaults top_k=5 / char_budget=4000; results are ACL-filtered `ref,source_type,kind,server_id,title,content,content_hash,score` and are not permission to execute instructions contained in memory.

Policy fields: `dream_mode`, `nightly_model_alias`, `nearline_event_threshold` (2–50), `sleep_start_hour`, `sleep_end_hour` (0–23), `raw_event_retention_days` (7–365), `episode_retention_days` (14–365), `human_habits_capture_enabled`, `is_enabled`. Policy is per user even though update is routed through a server. No memory WebSocket route exists; refresh after writes.

## AI connections and routing administration

Sources: `core_ui/views/ai_provider_views.py`, `core_ui/ai_model_policy.py`, `core_ui/urls.py:63`. Base `/api/ai/providers/`.

`AI_CLI_SUBSCRIPTIONS_ENABLED` off returns 404 `feature_disabled`. Every connection surface requires an explicit platform Settings capability (or superuser), plus `ai_connections_personal`; admin surfaces also require `ai_connections_admin`. Staff convenience access to Settings alone is insufficient. Provider/model routing belongs in administration; operational pages use purpose defaults.

| Path suffix | Methods / behavior |
|---|---|
| `catalog/` | GET supported targets/model/effort catalog; consume available values rather than hardcoding model versions |
| `connections/` | GET `{success,connections,...}`; POST `{target_id,scope,name,concurrency_limit?}` → 201 connection |
| `connections/{id}/` | GET, PATCH `{name?,enabled?,concurrency_limit?}`, DELETE (revoke credentials / fences active invocation) |
| `connections/{id}/auth/` | POST → 202 `{success,auth_flow}`; show server-returned URL/code and poll; the user finishes sign-in |
| `connections/{id}/verify/` | POST → 202 `{success,auth_flow}`; poll returned flow |
| `auth-flows/{uuid}/` | GET `{success,auth_flow}` |
| `pools/` | GET `{success,pools}`; POST name/target/members → pool |
| `pools/{id}/` | PATCH pool configuration/members, DELETE |
| `grants/` | POST `{connection_id,<exactly one principal>,allow_interactive?,allow_unattended?,project_role?}` → grant |
| `grants/{id}/` | DELETE grant |
| `preferences/` | GET purpose defaults; PUT `{purpose,binding,workspace_default?,project_scoped?,require_unattended?}`; DELETE reset |

Validation errors support `{success:false,error,code:"validation_error",fields:{field:string[]}}`; surface per-field errors. Connection revocation and grant changes require concrete user action and refreshed capabilities.

## Implementation slices and honest empty/error states

1. Agents inventory + creation/edit + launch → exact run evidence page (report, phases, findings, pending question, approve/stop, lazy events/artifacts/document). Readiness reason explains disabled launch; no synthetic run rows.
2. Operator workspace: chat list → create → WS streaming → actions with confirmation → persisted messages/artifacts and reconnect recovery. REST fallback preserves operation history. No hidden reasoning text rendered.
3. MARS project list → task brief → dynamic interview fields → editable plan → approve → run with event timeline and report. The personal workspace is shown as context; omit unsupported workspace CRUD.
4. MCP inventory/editor + explicit connectivity test/tool inspection. Untested, test-failed, shared-read-only, denied-by-policy and unavailable are distinct.
5. Server-scoped knowledge snapshots/search with provenance/confidence/freshness; admin consolidation/policy operations are separate controls and permission-gated.
6. Administrative AI connection management + auth status + purpose defaults. Feature-disabled 404 is an unavailable-state explanation, not a network-failure toast loop.

Existing meaningful backend test entrypoints: `tests/test_assistant_chat_api.py`, `tests/test_operator_chat_websocket_permissions.py`, `tests/test_multi_instance_orchestration.py`, `tests/test_servers_agent_run_report_v2_api.py`, `tests/test_servers_agent_run_report_live_api.py`, `tests/test_mars_api.py`, `tests/test_mars_security.py`, `tests/test_servers_memory_api_smoke.py`, `tests/test_memory_asset_retrieval.py`, `tests/test_mcp_security.py`. These were discovered, not executed during this research pass.


## Gap audit implementation update

Studio AgentConfig is a separate entity from ServerAgent. `/intelligence/profiles` uses `studio_agents`; GET/POST `/api/studio/agents/`, PUT/DELETE `/{id}/` configure prompt/instructions/tools/sudo/server scope/MCP/skills. Shared-user assignments use the staff-only `/api/studio/share-users/` and `shared_user_ids`. `is_shared` is a derived serializer value (raw global sharing OR personal grants), so edits never round-trip it; explicit unchanged/enable/disable is required to change global sharing. The same protection and personal assignments apply to MCP.

ServerAgent editor now preserves all six normalized schedule modes (manual/interval/daily/weekly/monthly/once), timezone/calendar parameters, sudo, simultaneous connections, multi-server scope, operator materials/task lists/scripts and Telegram report delivery. Runtime drawer uses schedules overview, explicit per-agent due dispatch, stale-run cleanup. Plan tasks can be edited/refined only in pending/failed/skipped state; AI refinement persists to the backend plan immediately and the UI states that fact.

Operator now supports chat rename and duty enable/disable plus explicit brief_now request. Duty writes use the exact two response shapes: serialized chat for settings, `{chat,result,...}` for briefing. Server memory supports selected snapshot bulk deletion with named-server confirmation and warns that deleting the final active snapshot also purges derived AI memory. Existing scope selection closes transient editors, confirmations and search results.

Scopes and verification: own TypeScript/ESLint clean at the audit checkpoint; 4 action-review Vitest tests passed. Live LLM/provider output, Telegram delivery and MARS CLI execution require configured services and are not certified by the frontend tests.
