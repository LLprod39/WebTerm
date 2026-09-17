import { useMemo, useState, type ReactNode } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity,
  ArrowLeft,
  Brain,
  Copy,
  FileWarning,
  RefreshCw,
  Terminal,
  Sparkles,
} from "lucide-react";

import {
  aiAnalyzeServer,
  fetchAlerts,
  fetchServerDetails,
  fetchServerHealth,
  fetchServerMemoryOverview,
  resolveAlert,
  triggerHealthCheck,
  type FleetHealthStatus,
  type ServerAlertItem,
} from "@/lib/api";
import {
  fetchServerFileSnapshots,
  restoreServerFileSnapshot,
  type ServerFileSnapshot,
} from "@/api/server-snapshots";
import { FleetHealthIndicator } from "@/components/StatusIndicator";
import { Button } from "@/components/ui/button";
import { EmptyState, PageShell, QueryStateBlock, SoftHeader } from "@/components/ui/page-shell";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";
import { formatRelativeTime } from "@/components/studio/StudioActivityText";
import { formatPercent, formatUptime } from "@/pages/monitoring-insights/insights-format";

function formatBytes(size: number): string {
  if (!Number.isFinite(size) || size < 0) return "—";
  if (size < 1024) return `${size} B`;
  if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
  return `${(size / (1024 * 1024)).toFixed(1)} MB`;
}

const FLEET_STATUSES = new Set<FleetHealthStatus>([
  "healthy",
  "warning",
  "critical",
  "unreachable",
  "unknown",
]);

function asFleetStatus(status: string | undefined): FleetHealthStatus {
  if (status && FLEET_STATUSES.has(status as FleetHealthStatus)) {
    return status as FleetHealthStatus;
  }
  return "unknown";
}

function MetricCard({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="rounded-sm border border-border bg-card px-4 py-3">
      <div className="text-[11px] uppercase tracking-wide text-muted-foreground">{label}</div>
      <div className="mt-1 font-mono text-xl tabular-nums text-foreground">{value}</div>
      {hint ? <div className="mt-1 text-xs text-muted-foreground">{hint}</div> : null}
    </div>
  );
}

function Section({
  title,
  description,
  actions,
  children,
}: {
  title: string;
  description?: string;
  actions?: ReactNode;
  children: ReactNode;
}) {
  return (
    <section className="space-y-3 rounded-sm border border-border bg-card p-4 shadow-elev-1 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h2 className="text-sm font-semibold text-foreground">{title}</h2>
          {description ? <p className="text-xs text-muted-foreground">{description}</p> : null}
        </div>
        {actions ? <div className="flex flex-wrap items-center gap-2">{actions}</div> : null}
      </div>
      {children}
    </section>
  );
}

