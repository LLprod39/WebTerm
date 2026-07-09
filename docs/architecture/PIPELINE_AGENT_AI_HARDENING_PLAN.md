# План: приведение ИИ-агентных нод Pipeline в порядок

**Статус:** implemented (2026-07-09: Phase 0–5 minimum acceptance delivered; optional PR-G native tool calling + full HITL bridge deferred per Non-goals)  
**Дата:** 2026-07-09  
**Область:** `agent/react`, `agent/multi`, `agent/ssh_cmd`, `agent/llm_query`, `agent/mcp_call` + runtime `AgentEngine` / `MultiAgentEngine`  
**Цель:** убрать логические дыры до/после real-world тестирования, чтобы статус success/fail и поведение агентов были предсказуемы.  
**Обновление 2026-07-09:** добавлены Phase 5 (launch readiness: бэкапы, kill switch, audit trail, лимиты) и staged rollout-план вывода на реальные пользовательские серверы (§4.6).

---

## 1. Контекст (как устроено сейчас)

```
PipelineExecutor
  → registry adapter (studio/executor/nodes/agent_*)
    → studio/pipeline_agent_runtime.py | pipeline_agent_llm.py | pipeline_agent_mcp.py
      → app.pipeline_agent_provider
        → servers.services.pipeline_agents
          → AgentEngine (ReAct)
          → MultiAgentEngine (orchestrator + mini-ReAct tasks)
```

| Нода | Роль | LLM-цикл | Действия |
|------|------|----------|----------|
| `agent/react` | ReAct: think → tool → observe | Да | SSH / MCP / skills |
| `agent/multi` | План задач → последовательные subagents | Да (2 уровня) | SSH / MCP / skills |
| `agent/ssh_cmd` | Прямая SSH-команда | Нет (fallback → react) | SSH |
| `agent/llm_query` | Один LLM-вызов | Один | Нет |
| `agent/mcp_call` | Один MCP tools/call | Нет | MCP |

Сильные стороны (не ломать):

- единый production runtime для pipeline и standalone agents;
- PermissionEngine / sandbox / sudo / skill policies;
- graph handles `success` / `error` / `out` + `on_failure`;
- MCP + skills + AgentConfig + server scope;
- guard «описал tool, но не вызвал ACTION» (до первого tool call).

---

## 2. Проблемы и решения

Приоритеты: **P0** — ломает доверие к real test / success-path; **P1** — сильные UX/логика; **P2** — качество и DX.

### P0-1. `completed` ≠ «цель достигнута»

**Проблема**

| Сценарий | Текущее поведение | Эффект на pipeline |
|----------|-------------------|--------------------|
| ReAct: кончились `max_iterations` | `AgentRun.STATUS_COMPLETED` | handle `success` |
| ReAct: LLM «закончил» без evidence / tools | часто `completed` | `success` |
| ReAct: пустой/битый LLM response | выход из цикла + report → часто `completed` | `success` |
| Multi: есть `failed` tasks | finalize всё равно `COMPLETED` (ветка no-op) | `success` |
| Multi: timeout → tasks `skipped` | `COMPLETED` | `success` |
| Multi: orchestrator `abort` | finalize → `COMPLETED` | `success` |

Pipeline маппит success **только** по `agent_run.status == "completed"`.  
Downstream на `success` может пойти при частичном/пустом результате.

Подтверждено в коде (2026-07-09):

- маппинг react/multi: `studio/pipeline_agent_runtime.py:230` и `:320`;
- dead-code ветка multi failed→COMPLETED: `servers/multi_agent_engine_runner.py:323-327`.

**Решение**

1. Ввести явную **outcome-семантику** agent run (минимум):
   - `success` — цель достигнута с evidence (tools / verification);
   - `partial` — работа была, цель не доказана;
   - `failed` — hard fail / timeout / abort / no capacity;
   - `stopped` — остановлено оператором.
