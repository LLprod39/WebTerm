# Automation contracts for Frontend Next

Source-verified on 2026-09-02. This inventory was produced from backend code and backend tests only. No previous frontend, design, screenshot, or Git history was used. This is a contract inventory, not a claim that live execution was tested.

## Transport and access

* Studio base: `/api/studio/` (`web_ui/urls.py`, `studio/urls.py`). Views return bare objects/arrays. The API middleware wraps bare arrays in `{success:true,code:"ok",data:[...]}` and preserves object fields at the top level; the shared API client unwraps pure envelopes. Errors normally `{error: string}`, graph validation adds `{details: string[], issues: Issue[]}`; runtime limits use HTTP 429 and an issue payload.
* Playbook base: `/servers/api/playbooks/` (`servers/urls.py`). JSON responses normally use `{success: true, playbook|draft|revision|validation|run|report|...}`; errors use `{success:false,error,code?,stage?,field?,details?}`. Some Django 404/403 responses can be HTML; the shared API client must handle non-JSON failures.
* Both use authenticated Django sessions and CSRF for unsafe HTTP methods. Feature checks are necessary but do not replace object capabilities.
* Playbooks: `automation` feature, `capabilities` returned for each playbook: `can_view`, `can_edit`, `can_validate`, `can_publish`, `can_run`, `can_export`, `can_share`, `can_delete`, `is_owner`. Owner has all; explicit user/group grants and project membership govern non-owner access. No staff bypass exists in the object capability service. New workspace-wide shares are rejected; explicit user/group sharing is supported.
* Pipeline CRUD/run access: `studio_pipelines`, active project, owner or staff. `is_shared` is serialized but does **not** grant non-owner pipeline access in the current queryset. Pipeline runs: `studio_runs`, same project/owner-or-staff filter.
* Agent configs and MCP: `studio_agents` / `studio_mcp`, active project; owner/shared/explicit share can read, owner/staff can edit; only staff can change sharing. Respect serialized `can_edit`, `can_share`, `access_mode`.
* Skills: `studio_skills`; explicit skill access record and active project are needed for non-staff readers; owners/staff can edit with active-project constraints; only staff can share. Staff can read global catalog entries even if they cannot edit an entry outside their active project.

## Primary payloads

`Playbook`: `{id,name,description,kind,category,visibility,tags,fidelity,compatibility,active_compatibility_revision,task_count,is_template_clone,template_slug,last_run_at,last_run_status,created_at,updated_at,owner_id,origin_revision_id,published_revision_id,published_revision_number,published_content_hash,draft_version,has_unpublished_draft,source,capabilities}`. Detail adds `{tasks,source_yaml,adapted_source_yaml}`. Tasks are `{id,command,description,continue_on_error}`. Published content and unpublished draft are separate.

`PlaybookDraft`: `{id,base_revision_id,content_format,source_yaml,tasks,content_hash,bundle_hash,asset_bundle_id,entrypoint,version,last_editor_id,updated_at}`.

`PlaybookRevision`: `{id,revision_number,parent_id,content_format,content_hash,bundle_hash,origin_type,message,author_id,author_username,created_at,compatibility}`; detail adds `{source_yaml,tasks}`.

`PlaybookRun`: `{id,playbook_id,revision_id,validation_id,binding_profile_id,status,playbook_name,target_server_ids,target_group_ids,options,variable_manifest,execution_fingerprint,summary,progress,inventory_preview,error_message,cancel_requested,started_at,finished_at,created_at}`. Detail adds `{host_results,playbook_snapshot,live_log}`. Secret variable names may be returned; values are redacted. Terminal states include `completed`, `failed`, `partial`, `cancelled`.

`PipelineSummary`: `{id,name,description,icon,tags,is_shared,is_template,graph_version,node_count,created_at,updated_at,provider_binding,trigger_summary,last_run}`. Detail adds `{nodes,edges,triggers}`. `last_run` is `{id,status,started_at,finished_at}|null`; trigger summary gives active counts and last trigger timestamp.

