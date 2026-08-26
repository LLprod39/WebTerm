import { Link } from "react-router-dom";
import {
  ChevronRight,
  FolderPlus,
  MoreVertical,
  Plus,
  Server,
  Settings,
  ShieldCheck,
  SlidersHorizontal,
  Terminal,
  Trash2,
} from "lucide-react";
import { FleetHealthIndicator, StatusIndicator } from "@/components/StatusIndicator";
import { ServerOsBadge } from "@/components/servers/ServerOsBadge";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { EmptyState } from "@/components/ui/page-shell";
import type { FrontendServer, MonitoringStatusItem } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { resolveServerOs, serverOsLabelKey } from "@/lib/server-os";
import { pushRecentServer } from "@/lib/recent-entities";
import { displayServerGroupName, formatServerCount } from "./formatters";

type MetricKey = "cpu_percent" | "memory_percent" | "disk_percent";

const METRICS: Array<{ key: MetricKey; label: string; warn: number; critical: number }> = [
  { key: "cpu_percent", label: "CPU", warn: 80, critical: 95 },
  { key: "memory_percent", label: "RAM", warn: 85, critical: 95 },
  { key: "disk_percent", label: "Disk", warn: 80, critical: 90 },
];

function formatRelativeTime(iso: string | null | undefined, lang: string) {
  if (!iso) return localize(lang, "нет данных", "no data");
  const timestamp = new Date(iso).getTime();
  if (!Number.isFinite(timestamp)) return localize(lang, "неизвестно", "unknown");
  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60_000));
  if (minutes < 1) return localize(lang, "только что", "just now");
  if (minutes < 60) return localize(lang, `${minutes} мин назад`, `${minutes}m ago`);
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return localize(lang, `${hours} ч назад`, `${hours}h ago`);
  return localize(lang, `${Math.floor(hours / 24)} дн назад`, `${Math.floor(hours / 24)}d ago`);
}

function metricTone(value: number, warn: number, critical: number) {
  if (value >= critical) return "text-destructive";
  if (value >= warn) return "text-warning";
  return "text-foreground";
}

function metricBarTone(value: number, warn: number, critical: number) {
  if (value >= critical) return "bg-destructive";
  if (value >= warn) return "bg-warning";
  return "bg-primary/75";
}

function ResourceValues({ health }: { health?: MonitoringStatusItem }) {
  return (
    <div className="grid grid-cols-3 gap-3">
      {METRICS.map((metric) => {
        const value = health?.[metric.key];
        const hasValue = typeof value === "number";
        const normalizedValue = hasValue ? Math.min(100, Math.max(0, value)) : 0;
        return (
          <div key={metric.key} className="min-w-0">
            <div className="mb-1.5 flex items-center justify-between gap-2">
              <span className="text-[11px] font-medium text-muted-foreground">{metric.label}</span>
              <span className={cn("font-mono text-xs font-semibold tabular-nums", hasValue ? metricTone(value, metric.warn, metric.critical) : "text-muted-foreground")}>
                {hasValue ? `${Math.round(value)}%` : "—"}
              </span>
            </div>
            <div className="h-1.5 overflow-hidden rounded-full bg-secondary" aria-hidden={!hasValue}>
              <div
                className={cn("h-full rounded-full transition-[width,background-color] duration-300", hasValue ? metricBarTone(value, metric.warn, metric.critical) : "bg-transparent")}
                style={{ width: `${normalizedValue}%` }}
                role={hasValue ? "progressbar" : undefined}
                aria-label={hasValue ? metric.label : undefined}
                aria-valuemin={hasValue ? 0 : undefined}
                aria-valuemax={hasValue ? 100 : undefined}
                aria-valuenow={hasValue ? Math.round(normalizedValue) : undefined}
              />
            </div>
          </div>
        );
      })}
    </div>
  );
}

interface ServersListTabProps {
  grouped: Record<string, FrontendServer[]>;
  filteredCount: number;
  totalServers: number;
  collapsed: Record<string, boolean>;
  fleetHealthByServerId: Map<number, MonitoringStatusItem>;
  t: (key: string) => string;
  tr: (key: string, vars?: Record<string, string | number>) => string;
  lang: string;
  onToggleGroup: (group: string) => void;
  onOpenCreate: () => void;
  onOpenAdvanced: (server: FrontendServer) => void | Promise<void>;
  onOpenEdit: (server: FrontendServer) => void | Promise<void>;
  onRequestDeleteServer: (server: FrontendServer) => void;
  onClearFilters: () => void;
}