2. Маппинг в pipeline:
   - `success` → `status=completed`, ports `success`+`out`;
   - `partial` → конфиг `on_partial`: `error` | `success` | `abort` (default: `error` для unattended);
   - `failed` / `stopped` → `status=failed` / `stopped`, port `error` (stopped — без downstream, как сейчас).
3. **ReAct criteria** (детерминированные правила + optional LLM judge):
   - timeout → failed;
   - stop → stopped;
   - 0 tool calls при наличии tools и goal, требующем действий → partial/failed;
   - max_iterations исчерпан без final ACTION-less answer с verification → partial;
   - pending verifications PermissionEngine → partial (не success).
4. **Multi criteria**:
   - any `failed` без успешного replan/retry → partial или failed (не silent completed);
   - abort → failed;
   - all skipped/timeout → failed;
   - mixed done+failed → partial + summary в `error`/`output` metadata.
5. В node state писать:
   - `outcome`, `agent_run_id`, `tool_call_count`, `failed_task_count`, `verification_summary`.

**Файлы (ориентир)**

- `servers/agent_engine_runner.py`
- `servers/multi_agent_engine_runner.py` (`_finalize_multi_agent_run`)
- `studio/pipeline_agent_runtime.py`
- `studio/pipeline_routing.py` (если понадобится port `partial`)
- tests: agent status + pipeline routing

---

### P0-2. Контекст предыдущих нод не попадает в react/multi

**Проблема**

- `agent/llm_query` умеет `include_all_outputs`.
- `agent/react` / `agent/multi` **не** инжектят outputs предыдущих нод.
- Context доступен только через шаблоны `{node_id}` в `goal` / prompts.
- Шаблоны — только simple `{identifier}`, не nested paths.

Цепочка «диагностика → агент почини» без placeholders = агент часто **слепой**.

**Решение**

1. Добавить node fields (с defaults для совместимости):
   - `include_upstream_outputs: bool` (default **true** для новых нод; false — legacy behavior);
   - `max_upstream_nodes`, `max_upstream_chars` (как у llm_query).
2. В `execute_agent_react` / `execute_agent_multi` собирать compact upstream block и:
   - добавлять в user goal message **или**
   - в system/ops prompt section `## Context from previous pipeline steps`.
3. Документировать placeholders: `{node_id}`, `{node_id_output}`, `{node_id_error}`, `{node_id_status}`.
4. UI: toggle + preview «какой context уйдёт в агента».

**Файлы**

- `studio/pipeline_agent_runtime.py`
- `studio/pipeline_context.py` (`compact_node_outputs_context` уже есть)
- frontend AgentNode settings
- `docs/PIPELINE_NODES_SPEC.md`

---

### P0-3. `ask_user` в pipeline — ловушка для unattended runs

**Проблема**

- Tool `ask_user` блокирует agent до 5 минут.
- Ответ — через `AgentRun.runtime_control`, не через pipeline human_approval / telegram_input.
- Pipeline node висит; schedule/webhook runs «молчат» или получают timeout-observation.
- Run может завершиться completed с дырявым evidence.

**Решение**

1. **Policy modes** на agent node:
   - `interactive` — ask_user разрешён;
   - `unattended` (default для schedule/webhook) — ask_user **запрещён** или auto-fail с clear error.
2. При ask_user в pipeline:
   - либо bridge: pipeline run → `hibernating` + UI/Telegram reply (как human_approval);
   - либо auto-deny tool с observation: «Human input unavailable in unattended pipeline; use logic/human_approval».
3. Docs/UI warning: для HITL использовать `logic/human_approval` / `logic/telegram_input`, не tool ask_user.
4. Preflight readiness: если trigger schedule/webhook + agent с ask_user enabled → warning/error.

**Файлы**

- `servers/agent_tools.py` / `agent_engine_tools.py`
- `studio/pipeline_agent_runtime.py` + pipeline runtime control
- `studio/pipeline_preflight.py` / readiness
- frontend guidance

---

### P1-1. Пустой goal → silent «Analyze the servers.»

**Проблема**