`PipelineNode`: `{id:string,type:string,position:{x:number,y:number},data:object}`. `type` is the backend node type, e.g. `trigger/manual`, `agent/ssh_cmd`, `logic/condition`. `PipelineEdge` uses `{id,source,target,sourceHandle?,targetHandle?}`. Preserve other fields when round-tripping a graph. Secrets in nodes are redacted by serialization.

`NodeManifest`: `{type,category,purpose,source_handles,risk_level,idempotency,mutates_state,supports_dry_run,requires_approval_by_default,recommended_verification,tags,input_schema,output_schema,metadata}`. Dynamic plugin manifests are included. JSON Schema properties include defaults, enum, required, descriptions, bounds and arrays. Build the node palette and property editor from this contract instead of an incomplete hard-coded node catalog.

`PipelineRun`: `{id,pipeline_id,pipeline_name,status,node_states,nodes_snapshot,edges_snapshot,context,summary,error,duration_seconds,started_at,finished_at,created_at,triggered_by,trigger_id,entry_node_id,trigger_type,trigger_name,trigger_node_id,can_resume,resume_confirmation_required,provider_binding_snapshot,provider_session_id}`. Run statuses: `pending|running|completed|failed|stopped|hibernating`; node state has its own status (including `awaiting_approval`), output/error/timestamps and only allowlisted fields. Approval tokens are deliberately excluded from run serialization. `edges_snapshot` is the additive, immutable graph field introduced for the read-only run canvas; older API responses can omit it, in which case the client must not substitute current pipeline edges.

`Trigger`: `{id,pipeline_id,node_id,name,trigger_type,is_active,webhook_token,webhook_url,webhook_header_url,webhook_token_path_deprecated,has_signing_secret,cron_expression,webhook_payload_map,monitoring_filters,last_triggered_at}`. Types: `manual|schedule|webhook|monitoring`. Treat webhook token as a secret: concealed by default, never in analytics or general logs.

## Playbook catalog and authoring

All paths below are relative to `/servers/api/playbooks/`.

| Method/path | Request | Response / behavior |
|---|---|---|
| GET `?q=&category=&kind=` | Optional filters | `{success,playbooks:Playbook[],count}` |
| GET `{id}/` | — | `{success,playbook:Playbook}` with published content |
| POST `create/` | `name`, `description?`, `kind?` (`ansible|runbook`), `category?`, `tags?`, `source_yaml` or nonempty `tasks` | `{success,playbook}`; source safety enforced |
| POST `{id}/update/` | Metadata/content fields; preserve concurrency fields required by service | `{success,playbook}`; bundled content must use draft-file API; non-owner capabilities enforced |
| POST `{id}/delete/` | — | `{success}`; archive operation, requires delete capability |
| POST `{id}/restore/` | — | `{success,playbook}`; owner scope |
| POST `{id}/duplicate/` | — | `{success,playbook}`; requires export capability |
| GET `{id}/draft/` | — | `{success,draft}`; requires edit |
| PUT `{id}/draft/` | `expected_draft_version` (alias `expected_version`), `source_yaml?`, `tasks?`, `content_format?` | `{success,draft}`. HTTP 409 `playbook_draft_conflict` contains current version/hash; do not overwrite on retry |
| GET `{id}/draft/files/?view=current|base|published` | Non-editors can request only `published` | `{success,view,tree}` |
| GET `{id}/draft/file/?view=...&path=...` | File path | `{success,view,file:{path,content,size_bytes,sha256,is_entrypoint,draft_version}}` |
| PATCH `{id}/draft/file/` | `path,content,expected_draft_version,expected_bundle_hash` | `{success,file,draft,tree}`; 409 on stale write |
| GET `{id}/revisions/` | — | `{success,published_revision_id,revisions}`; up to 100; readers see published revision only |
| POST `{id}/revisions/` | `expected_version?`, `message?` | HTTP 201 `{success,revision}`; immutable snapshot of draft |
| GET `{id}/revisions/{revision}/` | — | `{success,revision}` including content, access/safety checked |
| POST `{id}/revisions/{revision}/publish/` | — | `{success,published_revision_id,revision}`; publish capability |
| POST `{id}/revisions/{revision}/rollback/` | `message?` | `{success,revision}`; publish capability, creates restored revision |
| GET `{id}/revisions/{revision}/export/` | — | Download response, export capability; bundle safety checked |
| GET `ansible/status/` | — | `{success,ansible}` runtime diagnostics |
| GET `guided/` | — | `{success,recipes}` |
| POST `guided/generate/` | `slug` (alias `recipe`), `params`, `save:false` for preview | `{success,playbook,preview?}` |
| GET `templates/` | — | `{success,templates}` |
| POST `templates/{slug}/install/` | — | `{success,playbook}` |

