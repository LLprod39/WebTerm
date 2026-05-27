import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  fetchAdminDashboard,
} from "@/lib/api";
import { PageShell, PageHero, MetricGrid, MetricCard, SectionCard, StatusBadge, QueryStateBlock } from "@/components/ui/page-shell";
import { Users, Bot, Terminal as TerminalIcon, ShieldCheck, Activity, Server, AlertTriangle, Clock, Maximize2, Minimize2 } from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { relativeTime } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { CustomizableDashboard, type WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { 
  AreaChart, 
  Area, 
  XAxis, 
  YAxis, 
  CartesianGrid, 
  Tooltip, 
  ResponsiveContainer 
} from "recharts";
import { cn } from "@/lib/utils";

const sectionToneStyles: Record<string, string> = {
  default: "",
  info: "border-primary/30 shadow-sm bg-card/65",
  success: "border-emerald-500/25 bg-emerald-950/5 dark:bg-emerald-950/10 shadow-emerald-500/5",
  warning: "border-amber-500/25 bg-amber-950/5 dark:bg-amber-950/10 shadow-amber-500/5",
  danger: "border-red-500/25 bg-red-950/5 dark:bg-red-950/10 shadow-red-500/5",
};

export default function AdminDashboard() {
  const { t } = useI18n();
  const [isFullWidth, setIsFullWidth] = useState(() => {
    return localStorage.getItem("admin_dashboard_full_width") === "true";
  });

  const toggleWidth = () => {
    setIsFullWidth(prev => {
      const next = !prev;
      localStorage.setItem("admin_dashboard_full_width", String(next));
      return next;
    });
  };

  const { data: dashResponse, isLoading, error, refetch } = useQuery({
    queryKey: ["admin", "dashboard"],
    queryFn: fetchAdminDashboard,
    refetchInterval: 30000,
  });

  const d = dashResponse?.data;

  const availableWidgets = useMemo<WidgetDefinition[]>(() => {
    if (!d) return [];

    return [
      {
        id: "fleet_metrics",
        title: "Метрики флота",
        icon: <Server className="h-4 w-4" />,
        defaultSize: { w: 12, h: 1 },
        render: (config) => {
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Метрики флота";

          return (
            <SectionCard title={title} icon={<Server className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <MetricGrid>
                <MetricCard
                  label="Серверы"
                  value={d?.servers?.total || 0}
                  description={`${d?.servers?.active || 0} активно`}
                  icon={<Server className="h-5 w-5" />}
                />
                <MetricCard
                  label="Fleet CPU"
                  value={`${d?.fleet_health?.avg_cpu || 0}%`}
                  description="Средняя нагрузка"
                  icon={<Activity className="h-5 w-5" />}
                  tone={(d?.fleet_health?.avg_cpu || 0) > 80 ? "danger" : (d?.fleet_health?.avg_cpu || 0) > 60 ? "warning" : "default"}
                />
                <MetricCard
                  label="Агенты"
                  value={d?.agents?.running || 0}
                  description={`${d?.agents?.today || 0} запусков сегодня`}
                  icon={<Bot className="h-5 w-5" />}
                />
                <MetricCard
                  label="Алерты"
                  value={d?.active_alerts_count || 0}
                  description="Требуют внимания"
                  icon={<AlertTriangle className="h-5 w-5" />}
                  tone={(d?.active_alerts_count || 0) > 0 ? "danger" : "default"}
                />
              </MetricGrid>
            </SectionCard>
          );
        }
      },
      {
        id: "hourly_activity_chart",
        title: "Часовой график активности",
        icon: <Activity className="h-4 w-4" />,
        defaultSize: { w: 8, h: 1 },
        render: (config) => {
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Активность системы (по часам)";
          const chartData = d?.hourly_activity ?? [];

          return (
            <SectionCard title={title} icon={<Activity className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="h-[200px] w-full mt-2">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chartData} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                    <defs>
                      <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                        <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.35}/>
                        <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0}/>
                      </linearGradient>
                    </defs>
                    <CartesianGrid strokeDasharray="3 3" className="stroke-border/40" />
                    <XAxis dataKey="hour" className="text-[9px] font-medium fill-muted-foreground" />
                    <YAxis className="text-[9px] font-medium fill-muted-foreground" />
                    <Tooltip 
                      contentStyle={{ 
                        background: "hsl(var(--background))", 
                        borderColor: "hsl(var(--border))", 
                        borderRadius: "8px",
                        fontSize: "11px",
                        boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1)"
                      }} 
                    />
                    <Area type="monotone" dataKey="count" name="Действия" stroke="hsl(var(--primary))" strokeWidth={2} fillOpacity={1} fill="url(#colorCount)" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "ai_cost_tokens",
        title: "Расходы и Использование AI",
        icon: <ShieldCheck className="h-4 w-4" />,
        defaultSize: { w: 8, h: 1 },
        render: (config) => {
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Анализ вызовов AI & Провайдеры";
          const usageEntries = Object.entries(d?.api_usage || {});

          return (
            <SectionCard title={title} icon={<ShieldCheck className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="border-b border-border/60 text-muted-foreground text-[10px] uppercase font-bold tracking-wider">
                      <th className="py-2.5">Провайдер</th>
                      <th className="py-2.5 text-right font-semibold">Вызовы</th>
                      <th className="py-2.5 text-right font-semibold">Входные токен</th>
                      <th className="py-2.5 text-right font-semibold">Выходные токен</th>
                      <th className="py-2.5 text-right font-semibold">Ошибки</th>
                      <th className="py-2.5 text-right font-bold text-primary">Стоимость (USD)</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {usageEntries.map(([provider, usage]) => {
                      const errRate = usage.calls > 0 ? ((usage.errors / usage.calls) * 100).toFixed(1) : "0.0";
                      return (
                        <tr key={provider} className="hover:bg-secondary/10 transition-colors">
                          <td className="py-3 font-bold capitalize text-foreground/90">{provider}</td>
                          <td className="py-3 text-right font-mono">{usage.calls.toLocaleString()}</td>
                          <td className="py-3 text-right font-mono text-muted-foreground/80">{usage.input_tokens.toLocaleString()}</td>
                          <td className="py-3 text-right font-mono text-muted-foreground/80">{usage.output_tokens.toLocaleString()}</td>
                          <td className="py-3 text-right font-mono">
                            <span className={cn(usage.errors > 0 ? "text-red-500 font-bold" : "text-muted-foreground/80")}>
                              {usage.errors} ({errRate}%)
                            </span>
                          </td>
                          <td className="py-3 text-right font-bold font-mono text-emerald-500">${usage.cost_usd.toFixed(4)}</td>
                        </tr>
                      );
                    })}
                    {usageEntries.length === 0 && (
                      <tr>
                        <td colSpan={6} className="py-6 text-center text-muted-foreground">Нет зарегистрированных данных по API AI</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "active_providers",
        title: "Модели AI и Статус",
        icon: <ShieldCheck className="h-4 w-4" />,
        defaultSize: { w: 4, h: 1 },
        render: (config) => {
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Модели AI и Провайдеры";
          const providerEntries = Object.entries(d?.providers || {});

          return (
            <SectionCard title={title} icon={<ShieldCheck className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-3">
                {providerEntries.map(([provider, info]) => (
                  <div key={provider} className="flex items-center justify-between p-2.5 rounded-xl border border-border/80 bg-secondary/5 text-xs hover:border-primary/30 transition-all">
                    <div className="flex items-center gap-2">
                      <div className={cn("h-2 w-2 rounded-full shrink-0", info.enabled ? "bg-emerald-500" : "bg-muted-foreground/30")} />
                      <span className="font-semibold capitalize text-foreground/95">{provider}</span>
                    </div>
                    <span className="text-[10px] font-mono text-muted-foreground bg-card border rounded-md px-2 py-0.5 max-w-[150px] truncate shadow-sm">
                      {info.model || "n/a"}
                    </span>
                  </div>
                ))}
                {providerEntries.length === 0 && (
                  <div className="py-4 text-center text-xs text-muted-foreground">Провайдеры отсутствуют</div>
                )}
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "online_users",
        title: "Пользователи онлайн",
        icon: <Users className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = config.props?.limit ?? 5;
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Пользователи онлайн";
          const displayUsers = d?.online_users?.users?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<Users className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-3.5">
                {displayUsers.map((user, idx) => (
                  <div key={idx} className="flex items-center justify-between text-xs p-1.5 rounded-lg hover:bg-secondary/10 transition-colors">
                    <div className="flex items-center gap-2 min-w-0">
                      <div className="h-2 w-2 rounded-full bg-emerald-500 shrink-0" />
                      <span className="font-semibold text-foreground/90 truncate">{user.username}</span>
                    </div>
                    <div className="flex items-center gap-3 shrink-0 ml-3">
                      <span className="text-[11px] text-muted-foreground">{user.action}</span>
                      <span className="text-[9px] text-muted-foreground/50 font-mono">{relativeTime(user.time)}</span>
                    </div>
                  </div>
                ))}
                {displayUsers.length === 0 && (
                  <div className="py-6 text-center text-xs text-muted-foreground border border-dashed rounded-lg">Нет активных пользователей</div>
                )}
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "top_users",
        title: "Топ активных пользователей",
        icon: <Users className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = config.props?.limit ?? 5;
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Лидеры по активности";
          const displayUsers = d?.top_users?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<Users className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="overflow-x-auto">
                <table className="w-full text-xs text-left">
                  <thead>
                    <tr className="border-b border-border/60 text-muted-foreground text-[10px] uppercase font-bold tracking-wider">
                      <th className="py-2">Пользователь</th>
                      <th className="py-2 text-right">Всего операций</th>
                      <th className="py-2 text-right">AI Запросы</th>
                      <th className="py-2 text-right">Терминалы</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-border/40">
                    {displayUsers.map((u, idx) => (
                      <tr key={idx} className="hover:bg-secondary/10 transition-colors">
                        <td className="py-3 flex items-center gap-2">
                          <div className="flex h-6.5 w-6.5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-bold text-[10px] uppercase border border-primary/20 shadow-sm">
                            {u.username.substring(0, 2)}
                          </div>
                          <span className="font-semibold text-foreground/95">{u.username}</span>
                        </td>
                        <td className="py-3 text-right font-mono font-bold text-foreground/90">{u.total.toLocaleString()}</td>
                        <td className="py-3 text-right font-mono text-muted-foreground">{u.ai_requests.toLocaleString()}</td>
                        <td className="py-3 text-right font-mono text-muted-foreground">{u.terminal_sessions.toLocaleString()}</td>
                      </tr>
                    ))}
                    {displayUsers.length === 0 && (
                      <tr>
                        <td colSpan={4} className="py-4 text-center text-muted-foreground">Нет данных по активности пользователей</td>
                      </tr>
                    )}
                  </tbody>
                </table>
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "active_terminals",
        title: "Активные терминалы",
        icon: <TerminalIcon className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = config.props?.limit ?? 5;
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Активные сессии терминала";
          const displayConnections = d?.terminals?.connections?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<TerminalIcon className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-3">
                {displayConnections.map((c, idx) => (
                  <div key={idx} className="flex items-center gap-3 rounded-xl border border-border/60 bg-secondary/5 p-3 text-xs hover:border-primary/30 transition-all">
                    <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-card border shadow-inner">
                      <TerminalIcon className="h-3.5 w-3.5 text-muted-foreground" />
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-1.5">
                        <span className="font-bold text-foreground/95">{c.user}</span>
                        <span className="text-[10px] text-muted-foreground">connected to</span>
                      </div>
                      <p className="mt-0.5 truncate text-[11px] font-semibold text-primary font-mono">{c.server}</p>
                    </div>
                    <span className="ml-auto text-[9px] font-mono text-muted-foreground/50 shrink-0">{relativeTime(c.connected_at)}</span>
                  </div>
                ))}
                {displayConnections.length === 0 && (
                  <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-xl bg-secondary/5">Нет активных терминальных сессий</div>
                )}
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "system_alerts_list",
        title: "Инфраструктурные алерты",
        icon: <AlertTriangle className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = config.props?.limit ?? 5;
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Инфраструктурные алерты";
          const displayAlerts = d?.alerts?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<AlertTriangle className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-3">
                {displayAlerts.map((a, idx) => {
                  const alertTone = a.severity === "critical" ? "danger" : a.severity === "warning" ? "warning" : "info";
                  return (
                    <div key={idx} className="flex items-start gap-3 p-3 rounded-xl border border-border/80 bg-secondary/5 hover:border-primary/30 transition-all text-xs">
                      <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive text-[10px] font-bold">
                        !
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <strong className="font-semibold text-foreground/95 truncate">{a.title}</strong>
                          <StatusBadge label={a.severity} tone={alertTone as any} />
                        </div>
                        <p className="mt-1 text-muted-foreground text-[11px] leading-relaxed">{a.type}</p>
                        <p className="mt-1 text-[9px] text-muted-foreground/60">
                          сервер: <strong>{a.server}</strong> • {relativeTime(a.time)}
                        </p>
                      </div>
                    </div>
                  );
                })}
                {displayAlerts.length === 0 && (
                  <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-xl bg-secondary/5">
                    Инфраструктурных алертов нет
                  </div>
                )}
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "recent_activity",
        title: "Последние действия (Глобально)",
        icon: <Clock className="h-4 w-4" />,
        defaultSize: { w: 12, h: 1 },
        render: (config) => {
          const limit = config.props?.limit ?? 5;
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Лог активности системы";
          const displayActivity = d?.recent_activity?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<Activity className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-4">
                {displayActivity.map((a, idx) => (
                  <div key={idx} className="flex items-start gap-3 text-xs group">
                    <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-secondary/80 text-[10px] font-bold border shadow-inner">
                      {a.user[0].toUpperCase()}
                    </div>
                    <div className="flex-1 space-y-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-bold text-foreground/90">{a.user}</span>
                        <span className="text-[9px] font-mono text-muted-foreground/50 shrink-0">{relativeTime(a.time)}</span>
                      </div>
                      <p className="text-[11px] text-muted-foreground leading-relaxed">
                        <span className="font-semibold text-muted-foreground/70 uppercase text-[9px] tracking-wider bg-secondary/50 border px-1 py-0.2 rounded mr-1.5">{a.category}</span>
                        <span className="text-foreground/80">{a.action}</span>
                      </p>
                    </div>
                  </div>
                ))}
                {displayActivity.length === 0 && (
                  <div className="py-6 text-center text-xs text-muted-foreground">Действий в логе нет</div>
                )}
              </div>
            </SectionCard>
          );
        }
      }
    ];
  }, [d]);

  return (
    <PageShell width={isFullWidth ? "full" : "7xl"}>
      <PageHero
        kicker="System Overview"
        title="Admin Control Center"
        description="Мониторинг всей инфраструктуры, активности пользователей и работы AI-агентов в реальном времени."
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={toggleWidth}
              className="h-8 gap-1.5 text-xs font-semibold hover:border-primary/50 shadow-sm transition-all"
            >
              {isFullWidth ? (
                <>
                  <Minimize2 className="h-3.5 w-3.5" />
                  <span>Обычный экран</span>
                </>
              ) : (
                <>
                  <Maximize2 className="h-3.5 w-3.5" />
                  <span>На весь экран</span>
                </>
              )}
            </Button>
            <div className="flex items-center gap-3 px-3 py-1.5 rounded-xl bg-card border border-border/80 shadow-sm h-8 shrink-0">
              <ShieldCheck className="h-4 w-4 text-emerald-500" />
              <span className="text-xs font-semibold text-foreground/90">System Secure</span>
              <div className="h-3.5 w-px bg-border mx-1" />
              <span className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider">v{d?.app_version || "2.0.0"}</span>
            </div>
          </div>
        }
      />

      <QueryStateBlock loading={isLoading} error={error} onRetry={() => refetch()}>
        <CustomizableDashboard
          type="admin"
          availableWidgets={availableWidgets}
        />
      </QueryStateBlock>
    </PageShell>
  );
}