export default function ServerDetailPage() {
  const { id } = useParams<{ id: string }>();
  const serverId = Number(id);
  const validId = Number.isFinite(serverId) && serverId > 0;
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { lang } = useI18n();
  const [analysis, setAnalysis] = useState<string | null>(null);
  const [restorePreview, setRestorePreview] = useState<{ id: number; command: string } | null>(null);

  const detailsQuery = useQuery({
    queryKey: ["servers", "detail", serverId],
    queryFn: () => fetchServerDetails(serverId),
    enabled: validId,
  });

  const healthQuery = useQuery({
    queryKey: ["servers", "health", serverId],
    queryFn: () => fetchServerHealth(serverId, 24),
    enabled: validId,
    refetchInterval: 60_000,
  });

  const alertsQuery = useQuery({
    queryKey: ["servers", "alerts", serverId],
    queryFn: () => fetchAlerts({ server_id: serverId, resolved: false, limit: 20 }),
    enabled: validId,
    refetchInterval: 45_000,
  });

  const snapshotsQuery = useQuery({
    queryKey: ["servers", "file-snapshots", serverId],
    queryFn: () => fetchServerFileSnapshots(serverId, 30),
    enabled: validId,
  });

  const memoryQuery = useQuery({
    queryKey: ["servers", "memory-overview", serverId],
    queryFn: () => fetchServerMemoryOverview(serverId),
    enabled: validId,
    retry: false,
  });

  const healthCheckMutation = useMutation({
    mutationFn: () => triggerHealthCheck(serverId, false),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["servers", "health", serverId] });
      void queryClient.invalidateQueries({ queryKey: ["monitoring", "status"] });
      toast({ description: localize(lang, "Проверка выполнена.", "Health check completed.") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const analyzeMutation = useMutation({
    mutationFn: () => aiAnalyzeServer(serverId),
    onSuccess: (data) => {
      setAnalysis(data.analysis);
      toast({ description: localize(lang, "AI-разбор готов.", "AI analysis ready.") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const resolveMutation = useMutation({
    mutationFn: (alertId: number) => resolveAlert(alertId),
    onSuccess: () => {
      void queryClient.invalidateQueries({ queryKey: ["servers", "alerts", serverId] });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const restoreMutation = useMutation({
    mutationFn: (snapshotId: number) => restoreServerFileSnapshot(serverId, snapshotId),
    onSuccess: (data, snapshotId) => {
      setRestorePreview({ id: snapshotId, command: data.restore_command });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const latest = useMemo(() => {
    const checks = healthQuery.data?.checks ?? [];
    return checks[0] ?? null;
  }, [healthQuery.data?.checks]);

  const history = useMemo(() => {
    return (healthQuery.data?.checks ?? []).slice(0, 12);
  }, [healthQuery.data?.checks]);

  const alerts: ServerAlertItem[] = alertsQuery.data?.alerts ?? [];
  const snapshots: ServerFileSnapshot[] = snapshotsQuery.data?.snapshots ?? [];
  const memoryStats = memoryQuery.data?.stats;

  if (!validId) {
    return (
      <PageShell width="6xl">
        <EmptyState
          title={localize(lang, "Неверный сервер", "Invalid server")}
          description={localize(lang, "В адресе указан некорректный идентификатор.", "The URL has an invalid server id.")}
          actions={
            <Button asChild variant="outline">
              <Link to="/servers">{localize(lang, "К списку", "Back to list")}</Link>
            </Button>
          }
        />
      </PageShell>
    );
  }

  return (
    <PageShell width="6xl">
      <QueryStateBlock
        loading={detailsQuery.isLoading}
        error={detailsQuery.error}
        onRetry={() => void detailsQuery.refetch()}
        loadingText={localize(lang, "Загрузка сервера…", "Loading server…")}
        errorText={localize(lang, "Не удалось загрузить сервер.", "Could not load server.")}
      >
        {detailsQuery.data ? (
          <div className="space-y-5" data-ui-slot="server-detail-page" data-page-kind="server-detail">
            <SoftHeader
              compact
              title={
                <span className="inline-flex items-center gap-2.5">
                  <FleetHealthIndicator
                    status={asFleetStatus(latest?.status)}
                    showLabel={false}
                  />
                  {detailsQuery.data.name}
                </span>
              }
              subtitle={
                <span className="font-mono text-sm">
                  {detailsQuery.data.username}@{detailsQuery.data.host}:{detailsQuery.data.port}
                  {detailsQuery.data.is_shared_server
                    ? ` · ${localize(lang, "общий доступ", "shared")}`
                    : ""}
                </span>
              }
              actions={
                <>
                  <Button variant="outline" size="sm" className="gap-1.5" onClick={() => navigate("/servers")}>
                    <ArrowLeft className="h-3.5 w-3.5" />
                    {localize(lang, "Список", "List")}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    disabled={healthCheckMutation.isPending}
                    onClick={() => healthCheckMutation.mutate()}
                  >
                    <RefreshCw className={`h-3.5 w-3.5 ${healthCheckMutation.isPending ? "animate-spin" : ""}`} />
                    {localize(lang, "Проверить", "Check")}
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    className="gap-1.5"
                    disabled={analyzeMutation.isPending}
                    onClick={() => analyzeMutation.mutate()}
                  >
                    <Sparkles className="h-3.5 w-3.5" />
                    {localize(lang, "AI-разбор", "AI analyze")}
                  </Button>
                  <Button asChild size="sm" className="gap-1.5">
                    <Link to={`/servers/${serverId}/terminal`}>
                      <Terminal className="h-3.5 w-3.5" />
                      {localize(lang, "Терминал", "Terminal")}
                    </Link>
                  </Button>
                </>
              }
            />

            <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
              <MetricCard
                label="CPU"
                value={formatPercent(latest?.cpu_percent ?? null, 1)}
                hint={latest?.checked_at ? formatRelativeTime(latest.checked_at, lang) : undefined}
              />
              <MetricCard
                label={localize(lang, "Память", "Memory")}
                value={formatPercent(latest?.memory_percent ?? null, 1)}
                hint={
                  latest?.memory_used_mb != null && latest?.memory_total_mb != null
                    ? `${Math.round(latest.memory_used_mb)} / ${Math.round(latest.memory_total_mb)} MB`
                    : undefined
                }
              />
              <MetricCard
                label={localize(lang, "Диск", "Disk")}
                value={formatPercent(latest?.disk_percent ?? null, 1)}
                hint={
                  latest?.disk_used_gb != null && latest?.disk_total_gb != null
                    ? `${latest.disk_used_gb.toFixed(1)} / ${latest.disk_total_gb.toFixed(1)} GB`
                    : undefined
                }
              />
              <MetricCard
                label="Load / uptime"
                value={latest?.load_1m != null ? latest.load_1m.toFixed(2) : "—"}
                hint={formatUptime(lang, latest?.uptime_seconds ?? null)}
              />
            </div>

            {analysis ? (
              <Section title={localize(lang, "AI-разбор health", "AI health analysis")}>
                <pre className="max-h-64 overflow-auto whitespace-pre-wrap rounded-sm border border-border bg-surface-2 p-3 text-xs leading-5 text-foreground">
                  {analysis}
                </pre>
              </Section>
            ) : null}

            <Section
              title={localize(lang, "История проверок (24 ч)", "Health history (24h)")}
              description={localize(
                lang,
                "Последние снимки CPU / RAM / disk с сервера.",
                "Recent CPU / RAM / disk samples from this host.",
              )}
            >
              {healthQuery.isLoading ? (
                <p className="text-sm text-muted-foreground">{localize(lang, "Загрузка…", "Loading…")}</p>
              ) : history.length === 0 ? (
                <EmptyState
                  className="py-8"
                  icon={<Activity className="h-5 w-5" />}
                  title={localize(lang, "Пока нет метрик", "No metrics yet")}
                  description={localize(
                    lang,
                    "Нажмите «Проверить», чтобы снять текущие показатели.",
                    "Run a health check to collect the first sample.",
                  )}
                />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full min-w-[560px] text-left text-sm">
                    <thead>
                      <tr className="border-b border-border text-xs text-muted-foreground">
                        <th className="px-2 py-2 font-medium">{localize(lang, "Время", "Time")}</th>
                        <th className="px-2 py-2 font-medium">Status</th>
                        <th className="px-2 py-2 font-medium">CPU</th>
                        <th className="px-2 py-2 font-medium">RAM</th>
                        <th className="px-2 py-2 font-medium">{localize(lang, "Диск", "Disk")}</th>
                        <th className="px-2 py-2 font-medium">Load</th>
                      </tr>
                    </thead>
                    <tbody>
                      {history.map((row) => (
                        <tr key={row.id} className="border-b border-border/60 last:border-0">
                          <td className="px-2 py-2 font-mono text-xs text-muted-foreground">
                            {formatRelativeTime(row.checked_at, lang)}
                          </td>
                          <td className="px-2 py-2">
                            <FleetHealthIndicator
                              status={asFleetStatus(row.status)}
                              showLabel
                            />
                          </td>
                          <td className="px-2 py-2 font-mono tabular-nums">{formatPercent(row.cpu_percent, 0)}</td>
                          <td className="px-2 py-2 font-mono tabular-nums">{formatPercent(row.memory_percent, 0)}</td>
                          <td className="px-2 py-2 font-mono tabular-nums">{formatPercent(row.disk_percent, 0)}</td>
                          <td className="px-2 py-2 font-mono tabular-nums">
                            {row.load_1m != null ? row.load_1m.toFixed(2) : "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Section>

            <Section
              title={localize(lang, "Алерты", "Alerts")}
              description={localize(lang, "Открытые проблемы по этому хосту.", "Open issues for this host.")}
            >
              {alerts.length === 0 ? (
                <p className="text-sm text-muted-foreground">
                  {localize(lang, "Активных алертов нет.", "No active alerts.")}
                </p>
              ) : (
                <ul className="space-y-2">
                  {alerts.map((alert) => (
                    <li
                      key={alert.id}
                      className="flex flex-wrap items-start justify-between gap-3 rounded-sm border border-border bg-surface-2/60 px-3 py-2.5"
                    >
                      <div className="min-w-0 space-y-1">
                        <div className="flex flex-wrap items-center gap-2">
                          <span
                            className={`rounded-sm px-1.5 py-0.5 text-[10px] uppercase ${
                              alert.severity === "critical"
                                ? "bg-danger/10 text-danger"
                                : alert.severity === "warning"
                                  ? "bg-warning/10 text-warning"
                                  : "bg-info/10 text-info"
                            }`}
                          >
                            {alert.severity}
                          </span>
                          <span className="text-sm font-medium text-foreground">{alert.title}</span>
                        </div>
                        <p className="text-xs text-muted-foreground">{alert.message}</p>
                        <p className="font-mono text-[11px] text-muted-foreground">
                          {formatRelativeTime(alert.created_at, lang)}
                        </p>
                      </div>
                      <Button
                        size="xs"
                        variant="outline"
                        disabled={resolveMutation.isPending}
                        onClick={() => resolveMutation.mutate(alert.id)}
                      >
                        {localize(lang, "Снять", "Resolve")}
                      </Button>
                    </li>
                  ))}
                </ul>
              )}
            </Section>

            <Section
              title={localize(lang, "Снимки файлов AI", "AI file snapshots")}
              description={localize(
                lang,
                "Копии файлов до правок агента. Restore отдаёт команду — выполнять её нужно вручную в терминале.",
                "File copies taken before agent edits. Restore returns a shell command — run it manually in the terminal.",
              )}
            >
              {snapshotsQuery.isLoading ? (
                <p className="text-sm text-muted-foreground">{localize(lang, "Загрузка…", "Loading…")}</p>
              ) : snapshots.length === 0 ? (
                <EmptyState
                  className="py-8"
                  icon={<FileWarning className="h-5 w-5" />}
                  title={localize(lang, "Снимков пока нет", "No snapshots yet")}
                  description={localize(
                    lang,
                    "Появятся, когда AI изменит файл на этом сервере.",
                    "They appear when AI modifies a file on this server.",
                  )}
                />
              ) : (
                <div className="space-y-2">
                  {snapshots.map((snap) => (
                    <div
                      key={snap.id}
                      className="flex flex-wrap items-start justify-between gap-3 rounded-sm border border-border px-3 py-2.5"
                    >
                      <div className="min-w-0 space-y-1">
                        <p className="truncate font-mono text-sm text-foreground">{snap.file_path}</p>
                        <p className="truncate text-xs text-muted-foreground">{snap.command}</p>
                        <p className="text-[11px] text-muted-foreground">
                          {formatRelativeTime(snap.created_at, lang)} · {formatBytes(snap.byte_size)}
                          {snap.content_truncated
                            ? ` · ${localize(lang, "обрезан", "truncated")}`
                            : ""}
                          {snap.restored_at
                            ? ` · ${localize(lang, "restore уже запрашивали", "restore already requested")}`
                            : ""}
                        </p>
                      </div>
                      <Button
                        size="xs"
                        variant="outline"
                        disabled={snap.content_truncated || restoreMutation.isPending}
                        onClick={() => restoreMutation.mutate(snap.id)}
                      >
                        {localize(lang, "Restore-команда", "Restore command")}
                      </Button>
                    </div>
                  ))}
                </div>
              )}

              {restorePreview ? (
                <div className="mt-3 space-y-2 rounded-sm border border-border bg-surface-2 p-3">
                  <div className="flex items-center justify-between gap-2">
                    <p className="text-xs font-medium text-foreground">
                      {localize(lang, "Команда восстановления", "Restore command")}
                    </p>
                    <Button
                      size="xs"
                      variant="ghost"
                      className="gap-1"
                      onClick={async () => {
                        try {
                          await navigator.clipboard.writeText(restorePreview.command);
                          toast({
                            description: localize(lang, "Скопировано в буфер.", "Copied to clipboard."),
                          });
                        } catch {
                          toast({
                            variant: "destructive",
                            description: localize(lang, "Не удалось скопировать.", "Copy failed."),
                          });
                        }
                      }}
                    >
                      <Copy className="h-3.5 w-3.5" />
                      {localize(lang, "Копировать", "Copy")}
                    </Button>
                  </div>
                  <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-all font-mono text-[11px] leading-4 text-foreground">
                    {restorePreview.command}
                  </pre>
                </div>
              ) : null}
            </Section>

            <Section
              title={localize(lang, "Память AI", "AI memory")}
              description={localize(
                lang,
                "Краткий статус знаний о сервере (не файловые бэкапы).",
                "Brief status of knowledge about this server (not file backups).",
              )}
              actions={
                <Button asChild size="xs" variant="outline" className="gap-1.5">
                  <Link to="/settings/memory">
                    <Brain className="h-3.5 w-3.5" />
                    {localize(lang, "Открыть память", "Open memory")}
                  </Link>
                </Button>
              }
            >
              {memoryQuery.isError ? (
                <p className="text-sm text-muted-foreground">
                  {localize(
                    lang,
                    "Обзор памяти недоступен для этой роли или сервера.",
                    "Memory overview is unavailable for this role or server.",
                  )}
                </p>
              ) : memoryStats ? (
                <div className="flex flex-wrap gap-3 text-sm">
                  <span className="rounded-sm border border-border px-2.5 py-1">
                    canonical: <span className="font-mono">{memoryStats.canonical}</span>
                  </span>
                  <span className="rounded-sm border border-border px-2.5 py-1">
                    {localize(lang, "заметки", "notes")}:{" "}
                    <span className="font-mono">{memoryStats.manual}</span>
                  </span>
                  <span className="rounded-sm border border-border px-2.5 py-1">
                    {localize(lang, "эпизоды", "episodes")}:{" "}
                    <span className="font-mono">{memoryStats.episodes}</span>
                  </span>
                  <span className="rounded-sm border border-border px-2.5 py-1">
                    {localize(lang, "на проверке", "revalidation")}:{" "}
                    <span className="font-mono">{memoryStats.revalidation_open}</span>
                  </span>
                </div>
              ) : (
                <p className="text-sm text-muted-foreground">{localize(lang, "Загрузка…", "Loading…")}</p>
              )}
            </Section>
          </div>
        ) : null}
      </QueryStateBlock>
    </PageShell>
  );
}
