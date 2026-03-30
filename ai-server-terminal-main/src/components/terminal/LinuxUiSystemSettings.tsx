import { useMemo, useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Clock,
  Copy,
  Globe,
  Loader2,
  RefreshCw,
  Search,
  Server,
  Shield,
  User,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  fetchLinuxUiSettings,
  type FrontendServer,
  type LinuxUiSettingsSnapshot,
} from "@/lib/api";
import { cn } from "@/lib/utils";
import { useToast } from "@/hooks/use-toast";

type SettingsSection = "overview" | "general" | "users" | "crontab" | "environment" | "security";

interface SectionDef {
  id: SettingsSection;
  label: string;
  icon: ReactNode;
}

const SECTIONS: SectionDef[] = [
  { id: "overview", label: "Overview", icon: <Server className="h-4 w-4" /> },
  { id: "general", label: "General", icon: <Server className="h-4 w-4" /> },
  { id: "users", label: "Users", icon: <Users className="h-4 w-4" /> },
  { id: "crontab", label: "Cron Jobs", icon: <Clock className="h-4 w-4" /> },
  { id: "environment", label: "Environment", icon: <Globe className="h-4 w-4" /> },
  { id: "security", label: "Security", icon: <Shield className="h-4 w-4" /> },
];

function nonEmptyLines(value: string) {
  return String(value || "")
    .split(/\r?\n/)
    .map((line) => line.trim())
    .filter(Boolean);
}

function filterBlock(value: string, query: string) {
  const lines = nonEmptyLines(value);
  const normalizedQuery = query.trim().toLowerCase();
  if (!normalizedQuery) return lines.join("\n");
  return lines.filter((line) => line.toLowerCase().includes(normalizedQuery)).join("\n");
}

