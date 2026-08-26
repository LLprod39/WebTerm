import {
  Play,
  Radio,
  Server,
  Terminal as TerminalIcon,
} from "lucide-react";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { getWidgetNumberProp, getWidgetStringProp } from "@/components/dashboard/widgetProps";
import type { WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { relativeTime, cn } from "@/lib/utils";
import { localize } from "@/lib/i18n";
import type { UserDashboardData } from "./useUserDashboardData";
import { cpuToneClass, sectionToneStyles, type StatusTone } from "./userDashboardShared";

type ServerWidgetCtx = Pick<
  UserDashboardData,
  "boot" | "mon" | "monLoading" | "monFetching" | "liveConnected" | "liveMetrics" | "lang"
>;

/** Server health, quick connect, alerts. */
export function buildUserServerWidgets(ctx: ServerWidgetCtx): WidgetDefinition[] {
  const { boot, mon, monLoading, monFetching, liveConnected, liveMetrics, lang } = ctx;

  return [
    {
      id: "servers_health",
      title: localize(lang, "Состояние серверов", "Server health"),
      icon: <Server className="h-4 w-4" />,
      defaultSize: { w: 8, h: 1 },
      render: (config) => {
        const limit = getWidgetNumberProp(config, "limit", 5);
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", localize(lang, "Состояние серверов", "Server health"));
        const displayServers = mon?.servers?.slice(0, limit) ?? [];
        const isLive = (serverId: number) => liveMetrics.has(serverId);

        return (
          <SectionCard
            title={title}
            icon={<Server className="h-4 w-4" />}
            className={sectionToneStyles[tone]}
            description={
              liveConnected
                ? localize(lang, "Онлайн · CPU / RAM / диск · около 2 с", "Live · CPU / RAM / disk · about 2s")
                : localize(lang, "Снимок + обновление…", "Snapshot + updating…")
            }
            actions={
              <span
                className={cn(
                  "inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-[10px] font-medium",
                  liveConnected
                    ? "bg-success/10 text-success"
                    : "bg-muted text-muted-foreground",
                )}
              >
                <Radio className={cn("h-3 w-3", liveConnected && "animate-pulse")} />
                {liveConnected ? localize(lang, "Онлайн", "Live") : localize(lang, "Сохранённые данные", "Saved data")}
              </span>
            }
          >
            <div className="space-y-2.5">
              {displayServers.map((s) => {
                const stale = Boolean(s.is_stale);
                const hasMetrics =
                  typeof s.cpu_percent === "number" ||
                  typeof s.memory_percent === "number" ||
                  typeof s.disk_percent === "number";
                const displayStatus =
                  s.status === "unreachable" && (stale || hasMetrics)
                    ? "checking"
                    : s.status === "unknown" && hasMetrics
                      ? "healthy"
                      : s.status;
                const statusTone: StatusTone =
                  displayStatus === "healthy"
                    ? "success"
                    : displayStatus === "warning"
                      ? "warning"
                      : displayStatus === "critical"
                        ? "danger"
                        : displayStatus === "unreachable"
                          ? "danger"
                          : "neutral";
                const statusLabel =
                  displayStatus === "checking"
                    ? localize(lang, "проверка…", "checking…")
                    : displayStatus === "unknown"
                      ? localize(lang, "нет данных", "no data")
                      : displayStatus;
                const live = isLive(s.server_id);
                return (
                  <div key={s.server_id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-xl border border-border/60 bg-surface-2/40 hover:border-primary/40 hover:bg-surface-2 transition-all text-xs">
                    <div className="flex items-center gap-3 min-w-0">
                      <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface-1 border border-border/60">
                        <Server className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                      </div>
                      <div className="truncate">
                        <span className="font-semibold text-foreground/95">{s.server_name}</span>
                        <span className="text-xs text-muted-foreground/50 ml-2 font-mono">({s.host})</span>
                        {live ? (
                          <span className="ml-2 text-[10px] font-medium uppercase tracking-wide text-success/80">
                            live
                          </span>
                        ) : null}
                      </div>
                    </div>
                    <div className="flex items-center gap-2 shrink-0 flex-wrap sm:flex-nowrap">
                      <StatusBadge label={statusLabel} tone={statusTone} />
                      {s.cpu_percent !== null && s.cpu_percent !== undefined ? (
                        <div className="text-xs text-muted-foreground shrink-0 bg-surface-1 border border-border/60 rounded px-1.5 py-0.5 font-medium">
                          CPU: <span className={cn("font-bold", cpuToneClass(s.cpu_percent))}>{Math.round(s.cpu_percent)}%</span>
                        </div>
                      ) : monFetching || monLoading || liveConnected ? (
                        <div className="text-xs text-muted-foreground/60 shrink-0">CPU: —</div>
                      ) : null}
                      {s.memory_percent !== null && s.memory_percent !== undefined ? (
                        <div className="text-xs text-muted-foreground shrink-0 bg-surface-1 border border-border/60 rounded px-1.5 py-0.5 font-medium">
                          RAM: <span className="text-foreground/90 font-bold">{Math.round(s.memory_percent)}%</span>
                        </div>
                      ) : null}
                      {s.disk_percent !== null && s.disk_percent !== undefined ? (
                        <div className="text-xs text-muted-foreground shrink-0 bg-surface-1 border border-border/60 rounded px-1.5 py-0.5 font-medium">
                          HDD: <span className="text-foreground/90 font-bold">{Math.round(s.disk_percent)}%</span>
                        </div>
                      ) : null}
                      <Button size="xs" variant="outline" asChild className="shrink-0">
                        <Link to={`/servers/${s.server_id}/terminal`}>{localize(lang, "Терминал", "Terminal")}</Link>
                      </Button>
                    </div>
                  </div>
                );
              })}
              {displayServers.length === 0 && (
                <div className="py-6 text-center text-xs text-muted-foreground">
                  {monLoading
                    ? localize(lang, "Загрузка мониторинга…", "Loading monitoring…")
                    : localize(lang, "Нет данных по серверам", "No server data")}
                </div>
              )}
            </div>
          </SectionCard>
        );
      },
    },
    {
      id: "recent_servers",
      title: localize(lang, "Быстрое подключение", "Quick connect"),
      icon: <TerminalIcon className="h-4 w-4" />,
      defaultSize: { w: 6, h: 1 },
      render: (config) => {
        const limit = getWidgetNumberProp(config, "limit", 5);
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", localize(lang, "Быстрое подключение", "Quick connect"));
        const displayServers = boot?.servers?.slice(0, limit) ?? [];

        return (
          <SectionCard
            title={title}
            icon={<TerminalIcon className="h-4 w-4" />}
            description={localize(lang, "Быстрый переход к терминалу", "Open a terminal quickly")}
            className={sectionToneStyles[tone]}
          >
            <div className="grid gap-2 sm:grid-cols-2">
              {displayServers.map((s) => (
                <Link
                  key={s.id}
                  to={`/servers/${s.id}/terminal`}
                  className="group flex items-center gap-3 rounded-sm border border-border bg-surface-1 px-3 py-3 text-xs transition-all hover:border-primary/60 hover:shadow-elev-1"
                >
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-border bg-surface-2 text-muted-foreground transition-colors group-hover:border-primary/40 group-hover:text-primary">
                    <TerminalIcon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0">
                    <div className="truncate font-semibold text-foreground/95">{s.name}</div>
                    <div className="truncate font-mono text-2xs text-muted-foreground/60">{s.host}</div>
                  </div>
                </Link>
              ))}
              <Link
                to="/servers/hub"
                className="flex items-center justify-center gap-2 rounded-sm border border-dashed border-border bg-surface-1/40 px-3 py-3 text-xs font-semibold text-muted-foreground transition-all hover:border-primary/60 hover:text-primary"
              >
                <Server className="h-4 w-4" />
                {localize(lang, "Все серверы", "All servers")}
              </Link>
            </div>
            {displayServers.length === 0 && (
              <div className="mt-2 py-4 text-center text-xs text-muted-foreground">
                {localize(lang, "Серверов пока нет — добавьте первый в Хабе серверов.", "No servers yet — add your first one in the Server hub.")}
              </div>
            )}
          </SectionCard>
        );
      },
    },
    {
      id: "user_alerts",
      title: localize(lang, "Предупреждения и алерты", "Warnings & alerts"),
      icon: <Play className="h-4 w-4" />,
      defaultSize: { w: 6, h: 1 },
      render: (config) => {
        const limit = getWidgetNumberProp(config, "limit", 5);
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", localize(lang, "Предупреждения и алерты", "Warnings & alerts"));
        const displayAlerts = mon?.alerts?.slice(0, limit) ?? [];

        return (
          <SectionCard title={title} icon={<Play className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <div className="space-y-3">
              {displayAlerts.map((a) => {
                const alertTone: StatusTone = a.severity === "critical" ? "danger" : a.severity === "warning" ? "warning" : "info";
                return (
                  <div key={a.id} className="flex items-start gap-3 p-3 rounded-xl border border-border/60 bg-surface-2/40 hover:border-primary/30 transition-all text-xs">
                    <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive text-xs font-bold">
                      !
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <strong className="font-semibold text-foreground/95 truncate">{a.title}</strong>
                        <StatusBadge label={a.severity} tone={alertTone} />
                      </div>
                      <p className="mt-1 text-muted-foreground text-xs leading-relaxed">{a.message}</p>
                      <p className="mt-1 text-xs text-muted-foreground/60">
                        {localize(lang, "сервер", "server")}: <strong>{a.server_name}</strong> • {relativeTime(a.created_at)}
                      </p>
                    </div>
                  </div>
                );
              })}
              {displayAlerts.length === 0 && (
                <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-xl bg-surface-1/60">
                  {localize(lang, "Активных предупреждений нет", "No active warnings")}
                </div>
              )}
            </div>
          </SectionCard>
        );
      },
    },
  ];
}
