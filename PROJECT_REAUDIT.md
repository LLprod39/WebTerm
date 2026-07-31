# PROJECT REAUDIT — WebTerm

# NO-GO

Повторный независимый аудит коммита `6094c6b1dbf045ef8149cc85bc45a0d393fbf640` (ветка `test`).

---

## 1. Немедленный вердикт

### `NO-GO`

Причина в одном предложении: **центральный механизм исправления предыдущего аудита — durable-очередь claim/lease — не работает на PostgreSQL, а production-стек в этом коммите не может быть даже распарсен docker compose.** Обе проблемы внесены именно этим коммитом и обе подтверждены реальными логами CI, а не рассуждениями по коду.

| Вопрос | Ответ |
|---|---|
| Исправлен ли предыдущий аудит полностью? | **Нет.** Из 24 задач: 9 `FIXED`, 11 `PARTIALLY FIXED`, 3 `NOT FIXED`, 1 `REGRESSED`. |
| Готов ли проект к production? | **Нет.** Чистая установка невозможна (compose не интерполируется). Даже при ручном обходе — пайплайны и Operator Chat не исполняются. |
| Можно ли масштабировать backend? | **Нет.** `backend` действительно лишён `container_name` (условие выполнено), но горизонтальное восстановление operator turn'а через БД падает с `NotSupportedError` на PostgreSQL. SSH-пул остался процесс-локальным: отзыв доступа не распространяется на второй инстанс. |
| Можно ли безопасно исполнять плагины? | **Условно.** В production исполнение по умолчанию **выключено** (`RELEASE_MODE=disabled`, провайдер `disabled`) — это и есть реальная защита. `docker_runner` — настоящая граница изоляции. `local_subprocess` **не является защитой от злонамеренного кода** — Python-guard'ы обходятся тривиально. |
| Переживают ли пайплайны рестарт? | **Нет.** Схема (lease + fencing + attempts + reconcile) спроектирована корректно и доказана на SQLite, но на целевой СУБД `claim` бросает исключение на первом же вызове — прогоны не забираются вообще, ни до, ни после рестарта. |
| Можно ли доверять CI и тестам? | **Частично.** CI честно поймал обе критические проблемы и стоит красным — доверять ему можно. **Тестам — нет:** ключевые доказательства R-05/R-10/R-19 зелёные только на SQLite, а контракты docker-compose проверяются `yaml.safe_load`, а не `docker compose config`. |

---

## 2. Паспорт проверки

| Параметр | Значение |
|---|---|
| Дата аудита | 2026-07-31 |
| Репозиторий | `C:\WebTrerm` |
| Ветка | `test` |
| Локальный HEAD | `6094c6b1dbf045ef8149cc85bc45a0d393fbf640` |
| `origin/test` | `6094c6b1dbf045ef8149cc85bc45a0d393fbf640` (совпадает, расхождений нет) |
| Проверяемый диапазон | `ca8d45d..6094c6b` — 1 коммит, 338 файлов, +35 877 / −3 142 |
| Состояние рабочей папки | **Грязная**, но только фронтенд-оформление |
| Незакоммиченные файлы (ИСКЛЮЧЕНЫ из оценки) | `M frontend/DESIGN.md`, `M frontend/index.html`, `M frontend/src/components/AppLayout.tsx`, `M frontend/src/index.css`, `M frontend/src/lib/ui-style.tsx`, `?? frontend/src/components/AshitaAtmosphere.tsx` |
| Свободно на диске C: | 2.00 ГБ на момент старта |

### Окружение проверки

| Слой | Локально (мой прогон) | CI (GitHub Actions) |
|---|---|---|
| Python | 3.11.15 (`.venv-wsl`, WSL Ubuntu) | 3.11.15 |
| Django | 5.2.16 | 5.2.16 |
| pytest | 9.1.1 + pytest-django 4.12.0 | тот же lock (`requirements-dev.lock`, `--require-hashes`) |
| Settings | `web_ui.settings.test` | `web_ui.settings.test_postgres` |
| БД | **SQLite** (локального PostgreSQL нет) | **postgres:16-alpine** |
| Redis | нет (LocMemCache, InMemoryChannelLayer) | **redis:7-alpine** (кэш + channels) |
| Docker | не использовался (2 ГБ свободно — сборка образов запрещена условиями) | полноценный |

### Использованные команды

```
git rev-parse --abbrev-ref HEAD ; git rev-parse HEAD ; git rev-parse origin/test ; git status --porcelain
git diff --stat ca8d45d..6094c6b
git diff ca8d45d..6094c6b -- docker-compose.production.yml web_ui/settings/test.py pyproject.toml
git show ca8d45d:docker-compose.production.yml
gh run list --commit 6094c6b1dbf045ef8149cc85bc45a0d393fbf640 --limit 40 --json workflowName,status,conclusion,databaseId
gh run view <id> --json jobs ; gh run view <id> --log-failed
gh api repos/:owner/:repo/actions/jobs/91118700059/logs   # Backend Unit and Coverage
gh api repos/:owner/:repo/actions/jobs/91118700139/logs   # Production Checks
.venv-wsl/bin/python -m pytest tests/test_pipeline_dispatch.py tests/test_multi_instance_orchestration.py tests/test_pipeline_resume.py -q --no-cov
.venv-wsl/bin/python -m pytest tests app core_ui servers studio kubernetes_ops plugin_marketplace mars --collect-only -q --no-cov
python <scratch>/count_ops.py   # разбор docs/openapi.json
```

### Ограничения проверки (влияют на статусы)

1. **Нет локального PostgreSQL и Redis.** Прямое воспроизведение `NotSupportedError` локально невозможно; вместо этого использован лог реального PostgreSQL 16 из CI, где напечатан точный SQL и точное исключение. Это более сильное доказательство, чем локальный прогон.
2. **Docker не запускался** (2 ГБ свободно). Сценарии «10 прогонов + убийство воркера», backup/restore, upgrade/rollback, два инстанса backend, бенчмарк SSH-пула — **не выполнялись мной**. Однако CI-workflow'ы, которые их выполняют, красные и не дошли до содержательной части.
3. **Нагрузочное тестирование не проводилось** — ни мной, ни в репозитории нет ни одного нагрузочного сценария.
4. Полный прогон backend-набора локально не запускался: на SQLite он даёт заведомо ложнозелёный результат по ключевым тестам (доказано ниже), поэтому вместо него взяты фактические числа из CI на PostgreSQL.

---

## 3. Оценки (0–10)

| Область | Оценка | Обоснование |
|---|---:|---|
| Архитектура | **7** | Границы модулей реальные (`import-linter`, ADR-0003, fitness-гейт зелёный). Но durable-слой спроектирован без единого прогона на целевой СУБД. |
| Качество кода | **6** | Код типизирован, читаем, `from __future__ import annotations` везде. Но одна и та же ошибка `select_for_update()+select_related()` по nullable FK повторена в 6 местах, при том что в 3 других местах автор применил правильный `of=("self",)`. |
| Безопасность | **6** | Много сделано правильно: HMAC + replay-окно, docker-proxy с политикой, `cap_drop ALL`, `no-new-privileges`, managed secrets без PBKDF2 в рантайме, очистка identity-заголовков в nginx. Минусы: `/metrics` без аутентификации и с ACL на всю приватную сеть; guard'ы `sandbox_worker.py` обходятся; throttle логина схлопывается в один общий счётчик при `TRUSTED_PROXY_HOPS=0`. |
| API | **5** | Единый конверт ответа и безопасный 5xx реально работают. Но типизированная схема есть у **11 из 246** мутирующих операций. |
| Данные | **5** | Retention-политики полные и батчевые. Но у самых больших таблиц нет индекса под запрос очистки; legacy-колонки секретов не очищены и не удалены. |
| Производительность | **4** | Не измерена ни разу. `prune_history` делает `COUNT(*)` по многомиллионным таблицам; webhook чистит таблицу доставок внутри HTTP-транзакции. |
| Надёжность | **2** | Очередь пайплайнов и очередь operator turns не функционируют на production-СУБД. Воркеры уходят в crash-loop. |
| Тестирование | **4** | 2777 тестов, 2767 зелёных на PostgreSQL. Но главные доказательства коммита — ложнозелёные на SQLite, а compose-контракты проверяются парсером YAML вместо `docker compose config`. |
| DevOps | **3** | One-shot `migrate`, статика из образа, пиннинг образов по digest, разделение docker-proxy — всё правильно. Но чистая установка сломана, 4 из 8 workflow красные. |
| Документация | **7** | `scripts/env_contract.py` генерирует и проверяет справочник переменных, ADR присутствуют, docs-contract в CI. |
| **Production readiness** | **2** | Стек не поднимается штатным путём; ключевые фичи не исполняются. |
| Удобство развития | **7** | Структура понятная, гейты защищают от новой деградации, тесты быстро находят регрессии — что и произошло. |

---

## 4. Матрица R-01…R-24