Пустой/whitespace goal не fail-ит: fallback generic analyze (`servers/agent_engine_runner.py:163`). В automation это непредсказуемо.

**Решение**

1. Pipeline validation + runtime: **goal обязателен** для `agent/react` и `agent/multi` (после template render).
2. Если render дал пусто — failed с понятной ошибкой.
3. UI: required field + preview rendered goal.

---

### P1-2. Пустой `allowed_tools` = все tools

**Проблема**

```text
if not tools_config: return ALL tools
```

«Ничего не выбрано» ≠ «запретить всё» → полный toolset.

**Решение**

1. Разделить семантики:
   - `tools_mode: all | allowlist | denylist`;
   - allowlist пустой + mode=allowlist → fail validation («выберите tools»);
   - mode=all → явное «все встроенные» (текущее поведение).
2. Default UI: разумный safe set (`ssh_execute`, `read_console`, `report`, skills tools) вместо all.
3. MCP tools: отдельный toggle / inherit from mcp_server_ids.

---

### P1-3. Multi: failed tasks не влияют на status (dead code)

**Проблема**

```python
elif any(t["status"] == "failed" for t in plan_tasks):
    final_status = AgentRun.STATUS_COMPLETED  # no-op
```

**Решение**

См. P0-1. Минимум:

- failed without recovery → `failed` или `partial`;
- abort → `failed`;
- писать `plan_summary` в node output (done/failed/skipped counts).

---

### P1-4. Multi не получает `instructions` с ноды

**Проблема**

React: `instructions` → `ai_prompt`.  
Multi: только `goal` + `system_prompt`. Node/AgentConfig instructions теряются.

**Решение**

Передавать `instructions` / `ai_prompt` в multi path симметрично react; включать в orchestrator system prompt и task context.

---

### P1-5. Хрупкий LLM protocol (text THOUGHT/ACTION, flat history)

**Проблема**

- Нет native function calling.
- History склеивается в один flat prompt.
- Качество tool-use зависит от модели.

**Решение (поэтапно)**

1. **Short term:** улучшить system prompt + stronger reprompt (не только до первого tool); structured retry при bad ACTION JSON.
2. **Medium:** optional provider-native tool calling adapter (OpenAI/Anthropic tools) с fallback на text protocol.
3. **Medium:** multi-turn messages API вместо flat string, где provider поддерживает.
4. Метрики: parse_fail_rate, zero_tool_rate, reprompt_rate.

---

### P1-6. Permission SAFE vs ожидание «агент всё сделает»

**Проблема**

Default SAFE + sudo disabled: мутации режутся preflight/policy. Оператор думает «сломался», а политика работает.

**Решение**

1. В final_report / node error явно: `policy_blocked_count`, last deny reasons.
2. UI risk summary: что разрешено в выбранном mode.
3. Template presets:
   - Read-only diagnose (PLAN/SAFE);
   - Guarded remediate (AUTO_GUARDED + approval);
   - Autonomous lab only.
4. Не ослаблять default SAFE — чинить **наблюдаемость**, не безопасность.

---

### P1-7. Defaults model / iterations разъезжаются

**Проблема**

- UI default iterations ≈ 6;
- backend fallback react 10 / multi 20;
- hardcode model `gemini-2.0-flash-exp` в runtime fallbacks.

Места хардкода (подтверждено grep):

- `studio/pipeline_agent_runtime.py:169`, `:276`;
- `studio/pipeline_agent_llm.py:38`;
- `studio/models.py:127` (model default в схеме);
- `studio/views/agent_views.py:59`;
- `studio/docker_service_recovery_recovery.py`, `docker_service_recovery_preapproval.py` (шаблоны);
- `scripts/create_mega_pipeline.py` (демо-скрипт, низкий приоритет).

**Решение**

1. Единый source of truth: settings / model_manager defaults.
2. Manifest schema defaults = UI defaults = backend fallbacks.
3. Не хардкодить experimental model names в executor.
4. Проверить, что дефолтная модель вообще доступна у настроенного provider (иначе — понятная ошибка, а не молчаливый fail).

