# Server operations and monitoring contracts

Verified against current backend source, 2026-09-02. No historical frontend or Git history used. Client implementations: `frontend/src/api/server-operations.ts`, `frontend/src/api/monitoring-extras.ts`; panels are independently importable.

## Linux operations

Sources: `servers/urls.py`, `servers/views/server_linux_ui.py`, `servers/views/server_linux_ui_workloads.py`, `servers/linux_ui.py`, `servers/linux_ui_resources.py`, `servers/linux_ui_runtime.py`, `servers/linux_ui_commands.py`.

All endpoints below use prefix `/servers/api/{server_id}/ui/`. Authentication, `feature.servers`, **is_staff**, accessible SSH server, and server `connect_terminal` capability are required for reads. Mutations require `execute_command`. The staff gate is distinct from the feature/capability gates. Existing stored/session SSH credentials are resolved by backend; UI must never place a password in query parameters.

All GET responses contain `success`, `server:{id,name,host,username}`, `observed_at`, plus the resource below. Each snapshot is collected via SSH, not a database-only inventory.

| Method and suffix | Parameters | Response resource |
| --- | --- | --- |
| GET `capabilities/` | none | `capabilities:{hostname,current_user,os_name,os_id,kernel,is_systemd,package_manager,commands,available_apps}` |
| GET `overview/` | none | `overview:{hostname,current_user,home_path,cwd,os_name,kernel,uptime_seconds,process_count,load:{one,five,fifteen},memory:{total_mb,used_mb,percent},disk:{mount,total_gb,used_gb,percent}}` |
| GET `services/` | `limit=120` | **top-level** `services:[{unit,name,load,active,sub,description,health,is_active,is_failed}],summary:{total,active,failed,inactive,other},limit` |
| GET `services/logs/` | `service`, `lines` 20–200 | `service_logs:{service,lines,source,content}`; journalctl with systemctl status fallback |
| POST `services/action/` | `{service,action:start|stop|restart|reload}` | `service_action:{success,service,action,dangerous,output,status_excerpt}`, `performed_at` |
| GET `processes/` | `limit` 20–160 (default80) | `processes:{limit,summary:{total,high_cpu,high_memory},top_cpu,top_memory}` |
| POST `processes/action/` | `{pid,action:terminate|kill_force}` | `process_action:{success,pid,action,dangerous,output,still_running,process_excerpt}`, `performed_at` |
| GET `docker/` | none | `docker:{ready,error,summary:{total,running,exited,restarting,paused},containers}` |
| GET `docker/logs/` | `container`, `lines` | `docker_logs:{container,lines,content}` |
| POST `docker/action/` | `{container,action:start|stop|restart}` | `docker_action:{success,container,action,dangerous,output,inspect_excerpt}`, `performed_at` |
| GET `logs/` | `source=journal`, `lines` 20–240, `service` for service source | `logs:{source,service,lines,content,presets:[{key,label,description,available}],available}` |
| GET `disk/` | none | `disk:{summary,mounts,top_directories,large_logs,cleanup_candidates}` |
| GET `network/` | none | `network:{tools:{ip,ss},summary:{interfaces,addresses,routes,listening},interfaces,routes:string[],listening}` |
| GET `packages/` | none | `packages:{package_manager,installed:[{name,version}],updates:string[],summary:{installed_common,update_candidates}}` |
| GET `settings/` | none | `settings:{general,users,crontab,environment,security}` |

Process row: `{pid,user,cpu_percent,memory_percent,elapsed,command,args}`. CPU/memory percentages can be null. `high_cpu` counts >=20%; `high_memory` counts >=10% in the bounded lists.

Docker row: `{id,name,image,state,status,running_for,ports,cpu_percent,memory_percent,memory_usage,network_io,block_io}`. CPU/memory are already formatted strings. `ready:false` is a distinct unavailable Docker daemon state, not an empty successful inventory.

Disk mount: `{filesystem,mount,size_gb,used_gb,available_gb,percent}`. Sized path: `{path,size_mb}`. Summary: `{mounts,critical_mounts,top_directory_mb,largest_log_mb,cleanup_candidates}`; critical means >=90%. Cleanup candidates are up to12 `/tmp` entries older than7 days; no cleanup endpoint exists. Largest sizes can be null.

Network interface: `{name,state,mtu,kind,mac,flags:string[],addresses:[{family,address,scope}]}`. Socket: `{protocol,state,local_address,peer_address,process}`.

Settings general: hostname,time zone as `timezone`,kernel,os_release,uptime,architecture,cpu,total_memory. Users: current_user,sudo_group,accounts(name,uid,home,shell),logged_in,last_logins. Crontab: user_crontab,system_crontab,cron_dirs,timers. Environment: shell,locale,path_directories,variables. Security: ssh_config,firewall,failed_logins,listening_ports. UI intentionally does not render raw `environment.variables`, which may contain credentials.