| ID | Задача | Статус | Доказательство | Выполненная проверка | Остаточный риск |
|---|---|---|---|---|---|
| **R-01** | Доверенный источник IP | `PARTIALLY FIXED` | `core_ui/client_ip.py:20-44` `extract_client_ip` берёт адрес с **правого** края XFF (`forwarded[-hops]`), по умолчанию `REMOTE_ADDR`. `docker/nginx/webterm-server-common.conf:6` — `X-Forwarded-For $proxy_add_x_forwarded_for` (append, не replace). `docker/nginx/production.conf:12-14` — `set_real_ip_from 172.16.0.0/12`, `real_ip_header X-Forwarded-For`, `real_ip_recursive on` (критерий прошлого аудита по nginx **выполнен**). `web_ui/settings/security.py:134` — `TRUSTED_PROXY_HOPS` зажат в 0…16. | Чтение кода + `tests/test_client_ip_security.py:12,32` (RequestFactory, оба PASSED в CI). | `TRUSTED_PROXY_HOPS` **не задан** в `docker-compose.production.yml` — только в `.env.production.example:78`. Апгрейд существующего деплоя со старым `.env.production` молча даёт `hops=0` → в аудит пишется IP контейнера nginx для всех пользователей, без единой ошибки. Нет проверки, что `REMOTE_ADDR` действительно принадлежит доверенному прокси: при прямом доступе к backend-порту в обход nginx и `hops>0` подделка XFF снова возможна. Тест не проходит через реальный middleware-стек. |
| **R-02** | Throttle логина | `PARTIALLY FIXED` | `core_ui/auth_throttle.py:76-122`. Счётчик по IP — `cache.incr` (атомарен в Redis), `web_ui/settings/database.py:63-72` в проде даёт `RedisCache` (Redis обязателен: `database.py:15-19`). Лок-аут чужого username устранён правильно — заменён на мягкую задержку `_username_failure_delay_seconds` (`auth_throttle.py:52-59`). | Чтение кода + `tests/test_auth_bruteforce.py` (PASSED, LocMemCache). | (а) **При `TRUSTED_PROXY_HOPS=0` ключ IP один для всего деплоя** → 10 неудачных попыток любого пользователя блокируют вход **всем** на 900 с. Это ровно та проблема P-05, ради которой писалась задача; (б) `time.sleep(delay)` до 2 с выполняется в синхронном middleware и удерживает поток воркера — усилитель DoS; (в) проверка лимита выполняется **до** `get_response`, инкремент — **после**: параллельные запросы проскакивают лимит; (г) нет ни одного теста с общим Redis и несколькими процессами. |
| **R-03** | Deploy-check на движок БД | `FIXED` | `core_ui/checks.py:23-35` `production_database_deploy_check` → `core_ui.E006` при `sqlite3` и `DEBUG=False`. `.github/workflows/backend-ci.yml:246-259` — шаг «Prove production deploy check rejects SQLite fallback» с `test "$status" -ne 0` и `grep -q "core_ui.E006"`. | Лог job «Production Checks» (91118700139): шаг **прошёл**; job упал позже, на `docker compose config`. | Это гейт **CI**, а не рантайма: `docker/render-backend-start.sh` содержит только `exec daphne …`, `manage.py check --deploy` при старте контейнера не вызывается. Если оператор соберёт свой образ/энтрипоинт, SQLite снова возможен. |
| **R-04** | Исполнение плагинов | `PARTIALLY FIXED` | Дефолт при `DEBUG=False` — `disabled` (`web_ui/settings/plugin_marketplace.py:26`), `RELEASE_MODE` тоже `disabled` (там же, стр. 31-39), и при `disabled` проверка выходит рано (`plugin_marketplace/checks.py:158-179`). `docker_runner` (`backend_container_runner_service.py:52-93`) — реальная граница: `--user 10001:10001`, `--read-only`, `--cap-drop ALL`, `--security-opt no-new-privileges`, `--network none` (если манифест не объявил egress + не задана выделенная сеть — иначе жёсткий отказ), `--pids-limit`, memory/cpus, tmpfs `noexec`, **нет ни одного volume**, **нет docker socket**, образ обязан быть immutable `sha256`-digest, `--pull never`. Env в контейнер не пробрасывается. | Чтение кода всех четырёх провайдеров + `checks.py` + compose. | **Изоляция `local_subprocess` защищает только от случайной ошибки, не от злонамеренного кода.** `plugin_marketplace/sandbox_worker.py:176-218` патчит `builtins.open`, `io.open`, `os.open`, `subprocess.*`, `os.system/popen` и всё, что начинается на `exec`/`spawn`. Обходы очевидны: `os.posix_spawn` **не начинается** на `exec`/`spawn` и остаётся доступным; `ctypes.CDLL("libc.so.6").system(...)`/`.open(...)` игнорирует все патчи; egress-guard подменяет `socket.socket`, но не syscall. Провайдер включается одной переменной окружения и тогда исполняет чужой код в контейнере backend'а с его сетью (postgres, redis, docker-proxy) и файловой системой. Отдельно: `.env.production.example:361` ставит `external_worker`, но `PLUGIN_MARKETPLACE_EXTERNAL_BACKEND_SANDBOX_ENDPOINT` пуст — при включённом marketplace `check --deploy` упадёт (`plugin_marketplace.E022`). |
| **R-05** | Сверка зависших прогонов | `PARTIALLY FIXED` | `studio/management/commands/reconcile_pipeline_runs.py` существует и вызывается при старте: `docker-compose.production.yml:394` — `python manage.py reconcile_pipeline_runs && exec python manage.py run_scheduled_pipelines --daemon`. | Чтение compose + команды. | Формально критерий «нет прогонов без исполнителя» выполняется, но извращённым способом: поскольку `claim` не работает (см. R-10), reconcile будет переводить **все** прогоны в `failed` по таймауту. Не проверено на реальном рестарте контейнера. |
| **R-06** | Единый обработчик ошибок API | `FIXED` | `core_ui/api_errors.py:38-52` `APIErrorMiddleware.process_exception` → `internal_error_response` (текст исключения наружу не идёт); `normalize_api_response` приводит все ответы к конверту. Подтверждено **боевым случаем**: `NotSupportedError` в `server_transfer_owner` вышел наружу как безопасный **500** без утечки SQL — тест ожидал 400/200 и получил 500. `tests/test_api_errors.py::test_no_json_5xx_response_interpolates_caught_exception` — PASSED. | Чтение middleware + лог CI. | 117 вхождений `str(exc)`/`str(e)` в 38 файлах `*/views/*.py` формируют **4xx**-сообщения из текста исключения (напр. `servers/views/server_crud.py:352-357`). Это контролируемые доменные `ValueError`, но единого запрета нет, и новый `raise ValueError(f"...{path}...")` утечёт в ответ. |
| **R-07** | Telegram: один потребитель + approval в БД | `REGRESSED` | Дизайн правильный: `TELEGRAM_BOT_POLL_TOKEN` выдаётся **только** сервису `telegram-bot` (`docker-compose.production.yml:80`, `285` — пустая строка у всех остальных; `705` — токен только у бота). Персистентный офсет — `TelegramBotCursor` (`studio/approval_models.py:82-86`) + `advance_telegram_update_offset` под `select_for_update` (`telegram_delivery_service.py:56-66`). Решение хранится в БД, привязка к боту и чату сверяется `hmac.compare_digest` (`telegram_delivery_service.py:91,93`). | Чтение кода + compose + логи CI. | **Регрессия:** строка `705` `TELEGRAM_BOT_POLL_TOKEN: "${TELEGRAM_BOT_TOKEN:?…}"` добавлена именно в этом коммите (в `ca8d45d` её нет) и делает **весь** compose-файл непарсируемым без непустого `TELEGRAM_BOT_TOKEN`, несмотря на `profiles: ["telegram-bot"]`. Критерий «корректность compose без включённого Telegram-профиля» нарушен. Сценарии «два процесса» и «потеря callback после рестарта» не проверялись ни мной, ни в CI. |
| **R-08** | Ретеншен `CommandSnapshot` | `PARTIALLY FIXED` | Лимит размера есть: `servers/models_inventory.py:330-333` `content_truncated` + `COMMAND_SNAPSHOT_MAX_CONTENT_BYTES`. Политика: `core_ui/history_retention.py:122-128` — 30 дней / 50 000 строк, батчевое удаление `_delete_oldest` (`:167-177`). | Чтение модели + `history_retention.py` + Meta-индексов. | **Индекса под запрос очистки нет.** Запрос — `filter(created_at__lt=cutoff).order_by("created_at","pk")`, а индексы (`models_inventory.py:345-349`) все ведут с `server`/`user`. PostgreSQL пойдёт seq scan + sort. То же у `ServerHealthCheck` (лимит 1 000 000 строк, индексы ведут с `server`/`status`) и `ChatArtifact` (индекс по `-updated_at`, чистка по `created_at`). У `UserActivityLog`/`LLMUsageLog` индекс `["-created_at"]` есть. Требование «отсутствие полного сканирования таблицы» не выполнено на самых больших таблицах. |
| **R-09** | Очистка метрик независимо от монитора | `FIXED` | `core_ui/history_retention.py:219` — `cleanup_monitoring_metric_data` вызывается из `prune_history`, то есть из отдельного контейнера `history-pruner` (`docker-compose.production.yml:426-439`), без участия `monitor`. | Чтение кода + compose. | На каждом цикле выполняются `queryset.count()` по всем 9 таблицам (`history_retention.py:191,194,204`) — на многомиллионных таблицах это полный подсчёт. Раз в сутки терпимо, но деградирует. |
| **R-10** | Очередь исполнения пайплайнов | `NOT FIXED` | `threading.Thread` из пути пайплайнов действительно убран. Lease, heartbeat, fencing по `(claimed_by, attempt_count, lease_expires_at)`, `max_attempts`, `skip_locked` — всё написано (`studio/dispatch.py:151-330`). **Но на PostgreSQL `claim_next_pipeline_dispatch` бросает `django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join`** — см. NEW-01. | Лог job 91118700059 (PostgreSQL 16): 6 тестов `test_pipeline_dispatch.py` / `test_pipeline_resume.py` падают с этим исключением; в логе PostgreSQL напечатан сам SQL с `LEFT OUTER JOIN … FOR UPDATE SKIP LOCKED`. Локально на SQLite те же тесты — 12 passed. | Полный отказ подсистемы в production. Прогоны не забираются ни одним воркером; `pipeline-execution` уходит в crash-loop (`run_pipeline_execution_plane.py:107` — вызов `claim` вне try/except, исключение поднимается до `:78-81` и переброшено; `restart: unless-stopped`). Сценарий «10 прогонов + убийство воркера» на реальной СУБД невыполним. |
| **R-11** | SSH-пул с инвалидацией | `PARTIALLY FIXED` | `servers/services/ssh_pool.py`. Ключ пула `(server_id, user_id)` (`:219,290`) — изоляция пользователей есть. TTL/LRU/лимиты: `_limits()` (`:140-146`, 60 с / 4 на сервер / 50 глобально), `_evict_expired` (`:160-165`), `_make_room` (`:167-184`), `OrderedDict.move_to_end`. 4 триггера инвалидации: ротация секрета (`servers/secret_utils.py:21-25`), сигнал изменения сервера и сигнал изменения share (`servers/signals.py:50-60`), передача владения (`servers/services/server_ownership.py:80-86`). | Чтение кода + перечисление вызовов `invalidate_ssh_connections`. | **Пул процесс-локальный** (модульный синглтон `ssh_pool.py:347`, docstring это признаёт). При двух инстансах backend отзыв доступа на инстансе A не закрывает живую SSH-сессию на инстансе B — окно до 60 с (TTL). Смена host key и изменение connection settings покрыты только через общий `post_save` сигнал сервера — отдельно не проверялись. **Бенчмарка ≥5× нет ни одного**; все тесты (`tests/test_ssh_pool.py:78,112,142,186,207,214`) работают через `monkeypatch`/`patch`, то есть проверяют факт вызова, а не фактическое закрытие соединения и не ускорение. |
| **R-12** | Request-scoped кэш | `PARTIALLY FIXED` | `core_ui/projects.py:64-87` — кэш живёт на объекте `request` (`request._webterm_active_project_cache`), глобального состояния нет, переживать запрос не может. Read-путь не берёт блокировок и не создаёт строк (`:81-84` + комментарий `:82-83`). Отзыв прав применяется на следующем запросе — `tests/test_request_scoped_access_cache.py:32-45` (PASSED). GET не создаёт записи — `:48-63` (PASSED). | Чтение кода + разбор тестов + подсчёт call-sites. | **Кэш почти не используется:** `request=` передаётся лишь в **4 из 46** мест вызова `active_project_for_user(` в `servers/`, `studio/`, `core_ui/`. Заявленное снижение нагрузки на БД в реальном пути запроса не достигается. Тест `django_assert_num_queries(3)→(0)` меряет прямой вызов хелпера с `RequestFactory`, а не боевой view через middleware. |
| **R-13** | Идемпотентность и подпись webhook | `FIXED` | `studio/views/trigger_views.py:222-239` — HMAC-SHA256 по `f"{timestamp}."` + **сырому** телу, окно `WEBHOOK_SIGNATURE_TOLERANCE_SECONDS` (default 300), `hmac.compare_digest` + сверка длины. Дедуп: `:318-333` — `X-WebTerm-Delivery-Id` (лимит 200 симв.), fallback на `sha256:<body>`, `get_or_create(trigger, delivery_id)` внутри `transaction.atomic()`, повтор возвращает существующий `run_id` с `duplicate: true`. Токен принимается из заголовка `X-WebTerm-Trigger-Token`, конфликт с URL-токеном отсекается `compare_digest` (`:246-252`). | Чтение кода + nginx `limit_req zone=webhook_limit` (`webterm-server-common.conf:74-84`). | Подпись **опциональна**: `if not secret: return None` (`:224-225`) — триггер без `signing_secret` принимает любое тело, гейта «в production подпись обязательна» нет. `PipelineWebhookDelivery.objects.filter(received_at__lt=cutoff).delete()` (`:326`) выполняется **внутри транзакции каждого запроса** — очистка таблицы на горячем пути. Конкурентная доставка одного события и поведение после рестарта не проверялись эмпирически. |
| **R-14** | Завершить миграцию секретов | `PARTIALLY FIXED` | **Рабочий путь чист:** `servers/secret_utils.py:52-64` читает только `ManagedSecret`, `master_password` — мёртвый параметр, PBKDF2 при подключении не вызывается. Инструмент миграции: `servers/management/commands/migrate_legacy_server_secrets.py` — dry-run по умолчанию, `--apply`, `--clear-legacy` (требует `--apply`), транзакция на сервер (`:98-111`), идемпотентность через `has_managed_server_secret` (`:51,69`), счётчики `migrated/cleared/skipped/failed`, ненулевой выход при ошибках (`:125-126`). | Чтение кода + миграции `servers/migrations/0054_alter_server_encrypted_password_and_more.py`. | Критерий «`encrypted_password` пуст везде» **не выполнен**: миграция `0054` только меняет `help_text`/`editable=False`, данные не очищает и колонки не удаляет. `servers/encryption.py` с PBKDF2 и текстом «MASTER_PASSWORD пустой» остаётся. Нет readiness-проверки, которая покажет оставшиеся legacy-строки. Отдельный дефект: `store_server_auth_secret` (`secret_utils.py:67-74`) обнуляет `server.salt`/`server.encrypted_password` **только в памяти**, `save()` не вызывает — при обычном обновлении секрета через UI старый шифротекст остаётся в БД. Откат `--clear-legacy` невозможен (данные удаляются безвозвратно) — это не отмечено в help. |
| **R-15** | Единый контракт ответа API | `FIXED` | `frontend/src/lib/api.ts:145-153` — `parseErrorMessage` сведён к одной ветке (`data.error` строка → иначе `HTTP {status}`). `apiFetch` (`:201-212`) распаковывает конверт `{success, code, data}`. Бэкенд-сторона — `core_ui/api_errors.py:91-162`. | Чтение фронтенд-клиента и middleware. | Фронт **выбрасывает** `code` и `details` — машинно-читаемые коды ошибок до UI не доходят, вся обработка снова по тексту. |
| **R-16** | Валидация на границе HTTP | `NOT FIXED` | `core_ui/schemas/http.py:111-124` — `ROUTE_SCHEMAS` содержит **12 записей**, из них строгих (`extra="forbid"`) — 5. Всё остальное падает в `MutationSchema` с `extra="allow"` и единственным полем `name: str|None, max_length=200`. | Разбор `docs/openapi.json` скриптом: **373 пути, 246 мутирующих операций** (210 POST, 17 DELETE, 11 PUT, 8 PATCH), 229 с `requestBody`, из них типизированных/строгих — **11**, остальные 218 — универсальная схема. | Критерий «схема на каждый мутирующий эндпоинт» выполнен на ~4,5 %. Неизвестные поля, неверные типы и сверхдлинные значения принимаются на 218 эндпоинтах и доходят до ORM. Именно так рождаются 500 вместо 400. |
| **R-17** | Удалить мёртвый код | `FIXED` | `grep -rn "PipelineEngine"` по всему проекту (без `node_modules`/`.venv`) — **0 совпадений**. `noqa: F403` в `views/__init__.py` — 0. | Прямой поиск. | — |
| **R-18** | Prometheus-эндпоинт | `PARTIALLY FIXED` | `core_ui/urls.py:38` → `core_ui/views/metrics_views.py:7-12`. Метрики: глубина очереди пайплайнов + возраст старейшей + latency по типам нод (`studio/prometheus_metrics.py:44-62`); очередь агентов + возраст + активные/используемые SSH-соединения (`servers/prometheus_metrics.py:10-31`). Устойчивость к падению БД есть: `app/prometheus_registry.py:26-33` ловит исключение провайдера и отдаёт `webterm_metrics_provider_up{provider="…"} 0`. Закрытие в nginx: `webterm-server-common.conf:58-66`. | Чтение кода + nginx-конфига. | Эндпоинт **без аутентификации** — `@require_GET` и всё. ACL nginx пускает `10.0.0.0/8`, `172.16.0.0/12`, `192.168.0.0/16`, а nginx слушает `${PUBLIC_BIND_HOST:-0.0.0.0}` — значит метрики читает **любая машина в корпоративной сети**. Нет метрик очереди operator turns (при том что это ключевая очередь R-19), нет счётчиков ошибок и ретраев, нет HTTP-latency. |
| **R-19** | Оркестрационное состояние вне памяти | `NOT FIXED` | Модель `OperatorTurnDispatch` и сервис `core_ui/services/operator_dispatch.py` созданы, `backend` в compose **без** `container_name` (масштабирование не заблокировано). Но `claim_next_operator_dispatch` (`operator_dispatch.py:83-93`) падает на PostgreSQL. | Лог CI: `tests/test_multi_instance_orchestration.py::test_backend_b_can_snapshot_and_stop_turn_claimed_by_backend_a` и `::test_different_worker_executes_durable_dispatch_and_persists_turn` — **FAILED**, `NotSupportedError`. Локально на SQLite — оба PASSED. | Восстановление turn'а с другого backend не работает. Плюс сохраняется процесс-локальное состояние: SSH-пул (`ssh_pool.py:347`) и in-memory latency-буфер метрик. |
| **R-20** | Миграции и статика вне entrypoint | `PARTIALLY FIXED` | One-shot сервис есть: `docker-compose.production.yml:362-385` `migrate` с `restart: "no"`, `backend` зависит от него через `service_completed_successfully` (`:329-330`). `render-backend-start.sh` теперь только `exec daphne` — миграций в entrypoint нет. Статика копируется из образа: `cp -a /workspace/staticfiles/. /static-target/` (`:368`). `container_name` снят с `backend`, `operator-execution`, `playbook-execution-worker`. | Чтение compose + entrypoint + логи трёх smoke-workflow. | **Production install сломан** — все три эксплуатационных workflow падают на первом же `docker compose` (см. NEW-02). Значит backup/restore и upgrade/rollback в этом коммите **не имеют ни одного доказательства**. Отдельно: `pipeline-execution` сохранил `container_name: mini-prod-pipeline-execution` (`:399`) — этот воркер масштабировать нельзя, хотя он спроектирован под `--worker-key $HOSTNAME`. |
| **R-21** | ADR по `kubernetes_ops` и MARS | `FIXED` | `docs/architecture/adr/0003-kubernetes-ops-and-mars-boundary.md` существует; `scripts/check_kubernetes_ops_v01_scope.py` выполняется в workflow «Architecture Fitness» (зелёный, run 30618969220). | Листинг ADR + чтение workflow + статус run. | — |
| **R-22** | Убрать `import *`, алиасы, `sys.modules` | `PARTIALLY FIXED` | `sys.modules[__name__] = …` в коде проекта — **0** (совпадения только в `.venv`). `noqa: F403` в `views/__init__.py` — **0**. `import *` осталось в 5 файлах, из которых 4 — стандартный Django-паттерн настроек. | `grep` по `app core_ui servers studio mars kubernetes_ops plugin_marketplace web_ui`. | Остался ровно тот вид алиаса, против которого писалась задача: `app/agent_kernel/sudo_policy.py:1` — `from app.sudo_policy import *  # noqa: F401,F403`, скрывающий реальную зависимость от статического анализа. |
| **R-23** | Метрики связности вместо лимита строк | `FIXED` | `pyproject.toml` (диапазон `ca8d45d..6094c6b`): legacy-пин `".tools/k8s-provider-fixture.py" = 771` **удалён**, `[tool.architecture.legacy_baselines]` пуст, комментарий: «Line count is diagnostic only. Complexity and module coupling are the blocking fitness metrics». Гейт: `scripts/check_architecture_sizes.py --strict-new` + `scripts/check_architecture_no_regression.py` (сравнение с замороженным baseline по size-violations и по рёбрам импортов из `lint-imports`). | `git diff` + чтение скриптов + зелёный workflow. | Размер файлов теперь не блокирует вообще — гейт держится на complexity/fan-in/fan-out и границах импортов. Это соответствует критерию, но убирает единственный барьер против god-файлов. |
| **R-24** | Явные зависимости вместо `getattr` по модулю | `FIXED` | `grep -rn "consumer_module_attr"` — **0**. `grep -rn "getattr(sys.modules\|getattr(module"` по `app core_ui servers studio web_ui` — **0**. | Прямой поиск. | — |