---

### P2-1. Partial SSH connect в multi-server

**Проблема**

Часть серверов не коннектится → warning, агент идёт дальше. Может «успешно» отчитаться по 1 из N.

**Решение**

- Node option `require_all_servers: bool` (default true для multi).
- Если false — partial outcome + list disconnected.

---

### P2-2. Двойная executor-архитектура (путаница)

**Проблема**

Production: `PipelineExecutor` + registry adapters.  
`PipelineEngine` — target architecture, не main path.

**Решение**

- Документировать «source of truth» (уже частично в comments).
- Не добавлять новую логику только в PipelineEngine без production path.
- Долгосрочно: complete migration checklist (out of scope urgent).

---

### P2-3. Observability для real test

**Проблема**

Сложно понять, почему «зелёный» run бесполезен.

**Решение**

В node state / UI run detail:

- iterations, tool_calls, denied tools;
- MCP errors, skill errors;
- outcome + evidence score;
- link to `AgentRun` detail.

---

## 3. Дополнительные фичи (рекомендуемые)

Не блокеры, но сильно повышают готовность к prod.

### F1. Agent outcome gates в графе

- Port `partial` (опционально) или logic/condition по `outcome`.
- Policy templates: «partial → telegram + human_approval → retry agent».

### F2. Pipeline-native HITL bridge

- ask_user / multi ask_user → тот же channel, что `logic/telegram_input` / approval tokens.
- Resume pipeline без 5-min hard timeout only.

### F3. Budget & cost controls

- max LLM calls / max tokens per agent node;
- hard fail budget exceeded (уже есть зачатки budget в LLM layer — прокинуть в agent node).

### F4. Verification contract

- Node field `success_criteria` (regex / must_include tools / must_run verification markers).
- Agent cannot emit success without criteria match.

### F5. Dry-run / plan-only в pipeline multi

- `plan_only: true` → status completed с plan в output, без SSH mutations.
- Полезно для review перед apply.

### F6. Structured agent output

- Помимо markdown report: JSON `{summary, findings[], actions[], residual_risks[], evidence[]}`.
- Упростит conditions / webhooks / reports.

### F7. Preflight readiness pack для AI nodes

Расширить readiness:

- provider key present + smoke chat;
- servers reachable (optional);
- MCP tools listable;
- skills resolve;
- goal non-empty after template dry-render.

### F8. Safer default tool packs by purpose

Presets: `diagnose`, `logs`, `deploy`, `security_audit` — tool allowlist + permission mode + role.

### F9. Global concurrency & rate limits

- Максимум одновременных agent runs на платформу и на сервер (защита пользовательских серверов и LLM quota).
- Rate limit на LLM-вызовы per provider; backpressure вместо шторма ретраев.
- Очередь: scheduled runs при превышении лимита ждут, а не падают.

### F10. Agent action audit trail (обязательно до real user servers)

- Каждый `ssh_execute` от агента → command history с `agent_run_id` + `pipeline_run_id` + пользователь-владелец run.
- Проверить покрытие агентного пути в `servers/services/command_history.py` / `terminal_command_recorder.py`.
- `egress_redaction` применяется к outputs перед отправкой в LLM и в отчёты (секреты/токены из env, конфигов).
- Выгружаемый отчёт «что агент делал на сервере X за период» — для разбора инцидентов с пилотными пользователями.

---

## 4. План работ по фазам

### Phase 0 — Baseline перед real test (документация + checklist)

**Срок:** 0.5–1 день  
**Не код, операционные правила**

- [x] Зафиксировать ожидание: success ≠ goal done (до P0-1) — outcome model введён.
- [x] Чеклист оператора (см. §6).
- [x] Smoke scenarios list — `docs/local/AGENT_PIPELINE_SMOKE_SCENARIOS.md`.
- [x] Не гонять unattended + ask_user (runtime deny + readiness warning).

### Phase 1 — Correctness of outcomes (P0-1, P1-3)