Capabilities `available_apps` names: overview,files,terminal,ai,text_editor,quick_run,settings,services,logs,processes,disk,network,docker,packages. Service availability requires systemctl, Docker requires docker, network requires ss or ip, packages require apt/dnf/yum. Generic log sources include file fallbacks, so the logs page remains available when journalctl is absent and displays the actual `presets` availability.

Mutation top-level `success` mirrors command outcome; an HTTP200 with `success:false` is an error. UI retains failure output from ApiError.details. Stop/restart can interrupt workloads. SIGTERM vs SIGKILL are separate actions; force/stop confirmation requires the exact PID/unit/container. PID0/1 controls are disabled. No package installation, service enable/disable, network reconfiguration or disk deletion controls are fabricated.

## Server knowledge

Sources: `servers/views/server_knowledge.py`. Authentication + feature.servers + **server.user == request.user**. Shared server edit permission does not authorize knowledge CRUD.

Prefix `/servers/api/{server_id}/knowledge/`:

- GET `?include_inactive=1` returns `{success,items,categories:[{value,label}],include_inactive}`; latest100 by updated time.
- POST `create/` body `{title,content,category,is_active}` → `{success,id}`. Title/content required, max200/8000. New entries use source=manual and confidence=1.
- POST `{knowledge_id}/update/` partial `{title,content,category,is_active,confidence}` → `{success}`. Confidence clamped0..1.
- POST `{knowledge_id}/delete/` `{}` → `{success}`; related manual memory is archived.

Item: `{id,title,content,category,category_label,source,source_label,confidence,is_active,updated_at}`. Categories come from backend choices. Manual updates sync layered memory. Preserve draft inputs on failure; inactive entries are visibly distinct.

## Rollback snapshots

Sources: `servers/views/snapshot_views.py`, `servers/services/snapshot_service.py`. Authenticated. List is filtered by current user. Detail/prepare allow snapshot owner or staff and validate matching server_id.

- GET `/servers/api/{server_id}/snapshots/?limit=100` → `{snapshots:[{id,file_path,command,byte_size,content_truncated,content_hash,created_at,restored_at}]}`.
- GET same `{snapshot_id}/` → `{snapshot:{...row,server_id,user_id,content}}`.
- POST same `{snapshot_id}/restore/` → `{restore_command}`. **Generates a command only; it does not execute restoration.** Truncated content rejects with400. Empty content generates `rm -f <path>`; otherwise a single-quoted heredoc writes content.
- Actual execution is the separate POST `/servers/api/{server_id}/execute/` `{command}` with standard server permissions and audit. Response contains `output:{stdout,stderr,exit_code}`.

Known backend behavior: prepare sets `restored_at` before any command executes. UI does not present this field as a successful restore. Workflow: inspect content/hash/original command → prepare restore → review target+full command → type exact file path → execute → success only with returned exit_code0. No automatic execution after prepare. The fixed heredoc delimiter `_WEUAI_RESTORE_EOF_` can collide with content; UI refuses command preparation when an exact delimiter line is present. Empty content is explicitly presented as deletion before execution.

## Monitoring history, alerts and checks

Sources: `servers/views/server_monitoring.py`, `servers/views/server_monitoring_helpers.py`, `servers/views/server_monitoring_actions.py`.

All normal monitoring endpoints require auth + feature.servers and scope to `_accessible_servers_queryset`.

- GET `/servers/api/{server_id}/health/?hours=24` → `{success,server_id,server_name,checks}` chronological. UI allows6/24/72/168h.
- Health row: `{id,status,cpu_percent,memory_percent,disk_percent,load_1m,load_5m,load_15m,memory_used_mb,memory_total_mb,disk_used_gb,disk_total_gb,uptime_seconds,process_count,response_time_ms,is_deep,checked_at}`. Null metrics remain unknown, not zero. Chart gaps represent missing readings.
- POST `/servers/api/{server_id}/health/check/` `{deep:boolean}` → `{success,check?}`, optionally `cached:true` or `queued:true` (202 when no previous result). SSH only. Endpoint-based cooldown defaults60sec and shared endpoint probe locking. UI distinguishes requested/queued/cached/complete.
- POST `/servers/api/{server_id}/ai-analyze/` optional `provider_binding` → `{success,analysis:string,server_name}`; uses existing health, alerts and recent6 checks. UI relies on server-side AI route for purpose `opssummary`.
- GET `/servers/api/alerts/?server_id=&severity=&resolved=true|false&limit=200` → `{success,alerts}`; max500. Alert `{id,server_id,server_name,alert_type,severity,title,message,is_resolved,resolved_at,created_at,metadata}`.
- POST `/servers/api/alerts/{id}/resolve/` → `{success}`; marks resolved by current user and logs audit.

## Extended insights and certificates