function extractDirective(raw: string, key: string) {
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

function parseEnvVariables(raw: string) {
  return nonEmptyLines(raw)
    .map((line) => {
      const index = line.indexOf("=");
      if (index <= 0) return null;
      return { key: line.slice(0, index), value: line.slice(index + 1) };
    })
    .filter(Boolean) as Array<{ key: string; value: string }>;
}

function parseCronEntries(...sources: string[]) {
  return sources.flatMap((source) =>
    nonEmptyLines(source).filter((line) => !line.startsWith("#")),
  );
}

function firstMeaningfulLine(value: string, fallback = "N/A") {
  return nonEmptyLines(value)[0] || fallback;
}

function InfoCard({
  label,
  value,
  mono,
  hint,
  tone = "default",
}: {
  label: string;
  value: string | number;
  mono?: boolean;
  hint?: string;
  tone?: "default" | "accent" | "alert";
}) {
  return (
    <div
      className={cn(
        "rounded-[1.1rem] border p-3 shadow-sm",
        tone === "alert"
          ? "border-destructive/25 bg-destructive/10"
          : tone === "accent"
            ? "border-primary/20 bg-primary/10"
            : "border-border bg-background",
      )}
    >
      <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
      <div className={cn("mt-1.5 break-words text-sm", mono && "font-mono text-xs", tone === "alert" ? "text-destructive" : "text-foreground")}>
        {value || "N/A"}
      </div>
      {hint ? <div className="mt-1.5 text-[11px] text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

function OutputBlock({
  label,
  value,
  query,
  emptyLabel = "No data",
  onCopy,
}: {
  label: string;
  value: string;
  query: string;
  emptyLabel?: string;
  onCopy?: () => void;
}) {
  const filteredValue = filterBlock(value, query);
  const visibleValue = filteredValue || "";

  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2">
        <div className="text-xs font-medium uppercase tracking-[0.18em] text-muted-foreground">{label}</div>
        <div className="flex items-center gap-2">
          <span className="text-[10px] text-muted-foreground">{nonEmptyLines(visibleValue || value).length} lines</span>
          {onCopy ? (
            <Button type="button" size="sm" variant="ghost" className="h-6 px-2 text-[11px]" onClick={onCopy}>
              <Copy className="mr-1 h-3 w-3" />
              Copy
            </Button>
          ) : null}
        </div>
      </div>
      <div className="mt-1.5 rounded-[1.1rem] border border-border bg-background p-3">
        <pre className="whitespace-pre-wrap font-mono text-[11px] leading-5 text-foreground">
          {visibleValue || emptyLabel}
        </pre>
      </div>
    </div>
  );
}

function OverviewSection({
  settings,
  query,
}: {
  settings: LinuxUiSettingsSnapshot;
  query: string;
}) {
  const cronEntries = parseCronEntries(
    settings.crontab.user_crontab,
    settings.crontab.system_crontab,
    settings.crontab.cron_dirs,
  );
  const envVars = parseEnvVariables(settings.environment.variables);
  const permitRootLogin = extractDirective(settings.security.ssh_config, "PermitRootLogin") || "not specified";
  const passwordAuthentication = extractDirective(settings.security.ssh_config, "PasswordAuthentication") || "not specified";
  const firewallState = firstMeaningfulLine(settings.security.firewall, "No firewall data");

  return (
    <div className="space-y-4">
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <InfoCard label="Host" value={settings.general.hostname} mono hint={firstMeaningfulLine(settings.general.os_release, settings.general.kernel)} />
        <InfoCard label="Current User" value={settings.users.current_user} mono hint={settings.users.sudo_group} />
        <InfoCard label="Accounts" value={settings.users.accounts.length} hint="UID 1000+ users" />
        <InfoCard label="Active Sessions" value={nonEmptyLines(settings.users.logged_in).length} hint="Users logged in now" />
        <InfoCard label="Cron Entries" value={cronEntries.length} hint="User and system cron" />
        <InfoCard label="Env Vars" value={envVars.length} hint={`${settings.environment.path_directories.length} PATH entries`} />
        <InfoCard label="Root Login" value={permitRootLogin} tone={/no|prohibit-password/i.test(permitRootLogin) ? "accent" : "alert"} />
        <InfoCard label="Password Auth" value={passwordAuthentication} tone={/no/i.test(passwordAuthentication) ? "accent" : "alert"} />
      </div>

      <div className="grid gap-4 xl:grid-cols-2">
        <div className="space-y-4">
          <OutputBlock label="OS Release" value={settings.general.os_release} query={query} emptyLabel="No OS release data" />
          <OutputBlock label="Firewall Snapshot" value={settings.security.firewall} query={query} emptyLabel="No firewall tool detected" />
        </div>
        <div className="space-y-4">
          <div className="rounded-[1.1rem] border border-border bg-background p-3 shadow-sm">
            <div className="text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Runtime Snapshot</div>
            <div className="mt-3 grid gap-2 sm:grid-cols-2">
              <InfoCard label="Shell" value={settings.environment.shell} mono />
              <InfoCard label="Locale" value={settings.environment.locale} mono />
              <InfoCard label="Timers" value={nonEmptyLines(settings.crontab.timers).length} hint="Visible systemd timers" />
              <InfoCard label="Firewall" value={firewallState} tone={/active|enabled|running/i.test(firewallState) ? "accent" : "default"} />
            </div>
          </div>
          <div className="rounded-[1.1rem] border border-border bg-background p-3 shadow-sm">
            <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">PATH Directories</div>
            <div className="space-y-2">
              {settings.environment.path_directories.slice(0, 8).map((entry) => (
                <div key={entry} className="rounded-xl border border-border/70 bg-card px-3 py-2 font-mono text-[11px] text-foreground">
                  {entry}
                </div>
              ))}
              {settings.environment.path_directories.length === 0 ? (
                <div className="rounded-xl border border-dashed border-border/70 bg-card px-3 py-4 text-center text-xs text-muted-foreground">
                  PATH is empty
                </div>
              ) : null}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

function GeneralSection({ settings, query }: { settings: LinuxUiSettingsSnapshot["general"]; query: string }) {
  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">System Information</div>
      <div className="grid gap-2 sm:grid-cols-2">
        <InfoCard label="Hostname" value={settings.hostname} mono />
        <InfoCard label="Timezone" value={settings.timezone} />
        <InfoCard label="Kernel" value={settings.kernel} mono />
        <InfoCard label="Architecture" value={settings.architecture} />
        <InfoCard label="Uptime" value={settings.uptime} />
        <InfoCard label="CPU" value={settings.cpu} />
        <InfoCard label="Total Memory" value={settings.total_memory} />
      </div>
      {settings.os_release ? <OutputBlock label="OS Release" value={settings.os_release} query={query} /> : null}
    </div>
  );
}

function UsersSection({ settings, query }: { settings: LinuxUiSettingsSnapshot["users"]; query: string }) {
  const normalizedQuery = query.trim().toLowerCase();
  const visibleAccounts = normalizedQuery
    ? settings.accounts.filter((account) =>
        `${account.name} ${account.uid} ${account.home} ${account.shell}`.toLowerCase().includes(normalizedQuery),
      )
    : settings.accounts;

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">User Management</div>
      <div className="grid gap-2 sm:grid-cols-2">
        <InfoCard label="Current User" value={settings.current_user} mono />
        <InfoCard label="Sudo Group" value={settings.sudo_group} mono />
      </div>

      <div className="mt-4 text-xs font-medium uppercase tracking-wide text-muted-foreground">
        System Users (UID ≥ 1000)
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
                <span className="text-[10px] text-muted-foreground">uid:{account.uid}</span>
              </div>
              <div className="flex items-center gap-2 text-[10px] text-muted-foreground">
                <span className="font-mono">{account.home}</span>
                <span className="font-mono">{account.shell}</span>
              </div>
            </div>
          ))
        ) : (
          <div className="rounded-xl border border-dashed border-border/70 bg-background/90 px-3 py-4 text-center text-xs text-muted-foreground">
            No regular users found
          </div>
        )}
      </div>

      <OutputBlock label="Logged In Now" value={settings.logged_in} query={query} emptyLabel="No sessions" />
      <OutputBlock label="Last Logins" value={settings.last_logins} query={query} emptyLabel="No data" />
    </div>
  );
}

