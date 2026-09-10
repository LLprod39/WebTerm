# Kubernetes — подтверждённые контракты нового frontend

Источник: текущие `kubernetes_ops/urls.py`, `views.py`, отдельные `*_views.py`, `serializers.py`, `admin_models.py`, `permissions.py`, `services/*`, `consumers.py`. Старый frontend и история Git не использовались. Дата проверки: 2026-09-02.

## Доступ и модель ответа

Все маршруты `/api/kubernetes/` требуют аутентификацию и feature `kubernetes`. Provider CRUD/probe/sync требуют дополнительно `is_staff`. Наличие общей feature не даёт admin-доступ: backend вычисляет capabilities из `kubernetes_admin_read`, `kubernetes_admin_write`, `kubernetes_break_glass`, `kubernetes_secret_read` и runtime flags.

`GET capabilities/` → `{success,modes:[{id,feature,granted,active,purpose,capabilities}],workflows:[{id,mode,available,requestable,mutates_state,requires_session,feature_required,runtime_flag,runtime_enabled,transport_flag,transport_enabled,requirements,blocked_reason}],summary,runtime_flags,blocked_capabilities}`.

Ключи workflows: `safe_cockpit`, `diagnosis_draft`, `action_request`, `live_resource_explorer`, `logs_stream`, `secret_values`, `dry_run_apply`, `apply_yaml`, `patch`, `scale`, `rollout_restart`, `delete`, `pod_exec`, `port_forward`, `node_maintenance`, `node_drain`, `cluster_terminal`, `node_debug`. UI не считает `requestable` разрешением выполнить операцию. На backend сохраняются окончательные проверки срока, scope, владельца сессии, approval, ownership, provider credentials, runtime policy.

Ошибки содержат `{success:false,error,code,payload?}` и HTTP 4xx/5xx. Общий API-клиент отклоняет также логический `success:false` при HTTP 200. Чтения/изменения могут создавать audit events. Проверки провайдера вызывают настоящие внешние API; это не mock status.

## Инвентарь и обзор

| Метод и путь | Ответ / параметры |
|---|---|
| GET `readiness/` | `status,ready_for_sidebar,pilot_sidebar,summary,checks:[{id,status,detail,required}],access_policy,worker_state` и подробные readiness evidence |
| GET `overview/`, `diagnostics/summary/`, `release/summary/` | агрегаты backend, источник не live Kubernetes API |
| GET `clusters/` | `{clusters:[Cluster]}` |
| GET `clusters/{cluster}/` | `{cluster:Cluster}` |
| GET `clusters/{cluster}/namespaces/` | `{cluster,namespaces}` |
| GET `clusters/{cluster}/namespaces/{namespace}/` | `{cluster,namespace,apps,workloads,pods,network_refs,events,summary,policy}` |
| GET `clusters/{cluster}/workloads/` | `{cluster,workloads}`; fallback app refs могут иметь `app_` ID |
| GET `clusters/{cluster}/pods/` | `{cluster,pods}` |
| GET `clusters/{cluster}/network/` | `{cluster,network_refs}` — ключ не `network` |
| GET `clusters/{cluster}/events/` | `{cluster,events}` |
| GET `workloads/{id}/`, `pods/{id}/`, `network/{id}/` | типизированная сущность `workload` / `pod` / `network_ref`, родительский `cluster`, связанные ресурсы, `events`, `summary`, `policy` |
| GET `workloads/{id}/describe/` | нормализованный describe snapshot |
| GET `pods/{id}/logs/?tail=200` | `{available,source,target,provider,policy,lines,line_count,truncated,message}`; HTTP 200 при unavailable не означает доступные логи |
| GET `helm/releases/`, `fleet/bundles/`, `devtron/apps/` | списки источников доставки; Fleet/Devtron имеют detail GET по ID |
| GET `audit/` | `{events:[{id,action,username,provider,cluster,payload,created_at}]}` |

Cluster ID — `cluster_{database_id}`, прочие ID `namespace_`, `workload_`, `pod_`, `network_`, `app_`, `fleet_`. Namespace detail принимает ID или точное имя. Во frontend имена/ID в URL кодируются. Cluster содержит `name,environment,provider,health,nodes_ready,nodes_total,namespaces,workloads,last_sync_at,sync_status` и freshness. Не выводим свежесть инвентаря как live health.