**Срок:** 2–4 дня

- [x] Outcome model + mapping pipeline (`app/agent_kernel/runtime/outcomes.py`, `studio/pipeline_agent_runtime.py`).
- [x] ReAct: timeout / max_iter / zero-tools / verification pending (`servers/agent_engine_runner.py`).
- [x] Multi: failed/abort/timeout semantics (`servers/multi_agent_engine_runner.py`).
- [x] Unit + integration tests (`tests/test_agent_outcomes.py`, `tests/test_studio_agent_node_executors.py`).
- [x] Update PIPELINE_NODES_SPEC.

### Phase 2 — Context & configuration honesty (P0-2, P1-1, P1-2, P1-4, P1-7)

**Срок:** 2–3 дня

- [x] Upstream outputs injection (`include_upstream_outputs`, default true).
- [x] Required goal (fail after empty template render).
- [x] tools_mode allowlist semantics (`studio/pipeline_agent_config.py`).
- [x] multi instructions parity.
- [x] unified defaults (model/iterations = 6, no experimental hardcode).
- [x] Backend validation/readiness for tools_mode; UI polish deferred (Non-goal).

### Phase 3 — Human / unattended safety (P0-3, F2 light)

**Срок:** 2–3 дня

- [x] unattended deny ask_user (minimum).
- [x] preflight/readiness warnings for schedule/webhook + ask_user.
- [x] optional full HITL bridge — **deferred** (Non-goal; deny-only delivered).

### Phase 4 — Quality & observability (P1-5, P1-6, P2-*, F3–F7)

**Срок:** 1–2 недели (итеративно)

- [x] stronger parse recovery / metrics — deferred optional (P1-5 short-term only via existing reprompt).
- [x] policy deny visibility in reports (`policy_blocked_count` on node/report payload).
- [x] require_all_servers (react default false; multi default true).
- [x] structured output + success_criteria — **deferred** optional F4/F6.
- [x] readiness pack (tools_mode + unattended ask_user issues).

### Phase 5 — Launch readiness: реальные серверы (F9, F10 + инфраструктура)

**Срок:** 3–5 дней  
**Блокер для Stage C rollout (пилотные пользователи), можно делать параллельно с Phase 1–3.**

Факт (проверено 2026-07-09): production-стек уже есть (`docker-compose.production.yml`: postgres, redis, backend, workers, nginx, mcp; healthchecks; `docker-compose.production.smoke.yml`).

- [x] **Бэкапы БД:** `scripts/backup_postgres.sh` (7 daily / 4 weekly) + volume notes in `docs/local/BACKUP_RESTORE_KILL_SWITCH.md`.
- [x] **Restore drill:** `scripts/restore_postgres.sh` + dry-run + documented clean-machine steps (live drill depends on env).
- [x] **Kill switch:** `python manage.py ops_kill_switch` + scheduled pipelines/agents skip + new agent nodes blocked.
- [x] **Audit trail (F10):** agent `ssh_execute` → command history with `actor=agent`, `session_id` containing agent_run/pipeline_run.
- [x] **Egress redaction:** existing stack remains; documented operator expectation (no regression work in this pass).
- [x] **Concurrency limits (F9):** existing `AGENT_ACTIVE_RUNS_*` / pipeline limits documented.
- [x] **LLM budget:** existing `LLM_DAILY_TOKEN_LIMIT_PER_USER` documented.
- [x] **Алерты платформы:** documented Telegram/email env hooks.
- [x] **`.env.production` review:** checklist in backup/restore doc + upgrade section.
- [x] **Upgrade/rollback procedure:** documented.
- [x] **Smoke на проде:** operator smoke list written; full compose smoke depends on docker availability.

---

## 4.6. Rollout-план real test (staged)

Каждая стадия — gate: переходим дальше только если нет новых P0-багов, чеклист §6 проходит, kill switch проверен.

