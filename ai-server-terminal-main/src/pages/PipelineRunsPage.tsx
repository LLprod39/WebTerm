// @ts-nocheck
import { useState, useEffect, useRef } from "react";
import { useQuery, useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  CheckCircle2,
  XCircle,
  Clock,
  Loader2,
  ChevronDown,
  ChevronUp,
  ArrowLeft,
  Square,
  RotateCcw,
  Workflow,
  ExternalLink,
  Copy,
  AlertTriangle,
  Brain,
  Terminal,
  Activity,
  Zap,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { studioRuns, studioPipelines, type PipelineRun, type PipelineNode } from "@/lib/api";
import { useToast } from "@/hooks/use-toast";

// ---------------------------------------------------------------------------
// Agent event types from WebSocket
// ---------------------------------------------------------------------------
interface AgentEvent {
  event_type: "agent_thought" | "agent_action" | "agent_observation" | "agent_status" | "agent_report";
  data: Record<string, unknown>;
  ts: number;
}

type NodeAgentEvents = Record<string, AgentEvent[]>;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
function fmtDuration(seconds: number | null): string {
  if (!seconds) return "—";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  return `${Math.floor(seconds / 60)}m ${Math.round(seconds % 60)}s`;
}

function fmtDate(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  return d.toLocaleString("ru-RU", { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" });
}

// ---------------------------------------------------------------------------
// Status badge
// ---------------------------------------------------------------------------
function StatusBadge({ status }: { status: string }) {
  const cfg: Record<string, { icon: React.ReactNode; cls: string; label: string }> = {
    completed: { icon: <CheckCircle2 className="h-3 w-3" />, cls: "bg-green-500/15 text-green-400 border-green-500/30", label: "Выполнен" },
    failed:    { icon: <XCircle     className="h-3 w-3" />, cls: "bg-red-500/15 text-red-400 border-red-500/30",     label: "Ошибка"   },
    running:   { icon: <Loader2     className="h-3 w-3 animate-spin" />, cls: "bg-blue-500/15 text-blue-400 border-blue-500/30", label: "Выполняется" },
    pending:   { icon: <Clock       className="h-3 w-3" />, cls: "bg-muted/60 text-muted-foreground border-border",  label: "Ожидание" },
    stopped:   { icon: <Square      className="h-3 w-3" />, cls: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30", label: "Остановлен" },
  };
  const s = cfg[status] || cfg.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-xs font-medium ${s.cls}`}>
      {s.icon}{s.label}
    </span>
  );
}

// ---------------------------------------------------------------------------
// Node state icon
// ---------------------------------------------------------------------------
function NodeIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckCircle2 className="h-3.5 w-3.5 text-green-400 shrink-0" />;
  if (status === "failed")    return <XCircle      className="h-3.5 w-3.5 text-red-400 shrink-0" />;
  if (status === "running")   return <Loader2      className="h-3.5 w-3.5 text-blue-400 animate-spin shrink-0" />;
  if (status === "skipped")   return <AlertTriangle className="h-3.5 w-3.5 text-yellow-400 shrink-0" />;
  return <Clock className="h-3.5 w-3.5 text-muted-foreground shrink-0" />;
}

// ---------------------------------------------------------------------------
// Agent steps for a node
// ---------------------------------------------------------------------------
function AgentSteps({ events }: { events: AgentEvent[] }) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [events.length]);

  if (!events.length) return null;

  return (
    <div className="mt-2 space-y-1.5 max-h-72 overflow-auto pr-1">
      {events.map((ev, i) => {
        if (ev.event_type === "agent_thought") {
          const thought = String(ev.data.thought || "").trim();
          if (!thought) return null;
          return (
            <div key={i} className="flex gap-2 items-start text-xs">
              <Brain className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
              <span className="text-muted-foreground leading-relaxed">{thought}</span>
            </div>
          );
        }
        if (ev.event_type === "agent_action") {
          const tool = String(ev.data.tool || ev.data.action || "");
          const iter = ev.data.iteration ? `#${ev.data.iteration}` : "";
          return (
            <div key={i} className="flex gap-2 items-start text-xs">
              <Zap className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
              <span className="font-mono text-foreground/80">
                {iter && <span className="text-muted-foreground mr-1">{iter}</span>}
                {tool}
                {ev.data.args && (
                  <span className="text-muted-foreground ml-1 font-normal">
                    {JSON.stringify(ev.data.args).slice(0, 120)}
                  </span>
                )}
              </span>
            </div>
          );
        }
        if (ev.event_type === "agent_observation") {
          const obs = String(ev.data.observation || "").trim().slice(0, 300);
          if (!obs) return null;
          return (
            <div key={i} className="flex gap-2 items-start text-xs">
              <Terminal className="h-3.5 w-3.5 text-muted-foreground shrink-0 mt-0.5" />
              <span className="font-mono leading-relaxed whitespace-pre-wrap text-foreground/75">{obs}</span>
            </div>
          );
        }
        if (ev.event_type === "agent_status") {
          const status = String(ev.data.status || "");
          if (!status || status === "connecting") return null;
          const iter = ev.data.iteration ? ` · iter ${ev.data.iteration}` : "";
          return (
            <div key={i} className="flex gap-2 items-center text-xs text-muted-foreground">
              <Activity className="h-3 w-3 shrink-0" />
              <span>{status}{iter}</span>
            </div>
          );
        }
        return null;
      })}
      <div ref={bottomRef} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Run detail panel
// ---------------------------------------------------------------------------
function RunDetail({ runId, onClose }: { runId: number; onClose: () => void }) {
  const { toast } = useToast();
  const [expandedNode, setExpandedNode] = useState<string | null>(null);
  const [showRaw, setShowRaw] = useState(false);
  const [nodeAgentEvents, setNodeAgentEvents] = useState<NodeAgentEvents>({});
  const wsRef = useRef<WebSocket | null>(null);

  const { data: run, refetch } = useQuery({
    queryKey: ["studio", "run", runId],
    queryFn: () => studioRuns.get(runId),
    refetchInterval: (query) => {
      const s = query.state.data?.status;
      return s === "running" || s === "pending" ? 2000 : false;
    },
    refetchIntervalInBackground: true,
  });

  // WebSocket connection for live agent events
  useEffect(() => {
    const proto = window.location.protocol === "https:" ? "wss" : "ws";
    const url = `${proto}://${window.location.host}/ws/studio/pipeline-runs/${runId}/live/`;
    const ws = new WebSocket(url);
    wsRef.current = ws;

    ws.onmessage = (e) => {
      try {
        const msg = JSON.parse(e.data);
        if (msg.type === "node_event" && msg.event_type && msg.node_id) {
          const ev: AgentEvent = { event_type: msg.event_type, data: msg.data || {}, ts: Date.now() };
          setNodeAgentEvents((prev) => ({
            ...prev,
            [msg.node_id]: [...(prev[msg.node_id] || []), ev],
          }));
          // Auto-expand the node that has activity
          setExpandedNode((cur) => cur ?? msg.node_id);
        }
      } catch {
        // ignore
      }
    };

    ws.onerror = () => {};
    ws.onclose = () => {};

    return () => {
      ws.close();
      wsRef.current = null;
    };
  }, [runId]);

  const stopMutation = useMutation({
    mutationFn: () => studioRuns.stop(runId),
    onSuccess: () => { refetch(); toast({ description: "Run stopped" }); },
  });

  const navigate = useNavigate();

  if (!run) {
    return (
      <div className="flex items-center justify-center h-full text-muted-foreground text-sm">
        <Loader2 className="h-4 w-4 animate-spin mr-2" /> Загрузка…
      </div>
    );
  }

  const nodeStates: Record<string, Record<string, unknown>> =
    (run.node_states as Record<string, Record<string, unknown>>) || {};
  const nodes: PipelineNode[] = (run.nodes_snapshot || []).filter(
    (n) => !n.type?.startsWith("trigger/")
  );

  const copyOutput = (text: string) => {
    navigator.clipboard.writeText(text).then(() => toast({ description: "Скопировано" }));
  };

  return (
    <div className="flex flex-col h-full overflow-hidden">
      <div className="flex items-center justify-between px-5 py-3 border-b border-border bg-card shrink-0">
        <div className="flex items-center gap-3">
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground">
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm">Run #{run.id}</span>
              <StatusBadge status={run.status} />
            </div>
            <div className="text-xs text-muted-foreground mt-0.5">
              {run.pipeline_name} · {fmtDate(run.started_at || run.created_at)} · {fmtDuration(run.duration_seconds)}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          {(run.status === "running" || run.status === "pending") && (
            <Button size="sm" variant="destructive" className="h-7 text-xs gap-1"
              onClick={() => stopMutation.mutate()} disabled={stopMutation.isPending}>
              <Square className="h-3 w-3" /> Стоп
            </Button>
          )}
          <Button size="sm" variant="outline" className="h-7 text-xs gap-1"
            onClick={() => navigate(`/studio/pipeline/${run.pipeline_id}`)}>
            <ExternalLink className="h-3 w-3" /> Открыть пайплайн
          </Button>
          <Button size="sm" variant="ghost" className="h-7 text-xs gap-1" onClick={() => refetch()}>
            <RotateCcw className="h-3 w-3" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="p-5 space-y-5">
          {/* Error banner */}
          {run.error && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              <div className="font-medium mb-1 flex items-center gap-1.5">
                <XCircle className="h-4 w-4" /> Ошибка выполнения
              </div>
              <pre className="whitespace-pre-wrap text-xs font-mono">{run.error}</pre>
            </div>
          )}

          {run.summary && (
            <div className="rounded-lg border border-border bg-card/60">
              <div className="flex items-center justify-between px-4 py-2 border-b border-border">
                <span className="text-sm font-medium">📋 Отчёт</span>
                <Button size="sm" variant="ghost" className="h-6 text-xs gap-1" onClick={() => copyOutput(run.summary)}>
                  <Copy className="h-3 w-3" /> Копировать
                </Button>
              </div>
              <div className="px-4 py-3 text-xs text-muted-foreground font-mono whitespace-pre-wrap leading-relaxed max-h-80 overflow-auto">
                {run.summary}
              </div>
            </div>
          )}

          <div>
            <div className="text-sm font-medium mb-2 text-muted-foreground">Узлы ({nodes.length})</div>
            <div className="space-y-2">
              {nodes.map((node) => {
                const st = nodeStates[node.id] || {};
                const status = (st.status as string) || "pending";
                const output = (st.output as string) || "";
                const error = (st.error as string) || "";
                const isExp = expandedNode === node.id;
                const agentEvents = nodeAgentEvents[node.id] || [];
                const hasContent = !!(output || error || agentEvents.length);
                const startedAt = st.started_at as string | undefined;
                const finishedAt = st.finished_at as string | undefined;
                const isAgentNode = node.type?.startsWith("agent/");

                let duration = "";
                if (startedAt && finishedAt) {
                  const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
                  duration = ms < 1000 ? `${ms}ms` : `${(ms / 1000).toFixed(1)}s`;
                }

                // Count agent iterations for the badge
                const iterCount = agentEvents.filter((e) => e.event_type === "agent_action").length;

                return (
                  <div key={node.id} className={`rounded-lg border transition-colors ${
                    status === "failed"    ? "border-red-500/20 bg-background/24"
                    : status === "completed" ? "border-green-500/16 bg-background/24"
                    : status === "running"   ? "border-primary/20 bg-background/24"
                    : status === "skipped"   ? "border-amber-500/18 bg-background/24"
                    : "border-border/70 bg-background/24"
                  }`}>
                    <button
                      className="w-full flex items-center gap-3 px-4 py-2.5 text-left"
                      onClick={() => hasContent && setExpandedNode(isExp ? null : node.id)}
                    >
                      <NodeIcon status={status} />
                      <div className="flex-1 min-w-0">
                        <div className="font-medium text-sm truncate">{(node.data?.label as string) || node.id}</div>
                        <div className="text-xs text-muted-foreground">{node.type}</div>
                      </div>
                      {isAgentNode && iterCount > 0 && (
                        <span className="text-xs text-purple-400 shrink-0 flex items-center gap-1">
                          <Brain className="h-3 w-3" />{iterCount}
                        </span>
                      )}
                      {duration && <span className="text-xs text-muted-foreground shrink-0">{duration}</span>}
                      {hasContent && (
                        isExp
                          ? <ChevronUp className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                          : <ChevronDown className="h-3.5 w-3.5 text-muted-foreground shrink-0" />
                      )}
                    </button>

                    {isExp && hasContent && (
                      <div className="border-t border-border px-4 py-3 space-y-2">
                        {/* Live agent steps */}
                        {isAgentNode && agentEvents.length > 0 && (
                          <div className="rounded-lg border border-border/60 bg-background/18 px-3 py-2">
                            <div className="text-xs text-muted-foreground mb-2 flex items-center gap-1.5">
                              <Activity className="h-3 w-3 text-blue-400" />
                              <span>Шаги агента · {iterCount} действий</span>
                            </div>
                            <AgentSteps events={agentEvents} />
                          </div>
                        )}
                        {error && (
                          <div className="rounded-lg bg-red-500/5 px-3 py-2 font-mono text-xs text-red-300">
                            {error}
                          </div>
                        )}
                        {output && (
                          <div className="relative">
                            <Button
                              size="sm" variant="ghost"
                              className="absolute right-1 top-1 h-6 text-xs gap-1 z-10"
                              onClick={() => copyOutput(output)}
                            >
                              <Copy className="h-3 w-3" />
                            </Button>
                            <pre className="text-xs text-muted-foreground font-mono whitespace-pre-wrap break-all leading-relaxed bg-muted/20 rounded px-3 py-2 max-h-96 overflow-auto pr-16">
                              {output.length > 5000 ? output.slice(0, 5000) + "\n\n… [обрезано, полный вывод > 5000 символов]" : output}
                            </pre>
                          </div>
                        )}
                      </div>
                    )}
                  </div>
                );
              })}

              {nodes.length === 0 && (
                <div className="text-center py-8 text-muted-foreground text-sm">
                  Нет данных по узлам — пайплайн ещё не запускался или не сохранил snapshot
                </div>
              )}
            </div>
          </div>

          <div>
            <button
              className="text-xs text-muted-foreground hover:text-foreground flex items-center gap-1"
              onClick={() => setShowRaw(!showRaw)}
            >
              {showRaw ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              Raw JSON (для отладки)
            </button>
            {showRaw && (
              <pre className="mt-2 text-xs font-mono text-muted-foreground bg-muted/20 rounded px-4 py-3 max-h-96 overflow-auto">
                {JSON.stringify({ status: run.status, error: run.error, node_states: run.node_states, context: run.context }, null, 2)}
              </pre>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Runs list
// ---------------------------------------------------------------------------
const STATUS_FILTERS = ["all", "running", "completed", "failed", "pending", "stopped"] as const;
type StatusFilter = typeof STATUS_FILTERS[number];

export default function PipelineRunsPage() {
  const navigate = useNavigate();
  const [selectedRunId, setSelectedRunId] = useState<number | null>(null);
  const [statusFilter, setStatusFilter] = useState<StatusFilter>("all");
  const [pipelineFilter, setPipelineFilter] = useState<number | null>(null);

  const { data: runs = [], isLoading, refetch } = useQuery({
    queryKey: ["studio", "runs"],
    queryFn: studioRuns.list,
    refetchInterval: 5000,
  });

  const { data: pipelines = [] } = useQuery({
    queryKey: ["studio", "pipelines"],
    queryFn: () => studioPipelines.list(),
  });

  const filtered = runs.filter((r) => {
    if (statusFilter !== "all" && r.status !== statusFilter) return false;
    if (pipelineFilter && r.pipeline_id !== pipelineFilter) return false;
    return true;
  });

  const selectedRun = selectedRunId ? runs.find((r) => r.id === selectedRunId) : null;

  const statusCount = (s: string) => runs.filter((r) => r.status === s).length;

  useEffect(() => {
    if (!filtered.length) {
      setSelectedRunId(null);
      return;
    }

    if (!selectedRunId || !filtered.some((run) => run.id === selectedRunId)) {
      setSelectedRunId(filtered[0].id);
    }
  }, [filtered, selectedRunId]);

  return (
    <div className="flex h-full">
      {/* Left: runs list */}
      <div className={`flex flex-col border-r border-border ${selectedRunId ? "w-80 shrink-0" : "flex-1"}`}>
        {/* Header */}
        <div className="px-5 py-4 border-b border-border bg-card shrink-0">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <button onClick={() => navigate("/studio")} className="text-muted-foreground hover:text-foreground">
                <ArrowLeft className="h-4 w-4" />
              </button>
              <h1 className="text-base font-semibold flex items-center gap-2">
                <Workflow className="h-4 w-4 text-primary" />
                История запусков
              </h1>
            </div>
            <div className="flex items-center gap-2">
              <Button size="sm" variant="ghost" className="h-7" onClick={() => refetch()}>
                <RotateCcw className="h-3.5 w-3.5" />
              </Button>
            </div>
          </div>

          {/* Stats */}
          <div className="flex gap-3 text-xs text-muted-foreground mb-3">
            <span className="text-green-400 font-medium">{statusCount("completed")} выполнено</span>
            <span className="text-red-400 font-medium">{statusCount("failed")} ошибок</span>
            <span className="text-blue-400 font-medium">{statusCount("running")} активных</span>
          </div>

          {/* Filters */}
          <div className="flex gap-1 flex-wrap">
            {STATUS_FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => setStatusFilter(s)}
                className={`px-2 py-0.5 rounded text-xs border transition-colors ${
                  statusFilter === s
                    ? "bg-primary text-primary-foreground border-primary"
                    : "border-border text-muted-foreground hover:text-foreground hover:bg-muted/40"
                }`}
              >
                {s === "all" ? `Все (${runs.length})` : s}
              </button>
            ))}
          </div>
        </div>

        {/* List */}
        <div className="flex-1 overflow-auto">
          {isLoading && (
            <div className="flex items-center justify-center py-12 text-muted-foreground text-sm">
              <Loader2 className="h-4 w-4 animate-spin mr-2" /> Загрузка…
            </div>
          )}

          {!isLoading && filtered.length === 0 && (
            <div className="flex flex-col items-center justify-center py-16 text-muted-foreground text-sm gap-2">
              <Workflow className="h-8 w-8 text-muted-foreground/30" />
              <p>Нет запусков</p>
              <Button size="sm" variant="outline" className="mt-2" onClick={() => navigate("/studio")}>
                Перейти к пайплайнам
              </Button>
            </div>
          )}

          {filtered.map((run) => (
            <button
              key={run.id}
              onClick={() => setSelectedRunId(run.id === selectedRunId ? null : run.id)}
              className={`w-full text-left px-4 py-3 border-b border-border hover:bg-muted/30 transition-colors ${
                selectedRunId === run.id ? "bg-muted/40 border-l-2 border-l-primary" : ""
              }`}
            >
              <div className="flex items-center justify-between gap-2 mb-1">
                <span className="font-medium text-sm truncate">{run.pipeline_name}</span>
                <StatusBadge status={run.status} />
              </div>
              <div className="flex items-center gap-2 text-xs text-muted-foreground">
                <span>Run #{run.id}</span>
                <span>·</span>
                <span>{fmtDate(run.started_at || run.created_at)}</span>
                {run.duration_seconds && (
                  <>
                    <span>·</span>
                    <span>{fmtDuration(run.duration_seconds)}</span>
                  </>
                )}
              </div>
              {run.error && (
                <div className="mt-1 text-xs text-red-400 truncate">{run.error}</div>
              )}
            </button>
          ))}
        </div>
      </div>

      {/* Right: run detail */}
      {selectedRunId && (
        <div className="flex-1 overflow-hidden">
          <RunDetail runId={selectedRunId} onClose={() => setSelectedRunId(null)} />
        </div>
      )}
    </div>
  );
}
