import { useEffect, useState, type ReactNode } from "react";
import {
  Brain,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  ChevronUp,
  Clock,
  HelpCircle,
  Pencil,
  RefreshCw,
  RotateCcw,
  SkipForward,
  XCircle,
} from "lucide-react";

import type { PlanTask } from "./types";

type FlowColor = "blue" | "green" | "violet" | "red" | "yellow" | "gray";

const colorMap: Record<FlowColor, { border: string; bg: string; label: string; ring: string }> = {
  blue: { border: "border-sky-500/25", bg: "bg-sky-500/8", label: "text-sky-300", ring: "ring-sky-500/20" },
  green: { border: "border-emerald-500/25", bg: "bg-emerald-500/8", label: "text-emerald-300", ring: "ring-emerald-500/20" },
  violet: { border: "border-violet-500/25", bg: "bg-violet-500/8", label: "text-violet-300", ring: "ring-violet-500/20" },
  red: { border: "border-red-500/25", bg: "bg-red-500/8", label: "text-red-300", ring: "ring-red-500/20" },
  yellow: { border: "border-amber-500/25", bg: "bg-amber-500/8", label: "text-amber-300", ring: "ring-amber-500/20" },
  gray: { border: "border-border/70", bg: "bg-background/45", label: "text-muted-foreground", ring: "ring-border/40" },
};

export function TaskNode({ task, index, onEdit }: { task: PlanTask; index: number; onEdit?: () => void }) {
  const [expanded, setExpanded] = useState(task.status === "running" || task.status === "done");

  useEffect(() => {
    if (task.status === "running") setExpanded(true);
  }, [task.status]);

  const statusConfig = {
    pending: { icon: <Clock className="h-4 w-4 text-muted-foreground" />, color: "gray" as const, label: "В очереди" },
    running: { icon: <RefreshCw className="h-4 w-4 text-blue-400 animate-spin" />, color: "blue" as const, label: "Выполняется" },
    done: { icon: <CheckCircle2 className="h-4 w-4 text-green-400" />, color: "green" as const, label: "Готово" },
    failed: { icon: <XCircle className="h-4 w-4 text-red-400" />, color: "red" as const, label: "Ошибка" },
    skipped: { icon: <SkipForward className="h-4 w-4 text-yellow-400" />, color: "yellow" as const, label: "Пропущено" },
  };

  const cfg = statusConfig[task.status] || statusConfig.pending;

  return (
    <FlowNode
      icon={cfg.icon}
      label={`Задача ${index + 1}`}
      title={task.name}
      color={cfg.color}
      status={task.status as "pending" | "running" | "done" | "failed" | "skipped"}
      expandable
      expanded={expanded}
      onToggle={() => setExpanded(!expanded)}
      badge={cfg.label}
      onEdit={onEdit}
    >
      {expanded && (
        <div className="mt-3 space-y-3">
          <p className="text-sm leading-6 text-muted-foreground">{task.description}</p>

          {task.thought && task.status === "running" && (
            <div className="rounded-2xl border border-violet-500/20 bg-violet-500/8 px-3 py-3">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-violet-300">
                <Brain className="h-3 w-3" />
                Thinking
              </div>
              <p className="text-sm leading-6 text-foreground/85">{task.thought}</p>
            </div>
          )}

          {task.iterations && task.iterations.length > 0 && <TaskIterations iterations={task.iterations} />}

          {task.result && (
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/8 px-3 py-3">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-emerald-300">
                <CheckCircle2 className="h-3 w-3" />
                Result
              </div>
              <p className="whitespace-pre-wrap text-sm leading-6 text-foreground/85">{task.result}</p>
            </div>
          )}

          {task.error && (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/8 px-3 py-3">
              <div className="mb-1 flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-red-300">
                <XCircle className="h-3 w-3" />
                Error
              </div>
              <p className="font-mono text-xs leading-6 text-red-200/85">{task.error}</p>
            </div>
          )}
        </div>
      )}
    </FlowNode>
  );
}

