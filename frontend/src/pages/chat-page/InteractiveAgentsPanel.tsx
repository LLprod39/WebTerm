import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Loader2, Play, Square } from "lucide-react";

import { fetchAgentRunDetail, runAgent, stopAgent } from "@/api/agents";
import type { AgentRunDetail } from "@/api/agent-types";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";

export type InteractiveAgentItem = {
  id: number | string;
  name: string;
  mode?: string;
  mode_display?: string;
  agent_type?: string;
  goal?: string;
  server_count?: number;
  server_ids?: number[];
  server_names?: string[];
  is_enabled?: boolean;
  schedule_minutes?: number;
  schedule_state?: string;
  due_now?: boolean;
  last_run_at?: string | null;
  last_run_status?: string | null;
  last_run_id?: number | null;
  active_run_id?: number | null;
  active_run_status?: string | null;
  active_run_started_at?: string | null;
  active_run_iterations?: number;
  active_run_server_name?: string;
  active_run_pending_question?: string;
  max_iterations?: number;
  detail_url?: string;
  run_url?: string;
};

export type AgentPanelActions = {
  onAsk?: (prompt: string) => void;
  onRunChanged?: () => void;
};

type Props = {
  title?: string;
  items: InteractiveAgentItem[];
  actions?: AgentPanelActions;
};

type LocalRunState = {
  active_run_id: number | null;
  active_run_status: string | null;
  active_run_iterations: number;
  active_run_server_name: string;
  active_run_pending_question: string;
  active_run_started_at: string | null;
  last_run_status?: string | null;
  last_run_id?: number | null;
};

const ACTIVE = new Set(["pending", "running", "paused", "waiting", "plan_review"]);

function isActiveStatus(status?: string | null, activeId?: number | null) {
  if (activeId) return true;
  return ACTIVE.has(String(status || "").toLowerCase());
}

function statusDotClass(status?: string | null, active?: boolean) {
  if (active) return "bg-foreground/70";
  const s = String(status || "").toLowerCase();
  if (["completed", "succeeded", "success"].includes(s)) return "bg-success/80";
  if (["failed", "error"].includes(s)) return "bg-destructive/80";
  if (s === "stopped") return "bg-warning/70";
  return "bg-muted-foreground/35";
}

function shortStatus(status: string | null | undefined, lang: "ru" | "en") {
  switch ((status || "").toLowerCase()) {
    case "running":
      return localize(lang, "идёт", "running");
    case "pending":
      return localize(lang, "очередь", "queued");
    case "waiting":
      return localize(lang, "ждёт", "waiting");
    case "plan_review":
      return localize(lang, "план", "plan");
    case "paused":
      return localize(lang, "пауза", "paused");
    case "failed":
      return localize(lang, "ошибка", "failed");
    case "stopped":
      return localize(lang, "стоп", "stopped");
    case "completed":
    case "succeeded":
    case "success":
      return localize(lang, "ok", "ok");
    default:
      return "";
  }
}

function ageShort(iso?: string | null) {
  if (!iso) return "";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "";
  const sec = Math.max(0, Math.floor((Date.now() - t) / 1000));
  if (sec < 60) return `${sec}s`;
  if (sec < 3600) return `${Math.floor(sec / 60)}m`;
  return `${Math.floor(sec / 3600)}h`;
}

function progressPct(iterations: number, maxIterations: number, active: boolean) {
  if (!active) return 0;
  if (maxIterations > 0) return Math.min(94, Math.round((iterations / maxIterations) * 100));
  return Math.min(88, 10 + iterations * 7);
}

function stepLine(detail: AgentRunDetail | null, pending?: string): string {
  if (pending) return pending.slice(0, 72);
  if (!detail) return "";
  const tasks = detail.plan_tasks || [];
  const running = tasks.find((t) => t.status === "running");
  if (running) {
    const done = tasks.filter((t) => ["done", "failed", "skipped"].includes(t.status)).length;
    return `${running.name || "task"} · ${done}/${tasks.length}`;
  }
  const log = detail.iterations_log || [];
  if (log.length) {
    const last = log[log.length - 1];
    return String(last.action || last.thought || "").slice(0, 72);
  }
  const tools = detail.tool_calls || [];
  if (tools.length) return String(tools[tools.length - 1].tool || "").slice(0, 72);
  return "";
}

/**
 * Extreme-minimal agents list for Operator chat.
 * One line per agent. Play/stop on hover. Progress only when open or running+hover.
 */