**Итог матрицы (9 + 11 + 3 + 1 = 24):**

- `FIXED` — **9**: R-03, R-06, R-09, R-13, R-15, R-17, R-21, R-23, R-24
- `PARTIALLY FIXED` — **11**: R-01, R-02, R-04, R-05, R-08, R-11, R-12, R-14, R-18, R-20, R-22
- `NOT FIXED` — **3**: R-10, R-16, R-19
- `REGRESSED` — **1**: R-07

Ни одна задача не получила `NOT VERIFIED` — по каждой удалось получить либо доказательство из кода, либо лог CI. При этом `FIXED` у R-05/R-10/R-19 был бы невозможен в принципе: их критерии требуют реального рестарта и нескольких процессов, а даже unit-уровень на целевой СУБД красный.

---

## 5. Проверка старых Critical/High/Medium проблем

| Проблема | Старое доказательство | Текущее состояние | Статус | Комментарий |
|---|---|---|---|---|
| **P-01** Вечные `running` после рестарта; потеря всей активной работы | `threading.Thread` для запуска прогонов | `threading.Thread` из пути пайплайнов убран, построен durable-слой `PipelineRunDispatch` + `reconcile_pipeline_runs`. Но `claim` не работает на PostgreSQL | `NOT FIXED` | Исходная причина заменена на новую, худшую: раньше работа терялась при рестарте, теперь не начинается вовсе |
| **P-02** Approval теряется недетерминированно | Несколько потребителей `getUpdates` | Единственный владелец токена + персистентный курсор + решение в БД | `FIXED` (код) / `REGRESSED` (деплой) | Логика верна; изменение compose сломало запуск всего стека |
| **P-03** Плагин работает с правами приложения | `local_subprocess` по умолчанию | В production — `disabled` по умолчанию, marketplace выключен, есть жёсткий `docker_runner` | `PARTIALLY FIXED` | `local_subprocess` остался включаемым одной переменной и не является защитой от злонамеренного кода |
| **P-04** Аудит подделывается любым клиентом | `HTTP_X_FORWARDED_FOR` слева | `extract_client_ip` с правого края + `TRUSTED_PROXY_HOPS` | `PARTIALLY FIXED` | При апгрейде без новой переменной аудит молча пишет IP nginx для всех |
| **P-05** 10 запросов блокируют администратора | Лок-аут по username | Лок-аут по username заменён на мягкую задержку | `PARTIALLY FIXED` | При `hops=0` проблема воспроизводится в новой форме: 10 неудач кладут вход всему деплою |
| **P-06** Наружу уходит текст исключения | `str(exc)` в 5xx | `APIErrorMiddleware` + `internal_error_response`; подтверждено боевым 500 без утечки | `FIXED` | Остаются 117 мест `str(exc)` в 4xx-ответах |
| **P-07** SSH-хендшейк на каждую операцию | Нет пула | Пул с TTL/LRU/лимитами и 4 триггерами инвалидации | `PARTIALLY FIXED` | Бенчмарк не сделан; пул процесс-локальный |
| **P-08** Повторное выполнение webhook на проде | Нет дедупа | HMAC + timestamp + `compare_digest` + дедуп по delivery-id в транзакции | `FIXED` | Подпись остаётся опциональной |
| **P-09** Прод молча стартует на SQLite | Нет проверки | `core_ui.E006` + доказательный шаг в CI | `FIXED` | Проверка живёт в CI, а не в рантайм-энтрипоинте |
| **P-10** Два источника истины по секретам | legacy + managed | Рабочий путь только managed; есть команда миграции с dry-run | `PARTIALLY FIXED` | Колонки и `encryption.py` на месте; данные не очищены |
| **P-11** Неконтролируемый рост БД (`CommandSnapshot`) | Нет ретеншена | Политика 30 д / 50 000 строк + лимит размера `content` | `PARTIALLY FIXED` | Нет индекса под запрос очистки → seq scan |
| **P-12** Ретеншен зависит от живого монитора | Очистка в мониторе | `cleanup_monitoring_metric_data` вызывается из `prune_history` в отдельном контейнере | `FIXED` | `COUNT(*)` по большим таблицам каждый цикл |
| **P-13** Гонка миграций, потеря шаблонов | `migrate` в каждом entrypoint | One-shot `migrate`, статика из образа, `container_name` снят с backend | `PARTIALLY FIXED` | Ни один production-smoke не подтвердил это на практике — все красные |
| **P-14** Невозможен горизонтальный рост | Состояние в памяти | `OperatorTurnDispatch` в БД | `NOT FIXED` | `claim` падает на PostgreSQL; SSH-пул остался процесс-локальным |
| **P-15** 3 лишних запроса на вызов | Нет кэша | Request-scoped кэш реализован корректно | `PARTIALLY FIXED` | Используется в 4 из 46 мест |
| **P-16** Два формата ответа, нет кодов ошибок | Разнобой | Единый конверт + `parseErrorMessage` в одну ветку | `FIXED` | Фронт игнорирует `code`/`details` |
| **P-17** Мёртвый код (`PipelineEngine`) | Класс и его тест | Удалены полностью | `FIXED` | — |
| **P-18** 500 вместо 400 | Нет схем | 12 схем на 246 мутирующих операций | `NOT FIXED` | Покрытие ~4,5 % |

