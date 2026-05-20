import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  fetchAgentDashboardRuns,
  fetchFrontendBootstrap,
  fetchAuthSession,
  fetchMonitoringDashboard,
  studioRuns,
  type DashboardRunItem,
  type FrontendServer,
  type PipelineRun,
  type ServerHealth,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { canAccessStudio, hasFeatureAccess } from "@/lib/featureAccess";
import {
  Activity,
  AlertTriangle,
  ArrowRight,
  Bot,
  CheckCircle2,
  Clock,
  ExternalLink,
  Eye,
  RefreshCw,
  Server,
  Terminal,
  Workflow,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Link, useNavigate } from "react-router-dom";
import {
  EmptyState,
  MetricCard,
  MetricGrid,
  PageHero,
  PageShell,
  QueryStateBlock,
  SectionCard,
  StatusBadge,
} from "@/components/ui/page-shell";

function getGreeting(): string {
  const h = new Date().getHours();
  if (h < 6) return "🌙";
  if (h < 12) return "☀️";
  if (h < 18) return "🌤";
  return "🌙";
}

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

function formatDuration(ms: number): string {
  if (!ms) return "0s";
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  return `${mins}m`;
}

function healthTone(status: string): "success" | "warning" | "danger" | "neutral" | "info" {
  if (status === "healthy" || status === "online") return "success";
  if (status === "warning") return "warning";
  if (status === "critical" || status === "unreachable" || status === "offline") return "danger";
  if (status === "running") return "info";
  return "neutral";
}

function runTone(status: string): "success" | "warning" | "danger" | "neutral" | "info" {
  if (status === "completed" || status === "success") return "success";
  if (status === "running" || status === "in_progress") return "info";
  if (status === "failed" || status === "error") return "danger";
  if (status === "waiting" || status === "paused") return "warning";
  return "neutral";
}

function terminalPath(server: FrontendServer): string {
  return server.server_type === "rdp" ? `/servers/${server.id}/rdp` : `/servers/${server.id}/terminal`;
}

const QUICK_LINKS = [
  { key: "servers", to: "/servers", icon: Server, feature: null as string | null },
  { key: "terminal", to: "/servers/hub", icon: Terminal, feature: null },
  { key: "agents", to: "/agents", icon: Bot, feature: "agents" },
  { key: "studio", to: "/studio", icon: Workflow, feature: "studio" },
] as const;