function CrontabSection({ settings, query }: { settings: LinuxUiSettingsSnapshot["crontab"]; query: string }) {
  const cronEntries = parseCronEntries(settings.user_crontab, settings.system_crontab, settings.cron_dirs);

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">Scheduled Tasks</div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <InfoCard label="User Entries" value={parseCronEntries(settings.user_crontab).length} />
        <InfoCard label="System Entries" value={parseCronEntries(settings.system_crontab).length} />
        <InfoCard label="Cron.d" value={parseCronEntries(settings.cron_dirs).length} />
        <InfoCard label="Timers" value={nonEmptyLines(settings.timers).length} />
      </div>
      <div className="rounded-[1.1rem] border border-border bg-background p-3 shadow-sm">
        <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Visible Entries</div>
        <div className="space-y-2">
          {(query.trim() ? cronEntries.filter((line) => line.toLowerCase().includes(query.trim().toLowerCase())) : cronEntries).slice(0, 24).map((line) => (
            <div key={line} className="rounded-xl border border-border/70 bg-card px-3 py-2 font-mono text-[11px] text-foreground">
              {line}
            </div>
          ))}
          {cronEntries.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border/70 bg-card px-3 py-4 text-center text-xs text-muted-foreground">
              No cron entries found
            </div>
          ) : null}
        </div>
      </div>
      <OutputBlock label="User Crontab" value={settings.user_crontab} query={query} emptyLabel="No crontab for current user" />
      <OutputBlock label="System Crontab (/etc/crontab)" value={settings.system_crontab} query={query} emptyLabel="No /etc/crontab" />
      <OutputBlock label="/etc/cron.d/" value={settings.cron_dirs} query={query} emptyLabel="No /etc/cron.d/" />
      <OutputBlock label="Systemd Timers" value={settings.timers} query={query} emptyLabel="systemctl unavailable" />
    </div>
  );
}

