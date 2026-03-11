// @ts-nocheck
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  aiAnalyzeServer,
  deleteAgent,
  fetchAgentDashboardRuns,
  fetchAgents,
  fetchMonitoringDashboard,
  resolveAlert,
  runAgent,
  stopAgent,
  type AgentItem,
  type DashboardRunItem,
  type ServerAlertItem,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import {
  Activity,
  AlertTriangle,
  Bell,
  Bot,
  CheckCircle2,
  Clock,
  ExternalLink,
  Eye,
  FileText,
  Plus,
  RefreshCw,
  Server,
  Shield,
  Square,
  Terminal,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import ReactMarkdown from "react-markdown";
import { Link, useNavigate } from "react-router-dom";
import { useState } from "react";

function relativeTime(iso: string | null): string {
  if (!iso) return "now";
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "now";
  if (mins < 60) return `${mins}m`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours}h`;
  return `${Math.floor(hours / 24)}d`;
}

function formatDuration(ms: number): string {
  if (!ms) return "0ms";
  if (ms < 1000) return `${ms}ms`;
  const secs = Math.floor(ms / 1000);
  if (secs < 60) return `${secs}s`;
  const mins = Math.floor(secs / 60);
  return `${mins}m ${secs % 60}s`;
}

const AGENT_ICONS: Record<string, string> = {
  security_audit: "🔒",
  security_patrol: "🛡️",
  log_analyzer: "📋",
  log_investigator: "🔎",
  performance: "⚡",
  disk_report: "💾",
  docker_status: "🐳",
  service_health: "⚙️",
  deploy_manager: "🚀",
  health_checker: "💓",
  backup_manager: "📦",
  custom: "🔧",
};

function statusColor(status: string): string {
  if (status === "completed" || status === "healthy" || status === "running") return "text-green-400";
  if (status === "warning" || status === "paused" || status === "waiting") return "text-yellow-400";
  if (status === "failed" || status === "critical" || status === "unreachable") return "text-red-400";
  return "text-muted-foreground";
}

export default function UserDashboard() {
  const { t } = useI18n();
  const queryClient = useQueryClient();
  const navigate = useNavigate();
  const [analyzingServerId, setAnalyzingServerId] = useState<number | null>(null);
  const [analysisResult, setAnalysisResult] = useState<{ name: string; text: string } | null>(null);
  const [runningAgentId, setRunningAgentId] = useState<number | null>(null);
  const [stoppingAgentId, setStoppingAgentId] = useState<number | null>(null);
  const [reportOpen, setReportOpen] = useState<DashboardRunItem | null>(null);

  const { data, isLoading, error } = useQuery({
    queryKey: ["monitoring", "dashboard"],
    queryFn: fetchMonitoringDashboard,
    refetchInterval: 30_000,
  });

  const { data: agentsData } = useQuery({
    queryKey: ["agents", "list"],
    queryFn: fetchAgents,
    staleTime: 15_000,
  });

  const { data: runsData } = useQuery({
    queryKey: ["agents", "dashboard-runs"],
    queryFn: fetchAgentDashboardRuns,
    refetchInterval: 5_000,
  });

  const refresh = async () => {
    await queryClient.invalidateQueries({ queryKey: ["monitoring"] });
    await queryClient.invalidateQueries({ queryKey: ["agents"] });
    await queryClient.invalidateQueries({ queryKey: ["agents", "dashboard-runs"] });
  };

  const onResolve = async (alertId: number) => {
    await resolveAlert(alertId);
    await refresh();
  };

  const onAnalyze = async (serverId: number) => {
    setAnalyzingServerId(serverId);
    try {
      const result = await aiAnalyzeServer(serverId);
      setAnalysisResult({ name: result.server_name, text: result.analysis });
    } catch {
      setAnalysisResult({ name: "Error", text: "AI analysis failed." });
    } finally {
      setAnalyzingServerId(null);
    }
  };

  const onRunAgent = async (agent: AgentItem) => {
    setRunningAgentId(agent.id);
    try {
      const result = await runAgent(agent.id);
      if (agent.mode === "full" && result.run_id) {
        navigate(`/agents/run/${result.run_id}`);
        return;
      }
      if (result.runs?.length) {
        setAnalysisResult({
          name: result.runs[0].server_name || agent.name,
          text: result.runs[0].ai_analysis || "Agent run completed.",
        });
      }
      await refresh();
    } finally {
      setRunningAgentId(null);
    }
  };

  const onStopAgent = async (agentId: number) => {
    setStoppingAgentId(agentId);
    try {
      await stopAgent(agentId);
      await refresh();
    } finally {
      setStoppingAgentId(null);
    }
  };

  const onDeleteAgent = async (agentId: number) => {
    if (!confirm(t("agent.delete_confirm"))) return;
    await deleteAgent(agentId);
    await refresh();
  };

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">{t("dash.loading")}</div>;
  }

  if (error || !data) {
    return <div className="p-6 text-sm text-destructive">{t("dash.error")}</div>;
  }

  const alerts = data.alerts || [];
  const summary = data.summary;
  const agents = agentsData?.agents || [];
  const activeRuns = runsData?.active || [];
  const recentRuns = runsData?.recent || [];
  const problemCount = summary.critical + summary.warning + summary.unreachable;

  return (
    <div className="mx-auto max-w-6xl space-y-4 p-5">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-lg font-semibold text-foreground">{t("udash.title")}</h1>
          <p className="text-xs text-muted-foreground">
            {summary.total_servers} servers · {agents.length} agents · {activeRuns.length} active
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Link to="/agents">
            <Button size="sm" variant="outline" className="gap-1.5 h-7 text-xs">
              <Plus className="h-3.5 w-3.5" />
              Agents
            </Button>
          </Link>
          <Button size="sm" variant="ghost" className="gap-1.5 h-7 text-xs" onClick={() => void refresh()}>
            <RefreshCw className="h-3.5 w-3.5" />
            Refresh
          </Button>
        </div>
      </div>

      <div className="grid gap-4 md:grid-cols-4">
        <div className="rounded-lg border border-border bg-card p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs uppercase tracking-wide text-muted-foreground">Servers</span>
            <Server className="h-4 w-4 text-primary" />
          </div>
          <div className="text-2xl font-semibold text-foreground">{summary.total_servers}</div>
          <div className="text-xs text-muted-foreground">{summary.healthy} healthy</div>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs uppercase tracking-wide text-muted-foreground">Problems</span>
            <AlertTriangle className={`h-4 w-4 ${problemCount > 0 ? "text-red-400" : "text-green-400"}`} />
          </div>
          <div className={`text-2xl font-semibold ${problemCount > 0 ? "text-red-400" : "text-green-400"}`}>{problemCount}</div>
          <div className="text-xs text-muted-foreground">
            {summary.critical} critical, {summary.warning} warning, {summary.unreachable} down
          </div>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs uppercase tracking-wide text-muted-foreground">Alerts</span>
            <Bell className={`h-4 w-4 ${alerts.length > 0 ? "text-yellow-400" : "text-muted-foreground"}`} />
          </div>
          <div className="text-2xl font-semibold text-foreground">{alerts.length}</div>
          <div className="text-xs text-muted-foreground">Open monitoring alerts</div>
        </div>

        <div className="rounded-lg border border-border bg-card p-4">
          <div className="mb-2 flex items-center justify-between">
            <span className="text-xs uppercase tracking-wide text-muted-foreground">Fleet Load</span>
            <Activity className="h-4 w-4 text-blue-400" />
          </div>
          <div className="text-2xl font-semibold text-foreground">{Math.round(summary.avg_cpu || 0)}%</div>
          <div className="text-xs text-muted-foreground">
            RAM {Math.round(summary.avg_memory || 0)}%, disk {Math.round(summary.avg_disk || 0)}%
          </div>
        </div>
      </div>

      {alerts.length > 0 && (
        <section className="overflow-hidden rounded-lg border border-border bg-card">
          <div className="flex items-center gap-2 border-b border-border bg-secondary/20 px-4 py-3">
            <Shield className="h-4 w-4 text-red-400" />
            <span className="text-sm font-medium text-foreground">Open Alerts</span>
          </div>
          <div className="divide-y divide-border/50">
            {alerts.slice(0, 8).map((alert: ServerAlertItem) => (
              <div key={alert.id} className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className={`text-xs font-semibold uppercase ${statusColor(alert.severity)}`}>
                      {alert.severity}
                    </span>
                    <span className="truncate text-sm font-medium text-foreground">{alert.title}</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {alert.server_name} · {relativeTime(alert.created_at)}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    size="sm"
                    variant="ghost"
                    className="gap-1 text-xs"
                    disabled={analyzingServerId === alert.server_id}
                    onClick={() => void onAnalyze(alert.server_id)}
                  >
                    <Bot className={`h-3 w-3 ${analyzingServerId === alert.server_id ? "animate-spin" : ""}`} />
                    Analyze
                  </Button>
                  <Link to={`/servers/${alert.server_id}/terminal`}>
                    <Button size="sm" variant="outline" className="gap-1 text-xs">
                      <Terminal className="h-3 w-3" />
                      Open
                    </Button>
                  </Link>
                  <Button size="sm" variant="ghost" className="text-xs text-destructive" onClick={() => void onResolve(alert.id)}>
                    Resolve
                  </Button>
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {analysisResult && (
        <section className="overflow-hidden rounded-lg border border-primary/20 bg-card">
          <div className="flex items-center justify-between border-b border-primary/10 bg-primary/5 px-4 py-3">
            <div>
              <div className="text-sm font-medium text-foreground">{analysisResult.name}</div>
              <div className="text-xs text-muted-foreground">Latest AI analysis</div>
            </div>
            <Button size="sm" variant="ghost" className="h-7 w-7 p-0" onClick={() => setAnalysisResult(null)}>
              <X className="h-4 w-4" />
            </Button>
          </div>
          <div className="prose prose-sm prose-invert max-w-none px-4 py-4 text-sm [&_p]:text-sm">
            <ReactMarkdown>{analysisResult.text}</ReactMarkdown>
          </div>
        </section>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <section className="overflow-hidden rounded-lg border border-border bg-card">
          <div className="flex items-center gap-2 border-b border-border bg-secondary/20 px-4 py-3">
            <Activity className="h-4 w-4 text-blue-400" />
            <span className="text-sm font-medium text-foreground">Active Runs</span>
            <span className="text-xs text-muted-foreground">{activeRuns.length}</span>
          </div>
          {activeRuns.length === 0 ? (
            <div className="px-4 py-6 text-sm text-muted-foreground">No active agent runs.</div>
          ) : (
            <div className="divide-y divide-border/40">
              {activeRuns.map((run: DashboardRunItem) => (
                <div key={run.id} className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="text-base">{AGENT_ICONS[run.agent_type] || "🤖"}</span>
                      <span className="truncate text-sm font-medium text-foreground">{run.agent_name}</span>
                      <span className={`text-xs ${statusColor(run.status)}`}>{run.status}</span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {run.server_name} · {formatDuration(Date.now() - new Date(run.started_at).getTime())}
                    </div>
                    {run.pending_question ? (
                      <div className="mt-1 text-xs text-orange-300">{run.pending_question}</div>
                    ) : null}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button size="sm" variant="outline" className="gap-1 text-xs" onClick={() => navigate(`/agents/run/${run.id}`)}>
                      <Eye className="h-3 w-3" />
                      Open
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      className="gap-1 text-xs text-destructive"
                      disabled={stoppingAgentId === run.agent_id}
                      onClick={() => void onStopAgent(run.agent_id)}
                    >
                      {stoppingAgentId === run.agent_id ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Square className="h-3 w-3" />}
                      Stop
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>

        <section className="overflow-hidden rounded-lg border border-border bg-card">
          <div className="flex items-center gap-2 border-b border-border bg-secondary/20 px-4 py-3">
            <Clock className="h-4 w-4 text-muted-foreground" />
            <span className="text-sm font-medium text-foreground">Recent Runs</span>
            <span className="text-xs text-muted-foreground">{recentRuns.length}</span>
          </div>
          {recentRuns.length === 0 ? (
            <div className="px-4 py-6 text-sm text-muted-foreground">No recent runs.</div>
          ) : (
            <div className="divide-y divide-border/40">
              {recentRuns.map((run: DashboardRunItem) => (
                <div key={run.id} className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center">
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      {run.status === "completed" ? (
                        <CheckCircle2 className="h-4 w-4 text-green-400" />
                      ) : run.status === "failed" ? (
                        <X className="h-4 w-4 text-red-400" />
                      ) : (
                        <Square className="h-4 w-4 text-muted-foreground" />
                      )}
                      <span className="truncate text-sm font-medium text-foreground">{run.agent_name}</span>
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {run.server_name} · {formatDuration(run.duration_ms)} · {relativeTime(run.completed_at || run.started_at)}
                    </div>
                  </div>
                  <div className="flex items-center gap-2">
                    {(run.final_report || run.ai_analysis) ? (
                      <Button size="sm" variant="outline" className="gap-1 text-xs" onClick={() => setReportOpen(run)}>
                        <FileText className="h-3 w-3" />
                        Report
                      </Button>
                    ) : null}
                    <Button size="sm" variant="ghost" className="gap-1 text-xs" onClick={() => navigate(`/agents/run/${run.id}`)}>
                      <ExternalLink className="h-3 w-3" />
                      Open
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}
        </section>
      </div>

      <section className="overflow-hidden rounded-lg border border-border bg-card">
        <div className="flex items-center justify-between border-b border-border bg-secondary/20 px-4 py-3">
          <div className="flex items-center gap-2">
            <Bot className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium text-foreground">Agents</span>
            <span className="text-xs text-muted-foreground">{agents.length}</span>
          </div>
          <Link to="/agents">
            <Button size="sm" variant="ghost" className="gap-1 text-xs">
              Manage all
            </Button>
          </Link>
        </div>
        {agents.length === 0 ? (
          <div className="px-4 py-6 text-sm text-muted-foreground">No agents configured yet.</div>
        ) : (
          <div className="divide-y divide-border/40">
            {agents.slice(0, 6).map((agent: AgentItem) => (
              <div key={agent.id} className="flex flex-col gap-3 px-4 py-3 md:flex-row md:items-center">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <span className="text-base">{AGENT_ICONS[agent.agent_type] || "🔧"}</span>
                    <span className="truncate text-sm font-medium text-foreground">{agent.name}</span>
                    <span className="text-xs text-muted-foreground">{agent.mode}</span>
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {agent.server_count} servers
                    {agent.last_run_at ? ` · last run ${relativeTime(agent.last_run_at)}` : ""}
                    {agent.schedule_minutes ? ` · every ${agent.schedule_minutes}m` : ""}
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {agent.active_run_id ? (
                    <Button size="sm" variant="outline" className="gap-1 text-xs" onClick={() => navigate(`/agents/run/${agent.active_run_id}`)}>
                      <Eye className="h-3 w-3" />
                      Open
                    </Button>
                  ) : (
                    <Button
                      size="sm"
                      variant="outline"
                      className="gap-1 text-xs"
                      disabled={runningAgentId === agent.id}
                      onClick={() => void onRunAgent(agent)}
                    >
                      {runningAgentId === agent.id ? <RefreshCw className="h-3 w-3 animate-spin" /> : <Activity className="h-3 w-3" />}
                      Run
                    </Button>
                  )}
                  <Button size="sm" variant="ghost" className="gap-1 text-xs text-destructive" onClick={() => void onDeleteAgent(agent.id)}>
                    <Trash2 className="h-3 w-3" />
                    Delete
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      {data.servers.length > 0 ? (
        <section className="rounded-lg border border-border bg-card p-4">
          <div className="mb-3 flex items-center gap-2">
            <Server className="h-4 w-4 text-primary" />
            <span className="text-sm font-medium text-foreground">Server Status</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {data.servers.map((server) => (
              <div
                key={server.server_id}
                className="flex items-center gap-2 rounded-full border border-border/70 bg-background/40 px-3 py-1.5 text-xs"
                title={`CPU ${server.cpu_percent ?? "—"}% · RAM ${server.memory_percent ?? "—"}% · Disk ${server.disk_percent ?? "—"}%`}
              >
                <span className={`h-2 w-2 rounded-full ${statusColor(server.status).replace("text-", "bg-")}`} />
                <span className="text-foreground">{server.server_name}</span>
              </div>
            ))}
          </div>
        </section>
      ) : null}

      <Dialog open={!!reportOpen} onOpenChange={() => setReportOpen(null)}>
        <DialogContent className="w-[95vw] max-w-3xl">
          <DialogHeader>
            <DialogTitle className="flex items-center gap-2">
              <FileText className="h-4 w-4 text-primary" />
              <span>{reportOpen?.agent_name || "Run Report"}</span>
            </DialogTitle>
          </DialogHeader>
          <DialogBody className="max-h-[70vh] overflow-y-auto">
            {reportOpen ? (
              <>
                <div className="mb-4 flex flex-wrap items-center gap-3 border-b border-border pb-3 text-xs text-muted-foreground">
                  <span>{reportOpen.server_name}</span>
                  <span>{reportOpen.status}</span>
                  <span>{formatDuration(reportOpen.duration_ms)}</span>
                  <span>{relativeTime(reportOpen.completed_at || reportOpen.started_at)}</span>
                </div>
                <div className="prose prose-sm prose-invert max-w-none [&_p]:text-sm">
                  <ReactMarkdown>{reportOpen.final_report || reportOpen.ai_analysis || "No report available."}</ReactMarkdown>
                </div>
              </>
            ) : null}
          </DialogBody>
          <DialogFooter>
            {reportOpen ? (
              <Button size="sm" variant="outline" className="gap-1 text-xs" onClick={() => navigate(`/agents/run/${reportOpen.id}`)}>
                <ExternalLink className="h-3 w-3" />
                Open full run
              </Button>
            ) : null}
            <Button size="sm" onClick={() => setReportOpen(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
