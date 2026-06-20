import { NODE_TYPE_GUIDANCE_META } from "./nodeGuidanceMeta";
import type { LocalizedText, NodeTypeMeta, PipelineEditorLang } from "./nodeMetaTypes";

export type { PipelineEditorLang } from "./nodeMetaTypes";

export function localize(lang: PipelineEditorLang, ru: string, en: string) {
  return lang === "ru" ? ru : en;
}

export const NODE_TYPE_META: Record<string, NodeTypeMeta> = {
  "trigger/manual": {
    label: { ru: "Ручной запуск", en: "Manual Trigger" },
    paletteDescription: { ru: "Запуск вручную из Studio", en: "Start the pipeline manually from Studio" },
  },
  "trigger/webhook": {
    label: { ru: "Webhook", en: "Webhook Trigger" },
    paletteDescription: { ru: "Запуск по HTTP POST", en: "Start the pipeline via HTTP POST" },
  },
  "trigger/schedule": {
    label: { ru: "Расписание", en: "Schedule Trigger" },
    paletteDescription: { ru: "Автозапуск по cron", en: "Run the pipeline on a cron schedule" },
  },
  "trigger/monitoring": {
    label: { ru: "Мониторинг", en: "Monitoring Trigger" },
    paletteDescription: { ru: "Запуск по алерту мониторинга сервера", en: "Start from a server monitoring alert" },
  },
  "agent/react": {
    label: { ru: "ReAct-агент", en: "ReAct Agent" },
    paletteDescription: { ru: "Агент сам выбирает инструменты и шаги", en: "Agent reasons and chooses tools during execution" },
  },
  "agent/multi": {
    label: { ru: "Мультиагент", en: "Multi-Agent" },
    paletteDescription: { ru: "Координация нескольких агентов или целей", en: "Coordinate multiple agents or execution targets" },
  },
  "agent/ssh_cmd": {
    label: { ru: "SSH-команда", en: "SSH Command" },
    paletteDescription: { ru: "Точная команда по SSH без LLM-планирования", en: "Run one explicit SSH command without LLM planning" },
  },
  "agent/llm_query": {
    label: { ru: "LLM-запрос", en: "LLM Query" },
    paletteDescription: { ru: "Аналитический шаг без серверных действий", en: "Pure reasoning or analysis step" },
  },
  "agent/mcp_call": {
    label: { ru: "MCP-вызов", en: "MCP Call" },
    paletteDescription: { ru: "Прямой вызов конкретного MCP-инструмента", en: "Force one exact MCP tool call" },
  },
  "ops/server_snapshot": {
    label: { ru: "Снимок сервера", en: "Server Snapshot" },
    paletteDescription: { ru: "Безопасный снимок Linux, Docker, дисков и логов", en: "Read-only Linux/Docker/disk/log snapshot" },
  },
  "ops/log_query": {
    label: { ru: "Запрос логов", en: "Log Query" },
    paletteDescription: { ru: "Чтение логов Linux, сервисов и Docker", en: "Read-only Linux/service/Docker logs" },
  },
  "ops/file_action": {
    label: { ru: "Файл", en: "File Action" },
    paletteDescription: { ru: "Чтение или запись текстового файла через SFTP", en: "Read/write a text file through SFTP" },
  },
  "ops/package_action": {
    label: { ru: "Пакеты", en: "Package Action" },
    paletteDescription: { ru: "Просмотр, установка, обновление или удаление пакетов ОС", en: "List/install/update/remove OS packages" },
  },
  "ops/disk_cleanup": {
    label: { ru: "Очистка диска", en: "Disk Cleanup" },
    paletteDescription: { ru: "Проверка места, очистка journal или старых tmp-файлов", en: "Inspect, journal vacuum, or clean old tmp files" },
  },
  "ops/backup_restore_check": {
    label: { ru: "Проверка backup", en: "Backup Check" },
    paletteDescription: { ru: "Проверка свежести backup и целостности последнего архива", en: "Read-only backup freshness and latest archive integrity" },
  },
  "ops/service_action": {
    label: { ru: "Действие сервиса", en: "Service Action" },
    paletteDescription: { ru: "Структурированный systemctl с проверкой", en: "Structured systemctl with verification" },
  },
  "ops/docker_action": {
    label: { ru: "Действие Docker", en: "Docker Action" },
    paletteDescription: { ru: "Start, stop или restart контейнера с проверкой", en: "Start/stop/restart a container with verification" },
  },
  "ops/process_action": {
    label: { ru: "Действие процесса", en: "Process Action" },
    paletteDescription: { ru: "Остановить процесс мягко или принудительно", en: "Terminate or force kill a process" },
  },
  "ops/http_check": {
    label: { ru: "HTTP-проверка", en: "HTTP Check" },
    paletteDescription: { ru: "Проверка URL, статуса и текста ответа", en: "Verify URL status and response text" },
  },
  "ops/alert_update": {
    label: { ru: "Обновить alert", en: "Alert Update" },
    paletteDescription: { ru: "Закрыть алерт мониторинга после проверки", en: "Resolve a monitoring alert after verification" },
  },
  "logic/condition": {
    label: { ru: "Условие", en: "Condition" },
    paletteDescription: { ru: "Разветвление if / else", en: "Branch execution with if / else logic" },
  },
  "logic/parallel": {
    label: { ru: "Параллель", en: "Parallel" },
    paletteDescription: { ru: "Запуск нескольких веток параллельно", en: "Fan out into parallel branches" },
  },
  "logic/merge": {
    label: { ru: "Слияние", en: "Merge" },
    paletteDescription: { ru: "Явное объединение веток all / any", en: "Explicitly join branches with all / any semantics" },
  },
  "logic/wait": {
    label: { ru: "Пауза", en: "Wait" },
    paletteDescription: { ru: "Пауза на заданное время", en: "Pause the pipeline for a fixed duration" },
  },
  "logic/human_approval": {
    label: { ru: "Подтверждение", en: "Human Approval" },
    paletteDescription: { ru: "Ожидание решения оператора", en: "Pause and wait for operator approval" },
  },
  "logic/telegram_input": {
    label: { ru: "Ответ в Telegram", en: "Telegram Input" },
    paletteDescription: { ru: "Ожидание обычного текстового ответа оператора", en: "Wait for a plain-text operator reply in Telegram" },
  },
  "output/report": {
    label: { ru: "Отчёт", en: "Report" },
    paletteDescription: { ru: "Финальный markdown-отчёт", en: "Generate a final markdown report" },
  },
  "output/webhook": {
    label: { ru: "Исходящий webhook", en: "Send Webhook" },
    paletteDescription: { ru: "Отправка результата во внешний HTTP endpoint", en: "POST the result to an external endpoint" },
  },
  "output/email": {
    label: { ru: "Письмо", en: "Send Email" },
    paletteDescription: { ru: "Отправка результата по email", en: "Email the pipeline result" },
  },
  "output/telegram": {
    label: { ru: "Telegram", en: "Telegram" },
    paletteDescription: { ru: "Отправка результата в Telegram", en: "Send the result to Telegram" },
  },
};