### Import and compatibility

* `POST import/` JSON `{content|yaml,path|filename,save:false}` previews raw YAML. Commit is the same request with `save:true,expected_content_hash`; content drift rejects commit. Response preview includes parsed tasks and source preview; committed response includes playbook.
* `POST import/preview/`: multipart `bundle` (alias `file`), `entrypoint?`, `project_path?`; returns `{success,preview}`.
* `POST import/commit/`: same file, `expected_content_hash`, `expected_project_path` if a project path was selected, plus name/description/category/visibility/tags. Returns HTTP 201 `{success,playbook:{id,name,category,visibility},revision:{id,number,content_hash,bundle_hash},bundle:{id,content_hash,file_count,size_bytes,scan_status},preview}`. Changing archive or selected directory after preview yields 409.
* `POST import/gitlab/preview/`: JSON `{project_url,ref?,path?,token?,entrypoint?}` -> `{success,preview,source}`; `POST import/gitlab/commit/` adds `expected_content_hash` and metadata.
* `POST {id}/gitlab/refresh/preview/`: token/entrypoint; refreshes the saved source preview. Commit requires `expected_content_hash,expected_entrypoint,expected_base_revision_id` and token; stale base/source rejected.
* `POST compatibility/analyze/`: `{source_yaml,inventory_bindings?,syntax_check?}` -> `{success,report}`.
* `POST compatibility/adapt/`: `{source_yaml,inventory_bindings?,instruction?,provider_binding?}` -> `{success,proposal}`.
* Saved variants `{id}/compatibility/analyze/` and `adapt/` additionally understand `path`, target `server_ids/group_ids`; return `{success,report|proposal,base}`. Apply at `POST {id}/compatibility/apply/` requires adapted YAML and the captured base/concurrency metadata. Inspect returned base and current view contract before submission; never auto-apply a proposal or rebuild its base from guesses. `GET {id}/compatibility/revisions/` lists adaptation history.

### Target bindings, grants and execution

| Method/path | Request | Response / permission |
|---|---|---|
| GET `{id}/bindings/` | — | `{success,bindings}`; per-current-user profiles; edit or run capability |
| POST `{id}/bindings/` | `name,selector_mappings?,variable_values?,secret_references?,secret_values?,remove_secret_names?,options?,is_default?` | HTTP 201 `{success,binding}` |
| PATCH `{id}/bindings/{binding}/` | Same fields and `expected_version?` | `{success,binding}` |
| DELETE `{id}/bindings/{binding}/` | — | `{success}` |
| GET `{id}/shares/` | — | `{success,shares}`; share capability |
| POST `{id}/shares/` | `principal_type:user|group,principal_id,role?,expires_at?,capabilities?` | HTTP 201 `{success,share}`; explicit project members only |
| DELETE `{id}/shares/{share}/` | — | `{success,share}`; revoke |
| GET `{id}/shares/candidates/?q=&limit=` | Limit 1–50 | `{success,candidates:{users,groups}}`; share capability |
| POST `inventory/preview/` | `server_ids?,group_ids?,inventory_bindings?,playbook_id?` | Authorized inventory and resolved hosts |
| POST `{id}/revisions/{revision}/validate/` | `binding_profile_id?,server_ids?,group_ids?,inventory_bindings?,variable_names?` | `{success,validation}`; validate or run capability |
| POST `{id}/run/` | `revision_id?,binding_profile_id?,server_ids?,group_ids?,inventory_bindings?,extra_vars?,engine:auto|ansible|shell,concurrency?,dry_run?,become?,tags?,skip_tags?,limit?,master_password?` | `{success,run}`; run capability; server authority and immutable revision preflight enforced server-side |