export function ServersListTab({
  grouped,
  filteredCount,
  totalServers,
  collapsed,
  fleetHealthByServerId,
  t,
  tr,
  lang,
  onToggleGroup,
  onOpenCreate,
  onOpenAdvanced,
  onOpenEdit,
  onRequestDeleteServer,
  onClearFilters,
}: ServersListTabProps) {
  const groupEntries = Object.entries(grouped);

  return (
    <div>
      {filteredCount ? (
        <section className="overflow-hidden rounded-xl border border-border bg-card">
          <div className="hidden min-h-11 grid-cols-[minmax(240px,1fr)_minmax(210px,.75fr)_minmax(300px,.95fr)_76px_40px] items-center gap-4 border-b border-border bg-surface-0/70 px-5 text-[11px] font-semibold uppercase tracking-[0.09em] text-muted-foreground lg:grid">
            <span>{localize(lang, "Сервер", "Server")}</span>
            <span>{localize(lang, "Подключение", "Connection")}</span>
            <span>{localize(lang, "Ресурсы", "Resources")}</span>
            <span className="text-center">SSH</span>
            <span className="sr-only">{localize(lang, "Действия", "Actions")}</span>
          </div>

          {groupEntries.map(([group, inGroup]) => {
            const isCollapsed = collapsed[group];
            const groupLabel = displayServerGroupName(group, lang);
            const healthy = inGroup.filter((server) => {
              const health = fleetHealthByServerId.get(server.id);
              return Boolean(health && !health.is_stale && health.status === "healthy");
            }).length;

            return (
              <div key={group} className="border-b border-border last:border-b-0">
                <button
                  type="button"
                  onClick={() => onToggleGroup(group)}
                  className="flex min-h-12 w-full items-center gap-2.5 bg-surface-0/40 px-5 text-left transition-colors hover:bg-surface-1 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-primary"
                  aria-expanded={!isCollapsed}
                  aria-label={tr(isCollapsed ? "srv.expand_group" : "srv.collapse_group", { name: groupLabel })}
                >
                  <ChevronRight className={cn("h-4 w-4 shrink-0 text-muted-foreground transition-transform", !isCollapsed && "rotate-90")} />
                  <span className="text-[13px] font-semibold text-foreground">{groupLabel}</span>
                  <span className="text-xs text-muted-foreground">{formatServerCount(inGroup.length, lang)}</span>
                  <span className="inline-flex items-center gap-1.5 text-xs text-success">
                    <span className="h-1.5 w-1.5 rounded-full bg-success" />{healthy} {localize(lang, "в норме", "healthy")}
                  </span>
                </button>

                {!isCollapsed ? (
                  <div className="divide-y divide-border/70">
                    {inGroup.map((server) => {
                      const health = fleetHealthByServerId.get(server.id);
                      const osKind = resolveServerOs(server);
                      const osLabel = server.detected_os_pretty || t(serverOsLabelKey(osKind));
                      const statusDot = health ? (
                        <FleetHealthIndicator
                          status={health.is_stale && health.status === "unreachable" ? "unknown" : health.status}
                          stale={health.is_stale && health.status !== "unreachable"}
                          showLabel={false}
                        />
                      ) : <StatusIndicator status="unknown" showLabel={false} />;

                      return (
                        <div key={server.id} className="grid min-h-[68px] items-center gap-4 px-5 py-3 transition-colors hover:bg-surface-1/70 lg:grid-cols-[minmax(240px,1fr)_minmax(210px,.75fr)_minmax(300px,.95fr)_76px_40px]">
                          <div className="flex min-w-0 items-center gap-2.5">
                            <Link to={`/monitoring?server=${server.id}`} className="shrink-0 rounded-full focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-primary" aria-label={localize(lang, "Открыть мониторинг", "Open monitoring")}>{statusDot}</Link>
                            <ServerOsBadge kind={osKind} size="xs" />
                            <div className="min-w-0">
                              <div className="flex items-center gap-2">
                                <Link to={`/monitoring?server=${server.id}`} className="truncate text-sm font-semibold text-foreground hover:text-primary">{server.name}</Link>
                                {server.is_shared ? <span className="rounded-full bg-info/10 px-1.5 py-0.5 text-[9px] text-info">{t("srv.shared_badge")}</span> : null}
                              </div>
                              <p className="truncate text-xs text-muted-foreground">{osLabel}{server.last_connected ? ` · ${formatRelativeTime(server.last_connected, lang)}` : ""}</p>
                            </div>
                          </div>

                          <div className="min-w-0">
                            <p className="truncate font-mono text-[13px] text-foreground">{server.host}:{server.port}</p>
                            <p className="truncate text-xs text-muted-foreground">{server.username}</p>
                          </div>

                          <ResourceValues health={health} />

                          <Button asChild size="xs" variant="outline" className="h-9 w-full shrink-0 gap-1.5 px-2.5 text-[11px]">
                            <Link to={`/servers/${server.id}/terminal`} onClick={() => pushRecentServer({ id: server.id, name: server.name, host: server.host })}>
                              <Terminal className="h-3.5 w-3.5" />SSH
                            </Link>
                          </Button>

                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button size="icon" variant="secondary" className="h-9 w-9 border-border-strong bg-secondary text-foreground shadow-hard-sm hover:border-primary/60 hover:bg-primary/10 hover:text-primary" aria-label={tr("srv.open_advanced_for", { name: server.name })}><MoreVertical className="h-4 w-4" /></Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end" className="w-52">
                              <DropdownMenuItem onClick={() => void onOpenAdvanced(server)}><SlidersHorizontal className="mr-2 h-3.5 w-3.5" />{t("srv.advanced")}</DropdownMenuItem>
                              {server.can_edit ? <>
                                <DropdownMenuItem onClick={() => void onOpenEdit(server)}><Settings className="mr-2 h-3.5 w-3.5" />{t("srv.edit_server")}</DropdownMenuItem>
                                <DropdownMenuSeparator />
                                <DropdownMenuItem onClick={() => onRequestDeleteServer(server)} className="text-destructive focus:text-destructive"><Trash2 className="mr-2 h-3.5 w-3.5" />{t("srv.delete")}</DropdownMenuItem>
                              </> : null}
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      );
                    })}
                  </div>
                ) : null}
              </div>
            );
          })}
        </section>
      ) : totalServers ? (
        <EmptyState
          icon={<Server className="h-5 w-5" />}
          title={t("srv.empty_filtered_title")}
          description={t("srv.empty_filtered_text")}
          actions={<><Button size="sm" variant="outline" onClick={onClearFilters}>{localize(lang, "Сбросить фильтры", "Reset filters")}</Button><Button size="sm" onClick={onOpenCreate}><Plus className="mr-1 h-4 w-4" />{t("srv.add")}</Button></>}
        />
      ) : (
        <div className="rounded-xl border border-dashed border-border bg-card/50 px-6 py-12 text-center">
          <Server className="mx-auto h-6 w-6 text-muted-foreground" />
          <h3 className="mt-3 text-sm font-semibold text-foreground">{t("srv.empty_title")}</h3>
          <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-muted-foreground">{t("srv.empty_text")}</p>
          <div className="mt-5 flex flex-wrap justify-center gap-2">
            <Button size="sm" onClick={onOpenCreate}><Plus className="mr-1.5 h-4 w-4" />{localize(lang, "Добавить SSH-сервер", "Add SSH server")}</Button>
            <Button asChild size="sm" variant="outline"><Link to="/servers" state={{ mainTab: "groups" }}><FolderPlus className="mr-1.5 h-4 w-4" />{localize(lang, "Создать группу", "Create a group")}</Link></Button>
            <Button asChild size="sm" variant="ghost"><Link to="/servers" state={{ mainTab: "rules" }}><ShieldCheck className="mr-1.5 h-4 w-4" />{localize(lang, "Настроить правила", "Configure rules")}</Link></Button>
          </div>
        </div>
      )}
    </div>
  );
}
