import { User } from "lucide-react";

import type { LinuxUiSettingsSnapshot } from "@/lib/api";
import { localize } from "@/lib/i18n";

import { InfoCard, OutputBlock } from "./SettingsPrimitives";
import {
  extractDirective,
  firstMeaningfulLine,
  nonEmptyLines,
  parseCronEntries,
  parseEnvVariables,
} from "./settingsModel";

export function OverviewSection({
  settings,
  query,
  lang,
}: {
  settings: LinuxUiSettingsSnapshot;
  query: string;
  lang: string;
}) {
  const cronEntries = parseCronEntries(
    settings.crontab.user_crontab,
    settings.crontab.system_crontab,
    settings.crontab.cron_dirs,
  );
  const envVars = parseEnvVariables(settings.environment.variables);
  const permitRootLogin =
    extractDirective(settings.security.ssh_config, "PermitRootLogin") ||
    localize(lang, "не указано", "not specified");
  const passwordAuthentication =
    extractDirective(settings.security.ssh_config, "PasswordAuthentication") ||
    localize(lang, "не указано", "not specified");
  const firewallState = firstMeaningfulLine(
    settings.security.firewall,
    localize(lang, "Нет данных firewall", "No firewall data"),
  );

  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <InfoCard lang={lang} label={localize(lang, "Хост", "Host")} value={settings.general.hostname} mono hint={firstMeaningfulLine(settings.general.os_release, settings.general.kernel)} />
        <InfoCard lang={lang} label={localize(lang, "Текущий пользователь", "Current User")} value={settings.users.current_user} mono hint={settings.users.sudo_group} />
        <InfoCard lang={lang} label={localize(lang, "Аккаунты", "Accounts")} value={settings.users.accounts.length} hint={localize(lang, "Пользователи UID 1000+", "UID 1000+ users")} />
        <InfoCard lang={lang} label={localize(lang, "Активные сессии", "Active Sessions")} value={nonEmptyLines(settings.users.logged_in).length} hint={localize(lang, "Сейчас вошли в систему", "Users logged in now")} />
        <InfoCard lang={lang} label={localize(lang, "Записи cron", "Cron Entries")} value={cronEntries.length} hint={localize(lang, "Пользовательский и системный cron", "User and system cron")} />
        <InfoCard lang={lang} label={localize(lang, "Переменные окружения", "Env Vars")} value={envVars.length} hint={localize(lang, `${settings.environment.path_directories.length} записей PATH`, `${settings.environment.path_directories.length} PATH entries`)} />
        <InfoCard lang={lang} label={localize(lang, "Root-вход", "Root Login")} value={permitRootLogin} tone={/no|prohibit-password/i.test(permitRootLogin) ? "accent" : "alert"} />
        <InfoCard lang={lang} label={localize(lang, "Парольный вход", "Password Auth")} value={passwordAuthentication} tone={/no/i.test(passwordAuthentication) ? "accent" : "alert"} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-4">
          <OutputBlock lang={lang} label={localize(lang, "Версия ОС", "OS Release")} value={settings.general.os_release} query={query} emptyLabel={localize(lang, "Нет данных о версии ОС", "No OS release data")} />
          <OutputBlock lang={lang} label={localize(lang, "Снимок firewall", "Firewall Snapshot")} value={settings.security.firewall} query={query} emptyLabel={localize(lang, "Firewall-инструмент не найден", "No firewall tool detected")} />
        </div>
        <div className="space-y-4">
          <div className="rounded-[1.1rem] border border-border bg-background p-3 shadow-sm">
            <div className="text-xs uppercase tracking-[0.18em] text-muted-foreground">{localize(lang, "Снимок runtime", "Runtime Snapshot")}</div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <InfoCard lang={lang} label={localize(lang, "Shell", "Shell")} value={settings.environment.shell} mono />
              <InfoCard lang={lang} label={localize(lang, "Локаль", "Locale")} value={settings.environment.locale} mono />
              <InfoCard lang={lang} label={localize(lang, "Таймеры", "Timers")} value={nonEmptyLines(settings.crontab.timers).length} hint={localize(lang, "Видимые systemd timers", "Visible systemd timers")} />
              <InfoCard lang={lang} label="Firewall" value={firewallState} tone={/active|enabled|running/i.test(firewallState) ? "accent" : "default"} />
            </div>
          </div>
          <div className="rounded-[1.1rem] border border-border bg-background p-3 shadow-sm">
            <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">{localize(lang, "Каталоги PATH", "PATH Directories")}</div>
            <div className="space-y-2">
              {settings.environment.path_directories.slice(0, 8).map((entry) => (
                <div key={entry} className="rounded-xl border border-border/70 bg-card px-3 py-2 font-mono text-xs text-foreground">
                  {entry}
                </div>
              ))}
              {settings.environment.path_directories.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border/70 bg-card px-3 py-4 text-center text-xs text-muted-foreground">
                  {localize(lang, "PATH пуст", "PATH is empty")}
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

export function GeneralSection({ settings, query, lang }: { settings: LinuxUiSettingsSnapshot["general"]; query: string; lang: string }) {
  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">{localize(lang, "Информация о системе", "System Information")}</div>
      <div className="grid gap-2 sm:grid-cols-2">
        <InfoCard lang={lang} label={localize(lang, "Hostname", "Hostname")} value={settings.hostname} mono />
        <InfoCard lang={lang} label={localize(lang, "Часовой пояс", "Timezone")} value={settings.timezone} />
        <InfoCard lang={lang} label={localize(lang, "Ядро", "Kernel")} value={settings.kernel} mono />
        <InfoCard lang={lang} label={localize(lang, "Архитектура", "Architecture")} value={settings.architecture} />
        <InfoCard lang={lang} label={localize(lang, "Uptime", "Uptime")} value={settings.uptime} />
        <InfoCard lang={lang} label="CPU" value={settings.cpu} />
        <InfoCard lang={lang} label={localize(lang, "Всего памяти", "Total Memory")} value={settings.total_memory} />
      </div>
      {settings.os_release ? <OutputBlock lang={lang} label={localize(lang, "Версия ОС", "OS Release")} value={settings.os_release} query={query} emptyLabel={localize(lang, "Нет данных", "No data")} /> : null}
    </div>
  );
}

export function UsersSection({ settings, query, lang }: { settings: LinuxUiSettingsSnapshot["users"]; query: string; lang: string }) {
  const normalizedQuery = query.trim().toLowerCase();
  const visibleAccounts = normalizedQuery
    ? settings.accounts.filter((account) =>
        `${account.name} ${account.uid} ${account.home} ${account.shell}`.toLowerCase().includes(normalizedQuery),
      )
    : settings.accounts;

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">{localize(lang, "Управление пользователями", "User Management")}</div>
      <div className="grid gap-2 sm:grid-cols-2">
        <InfoCard lang={lang} label={localize(lang, "Текущий пользователь", "Current User")} value={settings.current_user} mono />
        <InfoCard lang={lang} label={localize(lang, "Группа sudo", "Sudo Group")} value={settings.sudo_group} mono />
      </div>

      <div className="mt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        {localize(lang, "Системные пользователи (UID ≥ 1000)", "System Users (UID ≥ 1000)")}
      </div>
      <div className="space-y-1.5">
        {visibleAccounts.length > 0 ? (
          visibleAccounts.map((account) => (
            <div
              key={`${account.name}-${account.uid}`}
              className="flex items-center justify-between rounded-xl border border-border/70 bg-background/90 px-3 py-2"
            >
              <div className="flex items-center gap-2">
                <User className="h-3.5 w-3.5 text-muted-foreground" />
                <span className="font-mono text-xs text-foreground">{account.name}</span>
                <span className="text-xs text-muted-foreground">uid:{account.uid}</span>
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span className="font-mono">{account.home}</span>
                <span className="font-mono">{account.shell}</span>
              </div>
            </div>
          ))
        ) : (
          <div className="rounded-xl border border-dashed border-border/70 bg-background/90 px-3 py-4 text-center text-xs text-muted-foreground">
            {localize(lang, "Обычные пользователи не найдены", "No regular users found")}
          </div>
        )}
      </div>

      <OutputBlock lang={lang} label={localize(lang, "Сейчас в системе", "Logged In Now")} value={settings.logged_in} query={query} emptyLabel={localize(lang, "Активных сессий нет", "No sessions")} />
      <OutputBlock lang={lang} label={localize(lang, "Последние входы", "Last Logins")} value={settings.last_logins} query={query} emptyLabel={localize(lang, "Нет данных", "No data")} />
    </div>
  );
}