Validation takes variable **names**, execution may take sensitive values. Do not persist password or runtime extra vars in localStorage. Backend always repeats exact-revision runtime preflight when launching. A validation success does not mean an execution happened.

## Playbook runs and reports

| Method/path | Request | Response |
|---|---|---|
| GET `runs/` | — | `{success,runs}` latest 50 owned runs |
| GET `runs/history/?limit=&cursor=&status=&playbook_id=&q=` | Limit 1–100; comma status; descending id cursor | `{success,items,page:{limit,next_cursor,has_more},filters}` |
| GET `runs/{run}/` | — | `{success,run}` with hosts and bounded redacted live log |
| GET `runs/{run}/report/` | `If-None-Match?` | `{success,report}` plus ETag; 304 unchanged |
| GET `runs/{run}/hosts/{server}/` | `If-None-Match?` | `{success,host}` plus ETag |
| GET `runs/{run}/log/?after=&limit_chars=` | Cursor; limit 1–120000 | `{success,text,cursor,next_cursor,start_cursor,end_cursor,has_more,truncated,reset_required,state_version}` |
| GET `runs/{run}/retry-context/` | — | `{success,retry_context}` includes failed IDs, can_retry, required variable names; no secret values |
| GET `runs/{run}/export/` | — | Download; terminal runs only, 409 `run_not_terminal` otherwise |
| POST `runs/{run}/cancel/` | — | `{success,run,message?}`; idempotent if already terminal |
| POST `runs/{run}/rerun-failed/` | Fresh `extra_vars?`, `master_password?` | `{success,run}`; exact original immutable revision preflight, 409 if legacy run has none |

No playbook-specific browser WebSocket route is registered. Use active-run bounded polling with cancellation, ETag reports and cursor logs. Stop background polling for terminal states or hidden documents. On `reset_required`, replace the retained log rather than appending duplicated/missing history. Reports explicitly support unknown/estimated totals; never invent a progress percentage.

## Pipelines, templates, canvas and schedules

All paths in this section are relative to `/api/studio/`.

| Method/path | Request | Response |
|---|---|---|
| GET `pipelines/?q=` | Name filter | `PipelineSummary[]` |
| POST `pipelines/` | `name,description?,icon?,tags?,nodes?,edges?,provider_binding?` | HTTP 201 pipeline detail; empty graph creates inactive manual trigger draft |
| GET `pipelines/{id}/` | — | Pipeline detail |
| PUT `pipelines/{id}/` | `name?,description?,icon?,tags?,nodes?,edges?,is_shared?,provider_binding?` | Validated graph detail; synchronizes node triggers |
| DELETE `pipelines/{id}/` | — | `{ok:true}` |
| POST `pipelines/{id}/clone/` | — | HTTP 201 cloned detail |
| GET `pipelines/{id}/runs/` | — | Latest 50 `PipelineRun[]` |
| POST `pipelines/{id}/run/` | `context:{},entry_node_id?,validate_only:true` (alias `dry_run`) | `{ok,validation:{ok,errors,issues},integration_requirements,risk,dry_run:{executed:false,mode,checks,message},entry_node_id,trigger_type,would_create_run:false}` |
| POST `pipelines/{id}/run/` | Same context/entry, omit validation flag; optional permitted provider binding | HTTP 202 `PipelineRun`; requires active manual trigger; multiple manual triggers require explicit entry |
| GET `node-manifests/` | — | `{version:1,count,nodes:NodeManifest[]}` |
| GET `capabilities/` | — | Capability registry, node catalog, integrations, resource/readiness context |
| GET `readiness/?pipeline_id=&active_only=&entry_node_id=` | IDs repeatable or comma separated | Runtime/integration readiness report; invalid id 400 |
| GET `templates/` | — | `{slug,name,description,icon,category,tags,node_count,graph_version}[]` |
| POST `templates/{slug}/use/` | — | HTTP 201 pipeline detail |
| GET `servers/` | — | Authorized server picker payload |
| GET `triggers/?pipeline_id=` | — | `Trigger[]` |
| POST `triggers/` | `pipeline_id,node_id?,name?,trigger_type?,is_active?,cron_expression?,webhook_payload_map?,monitoring_filters?,signing_secret?` | HTTP 201 trigger; existing node id upserts |
| PUT `triggers/{id}/` | Mutable trigger fields above | Trigger; activation checks graph/branch/context/integrations |
| DELETE `triggers/{id}/` | — | `{ok:true}` |

