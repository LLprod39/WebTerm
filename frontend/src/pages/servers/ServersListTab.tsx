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
  Activity,
  Import,
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
import { cn, relativeTime } from "@/lib/utils";
import { resolveServerOs, serverOsLabelKey } from "@/lib/server-os";
import { pushRecentServer } from "@/lib/recent-entities";
import { displayServerGroupName, formatServerCount } from "./formatters";

type MetricLevel = "ok" | "warn" | "crit";

function metricLevel(value: number, warn: number, crit: number): MetricLevel {
  if (value >= crit) return "crit";
  if (value >= warn) return "warn";
  return "ok";
}

// Mirrors warn/crit thresholds in servers/monitor.py.
const METRIC_THRESHOLDS = {
  cpu: { warn: 80, crit: 95 },
  memory: { warn: 85, crit: 95 },
  disk: { warn: 80, crit: 90 },
} as const;

const METRIC_CHIP: Record<MetricLevel, { chip: string; bar: string; value: string }> = {
  ok: {
    chip: "border-border bg-surface-0",
    bar: "bg-primary",
    value: "text-foreground",
  },
  warn: {
    chip: "border-warning/40 bg-warning/10",
    bar: "bg-warning",
    value: "text-warning",
  },
  crit: {
    chip: "border-destructive/40 bg-destructive/10",
    bar: "bg-destructive",
    value: "text-destructive",
  },
};

/** Compact metric chip: label + value + mini fill bar. */
function MetricChip({
  label,
  value,
  warn,
  crit,
}: {
  label: string;
  value: number;
  warn: number;
  crit: number;
}) {
  const level = metricLevel(value, warn, crit);
  const tone = METRIC_CHIP[level];
  const pct = Math.max(0, Math.min(100, Math.round(value)));

  return (
    <span className={cn("inline-flex min-w-[4.25rem] flex-col gap-1 rounded-sm border px-2 py-1", tone.chip)}>
      <span className="flex items-baseline justify-between gap-1.5 leading-none">
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
        <span className={cn("font-mono text-[12px] font-semibold tabular-nums", tone.value)}>{pct}%</span>
      </span>
      <span className="h-1 w-full overflow-hidden rounded-[1px] bg-border/80">
        <span className={cn("block h-full rounded-[1px] transition-[width] duration-300 ease-out", tone.bar)} style={{ width: `${pct}%` }} />
      </span>
    </span>
  );
}

function MetricChipPending({ label }: { label: string }) {
  return (
    <span className="inline-flex min-w-[4.25rem] flex-col gap-1 rounded-sm border border-dashed border-border bg-surface-0 px-2 py-1">
      <span className="flex items-baseline justify-between gap-1.5 leading-none">
        <span className="text-[10px] font-medium uppercase tracking-wide text-muted-foreground">{label}</span>
        <span className="font-mono text-[12px] font-semibold tabular-nums text-muted-foreground/70">—</span>
      </span>
      <span className="h-1 w-full overflow-hidden rounded-[1px] bg-border/60" />
    </span>
  );
}

