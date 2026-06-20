import { localize } from "@/lib/i18n";

export const ALL_TOOLS = [
  {
    id: "ssh_execute",
    labelRu: "SSH-команды",
    labelEn: "SSH Execute",
    descriptionRu: "Запуск команд на серверах",
    descriptionEn: "Run commands on servers",
  },
  {
    id: "read_console",
    labelRu: "Чтение консоли",
    labelEn: "Read Console",
    descriptionRu: "Чтение вывода терминала",
    descriptionEn: "Read terminal output",
  },
  {
    id: "open_connection",
    labelRu: "Открыть SSH",
    labelEn: "Open Connection",
    descriptionRu: "Открытие SSH-подключений",
    descriptionEn: "Open SSH connections",
  },
  {
    id: "close_connection",
    labelRu: "Закрыть SSH",
    labelEn: "Close Connection",
    descriptionRu: "Закрытие SSH-подключений",
    descriptionEn: "Close SSH connections",
  },
  {
    id: "wait_for_output",
    labelRu: "Ожидать вывод",
    labelEn: "Wait for Output",
    descriptionRu: "Ожидание нужного текста в терминале",
    descriptionEn: "Wait for terminal patterns",
  },
  {
    id: "report",
    labelRu: "Отчёт",
    labelEn: "Report",
    descriptionRu: "Промежуточные статусы выполнения",
    descriptionEn: "Send intermediate status updates",
  },
  {
    id: "ask_user",
    labelRu: "Спросить пользователя",
    labelEn: "Ask User",
    descriptionRu: "Пауза до ответа пользователя",
    descriptionEn: "Pause for user input",
  },
  {
    id: "analyze_output",
    labelRu: "Анализ вывода",
    labelEn: "Analyze Output",
    descriptionRu: "LLM-анализ полученного вывода",
    descriptionEn: "Run LLM analysis over output",
  },
];

export const MODEL_OPTIONS = [
  "gemini-2.0-flash-exp",
  "gemini-2.5-pro",
  "claude-4.5-sonnet",
  "claude-4.5-opus",
  "gpt-5.2",
];

export const SUDO_AGENT_OPTIONS = [
  {
    value: "disabled",
    labelRu: "Без sudo",
    labelEn: "No sudo",
    hintRu: "Команды с sudo будут заблокированы для этого профиля.",
    hintEn: "Commands with sudo are blocked for this profile.",
  },
  {
    value: "ask",
    labelRu: "Спросить при необходимости",
    labelEn: "Ask when needed",
    hintRu: "Агент остановится и попросит разрешение, если ему понадобится sudo.",
    hintEn: "The agent stops and asks when sudo is needed.",
  },
  {
    value: "approved",
    labelRu: "Разрешить на запуск",
    labelEn: "Approve for run",
    hintRu: "Sudo разрешён для запусков этого профиля; backend выполняет его как sudo -n.",
    hintEn: "Sudo is approved for this profile's runs; backend enforces sudo -n.",
  },
] as const;

export function visibleAllowedTools(tools?: string[]) {
  return Array.isArray(tools) ? tools.filter((tool) => tool !== "send_ctrl_c") : undefined;
}

export function toolLabel(toolId: string, lang: "ru" | "en") {
  const tool = ALL_TOOLS.find((item) => item.id === toolId);
  return tool ? localize(lang, tool.labelRu, tool.labelEn) : toolId;
}

export function sudoOption(value: string | undefined) {
  return SUDO_AGENT_OPTIONS.find((item) => item.value === value) || SUDO_AGENT_OPTIONS[0];
}
