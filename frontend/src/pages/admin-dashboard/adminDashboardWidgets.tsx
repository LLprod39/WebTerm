import { Activity, AlertTriangle, Bot, Clock, Server, Terminal as TerminalIcon, Users } from "lucide-react";
import {
  Area,
  AreaChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";

import type { AdminDashboardData } from "@/api";
import { MetricCard, MetricGrid, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { getWidgetNumberProp, getWidgetStringProp } from "@/components/dashboard/widgetProps";
import type { WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { localize } from "@/lib/i18n";
import { cn, relativeTime } from "@/lib/utils";
import { buildAdminUsageWidgets } from "./adminUsageWidgets";

const sectionToneStyles: Record<string, string> = {
  default: "",
  info: "border-primary/30 shadow-sm bg-card/65",
  success: "border-emerald-500/25 bg-emerald-950/5 dark:bg-emerald-950/10 shadow-emerald-500/5",
  warning: "border-amber-500/25 bg-amber-950/5 dark:bg-amber-950/10 shadow-amber-500/5",
  danger: "border-red-500/25 bg-red-950/5 dark:bg-red-950/10 shadow-red-500/5",
};

type StatusTone = "neutral" | "success" | "warning" | "danger" | "info";

function alertSeverityLabel(severity: string, lang: string) {
  const key = severity.toLowerCase();
  if (key === "critical") return localize(lang, "Критично", "Critical");
  if (key === "warning") return localize(lang, "Внимание", "Warning");
  if (key === "info") return localize(lang, "Инфо", "Info");
  return severity;
}

function alertTypeLabel(type: string, lang: string) {
  const key = type.toLowerCase();
  if (key === "server unreachable") return localize(lang, "Сервер недоступен", "Server unreachable");
  if (key === "unreachable") return localize(lang, "Сервер недоступен", "Unreachable");
  if (key === "service") return localize(lang, "Сервис", "Service");
  if (key === "resource") return localize(lang, "Ресурсы", "Resource");
  return type;
}

function activityCategoryLabel(category: string, lang: string) {
  const key = category.toLowerCase();
  if (key === "auth") return localize(lang, "Вход", "Auth");
  if (key === "agent") return localize(lang, "Агент", "Agent");
  if (key === "server") return localize(lang, "Сервер", "Server");
  if (key === "other") return localize(lang, "Другое", "Other");
  return category;
}

function activityActionLabel(action: string, lang: string) {
  const key = action.toLowerCase();
  if (key === "http_request") return localize(lang, "HTTP-запрос", "HTTP request");
  if (key === "login") return localize(lang, "Вход в систему", "Login");
  if (key === "logout") return localize(lang, "Выход", "Logout");
  return action;
}

function formatChartHour(value: unknown) {
  const date = new Date(String(value));
  if (Number.isNaN(date.getTime())) return String(value ?? "");
  return date.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

export function buildAdminDashboardWidgets(d: AdminDashboardData, lang: string): WidgetDefinition[] {
  return [
    {
      id: "fleet_metrics",
      title: "Метрики флота",
      icon: <Server className="h-4 w-4" />,
      defaultSize: { w: 12, h: 1 },
      render: (config) => {
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", "Метрики флота");

        return (
          <SectionCard title={title} icon={<Server className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <MetricGrid>
              <MetricCard
                label="Серверы"
                value={d.servers?.total || 0}
                description={`${d.servers?.active || 0} активно`}
                icon={<Server className="h-5 w-5" />}
              />
              <MetricCard
                label={localize(lang, "CPU флота", "Fleet CPU")}
                value={`${d.fleet_health?.avg_cpu || 0}%`}
                description="Средняя нагрузка"
                icon={<Activity className="h-5 w-5" />}
                tone={(d.fleet_health?.avg_cpu || 0) > 80 ? "danger" : (d.fleet_health?.avg_cpu || 0) > 60 ? "warning" : "default"}
              />
              <MetricCard
                label="Агенты"
                value={d.agents?.running || 0}
                description={`${d.agents?.today || 0} запусков сегодня`}
                icon={<Bot className="h-5 w-5" />}
              />
              <MetricCard
                label="Алерты"
                value={d.active_alerts_count || 0}
                description="Требуют внимания"
                icon={<AlertTriangle className="h-5 w-5" />}
                tone={(d.active_alerts_count || 0) > 0 ? "danger" : "default"}
              />
            </MetricGrid>
          </SectionCard>
        );
      },
    },
    {
      id: "hourly_activity_chart",
      title: "Часовой график активности",
      icon: <Activity className="h-4 w-4" />,
      defaultSize: { w: 8, h: 1 },
      render: (config) => {
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", "Активность системы (по часам)");

        return (
          <SectionCard title={title} icon={<Activity className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <div className="h-[200px] w-full mt-2">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={d.hourly_activity ?? []} margin={{ top: 5, right: 5, left: -25, bottom: 0 }}>
                  <defs>
                    <linearGradient id="colorCount" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.35} />
                      <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" className="stroke-border/40" />
                  <XAxis dataKey="hour" tickFormatter={formatChartHour} className="text-[9px] font-medium fill-muted-foreground" />
                  <YAxis className="text-[9px] font-medium fill-muted-foreground" />
                  <Tooltip
                    labelFormatter={formatChartHour}
                    contentStyle={{
                      background: "hsl(var(--background))",
                      borderColor: "hsl(var(--border))",
                      borderRadius: "8px",
                      fontSize: "11px",
                      boxShadow: "0 10px 15px -3px rgba(0, 0, 0, 0.1)",
                    }}
                  />
                  <Area type="monotone" dataKey="count" name="Действия" stroke="hsl(var(--primary))" strokeWidth={2} fillOpacity={1} fill="url(#colorCount)" />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </SectionCard>
        );
      },
    },
    ...buildAdminUsageWidgets(d, lang),
    {
      id: "online_users",
      title: "Пользователи онлайн",
      icon: <Users className="h-4 w-4" />,
      defaultSize: { w: 6, h: 1 },
      render: (config) => {
        const limit = getWidgetNumberProp(config, "limit", 5);
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", "Пользователи онлайн");
        const displayUsers = d.online_users?.users?.slice(0, limit) ?? [];

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
                    <span className="text-[11px] text-muted-foreground">{activityActionLabel(user.action, lang)}</span>
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
      },
    },
    {
      id: "top_users",
      title: "Топ активных пользователей",
      icon: <Users className="h-4 w-4" />,
      defaultSize: { w: 6, h: 1 },
      render: (config) => {
        const limit = getWidgetNumberProp(config, "limit", 5);
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", "Лидеры по активности");
        const displayUsers = d.top_users?.slice(0, limit) ?? [];

        return (
          <SectionCard title={title} icon={<Users className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <div className="space-y-2 md:hidden">
              {displayUsers.map((user, idx) => (
                <div key={idx} className="rounded-xl border border-border/70 bg-secondary/5 p-3 text-xs">
                  <div className="flex items-center gap-2">
                    <div className="flex h-6.5 w-6.5 shrink-0 items-center justify-center rounded-full border border-primary/20 bg-primary/10 text-[10px] font-bold uppercase text-primary">
                      {user.username.substring(0, 2)}
                    </div>
                    <span className="font-semibold text-foreground/95">{user.username}</span>
                  </div>
                  <div className="mt-2 grid grid-cols-3 gap-2 text-[11px]">
                    <div>
                      <div className="text-muted-foreground">Всего</div>
                      <div className="font-mono font-bold text-foreground">{user.total.toLocaleString()}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">AI</div>
                      <div className="font-mono text-foreground">{user.ai_requests.toLocaleString()}</div>
                    </div>
                    <div>
                      <div className="text-muted-foreground">Терминалы</div>
                      <div className="font-mono text-foreground">{user.terminal_sessions.toLocaleString()}</div>
                    </div>
                  </div>
                </div>
              ))}
              {displayUsers.length === 0 && (
                <div className="py-4 text-center text-xs text-muted-foreground">Нет данных по активности пользователей</div>
              )}
            </div>
            <div className="hidden overflow-x-auto md:block">
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
                  {displayUsers.map((user, idx) => (
                    <tr key={idx} className="hover:bg-secondary/10 transition-colors">
                      <td className="py-3 flex items-center gap-2">
                        <div className="flex h-6.5 w-6.5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-bold text-[10px] uppercase border border-primary/20 shadow-sm">
                          {user.username.substring(0, 2)}
                        </div>
                        <span className="font-semibold text-foreground/95">{user.username}</span>
                      </td>
                      <td className="py-3 text-right font-mono font-bold text-foreground/90">{user.total.toLocaleString()}</td>
                      <td className="py-3 text-right font-mono text-muted-foreground">{user.ai_requests.toLocaleString()}</td>
                      <td className="py-3 text-right font-mono text-muted-foreground">{user.terminal_sessions.toLocaleString()}</td>
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
      },
    },
    {
      id: "active_terminals",
      title: "Активные терминалы",
      icon: <TerminalIcon className="h-4 w-4" />,
      defaultSize: { w: 6, h: 1 },
      render: (config) => {
        const limit = getWidgetNumberProp(config, "limit", 5);
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", "Активные сессии терминала");
        const displayConnections = d.terminals?.connections?.slice(0, limit) ?? [];

        return (
          <SectionCard title={title} icon={<TerminalIcon className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <div className="space-y-3">
              {displayConnections.map((connection, idx) => (
                <div key={idx} className="flex items-center gap-3 rounded-xl border border-border/60 bg-secondary/5 p-3 text-xs hover:border-primary/30 transition-all">
                  <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-lg bg-card border shadow-inner">
                    <TerminalIcon className="h-3.5 w-3.5 text-muted-foreground" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-1.5">
                      <span className="font-bold text-foreground/95">{connection.user}</span>
                      <span className="text-[10px] text-muted-foreground">connected to</span>
                    </div>
                    <p className="mt-0.5 truncate text-[11px] font-semibold text-primary font-mono">{connection.server}</p>
                  </div>
                  <span className="ml-auto text-[9px] font-mono text-muted-foreground/50 shrink-0">{relativeTime(connection.connected_at)}</span>
                </div>
              ))}
              {displayConnections.length === 0 && (
                <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-xl bg-secondary/5">Нет активных терминальных сессий</div>
              )}
            </div>
          </SectionCard>
        );
      },
    },
    {
      id: "system_alerts_list",
      title: "Инфраструктурные алерты",
      icon: <AlertTriangle className="h-4 w-4" />,
      defaultSize: { w: 6, h: 1 },
      render: (config) => {
        const limit = getWidgetNumberProp(config, "limit", 5);
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", "Инфраструктурные алерты");
        const displayAlerts = d.alerts?.slice(0, limit) ?? [];

        return (
          <SectionCard title={title} icon={<AlertTriangle className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <div className="space-y-3">
              {displayAlerts.map((alert, idx) => {
                const alertTone: StatusTone = alert.severity === "critical" ? "danger" : alert.severity === "warning" ? "warning" : "info";
                return (
                  <div key={idx} className="flex items-start gap-3 p-3 rounded-xl border border-border/80 bg-secondary/5 hover:border-primary/30 transition-all text-xs">
                    <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive text-[10px] font-bold">
                      !
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <strong className="font-semibold text-foreground/95 truncate">{alertTypeLabel(alert.title, lang)}</strong>
                        <StatusBadge label={alertSeverityLabel(alert.severity, lang)} tone={alertTone} />
                      </div>
                      <p className="mt-1 text-muted-foreground text-[11px] leading-relaxed">{alertTypeLabel(alert.type, lang)}</p>
                      <p className="mt-1 text-[9px] text-muted-foreground/60">
                        сервер: <strong>{alert.server}</strong> • {relativeTime(alert.time)}
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
      },
    },
    {
      id: "recent_activity",
      title: "Последние действия (Глобально)",
      icon: <Clock className="h-4 w-4" />,
      defaultSize: { w: 12, h: 1 },
      render: (config) => {
        const limit = getWidgetNumberProp(config, "limit", 5);
        const tone = getWidgetStringProp(config, "tone", "default");
        const title = getWidgetStringProp(config, "customTitle", "Лог активности системы");
        const displayActivity = d.recent_activity?.slice(0, limit) ?? [];

        return (
          <SectionCard title={title} icon={<Activity className="h-4 w-4" />} className={sectionToneStyles[tone]}>
            <div className="space-y-4">
              {displayActivity.map((activity, idx) => (
                <div key={idx} className="flex items-start gap-3 text-xs group">
                  <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-secondary/80 text-[10px] font-bold border shadow-inner">
                    {activity.user[0].toUpperCase()}
                  </div>
                  <div className="flex-1 space-y-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-foreground/90">{activity.user}</span>
                      <span className="text-[9px] font-mono text-muted-foreground/50 shrink-0">{relativeTime(activity.time)}</span>
                    </div>
                    <p className="text-[11px] text-muted-foreground leading-relaxed">
                      <span className="font-semibold text-muted-foreground/70 uppercase text-[9px] tracking-wider bg-secondary/50 border px-1 py-0.2 rounded mr-1.5">{activityCategoryLabel(activity.category, lang)}</span>
                      <span className="text-foreground/80">{activityActionLabel(activity.action, lang)}</span>
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
      },
    },
  ];
}