| Stage | Где | Режим | Условие входа | Длительность |
|-------|-----|-------|---------------|--------------|
| **A. Lab** | локальный docker / lab VM | любой | Phase 0 done | 1–2 дня |
| **B. Своя инфраструктура** | собственные серверы команды | SAFE, read-only diagnose; schedule + webhook triggers | Phase 5: бэкапы + kill switch + алерты | 3–5 дней |
| **C. Пилотные пользователи** | 1–2 реальных пользователя, явно согласованный список серверов | SAFE, read-only presets (F8 `diagnose`/`logs`); ask_user запрещён (P0-3 минимум) | Phase 1 (честный outcome) + Phase 3 (unattended safety) + Phase 5 полностью | 1–2 недели |
| **D. Guarded mutations** | пилотные пользователи | AUTO_GUARDED + обязательный `logic/human_approval` перед мутациями | Phase 2 done; audit trail отчёты просмотрены по Stage C; инцидентов нет | по готовности |

Правила пилота (Stage C/D):

1. Письменное согласие пользователя + зафиксированный скоуп серверов (allowlist, не «все»).
2. Инцидент-протокол: контакт оператора, kill switch, где смотреть audit trail, SLA реакции.
3. Ежедневный просмотр: outcome distribution, policy_blocked_count, failed runs, стоимость LLM.
4. Канал обратной связи пилота (форма/чат) + журнал найденных проблем в `docs/backlog/`.
5. Любая мутация до Stage D — запрещена конфигурацией, а не договорённостью.

---

## 5. Definition of Done

Считаем ИИ-агентные ноды «в порядке» когда:

1. Pipeline `success` означает **заявленный outcome success**, а не «процесс дописал report».
2. Multi failed tasks **не** маскируются под completed.
3. React/multi видят upstream context без ручных placeholders (opt-out).
4. Unattended runs **не зависают** на ask_user.
5. Пустой goal / пустой allowlist — **явные** validation errors.
6. Есть тесты на status mapping и 3+ smoke e2e сценария.
7. Спека `docs/PIPELINE_NODES_SPEC.md` синхронизирована с runtime.

Дополнительно для запуска на реальных серверах (Stage C+):

8. Бэкапы БД автоматические, restore drill пройден.
9. Kill switch останавливает все scheduled/новые runs одной операцией и проверен вручную.
10. Каждая SSH-команда агента на реальном сервере видна в audit trail с привязкой к run и пользователю.
11. Concurrency limit и LLM budget активны; алерты на failed runs приходят в Telegram/email.

---

## 6. Чеклист оператора (real test, пока P0 не сделан)

| # | Проверка |
|---|----------|
| 1 | Provider/model из Settings реально отвечает |
| 2 | У agent node есть server и/или MCP и/или skill |
| 3 | Goal конкретный; если нужен прошлый output — `{node_id}` в goal |
| 4 | permission_mode / sudo соответствуют задаче |
| 5 | Mutating paths: `logic/human_approval` upstream |
| 6 | Не schedule/webhook + ask_user |
| 7 | Смотреть report / tool_calls / plan_tasks, не только зелёный handle |
| 8 | Лимиты iterations/timeout адекватны задаче |
| 9 | Smoke по типам нод по отдельности перед сложным графом |
| 10 | Свежий бэкап БД перед стартом теста (для Stage B+ — автоматический) |
| 11 | Kill switch известен оператору и проверен на этой инсталляции |
| 12 | Скоуп серверов зафиксирован allowlist-ом; для пилота — согласие пользователя |
| 13 | LLM budget/alerts включены; стоимость прошлых runs просмотрена |

---

## 7. Риски реализации