export function CrontabSection({ settings, query, lang }: { settings: LinuxUiSettingsSnapshot["crontab"]; query: string; lang: string }) {
  const cronEntries = parseCronEntries(settings.user_crontab, settings.system_crontab, settings.cron_dirs);
  const normalizedQuery = query.trim().toLowerCase();
  const visibleEntries = normalizedQuery
    ? cronEntries.filter((line) => line.toLowerCase().includes(normalizedQuery))
    : cronEntries;

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">{localize(lang, "Запланированные задачи", "Scheduled Tasks")}</div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <InfoCard lang={lang} label={localize(lang, "Записи пользователя", "User Entries")} value={parseCronEntries(settings.user_crontab).length} />
        <InfoCard lang={lang} label={localize(lang, "Системные записи", "System Entries")} value={parseCronEntries(settings.system_crontab).length} />
        <InfoCard lang={lang} label="Cron.d" value={parseCronEntries(settings.cron_dirs).length} />
        <InfoCard lang={lang} label={localize(lang, "Таймеры", "Timers")} value={nonEmptyLines(settings.timers).length} />
      </div>
      <div className="rounded-[1.1rem] border border-border bg-background p-3 shadow-sm">
        <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">{localize(lang, "Видимые записи", "Visible Entries")}</div>
        <div className="space-y-2">
          {visibleEntries.slice(0, 24).map((line) => (
            <div key={line} className="rounded-xl border border-border/70 bg-card px-3 py-2 font-mono text-xs text-foreground">
              {line}
            </div>
          ))}
          {cronEntries.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border/70 bg-card px-3 py-4 text-center text-xs text-muted-foreground">
              {localize(lang, "Записи cron не найдены", "No cron entries found")}
            </div>
          ) : null}
        </div>
      </div>
      <OutputBlock lang={lang} label={localize(lang, "Crontab пользователя", "User Crontab")} value={settings.user_crontab} query={query} emptyLabel={localize(lang, "Для текущего пользователя crontab нет", "No crontab for current user")} />
      <OutputBlock lang={lang} label={localize(lang, "Системный crontab (/etc/crontab)", "System Crontab (/etc/crontab)")} value={settings.system_crontab} query={query} emptyLabel={localize(lang, "Нет /etc/crontab", "No /etc/crontab")} />
      <OutputBlock lang={lang} label="/etc/cron.d/" value={settings.cron_dirs} query={query} emptyLabel={localize(lang, "Нет /etc/cron.d/", "No /etc/cron.d/")} />
      <OutputBlock lang={lang} label="Systemd timers" value={settings.timers} query={query} emptyLabel={localize(lang, "systemctl недоступен", "systemctl unavailable")} />
    </div>
  );
}

