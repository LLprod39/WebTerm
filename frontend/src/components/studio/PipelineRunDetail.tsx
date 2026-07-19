import { useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  Activity,
  AlertTriangle,
  ArrowLeft,
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronUp,
  Clock,
  Copy,
  ExternalLink,
  FileText,
  Loader2,
  RotateCcw,
  Square,
  Terminal,
  XCircle,
  Zap,
} from "lucide-react";

import { useToast } from "@/hooks/use-toast";
import { getStudioPipelineRunWsUrl, studioRuns, type PipelineNode, type PipelineRun } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { formatRunDate, formatRunDuration } from "./pipelineRunFormatters";

interface AgentEvent {
  event_type: "agent_thought" | "agent_action" | "agent_observation" | "agent_status" | "agent_report";
  data: Record<string, unknown>;
  ts: number;
}

type NodeAgentEvents = Record<string, AgentEvent[]>;

export function StatusBadge({ status, lang }: { status: string; lang: string }) {
  const cfg: Record<string, { icon: React.ReactNode; cls: string; label: string }> = {
    completed: { icon: <CheckCircle2 className="h-3 w-3" />, cls: "bg-green-500/15 text-green-400 border-green-500/30", label: localize(lang, "Выполнен", "Completed") },
    failed: { icon: <XCircle className="h-3 w-3" />, cls: "bg-red-500/15 text-red-400 border-red-500/30", label: localize(lang, "Ошибка", "Failed") },
    running: { icon: <Loader2 className="h-3 w-3 animate-spin" />, cls: "bg-blue-500/15 text-blue-400 border-blue-500/30", label: localize(lang, "В работе", "Running") },
    pending: { icon: <Clock className="h-3 w-3" />, cls: "bg-muted/60 text-muted-foreground border-border", label: localize(lang, "Ожидание", "Pending") },
    stopped: { icon: <Square className="h-3 w-3" />, cls: "bg-yellow-500/15 text-yellow-400 border-yellow-500/30", label: localize(lang, "Остановлен", "Stopped") },
  };
  const s = cfg[status] || cfg.pending;
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full border text-xs font-medium ${s.cls}`}>
      {s.icon}{s.label}
    </span>
  );
}

function NodeIcon({ status }: { status: string }) {
  if (status === "completed") return <CheckCircle2 className="h-3.5 w-3.5 text-green-400 shrink-0" />;
  if (status === "failed") return <XCircle className="h-3.5 w-3.5 text-red-400 shrink-0" />;
  if (status === "running") return <Loader2 className="h-3.5 w-3.5 text-blue-400 animate-spin shrink-0" />;
  if (status === "skipped") return <AlertTriangle className="h-3.5 w-3.5 text-yellow-400 shrink-0" />;
  return <Clock className="h-3.5 w-3.5 text-muted-foreground shrink-0" />;
}

function formatNodeDuration(ms: number, lang: string): string {
  if (ms < 1000) return localize(lang, `${ms} мс`, `${ms}ms`);
  return localize(lang, `${(ms / 1000).toFixed(1)} с`, `${(ms / 1000).toFixed(1)}s`);
}

function AgentSteps({ events, lang }: { events: AgentEvent[]; lang: string }) {
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
                {Boolean(ev.data.args) && (
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
          const iter = ev.data.iteration ? localize(lang, ` · итерация ${ev.data.iteration}`, ` · iter ${ev.data.iteration}`) : "";
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

export function PipelineRunDetail({ runId, onClose, lang }: { runId: number; onClose: () => void; lang: string }) {
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
  const liveEnabled = run?.status === "running" || run?.status === "pending";

  useEffect(() => {
    if (!liveEnabled) return;
    let cancelled = false;
    let reconnectTimer: number | null = null;
    let attempts = 0;

    const connect = () => {
      if (cancelled) return;
      const ws = new WebSocket(getStudioPipelineRunWsUrl(runId));
      wsRef.current = ws;
      ws.onopen = () => {
        attempts = 0;
      };
      ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          if (msg.type === "node_event" && msg.event_type && msg.node_id) {
            const ev: AgentEvent = { event_type: msg.event_type, data: msg.data || {}, ts: Date.now() };
            setNodeAgentEvents((prev) => ({ ...prev, [msg.node_id]: [...(prev[msg.node_id] || []), ev] }));
            setExpandedNode((cur) => cur ?? msg.node_id);
          }
        } catch {
          // ignore
        }
      };
      ws.onerror = () => {};
      ws.onclose = () => {
        if (wsRef.current === ws) wsRef.current = null;
        if (cancelled) return;
        attempts += 1;
        const delay = Math.min(5000, attempts <= 1 ? 1000 : attempts <= 2 ? 2000 : 4000);
        reconnectTimer = window.setTimeout(() => {
          reconnectTimer = null;
          connect();
        }, delay);
      };
    };

    connect();

    return () => {
      cancelled = true;
      if (reconnectTimer !== null) window.clearTimeout(reconnectTimer);
      wsRef.current?.close();
      wsRef.current = null;
    };
  }, [liveEnabled, runId]);

  useEffect(() => {
    setNodeAgentEvents({});
    setExpandedNode(null);
  }, [runId]);

  const stopMutation = useMutation({
    mutationFn: () => studioRuns.stop(runId),
    onSuccess: () => {
      refetch();
      toast({ description: localize(lang, "Запуск остановлен", "Run stopped") });
    },
  });

  const navigate = useNavigate();

  if (!run) {
    return (
      <div className="flex h-full items-center justify-center text-sm text-muted-foreground">
        <Loader2 className="mr-2 h-4 w-4 animate-spin" /> {localize(lang, "Загрузка…", "Loading…")}
      </div>
    );
  }

  const nodeStates: PipelineRun["node_states"] = run.node_states || {};
  const nodes: PipelineNode[] = (run.nodes_snapshot || []).filter((n) => !n.type?.startsWith("trigger/"));
  const copyOutput = (text: string) => {
    navigator.clipboard.writeText(text).then(() => toast({ description: localize(lang, "Скопировано", "Copied") }));
  };

  return (
    <div className="flex h-full flex-col overflow-hidden">
      <div className="flex shrink-0 flex-col gap-3 border-b border-border bg-card px-4 py-3 sm:flex-row sm:items-center sm:justify-between sm:px-5">
        <div className="flex min-w-0 items-center gap-3">
          <button
            type="button"
            onClick={onClose}
            className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-muted-foreground transition-colors hover:bg-secondary hover:text-foreground"
            aria-label={localize(lang, "Вернуться к списку запусков", "Back to run list")}
          >
            <ArrowLeft className="h-4 w-4" />
          </button>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <span className="text-sm font-semibold">{localize(lang, "Запуск", "Run")} #{run.id}</span>
              <StatusBadge status={run.status} lang={lang} />
            </div>
            <div className="mt-0.5 truncate text-xs text-muted-foreground">
              {run.pipeline_name} · {formatRunDate(run.started_at || run.created_at, lang)} · {formatRunDuration(run.duration_seconds, lang)}
            </div>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2 sm:justify-end">
          {(run.status === "running" || run.status === "pending") && (
            <Button size="sm" variant="destructive" className="h-9 gap-1.5" onClick={() => stopMutation.mutate()} disabled={stopMutation.isPending}>
              <Square className="h-3.5 w-3.5" /> {localize(lang, "Стоп", "Stop")}
            </Button>
          )}
          <Button size="sm" variant="outline" className="h-9 gap-1.5" onClick={() => navigate(`/studio/pipeline/${run.pipeline_id}`)}>
            <ExternalLink className="h-3.5 w-3.5" /> {localize(lang, "Открыть пайплайн", "Open pipeline")}
          </Button>
          <Button size="icon" variant="ghost" className="h-9 w-9" onClick={() => refetch()} aria-label={localize(lang, "Обновить запуск", "Refresh run")}>
            <RotateCcw className="h-3.5 w-3.5" />
          </Button>
        </div>
      </div>

      <div className="flex-1 overflow-auto">
        <div className="p-5 space-y-5">
          {run.error && (
            <div className="rounded-lg border border-red-500/30 bg-red-500/10 px-4 py-3 text-sm text-red-300">
              <div className="mb-1 flex items-center gap-1.5 font-medium">
                <XCircle className="h-4 w-4" /> {localize(lang, "Ошибка выполнения", "Execution failed")}
              </div>
              <pre className="whitespace-pre-wrap text-xs font-mono">{run.error}</pre>
            </div>
          )}

          {run.summary && (
            <div className="rounded-lg border border-border bg-card/60">
              <div className="flex items-center justify-between px-4 py-2 border-b border-border">
                <span className="flex items-center gap-2 text-sm font-medium">
                  <FileText className="h-4 w-4 text-muted-foreground" />
                  {localize(lang, "Отчёт", "Report")}
                </span>
                <Button size="xs" variant="ghost" className="h-8 gap-1" onClick={() => copyOutput(run.summary)}>
                  <Copy className="h-3 w-3" /> {localize(lang, "Копировать", "Copy")}
                </Button>
              </div>
              <div className="px-4 py-3 text-xs text-muted-foreground font-mono whitespace-pre-wrap leading-relaxed max-h-80 overflow-auto">
                {run.summary}
              </div>
            </div>
          )}

          <div>
            <div className="mb-2 text-sm font-medium text-muted-foreground">{localize(lang, "Шаги", "Steps")} ({nodes.length})</div>
            <div className="space-y-2">
              {nodes.map((node) => {
                const st: PipelineRun["node_states"][string] = nodeStates[node.id] || { status: "pending" };
                const status = st.status;
                const output = st.output || "";
                const error = st.error || "";
                const isExp = expandedNode === node.id;
                const agentEvents = nodeAgentEvents[node.id] || [];
                const hasContent = !!(output || error || agentEvents.length);
                const startedAt = st.started_at;
                const finishedAt = st.finished_at;
                const isAgentNode = node.type?.startsWith("agent/");

                let duration = "";
                if (startedAt && finishedAt) {
                  const ms = new Date(finishedAt).getTime() - new Date(startedAt).getTime();
                  duration = formatNodeDuration(ms, lang);
                }

                const iterCount = agentEvents.filter((e) => e.event_type === "agent_action").length;

                return (
                  <div key={node.id} className={`rounded-lg border transition-colors ${
                    status === "failed" ? "border-red-500/20 bg-background/24"
                    : status === "completed" ? "border-green-500/16 bg-background/24"
                    : status === "running" ? "border-primary/20 bg-background/24"
                    : status === "skipped" ? "border-amber-500/18 bg-background/24"
                    : "border-border/70 bg-background/24"
                  }`}>
                    <button
                      type="button"
                      className="flex min-h-12 w-full items-center gap-3 px-4 py-3 text-left"
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
                        {isAgentNode && agentEvents.length > 0 && (
                          <div className="rounded-lg border border-border/60 bg-background/18 px-3 py-2">
                            <div className="text-xs text-muted-foreground mb-2 flex items-center gap-1.5">
                              <Activity className="h-3 w-3 text-blue-400" />
                              <span>{localize(lang, `Шаги агента · ${iterCount} действий`, `Agent steps · ${iterCount} actions`)}</span>
                            </div>
                            <AgentSteps events={agentEvents} lang={lang} />
                          </div>
                        )}
                        {error && (
                          <div className="rounded-lg bg-red-500/5 px-3 py-2 font-mono text-xs text-red-300">
                            {error}
                          </div>
                        )}
                        {output && (
                          <div className="relative">
                            <Button size="xs" variant="ghost" className="absolute right-1 top-1 z-10 h-8 gap-1" onClick={() => copyOutput(output)} aria-label={localize(lang, "Копировать вывод шага", "Copy step output")}>
                              <Copy className="h-3 w-3" />
                            </Button>
                            <pre className="text-xs text-muted-foreground font-mono whitespace-pre-wrap break-all leading-relaxed bg-muted/20 rounded px-3 py-2 max-h-96 overflow-auto pr-16">
                              {output.length > 5000
                                ? output.slice(0, 5000) + localize(lang, "\n\n… [обрезано, полный вывод > 5000 символов]", "\n\n… [truncated, full output > 5000 characters]")
                                : output}
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
                  {localize(lang, "Нет данных по шагам: pipeline ещё не запускался или не сохранил snapshot.", "No step data yet: the pipeline has not run or did not save a snapshot.")}
                </div>
              )}
            </div>
          </div>

          <div>
            <button
              type="button"
              className="flex min-h-8 items-center gap-1 rounded-md text-xs text-muted-foreground transition-colors hover:text-foreground"
              onClick={() => setShowRaw(!showRaw)}
            >
              {showRaw ? <ChevronUp className="h-3 w-3" /> : <ChevronDown className="h-3 w-3" />}
              {localize(lang, "JSON для отладки", "Raw JSON")}
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
