# Вспомогательная (utility) модель и сервисные роли

Документ: план (фаза 1) + self-review (фаза 2).  
База: `cursor/ai-loops-audit-149c`. Реализация: `cursor/aux-model-roles-149c`.

---

## Контекст

После аудита AI-циклов (`docs/ai-loops-audit-plan.md`) в Operator есть:

- keyword-эвристики (`user_message_needs_ssh_actions`);
- one-shot self-check nudge (GOAL_SELF_CHECK);
- `_compress_messages` без LLM;
- Confirm gate на мутациях (детерминированные правила authoritative).

Нужна отдельная **вспомогательная модель** (дешёвая/локальная), назначаемая на сервисные роли вместо основной.

---

## Фаза 1. План

### 1. Data model

Переиспользуем file-backed `ModelConfig` (как chat/agent/orchestrator), не новую ORM-таблицу.

| Поле | Тип | Смысл |
|------|-----|--------|
| `aux_llm_enabled` | bool | Включить вспомогательную модель |
| `aux_llm_provider` | str | `ollama` / `openai` / `openai_compatible` / `claude` / `gemini` / `grok` / `openrouter` |
| `aux_llm_model` | str | id модели |
| `aux_llm_base_url` | str | Base URL для Ollama / LM Studio / любой OpenAI-compatible |
| `aux_llm_timeout_seconds` | int | Таймаут одного role-call (default 8, clamp 2–30) |
| `aux_role_verifier_enabled` | bool | Роль: проверка «цель достигнута?» |
| `aux_role_intent_enabled` | bool | Роль: классификатор намерения |
| `aux_role_summarizer_enabled` | bool | Роль: суммаризация/compaction |
| `aux_role_safety_enabled` | bool | Роль: hint read-only vs mutating (default **false**) |

API-ключ:

- известные провайдеры → существующий ManagedSecret `llm_api_key` / provider key;
- `openai_compatible` → новый ключ `openai_compatible` в том же namespace (LM Studio / vLLM / custom).

Fallback: роль выключена **или** aux не настроен / ошибка / timeout → текущее поведение (keywords, nudge главному модели, truncate без LLM). Confirm gate **никогда** не ослабляется safety-hint’ом.

### 2. Settings API

- Расширить `GET/POST /api/settings/` полями выше + `api_keys.openai_compatible`.
- Новый `POST /api/settings/aux-model/test/` — короткий ping (`{"ok":true}`) с таймаутом; admin-only.
- Admin gate: те же `user_can_manage_ai_routing` / `_ai_model_settings_keys`.

### 3. Settings UI

Секция «Вспомогательная модель» на `/settings/ai` (`AiSettingsPanel`):

- toggle enabled;
- provider + model + base URL (если ollama/openai_compatible);
- API key через существующий паттерн ManagedSecret;
- timeout;
- чекбоксы ролей;
- кнопка «Проверить соединение»;
- RU/EN через `ai.aux_*` в locales.

Стиль — существующие `SectionCard` / `SettingsField`.

### 4. Typed role interface (`app/core/aux_model_roles.py`)

```text
classify_intent(text) -> IntentResult(kind, needs_ssh, source)
verify_goal(goal, evidence_summary, ...) -> VerifyResult(decision=continue|finish, reason, source)
summarize(text, *, max_chars) -> str   # source in logs
classify_command_safety(command) -> SafetyHint(kind=read_only|mutating|unknown)  # HINT ONLY
```

Контракт вызова:

- structured JSON, короткий system prompt;
- `asyncio.wait_for(timeout=aux_llm_timeout_seconds)`;
- parse fail / timeout / HTTP error → fallback + log `source=fallback`;
- observability: `logger.info("aux_role role=… provider=… model=… source=aux|fallback …")`.

Транспорт:

- Ollama / openai_compatible / openai / openrouter / grok → non-stream OpenAI-compatible chat.completions (json_mode);
- claude / gemini → collect `stream_chat(purpose="aux", json_mode=True)` под тем же timeout.

Purpose alias: `aux` / `aux_verifier` / `aux_intent` / `aux_summarizer` / `aux_safety` → отдельный resolve из aux_* полей (не chat bucket).

### 5. Wiring в циклы

| Роль | Куда | Поведение |
|------|------|-----------|
| **intent** | `run_operator_loop` старт | `needs_ssh_actions = heuristic OR (intent.needs_ssh if aux ok)` |
| **verifier** | text-only early-stop path | aux `continue` → nudge; `finish` → DONE; fail → текущий self-check nudge |
| **summarizer** | `_compress_messages` (async wrapper / sync fallback) | LLM compact head; fail → truncate summary как сейчас |
| **safety** | `is_auto_executable_read` / mutate path | **только лог/hint**; Confirm и `is_operator_safe_read_command` authoritative |
| Full agent | premature done / observation compact | verifier hint / summarizer optional (лёгкий) |

90s turn timeout Operator не поднимаем; role timeout ≪ 90s.

### 6. Тесты

- routing: enabled+configured → aux; unset → fallback;
- timeout/fail → fallback;
- classifier JSON parse error → heuristic;
- verifier continue vs finish;
- settings API fields + secret key `openai_compatible`;
- safety hint не обходит Confirm.

---

## Фаза 2. Self-review против кода

| Проверка | Вердикт |
|----------|---------|
| ModelConfig уже хранит purpose routes — aux рядом уместен | ✅ |
| ManagedSecret llm_api_key расширяем, не дублируем ORM | ✅ |
| AIProviderPreference = CLI subscriptions — не смешивать | ✅ |
| Нет generic openai_compatible в stream path — отдельный one-shot клиент для ролей | ✅ |
| Keyword heuristics остаются fallback | ✅ |
| Confirm / `is_operator_safe_read_command` не ослаблять | ✅ |
| Operator stream events не менять | ✅ |
| Antigravity как aux тяжёлый — UI предупреждение; API providers ок | ✅ |
| `_compress_messages` sync — summarizer через best-effort sync wrapper или skip-if-no-loop | ✅ best-effort |

### Риски

1. Локальный Ollama медленный → упираемся в role timeout → частый fallback (ожидаемо).  
2. Двойной LLM (intent+verifier) на turn — держим timeout 8s и one-shot.  
3. Safety hint может расходиться с детерминизмом — только observability.  
4. Sync compress path: summarizer без event loop → truncate fallback.

---

## Статус реализации

Реализовано на `cursor/aux-model-roles-149c`:

- `ModelConfig` aux_* поля + purpose alias `aux*`
- `app/core/aux_model_roles.py` — classify_intent / verify_goal / summarize / classify_command_safety
- Settings API + `POST /api/settings/aux-model/test/` + ManagedSecret `openai_compatible`
- Operator: intent + verifier + summarizer + safety hint (log only)
- UI: секция «Вспомогательная модель» на Settings → AI (RU/EN)
- Тесты: `tests/test_aux_model_roles.py`

См. PR.