export function EnvironmentSection({ settings, query, lang }: { settings: LinuxUiSettingsSnapshot["environment"]; query: string; lang: string }) {
  const envVars = parseEnvVariables(settings.variables);
  const normalizedQuery = query.trim().toLowerCase();
  const visibleEnvVars = normalizedQuery
    ? envVars.filter((item) => `${item.key}=${item.value}`.toLowerCase().includes(normalizedQuery))
    : envVars;

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">{localize(lang, "Окружение", "Environment")}</div>
      <div className="grid gap-2 sm:grid-cols-2">
        <InfoCard lang={lang} label="Shell" value={settings.shell} mono />
        <InfoCard lang={lang} label={localize(lang, "Локаль", "Locale")} value={settings.locale} mono />
        <InfoCard lang={lang} label={localize(lang, "Записи PATH", "PATH Entries")} value={settings.path_directories.length} />
        <InfoCard lang={lang} label={localize(lang, "Переменные", "Env Vars")} value={envVars.length} />
      </div>

      <OutputBlock lang={lang} label={localize(lang, "Каталоги PATH", "PATH Directories")} value={settings.path_directories.join("\n")} query={query} emptyLabel={localize(lang, "PATH пуст", "PATH is empty")} />
      <div className="rounded-[1.1rem] border border-border bg-background p-3 shadow-sm">
        <div className="mb-2 text-xs uppercase tracking-[0.18em] text-muted-foreground">{localize(lang, "Переменные окружения", "Environment Variables")}</div>
        <div className="space-y-2">
          {visibleEnvVars.slice(0, 40).map((item) => (
            <div key={item.key} className="rounded-xl border border-border/70 bg-card px-3 py-2">
              <div className="font-mono text-xs text-foreground">{item.key}</div>
              <div className="mt-1 break-all font-mono text-xs text-muted-foreground">{item.value || localize(lang, "(пусто)", "(empty)")}</div>
            </div>
          ))}
          {visibleEnvVars.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border/70 bg-card px-3 py-4 text-center text-xs text-muted-foreground">
              {localize(lang, "Переменные окружения не совпали с фильтром", "No environment variables match the current filter")}
            </div>
          ) : null}
        </div>
      </div>
      <OutputBlock lang={lang} label={localize(lang, "Сырой вывод окружения", "Raw Environment Dump")} value={settings.variables} query={query} emptyLabel={localize(lang, "Переменные окружения не найдены", "No environment variables")} />
    </div>
  );
}