---

## 6. Новые проблемы

| № | Проблема | Доказательство | Последствия | Критичность | Сложность |
|---|---|---|---|---|---|
| **NEW-01** | `select_for_update()` вместе с `select_related()` по **nullable** FK — PostgreSQL отвергает такой запрос | Точный SQL из лога PostgreSQL 16 (job 91118700059): `… INNER JOIN "core_ui_chatsession" … LEFT OUTER JOIN "core_ui_assistantaction" ON ("core_ui_operatorturndispatch"."action_id" = …) … LIMIT 1 FOR UPDATE SKIP LOCKED` → `django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join`. Места: `studio/dispatch.py:125-126, 176-177, 245-246, 275-276` (`run__triggered_by` — `studio/models.py:454-460`, `null=True`); `core_ui/services/operator_dispatch.py:84-85` (`action` — `null`, ставится `None` при `KIND_MESSAGE`, `:43-52`); `servers/services/server_ownership.py:39` (`group` — `servers/models_inventory.py:35`, `null=True`). 8 тестов падают именно с этим исключением, 2 — с `assert 500 == 400` / `assert 500 == 200` из-за него же | **Пайплайны не исполняются вообще.** **Operator Chat не исполняется вообще.** Передача владения сервером возвращает 500. Воркеры `pipeline-execution` и `operator-execution` уходят в crash-loop: вызовы `claim` находятся вне try/except (`run_pipeline_execution_plane.py:107`, `run_operator_execution_plane.py:75`), исключение доходит до `:78-81` и перебрасывается, а `restart: unless-stopped` перезапускает контейнер | **Critical** | S (в 6 местах добавить `of=("self",)` либо убрать nullable-связь из `select_related`) |
| **NEW-02** | Production compose непарсируем без `TELEGRAM_BOT_TOKEN` — чистая установка невозможна | `docker-compose.production.yml:705`: `TELEGRAM_BOT_POLL_TOKEN: "${TELEGRAM_BOT_TOKEN:?TELEGRAM_BOT_TOKEN is required for telegram-bot}"` — строка добавлена в `6094c6b` (в `git show ca8d45d:docker-compose.production.yml` её нет). `.env.production.example:142` — `TELEGRAM_BOT_TOKEN=` (пусто), а `${VAR:?}` считает пустое значение отсутствующим. Compose интерполирует весь файл до фильтрации по профилям, поэтому `profiles: ["telegram-bot"]` не спасает. `docker/production-install-smoke.sh:146` копирует пример в `.env.production` и вызывает `docker compose --env-file` — это и есть документированный путь установки. 4 job'а падают с `error while interpolating services.telegram-bot.environment.TELEGRAM_BOT_POLL_TOKEN: required variable TELEGRAM_BOT_TOKEN is missing a value` | `docker compose up -d` не работает **ни для одного** сервиса у любого оператора, не использующего Telegram. Install/recovery/upgrade-rollback smoke не выполняются вовсе → у R-20 нет эксплуатационных доказательств | **Critical** | S (`${TELEGRAM_BOT_TOKEN:-}` + проверка непустоты внутри `run_telegram_bot`, который её уже делает — `run_telegram_bot.py:79-86`) |
| **NEW-03** | Ложнозелёные тесты на SQLite маскируют отказ на целевой СУБД | Локально: `pytest tests/test_pipeline_dispatch.py tests/test_multi_instance_orchestration.py tests/test_pipeline_resume.py` → **12 passed in 41.98s** (SQLite). В CI на PostgreSQL 8 из них FAILED. Причина: SQLite-бэкенд Django имеет `has_select_for_update = False`, `FOR UPDATE` просто не генерируется | Основной локальный цикл разработки даёт ложную уверенность именно по тем тестам, которые объявлены доказательством R-05/R-10/R-19 | **High** | M (пометить durable-тесты как требующие PostgreSQL и падать на SQLite вместо тихого прохода) |
| **NEW-04** | Контракты docker-compose проверяются `yaml.safe_load`, а не `docker compose config` | `tests/test_production_worker_topology.py:3,23-24` — `import yaml` / `yaml.safe_load(...)`. 14 тест-файлов ссылаются на production-compose, но ни один не вызывает `docker compose config` | Интерполяционные ошибки, `${VAR:?}`, ошибки профилей и merge-ключей проходят все 2777 тестов и ловятся только в эксплуатационных workflow. Ровно так NEW-02 попал в коммит | **High** | S |
| **NEW-05** | Throttle логина при `TRUSTED_PROXY_HOPS=0` схлопывается в один общий счётчик | `core_ui/auth_throttle.py:38` — ключ `_digest_key("ip-failures", extract_client_ip(request))`; при `hops=0` `extract_client_ip` возвращает `REMOTE_ADDR`, то есть IP контейнера nginx. `TRUSTED_PROXY_HOPS` отсутствует в `environment:` production-compose, задан только в `.env.production.example:78` | 10 неудачных попыток любого пользователя блокируют вход **всем** на `AUTH_LOGIN_FAILURE_WINDOW_SECONDS` (900 с). Тривиальный DoS на аутентификацию. Апгрейд со старым `.env.production` включает это молча | **High** | S (задать дефолт в compose + fail-fast, если `DEBUG=False` и `hops=0` при непустом XFF) |
| **NEW-06** | `/metrics` без аутентификации, ACL пускает всю приватную сеть | `core_ui/views/metrics_views.py:7-12` — только `@require_GET`. `docker/nginx/webterm-server-common.conf:58-66` — `allow 10.0.0.0/8; allow 172.16.0.0/12; allow 192.168.0.0/16; deny all;`. nginx слушает `${PUBLIC_BIND_HOST:-0.0.0.0}` (`docker-compose.production.yml:752-754`) | Любая машина корпоративной сети читает глубину очередей, возраст задач и число SSH-соединений. Разведданные для планирования атаки | **Medium** | S |
| **NEW-07** | `time.sleep()` до 2 с в синхронном middleware на пути логина | `core_ui/auth_throttle.py:117-119` | Каждая задержанная попытка удерживает поток пула. Масштаб ограничен: `docker/nginx/production.conf:6` держит `/api/auth/` на `rate=10r/m` с одного IP, поэтому для заметного удержания потоков нужен пул исходных адресов | **Low** (понижено с Medium после учёта nginx-лимита) | S |
| **NEW-08** | Гонка в проверке лимита throttle | `auth_throttle.py:100-106` читает счётчик **до** `get_response`, а инкрементирует **после** (`:112-114`) | Пачка параллельных запросов проходит проверку одновременно и превышает `AUTH_LOGIN_FAILURE_LIMIT` | **Medium** | S |
| **NEW-09** | Нет индексов под запросы retention на самых больших таблицах | `core_ui/history_retention.py:172` — `order_by(timestamp_field, "pk")`; индексы `CommandSnapshot` (`servers/models_inventory.py:345-349`) ведут с `server`/`user`; `ServerHealthCheck` (`servers/models_monitoring.py:47-49`) — с `server`/`status`; `ChatArtifact` (`core_ui/models/chat.py:316-317`) — по `-updated_at`, а чистка по `created_at` | Ежедневный prune делает seq scan + sort по таблицам с лимитом до 1 000 000 строк; растущая нагрузка и блокировки | **Medium** | S |
| **NEW-10** | Webhook чистит таблицу доставок внутри HTTP-транзакции | `studio/views/trigger_views.py:325-326` — `PipelineWebhookDelivery.objects.filter(received_at__lt=cutoff).delete()` внутри `transaction.atomic()` каждого приёма | Задержка и блокировки на горячем публичном эндпоинте; при всплеске доставок — контеншен | **Medium** | S |
| **NEW-11** | `store_server_auth_secret` не сохраняет очистку legacy-полей в БД | `servers/secret_utils.py:67-74` и `:77-82` — присваивают `server.salt = None`, `server.encrypted_password = ""` объекту, но `save()` не вызывают | Старый шифротекст остаётся в БД после смены секрета через UI; критерий R-14 «`encrypted_password` пуст везде» недостижим штатной эксплуатацией | **Medium** | S |
| **NEW-12** | Rate-limit приложения отключён во всём тестовом наборе | `web_ui/settings/test.py` (диапазон `ca8d45d..6094c6b`): добавлены `APP_RATE_LIMIT_ASSISTANT_PER_MINUTE = 0`, `APP_RATE_LIMIT_PIPELINE_RUNS_PER_MINUTE = 0`, `APP_RATE_LIMIT_AGENT_RUNS_PER_MINUTE = 0` | `ApplicationRateLimitMiddleware` по умолчанию не покрыт тестами; регрессии в лимитах пройдут CI | **Medium** | S |
| **NEW-13** | `pipeline-execution` нельзя масштабировать | `docker-compose.production.yml:399` — `container_name: mini-prod-pipeline-execution`, при том что команда принимает `--worker-key "$${HOSTNAME}"` и рассчитана на несколько экземпляров | `docker compose up --scale pipeline-execution=2` невозможен; вся пропускная способность пайплайнов ограничена одним контейнером | **Medium** | S |
| **NEW-14** | Fire-and-forget daemon-потоки остались в HTTP-путях вне пайплайнов | `servers/views/server_insights.py:404`, `servers/os_detect_service.py:137`, `servers/monitoring/monitor.py:463` — `threading.Thread(..., daemon=True).start()` | Работа, запущенная HTTP-запросом, теряется при рестарте и не видна другим инстансам — та же болезнь P-01, просто в других подсистемах | **Medium** | M |
| **NEW-15** | Guard'ы `sandbox_worker.py` не блокируют `os.posix_spawn` | `plugin_marketplace/sandbox_worker.py:216-218` — `if name.startswith(("exec", "spawn"))`; `posix_spawn`/`posix_spawnp` начинаются на `posix` и остаются доступны. Плюс `ctypes` не ограничен ничем | В режиме `local_subprocess` защита от запуска процессов не работает. В `docker_runner` компенсируется контейнером | **Medium** | S (или явно задокументировать, что это не граница безопасности) |
| **NEW-16** | Compat-alias `import *` скрывает зависимость от статанализа | `app/agent_kernel/sudo_policy.py:1` — `from app.sudo_policy import *  # noqa: F401,F403` | Ровно тот класс проблемы, против которого писалась R-22; граф зависимостей неполон | **Low** | S |
| **NEW-17** | Плейсхолдер-образ `mars-agent` заведомо нерабочий | `docker-compose.production.yml:708` — `registry.invalid/webterm-mars-agent@sha256:0000…0000` | Профиль `mars-agent` гарантированно падает при `pull`; вводит в заблуждение | **Low** | S |
| **NEW-18** | Тест проверяет текст исходника, а не поведение | `tests/test_pipeline_dispatch.py:69-71` — `inspect.getsource(...)`, `assert "threading.Thread" not in source` | Переименование импорта обходит проверку; тест не доказывает отсутствие фонового потока | **Low** | S |

