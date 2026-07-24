import {
  Activity,
  Bot,
  CheckCircle2,
  Clock,
  Play,
  Server,
  Siren,
} from "lucide-react";
import { Link } from "react-router-dom";
import { MetricCard, MetricGrid, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { AttentionPanel, type AttentionItem } from "@/components/dashboard/AttentionPanel";
import { RunPulse } from "@/components/dashboard/RunPulse";
import { getWidgetNumberProp, getWidgetStringProp } from "@/components/dashboard/widgetProps";
import type { WidgetDefinition } from "@/components/dashboard/CustomizableDashboard";
import { relativeTime } from "@/lib/utils";
import { isRunFailure, isRunFinished, isRunSuccess } from "@/lib/runStatus";
import { localize } from "@/lib/i18n";
import type { UserDashboardData } from "./useUserDashboardData";
import { sectionToneStyles, type StatusTone } from "./userDashboardShared";

type RunWidgetCtx = Pick<UserDashboardData, "boot" | "runs" | "mon" | "lang"> & {
  attentionItems: AttentionItem[];
};

/** Attention, quick stats, active/recent agent runs. */
export function buildUserRunWidgets(ctx: RunWidgetCtx): WidgetDefinition[] {
  const { boot, runs, mon, lang, attentionItems } = ctx;
  const recentRuns = runs?.recent ?? [];
  const finishedRuns = recentRuns.filter((r) => isRunFinished(r.status));
  const succeededRuns = recentRuns.filter((r) => isRunSuccess(r.status));
  const recentSuccessRate = finishedRuns.length
    ? Math.round((succeededRuns.length / finishedRuns.length) * 100)
    : null;
  const avgDurationSec = finishedRuns.length
    ? finishedRuns.reduce((sum, r) => sum + (r.duration_ms ?? 0), 0) / finishedRuns.length / 1000
    : null;

  return [
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
  ];
}