export function FleetMetricsLine({ health, lang }: { health: MonitoringStatusItem; lang: string }) {
  const items = [
    { label: "CPU", value: health.cpu_percent, ...METRIC_THRESHOLDS.cpu },
    { label: localize(lang, "ОЗУ", "RAM"), value: health.memory_percent, ...METRIC_THRESHOLDS.memory },
    { label: localize(lang, "Диск", "Disk"), value: health.disk_percent, ...METRIC_THRESHOLDS.disk },
  ];

  const known = items.filter((item) => typeof item.value === "number");
  // Keep three slots once we have any metric (or online health) so chips don't pop in one-by-one.
  const showPlaceholders = known.length > 0 || (!health.is_stale && health.status !== "unknown");
  if (!known.length && !showPlaceholders) return null;

  const titleParts = known.map((item) => `${item.label} ${Math.round(item.value as number)}%`);
  if (typeof health.load_1m === "number") titleParts.push(`load ${health.load_1m.toFixed(2)}`);

  return (
    <span className="inline-flex flex-wrap items-center gap-1.5" title={titleParts.join(" · ") || undefined}>
      {items.map((item) =>
        typeof item.value === "number" ? (
          <MetricChip
            key={item.label}
            label={item.label}
            value={item.value}
            warn={item.warn}
            crit={item.crit}
          />
        ) : showPlaceholders ? (
          <MetricChipPending key={item.label} label={item.label} />
        ) : null,
      )}
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
    <div className="space-y-3">
      {groupEntries.map(([group, inGroup]) => {
        const isCollapsed = collapsed[group];
        const groupLabel = displayServerGroupName(group, lang);
        const onlineInGroup = inGroup.filter((server) => {
          const health = fleetHealthByServerId.get(server.id);
          // Bootstrap `server.status` is terminal-session based — do not treat "offline" as health.
          return health ? health.status === "healthy" || health.status === "warning" : false;
        }).length;

        return (
          <section key={group} className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1">
            <button
              onClick={() => onToggleGroup(group)}
              className={cn(
                "flex w-full items-center gap-2.5 border-l-2 border-l-transparent px-3 py-3 text-left transition-colors hover:bg-surface-1 sm:px-4",
                !isCollapsed && "border-b border-border border-l-primary/70 bg-surface-0/40",
              )}
              aria-expanded={!isCollapsed}
              aria-label={tr(isCollapsed ? "srv.expand_group" : "srv.collapse_group", { name: groupLabel })}
            >
              <ChevronRight
                className={cn(
                  "h-4 w-4 shrink-0 text-muted-foreground transition-transform duration-200",
                  !isCollapsed && "rotate-90 text-primary",
                )}
                aria-hidden
              />
              <span className="font-display text-sm font-bold tracking-tight text-foreground">{groupLabel}</span>
              <span className="rounded-sm border border-border bg-surface-0 px-2 py-0.5 font-mono text-2xs tabular-nums text-muted-foreground">
                {formatServerCount(inGroup.length, lang)}
              </span>
              {onlineInGroup > 0 ? (
                <span className="rounded-sm border border-success/30 bg-success/10 px-2 py-0.5 text-2xs font-medium text-success">
                  {onlineInGroup} {localize(lang, "онлайн", "online")}
                </span>
              ) : null}
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
                  <div className="hidden border-b border-border bg-surface-0 px-4 py-2 type-label text-muted-foreground lg:grid lg:grid-cols-[minmax(0,1.35fr)_minmax(9rem,0.85fr)_minmax(14rem,1.15fr)_auto] lg:items-center lg:gap-3">
                    <span>{localize(lang, "Сервер", "Server")}</span>
                    <span>{localize(lang, "Адрес", "Address")}</span>
                    <span>{localize(lang, "Нагрузка", "Load")}</span>
                    <span className="sr-only">{localize(lang, "Действия", "Actions")}</span>
                  </div>

                  <div className="divide-y divide-border">
                    {inGroup.map((server) => {
                      const fleetHealth = fleetHealthByServerId.get(server.id);
                      const osKind = resolveServerOs(server);
                      const address = `${server.host}:${server.port}`;
                      // While monitoring snapshot is not ready, show neutral "unknown"
                      // (bootstrap online/offline is about open terminals, not host health).
                      const statusDot = fleetHealth ? (
                        <FleetHealthIndicator
                          status={
                            fleetHealth.is_stale && fleetHealth.status === "unreachable"
                              ? "unknown"
                              : fleetHealth.status
                          }
                          stale={fleetHealth.is_stale && fleetHealth.status !== "unreachable"}
                          showLabel={false}
                        />
                      ) : (
                        <StatusIndicator status="unknown" showLabel={false} />
                      );

                      const lastConnected = server.last_connected
                        ? relativeTime(server.last_connected)
                        : null;

                      return (
                        <div
                          key={server.id}
                          className="group px-3 py-3 transition-colors hover:bg-surface-1/80 sm:px-4"
                        >
                          <div className="flex items-center gap-3 lg:grid lg:grid-cols-[minmax(0,1.35fr)_minmax(9rem,0.85fr)_minmax(14rem,1.15fr)_auto] lg:items-center lg:gap-3">
                            <div className="flex min-w-0 flex-1 items-center gap-2.5">
                              <Link
                                to={`/monitoring?server=${server.id}`}
                                className="flex shrink-0 items-center rounded-full p-0.5 transition-colors hover:bg-secondary"
                                title={localize(lang, "Insights сервера", "Server insights")}
                                aria-label={localize(lang, "Insights сервера", "Server insights")}
                                onClick={(e) => e.stopPropagation()}
                              >
                                {statusDot}
                              </Link>
                              <ServerOsBadge kind={osKind} size="sm" />
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                                  <span className="text-sm font-semibold leading-5 text-foreground">{server.name}</span>
                                  {server.is_shared ? (
                                    <span className="rounded-sm border border-border bg-surface-0 px-1.5 py-0.5 text-2xs font-semibold uppercase tracking-wide text-muted-foreground">
                                      {t("srv.shared_badge")}
                                    </span>
                                  ) : null}
                                </div>
                                <p className="mt-0.5 truncate font-mono text-xs text-muted-foreground lg:hidden">
                                  {address}
                                  <span className="ml-2 font-sans text-muted-foreground/70">{t(serverOsLabelKey(osKind))}</span>
                                </p>
                                {lastConnected ? (
                                  <p className="mt-0.5 text-[11px] text-muted-foreground/80">
                                    {localize(lang, "Подключение", "Last connect")}: {lastConnected}
                                  </p>
                                ) : null}
                                {fleetHealth ? (
                                  <div className="mt-2 sm:hidden">
                                    <FleetMetricsLine health={fleetHealth} lang={lang} />
                                  </div>
                                ) : null}
                              </div>
                            </div>

                            <div className="hidden min-w-0 lg:block">
                              <p className="truncate font-mono text-[13px] leading-5 text-foreground/80">{address}</p>
                              <p className="mt-0.5 truncate text-xs text-muted-foreground">{t(serverOsLabelKey(osKind))}</p>
                            </div>

                            <div className="hidden min-w-0 items-center sm:flex">
                              {fleetHealth ? (
                                <FleetMetricsLine health={fleetHealth} lang={lang} />
                              ) : (
                                <span className="rounded-sm border border-dashed border-border px-2.5 py-1.5 font-mono text-2xs text-muted-foreground">
                                  {localize(lang, "нет данных", "no data")}
                                </span>
                              )}
                            </div>

                            <div className="flex shrink-0 items-center gap-1">
                              <Button
                                asChild
                                size="sm"
                                className="h-8 gap-1.5 shadow-elev-1"
                              >
                                <Link
                                  to={`/servers/${server.id}/terminal`}
                                  onClick={() =>
                                    pushRecentServer({
                                      id: server.id,
                                      name: server.name,
                                      host: server.host,
                                    })
                                  }
                                >
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
        totalServers ? (
          <EmptyState
            icon={<Server className="h-5 w-5" />}
            title={t("srv.empty_filtered_title")}
            description={t("srv.empty_filtered_text")}
            actions={
              <>
                <Button size="sm" variant="outline" onClick={onClearSearch}>
                  {t("srv.clear_search")}
                </Button>
                <Button size="sm" className="gap-1.5" onClick={onOpenCreate}>
                  <Plus className="h-4 w-4" /> {t("srv.add")}
                </Button>
              </>
            }
          />
        ) : (
          <div className="workspace-empty space-y-4 rounded-sm border border-dashed border-border bg-card/50 px-6 py-10">
            <div className="text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-sm border border-border bg-surface-2 text-muted-foreground">
                <Server className="h-5 w-5" />
              </div>
              <h3 className="text-sm font-semibold text-foreground">{t("srv.empty_title")}</h3>
              <p className="mx-auto mt-1 max-w-md text-xs leading-5 text-muted-foreground">{t("srv.empty_text")}</p>
            </div>
            <div className="mx-auto grid max-w-2xl gap-2 sm:grid-cols-3">
              <button
                type="button"
                onClick={onOpenCreate}
                className="rounded-lg border border-border bg-card px-3 py-3 text-left transition-colors hover:border-border-strong hover:bg-surface-1"
              >
                <Plus className="mb-2 h-4 w-4 text-primary" />
                <div className="text-sm font-medium text-foreground">
                  {localize(lang, "Добавить SSH-сервер", "Add SSH server")}
                </div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {localize(lang, "Хост, порт, ключ или пароль", "Host, port, key or password")}
                </div>
              </button>
              <Link
                to="/servers"
                state={{ mainTab: "groups" }}
                className="rounded-lg border border-border bg-card px-3 py-3 text-left transition-colors hover:border-border-strong hover:bg-surface-1"
              >
                <Import className="mb-2 h-4 w-4 text-info" />
                <div className="text-sm font-medium text-foreground">
                  {localize(lang, "Импорт из группы", "Import from group")}
                </div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {localize(lang, "Общий доступ и роли", "Shared access and roles")}
                </div>
              </Link>
              <Link
                to="/monitoring"
                className="rounded-lg border border-border bg-card px-3 py-3 text-left transition-colors hover:border-border-strong hover:bg-surface-1"
              >
                <Activity className="mb-2 h-4 w-4 text-success" />
                <div className="text-sm font-medium text-foreground">
                  {localize(lang, "Открыть Insights", "Open Insights")}
                </div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {localize(lang, "Когда флот уже есть", "When the fleet already exists")}
                </div>
              </Link>
            </div>
          </div>
        )
      ) : null}
    </div>
  );
}
