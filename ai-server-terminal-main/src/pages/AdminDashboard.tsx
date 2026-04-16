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
} from "lucide-react";
import { format, subDays } from "date-fns";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Calendar } from "@/components/ui/calendar";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { BarChart, Bar, XAxis, YAxis, Tooltip, ResponsiveContainer } from "recharts";
import { cn } from "@/lib/utils";
import { QueryStateBlock } from "@/components/ui/page-shell";

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

const DATE_PRESETS = [
  { label: "Сегодня", days: 0 },
  { label: "7 дней", days: 7 },
  { label: "14 дней", days: 14 },
  { label: "30 дней", days: 30 },
];

export default function AdminDashboard() {
  const { t } = useI18n();
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
    { label: "Пользователи онлайн", value: d.online_users.count, sub: `/ ${d.online_users.total_registered}`, icon: Users },
    { label: "Серверы активные", value: d.servers.active, sub: `/ ${d.servers.total}`, icon: Server },
    { label: "AI запросы сегодня", value: d.ai.requests_today, icon: Bot },
    { label: "Терминалы", value: d.terminals.active, icon: Terminal },
    { label: "API расходы", value: `$${totalCost.toFixed(2)}`, sub: `${d.api_calls_today} calls`, icon: DollarSign },
  ];

  return (
    <div className="p-5 max-w-7xl mx-auto space-y-4">
      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-lg font-semibold">Панель администратора</h1>
          <p className="text-[11px] text-muted-foreground">v{d.app_version}</p>
        </div>
        <Button size="sm" variant="outline" className="gap-1.5 h-7 text-xs" onClick={refresh}>
          <RefreshCw className="h-3 w-3" /> Обновить
        </Button>
      </div>

      {/* Top metrics */}
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        {METRICS.map((m) => (
          <div key={m.label} className="bg-card border border-border/60 rounded-xl px-4 py-3">
            <div className="flex items-center justify-between mb-1">
              <span className="text-[10px] text-muted-foreground uppercase tracking-wider">{m.label}</span>
              <m.icon className="h-3.5 w-3.5 text-primary" />
            </div>
            <p className="text-xl font-semibold">
              {m.value}
              {m.sub && <span className="text-[10px] font-normal text-muted-foreground ml-1">{m.sub}</span>}
            </p>
          </div>
        ))}
      </div>

      {/* Online users */}
      <div className="bg-card border border-border rounded-xl p-4 space-y-3">
        <div className="flex items-center gap-2">
          <Users className="h-3.5 w-3.5 text-primary" />
          <span className="text-xs font-medium">Пользователи онлайн</span>
          <Badge variant="outline" className="text-[10px]">{sessions.length}</Badge>
        </div>
        {sessions.length === 0 ? (
          <p className="text-xs text-muted-foreground py-2">Нет активных пользователей</p>
        ) : (
          <div className="grid grid-cols-1 md:grid-cols-3 gap-1.5 max-h-36 overflow-y-auto">
            {sessions.map((s) => (
              <div key={s.user_id} className="flex items-center gap-2 bg-muted/20 rounded-lg px-2.5 py-2">
                <div className="h-6 w-6 rounded-lg bg-primary/10 flex items-center justify-center text-[10px] font-bold text-primary shrink-0">
                  {s.username.slice(0, 1).toUpperCase()}
                </div>
                <div className="flex-1 min-w-0">
                  <span className="text-xs font-medium">{s.username}</span>
                  {s.is_staff && <Badge variant="secondary" className="ml-1 text-[8px] px-1 py-0">ADM</Badge>}
                </div>
                <span className="text-[10px] text-muted-foreground">{s.last_action}</span>
                {s.active_terminals > 0 && (
                  <Badge variant="outline" className="text-[9px] gap-0.5">
                    <Terminal className="h-2.5 w-2.5" /> {s.active_terminals}
                  </Badge>
                )}
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Activity chart */}
      {hourlyData.length > 0 && (
        <div className="bg-card border border-border rounded-lg p-4">
          <div className="flex items-center gap-2 mb-3">
            <TrendingUp className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-medium">Активность по часам</span>
          </div>
          <div className="h-32">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={hourlyData}>
                <XAxis dataKey="hour" tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} />
                <YAxis tick={{ fontSize: 9, fill: "hsl(var(--muted-foreground))" }} tickLine={false} axisLine={false} width={25} />
                <Tooltip
                  contentStyle={{
                    background: "hsl(var(--card))",
                    border: "1px solid hsl(var(--border))",
                    borderRadius: "6px",
                    fontSize: "11px",
                    padding: "4px 8px",
                  }}
                />
                <Bar dataKey="count" fill="hsl(var(--primary))" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Tabs: activity / top users / api */}
      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <div className="flex items-center justify-between px-3 py-2 border-b border-border bg-secondary/20">
          <div className="flex items-center gap-1">
            {(["activity", "users", "api"] as const).map((t2) => (
              <button
                key={t2}
                onClick={() => setTab(t2)}
                className={cn(
                  "px-3 py-1.5 rounded-md text-[11px] font-medium transition-colors",
                  tab === t2 ? "bg-card text-foreground shadow-sm" : "text-muted-foreground hover:text-foreground"
                )}
              >
                {t2 === "activity" ? "Лента действий" : t2 === "users" ? "Топ пользователей" : "API расходы"}
              </button>
            ))}
          </div>

          {/* Date filters for activity tab */}
          {tab === "activity" && (
            <div className="flex items-center gap-1.5">
              {DATE_PRESETS.map((preset) => (
                <Button
                  key={preset.days}
                  size="sm"
                  variant={activityPreset === preset.days ? "default" : "ghost"}
                  className="h-6 text-[9px] px-2"
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
                  <Button variant="outline" size="sm" className="h-6 text-[9px] gap-1 px-2">
                    <CalendarIcon className="h-2.5 w-2.5" />
                    {dateFrom ? format(dateFrom, "dd.MM") : "От"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="end">
                  <Calendar mode="single" selected={dateFrom} onSelect={setDateFrom} disabled={(d) => d > new Date()} className="p-3 pointer-events-auto" />
                </PopoverContent>
              </Popover>
              <span className="text-[9px] text-muted-foreground">—</span>
              <Popover>
                <PopoverTrigger asChild>
                  <Button variant="outline" size="sm" className="h-6 text-[9px] gap-1 px-2">
                    <CalendarIcon className="h-2.5 w-2.5" />
                    {dateTo ? format(dateTo, "dd.MM") : "До"}
                  </Button>
                </PopoverTrigger>
                <PopoverContent className="w-auto p-0" align="end">
                  <Calendar mode="single" selected={dateTo} onSelect={setDateTo} disabled={(d) => d > new Date()} className="p-3 pointer-events-auto" />
                </PopoverContent>
              </Popover>
            </div>
          )}
        </div>

        <div className="max-h-80 overflow-y-auto">
          {tab === "activity" && (
            <table className="w-full text-xs">
              <tbody className="divide-y divide-border/50">
                {filteredActivity.length === 0 ? (
                  <tr><td className="px-4 py-6 text-center text-muted-foreground">Нет событий за выбранный период</td></tr>
                ) : (
                  filteredActivity.map((item, i) => (
                    <tr key={i} className="hover:bg-muted/20">
                      <td className="px-3 py-2 w-24">
                        <span className="text-foreground font-medium">{item.user}</span>
                      </td>
                      <td className="px-2 py-2 text-muted-foreground">{item.action}</td>
                      <td className="px-2 py-2 text-right text-muted-foreground w-16">{relativeTime(item.time)}</td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          )}

          {tab === "users" && (
            <table className="w-full text-xs">
              <thead>
                <tr className="text-[10px] text-muted-foreground uppercase border-b border-border">
                  <th className="px-3 py-2 text-left font-medium">Пользователь</th>
                  <th className="px-2 py-2 text-right font-medium">Действия</th>
                  <th className="px-2 py-2 text-right font-medium">AI</th>
                  <th className="px-2 py-2 text-right font-medium">Терминал</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border/50">
                {d.top_users.map((u, i) => (
                  <tr key={i} className="hover:bg-muted/20">
                    <td className="px-3 py-2 font-medium">{u.username}</td>
                    <td className="px-2 py-2 text-right text-muted-foreground">{u.total}</td>
                    <td className="px-2 py-2 text-right text-muted-foreground">{u.ai_requests}</td>
                    <td className="px-2 py-2 text-right text-muted-foreground">{u.terminal_sessions}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}

          {tab === "api" && (
            <div className="grid grid-cols-2 md:grid-cols-4 gap-2 p-3">
              {Object.entries(d.api_usage).map(([provider, usage]) => (
                <div key={provider} className="rounded-lg border border-border p-3 space-y-1">
                  <div className="flex items-center justify-between">
                    <span className="text-[10px] font-semibold uppercase">{provider}</span>
                    <Badge variant={d.providers[provider]?.enabled ? "default" : "outline"} className="text-[8px] h-4">
                      {d.providers[provider]?.enabled ? "ON" : "OFF"}
                    </Badge>
                  </div>
                  <p className="text-lg font-semibold">{usage.calls} <span className="text-[10px] font-normal text-muted-foreground">calls</span></p>
                  <div className="text-[10px] text-muted-foreground space-y-0.5">
                    <p>{(usage.input_tokens || 0).toLocaleString()} in / {(usage.output_tokens || 0).toLocaleString()} out</p>
                    <p className="text-primary font-medium">${(usage.cost_usd || 0).toFixed(4)}</p>
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Active terminals */}
      {d.terminals.connections.length > 0 && (
        <div className="bg-card border border-border rounded-lg overflow-hidden">
          <div className="flex items-center gap-2 px-4 py-2.5 border-b border-border">
            <Terminal className="h-3.5 w-3.5 text-primary" />
            <span className="text-xs font-medium">Активные терминалы ({d.terminals.active})</span>
          </div>
          <div className="flex flex-wrap gap-2 p-3">
            {d.terminals.connections.map((c, i) => (
              <div key={i} className="flex items-center gap-1.5 bg-muted/20 rounded-lg px-2.5 py-1.5 text-[10px]">
                <Terminal className="h-3 w-3 text-primary" />
                <span className="font-medium">{c.user}</span>
                <span className="text-muted-foreground">→ {c.server}</span>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