function TaskIterations({ iterations }: { iterations: PlanTask["iterations"] }) {
  const [show, setShow] = useState(false);
  return (
    <div className="rounded-2xl border border-border/70 bg-background/45 px-3 py-3">
      <button
        onClick={() => setShow(!show)}
        className="flex items-center gap-1.5 text-[11px] font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        {show ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        {iterations.length} шаг{iterations.length > 1 && iterations.length < 5 ? "а" : "ов"} выполнения
      </button>
      {show && (
        <div className="mt-3 space-y-2 border-l border-border/60 pl-3">
          {iterations.map((it, i) => (
            <div key={i} className="text-[11px]">
              <div className="flex flex-wrap items-center gap-1.5 text-muted-foreground">
                <span className="font-mono text-[10px]">#{it.iteration}</span>
                {it.action && (
                  <span className="rounded-full border border-sky-500/20 bg-sky-500/10 px-2 py-0.5 font-mono text-[10px] text-sky-300">
                    {it.action}
                  </span>
                )}
              </div>
              {it.thought && <p className="mt-1 pl-1 text-foreground/75">{it.thought.slice(0, 200)}</p>}
              {it.observation && (
                <pre className="mt-1 max-h-24 overflow-y-auto rounded-xl bg-card/70 px-3 py-2 font-mono text-[10px] whitespace-pre-wrap text-muted-foreground">
                  {it.observation.slice(0, 500)}
                </pre>
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

export function OrchestratorDecisionNode({ decision }: { decision: { action: string; reason?: string; message?: string } }) {
  const decisionConfig: Record<string, { icon: ReactNode; label: string; color: string }> = {
    retry: { icon: <RotateCcw className="h-3.5 w-3.5 text-amber-300" />, label: "Повтор", color: "text-amber-300" },
    skip: { icon: <SkipForward className="h-3.5 w-3.5 text-muted-foreground" />, label: "Пропустить", color: "text-muted-foreground" },
    ask_user: { icon: <HelpCircle className="h-3.5 w-3.5 text-orange-300" />, label: "Спросить пользователя", color: "text-orange-300" },
    abort: { icon: <XCircle className="h-3.5 w-3.5 text-red-300" />, label: "Прервать пайплайн", color: "text-red-300" },
  };
  const cfg = decisionConfig[decision.action] || decisionConfig.skip;

  return (
    <div className="ml-7 rounded-2xl border border-dashed border-orange-500/25 bg-orange-500/8 px-4 py-3 text-sm">
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-[0.18em] text-violet-300">
        <Brain className="h-3.5 w-3.5" />
        Orchestrator decision
      </div>
      <div className={`mt-2 flex items-center gap-2 font-medium ${cfg.color}`}>
        {cfg.icon} {cfg.label}
      </div>
      {(decision.reason || decision.message) && (
        <p className="mt-2 text-sm leading-6 text-muted-foreground">{decision.reason || decision.message}</p>
      )}
    </div>
  );
}

export function FlowNode({
  icon,
  label,
  title,
  color,
  status,
  expandable,
  expanded,
  onToggle,
  badge,
  onEdit,
  children,
}: {
  icon: ReactNode;
  label: string;
  title: string;
  color: FlowColor;
  status: "pending" | "running" | "done" | "failed" | "skipped";
  expandable?: boolean;
  expanded?: boolean;
  onToggle?: () => void;
  badge?: string;
  onEdit?: () => void;
  children?: ReactNode;
}) {
  const c = colorMap[color];
  const isRunning = status === "running";

  return (
    <div
      className={`rounded-[24px] border ${c.border} ${c.bg} px-4 py-4 transition-all ${isRunning ? `ring-2 ${c.ring}` : ""}`}
    >
      <div
        className={`flex items-start gap-3 ${expandable ? "cursor-pointer select-none" : ""}`}
        onClick={expandable ? onToggle : undefined}
      >
        <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-white/5 bg-background/55 ${isRunning ? "animate-pulse" : ""}`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className={`text-[10px] font-medium uppercase tracking-[0.18em] ${c.label}`}>{label}</div>
          <div className="mt-1 text-base font-semibold text-foreground">{title}</div>
        </div>
        {badge && (
          <span className={`rounded-full border px-2.5 py-1 text-[10px] font-medium uppercase tracking-[0.14em] ${c.border} ${c.bg} ${c.label}`}>
            {badge}
          </span>
        )}
        {onEdit && (
          <button
            onClick={(e) => { e.stopPropagation(); onEdit(); }}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-violet-500/20 text-muted-foreground hover:text-violet-400 shrink-0"
            title="Редактировать задачу"
          >
            <Pencil className="h-3.5 w-3.5" />
          </button>
        )}
        {expandable && (
          <ChevronRight className={`mt-1 h-4 w-4 shrink-0 text-muted-foreground transition-transform ${expanded ? "rotate-90" : ""}`} />
        )}
      </div>
      {children}
    </div>
  );
}

export function FlowConnector({ active, thin }: { active?: boolean; thin?: boolean }) {
  return (
    <div className="flex justify-start py-1 pl-[1.7rem]">
      <div
        className={`w-px rounded-full ${thin ? "h-5" : "h-7"} ${active ? "bg-sky-400" : "bg-border/60"}`}
      />
    </div>
  );
}
