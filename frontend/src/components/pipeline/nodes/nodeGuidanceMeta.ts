import type { NodeGuidanceMeta } from "./nodeMetaTypes";
export const NODE_TYPE_GUIDANCE_META: Record<string, NodeGuidanceMeta> = {
  "trigger/manual": {
    category: { ru: "Триггер", en: "Trigger" },
    summary: {
      ru: "Ручной триггер запускает пайплайн из интерфейса Studio или из внутреннего API по команде оператора.",
      en: "Manual triggers let an operator or an internal API start the pipeline on demand.",
    },
    checklist: {
      ru: ["Оставьте триггер активным", "Запускайте пайплайн из toolbar или через API"],
      en: ["Keep the trigger enabled", "Run the pipeline from the toolbar or API"],
    },
  },
  "trigger/webhook": {
    category: { ru: "Триггер", en: "Trigger" },
    summary: {
      ru: "Webhook принимает HTTP POST и раскладывает входной payload в переменные контекста пайплайна.",
      en: "Webhook triggers accept HTTP POST payloads and map them into pipeline context variables.",
    },
    checklist: {
      ru: ["Сохраните пайплайн, чтобы получить URL", "Сопоставьте поля payload с контекстом", "Проверьте запуск sample curl-запросом"],
      en: ["Save the pipeline to get the webhook URL", "Map payload fields into context variables", "Test with a sample curl payload"],
    },
  },
  "trigger/schedule": {
    category: { ru: "Триггер", en: "Trigger" },
    summary: {
      ru: "Планировщик запускает пайплайн автоматически по cron-выражению.",
      en: "Schedule triggers run the pipeline automatically on a cron expression.",
    },
    checklist: {
      ru: ["Выберите или вставьте cron из 5 полей", "Оставьте триггер активным", "Проверьте окно запуска и частоту"],
      en: ["Choose or paste a 5-field cron expression", "Keep the trigger enabled", "Verify the schedule fits the operational window"],
    },
  },
  "trigger/monitoring": {
    category: { ru: "Триггер", en: "Trigger" },
    summary: {
      ru: "Monitoring-триггер запускает пайплайн, когда мониторинг сервера открывает подходящий alert.",
      en: "Monitoring triggers start the pipeline when server monitoring opens a matching alert.",
    },
    checklist: {
      ru: ["Выберите серверы или оставьте все", "Отфильтруйте severity / alert type", "При необходимости укажите имена Docker-контейнеров"],
      en: ["Select servers or leave all", "Filter by severity or alert type", "Optionally narrow to Docker container names"],
    },
  },
  "agent/react": {
    category: { ru: "Агент", en: "Agent" },
    summary: {
      ru: "ReAct-агент рассуждает над задачей и сам выбирает инструменты, серверы, MCP и skills во время выполнения.",
      en: "ReAct agents reason over the task and choose tools, servers, MCPs, and skills during execution.",
    },
    checklist: {
      ru: ["Опишите цель", "Выберите сохранённого агента или настройте шаг прямо здесь", "Подключите серверы, MCP или skills"],
      en: ["Describe the goal", "Choose a saved agent or configure the node inline", "Attach targets such as servers, skills, or MCPs"],
    },
  },
  "agent/multi": {
    category: { ru: "Агент", en: "Agent" },
    summary: {
      ru: "Мультиагент координирует работу нескольких целей или узких исполнителей.",
      en: "Multi-agent nodes coordinate work across several targets or sub-specialists.",
    },
    checklist: {
      ru: ["Определите цель оркестрации", "Выберите сохранённого агента или настройте шаг прямо здесь", "Подключите нужные серверы и MCP"],
      en: ["Define the orchestration goal", "Choose a saved agent or configure the node inline", "Attach the servers or MCPs to coordinate"],
    },
  },
  "agent/ssh_cmd": {
    category: { ru: "Агент", en: "Agent" },
    summary: {
      ru: "SSH-шаг выполняет одну конкретную команду без LLM-планирования.",
      en: "SSH command nodes execute a concrete command directly without LLM tool planning.",
    },
    checklist: {
      ru: ["Выберите целевой сервер", "Вставьте точную команду для запуска"],
      en: ["Select the target server", "Paste the exact command to run"],
    },
  },
  "agent/llm_query": {
    category: { ru: "Агент", en: "Agent" },
    summary: {
      ru: "LLM-запрос подходит для анализа, суммаризации и принятия решений без автономных инструментов.",
      en: "LLM query nodes are pure reasoning steps for analysis, summarization, or decision support.",
    },
    checklist: {
      ru: ["Напишите prompt", "Используйте Auto: провайдер и модель задаются настройками рабочей области", "Подставьте переменные пайплайна при необходимости"],
      en: ["Write the prompt", "Use Auto: provider and model come from workspace settings", "Use pipeline variables where needed"],
    },
  },
  "agent/mcp_call": {
    category: { ru: "Агент", en: "Agent" },
    summary: {
      ru: "MCP-вызов запускает один конкретный инструмент с фиксированными JSON-аргументами.",
      en: "MCP call nodes execute a specific MCP tool with structured JSON arguments.",
    },
    checklist: {
      ru: ["Выберите MCP-сервер", "Выберите инструмент", "Укажите валидный JSON аргументов"],
      en: ["Select the MCP server", "Select the tool", "Provide valid JSON arguments"],
    },
  },
  "ops/server_snapshot": {
    category: { ru: "OPS", en: "Ops" },
    summary: {
      ru: "Собирает безопасный read-only снимок сервера через существующие Linux UI collectors.",
      en: "Collects a safe read-only server snapshot through existing Linux UI collectors.",
    },
    checklist: {
      ru: ["Выберите сервер или оставьте server_id из контекста", "Отметьте нужные разделы снимка"],
      en: ["Select a server or use server_id from context", "Choose the snapshot sections"],
    },
  },
  "ops/log_query": {
    category: { ru: "OPS", en: "Ops" },
    summary: {
      ru: "Собирает read-only логи из journalctl, service journal, Docker logs или типовых файлов /var/log.",
      en: "Collects read-only logs from journalctl, service journal, Docker logs, or common /var/log files.",
    },
    checklist: {
      ru: ["Выберите сервер или используйте server_id из контекста", "Выберите источник логов", "Для service/docker укажите unit или container"],
      en: ["Select a server or use server_id from context", "Choose the log source", "For service/docker, set the unit or container"],
    },
  },
  "ops/file_action": {
    category: { ru: "OPS", en: "Ops" },
    summary: {
      ru: "Читает или записывает UTF-8 текстовые файлы через существующий SFTP слой WebTerm.",
      en: "Reads or writes UTF-8 text files through WebTerm's existing SFTP layer.",
    },
    checklist: {
      ru: ["Выберите сервер или используйте server_id из контекста", "Укажите path", "Для write поставьте approval перед нодой"],
      en: ["Select a server or use server_id from context", "Set the path", "Place approval before write actions"],
    },
  },
  "ops/package_action": {
    category: { ru: "OPS", en: "Ops" },
    summary: {
      ru: "Показывает доступные обновления или выполняет install/update/remove для явного списка пакетов.",
      en: "Lists package updates or runs install/update/remove for an explicit package list.",
    },
    checklist: {
      ru: ["Для list_updates approval не нужен", "Для install/update/remove укажите пакеты", "Поставьте approval перед изменением пакетов"],
      en: ["list_updates does not need approval", "For install/update/remove, set package names", "Place approval before package changes"],
    },
  },
  "ops/disk_cleanup": {
    category: { ru: "OPS", en: "Ops" },
    summary: {
      ru: "Показывает disk usage или выполняет ограниченную очистку journal/tmp на Linux сервере.",
      en: "Inspects disk usage or runs bounded journal/tmp cleanup on a Linux server.",
    },
    checklist: {
      ru: ["Inspect approval не требует", "Для journal_vacuum/tmp_cleanup поставьте approval", "Используйте dry-run перед реальной очисткой"],
      en: ["inspect does not require approval", "Place approval before journal_vacuum/tmp_cleanup", "Use dry-run before real cleanup"],
    },
  },
  "ops/backup_restore_check": {
    category: { ru: "OPS", en: "Ops" },
    summary: {
      ru: "Проверяет каталог backup: свежесть последнего файла и целостность последнего архива без восстановления.",
      en: "Checks a backup directory for latest-file freshness and archive integrity without restore.",
    },
    checklist: {
      ru: ["Укажите путь к backup", "Задайте допустимый возраст backup", "Используйте verify_latest для проверки целостности tar/gz/zip"],
      en: ["Set the backup path", "Set the accepted backup age", "Use verify_latest for tar/gz/zip integrity checks"],
    },
  },
  "ops/service_action": {
    category: { ru: "OPS", en: "Ops" },
    summary: {
      ru: "Выполняет systemd action как структурированный шаг с preflight и verification.",
      en: "Runs a systemd action as a structured step with preflight and verification.",
    },
    checklist: {
      ru: ["Выберите сервер", "Укажите unit и action", "Поставьте approval перед нодой для изменений"],
      en: ["Select a server", "Set unit and action", "Place approval before this node for mutations"],
    },
  },
  "ops/docker_action": {
    category: { ru: "OPS", en: "Ops" },
    summary: {
      ru: "Выполняет Docker action для контейнера и собирает inspect/logs после изменения.",
      en: "Runs a Docker container action and collects inspect/logs after the change.",
    },
    checklist: {
      ru: ["Выберите сервер", "Укажите контейнер или {container_name}", "Добавьте approval для restart/stop/start"],
      en: ["Select a server", "Set the container or {container_name}", "Add approval for restart/stop/start"],
    },
  },
  "ops/process_action": {
    category: { ru: "OPS", en: "Ops" },
    summary: {
      ru: "Завершает процесс по PID; force kill должен использоваться только как break-glass действие.",
      en: "Terminates a process by PID; force kill should be a break-glass action only.",
    },
    checklist: {
      ru: ["Передайте PID явно или из контекста", "Используйте approval перед kill_force"],
      en: ["Pass PID explicitly or from context", "Use approval before kill_force"],
    },
  },
  "ops/http_check": {
    category: { ru: "OPS", en: "Ops" },
    summary: {
      ru: "Проверяет HTTP endpoint по статусу и опциональному фрагменту body.",
      en: "Checks an HTTP endpoint by status and optional body fragment.",
    },
    checklist: {
      ru: ["Укажите URL", "Задайте ожидаемые статусы", "Добавьте body contains при необходимости"],
      en: ["Set the URL", "Set expected statuses", "Add body contains if needed"],
    },
  },
  "ops/alert_update": {
    category: { ru: "OPS", en: "Ops" },
    summary: {
      ru: "Обновляет алерт мониторинга WebTerm, например закрывает его после успешной проверки.",
      en: "Updates a WebTerm monitoring alert, for example resolving it after successful verification.",
    },
    checklist: {
      ru: ["Передайте alert_id из monitoring trigger", "Подключайте после успешной проверки"],
      en: ["Pass alert_id from a monitoring trigger", "Place it after successful verification"],
    },
  },
  "logic/condition": {
    category: { ru: "Логика", en: "Logic" },
    summary: {
      ru: "Условие выбирает продолжение пайплайна по результату или статусу предыдущего шага.",
      en: "Condition nodes decide which path continues based on a prior node output or status.",
    },
    checklist: {
      ru: ["Выберите тип проверки", "При необходимости задайте значение для сравнения"],
      en: ["Choose the condition type", "Provide the comparison value when needed"],
    },
  },
  "logic/parallel": {
    category: { ru: "Логика", en: "Logic" },
    summary: {
      ru: "Параллель разветвляет выполнение, чтобы downstream-ветки шли одновременно.",
      en: "Parallel nodes fan the flow out so downstream branches can run at the same time.",
    },
    checklist: {
      ru: ["Подключите ветки, которые должны работать параллельно"],
      en: ["Connect the branches you want to run in parallel"],
    },
  },
  "logic/merge": {
    category: { ru: "Логика", en: "Logic" },
    summary: {
      ru: "Merge объединяет несколько активированных веток обратно в одну управляемую точку.",
      en: "Merge nodes join multiple activated branches back into one controlled continuation point.",
    },
    checklist: {
      ru: ["Выберите режим all или any", "Подведите одну или несколько входящих веток"],
      en: ["Choose the all or any mode", "Connect one or more incoming branches"],
    },
  },
  "logic/wait": {
    category: { ru: "Логика", en: "Logic" },
    summary: {
      ru: "Пауза останавливает выполнение на контролируемое время перед следующим шагом.",
      en: "Wait nodes pause execution for a controlled amount of time before continuing.",
    },
    checklist: {
      ru: ["Укажите длительность паузы в минутах"],
      en: ["Set the wait duration in minutes"],
    },
  },
  "logic/human_approval": {
    category: { ru: "Логика", en: "Logic" },
    summary: {
      ru: "Подтверждение оператора приостанавливает поток до approve или reject.",
      en: "Human approval nodes pause the flow until an operator approves or rejects the action.",
    },
    checklist: {
      ru: ["Настройте email/Telegram или явно включите ручную ссылку", "Задайте timeout", "Укажите base URL для approval-ссылок"],
      en: ["Set email/Telegram delivery or explicitly enable manual link mode", "Set the timeout window", "Provide a reachable base URL for approval links"],
    },
  },
  "logic/telegram_input": {
    category: { ru: "Логика", en: "Logic" },
    summary: {
      ru: "Этот узел отправляет сообщение в Telegram и ждёт обычный текстовый ответ оператора.",
      en: "This node sends a Telegram prompt and waits for a plain-text operator reply.",
    },
    checklist: {
      ru: ["Укажите bot token и chat id", "Опишите, какой ответ ждёте", "Используйте ветку timeout для эскалации"],
      en: ["Set the bot token and chat id", "Describe the reply you expect", "Use the timeout branch for escalation"],
    },
  },
  "output/report": {
    category: { ru: "Выход", en: "Output" },
    summary: {
      ru: "Отчёт собирает результаты предыдущих шагов в финальную markdown-сводку.",
      en: "Report nodes compile prior outputs into a final markdown summary for the run.",
    },
    checklist: {
      ru: ["При необходимости задайте свой шаблон отчёта"],
      en: ["Optionally provide a custom report template"],
    },
  },
  "output/webhook": {
    category: { ru: "Выход", en: "Output" },
    summary: {
      ru: "Исходящий webhook отправляет результат пайплайна во внешнюю систему.",
      en: "Webhook output nodes push the pipeline result to another system.",
    },
    checklist: {
      ru: ["Вставьте URL назначения", "Если нужно, подготовьте дополнительные поля upstream"],
      en: ["Paste the destination URL", "Optionally add extra payload fields upstream"],
    },
  },
  "output/email": {
    category: { ru: "Выход", en: "Output" },
    summary: {
      ru: "Email-выход отправляет результат через SMTP или через настройки платформы по умолчанию.",
      en: "Email output nodes send the pipeline result through SMTP or platform defaults.",
    },
    checklist: {
      ru: ["Укажите получателей или используйте платформенные значения", "При необходимости настройте тему и тело письма"],
      en: ["Set recipients or rely on platform defaults", "Optionally customize subject and body"],
    },
  },
  "output/telegram": {
    category: { ru: "Выход", en: "Output" },
    summary: {
      ru: "Telegram-выход отправляет результат оператору или в канал через Bot API.",
      en: "Telegram output nodes send the result to an operator or channel through Bot API.",
    },
    checklist: {
      ru: ["Укажите bot token и chat ID или используйте значения платформы", "При необходимости задайте шаблон сообщения"],
      en: ["Set bot token and chat ID or rely on platform defaults", "Optionally provide a message template"],
    },
  },
};