function EnvironmentSection({ settings, query }: { settings: LinuxUiSettingsSnapshot["environment"]; query: string }) {
  const envVars = parseEnvVariables(settings.variables);
  const normalizedQuery = query.trim().toLowerCase();
  const visibleEnvVars = normalizedQuery
    ? envVars.filter((item) => `${item.key}=${item.value}`.toLowerCase().includes(normalizedQuery))
    : envVars;

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">Environment</div>
      <div className="grid gap-2 sm:grid-cols-2">
        <InfoCard label="Shell" value={settings.shell} mono />
        <InfoCard label="Locale" value={settings.locale} mono />
        <InfoCard label="PATH Entries" value={settings.path_directories.length} />
        <InfoCard label="Env Vars" value={envVars.length} />
      </div>

      <OutputBlock label="PATH Directories" value={settings.path_directories.join("\n")} query={query} emptyLabel="PATH is empty" />
      <div className="rounded-[1.1rem] border border-border bg-background p-3 shadow-sm">
        <div className="mb-2 text-[11px] uppercase tracking-[0.18em] text-muted-foreground">Environment Variables</div>
        <div className="space-y-2">
          {visibleEnvVars.slice(0, 40).map((item) => (
            <div key={item.key} className="rounded-xl border border-border/70 bg-card px-3 py-2">
              <div className="font-mono text-[11px] text-foreground">{item.key}</div>
              <div className="mt-1 break-all font-mono text-[10px] text-muted-foreground">{item.value || "(empty)"}</div>
            </div>
          ))}
          {visibleEnvVars.length === 0 ? (
            <div className="rounded-xl border border-dashed border-border/70 bg-card px-3 py-4 text-center text-xs text-muted-foreground">
              No environment variables match the current filter
            </div>
          ) : null}
        </div>
      </div>
      <OutputBlock label="Raw Environment Dump" value={settings.variables} query={query} emptyLabel="No environment variables" />
    </div>
  );
}

function SecuritySection({ settings, query }: { settings: LinuxUiSettingsSnapshot["security"]; query: string }) {
  const permitRootLogin = extractDirective(settings.ssh_config, "PermitRootLogin") || "not specified";
  const passwordAuthentication = extractDirective(settings.ssh_config, "PasswordAuthentication") || "not specified";

  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">Security Overview</div>
      <div className="grid gap-2 sm:grid-cols-2 xl:grid-cols-4">
        <InfoCard label="Root Login" value={permitRootLogin} tone={/no|prohibit-password/i.test(permitRootLogin) ? "accent" : "alert"} />
        <InfoCard label="Password Auth" value={passwordAuthentication} tone={/no/i.test(passwordAuthentication) ? "accent" : "alert"} />
        <InfoCard label="Firewall" value={firstMeaningfulLine(settings.firewall, "No firewall data")} hint="First reported line" />
        <InfoCard label="Listening Ports" value={nonEmptyLines(settings.listening_ports).length} tone={nonEmptyLines(settings.listening_ports).length > 0 ? "accent" : "default"} />
      </div>
      <OutputBlock label="SSH Configuration" value={settings.ssh_config} query={query} emptyLabel="Cannot read sshd_config" />
      <OutputBlock label="Firewall Status" value={settings.firewall} query={query} emptyLabel="No firewall tool detected" />
      <OutputBlock label="Listening Ports" value={settings.listening_ports} query={query} emptyLabel="Cannot list ports" />
      <OutputBlock label="Recent Failed Logins" value={settings.failed_logins} query={query} emptyLabel="No failed login data" />
    </div>
  );
}