---

## 7. Регрессии (появились из-за исправлений аудита)

1. **NEW-02 — сломан чистый production-запуск.** Прямое следствие R-07: строка `TELEGRAM_BOT_POLL_TOKEN: "${TELEGRAM_BOT_TOKEN:?…}"` добавлена в `6094c6b` для гарантии единственного потребителя `getUpdates`. Побочный эффект — весь `docker-compose.production.yml` перестал интерполироваться. В `ca8d45d` файл парсился. **Критичность: Critical.**

2. **NEW-01 — новый durable-слой не работает на production-СУБД.** Прямое следствие R-05/R-10/R-19: файлы `studio/dispatch.py` (+390 строк), `core_ui/services/operator_dispatch.py` (+229 строк), `servers/services/server_ownership.py` (+94 строки) созданы в этом коммите и все три содержат одну и ту же несовместимую с PostgreSQL конструкцию. До коммита этих путей не существовало вовсе — то есть заменой «работает плохо» стало «не работает». **Критичность: Critical.**

3. **NEW-05 — throttle логина стал общесистемным при непрописанном `TRUSTED_PROXY_HOPS`.** Следствие связки R-01 + R-02: раньше блокировался username, теперь блокируется IP — но при `hops=0` этот IP один на весь деплой. Форма проблемы P-05 сменилась, масштаб вырос с одной учётки до всех. **Критичность: High.**

