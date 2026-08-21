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
  FolderPlus,
  ShieldCheck,
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

function formatLastConnection(iso: string, lang: string) {
  const timestamp = new Date(iso).getTime();
  if (!Number.isFinite(timestamp)) return localize(lang, "время неизвестно", "time unknown");

  const minutes = Math.max(0, Math.floor((Date.now() - timestamp) / 60_000));
  if (minutes < 1) return localize(lang, "только что", "just now");
  if (minutes < 60) return localize(lang, `${minutes} мин назад`, `${minutes}m ago`);

  const hours = Math.floor(minutes / 60);
  if (hours < 24) return localize(lang, `${hours} ч назад`, `${hours}h ago`);

  const days = Math.floor(hours / 24);
  return localize(lang, `${days} дн назад`, `${days}d ago`);
}

const METRIC_GAUGE: Record<MetricLevel, { bar: string; value: string }> = {
  ok: {
    bar: "bg-info",
    value: "text-foreground",
  },
  warn: {
    bar: "bg-warning",
    value: "text-warning",
  },
  crit: {
    bar: "bg-destructive",
    value: "text-destructive",
  },
};

/** Quiet, table-friendly metric gauge with the same thresholds as monitoring. */
function MetricGauge({
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
  const tone = METRIC_GAUGE[level];
  const pct = Math.max(0, Math.min(100, Math.round(value)));

  return (
    <span className="inline-flex min-w-[4.25rem] flex-1 flex-col gap-1">
      <span className="flex items-baseline justify-between gap-2 leading-none">
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">{label}</span>
        <span className={cn("font-mono text-[11px] font-semibold tabular-nums", tone.value)}>{pct}%</span>
      </span>
      <span className="h-1 w-full overflow-hidden rounded-full bg-border/70">
        <span className={cn("block h-full rounded-full transition-[width] duration-300 ease-out", tone.bar)} style={{ width: `${pct}%` }} />
      </span>
    </span>
  );
}

function MetricGaugePending({ label }: { label: string }) {
  return (
    <span className="inline-flex min-w-[4.25rem] flex-1 flex-col gap-1">
      <span className="flex items-baseline justify-between gap-2 leading-none">
        <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">{label}</span>
        <span className="font-mono text-[11px] font-semibold tabular-nums text-muted-foreground/60">—</span>
      </span>
      <span className="h-1 w-full overflow-hidden rounded-full bg-border/50" />
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
  // Keep three slots once we have any metric so the table does not jump as checks arrive.
  const showPlaceholders = known.length > 0 || (!health.is_stale && health.status !== "unknown");
  if (!known.length && !showPlaceholders) return null;

  const titleParts = known.map((item) => `${item.label} ${Math.round(item.value as number)}%`);
  if (typeof health.load_1m === "number") titleParts.push(`load ${health.load_1m.toFixed(2)}`);

  return (
    <span className="flex w-full min-w-0 items-center gap-2.5" title={titleParts.join(" · ") || undefined}>
      {items.map((item) =>
        typeof item.value === "number" ? (
          <MetricGauge
            key={item.label}
            label={item.label}
            value={item.value}
            warn={item.warn}
            crit={item.crit}
          />
        ) : showPlaceholders ? (
          <MetricGaugePending key={item.label} label={item.label} />
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
    <div className="space-y-2">
      {groupEntries.map(([group, inGroup]) => {
        const isCollapsed = collapsed[group];
        const groupLabel = displayServerGroupName(group, lang);
        const healthyInGroup = inGroup.filter((server) => {
          const health = fleetHealthByServerId.get(server.id);
          return health ? !health.is_stale && health.status === "healthy" : false;
        }).length;
        const attentionInGroup = Math.max(0, inGroup.length - healthyInGroup);

        return (
          <section key={group} className="overflow-hidden rounded-lg border border-border bg-card shadow-elev-1">
            <button
              onClick={() => onToggleGroup(group)}
              className={cn(
                "flex w-full items-center gap-2 px-3.5 py-2.5 text-left transition-colors hover:bg-surface-1",
                !isCollapsed && "border-b border-border bg-surface-0/55",
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
              <span className="font-display text-[13px] font-bold tracking-[-0.01em] text-foreground">{groupLabel}</span>
              <span className="rounded-full border border-border bg-card px-2 py-0.5 text-[11px] tabular-nums text-muted-foreground">
                {formatServerCount(inGroup.length, lang)}
              </span>
              {healthyInGroup > 0 ? (
                <span className="rounded-full border border-success/25 bg-success/[0.08] px-2 py-0.5 text-[11px] font-medium text-success">
                  {healthyInGroup} {localize(lang, "в норме", "healthy")}
                </span>
              ) : null}
              {attentionInGroup > 0 ? (
                <span className="rounded-full border border-warning/25 bg-warning/[0.08] px-2 py-0.5 text-[11px] font-medium text-warning">
                  {localize(lang, "Требуют внимания", "Needs attention")}: {attentionInGroup}
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
                  <div className="hidden border-b border-border bg-surface-0/70 px-3.5 py-2 text-[11px] font-semibold uppercase tracking-[0.09em] text-muted-foreground lg:grid lg:grid-cols-[minmax(0,1.25fr)_minmax(8.5rem,0.75fr)_minmax(13.5rem,1fr)_auto] lg:items-center lg:gap-3.5">
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
                        ? formatLastConnection(server.last_connected, lang)
                        : null;
                      const osLabel = server.detected_os_pretty || t(serverOsLabelKey(osKind));

                      return (
                        <div
                          key={server.id}
                          className="group px-3.5 py-2.5 transition-colors hover:bg-surface-1/80"
                        >
                          <div className="flex items-center gap-2.5 lg:grid lg:grid-cols-[minmax(0,1.25fr)_minmax(8.5rem,0.75fr)_minmax(13.5rem,1fr)_auto] lg:items-center lg:gap-3.5">
                            <div className="flex min-w-0 flex-1 items-center gap-2">
                              <Link
                                to={`/monitoring?server=${server.id}`}
                                className="flex shrink-0 items-center rounded-full p-0.5 transition-colors hover:bg-secondary"
                                title={localize(lang, "Мониторинг сервера", "Server monitoring")}
                                aria-label={localize(lang, "Мониторинг сервера", "Server monitoring")}
                                onClick={(e) => e.stopPropagation()}
                              >
                                {statusDot}
                              </Link>
                              <ServerOsBadge kind={osKind} size="xs" />
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                                  <Link
                                    to={`/monitoring?server=${server.id}`}
                                    className="text-[13px] font-semibold leading-5 text-foreground underline-offset-4 transition-colors hover:text-primary hover:underline"
                                    title={localize(lang, "Открыть мониторинг сервера", "Open server monitoring")}
                                  >
                                    {server.name}
                                  </Link>
                                  {server.is_shared ? (
                                    <span className="rounded-full border border-info/20 bg-info/[0.06] px-2 py-0.5 text-[10px] font-medium text-info">
                                      {t("srv.shared_badge")}
                                    </span>
                                  ) : null}
                                </div>
                                <p className="mt-0.5 truncate font-mono text-[11px] text-muted-foreground lg:hidden">
                                  {address}
                                  <span className="ml-2 font-sans text-muted-foreground/70">{osLabel}</span>
                                </p>
                                {lastConnected ? (
                                  <p className="mt-0.5 text-[11px] text-muted-foreground/80">
                                    {localize(lang, "Последнее подключение", "Last connected")}: {lastConnected}
                                  </p>
                                ) : null}
                                {fleetHealth ? (
                                  <div className="mt-3 sm:hidden">
                                    <FleetMetricsLine health={fleetHealth} lang={lang} />
                                  </div>
                                ) : null}
                              </div>
                            </div>

                            <div className="hidden min-w-0 lg:block">
                              <p className="truncate font-mono text-[11px] leading-4 text-foreground/85">{address}</p>
                              <p className="mt-0.5 truncate text-[11px] text-muted-foreground">
                                {server.username} · {osLabel}
                              </p>
                            </div>

                            <div className="hidden min-w-0 items-center sm:flex">
                              {fleetHealth ? (
                                <FleetMetricsLine health={fleetHealth} lang={lang} />
                              ) : (
                                <span className="text-xs text-muted-foreground">
                                  {localize(lang, "нет данных", "no data")}
                                </span>
                              )}
                            </div>

                            <div className="flex shrink-0 items-center gap-1">
                              <Button
                                asChild
                                size="sm"
                                variant="outline"
                                className="h-7 gap-1.5 rounded-md bg-card px-2.5 text-xs shadow-none hover:border-primary/30 hover:bg-primary/[0.04] hover:text-primary"
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
                                    className="h-7 w-7 rounded-md text-muted-foreground hover:text-foreground"
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
                <Button size="sm" variant="outline" onClick={onClearFilters}>
                  {localize(lang, "Сбросить фильтры", "Reset filters")}
                </Button>
                <Button size="sm" className="gap-1.5" onClick={onOpenCreate}>
                  <Plus className="h-4 w-4" /> {t("srv.add")}
                </Button>
              </>
            }
          />
        ) : (
          <div className="workspace-empty space-y-5 rounded-xl border border-dashed border-border bg-card/50 px-6 py-12">
            <div className="text-center">
              <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-xl border border-border bg-surface-2 text-muted-foreground">
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
                <FolderPlus className="mb-2 h-4 w-4 text-info" />
                <div className="text-sm font-medium text-foreground">
                  {localize(lang, "Создать группу", "Create a group")}
                </div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {localize(lang, "Общие правила и доступ", "Shared rules and access")}
                </div>
              </Link>
              <Link
                to="/servers"
                state={{ mainTab: "rules" }}
                className="rounded-lg border border-border bg-card px-3 py-3 text-left transition-colors hover:border-border-strong hover:bg-surface-1"
              >
                <ShieldCheck className="mb-2 h-4 w-4 text-success" />
                <div className="text-sm font-medium text-foreground">
                  {localize(lang, "Настроить правила", "Configure rules")}
                </div>
                <div className="mt-0.5 text-[11px] text-muted-foreground">
                  {localize(lang, "Единые ограничения доступа", "Consistent access guardrails")}
                </div>
              </Link>
            </div>
          </div>
        )
      ) : null}
    </div>
  );
}
