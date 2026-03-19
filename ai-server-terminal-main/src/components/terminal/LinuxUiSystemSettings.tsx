import { useState, type ReactNode } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  Clock,
  Globe,
  Loader2,
  RefreshCw,
  Server,
  Shield,
  User,
  Users,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import {
  fetchLinuxUiSettings,
  type FrontendServer,
  type LinuxUiSettingsSnapshot,
} from "@/lib/api";
import { cn } from "@/lib/utils";

type SettingsSection = "general" | "users" | "crontab" | "environment" | "security";

interface SectionDef {
  id: SettingsSection;
  label: string;
  icon: ReactNode;
}

const SECTIONS: SectionDef[] = [
  { id: "general", label: "General", icon: <Server className="h-4 w-4" /> },
  { id: "users", label: "Users", icon: <Users className="h-4 w-4" /> },
  { id: "crontab", label: "Cron Jobs", icon: <Clock className="h-4 w-4" /> },
  { id: "environment", label: "Environment", icon: <Globe className="h-4 w-4" /> },
  { id: "security", label: "Security", icon: <Shield className="h-4 w-4" /> },
];

function InfoCard({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="rounded-xl border border-border/70 bg-background/90 p-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className={cn("mt-1.5 break-words text-sm text-foreground", mono && "font-mono text-xs")}>
        {value || "N/A"}
      </div>
    </div>
  );
}

function OutputBlock({
  label,
  value,
  emptyLabel = "No data",
}: {
  label: string;
  value: string;
  emptyLabel?: string;
}) {
  return (
    <div>
      <div className="text-xs font-medium uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1.5 rounded-xl border border-border/70 bg-background/90 p-3">
        <pre className="whitespace-pre-wrap font-mono text-[11px] leading-5 text-foreground">
          {value || emptyLabel}
        </pre>
      </div>
    </div>
  );
}

function GeneralSection({ settings }: { settings: LinuxUiSettingsSnapshot["general"] }) {
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
      {settings.os_release ? <OutputBlock label="OS Release" value={settings.os_release} /> : null}
    </div>
  );
}

function UsersSection({ settings }: { settings: LinuxUiSettingsSnapshot["users"] }) {
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
        {settings.accounts.length > 0 ? (
          settings.accounts.map((account) => (
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

      <OutputBlock label="Logged In Now" value={settings.logged_in} emptyLabel="No sessions" />
      <OutputBlock label="Last Logins" value={settings.last_logins} emptyLabel="No data" />
    </div>
  );
}

function CrontabSection({ settings }: { settings: LinuxUiSettingsSnapshot["crontab"] }) {
  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">Scheduled Tasks</div>
      <OutputBlock label="User Crontab" value={settings.user_crontab} emptyLabel="No crontab for current user" />
      <OutputBlock label="System Crontab (/etc/crontab)" value={settings.system_crontab} emptyLabel="No /etc/crontab" />
      <OutputBlock label="/etc/cron.d/" value={settings.cron_dirs} emptyLabel="No /etc/cron.d/" />
      <OutputBlock label="Systemd Timers" value={settings.timers} emptyLabel="systemctl unavailable" />
    </div>
  );
}

function EnvironmentSection({ settings }: { settings: LinuxUiSettingsSnapshot["environment"] }) {
  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">Environment</div>
      <div className="grid gap-2 sm:grid-cols-2">
        <InfoCard label="Shell" value={settings.shell} mono />
        <InfoCard label="Locale" value={settings.locale} mono />
      </div>

      <OutputBlock
        label="PATH Directories"
        value={settings.path_directories.join("\n")}
        emptyLabel="PATH is empty"
      />
      <OutputBlock label="Environment Variables" value={settings.variables} emptyLabel="No environment variables" />
    </div>
  );
}

function SecuritySection({ settings }: { settings: LinuxUiSettingsSnapshot["security"] }) {
  return (
    <div className="space-y-3">
      <div className="text-sm font-medium text-foreground">Security Overview</div>
      <OutputBlock label="SSH Configuration" value={settings.ssh_config} emptyLabel="Cannot read sshd_config" />
      <OutputBlock label="Firewall Status" value={settings.firewall} emptyLabel="No firewall tool detected" />
      <OutputBlock label="Listening Ports" value={settings.listening_ports} emptyLabel="Cannot list ports" />
      <OutputBlock label="Recent Failed Logins" value={settings.failed_logins} emptyLabel="No failed login data" />
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
  const [section, setSection] = useState<SettingsSection>("general");

  const settingsQuery = useQuery({
    queryKey: ["linux-ui", server.id, "settings"],
    queryFn: () => fetchLinuxUiSettings(server.id),
    enabled: active,
    staleTime: 30_000,
  });

  const settings = settingsQuery.data?.settings;
  const hasError = settingsQuery.error instanceof Error ? settingsQuery.error.message : "Failed to load settings";

  return (
    <div className="flex h-full min-h-0 overflow-hidden">
      <nav className="flex w-48 shrink-0 flex-col border-r border-border/60 bg-muted/20">
        <div className="border-b border-border/40 px-3 py-2.5">
          <div className="flex items-center justify-between gap-2">
            <div>
              <div className="text-xs font-medium text-foreground">System Settings</div>
              <div className="text-[10px] text-muted-foreground">{server.name}</div>
            </div>
            <Button
              type="button"
              size="sm"
              variant="ghost"
              className="h-7 w-7 shrink-0 p-0"
              onClick={() => void settingsQuery.refetch()}
              disabled={settingsQuery.isFetching}
            >
              <RefreshCw className={cn("h-3.5 w-3.5", settingsQuery.isFetching && "animate-spin")} />
            </Button>
          </div>
        </div>
        <div className="flex-1 space-y-0.5 p-1.5">
          {SECTIONS.map((item) => (
            <button
              key={item.id}
              type="button"
              onClick={() => setSection(item.id)}
              className={cn(
                "flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-xs transition-colors",
                section === item.id
                  ? "bg-primary/10 text-foreground"
                  : "text-muted-foreground hover:bg-muted/50 hover:text-foreground",
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
          {settingsQuery.isLoading && !settings ? (
            <div className="flex h-full min-h-[220px] items-center justify-center">
              <Loader2 className="h-5 w-5 animate-spin text-primary" />
              <span className="ml-2 text-sm text-muted-foreground">Loading system info...</span>
            </div>
          ) : settingsQuery.isError || !settings ? (
            <div className="rounded-xl border border-destructive/30 bg-destructive/10 p-4 text-sm text-destructive">
              {hasError}
            </div>
          ) : (
            <>
              {section === "general" ? <GeneralSection settings={settings.general} /> : null}
              {section === "users" ? <UsersSection settings={settings.users} /> : null}
              {section === "crontab" ? <CrontabSection settings={settings.crontab} /> : null}
              {section === "environment" ? <EnvironmentSection settings={settings.environment} /> : null}
              {section === "security" ? <SecuritySection settings={settings.security} /> : null}
            </>
          )}
        </div>
      </ScrollArea>
    </div>
  );
}