## Провайдеры

`GET/POST providers/`, `GET/PATCH/POST/DELETE providers/{id}/` — staff only. Поля записи: `name,kind:rancher|devtron,base_url,enabled,auth_mode:none|secret_ref|oidc,labels:{},secret_ref?,secret_value?`.

Сырой токен передаётся только как `secret_value`, backend сохраняет managed secret. Значение существующего секрета API не отдаёт: serializer предоставляет `has_secret_ref,secret_storage,connection_details_visible`. Отсутствующее поле секрета при редактировании сохраняет значение; пустая `secret_ref` может очистить его, поэтому UI не отправляет пустой ref при обычном редактировании.

`POST providers/{id}/probe/ {}` проверяет соединение. `POST providers/{id}/sync/ {dry_run:false}` обновляет инвентарь. `POST sync/ {kind?,dry_run?}` синхронизирует группу. Ответ sync `{success,results:[{provider_id,provider_name,provider_kind,success,clusters,namespaces,workloads,pods,services,ingresses,events,apps,fleet_bundles,error,dry_run}]}`.

## Сессии доступа

`GET admin/sessions/?all=true` — список до 100, all действует только для staff. Detail GET видит **только владелец**, staff для согласования использует список и approve endpoint. `POST admin/sessions/`:

```json
{"cluster_id":"cluster_1","namespace":"team-a","mode":"write","reason":"CHG-123: обновление сервиса","ttl_minutes":30,"allowed_namespaces":["team-a"],"allowed_kinds":["Deployment"]}
```

Режимы в request **`read`, `write`, `break_glass`**, не имена features. Read активен сразу; write/break_glass → `pending_approval`. TTL default/max: read 60/240, write 30/60, break_glass 15/30 минут. Backend фиксирует allowed verbs для режима, пользователь выбирает kinds/namespaces. Отсутствующая область даёт `*`, поэтому UI просит явную область.

Session serializer: `id,mode,status,risk_tier,cluster_id,cluster_name,provider_id,provider_name,namespace,reason,approval_ref,approved_by,approved_at,expires_at,closed_at,allowed_verbs,allowed_kinds,allowed_namespaces,post_review_required,post_review_status,post_review,metadata,created_by,created_at,updated_at`.

| POST `admin/sessions/{uuid}/…` | Тело и условие |
|---|---|
| `approve/` | `{approval_ref}`; staff с правом режима, requester != approver; только pending |
| `revoke/`, `close/` | `{reason}`; owner либо разрешённый backend staff flow; close active only |
| `review/` | `{outcome:accepted|needs_followup|incident_created,summary,evidence_ref?}`; staff break_glass; закрытая/истёкшая аварийная сессия |
| `restricted-context/` | `{include_manifest:boolean}`; выдаёт ограниченный контекст/RBAC manifest, не применяет его |
| `terminal/start/`, `node-debug/start/` | `{reason,include_restricted_context?}` / `{node_name,reason}`; REST **только blocked bridge envelope**, не запущенный terminal |
| `terminal/stop/`, `node-debug/stop/` | `{action_id,reason}`; не подменять реальное закрытие WS этим bridge |

## Live resource explorer

Сессия должна принадлежать текущему пользователю, быть active, иметь нужные verb/kind/namespace. Live provider — Rancher.

`GET admin/clusters/{cluster}/discovery/?session_id=…` → `resource_catalog:{items:[{id,api_version,kind,resource,namespaced,scope,verbs,cluster_available,custom,ui_group,query}],status,counts,truncated}`. `common_resources` содержит fallback registry, его наличие не доказывает доступность API; UI использует обнаруженные `cluster_available` resources.

`GET admin/clusters/{cluster}/resources/` query: `session_id,api_version,kind,resource,namespace,name?,label_selector?,field_selector?,search?,limit?,continue?,include_managed_fields?,include_secret_values?`.
List → `{items,item_count,truncated,continue_token,list_query,ownership_summary,secret_values}`; items — Kubernetes resource + `summary` и `webterm_ownership`. `summary` содержит `phase,ready,replicas,conditions,containers,owner_references,resource_version,generation,creation_timestamp`.

