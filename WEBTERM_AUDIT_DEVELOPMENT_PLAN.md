# WebTerm audit development plan

Дата среза: 2026-05-20

Назначение: подробный план после продуктово-технического аудита WebTerm. Документ дополняет `PROJECT_REVIEW_ACTION_PLAN.md` и разбивает замечания на безопасные задачи, которые можно отдавать отдельным агентам/разработчикам.

## Короткий вывод

Аудит в целом полезный и направление верное: WebTerm стоит фокусировать как web-first Ops/DevOps платформу, а не распыляться на WinUI-клиент и экспериментальные обходные слои. Но часть рекомендаций нельзя делать прямым удалением "сразу": в коде есть совместимые shim-модули, живые импорты, тесты и существующие зашифрованные данные. Правильная стратегия: сначала dependency/discovery, затем маленькие миграционные PR, затем удаление legacy.

Главные приоритеты:

1. Security hardening: права shared server, единый execution policy gate, redaction, shell safety, encryption migration.
2. Repo/product cleanup: desktop decision, passwords shim removal, `servers.mcp_tool_runtime` import migration, frontend toolchain cleanup.
3. DevOps expansion: Kubernetes read-only observability first, then guarded actions; GitOps/PR-based remediation before direct write; CI/CD visualization.
4. Operability: time-series metrics, audit trail, worker/scheduler clarity, performance profiling.

## Подтверждение замечаний по коду

| Замечание | Статус | Что найдено |
|---|---:|---|
| WinUI desktop избыточен | Частично подтверждено | `desktop/` содержит отдельный WinUI scaffold, WebView2 bridge и API client. Это отдельная поверхность поддержки. Нужен продуктовый decision: удалить, заморозить или оставить как experimental. |
| `passwords/` мертвый код | Почти подтверждено | `passwords/encryption.py` только re-export из `servers.encryption.PasswordEncryption`. Нужно проверить внешние импорты, затем удалить модуль. |
| `servers/mcp_tool_runtime.py` нарушает границы | Подтверждено как legacy shim | Файл сам помечен deprecated и re-export-ит `studio.mcp_tool_runtime`, но его еще импортируют `servers/agent_engine.py`, `servers/multi_agent_engine.py` и тесты. Нельзя удалять до миграции импортов. |
| Shell safety на regex | Подтверждено | `app/tools/safety.py` использует regex-каталог. Это лучше, чем простой один regex, но AST/token parsing нужен для обфускаций, shell chaining и quoted/subshell случаев. |
| PBKDF2 100k слабоват | Подтверждено | `servers/encryption.py` использует `PBKDF2HMAC(... iterations=100000)`. Нужна versioned encryption migration, иначе старые secrets сломаются. |
| Redaction без entropy | Подтверждено | `app/agent_kernel/memory/redaction.py` покрывает известные паттерны/ключи, но нет Shannon entropy/high-entropy fallback. |
| N+1 / pagination | Частично подтверждено | Есть `select_related`/`prefetch_related` в ряде мест, но монолитные views большие. Нужен endpoint-level profiling, а не общий "везде добавить". |
| `ast.literal_eval` блокирует event loop | Частично спорно | В `store.py` heavy memory API в основном имеет async wrappers через `sync_to_async`. Конкретный `_try_parse_list_literal()` стоит профилировать, но это не очевидный P0. |
| ORM tools в `app/tools` нарушают границы | Подтверждено как архитектурный smell | `app/tools/ssh_tools.py` и `app/tools/server_tools.py` завязаны на `servers` domain, но используются существующими runtime paths. Перенос нужен через compatibility shim. |

## Принципы выдачи задач агентам

- Одна задача = один bounded scope и один ожидаемый результат.
- Для удаления legacy сначала отдельная read-only задача: найти импорты, тесты, runtime entrypoints, документацию.
- Security changes идут с тестами до/после.
- Не смешивать продуктовую фичу и архитектурный cleanup в одном PR.
- Не трогать unrelated dirty files и не удалять локальные артефакты без явного подтверждения.