export const NODE_CATEGORY_LABELS: Record<string, LocalizedText> = {
  Triggers: { ru: "Триггеры", en: "Triggers" },
  Agents: { ru: "Агенты", en: "Agents" },
  Ops: { ru: "OPS", en: "Ops" },
  Logic: { ru: "Логика", en: "Logic" },
  Output: { ru: "Выходы", en: "Output" },
  All: { ru: "Все", en: "All" },
};

export function getNodeTypeInfo(type: string, lang: PipelineEditorLang) {
  const meta = NODE_TYPE_META[type];
  if (!meta) return { label: type };
  return { label: meta.label[lang] };
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

export function getNodeBranchLabel(branchId: string, lang: PipelineEditorLang) {
  const labels: Record<string, LocalizedText> = {
    out: { ru: "Далее", en: "Next" },
    success: { ru: "Готово", en: "Success" },
    error: { ru: "Ошибка", en: "Error" },
    true: { ru: "Да", en: "True" },
    false: { ru: "Нет", en: "False" },
    approved: { ru: "Да", en: "Approved" },
    rejected: { ru: "Нет", en: "Rejected" },
    timeout: { ru: "Timeout", en: "Timeout" },
    received: { ru: "Ответ", en: "Reply" },
    done: { ru: "Готово", en: "Done" },
  };
  return labels[branchId]?.[lang] || branchId;
}
