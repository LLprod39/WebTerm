import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState, useMemo } from "react";
import {
  fetchAdminDashboard,
  fetchAdminUsersSessions,
  type AdminDashboardData,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  Users,
  Server,
  Bot,
  Terminal,
  DollarSign,
  RefreshCw,
  TrendingUp,
  CalendarIcon,
  AlertTriangle,
  Activity,
  CheckCircle2,
} from "lucide-react";
import { format, subDays } from "date-fns";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { cn } from "@/lib/utils";
import { EmptyState, MetricCard, MetricGrid, PageHero, PageShell, QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";

function relativeTime(iso: string | null | undefined): string {
  if (!iso) return "—";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

const DATE_PRESET_KEYS = [
  { labelKey: "adash.preset_today", days: 0 },
  { labelKey: "adash.preset_7d", days: 7 },
  { labelKey: "adash.preset_14d", days: 14 },
  { labelKey: "adash.preset_30d", days: 30 },
];

function severityTone(severity: string): "success" | "warning" | "danger" | "neutral" {
  const normalized = severity.toLowerCase();
  if (normalized.includes("critical") || normalized.includes("error")) return "danger";
  if (normalized.includes("warn")) return "warning";
  if (normalized.includes("ok") || normalized.includes("healthy")) return "success";
  return "neutral";
}

export default function AdminDashboard() {
  const { t } = useI18n();
  const DATE_PRESETS = DATE_PRESET_KEYS.map((p) => ({ label: t(p.labelKey), days: p.days }));
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<"activity" | "users" | "api">("activity");
  const [activityPreset, setActivityPreset] = useState(0);
  const [dateFrom, setDateFrom] = useState<Date | undefined>(new Date());
  const [dateTo, setDateTo] = useState<Date | undefined>(new Date());

  const { data: dashData, isLoading } = useQuery({
    queryKey: ["admin", "dashboard"],
    queryFn: fetchAdminDashboard,
    refetchInterval: 15_000,
  });

  const { data: sessionsData } = useQuery({
    queryKey: ["admin", "sessions"],
    queryFn: fetchAdminUsersSessions,
    refetchInterval: 30_000,
  });

  // Filter activity by date
  const filteredActivity = useMemo(() => {
    if (!dashData?.data) return [];
    let items = dashData.data.recent_activity || [];
    if (dateFrom) {
      const from = dateFrom.getTime();
      items = items.filter((a) => a.time && new Date(a.time).getTime() >= from);
    }
    if (dateTo) {
      const to = dateTo.getTime() + 86400000;
      items = items.filter((a) => a.time && new Date(a.time).getTime() <= to);
    }
    return items;
  }, [dashData, dateFrom, dateTo]);

  if (isLoading || !dashData?.data) {
    return <QueryStateBlock loading={isLoading} className="p-6">{null}</QueryStateBlock>;
  }

  const d: AdminDashboardData = dashData.data;
  const sessions = sessionsData?.sessions || [];
  const totalCost = Object.values(d.api_usage).reduce((s, u) => s + (u.cost_usd || 0), 0);

  const hourlyData = (d.hourly_activity || []).map((h) => ({
    hour: new Date(h.hour).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" }),
    count: h.count,
  }));

  const refresh = () => queryClient.invalidateQueries({ queryKey: ["admin"] });

  const METRICS = [
    {
      label: t("adash.users_online"),
      value: d.online_users.count,
      description: `${d.online_users.total_registered} ${t("adash.registered")}`,
      icon: <Users className="h-4 w-4" />,
      tone: "info" as const,
    },
    {
      label: t("adash.servers"),
      value: d.servers.active,
      description: `${d.servers.total} ${t("adash.total")}`,
      icon: <Server className="h-4 w-4" />,
      tone: d.active_alerts_count > 0 ? "warning" as const : "default" as const,
    },
    {
      label: t("adash.ai_requests"),
      value: d.ai.requests_today,
      description: t("adash.today"),
      icon: <Bot className="h-4 w-4" />,
      tone: "default" as const,
    },
    {
      label: t("adash.terminals"),
      value: d.terminals.active,
      description: t("adash.active_now"),
      icon: <Terminal className="h-4 w-4" />,
      tone: d.terminals.active > 0 ? "success" as const : "default" as const,
    },
    {
      label: t("adash.api_cost"),
      value: `$${totalCost.toFixed(2)}`,
      description: `${d.api_calls_today} ${t("adash.calls")}`,
      icon: <DollarSign className="h-4 w-4" />,
      tone: "default" as const,
    },
  ];

  return (
    <PageShell width="7xl">
      <PageHero
        kicker={`WEU AI · v${d.app_version}`}
        title={t("dashboard.admin.title")}
        description={t("dashboard.admin.subtitle")}
        actions={
          <>
            <StatusBadge
              label={d.active_alerts_count > 0 ? `${d.active_alerts_count} ${t("adash.alerts")}` : t("adash.no_alerts")}
              tone={d.active_alerts_count > 0 ? "warning" : "success"}
            />
            <Button size="sm" variant="outline" className="gap-1.5" onClick={refresh}>
              <RefreshCw className="h-3.5 w-3.5" /> {t("udash.refresh")}
            </Button>
          </>
        }
      />

      <MetricGrid className="xl:grid-cols-5">
        {METRICS.map((m) => (
          <MetricCard key={m.label} label={m.label} value={m.value} description={m.description} icon={m.icon} tone={m.tone} />
        ))}
      </MetricGrid>

      <div className="grid gap-4 lg:grid-cols-[minmax(0,1.2fr)_minmax(320px,0.8fr)]">
        <SectionCard
          title={t("adash.fleet_health")}
          description={`${t("adash.avg_cpu")}: ${Math.round(d.fleet_health.avg_cpu)}% · ${t("adash.avg_memory")}: ${Math.round(d.fleet_health.avg_memory)}% · ${t("adash.avg_disk")}: ${Math.round(d.fleet_health.avg_disk)}%`}
          icon={<Activity className="h-4 w-4" />}
          bodyClassName="grid gap-3 sm:grid-cols-4"
        >
          {[
            { label: t("udash.healthy"), value: d.fleet_health.healthy, tone: "success" as const, icon: CheckCircle2 },
            { label: t("udash.warning"), value: d.fleet_health.warning, tone: "warning" as const, icon: AlertTriangle },
            { label: t("udash.critical"), value: d.fleet_health.critical, tone: "danger" as const, icon: AlertTriangle },
            { label: t("udash.unreachable"), value: d.fleet_health.unreachable, tone: "default" as const, icon: Server },
          ].map((item) => (
            <MetricCard
              key={item.label}
              label={item.label}
              value={item.value}
              description={item.value === 1 ? "server" : "servers"}
              icon={<item.icon className="h-4 w-4" />}
              tone={item.tone}
            />
          ))}
        </SectionCard>

        <SectionCard
          title={t("adash.online_users")}
          description={`${sessions.length} active · ${sessionsData?.active_today || 0} today`}
          icon={<Users className="h-4 w-4" />}
          bodyClassName="space-y-2"
        >
          {sessions.length === 0 ? (
            <EmptyState
              icon={<Users className="h-5 w-5" />}
              title={t("adash.no_users_online")}
              description="Новые сессии появятся здесь после входа пользователей."
              className="py-8"
            />
          ) : (
            <div className="space-y-2 max-h-72 overflow-y-auto pr-1">
              {sessions.map((s) => (
                <div key={s.user_id} className="flex items-center gap-3 rounded-lg border border-border/60 bg-secondary/30 px-3 py-2">
                  <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-primary/10 text-xs font-semibold text-primary">
                    {s.username.slice(0, 1).toUpperCase()}
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="truncate text-sm font-medium">{s.username}</span>
                      {s.is_staff ? <StatusBadge label="admin" tone="info" dot={false} /> : null}
                    </div>
                    <div className="truncate text-xs text-muted-foreground">{s.last_action || s.last_category || "active"}</div>
                  </div>
                  <div className="flex shrink-0 items-center gap-2 text-xs text-muted-foreground">
                    {s.active_terminals > 0 ? <StatusBadge label={`${s.active_terminals} tty`} tone="success" /> : null}
                    <span>{relativeTime(s.last_activity)}</span>
                  </div>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      {hourlyData.length > 0 && (
        <SectionCard title={t("adash.hourly_activity")} icon={<TrendingUp className="h-4 w-4" />} bodyClassName="pt-4">
          <div className="h-44">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={hourlyData}>
                <XAxis dataKey="hour" tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 10, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} width={28} />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "8px",
                    fontSize: "12px",
                    padding: "6px 10px",
                  }}
                />
                <Bar dataKey="count" fill="hsl(var(--primary))" radius={[4, 4, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </SectionCard>
      )}

      <SectionCard
        title={tab === "activity" ? t("adash.activity_feed") : tab === "users" ? t("adash.top_users") : t("adash.api_usage")}
        icon={tab === "activity" ? <Activity className="h-4 w-4" /> : tab === "users" ? <Users className="h-4 w-4" /> : <DollarSign className="h-4 w-4" />}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <div className="inline-flex rounded-lg border border-border bg-background p-1">
              {(["activity", "users", "api"] as const).map((t2) => (
                <button
                  key={t2}
                  type="button"
                  onClick={() => setTab(t2)}
                  className={cn(
                    "rounded-md px-3 py-1.5 text-xs font-medium transition-colors",
                    tab === t2 ? "bg-secondary text-foreground" : "text-muted-foreground hover:text-foreground",
                  )}
                >
                  {t2 === "activity" ? t("adash.activity_feed") : t2 === "users" ? t("adash.top_users") : t("adash.api_usage")}
                </button>
              ))}
            </div>
            {tab === "activity" ? (
              <div className="flex flex-wrap items-center gap-1.5">
                {DATE_PRESETS.map((preset) => (
                  <Button
                    key={preset.days}
                    size="sm"
                    variant={activityPreset === preset.days ? "default" : "outline"}
                    className="h-8 text-xs"
                    onClick={() => {
                      setActivityPreset(preset.days);
                      setDateFrom(subDays(new Date(), preset.days));
                      setDateTo(new Date());
                    }}
                  >
                    {preset.label}
                  </Button>
                ))}
                <Popover>
                  <PopoverTrigger asChild>
                    <Button variant="outline" size="sm" className="h-8 gap-1 text-xs">
                      <CalendarIcon className="h-3.5 w-3.5" />
                      {dateFrom ? format(dateFrom, "dd.MM") : "От"}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="end">
                    <Calendar mode="single" selected={dateFrom} onSelect={setDateFrom} disabled={(d) => d > new Date()} className="p-3 pointer-events-auto" />
                  </PopoverContent>
                </Popover>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button variant="outline" size="sm" className="h-8 gap-1 text-xs">
                      <CalendarIcon className="h-3.5 w-3.5" />
                      {dateTo ? format(dateTo, "dd.MM") : "До"}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="end">
                    <Calendar mode="single" selected={dateTo} onSelect={setDateTo} disabled={(d) => d > new Date()} className="p-3 pointer-events-auto" />
                  </PopoverContent>
                </Popover>
              </div>
            ) : null}
          </div>
        }
        bodyClassName="p-0"
      >
        <div className="max-h-96 overflow-y-auto">
          {tab === "activity" && (
            <table className="w-full text-sm">
              <tbody className="divide-y divide-border/50">
                {filteredActivity.length === 0 ? (
                  <tr><td className="px-5 py-8 text-center text-muted-foreground">Нет событий за выбранный период</td></tr>
                ) : (
                  filteredActivity.map((item, i) => (
                    <tr key={`${item.user}-${item.time}-${i}`} className="hover:bg-secondary/30">
                      <td className="px-5 py-3 align-top">
                        <div className="font-medium text-foreground">{item.user}</div>
                        <div className="text-xs text-muted-foreground">{item.category || "activity"}</div>
                      </td>
                      <td className="px-3 py-3 text-muted-foreground">{item.action}</td>
                      <td className="px-5 py-3 text-right text-xs text-muted-foreground">{relativeTime(item.time)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}

          {tab === "users" && (
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border bg-secondary/20 text-xs text-muted-foreground">
                  <th className="px-5 py-3 text-left font-medium">{t("adash.user")}</th>
                  <th className="px-3 py-3 text-right font-medium">{t("adash.actions")}</th>
                  <th className="px-3 py-3 text-right font-medium">{t("adash.ai_req")}</th>
                  <th className="px-5 py-3 text-right font-medium">{t("adash.term_sessions")}</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {d.top_users.map((u) => (
                  <tr key={u.username} className="hover:bg-secondary/30">
                    <td className="px-5 py-3 font-medium">{u.username}</td>
                    <td className="px-3 py-3 text-right text-muted-foreground">{u.total}</td>
                    <td className="px-3 py-3 text-right text-muted-foreground">{u.ai_requests}</td>
                    <td className="px-5 py-3 text-right text-muted-foreground">{u.terminal_sessions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {tab === "api" && (
            <div className="grid gap-3 p-5 sm:grid-cols-2 xl:grid-cols-4">
              {Object.entries(d.api_usage).map(([provider, usage]) => {
                const enabled = d.providers[provider]?.enabled;
                return (
                  <div key={provider} className={`relative overflow-hidden rounded-xl border p-4 space-y-3 ${enabled ? "border-primary/20 bg-primary/4" : "border-border bg-card"}`}>
                    <div className={`absolute left-0 top-0 h-full w-0.5 ${enabled ? "bg-primary" : "bg-border"}`} />
                    <div className="flex items-center justify-between gap-3">
                      <span className="truncate text-xs font-bold uppercase tracking-[0.12em] text-foreground">{provider}</span>
                      <StatusBadge label={enabled ? "ON" : "OFF"} tone={enabled ? "success" : "neutral"} dot={false} />
                    </div>
                    <div className="text-3xl font-bold tracking-tight">{usage.calls}</div>
                    <div className="space-y-1 text-[11px] text-muted-foreground">
                      <p>{(usage.input_tokens || 0).toLocaleString()} in / {(usage.output_tokens || 0).toLocaleString()} out</p>
                      <p className={usage.errors ? "text-red-400" : ""}>{usage.errors || 0} errors</p>
                      <p className="font-semibold text-primary">${(usage.cost_usd || 0).toFixed(4)}</p>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </SectionCard>

      {d.alerts.length > 0 ? (
        <SectionCard title={t("adash.alert_center")} icon={<AlertTriangle className="h-4 w-4" />} bodyClassName="divide-y divide-border/50 p-0">
          {d.alerts.map((alert, index) => (
            <div key={`${alert.server}-${alert.title}-${index}`} className="flex flex-col gap-2 px-5 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="min-w-0">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium">{alert.title}</span>
                  <StatusBadge label={alert.severity} tone={severityTone(alert.severity)} />
                </div>
                <div className="text-xs text-muted-foreground">{alert.server} · {alert.type}</div>
              </div>
              <span className="shrink-0 text-xs text-muted-foreground">{relativeTime(alert.time)}</span>
            </div>
          ))}
        </SectionCard>
      ) : null}

      {d.terminals.connections.length > 0 && (
        <SectionCard title={`${t("adash.active_terminals")} (${d.terminals.active})`} icon={<Terminal className="h-4 w-4" />}>
          <div className="flex flex-wrap gap-2">
            {d.terminals.connections.map((c, i) => (
              <div key={`${c.user}-${c.server}-${i}`} className="flex items-center gap-2 rounded-xl border border-primary/15 bg-primary/5 px-3 py-2 text-xs">
                <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/15">
                  <Terminal className="h-3.5 w-3.5 text-primary" />
                </div>
                <span className="font-semibold text-foreground">{c.user}</span>
                <span className="text-muted-foreground/60">→</span>
                <span className="font-medium text-muted-foreground">{c.server}</span>
                <span className="ml-auto text-muted-foreground/50">{relativeTime(c.connected_at)}</span>
              </div>
            ))}
          </div>
        </SectionCard>
      )}
    </PageShell>
  );
}