Шаблон для выдачи:

```text
Task type: discovery | implementation | tests | docs
Scope: <paths>
Goal: <one concrete objective>
Constraints:
- Do not commit or push.
- Do not touch unrelated files.
- Do not print secret values.
- Preserve backward compatibility unless task explicitly says otherwise.
Return:
- summary
- files inspected
- files changed
- tests/checks run
- risks/open questions
```

## Phase 0 - Decisions before implementation

### D0.1 Desktop strategy decision

Decision: выбрать один вариант.

- `archive`: удалить из активного продукта, сохранить только историческую заметку/ветку.
- `freeze`: оставить в репозитории, но выключить из roadmap, CI и документации как experimental.
- `productize`: выделить владельца, CI build, release channel и parity matrix с SPA.

Рекомендация: `freeze` на короткий срок, затем `archive`, если нет реального пользователя desktop-клиента. Для desktop experience лучше PWA, а Tauri/Electron рассматривать только после web parity.

### D0.2 Product positioning

Рекомендация: позиционировать WebTerm как "AI-assisted Ops control plane":

- SSH/RDP и Linux UI остаются incident/debug layer.
- Studio становится automation/runbook layer.
- AI memory становится context layer, а не самостоятельной фичей ради фичи.
- Новые изменения серверов должны по умолчанию идти через plan -> approval -> apply -> verify, а для IaC через PR/MR.

## Phase 1 - P0 security and safety

### A1. Shared server permissions matrix

Task type: implementation

Scope:

- `servers/models.py`
- `servers/views/_views_all.py`
- `servers/consumers/ssh_terminal.py`
- `servers/consumers/rdp_terminal.py`
- `servers/sftp.py`
- `app/tools/server_tools.py`
- `tests/test_servers_api_smoke.py`

Problem:

`ServerShare` сейчас фактически дает общий доступ к серверу через `_accessible_servers_queryset()`. У модели есть `share_context`, но нет явных прав `view/connect/execute/file_read/file_write/admin`.

Implementation:

1. Добавить granular permissions в `ServerShare` или отдельную related-модель:
   - `can_view`
   - `can_connect_terminal`
   - `can_execute_commands`
   - `can_read_files`
   - `can_write_files`
   - `can_use_rdp`
   - `can_view_context`
   - `can_admin_share`
2. Ввести helper уровня domain:
   - `get_server_access(user, server) -> ServerAccess`
   - `require_server_access(user, server, capability)`
3. Заменить risky endpoints с `_accessible_servers_queryset()` на capability checks.
4. Добавить отрицательные тесты для shared user.

Acceptance:

- Shared user с view-only не может открыть SSH execution, RDP, write/delete/chmod/chown/upload.
- Owner сохраняет полный доступ.
- Existing shares получают совместимые default permissions через migration.

### A2. Unified execution policy gate

Task type: implementation

Scope:

- `app/agent_kernel/permissions/engine.py`
- `app/tools/safety.py`
- `app/tools/ssh_tools.py`
- `app/tools/server_tools.py`
- `studio/pipeline_executor.py`
- `studio/mcp_client.py`
- `servers/services/terminal_ai/`
- `tests/test_agent_and_pipeline_policy_enforcement.py`

Problem:

Разные execution paths используют разные guardrails. Pipeline/MCP/SSH/webhook должны проходить единый policy gate.

Implementation:

1. Описать contract для modes: `PLAN`, `SAFE`, `AUTO_GUARDED`, `ADMIN`.
2. Вынести общий `ExecutionPolicyDecision`:
   - actor/user
   - target server/tool/url
   - operation kind
   - command/args preview redacted
   - risk categories
   - required approval
3. Подключить gate к SSH command, MCP call, webhook/http MCP destination, file write/delete.
4. Добавить allowlist/blocklist для outbound URLs и запрет private/localhost SSRF по умолчанию.

Acceptance:

- Tests доказывают, что direct pipeline nodes не обходят policy.
- Dangerous command требует approval или блокируется в SAFE mode.
- Webhook/MCP HTTP не ходит в localhost/private ranges без явного allowlist.

### A3. Shell safety parser upgrade

Task type: implementation

Scope:

- `app/tools/safety.py`
- `tests/test_command_safety.py`
- `requirements-mini.txt`
- `requirements.txt`

Problem:

Regex-каталог ловит много простых случаев, но shell можно обойти quotes, variables, command substitution, chained commands.

Implementation:

1. Добавить parser/tokenizer layer. Предпочтительно `bashlex`, если совместим с Python 3.10+ и Windows dev workflow.
2. Сохранить текущий regex-каталог как fallback.
3. Нормализовать command chain:
   - pipes
   - `&&`, `||`, `;`
   - subshell `$()`, backticks
   - quoted executable names
4. Вернуть richer verdict с категориями и parse errors.
5. Добавить tests на обфускации:
   - `r"rm" -rf /tmp/x`
   - `$(echo rm) -rf /tmp/x`
   - `curl ... | bash`
   - `bash -c 'rm -rf /tmp/x'`
   - base64 decode to shell

Acceptance:

- Existing tests pass.
- New evasive dangerous commands are detected.
- Safe read-only commands do not regress.

### A4. Versioned credential encryption migration

Task type: implementation

Scope:

- `servers/encryption.py`
- `servers/models.py`
- migrations under `servers/migrations/`
- views/tools that decrypt server secrets
- tests around server credentials

Problem:

`PasswordEncryption` uses PBKDF2-HMAC SHA256 with 100000 iterations. Changing directly will break existing encrypted values.

Implementation:

1. Introduce encrypted payload format:
   - version
   - kdf
   - iterations/memory/time/parallelism
   - salt
   - ciphertext
2. Support decrypting legacy payloads.
3. Add encrypt v2 using Argon2id if dependency is acceptable; otherwise PBKDF2 600000+ as fallback.
4. Re-encrypt-on-write and optional management command `rotate_server_secrets`.
5. Add tests for legacy decrypt and v2 roundtrip.

Acceptance:

- Old credentials still decrypt.
- New credentials are stored with version metadata.
- Rotation command reports counts without printing secret values.

### A5. Redaction entropy fallback

Task type: implementation

Scope:

- `app/agent_kernel/memory/redaction.py`
- `tests/test_memory_redaction.py`
- log/activity writers found by `rg "logger\\.|log_user_activity|payload|args|output"`

Problem:

Known token patterns are covered, but random high-entropy secrets without key hints may survive.

Implementation:

1. Add Shannon entropy scorer for candidate strings.
2. Gate by length and character mix to reduce false positives.
3. Exclude common hashes/checksums where useful, or tag separately as `high_entropy_candidate`.
4. Apply redaction helper consistently to logs/activity/pipeline output excerpts/MCP args.

Acceptance:

- Random API-like strings are redacted even without `token=` key.
- Normal hostnames, package versions, UUID-like IDs and common paths are not over-redacted.
- Logs/activity tests prove no raw secret values.

## Phase 2 - Legacy cleanup and architecture boundaries

### B1. Remove `servers.mcp_tool_runtime` shim safely

Task type: implementation

Scope:

- `servers/mcp_tool_runtime.py`
- `studio/mcp_tool_runtime.py`
- `servers/agent_engine.py`
- `servers/multi_agent_engine.py`
- `app/test_studio_pipeline_features.py`
- `tests/test_tools_and_policy_units.py`

Implementation:

1. Change imports from `servers.mcp_tool_runtime` to `studio.mcp_tool_runtime`.
2. Update monkeypatch targets in tests.
3. Run targeted tests.
4. Delete `servers/mcp_tool_runtime.py`.

Acceptance:

- `rg "servers\\.mcp_tool_runtime"` returns nothing.
- MCP-bound agent tests pass.
- No behavior change in tool description/execution.

