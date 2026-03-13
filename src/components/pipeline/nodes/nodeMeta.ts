export type PipelineEditorLang = "en" | "ru";

type LocalizedText = Record<PipelineEditorLang, string>;
type LocalizedList = Record<PipelineEditorLang, string[]>;

type NodeTypeMeta = {
  icon: string;
  label: LocalizedText;
  paletteDescription: LocalizedText;
};

type NodeGuidanceMeta = {
  category: LocalizedText;
  summary: LocalizedText;
  checklist: LocalizedList;
};

export function localize(lang: PipelineEditorLang, ru: string, en: string) {
  return lang === "ru" ? ru : en;
}

export const NODE_TYPE_META: Record<string, NodeTypeMeta> = {
  "trigger/manual": {
    icon: "▶️",
    label: { ru: "Ручной запуск", en: "Manual Trigger" },
    paletteDescription: { ru: "Запуск вручную из Studio", en: "Start the pipeline manually from Studio" },
  },
  "trigger/webhook": {
    icon: "🔗",
    label: { ru: "Webhook", en: "Webhook Trigger" },
    paletteDescription: { ru: "Запуск по HTTP POST", en: "Start the pipeline via HTTP POST" },
  },
  "trigger/schedule": {
    icon: "⏰",
    label: { ru: "Расписание", en: "Schedule Trigger" },
    paletteDescription: { ru: "Автозапуск по cron", en: "Run the pipeline on a cron schedule" },
  },
  "agent/react": {
    icon: "🤖",
    label: { ru: "ReAct-агент", en: "ReAct Agent" },
    paletteDescription: { ru: "Агент сам выбирает инструменты и шаги", en: "Agent reasons and chooses tools during execution" },
  },
  "agent/multi": {
    icon: "🦾",
    label: { ru: "Мультиагент", en: "Multi-Agent" },
    paletteDescription: { ru: "Координация нескольких агентов или целей", en: "Coordinate multiple agents or execution targets" },
  },
  "agent/ssh_cmd": {
    icon: "💻",
    label: { ru: "SSH-команда", en: "SSH Command" },
    paletteDescription: { ru: "Точная команда по SSH без LLM-планирования", en: "Run one explicit SSH command without LLM planning" },
  },
  "agent/llm_query": {
    icon: "🧠",
    label: { ru: "LLM-запрос", en: "LLM Query" },
    paletteDescription: { ru: "Аналитический шаг без серверных действий", en: "Pure reasoning or analysis step" },
  },
  "agent/mcp_call": {
    icon: "🧩",
    label: { ru: "MCP-вызов", en: "MCP Call" },
    paletteDescription: { ru: "Прямой вызов конкретного MCP-инструмента", en: "Force one exact MCP tool call" },
  },
  "logic/condition": {
    icon: "🔀",
    label: { ru: "Условие", en: "Condition" },
    paletteDescription: { ru: "Разветвление if / else", en: "Branch execution with if / else logic" },
  },
  "logic/parallel": {
    icon: "⚡",
    label: { ru: "Параллель", en: "Parallel" },
    paletteDescription: { ru: "Запуск нескольких веток параллельно", en: "Fan out into parallel branches" },
  },
  "logic/wait": {
    icon: "⏱️",
    label: { ru: "Пауза", en: "Wait" },
    paletteDescription: { ru: "Пауза на заданное время", en: "Pause the pipeline for a fixed duration" },
  },
  "logic/human_approval": {
    icon: "👤",
    label: { ru: "Подтверждение", en: "Human Approval" },
    paletteDescription: { ru: "Ожидание решения оператора", en: "Pause and wait for operator approval" },
  },
  "output/report": {
    icon: "📋",
    label: { ru: "Отчёт", en: "Report" },
    paletteDescription: { ru: "Финальный markdown-отчёт", en: "Generate a final markdown report" },
  },
  "output/webhook": {
    icon: "📤",
    label: { ru: "Исходящий webhook", en: "Send Webhook" },
    paletteDescription: { ru: "Отправка результата во внешний HTTP endpoint", en: "POST the result to an external endpoint" },
  },
  "output/email": {
    icon: "✉️",
    label: { ru: "Письмо", en: "Send Email" },
    paletteDescription: { ru: "Отправка результата по email", en: "Email the pipeline result" },
  },
  "output/telegram": {
    icon: "📱",
    label: { ru: "Telegram", en: "Telegram" },
    paletteDescription: { ru: "Отправка результата в Telegram", en: "Send the result to Telegram" },
  },
};

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
      ru: ["Напишите prompt", "Выберите provider и model", "Подставьте переменные пайплайна при необходимости"],
      en: ["Write the prompt", "Choose provider and model", "Use pipeline variables where needed"],
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
      ru: ["Настройте доставку через email или Telegram", "Задайте timeout", "Укажите base URL для approval-ссылок"],
      en: ["Set email or Telegram delivery", "Set the timeout window", "Provide a reachable base URL for approval links"],
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

export const NODE_CATEGORY_LABELS: Record<string, LocalizedText> = {
  Triggers: { ru: "Триггеры", en: "Triggers" },
  Agents: { ru: "Агенты", en: "Agents" },
  Logic: { ru: "Логика", en: "Logic" },
  Output: { ru: "Выходы", en: "Output" },
  All: { ru: "Все", en: "All" },
};

export function getNodeTypeInfo(type: string, lang: PipelineEditorLang) {
  const meta = NODE_TYPE_META[type];
  if (!meta) return { label: type, icon: "🔧" };
  return { label: meta.label[lang], icon: meta.icon };
}

export function getNodeTypeGuidance(type: string, lang: PipelineEditorLang) {
  const meta = NODE_TYPE_GUIDANCE_META[type];
  if (!meta) {
    return {
      category: localize(lang, "Нода", "Node"),
      summary: localize(lang, "Настройте шаг так, чтобы пайплайн мог выполнить его без двусмысленностей.", "Configure this step so the pipeline can execute it deterministically."),
      checklist: [localize(lang, "Проверьте обязательные поля для этого типа ноды.", "Review the required fields for this node type.")],
    };
  }
  return {
    category: meta.category[lang],
    summary: meta.summary[lang],
    checklist: meta.checklist[lang],
  };
}

export function getNodePaletteText(type: string, lang: PipelineEditorLang) {
  const meta = NODE_TYPE_META[type];
  if (!meta) return { label: type, description: type };
  return {
    label: meta.label[lang],
    description: meta.paletteDescription[lang],
  };
}

export function getNodeCategoryLabel(category: string, lang: PipelineEditorLang) {
  return NODE_CATEGORY_LABELS[category]?.[lang] || category;
}