export function SecuritySection({ settings, query, lang }: { settings: LinuxUiSettingsSnapshot["security"]; query: string; lang: string }) {
  const permitRootLogin =
    extractDirective(settings.ssh_config, "PermitRootLogin") ||
    localize(lang, "не указано", "not specified");
  const passwordAuthentication =
    extractDirective(settings.ssh_config, "PasswordAuthentication") ||
    localize(lang, "не указано", "not specified");

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">{localize(lang, "Обзор безопасности", "Security Overview")}</div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <InfoCard lang={lang} label={localize(lang, "Root-вход", "Root Login")} value={permitRootLogin} tone={/no|prohibit-password/i.test(permitRootLogin) ? "accent" : "alert"} />
        <InfoCard lang={lang} label={localize(lang, "Парольный вход", "Password Auth")} value={passwordAuthentication} tone={/no/i.test(passwordAuthentication) ? "accent" : "alert"} />
        <InfoCard lang={lang} label="Firewall" value={firstMeaningfulLine(settings.firewall, localize(lang, "Нет данных firewall", "No firewall data"))} hint={localize(lang, "Первая строка отчета", "First reported line")} />
        <InfoCard lang={lang} label={localize(lang, "Открытые порты", "Listening Ports")} value={nonEmptyLines(settings.listening_ports).length} tone={nonEmptyLines(settings.listening_ports).length > 0 ? "accent" : "default"} />
      </div>
      <OutputBlock lang={lang} label={localize(lang, "Конфигурация SSH", "SSH Configuration")} value={settings.ssh_config} query={query} emptyLabel={localize(lang, "Не удалось прочитать sshd_config", "Cannot read sshd_config")} />
      <OutputBlock lang={lang} label={localize(lang, "Статус firewall", "Firewall Status")} value={settings.firewall} query={query} emptyLabel={localize(lang, "Firewall-инструмент не найден", "No firewall tool detected")} />
      <OutputBlock lang={lang} label={localize(lang, "Открытые порты", "Listening Ports")} value={settings.listening_ports} query={query} emptyLabel={localize(lang, "Не удалось получить список портов", "Cannot list ports")} />
      <OutputBlock lang={lang} label={localize(lang, "Недавние неудачные входы", "Recent Failed Logins")} value={settings.failed_logins} query={query} emptyLabel={localize(lang, "Неудачных входов нет", "No failed login data")} />
    </div>
  );
}
