import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import {
  fetchAgentDashboardRuns,
  fetchFrontendBootstrap,
  fetchMonitoringDashboard,
} from "@/lib/api";
import { PageShell, PageHero, MetricGrid, MetricCard, SectionCard, StatusBadge, QueryStateBlock } from "@/components/ui/page-shell";
import { 
  Activity, 
  Bot, 
  Terminal as TerminalIcon, 
  Clock, 
  Server, 
  Play, 
  Settings,
  Workflow
} from "lucide-react";
import { useI18n } from "@/lib/i18n";
import { relativeTime, cn } from "@/lib/utils";
import { CustomizableDashboard, type WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";

const sectionToneStyles: Record<string, string> = {
  default: "",
  info: "border-primary/30 shadow-sm bg-card/65",
  success: "border-emerald-500/25 bg-emerald-950/5 dark:bg-emerald-950/10 shadow-emerald-500/5",
  warning: "border-amber-500/25 bg-amber-950/5 dark:bg-amber-950/10 shadow-amber-500/5",
  danger: "border-red-500/25 bg-red-950/5 dark:bg-red-950/10 shadow-red-500/5",
};

export default function UserDashboard() {
  const { t } = useI18n();

  const { data: bootstrapResponse, isLoading: bootLoading } = useQuery({
    queryKey: ["bootstrap"],
    queryFn: fetchFrontendBootstrap,
  });

  const { data: runsResponse, isLoading: runsLoading } = useQuery({
    queryKey: ["agent-dashboard-runs"],
    queryFn: fetchAgentDashboardRuns,
    refetchInterval: 10000,
  });

  const { data: monitoringResponse, isLoading: monLoading } = useQuery({
    queryKey: ["monitoring-dashboard"],
    queryFn: fetchMonitoringDashboard,
  });

  const boot = bootstrapResponse;
  const runs = runsResponse;
  const mon = monitoringResponse;

  const isLoading = bootLoading || runsLoading || monLoading;

  const availableWidgets = useMemo<WidgetDefinition[]>(() => {
    if (!boot && !runs && !mon) return [];

    return [
      {
        id: "quick_stats",
        title: "Краткая сводка",
        icon: <Activity className="h-4 w-4" />,
        defaultSize: { w: 12, h: 1 },
        render: (config) => {
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Краткая сводка";

          return (
            <SectionCard title={title} icon={<Activity className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <MetricGrid>
                <MetricCard
                  label="Мои серверы"
                  value={boot?.servers?.length || 0}
                  description="Доступно для управления"
                  icon={<Server className="h-5 w-5" />}
                />
                <MetricCard
                  label="Активные агенты"
                  value={runs?.active?.length || 0}
                  description="Выполняются сейчас"
                  icon={<Bot className="h-5 w-5" />}
                  tone={runs?.active?.length ? "info" : "default"}
                />
                <MetricCard
                  label="Fleet Health"
                  value={mon?.summary?.healthy ?? 0}
                  description="Стабильных узлов"
                  icon={<Activity className="h-5 w-5" />}
                  tone="success"
                />
                <MetricCard
                  label="Алерты"
                  value={mon?.summary?.active_alerts ?? 0}
                  description="Требуют внимания"
                  icon={<Play className="h-5 w-5" />}
                  tone={mon?.summary?.active_alerts ? "warning" : "default"}
                />
              </MetricGrid>
            </SectionCard>
          );
        }
      },
      {
        id: "active_runs",
        title: "Запуски агентов (Активные)",
        icon: <Bot className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = config.props?.limit ?? 5;
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Активные запуски";
          const displayRuns = runs?.active?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<Bot className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-3">
                {displayRuns.map((run) => (
                  <Link
                    key={run.id}
                    to={`/agents/run/${run.id}`}
                    className="flex items-center justify-between rounded-lg border border-border/60 bg-secondary/5 p-3 transition-all hover:bg-secondary/15 hover:border-primary/30"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold truncate text-xs">{run.agent_name}</span>
                        <StatusBadge label={run.status} tone="info" />
                      </div>
                      <p className="mt-1 truncate text-[10px] text-muted-foreground">
                        на сервере: {run.server_name}
                      </p>
                    </div>
                    <div className="text-right shrink-0 ml-3">
                      <div className="text-[10px] text-muted-foreground font-mono">{relativeTime(run.started_at)}</div>
                    </div>
                  </Link>
                ))}
                {displayRuns.length === 0 && (
                  <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-xl bg-secondary/5">
                    Нет активных агентов
                  </div>
                )}
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "recent_runs",
        title: "Запуски агентов (История)",
        icon: <Clock className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = config.props?.limit ?? 5;
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "История запусков агентов";
          const displayRuns = runs?.recent?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<Clock className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-3">
                {displayRuns.map((r) => {
                  const isSuccess = r.status === "succeeded" || r.status === "success";
                  const isFailed = r.status === "failed" || r.status === "error";
                  const runTone = isSuccess ? "success" : isFailed ? "danger" : "info";
                  
                  return (
                    <Link
                      key={r.id}
                      to={`/agents/run/${r.id}`}
                      className="flex items-center justify-between rounded-lg border border-border/40 bg-secondary/5 p-2.5 transition-all hover:bg-secondary/15 hover:border-primary/30"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold truncate text-xs">{r.agent_name}</span>
                          <StatusBadge label={r.status} tone={runTone as any} />
                        </div>
                        <p className="mt-1 truncate text-[10px] text-muted-foreground">
                          сервер: <span className="text-foreground/80">{r.server_name}</span> • итераций: {r.total_iterations}
                        </p>
                      </div>
                      <div className="text-right shrink-0 ml-3">
                        <div className="text-[10px] font-mono font-medium text-foreground">{r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : "n/a"}</div>
                        <div className="text-[9px] text-muted-foreground/60 mt-0.5">{relativeTime(r.started_at)}</div>
                      </div>
                    </Link>
                  );
                })}
                {displayRuns.length === 0 && (
                  <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-xl bg-secondary/5">
                    История запусков пуста
                  </div>
                )}
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "servers_health",
        title: "Состояние серверов",
        icon: <Server className="h-4 w-4" />,
        defaultSize: { w: 8, h: 1 },
        render: (config) => {
          const limit = config.props?.limit ?? 5;
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Состояние Fleet серверов";
          const displayServers = mon?.servers?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<Server className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-2.5">
                {displayServers.map((s) => {
                  const statusTone = s.status === "healthy" ? "success" : s.status === "warning" ? "warning" : s.status === "critical" ? "danger" : s.status === "unreachable" ? "danger" : "neutral";
                  return (
                    <div key={s.server_id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-xl border border-border/80 bg-secondary/5 hover:border-primary/40 hover:bg-secondary/10 transition-all text-xs">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-card border shadow-sm">
                          <Server className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        </div>
                        <div className="truncate">
                          <span className="font-semibold text-foreground/95">{s.server_name}</span>
                          <span className="text-[10px] text-muted-foreground/50 ml-2 font-mono">({s.host})</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-3.5 shrink-0 flex-wrap sm:flex-nowrap">
                        <StatusBadge label={s.status} tone={statusTone as any} />
                        {s.cpu_percent !== null && (
                          <div className="text-[10px] text-muted-foreground shrink-0 bg-card border rounded px-1.5 py-0.5 font-medium">
                            CPU: <span className={cn("font-bold", s.cpu_percent > 80 ? "text-red-500" : s.cpu_percent > 60 ? "text-amber-500" : "text-emerald-500")}>{s.cpu_percent}%</span>
                          </div>
                        )}
                        {s.memory_percent !== null && (
                          <div className="text-[10px] text-muted-foreground shrink-0 bg-card border rounded px-1.5 py-0.5 font-medium">
                            RAM: <span className="text-foreground/90 font-bold">{s.memory_percent}%</span>
                          </div>
                        )}
                        {s.response_time_ms !== null && (
                          <span className="text-[10px] text-muted-foreground/50 font-mono shrink-0">
                            {s.response_time_ms}ms
                          </span>
                        )}
                        <Button size="xs" variant="outline" asChild className="h-6 px-2.5 text-[10px] shrink-0 font-semibold shadow-sm hover:border-primary/50">
                          <Link to={`/servers/${s.server_id}/terminal`}>Terminal</Link>
                        </Button>
                      </div>
                    </div>
                  );
                })}
                {displayServers.length === 0 && (
                  <div className="py-6 text-center text-xs text-muted-foreground">Нет данных по серверам</div>
                )}
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "recent_servers",
        title: "Недавние серверы",
        icon: <TerminalIcon className="h-4 w-4" />,
        defaultSize: { w: 4, h: 1 },
        render: (config) => {
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Недавние подключенные";
          const displayServers = boot?.servers?.slice(0, 5) ?? [];

          return (
            <SectionCard title={title} icon={<Clock className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-2">
                {displayServers.map((s) => (
                  <Link
                    key={s.id}
                    to={`/servers/${s.id}/terminal`}
                    className="flex items-center gap-3 rounded-xl border border-border/50 bg-card/40 p-2.5 text-xs hover:border-primary/50 hover:bg-secondary/10 hover:shadow-sm transition-all"
                  >
                    <div className="flex h-6 w-6 items-center justify-center rounded-lg bg-secondary/50">
                      <TerminalIcon className="h-3 w-3 text-muted-foreground" />
                    </div>
                    <span className="font-semibold truncate text-foreground/95">{s.name}</span>
                    <span className="ml-auto text-[10px] font-mono text-muted-foreground/50">{s.host}</span>
                  </Link>
                ))}
                {displayServers.length === 0 && (
                  <div className="py-6 text-center text-xs text-muted-foreground">Нет недавних серверов</div>
                )}
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "user_alerts",
        title: "Предупреждения и алерты",
        icon: <Play className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = config.props?.limit ?? 5;
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Предупреждения и алерты";
          const displayAlerts = mon?.alerts?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<Play className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-3">
                {displayAlerts.map((a) => {
                  const alertTone = a.severity === "critical" ? "danger" : a.severity === "warning" ? "warning" : "info";
                  return (
                    <div key={a.id} className="flex items-start gap-3 p-3 rounded-xl border border-border/80 bg-secondary/5 hover:border-primary/30 transition-all text-xs">
                      <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive text-[10px] font-bold">
                        !
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <strong className="font-semibold text-foreground/95 truncate">{a.title}</strong>
                          <StatusBadge label={a.severity} tone={alertTone as any} />
                        </div>
                        <p className="mt-1 text-muted-foreground text-[11px] leading-relaxed">{a.message}</p>
                        <p className="mt-1 text-[9px] text-muted-foreground/60">
                          сервер: <strong>{a.server_name}</strong> • {relativeTime(a.created_at)}
                        </p>
                      </div>
                    </div>
                  );
                })}
                {displayAlerts.length === 0 && (
                  <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-xl bg-secondary/5">
                    Активных предупреждений нет
                  </div>
                )}
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "recent_activity",
        title: "Моя активность",
        icon: <Activity className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = config.props?.limit ?? 5;
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "История действий";
          const displayActivity = boot?.recent_activity?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<Clock className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-4">
                {displayActivity.map((a, idx) => (
                  <div key={idx} className="flex items-start gap-3 text-xs group">
                    <div className="mt-1.5 h-2 w-2 rounded-full bg-primary/45 shrink-0 transition-transform group-hover:scale-125" />
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center justify-between gap-2">
                        <span className="font-semibold truncate text-foreground/90">{a.action}</span>
                        <span className="text-[10px] text-muted-foreground/40 font-mono shrink-0">{relativeTime(a.created_at)}</span>
                      </div>
                      <p className="mt-0.5 text-[11px] text-muted-foreground/70 leading-relaxed truncate">{a.description}</p>
                    </div>
                  </div>
                ))}
                {displayActivity.length === 0 && (
                  <div className="py-6 text-center text-xs text-muted-foreground">Нет недавних действий</div>
                )}
              </div>
            </SectionCard>
          );
        }
      },
      {
        id: "quick_tools",
        title: "Быстрые действия",
        icon: <Settings className="h-4 w-4" />,
        defaultSize: { w: 4, h: 1 },
        render: (config) => {
          const tone = config.props?.tone ?? "default";
          const title = config.props?.customTitle ?? "Быстрые действия";

          return (
            <SectionCard title={title} icon={<Settings className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="grid grid-cols-2 gap-2 text-xs">
                <Link to="/servers/hub" className="flex flex-col items-center justify-center p-3 rounded-xl border border-border/80 bg-card hover:border-primary/50 hover:bg-secondary/20 hover:shadow-sm transition-all text-center group">
                  <Server className="h-5 w-5 text-primary/80 mb-2 transition-transform group-hover:scale-110" />
                  <span className="font-semibold text-foreground/90">Хаб серверов</span>
                  <span className="text-[9px] text-muted-foreground/60 mt-0.5">Все узлы</span>
                </Link>
                <Link to="/studio" className="flex flex-col items-center justify-center p-3 rounded-xl border border-border/80 bg-card hover:border-primary/50 hover:bg-secondary/20 hover:shadow-sm transition-all text-center group">
                  <Workflow className="h-5 w-5 text-primary/80 mb-2 transition-transform group-hover:scale-110" />
                  <span className="font-semibold text-foreground/90">Студия</span>
                  <span className="text-[9px] text-muted-foreground/60 mt-0.5">Пайплайны</span>
                </Link>
                <Link to="/studio/skills" className="flex flex-col items-center justify-center p-3 rounded-xl border border-border/80 bg-card hover:border-primary/50 hover:bg-secondary/20 hover:shadow-sm transition-all text-center group">
                  <Bot className="h-5 w-5 text-primary/80 mb-2 transition-transform group-hover:scale-110" />
                  <span className="font-semibold text-foreground/90">Создать агента</span>
                  <span className="text-[9px] text-muted-foreground/60 mt-0.5">AI Скиллы</span>
                </Link>
                <Link to="/settings" className="flex flex-col items-center justify-center p-3 rounded-xl border border-border/80 bg-card hover:border-primary/50 hover:bg-secondary/20 hover:shadow-sm transition-all text-center group">
                  <Settings className="h-5 w-5 text-primary/80 mb-2 transition-transform group-hover:scale-110" />
                  <span className="font-semibold text-foreground/90">Настройки</span>
                  <span className="text-[9px] text-muted-foreground/60 mt-0.5">Параметры</span>
                </Link>
              </div>
            </SectionCard>
          );
        }
      }
    ];
  }, [boot, runs, mon]);

  return (
    <PageShell>
      <PageHero
        kicker="Dashboard"
        title="Мой воркспейс"
        description="Обзор активных задач, доступных серверов и последних событий в вашей рабочей среде."
        actions={
          <div className="flex items-center gap-2">
             <Button variant="outline" size="sm" asChild className="h-8 text-xs">
                <Link to="/servers/hub">
                  <Server className="mr-1.5 h-3.5 w-3.5" /> Хаб серверов
                </Link>
             </Button>
             <Button size="sm" asChild className="h-8 text-xs">
                <Link to="/studio">
                  <Workflow className="mr-1.5 h-3.5 w-3.5" /> Студия
                </Link>
             </Button>
          </div>
        }
      />

      <QueryStateBlock loading={isLoading}>
        <CustomizableDashboard
          type="user"
          availableWidgets={availableWidgets}
        />
      </QueryStateBlock>
    </PageShell>
  );
}