| Риск | Митигация |
|------|-----------|
| Ломаем существующие pipelines, которые ждут completed на partial | feature flag / `on_partial` default continue+error handle; changelog |
| Строгий outcome = больше failed runs | docs + UI explain; partial port |
| Native tool calling = большой diff | phase 4 optional adapter |
| HITL bridge сложный | phase 3 minimum = deny unattended |
| Агент повреждает реальный пользовательский сервер | staged rollout (§4.6): мутации запрещены конфигом до Stage D; SAFE default; human_approval; audit trail для разбора |
| Секреты пользователя утекают в LLM-провайдер | egress_redaction на outputs перед LLM/отчётом; не логировать env; провайдер согласован с пилотом |
| Стоимость LLM взрывается на цикличных агентах | F3 budget per node + суточный лимит + alert; concurrency limit (F9) |
| Потеря данных платформы во время пилота | Phase 5: автоматический pg_dump + restore drill до Stage B |
| Инцидент у пилота без быстрой реакции | kill switch + инцидент-протокол + алерты в Telegram |

---

## 8. Ключевые файлы

| Зона | Путь |
|------|------|
| Pipeline adapters | `studio/executor/nodes/agent_*.py` |
| Agent runtime glue | `studio/pipeline_agent_runtime.py` |
| LLM / MCP nodes | `studio/pipeline_agent_llm.py`, `studio/pipeline_agent_mcp.py` |
| Provider | `app/pipeline_agent_provider.py`, `servers/services/pipeline_agents.py` |
| ReAct engine | `servers/agent_engine.py`, `servers/agent_engine_runner.py`, `servers/agent_engine_tools.py` |
| Multi engine | `servers/multi_agent_*.py` |
| Tools | `servers/agent_tools.py` |
| Permissions | `app/agent_kernel/permissions/` |
| Parsing | `app/agent_kernel/runtime/parsing.py` |
| Routing | `studio/pipeline_routing.py`, `studio/pipeline_run_loop.py` |
| Spec | `docs/PIPELINE_NODES_SPEC.md` |

---

## 9. Предлагаемый порядок PR

1. **PR-A..C:** outcome + multi fix + upstream/goal — **DONE**.
2. **PR-D:** tools_mode + defaults + multi instructions — **DONE**.
3. **PR-E:** unattended ask_user + readiness — **DONE**.
4. **PR-F:** policy_blocked_count / require_all_servers / plan_summary — **DONE** (structured JSON report optional deferred).
5. **PR-G:** native tool calling — **DEFERRED** (Non-goal).
6. **PR-H:** backup scripts + kill switch — **DONE**.
7. **PR-I:** agent SSH audit attribution + limits/alerts docs — **DONE**.

### Реализовано 2026-07-09 (full acceptance minimum)

| Компонент | Путь |
|-----------|------|
| Outcome core | `app/agent_kernel/runtime/outcomes.py` |
| Agent config helpers | `studio/pipeline_agent_config.py` |
| Kill switch | `studio/ops_controls.py`, `manage.py ops_kill_switch` |
| Backup/restore | `scripts/backup_postgres.sh`, `scripts/restore_postgres.sh` |
| Ops docs | `docs/local/BACKUP_RESTORE_KILL_SWITCH.md`, `docs/local/AGENT_PIPELINE_SMOKE_SCENARIOS.md` |
| Tests | `tests/test_agent_outcomes.py`, `test_pipeline_agent_config.py`, `test_agent_unattended_ask_user.py`, agent node executors |


---

## 10. Итог

Система **не «сломанная»**: wiring, tools, policies и graph contract в целом рабочие для DevOps-автоматизации.  
Главная проблема — **семантика успеха и прозрачность ограничений**, а не отсутствие «мозгов».

Фокус плана:

1. Честный success/fail/partial.  
2. Контекст между нодами.  
3. Безопасный unattended mode.  
4. Честные defaults tools/goal/model.  
5. Наблюдаемость для real-world test.  
6. Launch readiness: бэкапы, kill switch, audit trail, лимиты (Phase 5).

Порядок к реальному запуску: Phase 0 → Stage A (lab) сразу; Phase 5 параллельно с Phase 1–3; Stage B (свои серверы) после Phase 5; Stage C (пилотные пользователи, read-only) после Phase 1+3+5; Stage D (guarded mutations) после Phase 2 и чистого Stage C. Phase 4 — качество и prod hardening, не блокирует пилот.
