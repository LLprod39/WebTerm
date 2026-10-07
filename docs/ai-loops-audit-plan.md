# Аудит и план AI/LLM-циклов WebTerm

Документ: инвентаризация (фаза 1), выбор формы цикла (фаза 2), self-review (фаза 3).  
База: ветка `cursor/operator-ssh-continuation-35e1`. Реализация — `cursor/ai-loops-audit-149c`.

---

## Фаза 1. Инвентаризация touchpoint’ов

### Легенда форм цикла

| Код | Форма |
|-----|--------|
| **MDT** | Model-driven tool loop: пока модель отдаёт tool_calls — исполняем |
| **ReAct-JSON** | JSON step (`tool` / `done`) |
| **ReAct-TEXT** | THOUGHT/ACTION текстовый протокол |
| **HOST** | Хост оркестрирует очередь; LLM решает next/skip |
| **SS** | Single-shot: один LLM-вызов |
| **KW** | Keyword/heuristic continuation (слабое звено) |

---

### 1. Operator chat — `core_ui/services/operator_loop*.py`

| Поле | Значение |
|------|----------|
| **Файлы** | `operator_loop.py:92–536`, `operator_loop_tool_cycle.py:38–550`, `operator_loop_prompt.py`, `operator_loop_helpers.py`; рантайм `operator_turn_runtime.py` (90s) |
| **Назначение** | Чат «Оператор»: флот, SSH, планы, мутации с Confirm |
| **Форма сейчас** | MDT + **KW** (`user_message_needs_ssh_actions`, `should_continue_after_inventory_only`, до 2 nudges) + plan nudges + empty retry |
| **Стоп** | text-only → `STATUS_DONE` (если heuristics не продолжили); park confirm; error; `MAX_ITERATIONS=16` → final report → `limit`; outer 90s |
| **Tools** | Native `stream_chat_tools`; read auto; mutate → Confirm |
| **Stream** | `token`, `thinking`, `tool_started`, `tool_result`, `confirm_required`, `turn_done`, … |
| **Timeout** | Outer turn 90s; provider stream ~90s; **action-resume без wait_for 90s** |
| **Ошибки** | `error` + RU текст + `turn_done failed`; Antigravity `auth_required` закрывает stream |
| **Confirm** | Mutate park; autonomy/`plan_once`/`autonomous` могут auto-run |
| **Провайдеры** | Один контракт событий; subscription/Antigravity через CLI adapters |
| **Дефекты** | ① Text-only после tool считается финалом → KW-костыль. ② «глянь что с @host» без ключевых слов может не продолжить. ③ Dead branch `iteration_limit_report_done`. ④ 90s на весь multi-step turn. ⑤ Sibling tool_calls обрезаются при park. |

