import type { LinuxUiSettingsSnapshot } from "@/lib/api";
import { localize } from "@/lib/i18n";

export type SettingsSection =
  | "overview"
  | "general"
  | "users"
  | "crontab"
  | "environment"
  | "security";

export interface SearchResult {
  section: SettingsSection;
  label: string;
  snippet: string;
}

export function emptyValue(lang: string) {
  return localize(lang, "Нет данных", "N/A");
}

export function lineCountLabel(lang: string, count: number) {
  return localize(lang, `${count} строк`, `${count} lines`);
}

export function nonEmptyLines(value: string) {
  return String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

export function filterBlock(value: string, query: string) {
  const lines = nonEmptyLines(value);
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return lines.join("\n");
  return lines.filter((line) => line.toLowerCase().includes(normalizedQuery)).join("\n");
}

export function extractDirective(raw: string, key: string) {
  const normalizedKey = key.toLowerCase();
  for (const line of String(raw || "").split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) continue;
    const [directive, ...rest] = trimmed.split(/\s+/);
    if (directive.toLowerCase() === normalizedKey) {
      return rest.join(" ").trim();
    }
  }
  return "";
}

export function parseEnvVariables(raw: string) {
  return nonEmptyLines(raw)
    .map((line) => {
      const index = line.indexOf("=");
      if (index <= 0) return null;
      return { key: line.slice(0, index), value: line.slice(index + 1) };
    })
    .filter(Boolean) as Array<{ key: string; value: string }>;
}

export function parseCronEntries(...sources: string[]) {
  return sources.flatMap((source) =>
    nonEmptyLines(source).filter((line) => !line.startsWith("#")),
  );
}

export function firstMeaningfulLine(value: string, fallback = "N/A") {
  return nonEmptyLines(value)[0] || fallback;
}

export function buildSettingsSearchResults(
  settings: LinuxUiSettingsSnapshot | undefined,
  query: string,
  lang: string,
): SearchResult[] {
  const normalizedQuery = query.trim().toLowerCase();
  if (!settings || !normalizedQuery) return [];

  const sections = [
    {
      section: "general" as const,
      label: localize(lang, "Сводка хоста", "Host Summary"),
      value: [
        settings.general.hostname,
        settings.general.timezone,
        settings.general.kernel,
        settings.general.os_release,
        settings.general.cpu,
        settings.general.total_memory,
      ].join("\n"),
    },
    {
      section: "users" as const,
      label: localize(lang, "Пользователи и сессии", "Users and Sessions"),
      value: [
        settings.users.current_user,
        settings.users.sudo_group,
        ...settings.users.accounts.map(
          (account) => `${account.name} ${account.uid} ${account.home} ${account.shell}`,
        ),
        settings.users.logged_in,
        settings.users.last_logins,
      ].join("\n"),
    },
    {
      section: "crontab" as const,
      label: localize(lang, "Запланированные задачи", "Scheduled Tasks"),
      value: [
        settings.crontab.user_crontab,
        settings.crontab.system_crontab,
        settings.crontab.cron_dirs,
        settings.crontab.timers,
      ].join("\n"),
    },
    {
      section: "environment" as const,
      label: localize(lang, "Окружение", "Environment"),
      value: [
        settings.environment.shell,
        settings.environment.locale,
        settings.environment.path_directories.join("\n"),
        settings.environment.variables,
      ].join("\n"),
    },
    {
      section: "security" as const,
      label: localize(lang, "Безопасность", "Security"),
      value: [
        settings.security.ssh_config,
        settings.security.firewall,
        settings.security.listening_ports,
        settings.security.failed_logins,
      ].join("\n"),
    },
  ];

  return sections
    .map((item) => {
      const matches = filterBlock(item.value, query);
      if (!matches && !item.label.toLowerCase().includes(normalizedQuery)) return null;
      return {
        section: item.section,
        label: item.label,
        snippet: (matches || item.label).split("\n").slice(0, 3).join("\n"),
      };
    })
    .filter(Boolean) as SearchResult[];
}