Schedules are pipeline `trigger/schedule` nodes and associated trigger rows with a five-field cron expression. Editing a pipeline synchronizes trigger nodes. Surface activation errors and last-triggered time. There is no separate Studio schedule execution API to invent.

Webhook configuration should show `webhook_header_url` and `X-WebTerm-Trigger-Token`; token-bearing URL is deprecated. Signed webhooks use `X-WebTerm-Timestamp` and `X-WebTerm-Signature`. The receive endpoint is an external integration contract, not a general UI Run action.

## Pipeline run realtime and control

* `GET runs/` -> latest 100 owned/project-visible `PipelineRun[]`; `GET runs/{id}/` -> single run.
* `POST runs/{id}/stop/` -> `{ok:true,live_executor:false,runtime_control}`. Cancels dispatch and persists stop request.
* `POST runs/{id}/resume/` with `{confirm_non_idempotent?:true}`; use `can_resume`. HTTP 409 can require explicit confirmation for re-execution with side effects; show affected nodes and ask for a deliberate action before resubmitting.
* `GET dead-letters/?status=open|resolved|all` -> up to 200 failed-attempt items; `POST dead-letters/{id}/resolve/` with `{note?}` -> `{ok,item}`. Resolve is an operator acknowledgment, not a retry.
* Approval `GET runs/{run}/approve/{node}/?token=...` returns a no-store **HTML confirmation page**, not JSON; GET never records approval. `POST` accepts `{token,decision:'approved'|'rejected',response_text?}` and requires CSRF plus assigned approver authorization. A pipeline owner is not automatically its assigned approver. Run/WS state intentionally never exposes approval tokens, so the product must use delivery links or manually supplied authorized token rather than fabricate approve buttons that cannot work.

WebSocket: `/ws/studio/pipeline-runs/{run_id}/live/` using session authentication. Anonymous closes 4001, inaccessible closes 4003. Current websocket ACL requires `studio` feature and **pipeline ownership**; unlike REST it has no staff cross-owner/project bypass. Fetch REST detail first, connect for owned active run, and retain a REST reconciliation path if WS cannot connect or events are missed.

Actual event payloads (the consumer spreads the original event **after** its short type alias, so dotted types win):

```ts
{ type: 'pipeline.node.event', node_id: string, event_type: string, data: unknown }
{ type: 'pipeline.node.state', node_id: string, state: NodeState }
{ type: 'pipeline.status', status: PipelineRunStatus, ...extra }
{ type: 'control_ack', action: 'stop', ok: true }
```

The client can accept the short aliases `node_event|node_state|run_status` defensively, but dotted types are emitted by current runtime source. Client message `{action:'stop'}` exists; prefer CSRF-protected HTTP stop for a consistent mutation/error path. There is no initial snapshot or heartbeat/replay contract in this consumer.

