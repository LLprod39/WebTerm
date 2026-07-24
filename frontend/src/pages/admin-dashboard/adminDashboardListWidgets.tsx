import { Activity, AlertTriangle, Clock, Terminal as TerminalIcon, Users } from "lucide-react";

import type { AdminDashboardData } from "@/api";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { getWidgetNumberProp, getWidgetStringProp } from "@/components/dashboard/widgetProps";
import type { WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { relativeTime } from "@/lib/utils";
import {
  activityActionLabel,
  activityCategoryLabel,
  alertSeverityLabel,
  alertTypeLabel,
  sectionToneStyles,
  type StatusTone,
} from "./adminDashboardFormatters";

/** Users, terminals, alerts, recent activity list widgets. */
export function buildAdminListWidgets(d: AdminDashboardData, lang: string): WidgetDefinition[] {
  return [
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
                    <div className="h-2 w-2 rounded-full bg-success shrink-0" />
                    <span className="font-semibold text-foreground/90 truncate">{user.username}</span>
                  </div>
                  <div className="flex items-center gap-3 shrink-0 ml-3">
                    <span className="text-xs text-muted-foreground">{activityActionLabel(user.action, lang)}</span>
                    <span className="text-xs text-muted-foreground/50 font-mono">{relativeTime(user.time)}</span>
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
                    <div className="flex h-6.5 w-6.5 shrink-0 items-center justify-center rounded-full border border-primary/20 bg-primary/10 text-xs font-bold uppercase text-primary">
                      {user.username.substring(0, 2)}
                    </div>
                    <span className="font-semibold text-foreground/95">{user.username}</span>
                  </div>
                  <div className="mt-2 grid grid-cols-3 gap-2 text-xs">
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
                  <tr className="border-b border-border/60 text-muted-foreground text-xs uppercase font-bold tracking-wider">
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
                        <div className="flex h-6.5 w-6.5 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary font-bold text-xs uppercase border border-primary/20 shadow-sm">
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
                      <span className="text-xs text-muted-foreground">connected to</span>
                    </div>
                    <p className="mt-0.5 truncate text-xs font-semibold text-primary font-mono">{connection.server}</p>
                  </div>
                  <span className="ml-auto text-xs font-mono text-muted-foreground/50 shrink-0">{relativeTime(connection.connected_at)}</span>
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
                    <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive text-xs font-bold">
                      !
                    </div>
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center justify-between gap-2">
                        <strong className="font-semibold text-foreground/95 truncate">{alertTypeLabel(alert.title, lang)}</strong>
                        <StatusBadge label={alertSeverityLabel(alert.severity, lang)} tone={alertTone} />
                      </div>
                      <p className="mt-1 text-muted-foreground text-xs leading-relaxed">{alertTypeLabel(alert.type, lang)}</p>
                      <p className="mt-1 text-xs text-muted-foreground/60">
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
                  <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-secondary/80 text-xs font-bold border shadow-inner">
                    {activity.user[0].toUpperCase()}
                  </div>
                  <div className="flex-1 space-y-1 min-w-0">
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-bold text-foreground/90">{activity.user}</span>
                      <span className="text-xs font-mono text-muted-foreground/50 shrink-0">{relativeTime(activity.time)}</span>
                    </div>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      <span className="font-semibold text-muted-foreground/70 uppercase text-xs tracking-wider bg-secondary/50 border px-1 py-0.2 rounded mr-1.5">{activityCategoryLabel(activity.category, lang)}</span>
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