4. **NEW-12 — ослаблены тестовые настройки.** В `web_ui/settings/test.py` добавлено отключение трёх лимитов приложения. Заметно, что одновременно **убрана** строка `PIPELINE_RUNS_DISABLE_BACKGROUND = True` — это усиление (фоновый путь теперь реально исполняется в тестах), и его следует засчитать в плюс. Но отключение rate-limit — ослабление. **Критичность: Medium.**

5. **NEW-13 — `pipeline-execution` закреплён `container_name`**, хотя вся задача R-19/R-20 была про снятие таких ограничений. Для `backend`, `operator-execution` и `playbook-execution-worker` имя снято корректно — для `pipeline-execution` забыто. **Критичность: Medium.**

---

## 8. CI и эксплуатационные проверки

Набор прогонов для `6094c6b`, событие `push`, время постановки `2026-07-31T09:10:45Z`.

| Workflow | Run ID | Статус | Точная причина падения |
|---|---|---|---|
| **Backend CI** | 30618969209 | ❌ **failure** | Два job'а из семи. См. разбор ниже |
| **Frontend CI** | 30618969356 | ✅ success | — |
| **Security** | 30618969208 | ✅ success | — |
| **Architecture Fitness** | 30618969220 | ✅ success | — |
| **Playwright Smoke** | 30618969296 | ✅ success | — |
| **Production Install Smoke** | 30618969219 | ❌ **failure** | Job «Clean Linux Install and Runtime Smoke», шаг «Run production install, readiness and worker smoke»: `error while interpolating services.telegram-bot.environment.TELEGRAM_BOT_POLL_TOKEN: required variable TELEGRAM_BOT_TOKEN is missing a value: TELEGRAM_BOT_TOKEN is required for telegram-bot` → `Process completed with exit code 1` |
| **Production Recovery Smoke** | 30618969295 | ❌ **failure** | Job «Isolated Backup Restore and Restart Recovery», шаг «Run production backup, isolated restore and recovery smoke»: **та же** ошибка интерполяции |
| **Production Upgrade Rollback Smoke** | 30618969370 | ❌ **failure** | **Обе** матричные ветки — «Upgrade and Rollback (v0.1.0-rc.1)» и «Upgrade and Rollback (schema-snapshot-b8924ee)»: **та же** ошибка интерполяции |

### Backend CI — детализация по job'ам

| Job | Статус | Причина |
|---|---|---|
| Runtime Contract | ✅ success | — |
| Python Quality | ✅ success | — |
| Django Checks | ✅ success | `check`, migration drift, OpenAPI drift — чисто |
| PostgreSQL and Redis Integration | ✅ success | `tests/test_ci_postgres_redis.py` прошёл |
| Documentation Contract | ✅ success | — |
| **Backend Unit and Coverage** (id 91118700059) | ❌ **failure** | `= 10 failed, 2767 passed, 3 warnings, 10 subtests passed in 505.59s (0:08:25) =` |
| **Production Checks** (id 91118700139) | ❌ **failure** | Шаги «Django production deploy check» и «Prove production deploy check rejects SQLite fallback» **прошли**. Упал последний шаг — `docker compose -f docker-compose.production.yml config --quiet`: `error while interpolating services.telegram-bot.environment.TELEGRAM_BOT_POLL_TOKEN: required variable TELEGRAM_BOT_TOKEN is missing a value` |

### Полный список упавших тестов (PostgreSQL 16)

```
FAILED tests/test_server_ownership_and_bulk_operations.py::test_server_owner_transfer_rejects_viewer_and_non_owner
       - assert 500 == 400
FAILED tests/test_multi_instance_orchestration.py::test_backend_b_can_snapshot_and_stop_turn_claimed_by_backend_a
       - django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
FAILED tests/test_multi_instance_orchestration.py::test_different_worker_executes_durable_dispatch_and_persists_turn
       - django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
FAILED tests/test_pipeline_dispatch.py::test_expired_lease_is_reclaimed_and_old_attempt_is_fenced
       - django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
FAILED tests/test_pipeline_dispatch.py::test_failed_attempt_is_requeued_until_max_attempts
       - django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
FAILED tests/test_pipeline_dispatch.py::test_per_user_and_global_claim_limits_are_database_enforced
       - django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
FAILED tests/test_pipeline_dispatch.py::test_ten_active_runs_survive_backend_restart_and_finish_in_worker
       - django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
FAILED tests/test_pipeline_resume.py::test_resume_uses_completed_nodes_and_retries_only_failed_idempotent_node
       - django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
FAILED tests/test_pipeline_resume.py::test_non_idempotent_retry_requires_explicit_operator_confirmation
       - django.db.utils.NotSupportedError: FOR UPDATE cannot be applied to the nullable side of an outer join
FAILED tests/test_server_ownership_and_bulk_operations.py::test_server_owner_transfer_preserves_server_and_revokes_old_runtime_access
       - assert 500 == 200
```

Отдельно отмечу: **упали ровно те тесты, которые объявлены доказательствами R-05, R-10 и R-19.** Это не случайные флаки — это провал центральной части ремедиации.

### Статистика тестов

| Показатель | Значение | Источник |
|---|---|---|
| Собрано | **2777** | локально, `--collect-only -q` |
| Прошло (PostgreSQL) | **2767** + 10 subtests | лог CI |
| Упало (PostgreSQL) | **10** | лог CI |
| Пропущено | **0** явных skip в итоговой строке | лог CI |
| Coverage gate | `--cov-fail-under=71.5` (baseline 71.95 %) — до порога дело не дошло, job упал на тестах | `backend-ci.yml:129-140` |
| Требуют PostgreSQL + Redis | весь `backend-unit` и `backend-integration` job'ы (`WEBTERM_REQUIRE_EXTERNAL_TEST_SERVICES=1`) | `backend-ci.yml:105-114` |
| Реальный background-path | **да** — `PIPELINE_RUNS_DISABLE_BACKGROUND` удалён из `web_ui/settings/test.py` в этом коммите | `git diff` |
| Тесты на несколько процессов | `tests/test_multi_instance_orchestration.py` — **эмулирует** два инстанса в одном процессе через разные `worker_key`; настоящих multi-process тестов нет | чтение теста |
| Ложнозелёные | **да**, подтверждено: 12 тестов зелёные на SQLite, 8 из них красные на PostgreSQL | локальный прогон + лог CI |

---

## 9. Что нельзя подтвердить (и что нужно для доказательства)

| Пункт | Почему не проверено | Что нужно сделать |
|---|---|---|
| «10 прогонов + убийство воркера» на реальной СУБД | Нет локального PostgreSQL; docker запрещён из-за 2 ГБ свободного места. И это бессмысленно до исправления NEW-01 | Поднять PostgreSQL, запустить `pipeline-execution`, создать 10 прогонов, `docker kill` воркера в середине, убедиться что все 10 дошли до terminal state ровно один раз и `attempt_count` вырос на 1 |
| Отсутствие двойного исполнения при конкуренции двух воркеров | То же | Два процесса `run_pipeline_execution_plane` с разными `--worker-key` на одной БД + счётчик побочных эффектов в узле |
| Graceful shutdown и `stop_grace_period: 45s` | Требует запуска контейнеров | `docker compose stop pipeline-execution` во время активного прогона; проверить, что lease освобождён, а не «завис» |
| Production install / backup-restore / upgrade-rollback | Все три smoke-workflow упали **до** содержательной части (NEW-02) | Исправить NEW-02 и получить зелёные `production-install-smoke`, `production-recovery-smoke`, `production-upgrade-rollback-smoke` |
| Два инстанса backend (`--scale backend=2`) | Docker не запускался; и подсистема падает на PostgreSQL | После NEW-01: два backend'а, стоп turn'а с инстанса B по turn'у, начатому на A |
| Ускорение SSH-пула ≥5× | Бенчмарка нет в репозитории; требуется живой SSH-хост | Замер: N последовательных SFTP-операций с пулом и без, на реальном сервере |
| Отзыв SSH-доступа при нескольких процессах | Пул процесс-локальный, тесты через `monkeypatch` | Два backend-процесса, открыть сессию на обоих, отозвать доступ на одном, проверить второй |
| Нагрузка 20–30 одновременных пользователей | Нагрузочных сценариев в репозитории нет вообще | Locust/k6 на `/api/`: p95 latency, число соединений PostgreSQL (`max_connections=200`), Redis, память и FD воркеров |
| Latency API, блокировки БД, рост таблиц под нагрузкой | То же | То же + `pg_stat_activity`/`pg_locks` во время прогона |
| Поведение Telegram при двух процессах и потеря callback после рестарта | Требует живого бота и токена | Запустить два `run_telegram_bot` на одном токене, убедиться что второй отказывает; убить бота в момент нажатия кнопки, проверить что решение долетело после рестарта по персистентному офсету |
| Реальные ограничения БД при миграции секретов (частичный сбой, откат) | Требует production-подобного набора данных | Прогон `migrate_legacy_server_secrets --apply` на копии БД с намеренно испорченным шифротекстом; проверить, что частичный сбой не оставляет смешанное состояние |
| Поведение `/metrics` при недоступной БД | Код обрабатывает (`app/prometheus_registry.py:26-33`), но эмпирически не проверено | Остановить PostgreSQL, вызвать `/metrics`, убедиться в `webterm_metrics_provider_up{...} 0` и HTTP 200 |