### B2. Remove `passwords/` compatibility module

Task type: implementation

Scope:

- `passwords/`
- imports across repo
- `web_ui/settings/base.py`
- tests

Implementation:

1. Verify no active import depends on `passwords.encryption`.
2. If external compatibility is not required, delete `passwords/`.
3. If compatibility is required for one release, keep a deprecation note but remove from docs.

Acceptance:

- `rg "passwords"` has no runtime import except historical docs/changelog, or no hits.
- Django `INSTALLED_APPS` remains clean.

### B3. Desktop archive/freeze

Task type: docs or implementation depending on D0.1

Scope:

- `desktop/`
- `README.md`
- CI/build scripts if any
- product docs

Implementation options:

- Freeze: add `desktop/README.md` status banner, remove from active quickstart/roadmap, ensure no CI depends on it.
- Archive: delete `desktop/` after explicit approval and update docs.

Acceptance:

- New developer does not assume WinUI is a supported surface.
- Product roadmap points to SPA/PWA as canonical client.

### B4. Move ORM-bound server tools into server domain

Task type: implementation

Scope:

- `app/tools/ssh_tools.py`
- `app/tools/server_tools.py`
- `servers/tools/`
- callers in `core_ui`, `servers`, `studio`, `app/agent_kernel`
- tests

Implementation:

1. Create `servers/tools/` and move ORM-bound implementations there.
2. Keep `app/tools/*` compatibility re-export for one step.
3. Update first-party imports.
4. Keep truly generic safety/base classes in `app/tools`.

Acceptance:

- Domain dependency direction is clearer: generic app kernel does not own server ORM tools.
- Compatibility shims can be removed in a later task.

### B5. View monolith split by domain

Task type: implementation

Scope:

- `servers/views/_views_all.py`
- `core_ui/views/_views_all.py`
- `studio/views/_views_all.py`
- matching `urls.py`

Implementation:

1. Start with one slice only, for example server file manager endpoints.
2. Move code into `servers/views/files.py`.
3. Keep URL names and response shapes stable.
4. Add smoke tests for moved endpoints.

Acceptance:

- `_views_all.py` shrinks.
- No URL/response regression.

## Phase 3 - Product expansion: DevOps workflows

### C1. Kubernetes discovery/read-only integration

Task type: implementation

Scope:

- new or existing nearest app: likely `servers` for infrastructure targets, plus `studio` for pipeline nodes
- frontend Linux UI/Servers pages
- secret storage/encryption layer

Recommendation:

Do not start with "AI can run kubectl freely". Start with read-only inventory and logs.

Data model:

- `KubernetesCluster`
- encrypted kubeconfig/credential reference
- namespace allowlist
- RBAC profile: read-only, guarded-admin

Read-only API:

- list namespaces
- list workloads/pods/services/ingress
- pod status/events
- logs tail
- describe workload

AI/tooling:

- `kubectl` wrapper with namespace/resource allowlist.
- Structured parser for YAML/JSON manifests.
- Policy gate before apply/delete/scale/restart.

Acceptance:

- A user can attach a cluster and inspect pods/logs from UI.
- AI can answer read-only K8s questions without mutating the cluster.
- Mutating commands are blocked or approval-gated.

### C2. Kubernetes guarded actions

Task type: implementation after C1

Scope:

- K8s tool wrapper
- Studio pipeline nodes
- policy engine
- audit log

Implementation:

1. Add dry-run support: `kubectl apply --dry-run=server -o yaml`.
2. Show diff/plan before apply.
3. Gate actions by namespace/resource kind.
4. Require verification step after apply/restart/scale.

Acceptance:

- No direct `kubectl delete/apply` without plan and approval.
- Every mutation has audit event and verification result.

### C3. GitOps / PR-based remediation

Task type: implementation

Scope:

- `studio`
- agent runtime
- new integration module for GitHub/GitLab
- frontend Studio run UI

Problem:

For production DevOps, agents should prefer PR/MR changes to direct server edits when the target is IaC/config.