`resources/detail/`, `resources/describe/`, `yaml/`, `resources/events/` используют тот же target query. Detail → `resource,summary,describe,ownership,events:{available,events,event_count,…},secret_values,redacted`.
`yaml/` возвращает **JSON resource и manifest contract**, не строку YAML. `copy_for_apply_recommended:false`; редактирование sanitized snapshot не считается безопасным шаблоном apply.
`logs/` query `session_id,namespace,pod,container?,tail?`; семантика available совпадает snapshot. `nodes/`, `metrics/`, `crds/`, `watch/` — отдельные live read endpoints.

Secret values скрыты по умолчанию. Reveal — explicit `include_secret_values=1` плюс соответствующая feature/flag и active session; списки всегда metadata only.

## Изменение ресурсов

Все POST под `admin/clusters/{cluster}/resources/`:

| Операция | Тело |
|---|---|
| `schema-validate/`, `dry-run-apply/` | `{session_id,manifest?:object,manifest_yaml?:string,namespace?,resource?}` |
| `apply/` | то же + **`dry_run_action_id`**, `reason` |
| `patch/` | `{session_id,api_version,kind,namespace,name,resource,patch_type:merge|strategic|json,patch:object|array,reason}` |
| `scale/` | `{session_id,api_version,kind,namespace,name,resource,replicas,reason}` |
| `restart/` | тот же target + reason |
| `delete/` | target + `{reason,confirmation,propagation_policy}` |

Dry-run requires **write**, не break_glass. Ответ содержит `action:{id,status},target,submitted,resource,diff_summary,diff:{changes:[{path,operation,before,after}],change_count,truncated},ownership,redacted`. **Diff сравнивает submitted с server dry-run response, не live baseline**. UI прямо сообщает эту семантику.

Apply проверяет свежесть proof, пользователя, exact manifest fingerprint и target; после изменения манифеста/namespace UI сбрасывает proof. Перед mutation — отдельный обзор target/reason; ни auto-run на открытии, ни autoretry mutation нет. Delete confirmation точно `delete {Kind} {namespace}/{name}` либо `delete {Kind} {name}` для cluster scope. Backend дополнительно запрещает protected namespaces, запрещённые owners, credentials/runtimes.

Node POST `nodes/cordon|uncordon|drain/`: `{session_id,node_name,reason,confirmation?,options?}`. Drain exact `drain Node {name}`, параметры `ignore_daemonsets,delete_emptydir_data,force,grace_period_seconds,timeout_seconds,max_pods`; отдельный flag native drain execution. Blocked envelope не отображать выполнением.

## Действия, записи, разбор

`GET admin/actions/` query `all,session_id,cluster_id,verb,status,post_review_status,limit` → `{actions,count,limit,review_summary}`. `post_review_status`: pending/completed/not_ready/required/any/none. Action contains `id,session_id,verb,status,target fields,request_payload_sanitized,diff_summary,response_summary,created_by,created_at,post_review_required,post_review_status`.

`GET admin/actions/{uuid}/report/` → `{report:{action,session,recordings,timeline,summary}}`.
`POST admin/actions/{uuid}/review/ {outcome:accepted|verified|needs_followup|incident_created,summary,evidence_ref?,follow_up_ref?}` — staff и соответствующий write/break-glass mode; terminal statuses only.

`GET admin/recordings/` query `all,session_id,action_id,cluster_id,operation,status,limit` → `{recordings,count,limit}`.
`GET admin/recordings/{uuid}/?event_limit=500` → `{recording,event_limit}`. Recording contains retention/redaction policy, `transcript_stored`, `event_count`, events `{sequence,stream,data,redacted,truncated,original_length,stored_length,…}`. Отсутствующий transcript не трактуется как пустая успешная сессия. UI скачивает только доступное API содержимое.

## WebSocket