---

## 10. Оставшийся backlog

### P0 — блокирует любой запуск

**B-01. Починить `select_for_update` в durable-слое**
- Результат: `claim_next_pipeline_dispatch`, `claim_next_operator_dispatch`, `complete/retry_pipeline_dispatch`, `_fail_exhausted_dispatches` и `transfer_server_ownership` выполняются на PostgreSQL без исключений.
- Файлы: `studio/dispatch.py:125-126, 176-177, 245-246, 275-276`; `core_ui/services/operator_dispatch.py:84-85`; `servers/services/server_ownership.py:39`.
- Зависимости: нет.
- Сложность: **S**.
- Критерий готовности: job «Backend Unit and Coverage» зелёный на PostgreSQL; дополнительно — тест, который проверяет, что ни один `select_for_update()` в проекте не сочетается с `select_related()` по nullable FK без `of=("self",)`.

**B-02. Восстановить парсируемость production compose**
- Результат: `docker compose --env-file .env.production -f docker-compose.production.yml config --quiet` проходит на немодифицированном `.env.production.example`.
- Файлы: `docker-compose.production.yml:705`; при необходимости `studio/management/commands/run_telegram_bot.py` (проверка непустого токена там уже есть, `:79-86`).
- Зависимости: нет.
- Сложность: **S**.
- Критерий готовности: зелёные `Production Install Smoke`, `Production Recovery Smoke`, `Production Upgrade Rollback Smoke` и шаг «Validate production Compose model» в Backend CI.

**B-03. Не глотать сбой claim в воркерах**
- Результат: исключение в `claim_*` логируется, воркер выдерживает паузу и продолжает цикл вместо падения контейнера; в метрики уходит счётчик ошибок claim.
- Файлы: `studio/management/commands/run_pipeline_execution_plane.py:100-131`; `core_ui/management/commands/run_operator_execution_plane.py:67-80`.
- Зависимости: B-01 (чинит причину, B-03 чинит поведение при любой будущей причине).
- Сложность: **S**.
- Критерий готовности: при принудительной ошибке БД воркер не выходит, а пишет ошибку и повторяет; `webterm_*_claim_errors_total` растёт.

### P1 — блокирует пилот с реальными пользователями

**B-04. Валидировать compose реальным `docker compose config`, а не YAML-парсером**
- Результат: contract-тест или CI-шаг, который выполняет `docker compose config` для всех трёх production-compose файлов на `.env.production.example`.
- Файлы: `tests/test_production_worker_topology.py`, `.github/workflows/backend-ci.yml`.
- Зависимости: B-02.
- Сложность: **S**.
- Критерий готовности: намеренное внесение `${MISSING:?}` роняет проверку.

**B-05. Durable-тесты должны падать на SQLite, а не тихо проходить**
- Результат: тесты, доказывающие lease/fencing/multi-instance, помечены как требующие PostgreSQL и на SQLite дают ошибку окружения, а не PASS.
- Файлы: `tests/test_pipeline_dispatch.py`, `tests/test_pipeline_resume.py`, `tests/test_multi_instance_orchestration.py`, `conftest.py`.
- Зависимости: B-01.
- Сложность: **M**.
- Критерий готовности: `DJANGO_SETTINGS_MODULE=web_ui.settings.test pytest tests/test_pipeline_dispatch.py` завершается ошибкой «requires PostgreSQL».

**B-06. Зафиксировать `TRUSTED_PROXY_HOPS` в production-топологии**
- Результат: переменная задана в `environment:` compose со значением `1`; при `DEBUG=False`, `hops=0` и присутствующем `X-Forwarded-For` — явная ошибка конфигурации в `check --deploy`.
- Файлы: `docker-compose.production.yml`, `web_ui/settings/security.py:134`, `core_ui/checks.py`.
- Зависимости: нет.
- Сложность: **S**.
- Критерий готовности: тест через полный middleware-стек, где два разных клиента за одним прокси получают независимые счётчики throttle.

**B-07. Устранить общесистемную блокировку логина и гонку счётчика**
- Результат: инкремент и проверка лимита выполняются одной атомарной операцией; задержка не блокирует поток воркера.
- Файлы: `core_ui/auth_throttle.py:100-122`.
- Зависимости: B-06.
- Сложность: **M**.
- Критерий готовности: тест на общем Redis из двух процессов — 20 неудач с IP A не мешают входу с IP B; параллельные 50 запросов не превышают лимит.

**B-08. Реальное эксплуатационное доказательство восстановления**
- Результат: пройденный сценарий «10 активных прогонов → `docker kill pipeline-execution` → рестарт → все 10 доведены до terminal state ровно один раз» и «стоп operator turn'а с другого backend-инстанса».
- Файлы: новый скрипт в `docker/`, workflow `production-recovery-smoke.yml`.
- Зависимости: B-01, B-02, B-03.
- Сложность: **L**.
- Критерий готовности: артефакт workflow с логами и итоговым состоянием прогонов.

### P2 — необходимо до роста нагрузки

**B-09. Индексы под retention**
- Результат: индексы, покрывающие `order_by(<timestamp>, pk)` для `CommandSnapshot.created_at`, `ServerHealthCheck.checked_at`, `ChatArtifact.created_at`, `ServerCommandHistory.executed_at`.
- Файлы: `servers/models_inventory.py`, `servers/models_monitoring.py`, `core_ui/models/chat.py` + миграции.
- Сложность: **S**. Критерий: `EXPLAIN` prune-запроса показывает index scan, не seq scan.

**B-10. Расширить схемы валидации на мутирующие маршруты**
- Результат: типизированная схема минимум для всех POST/PUT/PATCH под `/api/servers/`, `/api/studio/`, `/api/access/` — приоритет по частоте использования.
- Файлы: `core_ui/schemas/http.py:111-124`.
- Сложность: **XL** (246 операций). Критерий: покрытие ≥60 % мутирующих операций строгими схемами + контрактный тест «неизвестное поле → 400».

**B-11. Убрать очистку доставок из HTTP-пути webhook**
- Результат: удаление старых `PipelineWebhookDelivery` перенесено в `prune_history`.
- Файлы: `studio/views/trigger_views.py:325-326`, `core_ui/history_retention.py`.
- Сложность: **S**. Критерий: приём webhook выполняет ≤3 запроса.

**B-12. Закрыть `/metrics` аутентификацией**
- Результат: bearer-токен или mTLS на эндпоинте; ACL nginx сужен до сети мониторинга.
- Файлы: `core_ui/views/metrics_views.py`, `docker/nginx/webterm-server-common.conf:58-66`.
- Сложность: **S**. Критерий: запрос без токена из подсети `192.168.0.0/16` получает 403.

**B-13. Завершить миграцию секретов до конца**
- Результат: `store_*_secret` сохраняет очистку legacy-полей; readiness показывает число оставшихся legacy-строк; миграция удаления колонок запланирована.
- Файлы: `servers/secret_utils.py:67-96`, `web_ui/services/settings_readiness*.py`, новая миграция.
- Сложность: **M**. Критерий: `Server.objects.exclude(encrypted_password="").count() == 0` на тестовом наборе после штатной смены секретов.

**B-14. Снять `container_name` с `pipeline-execution`; метрики очереди operator turns**
- Файлы: `docker-compose.production.yml:399`, `core_ui/prometheus_metrics.py` (создать по образцу `studio/prometheus_metrics.py`).
- Сложность: **S**. Критерий: `--scale pipeline-execution=2` работает; `webterm_operator_queue_depth` присутствует в `/metrics`.

**B-15. Нагрузочный сценарий на 20–30 пользователей**
- Результат: воспроизводимый k6/Locust-сценарий и зафиксированный baseline p95, число соединений БД, память и FD.
- Сложность: **L**. Критерий: отчёт с числами приложен к релизу.

---

## 11. Финальный ответ без дипломатии

**1. Все ли проблемы предыдущего аудита исправлены?**
Нет. 9 из 24 задач закрыты полностью, 11 закрыты частично, 3 не закрыты, 1 привела к регрессии. Более того, три задачи с приоритетом P0 предыдущего аудита (R-05, R-10 в части исполнения и R-19) сейчас находятся в худшем состоянии, чем до коммита: раньше пайплайны исполнялись в потоке и терялись при рестарте, теперь они не исполняются вообще.

**2. Какие проблемы всё ещё блокируют production?**
Две, и обе абсолютные:
- **NEW-01**: `select_for_update()` + `select_related()` по nullable FK в шести местах нового durable-слоя. На PostgreSQL это `NotSupportedError` на первом же вызове. Пайплайны, Operator Chat и передача владения сервером не работают. Воркеры уходят в crash-loop.
- **NEW-02**: `docker-compose.production.yml` не интерполируется без непустого `TELEGRAM_BOT_TOKEN`. Стек невозможно поднять штатной командой из README.