export function InteractiveAgentsPanel({ title, items, actions }: Props) {
  const { lang } = useI18n();
  const [openId, setOpenId] = useState<number | null>(null);
  const [hoverId, setHoverId] = useState<number | null>(null);
  const [localById, setLocalById] = useState<Record<number, LocalRunState>>({});
  const [busyId, setBusyId] = useState<number | null>(null);
  const [errorById, setErrorById] = useState<Record<number, string>>({});
  const [detailByRun, setDetailByRun] = useState<Record<number, AgentRunDetail>>({});
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const mergeLocal = useCallback((id: number, patch: Partial<LocalRunState>) => {
    setLocalById((prev) => {
      const base = prev[id] || {
        active_run_id: null,
        active_run_status: null,
        active_run_iterations: 0,
        active_run_server_name: "",
        active_run_pending_question: "",
        active_run_started_at: null,
      };
      return { ...prev, [id]: { ...base, ...patch } };
    });
  }, []);

  const loadDetail = useCallback(
    async (runId: number) => {
      if (!runId) return;
      try {
        const res = await fetchAgentRunDetail(runId);
        if (!res?.run) return;
        setDetailByRun((prev) => ({ ...prev, [runId]: res.run }));
        const agentId = res.run.agent_id;
        if (!agentId) return;
        const active = isActiveStatus(res.run.status, res.run.id);
        mergeLocal(agentId, {
          active_run_id: active ? res.run.id : null,
          active_run_status: res.run.status,
          active_run_iterations: res.run.total_iterations || 0,
          active_run_server_name: res.run.server_name || "",
          active_run_pending_question: res.run.pending_question || "",
          active_run_started_at: res.run.started_at || null,
          last_run_status: active ? undefined : res.run.status,
          last_run_id: res.run.id,
        });
      } catch {
        /* ignore */
      }
    },
    [mergeLocal],
  );

  useEffect(() => {
    const focusId = openId ?? hoverId;
    if (focusId == null) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    const item = items.find((a) => Number(a.id) === focusId);
    const local = localById[focusId];
    const runId = local?.active_run_id ?? item?.active_run_id ?? null;
    if (!runId) {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
      return;
    }
    void loadDetail(runId);
    pollRef.current = setInterval(() => void loadDetail(runId), 5000);
    return () => {
      if (pollRef.current) {
        clearInterval(pollRef.current);
        pollRef.current = null;
      }
    };
  }, [openId, hoverId, items, localById, loadDetail]);

  const onStart = async (item: InteractiveAgentItem) => {
    const id = Number(item.id);
    if (!id || busyId === id) return;
    if (item.is_enabled === false) {
      setErrorById((p) => ({ ...p, [id]: localize(lang, "Выключен", "Disabled") }));
      return;
    }
    if (!item.server_count && !(item.server_names?.length || item.server_ids?.length)) {
      setErrorById((p) => ({ ...p, [id]: localize(lang, "Нет серверов", "No servers") }));
      return;
    }
    setBusyId(id);
    setErrorById((p) => {
      const n = { ...p };
      delete n[id];
      return n;
    });
    try {
      const res = await runAgent(id);
      const runId = res.run_id || res.runs?.[0]?.run_id || null;
      mergeLocal(id, {
        active_run_id: runId,
        active_run_status: res.status || res.runs?.[0]?.status || "pending",
        active_run_iterations: 0,
        active_run_server_name: res.runs?.[0]?.server_name || item.server_names?.[0] || "",
        active_run_pending_question: "",
        active_run_started_at: new Date().toISOString(),
      });
      if (runId) void loadDetail(runId);
      setOpenId(id);
      actions?.onRunChanged?.();
    } catch {
      setErrorById((p) => ({ ...p, [id]: localize(lang, "Не запустился", "Failed") }));
    } finally {
      setBusyId(null);
    }
  };

  const onStop = async (item: InteractiveAgentItem) => {
    const id = Number(item.id);
    const runId = localById[id]?.active_run_id ?? item.active_run_id ?? undefined;
    if (!id || busyId === id || !runId) return;
    setBusyId(id);
    try {
      await stopAgent(id, runId);
      mergeLocal(id, {
        active_run_id: null,
        active_run_status: "stopped",
        last_run_status: "stopped",
        last_run_id: runId,
      });
      actions?.onRunChanged?.();
    } catch {
      setErrorById((p) => ({ ...p, [id]: localize(lang, "Не остановился", "Stop failed") }));
    } finally {
      setBusyId(null);
    }
  };

  const rows = useMemo(() => items.slice(0, 40), [items]);

  if (!rows.length) return null;

  return (
    <div className="w-full max-w-[520px] overflow-hidden rounded-sm border border-border/40 bg-card/30">
      <div className="flex items-baseline justify-between gap-3 px-3.5 pt-2.5 pb-1">
        <span className="text-[11px] font-medium tracking-wide text-muted-foreground">
          {title?.replace(/\s*·\s*\d+\s*$/, "") || localize(lang, "Агенты", "Agents")}
        </span>
        <span className="text-[11px] tabular-nums text-muted-foreground/70">{rows.length}</span>
      </div>

      <ul className="pb-1">
        {rows.map((a) => {
          const id = Number(a.id);
          const local = localById[id];
          const activeRunId = local?.active_run_id ?? a.active_run_id ?? null;
          const status = local?.active_run_status ?? a.active_run_status ?? a.last_run_status ?? null;
          const active = isActiveStatus(status, activeRunId);
          const open = openId === id;
          const hover = hoverId === id;
          const showProgress = active && (open || hover);
          const iterations = local?.active_run_iterations ?? a.active_run_iterations ?? 0;
          const maxIter = a.max_iterations || 0;
          const pct = progressPct(iterations, maxIter, active);
          const age = ageShort(local?.active_run_started_at ?? a.active_run_started_at);
          const pending = local?.active_run_pending_question || a.active_run_pending_question || "";
          const detail = activeRunId ? detailByRun[activeRunId] : undefined;
          const step = stepLine(detail || null, pending);
          const busy = busyId === id;
          const runUrl =
            a.run_url ||
            (activeRunId
              ? `/agents/run/${activeRunId}`
              : local?.last_run_id || a.last_run_id
                ? `/agents/run/${local?.last_run_id || a.last_run_id}`
                : "/agents");

          const server =
            (a.server_names?.length || 0) > 1
              ? `${a.server_names![0]} +${a.server_names!.length - 1}`
              : a.server_names?.[0] || "";

          const meta = [
            a.mode || "",
            active ? shortStatus(status || "running", lang) : shortStatus(status, lang),
            active && age ? age : "",
            !active && server ? server : active && !age ? server : "",
          ]
            .filter(Boolean)
            .join(" · ");

          return (
            <li
              key={id}
              className="group"
              onMouseEnter={() => setHoverId(id)}
              onMouseLeave={() => setHoverId((c) => (c === id ? null : c))}
            >
              <div
                className={cn(
                  "flex items-center gap-2.5 px-3.5 py-1.5 transition-colors",
                  "hover:bg-foreground/[0.03]",
                  open && "bg-foreground/[0.03]",
                )}
              >
                <span
                  className={cn(
                    "h-1 w-1 shrink-0 rounded-full",
                    statusDotClass(status, active),
                    active && "animate-pulse motion-reduce:animate-none",
                  )}
                  aria-hidden
                />

                <button
                  type="button"
                  className="min-w-0 flex-1 text-left"
                  onClick={() => setOpenId(open ? null : id)}
                >
                  <div className="flex min-w-0 items-baseline gap-2">
                    <span className="truncate text-[13px] font-medium tracking-tight text-foreground">
                      {a.name}
                    </span>
                    {meta ? (
                      <span className="truncate text-[11px] text-muted-foreground/75">{meta}</span>
                    ) : null}
                  </div>
                </button>

                <div className="flex shrink-0 items-center gap-0.5">
                  <button
                    type="button"
                    disabled={busy || (!active && a.is_enabled === false)}
                    title={
                      active
                        ? localize(lang, "Стоп", "Stop")
                        : localize(lang, "Старт", "Start")
                    }
                    onClick={(e) => {
                      e.stopPropagation();
                      if (active) void onStop(a);
                      else void onStart(a);
                    }}
                    className={cn(
                      "flex h-7 w-7 items-center justify-center rounded-full text-muted-foreground",
                      "transition-all hover:bg-foreground/[0.06] hover:text-foreground motion-reduce:transition-none",
                      "disabled:opacity-40",
                      // Always visible when active or busy; otherwise only on row hover
                      active || busy || hover || open ? "opacity-100" : "opacity-0 group-hover:opacity-100",
                    )}
                  >
                    {busy ? (
                      <Loader2 className="h-3.5 w-3.5 animate-spin motion-reduce:animate-none" />
                    ) : active ? (
                      <Square className="h-3 w-3 fill-current" />
                    ) : (
                      <Play className="h-3.5 w-3.5 fill-current" />
                    )}
                  </button>
                </div>
              </div>

              {(showProgress || open) && (active || step || errorById[id]) ? (
                <div className="px-3.5 pb-2 pl-[1.625rem]">
                  {active ? (
                    <div className="mb-1.5 h-px overflow-hidden rounded-full bg-foreground/[0.06]">
                      <div
                        className="h-full bg-foreground/35 transition-all duration-700 ease-out motion-reduce:transition-none"
                        style={{ width: `${Math.max(6, pct)}%` }}
                      />
                    </div>
                  ) : null}
                  <div className="flex items-center justify-between gap-3">
                    <p className="min-w-0 truncate text-[11px] leading-4 text-muted-foreground/80">
                      {errorById[id] ||
                        step ||
                        (active
                          ? localize(lang, "Выполняется…", "Running…")
                          : localize(lang, "Нет активного запуска", "Idle"))}
                    </p>
                    <Link
                      to={runUrl}
                      className="shrink-0 text-[11px] text-muted-foreground/70 underline-offset-2 hover:text-foreground hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      {localize(lang, "Открыть", "Open")}
                    </Link>
                  </div>
                </div>
              ) : errorById[id] ? (
                <p className="px-3.5 pb-1.5 pl-[1.625rem] text-[11px] text-destructive/90">{errorById[id]}</p>
              ) : null}
            </li>
          );
        })}
      </ul>
    </div>
  );
}