Paths `/ws/kubernetes/admin/{logs|watch|exec|port-forward|terminal|node-debug}/{session_uuid}/`.
Logs query `cluster_id,namespace,pod,container?,tail?,follow=1,max_batches=25`; messages `stream_started`, `log_batch:{payload:{available,lines,message,…}}`, `stream_heartbeat`, `stream_stopped`, `stream_error:{message,code,payload}`. Бounded noncontinuous follow закрывается нормально после max batches. UI не возобновляет его автоматически.

Terminal/node-debug запускаются **только** WS с `stream=1` либо `provider_stream=1`, explicit reason и approved break_glass; `node` для node-debug. Events `terminal_started` / `node_debug_started`, `cluster_terminal_output` / `node_debug_output` `{data,stream}`, `terminal_stopped` / `node_debug_stopped`, rejected/error. Client `{type:'stdin',data}`. Connection close прекращает provider transport. Автоматический reconnect для действий, запускающих shell, должен быть отключён.

## Отдельная очередь запросов изменения

Это независимая модель от admin sessions. `actions/request-approval/` POST `{action,target,reason,approval_ref?}` строит preflight/preview/rollback plan. `actions/` GET возвращает requests, `actions/{uuid}/status|report/` GET — статус и доказательства. `actions/{uuid}/approve-external/` POST требует другой staff и approval ref; `actions/execute-approved/` POST request_id проверяет runtime/связанную approved сессию; `verify-external/` сохраняет проверку. `actions/diagnose/` POST `{app_id}` создаёт Studio draft (requires pipelines + owned read-only Kubernetes MCP), не запускает кластерную мутацию.

## Реализовано и ограничения проверки

Реализованы маршруты clusters/namespaces/workloads/pods/network/events; snapshot logs; providers create/edit/probe/sync/delete; readiness/capabilities; scoped sessions create/approve/revoke/close/review; discovery-backed live resource list/details/events/manifest/Secret reveal; bounded WS logs and resource watch; schema/dry-run/apply/patch/scale/restart/delete with review; admin actions/report/post-review and recording inspection/export.

После gap audit добавлены:
- `/requests` и `/requests/:id`: все 9 типов action-request, target forms, dry-run proof selection, peer staff approval, native execute under returned access_policy + selected write session, external/native verification evidence and report/timeline export. Native apply accepts JSON manifest and backend checks the exact fingerprint of the approved proof.
- `/delivery` и `/delivery/:kind/:id`: Helm ownership/conflict review, Fleet detail/partitions/related workloads, Devtron detail/history/values metadata/pods/events/rollback request, diagnosis draft into `/automation/drafts/:id`, staff-only external fallback with explicit audit before navigation.
- `ResourceTools.tsx`: pod exec xterm; Pod/Service port-forward tunnel with HTTP GET helper and UTF-8/Base64 data input; resource watch (20 batches/300 events); metrics snapshots with normalized CPU/memory and source timestamps.
- `ResourceDescription.tsx`: the «Описание и связи» detail tab calls live `resources/describe/` with events/related enabled; typed identity, metadata, owners, conditions, service ports, related Pods/ReplicaSets, independent partial errors and truncation. This read is lazy on tab open and requires an active session.
- `Emergency.tsx`: cluster terminal, node debug, cordon/uncordon/drain with exact drain confirmation, restricted-context/RBAC review.

Interactive mutation transports require explicit review, approved break-glass, capability and transport_enabled. Retry is zero. Closure/unmount/expired session ends connection. Deferred initial connection prevents React StrictMode from starting a discarded first transport. Port-forward works as a browser data tunnel: browser cannot expose a local OS TCP listener. This is an explicit transport limitation, not a fabricated localhost URL.

Validation evidence: scoped ESLint and TypeScript (own files) passed; Vitest 7/7 for action confirmation and dry-run guards; three Playwright Chromium contract fixtures passed against real QA login at isolated frontend8091/backend9001. A fourth fixture for action-request peer approval/policy/verification was added for the parent’s final suite. Fixtures do not claim real Rancher availability. Main8090 user database was not mutated by these tests.

Actual provider acceptance still requires a reachable Rancher/Kubernetes cluster, live approved credentials, transport flags, recording/retention policy and a second user for real approvals. Native execution, shell, tunnel and provider metrics cannot be certified from network fixtures. Product code does not substitute demo output when these dependencies are unavailable.
