import { Link } from "react-router-dom";
import { AnimatePresence, motion } from "framer-motion";
import {
  ChevronRight,
  MoreHorizontal,
  Plus,
  Server,
  Settings,
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
import { displayServerGroupName, formatServerCount } from "./formatters";

function metricToneClass(value: number, warn: number, crit: number): string {
  if (value >= crit) return "text-destructive font-semibold";
  if (value >= warn) return "text-warning";
  return "text-muted-foreground/70";
}

function formatMetricsAge(seconds: number, lang: string): string {
  if (seconds < 90) return localize(lang, `${seconds} с назад`, `${seconds}s ago`);
  const minutes = Math.round(seconds / 60);
  if (minutes < 90) return localize(lang, `${minutes} мин назад`, `${minutes}m ago`);
  const hours = Math.round(minutes / 60);
  return localize(lang, `${hours} ч назад`, `${hours}h ago`);
}

// Mirrors warn/crit thresholds in servers/monitor.py.
const METRIC_THRESHOLDS = {
  cpu: { warn: 80, crit: 95 },
  memory: { warn: 85, crit: 95 },
  disk: { warn: 80, crit: 90 },
} as const;

export function FleetMetricsLine({ health, lang }: { health: MonitoringStatusItem; lang: string }) {
  const items = [
    { label: "CPU", value: health.cpu_percent, ...METRIC_THRESHOLDS.cpu },
    { label: localize(lang, "ОЗУ", "RAM"), value: health.memory_percent, ...METRIC_THRESHOLDS.memory },
    { label: localize(lang, "Диск", "Disk"), value: health.disk_percent, ...METRIC_THRESHOLDS.disk },
  ].filter((item) => typeof item.value === "number") as Array<{
    label: string;
    value: number;
    warn: number;
    crit: number;
  }>;

  if (!items.length) return null;

  const age = health.metrics_age_seconds ?? null;
  const outdated = age !== null && age > 600;
  const titleParts = items.map((item) => `${item.label} ${Math.round(item.value)}%`);
  if (typeof health.load_1m === "number") titleParts.push(`load ${health.load_1m.toFixed(2)}`);
  if (age === 0) {
    titleParts.push(localize(lang, "живые данные", "live"));
  } else if (age !== null) {
    titleParts.push(localize(lang, `обновлено ${formatMetricsAge(age, lang)}`, `updated ${formatMetricsAge(age, lang)}`));
  }

  return (
    <span
      className={cn(
        "flex items-center gap-1 font-mono text-2xs tabular-nums leading-none",
        outdated && "opacity-50",
      )}
      title={titleParts.join(" · ")}
    >
      {items.map((item, idx) => (
        <span key={item.label} className="flex items-center gap-1">
          {idx > 0 ? <span className="text-muted-foreground/40">·</span> : null}
          <span className={metricToneClass(item.value, item.warn, item.crit)}>
            {item.label} {Math.round(item.value)}%
          </span>
        </span>
      ))}
    </span>
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
  onClearSearch: () => void;
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
  onClearSearch,
}: ServersListTabProps) {
  const groupEntries = Object.entries(grouped);

  return (
    <div className="space-y-2.5">
      {groupEntries.map(([group, inGroup]) => {
        const isCollapsed = collapsed[group];
        const groupLabel = displayServerGroupName(group, lang);
        const onlineInGroup = inGroup.filter((server) => {
          const health = fleetHealthByServerId.get(server.id);
          return health ? health.status === "healthy" : server.status === "online";
        }).length;

        return (
          <section key={group} className="overflow-hidden rounded-xl border border-border/50 bg-surface-1/60 shadow-elev-1">
            <button
              onClick={() => onToggleGroup(group)}
              className={cn(
                "flex w-full items-center gap-2.5 px-3 py-2.5 text-left transition-colors hover:bg-surface-2/50 sm:px-4",
                !isCollapsed && "border-b border-border/50",
              )}
              aria-expanded={!isCollapsed}
              aria-label={tr(isCollapsed ? "srv.expand_group" : "srv.collapse_group", { name: groupLabel })}
            >
              <ChevronRight
                className={cn(
                  "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
                  !isCollapsed && "rotate-90",
                )}
                aria-hidden
              />
              <span className="text-sm font-semibold text-foreground">{groupLabel}</span>
              <span className="text-xs text-muted-foreground">
                {formatServerCount(inGroup.length, lang)}
                {onlineInGroup > 0 ? (
                  <span className="text-success"> · {onlineInGroup} {localize(lang, "онлайн", "online")}</span>
                ) : null}
              </span>
            </button>

            <AnimatePresence initial={false}>
              {!isCollapsed && (
                <motion.div
                  initial={{ height: 0, opacity: 0 }}
                  animate={{ height: "auto", opacity: 1 }}
                  exit={{ height: 0, opacity: 0 }}
                  transition={{ duration: 0.18 }}
                  className="overflow-hidden"
                >
                  {/* Column headers on wide screens */}
                  <div className="hidden border-b border-border/40 bg-surface-2/30 px-4 py-2 text-2xs font-semibold uppercase tracking-wide text-muted-foreground/70 lg:grid lg:grid-cols-[minmax(0,1.4fr)_minmax(10rem,1fr)_minmax(7rem,0.7fr)_auto] lg:items-center lg:gap-3">
                    <span>{localize(lang, "Сервер", "Server")}</span>
                    <span>{localize(lang, "Адрес", "Address")}</span>
                    <span>{localize(lang, "Статус", "Status")}</span>
                    <span className="sr-only">{localize(lang, "Действия", "Actions")}</span>
                  </div>

                  <div className="divide-y divide-border/40">
                    {inGroup.map((server) => {
                      const fleetHealth = fleetHealthByServerId.get(server.id);
                      const osKind = resolveServerOs(server);
                      const address = `${server.host}:${server.port}`;

                      return (
                        <div
                          key={server.id}
                          className="group px-3 py-2.5 transition-colors hover:bg-surface-2/40 sm:px-4"
                        >
                          <div className="flex items-center gap-2.5 lg:grid lg:grid-cols-[minmax(0,1.4fr)_minmax(10rem,1fr)_minmax(7rem,0.7fr)_auto] lg:gap-3">
                            <div className="flex min-w-0 flex-1 items-center gap-2.5">
                              <ServerOsBadge kind={osKind} size="sm" />
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                                  <span className="text-sm font-semibold leading-5 text-foreground">{server.name}</span>
                                  {server.is_shared ? (
                                    <span className="text-2xs font-semibold uppercase tracking-wide text-muted-foreground/70">
                                      {t("srv.shared_badge")}
                                    </span>
                                  ) : null}
                                </div>
                                <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground/80 lg:hidden">
                                  {address}
                                  <span className="ml-2 font-sans text-muted-foreground/60">{t(serverOsLabelKey(osKind))}</span>
                                </p>
                              </div>
                            </div>

                            <div className="hidden min-w-0 lg:block">
                              <p className="truncate font-mono text-[13px] leading-4 text-muted-foreground">{address}</p>
                              <p className="mt-0.5 truncate text-xs text-muted-foreground/60">{t(serverOsLabelKey(osKind))}</p>
                            </div>

                            <div className="hidden shrink-0 flex-col items-start gap-1 sm:flex">
                              {fleetHealth ? (
                                <FleetHealthIndicator status={fleetHealth.status} stale={fleetHealth.is_stale} showLabel />
                              ) : (
                                <StatusIndicator status={server.status} showLabel />
                              )}
                              {fleetHealth ? <FleetMetricsLine health={fleetHealth} lang={lang} /> : null}
                            </div>

                            <div className="flex shrink-0 items-center gap-0.5">
                              <Button
                                asChild
                                size="sm"
                                variant="outline"
                                className="h-8 gap-1.5 hover:border-primary hover:text-primary"
                              >
                                <Link to={`/servers/${server.id}/terminal`}>
                                  <Terminal className="h-3.5 w-3.5" /> SSH
                                </Link>
                              </Button>
                              <DropdownMenu>
                                <DropdownMenuTrigger asChild>
                                  <Button
                                    size="icon"
                                    variant="ghost"
                                    className="h-8 w-8 text-muted-foreground hover:text-foreground"
                                    aria-label={tr("srv.open_advanced_for", { name: server.name })}
                                  >
                                    <MoreHorizontal className="h-4 w-4" />
                                  </Button>
                                </DropdownMenuTrigger>
                                <DropdownMenuContent align="end" className="w-52">
                                  <DropdownMenuItem onClick={() => void onOpenAdvanced(server)} className="gap-2">
                                    <SlidersHorizontal className="h-3.5 w-3.5" /> {t("srv.advanced")}
                                  </DropdownMenuItem>
                                  {server.can_edit ? (
                                    <>
                                      <DropdownMenuItem onClick={() => void onOpenEdit(server)} className="gap-2">
                                        <Settings className="h-3.5 w-3.5" /> {t("srv.edit_server")}
                                      </DropdownMenuItem>
                                      <DropdownMenuSeparator />
                                      <DropdownMenuItem
                                        onClick={() => onRequestDeleteServer(server)}
                                        className="gap-2 text-destructive focus:text-destructive"
                                      >
                                        <Trash2 className="h-3.5 w-3.5" /> {t("srv.delete")}
                                      </DropdownMenuItem>
                                    </>
                                  ) : null}
                                </DropdownMenuContent>
                              </DropdownMenu>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </motion.div>
              )}
            </AnimatePresence>
          </section>
        );
      })}

      {!filteredCount ? (
        <EmptyState
          icon={<Server className="h-5 w-5" />}
          title={totalServers ? t("srv.empty_filtered_title") : t("srv.empty_title")}
          description={totalServers ? t("srv.empty_filtered_text") : t("srv.empty_text")}
          actions={
            <>
              {totalServers ? (
                <Button size="sm" variant="outline" onClick={onClearSearch}>
                  {t("srv.clear_search")}
                </Button>
              ) : null}
              <Button size="sm" className="gap-1.5" onClick={onOpenCreate}>
                <Plus className="h-4 w-4" /> {t("srv.add")}
              </Button>
            </>
          }
        />
      ) : null}
    </div>
  );
}
