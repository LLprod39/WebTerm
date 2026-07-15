import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import {
  fetchAgentDashboardRuns,
  fetchFrontendBootstrap,
  fetchMonitoringDashboard,
  fetchPluginSurfaces,
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
  Workflow,
  Maximize2,
  Minimize2,
  CheckCircle2,
  Siren,
} from "lucide-react";
import { relativeTime, cn } from "@/lib/utils";
import { isRunFailure, isRunFinished, isRunSuccess } from "@/lib/runStatus";
import { useI18n, localize } from "@/lib/i18n";
import { CustomizableDashboard, type WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { AttentionPanel, type AttentionItem } from "@/components/dashboard/AttentionPanel";
import { RunPulse } from "@/components/dashboard/RunPulse";
import { getWidgetNumberProp, getWidgetStringProp } from "@/components/dashboard/widgetProps";
import { Link } from "react-router-dom";
import { Button } from "@/components/ui/button";
import { buildPluginDashboardWidgets } from "@/plugins/dashboardWidgets";

const sectionToneStyles: Record<string, string> = {
  default: "",
  info: "border-primary/30 bg-primary/5",
  success: "border-success/25 bg-success/5",
  warning: "border-warning/25 bg-warning/5",
  danger: "border-destructive/25 bg-destructive/5",
};
type StatusTone = "neutral" | "success" | "warning" | "danger" | "info";

function cpuToneClass(value: number): string {
  return value > 80 ? "text-destructive" : value > 60 ? "text-warning" : "text-success";
}

export default function UserDashboard() {
  const { lang } = useI18n();
  const [isFullWidth, setIsFullWidth] = useState(() => {
    return localStorage.getItem("user_dashboard_full_width") === "true";
  });

  const toggleWidth = () => {
    setIsFullWidth((prev) => {
      const next = !prev;
      localStorage.setItem("user_dashboard_full_width", String(next));
      return next;
    });
  };

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
  const { data: pluginSurfaces } = useQuery({
    queryKey: ["plugins", "surfaces", "dashboard", "user"],
    queryFn: fetchPluginSurfaces,
  });

  const boot = bootstrapResponse;
  const runs = runsResponse;
  const mon = monitoringResponse;

  const isLoading = bootLoading || runsLoading || monLoading;

  const availableWidgets = useMemo<WidgetDefinition[]>(() => {
    if (!boot && !runs && !mon) return [];

    const recentRuns = runs?.recent ?? [];
    const finishedRuns = recentRuns.filter((r) => isRunFinished(r.status));
    const succeededRuns = recentRuns.filter((r) => isRunSuccess(r.status));
    const recentSuccessRate = finishedRuns.length
      ? Math.round((succeededRuns.length / finishedRuns.length) * 100)
      : null;
    const avgDurationSec = finishedRuns.length
      ? finishedRuns.reduce((sum, r) => sum + (r.duration_ms ?? 0), 0) / finishedRuns.length / 1000
      : null;

    const attentionItems: AttentionItem[] = [];
    for (const run of runs?.active ?? []) {
      if (run.pending_question) {
        attentionItems.push({
          id: `run-question-${run.id}`,
          severity: "warning",
          title: `${localize(lang, "Агент ждёт вашего ответа", "Agent is waiting for your reply")}: ${run.agent_name}`,
          detail: run.pending_question,
          time: run.started_at,
          action: { label: localize(lang, "Ответить", "Reply"), to: `/agents/run/${run.id}` },
        });
      }
    }
    for (const server of mon?.servers ?? []) {
      if (server.status === "unreachable") {
        attentionItems.push({
          id: `srv-unreachable-${server.server_id}`,
          severity: "critical",
          title: `${localize(lang, "Сервер недоступен", "Server unreachable")}: ${server.server_name}`,
          detail: server.host,
          time: server.checked_at,
          action: { label: localize(lang, "К серверам", "Servers"), to: "/servers" },
        });
      }
    }
    for (const alert of (mon?.alerts ?? []).filter((a) => !a.is_resolved).slice(0, 6)) {
      attentionItems.push({
        id: `alert-${alert.id}`,
        severity: alert.severity === "critical" ? "critical" : alert.severity === "warning" ? "warning" : "info",
        title: alert.title,
        detail: `${alert.server_name} · ${alert.message}`,
        time: alert.created_at,
        action: { label: localize(lang, "Терминал", "Terminal"), to: `/servers/${alert.server_id}/terminal` },
      });
    }
    for (const run of recentRuns.filter((r) => isRunFailure(r.status)).slice(0, 4)) {
      attentionItems.push({
        id: `run-failed-${run.id}`,
        severity: "warning",
        title: `${localize(lang, "Сбой агента", "Agent run failed")}: ${run.agent_name}`,
        detail: `${localize(lang, "сервер", "server")}: ${run.server_name}`,
        time: run.started_at,
        action: { label: localize(lang, "Разбор", "Inspect"), to: `/agents/run/${run.id}` },
      });
    }

    const builtins: WidgetDefinition[] = [
      {
        id: "my_attention",
        title: localize(lang, "Требует внимания", "Needs attention"),
        icon: <Siren className="h-4 w-4" />,
        defaultSize: { w: 12, h: 1 },
        render: (config) => {
          const limit = getWidgetNumberProp(config, "limit", 6);
          const tone = getWidgetStringProp(config, "tone", "default");
          const title = getWidgetStringProp(config, "customTitle", localize(lang, "Требует внимания", "Needs attention"));

          return (
            <SectionCard
              title={title}
              icon={<Siren className="h-4 w-4" />}
              description={localize(lang, "Вопросы агентов, сбои и алерты по вашим серверам", "Agent questions, failures and alerts on your servers")}
              className={sectionToneStyles[tone]}
            >
              <AttentionPanel
                items={attentionItems}
                lang={lang}
                maxItems={limit}
                allClearTitle={localize(lang, "У вас всё в порядке", "You're all clear")}
                allClearDetail={localize(
                  lang,
                  "Агенты не ждут ответа, серверы на связи, сбоев нет.",
                  "No agents waiting, servers reachable, no failures.",
                )}
              />
            </SectionCard>
          );
        },
      },
      {
        id: "quick_stats",
        title: localize(lang, "Краткая сводка", "Quick stats"),
        icon: <Activity className="h-4 w-4" />,
        defaultSize: { w: 12, h: 1 },
        render: (config) => {
          const tone = getWidgetStringProp(config, "tone", "default");
          const title = getWidgetStringProp(config, "customTitle", localize(lang, "Краткая сводка", "Quick stats"));

          return (
            <SectionCard title={title} icon={<Activity className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <MetricGrid>
                <MetricCard
                  label={localize(lang, "Мои серверы", "My servers")}
                  value={boot?.servers?.length || 0}
                  description={localize(lang, "Доступно для управления", "Available to manage")}
                  icon={<Server className="h-5 w-5" />}
                />
                <MetricCard
                  label={localize(lang, "Активные агенты", "Active agents")}
                  value={runs?.active?.length || 0}
                  description={localize(lang, "Выполняются сейчас", "Running now")}
                  icon={<Bot className="h-5 w-5" />}
                  tone={runs?.active?.length ? "info" : "default"}
                />
                <MetricCard
                  label={localize(lang, "Успешность запусков", "Run success rate")}
                  value={recentSuccessRate === null ? "—" : `${recentSuccessRate}%`}
                  description={
                    avgDurationSec === null
                      ? localize(lang, "Пока нет завершённых", "No finished runs yet")
                      : `${localize(lang, "средняя длительность", "avg duration")} ${avgDurationSec.toFixed(1)}s`
                  }
                  icon={<CheckCircle2 className="h-5 w-5" />}
                  tone={recentSuccessRate === null ? "default" : recentSuccessRate >= 80 ? "success" : recentSuccessRate >= 50 ? "warning" : "danger"}
                />
                <MetricCard
                  label={localize(lang, "Алерты", "Alerts")}
                  value={mon?.summary?.active_alerts ?? 0}
                  description={localize(lang, "Требуют внимания", "Need attention")}
                  icon={<Play className="h-5 w-5" />}
                  tone={mon?.summary?.active_alerts ? "warning" : "default"}
                />
              </MetricGrid>
              <RunPulse
                runs={recentRuns}
                lang={lang}
                className="mt-4 rounded-sm border border-border/60 bg-surface-1/60 px-3 py-2"
              />
            </SectionCard>
          );
        },
      },
      {
        id: "active_runs",
        title: localize(lang, "Запуски агентов (Активные)", "Agent runs (Active)"),
        icon: <Bot className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = getWidgetNumberProp(config, "limit", 5);
          const tone = getWidgetStringProp(config, "tone", "default");
          const title = getWidgetStringProp(config, "customTitle", localize(lang, "Активные запуски", "Active runs"));
          const displayRuns = runs?.active?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<Bot className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-3">
                {displayRuns.map((run) => (
                  <Link
                    key={run.id}
                    to={`/agents/run/${run.id}`}
                    className="flex items-center justify-between rounded-lg border border-border/60 bg-surface-2/40 p-3 transition-all hover:bg-surface-2 hover:border-primary/30"
                  >
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2">
                        <span className="font-semibold truncate text-xs">{run.agent_name}</span>
                        <StatusBadge label={run.status} tone="info" />
                      </div>
                      <p className="mt-1 truncate text-xs text-muted-foreground">
                        {localize(lang, "на сервере", "on server")}: {run.server_name}
                      </p>
                    </div>
                    <div className="text-right shrink-0 ml-3">
                      <div className="text-xs text-muted-foreground font-mono">{relativeTime(run.started_at)}</div>
                    </div>
                  </Link>
                ))}
                {displayRuns.length === 0 && (
                  <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-xl bg-surface-1/60">
                    {localize(lang, "Нет активных агентов", "No active agents")}
                  </div>
                )}
              </div>
            </SectionCard>
          );
        },
      },
      {
        id: "recent_runs",
        title: localize(lang, "Запуски агентов (История)", "Agent runs (History)"),
        icon: <Clock className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = getWidgetNumberProp(config, "limit", 5);
          const tone = getWidgetStringProp(config, "tone", "default");
          const title = getWidgetStringProp(config, "customTitle", localize(lang, "История запусков агентов", "Agent run history"));
          const displayRuns = runs?.recent?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<Clock className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-3">
                {displayRuns.map((r) => {
                  const runTone: StatusTone = isRunSuccess(r.status) ? "success" : isRunFailure(r.status) ? "danger" : "info";

                  return (
                    <Link
                      key={r.id}
                      to={`/agents/run/${r.id}`}
                      className="flex items-center justify-between rounded-lg border border-border/40 bg-surface-2/40 p-2.5 transition-all hover:bg-surface-2 hover:border-primary/30"
                    >
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <span className="font-semibold truncate text-xs">{r.agent_name}</span>
                          <StatusBadge label={r.status} tone={runTone} />
                        </div>
                        <p className="mt-1 truncate text-xs text-muted-foreground">
                          {localize(lang, "сервер", "server")}: <span className="text-foreground/80">{r.server_name}</span> • {localize(lang, "итераций", "iterations")}: {r.total_iterations}
                        </p>
                      </div>
                      <div className="text-right shrink-0 ml-3">
                        <div className="text-xs font-mono font-medium text-foreground">{r.duration_ms ? `${(r.duration_ms / 1000).toFixed(1)}s` : "n/a"}</div>
                        <div className="text-xs text-muted-foreground/60 mt-0.5">{relativeTime(r.started_at)}</div>
                      </div>
                    </Link>
                  );
                })}
                {displayRuns.length === 0 && (
                  <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-xl bg-surface-1/60">
                    {localize(lang, "История запусков пуста", "Run history is empty")}
                  </div>
                )}
              </div>
            </SectionCard>
          );
        },
      },
      {
        id: "servers_health",
        title: localize(lang, "Состояние серверов", "Server health"),
        icon: <Server className="h-4 w-4" />,
        defaultSize: { w: 8, h: 1 },
        render: (config) => {
          const limit = getWidgetNumberProp(config, "limit", 5);
          const tone = getWidgetStringProp(config, "tone", "default");
          const title = getWidgetStringProp(config, "customTitle", localize(lang, "Состояние серверов", "Server health"));
          const displayServers = mon?.servers?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<Server className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-2.5">
                {displayServers.map((s) => {
                  const statusTone: StatusTone = s.status === "healthy" ? "success" : s.status === "warning" ? "warning" : s.status === "critical" ? "danger" : s.status === "unreachable" ? "danger" : "neutral";
                  return (
                    <div key={s.server_id} className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 p-3 rounded-xl border border-border/60 bg-surface-2/40 hover:border-primary/40 hover:bg-surface-2 transition-all text-xs">
                      <div className="flex items-center gap-3 min-w-0">
                        <div className="flex h-7 w-7 items-center justify-center rounded-lg bg-surface-1 border border-border/60">
                          <Server className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                        </div>
                        <div className="truncate">
                          <span className="font-semibold text-foreground/95">{s.server_name}</span>
                          <span className="text-xs text-muted-foreground/50 ml-2 font-mono">({s.host})</span>
                        </div>
                      </div>
                      <div className="flex items-center gap-3.5 shrink-0 flex-wrap sm:flex-nowrap">
                        <StatusBadge label={s.status} tone={statusTone} />
                        {s.cpu_percent !== null && (
                          <div className="text-xs text-muted-foreground shrink-0 bg-surface-1 border border-border/60 rounded px-1.5 py-0.5 font-medium">
                            CPU: <span className={cn("font-bold", cpuToneClass(s.cpu_percent))}>{s.cpu_percent}%</span>
                          </div>
                        )}
                        {s.memory_percent !== null && (
                          <div className="text-xs text-muted-foreground shrink-0 bg-surface-1 border border-border/60 rounded px-1.5 py-0.5 font-medium">
                            RAM: <span className="text-foreground/90 font-bold">{s.memory_percent}%</span>
                          </div>
                        )}
                        {s.response_time_ms !== null && (
                          <span className="text-xs text-muted-foreground/50 font-mono shrink-0">
                            {s.response_time_ms}ms
                          </span>
                        )}
                        <Button size="xs" variant="outline" asChild className="shrink-0">
                          <Link to={`/servers/${s.server_id}/terminal`}>{localize(lang, "Терминал", "Terminal")}</Link>
                        </Button>
                      </div>
                    </div>
                  );
                })}
                {displayServers.length === 0 && (
                  <div className="py-6 text-center text-xs text-muted-foreground">{localize(lang, "Нет данных по серверам", "No server data")}</div>
                )}
              </div>
            </SectionCard>
          );
        },
      },
      {
        id: "recent_servers",
        title: localize(lang, "Быстрое подключение", "Quick connect"),
        icon: <TerminalIcon className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = getWidgetNumberProp(config, "limit", 5);
          const tone = getWidgetStringProp(config, "tone", "default");
          const title = getWidgetStringProp(config, "customTitle", localize(lang, "Быстрое подключение", "Quick connect"));
          const displayServers = boot?.servers?.slice(0, limit) ?? [];

          return (
            <SectionCard
              title={title}
              icon={<TerminalIcon className="h-4 w-4" />}
              description={localize(lang, "Один клик — и вы в терминале", "One click to a live terminal")}
              className={sectionToneStyles[tone]}
            >
              <div className="grid gap-2 sm:grid-cols-2">
                {displayServers.map((s) => (
                  <Link
                    key={s.id}
                    to={`/servers/${s.id}/terminal`}
                    className="group flex items-center gap-3 rounded-sm border border-border bg-surface-1 px-3 py-3 text-xs transition-all hover:border-primary/60 hover:shadow-elev-1"
                  >
                    <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-sm border border-border bg-surface-2 text-muted-foreground transition-colors group-hover:border-primary/40 group-hover:text-primary">
                      <TerminalIcon className="h-4 w-4" />
                    </div>
                    <div className="min-w-0">
                      <div className="truncate font-semibold text-foreground/95">{s.name}</div>
                      <div className="truncate font-mono text-2xs text-muted-foreground/60">{s.host}</div>
                    </div>
                  </Link>
                ))}
                <Link
                  to="/servers/hub"
                  className="flex items-center justify-center gap-2 rounded-sm border border-dashed border-border bg-surface-1/40 px-3 py-3 text-xs font-semibold text-muted-foreground transition-all hover:border-primary/60 hover:text-primary"
                >
                  <Server className="h-4 w-4" />
                  {localize(lang, "Все серверы", "All servers")}
                </Link>
              </div>
              {displayServers.length === 0 && (
                <div className="mt-2 py-4 text-center text-xs text-muted-foreground">
                  {localize(lang, "Серверов пока нет — добавьте первый в Хабе серверов.", "No servers yet — add your first one in the Server hub.")}
                </div>
              )}
            </SectionCard>
          );
        },
      },
      {
        id: "user_alerts",
        title: localize(lang, "Предупреждения и алерты", "Warnings & alerts"),
        icon: <Play className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = getWidgetNumberProp(config, "limit", 5);
          const tone = getWidgetStringProp(config, "tone", "default");
          const title = getWidgetStringProp(config, "customTitle", localize(lang, "Предупреждения и алерты", "Warnings & alerts"));
          const displayAlerts = mon?.alerts?.slice(0, limit) ?? [];

          return (
            <SectionCard title={title} icon={<Play className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="space-y-3">
                {displayAlerts.map((a) => {
                  const alertTone: StatusTone = a.severity === "critical" ? "danger" : a.severity === "warning" ? "warning" : "info";
                  return (
                    <div key={a.id} className="flex items-start gap-3 p-3 rounded-xl border border-border/60 bg-surface-2/40 hover:border-primary/30 transition-all text-xs">
                      <div className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-destructive/10 text-destructive text-xs font-bold">
                        !
                      </div>
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center justify-between gap-2">
                          <strong className="font-semibold text-foreground/95 truncate">{a.title}</strong>
                          <StatusBadge label={a.severity} tone={alertTone} />
                        </div>
                        <p className="mt-1 text-muted-foreground text-xs leading-relaxed">{a.message}</p>
                        <p className="mt-1 text-xs text-muted-foreground/60">
                          {localize(lang, "сервер", "server")}: <strong>{a.server_name}</strong> • {relativeTime(a.created_at)}
                        </p>
                      </div>
                    </div>
                  );
                })}
                {displayAlerts.length === 0 && (
                  <div className="py-8 text-center text-xs text-muted-foreground border border-dashed rounded-xl bg-surface-1/60">
                    {localize(lang, "Активных предупреждений нет", "No active warnings")}
                  </div>
                )}
              </div>
            </SectionCard>
          );
        },
      },
      {
        id: "recent_activity",
        title: localize(lang, "Моя активность", "My activity"),
        icon: <Activity className="h-4 w-4" />,
        defaultSize: { w: 6, h: 1 },
        render: (config) => {
          const limit = getWidgetNumberProp(config, "limit", 5);
          const tone = getWidgetStringProp(config, "tone", "default");
          const title = getWidgetStringProp(config, "customTitle", localize(lang, "История действий", "Action history"));
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
                        <span className="text-xs text-muted-foreground/40 font-mono shrink-0">{relativeTime(a.created_at)}</span>
                      </div>
                      <p className="mt-0.5 text-xs text-muted-foreground/70 leading-relaxed truncate">{a.description}</p>
                    </div>
                  </div>
                ))}
                {displayActivity.length === 0 && (
                  <div className="py-6 text-center text-xs text-muted-foreground">{localize(lang, "Нет недавних действий", "No recent actions")}</div>
                )}
              </div>
            </SectionCard>
          );
        },
      },
      {
        id: "quick_tools",
        title: localize(lang, "Быстрые действия", "Quick actions"),
        icon: <Settings className="h-4 w-4" />,
        defaultSize: { w: 4, h: 1 },
        render: (config) => {
          const tone = getWidgetStringProp(config, "tone", "default");
          const title = getWidgetStringProp(config, "customTitle", localize(lang, "Быстрые действия", "Quick actions"));

          const tools = [
            { to: "/servers/hub", icon: Server, title: localize(lang, "Хаб серверов", "Server hub"), sub: localize(lang, "Все узлы", "All nodes") },
            { to: "/studio", icon: Workflow, title: localize(lang, "Студия", "Studio"), sub: localize(lang, "Пайплайны", "Pipelines") },
            { to: "/agents", icon: Bot, title: localize(lang, "Агенты", "Agents"), sub: localize(lang, "Создать и запустить", "Create & run") },
            { to: "/settings", icon: Settings, title: localize(lang, "Настройки", "Settings"), sub: localize(lang, "Параметры", "Preferences") },
          ];

          return (
            <SectionCard title={title} icon={<Settings className="h-4 w-4" />} className={sectionToneStyles[tone]}>
              <div className="grid grid-cols-2 gap-2 text-xs">
                {tools.map((tool) => (
                  <Link
                    key={tool.to}
                    to={tool.to}
                    className="flex flex-col items-center justify-center p-3 rounded-xl border border-border/60 bg-surface-2/40 hover:border-primary/50 hover:bg-surface-2 transition-all text-center group"
                  >
                    <tool.icon className="h-5 w-5 text-primary/80 mb-2 transition-transform group-hover:scale-110" />
                    <span className="font-semibold text-foreground/90">{tool.title}</span>
                    <span className="text-xs text-muted-foreground/60 mt-0.5">{tool.sub}</span>
                  </Link>
                ))}
              </div>
            </SectionCard>
          );
        },
      },
    ];
    return [...builtins, ...buildPluginDashboardWidgets(pluginSurfaces?.surfaces?.dashboard_widgets ?? [])];
  }, [boot, runs, mon, pluginSurfaces?.surfaces?.dashboard_widgets, lang]);

  return (
    <PageShell width={isFullWidth ? "full" : "7xl"}>
      <PageHero
        kicker={localize(lang, "Операции", "Operations")}
        title={localize(lang, "Мой воркспейс", "My workspace")}
        description={localize(
          lang,
          "Обзор активных задач, доступных серверов и последних событий в вашей рабочей среде.",
          "Overview of active tasks, available servers and recent events in your workspace.",
        )}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={toggleWidth} className="gap-1.5">
              {isFullWidth ? (
                <>
                  <Minimize2 className="h-3.5 w-3.5" />
                  <span>{localize(lang, "Обычный экран", "Normal width")}</span>
                </>
              ) : (
                <>
                  <Maximize2 className="h-3.5 w-3.5" />
                  <span>{localize(lang, "На весь экран", "Full width")}</span>
                </>
              )}
            </Button>
            <Button variant="outline" size="sm" asChild>
              <Link to="/servers/hub">
                <Server className="mr-1.5 h-3.5 w-3.5" /> {localize(lang, "Хаб серверов", "Server hub")}
              </Link>
            </Button>
            <Button size="sm" asChild>
              <Link to="/studio">
                <Workflow className="mr-1.5 h-3.5 w-3.5" /> {localize(lang, "Студия", "Studio")}
              </Link>
            </Button>
          </div>
        }
      />

      <QueryStateBlock loading={isLoading}>
        <CustomizableDashboard type="user" availableWidgets={availableWidgets} />
      </QueryStateBlock>
    </PageShell>
  );
}