export function buildSectionCopyContent(
  settings: LinuxUiSettingsSnapshot | undefined,
  section: SettingsSection,
  lang: string,
) {
  if (!settings) return "";
  if (section === "overview") {
    return [
      `${localize(lang, "Хост", "Host")}: ${settings.general.hostname}`,
      `${localize(lang, "Часовой пояс", "Timezone")}: ${settings.general.timezone}`,
      `${localize(lang, "Текущий пользователь", "Current User")}: ${settings.users.current_user}`,
      `${localize(lang, "Аккаунты", "Accounts")}: ${settings.users.accounts.length}`,
      `${localize(lang, "Записи cron", "Cron Entries")}: ${parseCronEntries(settings.crontab.user_crontab, settings.crontab.system_crontab, settings.crontab.cron_dirs).length}`,
      `${localize(lang, "Переменные окружения", "Environment Vars")}: ${parseEnvVariables(settings.environment.variables).length}`,
      `${localize(lang, "Открытые порты", "Listening Ports")}: ${nonEmptyLines(settings.security.listening_ports).length}`,
      "",
      settings.general.os_release,
      "",
      settings.security.firewall,
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (section === "general") {
    return [
      `Hostname: ${settings.general.hostname}`,
      `${localize(lang, "Часовой пояс", "Timezone")}: ${settings.general.timezone}`,
      `${localize(lang, "Ядро", "Kernel")}: ${settings.general.kernel}`,
      `${localize(lang, "Архитектура", "Architecture")}: ${settings.general.architecture}`,
      `Uptime: ${settings.general.uptime}`,
      `CPU: ${settings.general.cpu}`,
      `${localize(lang, "Всего памяти", "Total Memory")}: ${settings.general.total_memory}`,
      settings.general.os_release,
    ]
      .filter(Boolean)
      .join("\n");
  }
  if (section === "users") {
    return [
      `${localize(lang, "Текущий пользователь", "Current User")}: ${settings.users.current_user}`,
      `${localize(lang, "Группа sudo", "Sudo Group")}: ${settings.users.sudo_group}`,
      "",
      `${localize(lang, "Аккаунты", "Accounts")}:`,
      ...settings.users.accounts.map(
        (account) => `${account.name} uid:${account.uid} ${account.home} ${account.shell}`,
      ),
      "",
      `${localize(lang, "Сейчас в системе", "Logged In Now")}:`,
      settings.users.logged_in,
      "",
      `${localize(lang, "Последние входы", "Last Logins")}:`,
      settings.users.last_logins,
    ]
      .filter((item) => item != null)
      .join("\n");
  }
  if (section === "crontab") {
    return [
      `${localize(lang, "Crontab пользователя", "User Crontab")}:`,
      settings.crontab.user_crontab,
      "",
      `${localize(lang, "Системный crontab", "System Crontab")}:`,
      settings.crontab.system_crontab,
      "",
      "/etc/cron.d/:",
      settings.crontab.cron_dirs,
      "",
      "Systemd timers:",
      settings.crontab.timers,
    ].join("\n");
  }
  if (section === "environment") {
    return [
      `Shell: ${settings.environment.shell}`,
      `Locale: ${settings.environment.locale}`,
      "",
      "PATH:",
      settings.environment.path_directories.join("\n"),
      "",
      `${localize(lang, "Переменные окружения", "Environment Variables")}:`,
      settings.environment.variables,
    ].join("\n");
  }
  return [
    `${localize(lang, "Конфигурация SSH", "SSH Configuration")}:`,
    settings.security.ssh_config,
    "",
    `${localize(lang, "Статус firewall", "Firewall Status")}:`,
    settings.security.firewall,
    "",
    `${localize(lang, "Открытые порты", "Listening Ports")}:`,
    settings.security.listening_ports,
    "",
    `${localize(lang, "Недавние неудачные входы", "Recent Failed Logins")}:`,
    settings.security.failed_logins,
  ].join("\n");
}