**Известный баг:** `@grafana-01 проверь что крутится` останавливался после `resolve_server` (PR #40 расширил keywords — симптоматично).

**Сохранить из PR #36/#39/#40:** `thread_sensitive=False`, Antigravity auth stream close, 90s turn timeout, legacy secret promotion.

---

### 2. Nova (terminal AI agent) — `servers/services/terminal_ai/agent/loop.py`

| Поле | Значение |
|------|----------|
| **Вход** | `run_agent_loop` ~137; consumer `ssh_terminal_agent_runner.py` |
| **Форма** | ReAct-JSON с явным `tool=done` (+ todos) — **уже правильная** |
| **Стоп** | `done` / max iters / total timeout / user stop / LLM error |
| **Confirm** | Shell gate + `prompt_user` |
| **Дефекты** | Debug `#region agent log` в loop; иначе форма цикла ок |

---

### 3. Full Ops Agent — `servers/agents/agent_engine_runner_loop.py` + `agent_engine.py`

| Поле | Значение |
|------|----------|
| **Форма** | ReAct-TEXT; stop = нет ACTION |
| **Стоп** | Final answer / max iters / session timeout / stop / empty / LLM error |
| **Tools** | SSH/MCP/skills; HITL `ask_user` |
| **Дефекты** | `_should_reprompt_missing_action` **не** репромптит «готово» при 0 tool calls (`_FINAL_COMPLETION_RE` → False) — premature done |

---

### 4. Multi-agent — `multi_agent_*`

| Поле | Значение |
|------|----------|
| **Форма** | Outer plan + per-task ReAct-TEXT |
| **Стоп** | Task: no ACTION + verify; outer: plan_review / abort / timeout |
| **Дефекты** | Parse failure decision → `skip`; в целом MDT-подобно, KW только в routing/roles |

---

### 5. Studio pipeline agent nodes

| Поле | Значение |
|------|----------|
| **Файлы** | `studio/pipeline/pipeline_agent_runtime.py`, `pipeline_agent_config.py` |
| **Форма** | Делегат в Full/Multi (эфемерный ServerAgent) |
| **Дефекты** | Наследуют дефекты Full; defaults max_iters ≈6 |

---

### 6. Fast terminal plan→execute

| Поле | Значение |
|------|----------|
| **Файлы** | `terminal_ai/planning.py`, `decision.py`, consumers |
| **Форма** | HOST + SS decisions per step |
| **Confirm** | ask/agent modes, dry_run |
| **Вердикт** | Оставить HOST; не смешивать с Operator MDT |

---

### 7. AI CLI runners (Antigravity / Codex / Cursor / Grok)

| Поле | Значение |
|------|----------|
| **Файлы** | `ai_cli_runner_manager/adapters/*`, `provider_runtime.py` |
| **Форма** | Один provider-turn → TEXT/TOOL_REQUEST; цикл снаружи |
| **Вердикт** | Транспорт; не дублировать product loop |

---

### 8. MCP

| Поле | Значение |
|------|----------|
| **Файлы** | `app/agent_kernel/mcp_runtime.py`, `studio/mcp/*` |
| **Роль** | I/O бэкенд инструментов внутри Full/Multi/Studio |
| **Вердикт** | Отдельный LLM-цикл не нужен |

---

### 9. Single-shot (оставить SS)

| Touchpoint | Файл (вход) | Timeout / ошибки |
|------------|-------------|------------------|
| Terminal explain | `output_explanation.py` | stream / max_chars |
| Terminal report | `report_generation.py` | SS |
| Memory extraction | `memory_extraction.py` | parse fail → empty |
| Mini agent analysis | `mini_executor.py` + `agent_analysis.py` | 15m wall / 180s analysis |
| Final/task reports | `agent_engine_prompts.py`, multi synthesize | из agentic parent |
| Legacy assistant planner | `assistant_chat.py` `_planner_fallback_turn` | KW routing; Confirm cards |
| Plain `chat_api` | `chat_views.py` | Cursor CLI stream / orchestrator (mini: may be absent) |
| Pipeline assistant / drafts | `pipeline_assistant.py`, `pipeline_draft_views.py` | sync wrap 180s; structured JSON |
| `agent/llm_query` node | `pipeline_agent_llm.py` | max_iterations=1 |
| AI insights | `ai_insights.py` | verdict regex |
| Playbook compatibility AI | `playbook_compatibility_ai.py` | JSON ≤6 edits |
| Agent task AI refine | `server_agent_runs.py` | SS JSON |
| Memory distill | `django_memory_llm.py` | gate + SS |
| Telegram bridge | `assistant_bridge.py` | канал → Operator/fallback |

---

### 10. MARS

| Поле | Значение |
|------|----------|
| **Форма** | Phased CLI orchestration (architect→executor→verify) |
| **Вердикт** | Вне scope product chat loops; KW skill routing ок для фазы |

---

## Фаза 2. План замены циклов

### Принципы целевой модели

**Agentic (Operator, Nova, Full/Multi, pipeline agents):**

1. Пока модель возвращает tool_calls — исполнять (read auto, mutate → Confirm).
2. Промежуточный текст = progress (stream), не финал.
3. Финал: явный `finish`/`done` **или** text-only после достаточных evidence.
4. One-shot self-check «цель достигнута? следующий tool?» при раннем стопе на host-задаче.
5. Plan/todo (уже есть `propose_plan` + PlanTasksPanel) — incomplete plan → continue/pause.
6. Cap шагов + timeout + forced final report на cap.
7. Keyword heuristics — **только fallback** после self-check.
8. Общее ядро политики в `app/core/agentic_loop_policy.py` (без копипасты).

**Single-shot:** без tool-loop; timeout + error surfacing; без KW-continuation.

### Матрица решений

| Touchpoint | Было | Станет | Действие |
|------------|------|--------|----------|
| Operator | MDT+KW primary | MDT + finish_report + self-check primary + KW fallback | **Implement** |
| Nova | ReAct-JSON + done | Без смены формы | Keep; optional debug cleanup later |
| Full Ops | ReAct-TEXT + KW reprompt | + premature «готово» при 0 tools → self-check | **Implement** |
| Multi / pipeline agents | ReAct / delegate | Наследуют Full fix | Indirect |
| Fast terminal | HOST | HOST | Keep |
| AI CLI | Transport | Transport | Keep |
| MCP | Tool I/O | Tool I/O | Keep |
| SS (explain/report/…) | SS | SS | Keep; timeouts already present |
| Pipeline assistant | SS 180s | SS | Keep (deadlock fix PR #36) |

### Operator — целевой алгоритм

```
while True:
  stream LLM(tools)
  on provider error → fail (stream closed)
  if force_final_report → LIMIT + report
  if tool_calls:
     process (read / park mutate / finish_report→DONE)
     if parked: break
     if finished: DONE
     append tool_results; emit progress; continue   # text was progress
  else:  # text-only
     empty retry…
     incomplete plan nudge…
     # PRIMARY model-driven:
     if tools_ran and not ssh_evidence and self_check < 1
        and (inventory_only or @host or needs_ssh):
          self_check++; inject GOAL_SELF_CHECK; continue
     # FALLBACK keywords:
     if should_continue_after_inventory_only and nudges < N:
          nudge; continue
     DONE  # final answer
```

Новый tool: `operator.finish_report({summary})` — read, auto, сигнал явного финала после evidence.

### Shared core

`app/core/agentic_loop_policy.py`:

- `GOAL_SELF_CHECK_NUDGE`, `MAX_GOAL_SELF_CHECKS`
- `messages_have_host_mention`
- `should_goal_self_check(...)`
- переиспользуется Operator (+ при необходимости Full)

### Тесты (обязательные)

1. «глянь что с @grafana-01» → resolve → self-check → SSH read → summary (**без** match «крутится»).
2. Greeting «Привет» → 1 шаг.
3. Mutate → Confirm park.
4. Cap → final report / limit.
5. Provider error → stream ends failed.
6. Full agent: «готово» при 0 tools → reprompt.
7. Регрессии PR #36/#39/#40 не ломать.

### Совместимость UI/stream

Не менять имена событий: `token`, `thinking` (+phase), `tool_started`, `tool_result`, `confirm_required`, `turn_done`, `plan_*`, `error`.

---

## Фаза 3. Self-review плана

| Проверка | Статус |
|----------|--------|
| Все touchpoint’ы из grep покрыты таблицами | ✅ |
| Operator дефект text-after-tool адресован model-driven + finish | ✅ |
| KW demoted to fallback | ✅ |
| Nova/Full/Multi/pipeline/SS/CLI/MCP/MARS классифицированы | ✅ |
| `thread_sensitive=False` не трогаем | ✅ |
| Antigravity auth close не трогаем | ✅ |
| 90s turn timeout сохраняем (не поднимаем без отдельного решения) | ✅ |
| Legacy secret promotion не трогаем | ✅ |
| Plan/todo (plan-todo-d8d1) сохраняем | ✅ |
| Shared core без большого refactor copy-paste loops | ✅ |
| UI event contract preserved | ✅ |

### Риски

1. **Self-check +1 LLM call** на host-задачах → чаще упираться в 90s wall-clock на медленном Antigravity.
2. **Модель игнорирует self-check** → KW fallback всё ещё нужен; после 2 KW nudges возможен DONE без SSH (как сейчас).
3. **`finish_report` не вызван** — финал по text-only после evidence; ок.
4. **Full agent reprompt «готово»** может добавить итерацию на коротких informational goals без tools — ограничено `tool_calls_log==0` и ≤2 reprompts.
5. Не трогаем 90s на action-resume в этом PR (отдельный follow-up).

### Out of scope этого PR

- Поднять OPERATOR_TURN_TIMEOUT / per-iteration budgets.
- Удаление debug-логов Nova.
- Переписывание Multi parse-default `skip`.
- UnifiedOrchestrator в mini-сборке.

---

## Статус реализации

Реализовано на `cursor/ai-loops-audit-149c`:

- `app/core/agentic_loop_policy.py` — shared self-check / finish helpers
- Operator: self-check primary + KW fallback + `operator.finish_report`
- Full Ops: premature «готово» с claim host-work при 0 tools → reprompt
- Тесты: glance host, greeting, provider error, step cap, policy unit, Full premature done
- Регрессии PR #36/#39/#40 не затронуты (`thread_sensitive=False`, auth close, 90s, legacy secrets)

См. итоговый отчёт в PR.