Implementation:

1. Add repository connection model:
   - provider: GitHub/GitLab
   - repo URL
   - credential reference
   - allowed branches/path allowlist
2. Add tools:
   - create branch
   - propose file patch
   - run tests/lint command if configured
   - create PR/MR
3. Agent policy:
   - if task touches IaC/app config, prefer PR path.
   - direct server write only for incident/runbook-approved cases.

Acceptance:

- Agent can create a PR/MR with diff, summary, verification and rollback note.
- Direct writes remain available but are visibly risky and policy-gated.

### C4. CI/CD visualization in Studio

Task type: implementation after C3 discovery

Scope:

- `studio/models.py`
- `studio/views`
- frontend Studio runs/pipeline pages

Implementation:

1. Read-only provider adapters:
   - GitHub Actions workflow runs/jobs/log excerpts
   - GitLab pipelines/jobs/log excerpts
2. Map external CI status into Studio run context.
3. Show status, failed job, relevant logs, retry/re-run action only with permission.

Acceptance:

- Studio can show CI status for connected repo.
- Agent can use failed CI logs as context for PR fixes.

## Phase 4 - Observability and operations

### D1. Time-series metrics foundation

Task type: implementation

Scope:

- `servers/models.py`
- `servers/monitor.py`
- `servers/views`
- frontend monitoring/Linux UI

Recommendation:

Do not model this as "graphs for L0/L1/L2 memory" first. Start with operational metrics: CPU/RAM/disk/network/load/service status, then add AI memory pipeline health metrics.

Implementation:

1. Add `ServerMetricSample` or extend `ServerHealthCheck` with normalized time-series fields.
2. Retention/downsampling policy.
3. API for range queries.
4. Frontend charts using existing chart library.
5. Add AI memory metrics:
   - event count
   - episode count
   - dream duration
   - compaction failures
   - revalidation queue size

Acceptance:

- UI can render last 1h/24h/7d charts.
- Agent prompt can request incident context around a time window.

### D2. Audit trail / evidence pack

Task type: implementation

Scope:

- `core_ui/audit.py`
- `servers/run_events.py`
- `studio/run events`
- frontend run pages

Implementation:

1. Standardize event schema for:
   - who
   - what target
   - policy decision
   - redacted inputs/outputs
   - approval
   - verification
2. Add exportable incident evidence pack for agent runs/pipeline runs.

Acceptance:

- For every mutation, user can see actor, command/tool, approval, result and verification.
- Secrets are redacted in evidence.

### D3. Background workers and scheduler clarity

Task type: implementation/docs

Scope:

- `servers/management/commands/`
- `studio/management/commands/`
- `docker-compose.production.yml`
- `render.yaml`
- docs/README

Implementation:

1. Define required workers:
   - monitor
   - memory dreams
   - scheduled pipelines
   - agent execution plane
   - watchers
2. Add production compose services or document unsupported pieces.
3. Expose worker heartbeat status in Settings.

Acceptance:

- Production deployment has explicit worker processes.
- Settings worker status matches actual heartbeat.

## Phase 5 - Performance and quality

### E1. Endpoint performance profiling

Task type: discovery

Scope:

- `servers/views/_views_all.py`
- `core_ui/views/_views_all.py`
- `studio/views/_views_all.py`
- frontend pages that load large lists

Implementation:

1. Identify top endpoints:
   - servers list
   - server detail
   - command history
   - memory overview
   - studio pipelines/runs
   - settings users/activity
2. Add query-count tests for 3-5 most important endpoints.
3. Add pagination where lists can grow.
4. Apply `select_related/prefetch_related` only with measured benefit.

Acceptance:

- Query counts are documented.
- Large-list endpoints have pagination/limits.
- No blind prefetch of huge relations.

### E2. Frontend canonical app/toolchain cleanup

Task type: implementation

Scope:

- root `package.json`
- root `vite.config.ts`
- root `src/` if present
- `ai-server-terminal-main/package.json`
- README scripts