Sources: `servers/views/server_insights.py`, `servers/monitoring/forecasting.py`, `servers/monitoring/ai_insights.py`. **Staff only**; all active platform servers, not active-project scoped.

- GET `/servers/api/admin/insights/?refresh=1` bypasses60sec cache. Response `{success,generated_at,cached?,summary,servers,predictions,certificates,alerts,ai}`.
- Summary: servers_total,healthy,warning,critical,unreachable,unknown,fleet_health_score,fleet_health_worst,active_alerts,predictions_total,predictions_critical,predictions_warning,certificates_total,certificates_expiring_30d,certificates_changed_7d.
- Server: id,name,host,endpoint_key,owner,status,checked_at,sample_at,has_extended_metrics,health_score,cpu_percent,cpu_iowait_percent,cpu_steal_percent,cpu_count,load_1m,memory_percent,memory_available_mb,swap_percent,worst_disk,disk_mounts,net_rx_bps,net_tx_bps,tcp_retrans_per_sec,tcp_established,fd_percent,process_count,zombie_count,top_processes,journal_err_10m,journal_warn_10m,reboot_required,ntp_synchronized,uptime_seconds,spark(cpu,mem,disk arrays),predictions.
- Prediction: `{kind,target,severity,eta_days,predicted_for,current_value,threshold,unit,slope_per_day,confidence,evidence,server_id,server_name}`. Theil-Sen trend estimates; bounded horizon and minimum observations. Empty prediction list is not evidence that no risk exists. Flat predictions deduplicate physical host:port.
- Certificate: `{id,server_id,server_name,port,endpoint,subject,issuer,not_after,days_left,sans,is_active,changed_at,last_checked_at}`; SAN capped10. No certificate edit/renew/delete endpoint is available here.
- AI block `{enabled,running,fleet:AiInsight|null,by_endpoint:Record<endpoint,AiInsight>}`. AiInsight `{id,kind,endpoint_key,server_id,verdict,content,error,model,created_at}`.
- POST `/servers/api/admin/insights/ai/run/` `{server_id?:number,force:true}` → `{success,queued:true}` or `{success,queued:false,running:true}`. Background analysis; UI polls5sec only while running. Disabled AI returns400; no synthetic result.

## Watcher proposals

Sources: `servers/monitoring/watcher_service.py`, `servers/monitoring/watcher_actions.py`, `servers/agents/agent_service.py`, `servers/views/server_monitoring_actions.py`.

- GET `/servers/api/watchers/drafts/?server_id=&status=open,acknowledged&limit=200` → `{success,summary:{open,acknowledged,resolved,suppressed,total},drafts}`. Only accessible servers.
- Draft `{id,server_id,server_name,severity,recommended_role,objective,reasons:string[],memory_excerpt:string[],status,acknowledged_at,acknowledged_by,resolved_at,first_seen_at,last_seen_at,metadata}`. Metadata may contain last_launch_run_id,last_launch_agent_id,last_launched_at,launch_count.
- POST `/servers/api/watchers/scan/` `{server_ids:number[],persist:boolean,limit:100}` → `{success,generated_at,summary:{scanned_servers,critical,warning,drafts},scanned_server_ids,drafts,requested_server_ids,persisted_scan,persisted?:{created,updated,reopened,resolved}}`. Empty IDs means first100 accessible servers. Nonpersistent drafts have no id. Scan uses saved signals/memory, does not launch an agent. Persist may resolve older proposals that no longer have signals.
- POST `/servers/api/watchers/drafts/{id}/ack/` → `{success,draft}`; records acknowledged_by/time.
- POST `/servers/api/watchers/drafts/{id}/launch/` → `{success,draft,agent_id,run_id,status,runs?}` or policy rejection. Creates/reuses a full agent with recommended role and queues it through the execution plane; pilot policy is enforced. UI reviews objective, role and exact server before launch, then links to `/intelligence/runs/{run_id}` when agents navigation is permitted.

No monitoring subscription CRUD exists in this API. Live metric subscriptions are `/ws/monitoring/live/` with `{type:'subscribe',server_ids}` (parent MonitoringPage owns them); group follow/favorite uses existing group subscription endpoint (group implementation owns it). No invented email/SMS subscription settings.

## Monitoring thresholds

GET/POST `/servers/api/monitoring/config/` is staff-only (no feature decorator). GET `{success,thresholds:{cpu_warn,cpu_crit,mem_warn,mem_crit,disk_warn,disk_crit},stats:{total_checks,active_alerts,last_check_at,monitored_servers}}`; POST `{thresholds}` → `{success}`.

Important limitation: POST writes Python module globals for the current process only, not persistent storage or all workers. UI explicitly labels values temporary and explains reset after restart and lack of cross-worker synchronization. Browser validates0..100 and warn<crit; backend currently merely casts float.