Далее по убыванию: NEW-05 (10 неудачных логинов кладут аутентификацию всему деплою), NEW-03/NEW-04 (тестовая база не ловит оба класса дефектов), R-16 (валидация на 4,5 % мутирующих маршрутов).

**3. Какие исправления оказались формальными или неполными?**
- **R-16** — схемы добавлены на 12 маршрутов из 246. Формально «схемы есть», по сути валидации нет.
- **R-12** — кэш написан корректно, но `request=` передаётся в 4 из 46 мест вызова. Заявленное снижение нагрузки на БД не реализовано.
- **R-14** — миграция rewritten, рабочий путь чист, но `encrypted_password` не очищен ни у кого, а `store_server_auth_secret` даже не сохраняет очистку в БД. Критерий «пуст везде» недостижим штатной эксплуатацией.
- **R-11** — четыре триггера инвалидации есть, но все тесты через `monkeypatch` проверяют факт вызова, а не закрытие соединения; обещанный бенчмарк ≥5× не написан; пул процесс-локальный, то есть при масштабировании отзыв доступа не работает.
- **R-08** — политика ретеншена есть, индексов под неё нет: очистка самой большой таблицы идёт seq scan'ом.
- **R-05** — команда reconcile есть и вызывается, но в текущем состоянии её единственный эффект — массовый перевод прогонов в `failed`.

**4. Появились ли новые критические проблемы?**
Да, две (NEW-01, NEW-02), и обе — прямые побочные эффекты работы по этому же аудиту. Плюс три High (NEW-03, NEW-04, NEW-05).

**5. Можно ли запускать систему для реальных пользователей?**
Нет. Не «рискованно» — а технически невозможно: `docker compose up -d` завершится ошибкой, а при ручном обходе этой ошибки пользователь получит систему, в которой не запускается ни один пайплайн и не отвечает Operator Chat.

**6. Какова точная следующая последовательность действий?**

1. **B-01** — добавить `of=("self",)` (или убрать nullable-связи из `select_related`) в шести местах: `studio/dispatch.py:126,177,246,276`, `core_ui/services/operator_dispatch.py:85`, `servers/services/server_ownership.py:39`.
2. **B-02** — заменить `${TELEGRAM_BOT_TOKEN:?…}` на `${TELEGRAM_BOT_TOKEN:-}` в `docker-compose.production.yml:705`; проверка непустоты уже реализована внутри `run_telegram_bot.py:79-86`.
3. Дождаться **полностью зелёного** набора из восьми workflow на новом коммите. До этого момента к остальным пунктам не переходить.
4. **B-04** и **B-05** — закрыть оба слепых пятна тестовой базы, иначе следующий дефект того же класса снова пройдёт 2777 тестов.
5. **B-03** — воркеры не должны падать контейнером при ошибке claim.
6. **B-06** и **B-07** — `TRUSTED_PROXY_HOPS` в топологию, атомарный счётчик throttle.
7. **B-08** — реальный сценарий «10 прогонов + убийство воркера» и восстановление turn'а со второго backend-инстанса. **Только после этого** можно впервые обсуждать готовность к пилоту.
8. Далее P2 в порядке B-09 → B-12 → B-11 → B-13 → B-14 → B-10 → B-15.

---

## Приложение A — исправления, внесённые после аудита

Аудит выше описывает состояние коммита `6094c6b`. Ниже — что было исправлено уже после его публикации, в рабочей папке той же ветки. Коммит не создавался.

### Две поправки к самому аудиту

1. **Ошибка отчёта.** В первой редакции матрицы R-01 утверждалось, что в nginx нет `set_real_ip_from`/`real_ip_header`. Это неверно: `docker/nginx/production.conf:12-14` содержит все три директивы. Проверялся только `webterm-server-common.conf`. Строка исправлена; вывод по R-01 (`PARTIALLY FIXED`) не меняется — он держится на незаданном `TRUSTED_PROXY_HOPS`, а не на конфигурации nginx.
2. **NEW-07 понижена с Medium до Low.** `docker/nginx/production.conf:6` ограничивает `/api/auth/` до `rate=10r/m` на IP, что существенно сужает окно удержания потоков.

### Исправленные дефекты

| Дефект | Что сделано | Файлы | Доказательство |
|---|---|---|---|
| **NEW-01** (Critical) | `of=("self",)` в 7 местах. Полный перечень получен интроспекцией моделей, а не поиском по тексту: из 18 связок `select_for_update`+`select_related` затронуты ровно 4 модели | `studio/dispatch.py` (×4), `core_ui/services/operator_dispatch.py`, `servers/services/server_ownership.py`, `studio/pipeline/pipeline_resume.py` | Компиляция запросов PostgreSQL-бэкендом офлайн: было `FOR UPDATE SKIP LOCKED` при `LEFT OUTER JOIN`, стало `FOR UPDATE OF "<таблица>" SKIP LOCKED` |
| **NEW-01 (дополнение)** | В аудите было названо 6 мест; интроспекция нашла седьмое — `studio/pipeline/pipeline_resume.py:148` | — | `PipelineRun.triggered_by` nullable |
| **NEW-02** (Critical) | `${TELEGRAM_BOT_TOKEN:?…}` → `${TELEGRAM_BOT_TOKEN:-}`. Остальные `:?` в файле (`STUDIO_MCP_RUNNER_TOKEN`, `AGENT_COMMAND_RUNNER_IMAGE`) оставлены: они законно обязательны и заполняются установщиком (`docker/install-production.sh:395,655`) до вызова compose | `docker-compose.production.yml:705` | Реальный `docker compose config` на чистом `.env.production.example`: до — `EXIT=1` с той же ошибкой, что в CI; после — `EXIT=0` |
| **NEW-03** (High) | Статический guard, ловящий класс дефекта на SQLite: разбор AST + резолв моделей + проверка nullability пути `select_related` | `tests/test_select_for_update_join_safety.py` (новый) | Guard проверен «от обратного»: при откате одной правки падает с точным `file:line` и указанием nullable-поля |
| **NEW-04** (High) | Шаг валидации compose в CI переведён на `--env-file` — то есть на путь, описанный в README. Раньше пример вообще не читался | `.github/workflows/backend-ci.yml` | Именно отсутствие `--env-file` позволило NEW-02 пройти |
| **NEW-05** (High) | Deploy-check `core_ui.W001`: предупреждает, когда прокси доверяют по протоколу (`SECURE_PROXY_SSL_HEADER`), но не по IP (`TRUSTED_PROXY_HOPS=0`) | `core_ui/checks.py`, `tests/test_core_deploy_checks.py` | 5 сценариев: срабатывает только на противоречивой комбинации, в CI молчит |
| **NEW-07** (Low) | Проверка IP-лимита перенесена **перед** задержкой: запрос, который всё равно получит 429, больше не удерживает поток | `core_ui/auth_throttle.py` | — |
| **NEW-09** (Medium) | Индексы под ретеншен для 4 таблиц, которые чистятся по `.all()`. Для `PipelineRun`/`AgentRun`/`ServerAlert` индексы **не** добавлялись: существующие `(status, timestamp)` и `(is_resolved, created_at)` уже покрывают фильтр очистки | `servers/migrations/0056_*`, `core_ui/migrations/0024_*` | Покрытие определено интроспекцией `Meta.indexes`, не на глаз |
| **Наблюдаемость** | Метрики очереди operator turns и здоровья обеих очередей: `queue_depth`, `queue_oldest_age_seconds`, `inflight`, `stalled`, `retrying`, `failed`, `open_dead_letters`. Реализованы как gauge поверх durable-таблиц, поэтому одинаковы во всех процессах и переживают рестарт | `core_ui/prometheus_metrics.py` (новый), `studio/prometheus_metrics.py`, `core_ui/apps.py` | `tests/test_prometheus_metrics.py` |
| **Устойчивость воркеров** | `claim` обёрнут в обоих execution plane: ошибка БД больше не убивает контейнер под `restart: unless-stopped`. В режиме `--once` ошибка по-прежнему поднимается, чтобы CI её видел | `studio/management/commands/run_pipeline_execution_plane.py`, `core_ui/management/commands/run_operator_execution_plane.py` | Счётчик `claim_errors` в summary воркера |

### Проверки после правок

- `pytest tests` — **2724 passed, 7 skipped, 0 failed** (на исходном коммите те же тесты давали 10 падений на PostgreSQL)
- `ruff format --check .` — 1596 файлов чисто; `ruff check .` — без замечаний
- `manage.py makemigrations --check --dry-run` — дрейфа нет
- `scripts/env_contract.py --check` — 304 переменные, контракт цел
- `docker compose --env-file … config --quiet` — модель валидна

### Что по-прежнему не подтверждено

Локального PostgreSQL нет, а SQLite `FOR UPDATE` не исполняет вообще. Исправление NEW-01 доказано на уровне сгенерированного SQL, но **окончательное подтверждение — только зелёный `Backend CI` на PostgreSQL**. Три production-smoke по-прежнему ни разу не выполняли своё содержимое: пока они не станут зелёными, у install, backup/restore и upgrade/rollback доказательств нет.

Вердикт первой строки (`NO-GO`) остаётся в силе до зелёного CI.

---

### Замечание о качестве самого CI

Единственная по-настоящему хорошая новость этого аудита: **CI отработал честно.** Он поймал обе критические проблемы, показал точный SQL и точное исключение, и стоит красным. Ни один гейт не был обойдён. Проблема не в CI, а в том, что коммит был объявлен реализацией плана ремедиации при четырёх красных workflow из восьми.

Разница между «код написан» и «проблема устранена» в этом коммите измерима буквально: 35 877 добавленных строк, 2767 зелёных тестов — и ноль исполненных пайплайнов на целевой СУБД.