Problem:

There are root frontend scripts and a full frontend app under `ai-server-terminal-main/`. This confuses developer workflow.

Implementation:

1. Decide canonical frontend location: likely `ai-server-terminal-main/`.
2. Make root scripts delegate clearly to canonical app or remove root frontend build if unused.
3. Update README quickstart.

Acceptance:

- New developer has one obvious frontend workflow.
- CI/build commands use the same canonical path.

### E3. Settings and AI Memory UI consolidation

Task type: implementation

Scope:

- `ai-server-terminal-main/src/App.tsx`
- `ai-server-terminal-main/src/pages/SettingsPage.tsx`
- `ai-server-terminal-main/src/pages/settings/SettingsMemoryPage.tsx`
- `ai-server-terminal-main/src/lib/api.ts`
- `servers/views/_views_all.py`

Implementation:

1. Decide canonical Settings route/layout.
2. Remove or migrate legacy `SettingsPage.tsx` memory UI.
3. Align policy fields with backend contract.

Acceptance:

- One AI Memory settings UI.
- Policy update payload matches backend fields exactly.

## Suggested agent assignment order

1. A1 Shared server permissions matrix.
2. A2 Unified execution policy gate.
3. A5 Redaction entropy fallback and egress redaction.
4. A4 Versioned credential encryption migration.
5. A3 Shell safety parser upgrade.
6. B1 Remove `servers.mcp_tool_runtime` shim.
7. B2 Remove `passwords/` compatibility module.
8. E2 Frontend canonical app/toolchain cleanup.
9. E3 Settings and AI Memory UI consolidation.
10. D3 Background workers and scheduler clarity.
11. C1 Kubernetes read-only integration.
12. C3 GitOps / PR-based remediation.
13. C4 CI/CD visualization.
14. D1 Time-series metrics.

Rationale: сначала закрываем риск исполнения команд/секретов/доступов, затем убираем legacy, затем добавляем K8s/Git/CI. Иначе новые интеграции увеличат blast radius поверх еще не укрепленной security-модели.

## Additional concerns from review

### 1. Auto-actions should be treated as a product risk

Для Ops-продукта ключевая ценность не в том, что AI "может выполнить команду", а в том, что он делает это проверяемо:

- план;
- риск-категория;
- explicit approval;
- выполнение;
- verification;
- rollback note;
- audit evidence.

Это должно стать общим UX-контрактом для SSH, MCP, K8s, GitOps и CI/CD.

### 2. Memory candidates should not become hidden automation

AI memory и skill drafts полезны, но auto-promotion в operational skill может быть опасным. Рекомендация: все `automation_candidate:*` и `skill_draft:*` показывать как suggestions, а не превращать в активную автоматизацию без review.

### 3. PWA is better first desktop step than Electron/Tauri

Если нужен desktop-like UX:

- добавить manifest, icons, installability;
- offline shell only where safe;
- notifications for runs/alerts;
- deep links to terminal/run pages.

Нативная оболочка нужна только если появятся реальные local OS integrations: локальный SSH agent, VPN checks, filesystem bridge, tray notifications.

### 4. K8s should be cluster inventory before cluster mutation

Kubernetes сразу с `kubectl apply/delete` создаст большой риск. Лучший MVP:

- attach cluster;
- inventory;
- logs/events;
- explain failing pods;
- generate remediation plan;
- then guarded dry-run/apply.

### 5. GitOps should be the default path for non-incident changes

Правило продукта: если изменение можно сделать через репозиторий, AI должен сначала предложить PR/MR. Direct SSH write остается для incident break-glass сценариев.

## Definition of done for this roadmap

- Security P0 tasks have regression tests.
- Legacy shims removed or explicitly documented as frozen.
- Web frontend is the canonical client.
- Dangerous operations share one policy/audit contract.
- K8s/Git/CI integrations start read-only or PR-based before mutating production.
- Settings/Memory/Workers have one clear UI and deploy story.