## AI pipeline drafts

* `POST pipelines/assistant/`: `{user_message,pipeline_name?,pipeline_id?,nodes?,edges?,selected_node?,history?:{role,content}[],intent?:create|edit|validate|fix_run,draft_mode?,last_validation_errors?,last_run_summary?,provider_binding?,idempotency_key?}` -> assistant proposal/validation/risk/graph patch. This by itself does not save a pipeline.
* `GET assistant/drafts/`: last 25 visible sessions; `POST assistant/drafts/` with assistant payload -> HTTP 201 draft session.
* `GET assistant/drafts/{id}/` -> session; `DELETE` marks discarded (applied drafts cannot be discarded).
* `POST assistant/drafts/{id}/revise/`: `{user_message,pipeline_name?,nodes?,edges?,selected_node?,intent?,history?,last_validation_errors?,last_run_summary?}` -> revised session.
* `POST assistant/drafts/{id}/validate/` -> `{draft,...validation result}`.
* `POST assistant/drafts/{id}/use-template/`: `{template_slug}` -> session with a new revision.
* `POST assistant/drafts/{id}/apply/`: `{create_new?,name?,description?,icon?,tags?}` -> `{draft,pipeline}`. Explicit application; invalid or dangerous draft is rejected. Saving a draft does not execute its operations.

Session: `{id,status,intent,title,user_goal,source_pipeline_id,applied_pipeline_id,selected_node_id,created_at,updated_at,applied_at,latest_revision}`. States: `drafting|needs_input|ready|invalid|blocked|applied|discarded`. Latest revision: `{id,session_id,user_message,created_at,preview_nodes,preview_edges,response}`; response has `reply,node_patch,graph_patch,validation,risk,requirements,assumptions,questions,resource_plan,node_explanations,warnings,patch_summary,suggested_next_actions,confidence`.

## Skills, MCP and saved agent configs

| Method/path | Payload / response |
|---|---|
| GET `skills/`, GET `skills/{slug}/` | Summary array/detail; includes access fields `can_edit,can_share,is_owner,owner,shared_users,access_mode`, detail includes skill content/metadata |
| PUT `skills/{slug}/` | Metadata `name,description,service,category,safety_level,ui_hint,tags,guardrail_summary,recommended_tools,runtime_policy`; owner/staff. Staff-only `is_shared,shared_user_ids` |
| GET `skills/templates/` | Template catalog |
| POST `skills/scaffold/` | `name,description,slug?,template_slug?,service?,category?,safety_level?,ui_hint?,tags?,guardrail_summary?,recommended_tools?,runtime_policy?,with_scripts?,with_references?,with_assets?,force?`; -> HTTP 201 `{ok,skill,validation}` |
| POST `skills/validate/` | `{slugs?:string[],strict?:boolean}` -> `{results,summary:{skills,errors,warnings,is_valid,strict}}` |
| GET `skills/{slug}/workspace/` | Authorized file tree/workspace metadata |
| GET `skills/{slug}/workspace/file/?path=` | File payload including content, editable metadata |
| POST/PUT `skills/{slug}/workspace/file/` | `{path,content}` -> `{ok,file,validation}`; text max 500000 UTF-8 bytes |
| DELETE `skills/{slug}/workspace/file/` | `{path}` -> `{ok,validation}`; `SKILL.md` cannot be deleted |
| GET `mcp/`, GET `mcp/{id}/` | MCP array/detail |
| POST `mcp/`, PUT `mcp/{id}/` | `name,description?,transport:stdio|sse,command?,args?:string[],env?:object,url?,headers?:object`, staff-only sharing fields. Runtime command/URL policy may return 403 |
| DELETE `mcp/{id}/` | `{ok:true}`, owner/staff |
| POST `mcp/{id}/test/` | -> `{ok:boolean,error:string|null}`; owner/staff, policy checked; false is a real failed connection, not HTTP failure |
| GET `mcp/{id}/tools/` | Live inspection payload (server info/capabilities/tools with schemas); readable shared entry may still be denied runtime inspection by policy |
| GET `mcp/templates/` | Template array containing transport/command/args/env defaults |
| GET `agents/`, GET `agents/{id}/` | Saved Studio agent config array/detail |
| POST `agents/`, PUT `agents/{id}/` | `name,description?,icon?,system_prompt?,instructions?,model?,max_iterations?,allowed_tools?,sudo_policy?,skill_slugs?,mcp_server_ids?,server_scope_ids?,provider_binding?`; staff-only sharing |
| DELETE `agents/{id}/` | `{ok:true}`, owner/staff |
| GET `share-users/` | Staff-only shared-user picker |