export default function UserDashboard() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const navigate = useNavigate();

  const { data: authData } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const username = authData?.user?.username || "";
  const studioEnabled = canAccessStudio(authData?.user);
  const agentsEnabled = hasFeatureAccess(authData?.user, "agents");

  const { data: bootstrapData, isLoading: bootstrapLoading, error: bootstrapError } = useQuery({
    queryKey: ["frontend", "bootstrap", "dashboard"],
    queryFn: fetchFrontendBootstrap,
    staleTime: 20_000,
  });

  const { data: monitoringData, isLoading: monitoringLoading } = useQuery({
    queryKey: ["monitoring", "dashboard", "user"],
    queryFn: fetchMonitoringDashboard,
    staleTime: 20_000,
    refetchInterval: 30_000,
  });

  const { data: runsData } = useQuery({
    queryKey: ["agents", "dashboard-runs"],
    queryFn: () => fetchAgentDashboardRuns(),
    enabled: agentsEnabled,
    refetchInterval: 10_000,
  });

  const { data: pipelineRuns } = useQuery({
    queryKey: ["studio", "runs", "dashboard"],
    queryFn: () => studioRuns.list(),
    enabled: studioEnabled,
    staleTime: 15_000,
  });

  const refresh = async () => {
    await Promise.all([
      queryClient.invalidateQueries({ queryKey: ["frontend", "bootstrap"] }),
      queryClient.invalidateQueries({ queryKey: ["monitoring", "dashboard"] }),
      queryClient.invalidateQueries({ queryKey: ["agents", "dashboard-runs"] }),
      queryClient.invalidateQueries({ queryKey: ["studio", "runs"] }),
    ]);
  };

  const isLoading = bootstrapLoading || monitoringLoading;
  const error = bootstrapError;

  if (isLoading || error || !bootstrapData) {
    return (
      <QueryStateBlock
        loading={isLoading}
        error={error || (!isLoading && !bootstrapData ? new Error(t("dash.error")) : undefined)}
        className="p-6"
      >
        {null}
      </QueryStateBlock>
    );
  }

  const servers = bootstrapData.servers || [];
  const summary = monitoringData?.summary;
  const healthById = new Map<number, ServerHealth>(
    (monitoringData?.servers || []).map((item) => [item.server_id, item]),
  );
  const alerts = (monitoringData?.alerts || []).filter((a) => !a.is_resolved).slice(0, 6);
  const activeRuns = runsData?.active || [];
  const recentAgentRuns = (runsData?.recent || []).slice(0, 4);
  const recentPipelines = (pipelineRuns || [])
    .slice()
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
    .slice(0, 4);
  const recentActivity = (bootstrapData.recent_activity || []).slice(0, 6);

  const recentServers = servers
    .slice()
    .sort((a, b) => {
      const ta = a.last_connected ? new Date(a.last_connected).getTime() : 0;
      const tb = b.last_connected ? new Date(b.last_connected).getTime() : 0;
      return tb - ta;
    })
    .slice(0, 6);

  const attentionServers = servers
    .map((server) => ({ server, health: healthById.get(server.id) }))
    .filter(({ health }) => health && health.status !== "healthy" && health.status !== "unknown")
    .slice(0, 5);

  const quickLinks = QUICK_LINKS.filter((item) => {
    if (!item.feature) return true;
    if (item.feature === "studio") return studioEnabled;
    return hasFeatureAccess(authData?.user, item.feature);
  });

  const healthyCount = summary?.healthy ?? servers.filter((s) => s.status === "online").length;
  const problemCount = (summary?.warning ?? 0) + (summary?.critical ?? 0) + (summary?.unreachable ?? 0);
  const totalServers = summary?.total_servers ?? servers.length;
  const activeAlerts = summary?.active_alerts ?? alerts.length;
  const runningPipelines = recentPipelines.filter((r) => r.status === "running" || r.status === "in_progress").length;

  return (
    <PageShell width="6xl">
      <PageHero
        kicker={username ? `${getGreeting()} ${username}` : t("dashboard.user.kicker")}
        title={t("dashboard.user.title")}
        description={t("dashboard.user.subtitle")}
        actions={
          <Button size="sm" variant="outline" className="gap-1.5" onClick={() => void refresh()}>
            <RefreshCw className="h-3.5 w-3.5" />
            {t("dashboard.user.refresh")}
          </Button>
        }
      />

      <MetricGrid>
        <MetricCard
          label={t("dashboard.user.metric_servers")}
          value={totalServers}
          description={`${healthyCount} ${t("udash.healthy_lc")} · ${problemCount} ${t("udash.problems")}`}
          icon={<Server className="h-4 w-4" />}
          tone={problemCount > 0 ? "warning" : "success"}
        />
        <MetricCard
          label={t("dashboard.user.metric_alerts")}
          value={activeAlerts}
          description={activeAlerts > 0 ? t("dashboard.user.metric_alerts_active") : t("dashboard.user.metric_alerts_clear")}
          icon={<AlertTriangle className="h-4 w-4" />}
          tone={activeAlerts > 0 ? "danger" : "success"}
        />
        <MetricCard
          label={t("dashboard.user.metric_agents")}
          value={activeRuns.length}
          description={agentsEnabled ? t("dashboard.user.metric_agents_desc") : t("dashboard.user.metric_agents_disabled")}
          icon={<Bot className="h-4 w-4" />}
          tone={activeRuns.length > 0 ? "info" : "default"}
        />
        <MetricCard
          label={t("dashboard.user.metric_studio")}
          value={runningPipelines}
          description={studioEnabled ? t("dashboard.user.metric_studio_desc") : t("dashboard.user.metric_studio_disabled")}
          icon={<Workflow className="h-4 w-4" />}
          tone="default"
        />
      </MetricGrid>

      <section className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        {quickLinks.map((item) => {
          const Icon = item.icon;
          return (
            <Link
              key={item.key}
              to={item.to}
              className="group flex items-center gap-3 rounded-xl border border-border bg-card px-4 py-3.5 transition-colors hover:border-primary/30 hover:bg-primary/5"
            >
              <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                <Icon className="h-4 w-4" />
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-medium text-foreground">{t(`dashboard.user.quick_${item.key}`)}</div>
                <p className="text-xs text-muted-foreground">{t(`dashboard.user.quick_${item.key}_hint`)}</p>
              </div>
              <ArrowRight className="h-4 w-4 shrink-0 text-muted-foreground transition-transform group-hover:translate-x-0.5 group-hover:text-primary" />
            </Link>
          );
        })}
      </section>

      <div className="grid gap-4 lg:grid-cols-2">
        <SectionCard
          title={t("dashboard.user.recent_servers")}
          description={t("dashboard.user.recent_servers_desc")}
          icon={<Server className="h-4 w-4" />}
          actions={
            <Link to="/servers">
              <Button size="sm" variant="ghost" className="text-xs">
                {t("dashboard.user.view_all_servers")}
              </Button>
            </Link>
          }
          bodyClassName="p-0"
        >
          {recentServers.length === 0 ? (
            <EmptyState
              icon={<Server className="h-5 w-5" />}
              title={t("dashboard.user.no_servers")}
              description={t("dashboard.user.no_servers_desc")}
              className="m-5"
            />
          ) : (
            <div className="divide-y divide-border/40">
              {recentServers.map((server) => {
                const health = healthById.get(server.id);
                const status = health?.status || server.status;
                return (
                  <div key={server.id} className="flex items-center gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="truncate text-sm font-medium">{server.name}</span>
                        <StatusBadge label={status} tone={healthTone(status)} />
                      </div>
                      <p className="mt-1 truncate text-xs text-muted-foreground">
                        {server.host}
                        {server.last_connected ? ` · ${relativeTime(server.last_connected)}` : ""}
                      </p>
                    </div>
                    <Link to={terminalPath(server)}>
                      <Button size="sm" variant="outline" className="gap-1 text-xs">
                        <Terminal className="h-3 w-3" />
                        {t("udash.quick_connect")}
                      </Button>
                    </Link>
                  </div>
                );
              })}
            </div>
          )}
        </SectionCard>

        <SectionCard
          title={t("dashboard.user.alerts")}
          description={activeAlerts > 0 ? `${activeAlerts} ${t("udash.active_alerts").toLowerCase()}` : t("udash.all_good")}
          icon={<AlertTriangle className="h-4 w-4" />}
          bodyClassName="p-0"
        >
          {alerts.length === 0 ? (
            <EmptyState
              icon={<CheckCircle2 className="h-5 w-5" />}
              title={t("udash.all_good")}
              description={t("udash.all_good_desc")}
              className="m-5"
            />
          ) : (
            <div className="divide-y divide-border/40">
              {alerts.map((alert) => (
                <div key={alert.id} className="px-4 py-3">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-medium">{alert.title}</span>
                    <StatusBadge label={alert.severity} tone={healthTone(alert.severity)} />
                  </div>
                  <p className="mt-1 text-xs text-muted-foreground">
                    {alert.server_name} · {relativeTime(alert.created_at)}
                  </p>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      </div>

      {attentionServers.length > 0 ? (
        <SectionCard
          title={t("udash.needs_attention")}
          description={`${attentionServers.length} ${t("udash.problems").toLowerCase()}`}
          icon={<AlertTriangle className="h-4 w-4" />}
          bodyClassName="divide-y divide-border/40 p-0"
        >
          {attentionServers.map(({ server, health }) => (
            <div key={server.id} className="flex items-center gap-3 px-4 py-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <span className="truncate text-sm font-medium">{server.name}</span>
                  {health ? <StatusBadge label={health.status} tone={healthTone(health.status)} /> : null}
                </div>
                <p className="mt-1 text-xs text-muted-foreground">
                  {health?.cpu_percent != null ? `CPU ${Math.round(health.cpu_percent)}%` : server.host}
                </p>
              </div>
              <Link to={terminalPath(server)}>
                <Button size="sm" variant="outline" className="text-xs">
                  {t("udash.quick_connect")}
                </Button>
              </Link>
            </div>
          ))}
        </SectionCard>
      ) : null}

      {agentsEnabled ? (
        <div className="grid gap-4 lg:grid-cols-2">
          <SectionCard
            title={t("agent.active_runs")}
            description={activeRuns.length > 0 ? `${activeRuns.length}` : t("agent.no_active")}
            icon={<Activity className="h-4 w-4" />}
            actions={
              <Link to="/agents">
                <Button size="sm" variant="ghost" className="text-xs">
                  {t("agent.view_all")}
                </Button>
              </Link>
            }
            bodyClassName="p-0"
          >
            {activeRuns.length === 0 ? (
              <EmptyState icon={<Activity className="h-5 w-5" />} title={t("agent.no_active")} className="m-5" />
            ) : (
              <div className="divide-y divide-border/40">
                {activeRuns.map((run: DashboardRunItem) => (
                  <div key={run.id} className="flex items-center gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="truncate text-sm font-medium">{run.agent_name}</span>
                        <StatusBadge label={run.status} tone={runTone(run.status)} />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {run.server_name} · {formatDuration(Date.now() - new Date(run.started_at).getTime())}
                      </p>
                    </div>
                    <Button size="sm" variant="outline" className="gap-1 text-xs" onClick={() => navigate(`/agents/run/${run.id}`)}>
                      <Eye className="h-3 w-3" />
                      {t("agent.open")}
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>

          <SectionCard
            title={t("agent.recent_runs")}
            description={recentAgentRuns.length > 0 ? `${recentAgentRuns.length}` : t("agent.no_recent")}
            icon={<Clock className="h-4 w-4" />}
            bodyClassName="p-0"
          >
            {recentAgentRuns.length === 0 ? (
              <EmptyState icon={<Clock className="h-5 w-5" />} title={t("agent.no_recent")} className="m-5" />
            ) : (
              <div className="divide-y divide-border/40">
                {recentAgentRuns.map((run: DashboardRunItem) => (
                  <div key={run.id} className="flex items-center gap-3 px-4 py-3">
                    <div className="min-w-0 flex-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="truncate text-sm font-medium">{run.agent_name}</span>
                        <StatusBadge label={run.status} tone={runTone(run.status)} />
                      </div>
                      <p className="mt-1 text-xs text-muted-foreground">
                        {run.server_name} · {formatDuration(run.duration_ms)} · {relativeTime(run.completed_at || run.started_at)}
                      </p>
                    </div>
                    <Button size="sm" variant="ghost" className="gap-1 text-xs" onClick={() => navigate(`/agents/run/${run.id}`)}>
                      <ExternalLink className="h-3 w-3" />
                      {t("agent.open")}
                    </Button>
                  </div>
                ))}
              </div>
            )}
          </SectionCard>
        </div>
      ) : null}

      {studioEnabled ? (
        <SectionCard
          title={t("dashboard.user.pipeline_runs")}
          description={t("dashboard.user.pipeline_runs_desc")}
          icon={<Workflow className="h-4 w-4" />}
          actions={
            <Link to="/studio/runs">
              <Button size="sm" variant="ghost" className="text-xs">
                {t("dashboard.user.view_pipeline_runs")}
              </Button>
            </Link>
          }
          bodyClassName="p-0"
        >
          {recentPipelines.length === 0 ? (
            <EmptyState icon={<Workflow className="h-5 w-5" />} title={t("dashboard.user.no_pipeline_runs")} className="m-5" />
          ) : (
            <div className="divide-y divide-border/40">
              {recentPipelines.map((run: PipelineRun) => (
                <div key={run.id} className="flex items-center gap-3 px-4 py-3">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2 flex-wrap">
                      <span className="truncate text-sm font-medium">{run.pipeline_name}</span>
                      <StatusBadge label={run.status} tone={runTone(run.status)} />
                    </div>
                    <p className="mt-1 text-xs text-muted-foreground">
                      {relativeTime(run.finished_at || run.started_at || run.created_at)}
                    </p>
                  </div>
                  <Link to={`/studio/pipeline/${run.pipeline_id}`}>
                    <Button size="sm" variant="ghost" className="gap-1 text-xs">
                      <ExternalLink className="h-3 w-3" />
                      {t("agent.open")}
                    </Button>
                  </Link>
                </div>
              ))}
            </div>
          )}
        </SectionCard>
      ) : null}

      {recentActivity.length > 0 ? (
        <SectionCard
          title={t("udash.recent_activity")}
          icon={<Clock className="h-4 w-4" />}
          bodyClassName="divide-y divide-border/40 p-0"
        >
          {recentActivity.map((item) => (
            <div key={item.id} className="px-4 py-3">
              <p className="text-sm font-medium text-foreground">{item.description || item.action}</p>
              <p className="mt-1 text-xs text-muted-foreground">
                {item.entity_name} · {relativeTime(item.created_at)}
              </p>
            </div>
          ))}
        </SectionCard>
      ) : null}

    </PageShell>
  );
}