export function SystemSettingsWindow({
  server,
  active,
}: {
  server: FrontendServer;
  active: boolean;
}) {
  const { toast } = useToast();
  const [section, setSection] = useState<SettingsSection>("overview");
  const [query, setQuery] = useState("");

  const settingsQuery = useQuery({
    queryKey: ["linux-ui", server.id, "settings"],
    queryFn: () => fetchLinuxUiSettings(server.id),
    enabled: active,
    staleTime: 30_000,
  });

  const settings = settingsQuery.data?.settings;
  const hasError = settingsQuery.error instanceof Error ? settingsQuery.error.message : "Failed to load settings";
  const normalizedQuery = query.trim().toLowerCase();
  const searchResults = useMemo(() => {
    if (!settings || !normalizedQuery) return [];
    const sections = [
      {
        section: "general" as const,
        label: "Host Summary",
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
        label: "Users and Sessions",
        value: [
          settings.users.current_user,
          settings.users.sudo_group,
          ...settings.users.accounts.map((account) => `${account.name} ${account.uid} ${account.home} ${account.shell}`),
          settings.users.logged_in,
          settings.users.last_logins,
        ].join("\n"),
      },
      {
        section: "crontab" as const,
        label: "Scheduled Tasks",
        value: [
          settings.crontab.user_crontab,
          settings.crontab.system_crontab,
          settings.crontab.cron_dirs,
          settings.crontab.timers,
        ].join("\n"),
      },
      {
        section: "environment" as const,
        label: "Environment",
        value: [
          settings.environment.shell,
          settings.environment.locale,
          settings.environment.path_directories.join("\n"),
          settings.environment.variables,
        ].join("\n"),
      },
      {
        section: "security" as const,
        label: "Security",
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
      .filter(Boolean) as Array<{ section: SettingsSection; label: string; snippet: string }>;
  }, [normalizedQuery, query, settings]);

  const sectionContent = useMemo(() => {
    if (!settings) return "";
    if (section === "overview") {
      return [
        `Host: ${settings.general.hostname}`,
        `Timezone: ${settings.general.timezone}`,
        `Current User: ${settings.users.current_user}`,
        `Accounts: ${settings.users.accounts.length}`,
        `Cron Entries: ${parseCronEntries(settings.crontab.user_crontab, settings.crontab.system_crontab, settings.crontab.cron_dirs).length}`,
        `Environment Vars: ${parseEnvVariables(settings.environment.variables).length}`,
        `Listening Ports: ${nonEmptyLines(settings.security.listening_ports).length}`,
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
        `Timezone: ${settings.general.timezone}`,
        `Kernel: ${settings.general.kernel}`,
        `Architecture: ${settings.general.architecture}`,
        `Uptime: ${settings.general.uptime}`,
        `CPU: ${settings.general.cpu}`,
        `Total Memory: ${settings.general.total_memory}`,
        settings.general.os_release,
      ]
        .filter(Boolean)
        .join("\n");
    }
    if (section === "users") {
      return [
        `Current User: ${settings.users.current_user}`,
        `Sudo Group: ${settings.users.sudo_group}`,
        "",
        "Accounts:",
        ...settings.users.accounts.map((account) => `${account.name} uid:${account.uid} ${account.home} ${account.shell}`),
        "",
        "Logged In Now:",
        settings.users.logged_in,
        "",
        "Last Logins:",
        settings.users.last_logins,
      ]
        .filter((item) => item != null)
        .join("\n");
    }
    if (section === "crontab") {
      return [
        "User Crontab:",
        settings.crontab.user_crontab,
        "",
        "System Crontab:",
        settings.crontab.system_crontab,
        "",
        "/etc/cron.d/:",
        settings.crontab.cron_dirs,
        "",
        "Systemd Timers:",
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
        "Environment Variables:",
        settings.environment.variables,
      ].join("\n");
    }
    return [
      "SSH Configuration:",
      settings.security.ssh_config,
      "",
      "Firewall Status:",
      settings.security.firewall,
      "",
      "Listening Ports:",
      settings.security.listening_ports,
      "",
      "Recent Failed Logins:",
      settings.security.failed_logins,
    ].join("\n");
  }, [section, settings]);

  const activeSection = SECTIONS.find((item) => item.id === section) || SECTIONS[0];

  return (
    <div className="flex h-full min-h-0 overflow-hidden bg-card text-foreground">
      <nav className="flex w-52 shrink-0 flex-col border-r border-border bg-card">
        <div className="border-b border-border px-3 py-3">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-xs font-medium text-foreground">System Settings</div>
              <div className="text-[10px] text-muted-foreground">{server.name}</div>
            </div>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-8 w-8 shrink-0 rounded-xl p-0 text-muted-foreground hover:bg-secondary hover:text-foreground"
              onClick={() => void settingsQuery.refetch()}
              disabled={settingsQuery.isFetching}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", settingsQuery.isFetching && "animate-spin")} />
            </Button>
          </div>
          <div className="relative mt-3">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
            <Input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Search settings..."
              className="h-9 rounded-xl border-border bg-background pl-9 text-sm"
            />
          </div>
        </div>
        <div className="border-b border-border px-3 py-3">
          <div className="grid gap-2">
            <InfoCard label="Host" value={settings?.general.hostname || server.host} mono />
            <InfoCard label="User" value={settings?.users.current_user || server.username} mono />
            <InfoCard label="Uptime" value={settings?.general.uptime || "Loading..."} />
          </div>
        </div>
        <div className="flex-1 space-y-1.5 p-2">
          {SECTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setSection(item.id)}
              className={cn(
                "flex w-full items-center gap-2 rounded-xl px-3 py-2.5 text-left text-xs transition-colors",
                section === item.id
                  ? "border border-primary/20 bg-primary/10 text-foreground"
                  : "text-muted-foreground hover:bg-secondary hover:text-foreground",
              )}
            >
              <span className="flex h-4 w-4 items-center justify-center [&>svg]:h-3.5 [&>svg]:w-3.5">{item.icon}</span>
              {item.label}
            </button>
          ))}
        </div>
      </nav>

      <ScrollArea className="min-h-0 flex-1">
        <div className="p-4">
          <div className="mb-4 rounded-[1.2rem] border border-border bg-background p-4">
            <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
              <div>
                <div className="text-sm font-semibold text-foreground">{activeSection.label}</div>
                <div className="mt-1 text-xs text-muted-foreground">
                  Focused system snapshot with only the operational details that usually matter first.
                </div>
                {normalizedQuery ? (
                  <div className="mt-2 text-[11px] text-muted-foreground">
                    Search filter: <span className="font-mono text-foreground">{query}</span>
                  </div>
                ) : null}
              </div>
              <div className="flex flex-wrap items-center gap-2">
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-8 rounded-xl border-border bg-card px-3 text-xs text-foreground hover:bg-secondary"
                  onClick={() => void settingsQuery.refetch()}
                  disabled={settingsQuery.isFetching}
                >
                  <RefreshCw className={cn("mr-1.5 h-3.5 w-3.5", settingsQuery.isFetching && "animate-spin")} />
                  Refresh
                </Button>
                <Button
                  type="button"
                  size="sm"
                  variant="outline"
                  className="h-8 rounded-xl border-border bg-card px-3 text-xs text-foreground hover:bg-secondary"
                  onClick={async () => {
                    await navigator.clipboard.writeText(sectionContent);
                    toast({ title: "Copied", description: `Copied ${section} details` });
                  }}
                  disabled={!sectionContent}
                >
                  <Copy className="mr-1.5 h-3.5 w-3.5" />
                  Copy
                </Button>
              </div>
            </div>
          </div>
          {normalizedQuery ? (
            <div className="mb-4 rounded-[1.2rem] border border-border bg-background p-4">
              <div className="text-sm font-semibold text-foreground">Search Results</div>
              <div className="mt-1 text-xs text-muted-foreground">
                {searchResults.length > 0 ? `${searchResults.length} matching settings areas` : "No matching settings areas"}
              </div>
              {searchResults.length > 0 ? (
                <div className="mt-3 grid gap-2">
                  {searchResults.map((item) => (
                    <button
                      key={`${item.section}-${item.label}`}
                      type="button"
                      onClick={() => setSection(item.section)}
                      className="rounded-xl border border-border bg-card px-3 py-3 text-left transition-colors hover:border-primary/20 hover:bg-secondary"
                    >
                      <div className="flex items-center gap-2">
                        <span className="rounded-full border border-border bg-background px-2 py-0.5 text-[10px] uppercase tracking-wide text-muted-foreground">
                          {SECTIONS.find((sectionItem) => sectionItem.id === item.section)?.label}
                        </span>
                        <span className="text-sm font-medium text-foreground">{item.label}</span>
                      </div>
                      <pre className="mt-2 whitespace-pre-wrap font-mono text-[11px] leading-5 text-muted-foreground">
                        {item.snippet}
                      </pre>
                    </button>
                  ))}
                </div>
              ) : null}
            </div>
          ) : null}
          {settingsQuery.isLoading && !settings ? (
            <div className="flex h-full min-h-[220px] items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              <span className="ml-2 text-sm text-muted-foreground">Loading system info...</span>
            </div>
          ) : settingsQuery.isError || !settings ? (
            <div className="rounded-[1.2rem] border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
              {hasError}
            </div>
          ) : (
            <>
              {section === "overview" ? <OverviewSection settings={settings} query={query} /> : null}
              {section === "general" ? <GeneralSection settings={settings.general} query={query} /> : null}
              {section === "users" ? <UsersSection settings={settings.users} query={query} /> : null}
              {section === "crontab" ? <CrontabSection settings={settings.crontab} query={query} /> : null}
              {section === "environment" ? <EnvironmentSection settings={settings.environment} query={query} /> : null}
              {section === "security" ? <SecuritySection settings={settings.security} query={query} /> : null}
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