MCP detail: `{id,name,description,transport,command,args,env,secret_env_keys,url,headers,is_shared,shared_user_ids,shared_users,owner,owner_username,is_owner,can_edit,can_share,access_mode,last_test_ok,last_test_at,last_test_error}`. Non-editors receive empty env/headers/secret key arrays. Preserve redacted secrets; never echo placeholders as user-entered values.

`GET/POST notifications/` is staff-only and gated by `studio_notifications`; GET masks saved SMTP/Telegram credentials, POST returns `{ok,saved}`. `POST notifications/test-telegram/` and `test-email/` send real messages and are explicit UI actions only, never background readiness probes.

## Recommended vertical slices

1. **Automation library**: searchable playbook and workflow tables with genuine empty/error/loading states; compact metadata; contextual create/import/template actions; execution state links.
2. **Playbook workspace**: route by id; published/draft distinction; YAML editor or bundle tree; save with version token; conflict panel preserving local work; revision create/validate/publish; binding profile drawer; explicit target selection and reviewed launch; grants behind capabilities.
3. **Execution detail**: separate playbook and pipeline typed adapters; consistent status/timing/target summaries; host or node table; controlled log stream; cancellation and retry/resume with exact runtime confirmation; report/export only when backend allows.
4. **Workflow canvas**: canvas dominates the page; server node manifests drive searchable palette and schema forms; React Flow type adapter preserves backend node types; source handles follow manifest; accessible property panel; dirty/saving/saved/error state; validate before launch; node-linked errors; node run statuses. Heavy graph editor lazy-loaded.
5. **Draft assistant**: persisted draft sessions, question/answer conversation, preview graph, explicit validation and apply actions; runtime errors stay visible. Applied pipeline opens without running it.
6. **Schedules**: table of trigger rows joined to pipeline names; cron, enabled state, next configuration action and last triggered timestamp. Add/change schedules through graph or trigger contract; show activation failures with remediation links.
7. **Tooling catalog**: skills and MCP each have searchable tables and focused detail editors; shared/read-only status visible; MCP test and discovered tool schemas; skills metadata/workspace/validation. Saved Studio agents configure server/tool/skill scope using these catalogs.

## Verification anchors and remaining risks

* Backend tests read: `tests/test_studio_capabilities.py` covers node manifest schemas/approval metadata; `tests/test_studio_pipeline_v2_api.py` covers validation-only runs, approval CSRF/assigned identities and token redaction; `tests/test_playbook_run_report_api.py` covers unknown progress, ETag, logs/cursors, terminal-only export and redaction. Relevant broader gates include playbook workspace, bundle/GitLab import, runtime preflight, pipeline resume and schedules tests.
* Contract mismatch to handle in frontend: dotted pipeline websocket event types; REST-versus-WS staff access; no replay/initial snapshot; successful HTTP with `{ok:false}` for MCP tests; version-conflict 409; unknown progress totals; approval token intentionally absent from run detail.
* Import/compatibility/report internals contain richer schemas than this compact document. During each implementation slice inspect that backend serializer/helper before typing the exact detail payload; never infer a mutation payload from displayed JSON.
* Runtime/browser verification remains required against the current service configuration; source contracts alone do not establish production readiness.
