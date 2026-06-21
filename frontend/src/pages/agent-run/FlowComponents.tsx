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

import { useI18n } from "@/lib/i18n";
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
  const { t } = useI18n();
  const tr = (key: string, vars?: Record<string, string | number>) => {
    let text = t(key);
    if (!vars) return text;
    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value));
    }
    return text;
  };
  const [expanded, setExpanded] = useState(task.status === "running" || task.status === "done");

  useEffect(() => {
    if (task.status === "running") setExpanded(true);
  }, [task.status]);

  const statusConfig = {
    pending: { icon: <Clock className="h-4 w-4 text-muted-foreground" />, color: "gray" as const, label: t("run.task_status.pending") },
    running: { icon: <RefreshCw className="h-4 w-4 animate-spin text-info" />, color: "blue" as const, label: t("run.task_status.running") },
    done: { icon: <CheckCircle2 className="h-4 w-4 text-success" />, color: "green" as const, label: t("run.task_status.done") },
    failed: { icon: <XCircle className="h-4 w-4 text-destructive" />, color: "red" as const, label: t("run.task_status.failed") },
    skipped: { icon: <SkipForward className="h-4 w-4 text-warning" />, color: "yellow" as const, label: t("run.task_status.skipped") },
  };

  const cfg = statusConfig[task.status] || statusConfig.pending;

  return (
    <FlowNode
      icon={cfg.icon}
      label={tr("run.task_label", { index: index + 1 })}
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
              <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[color:var(--wt-ai)]">
                <Brain className="h-3 w-3" />
                {t("run.thinking")}
              </div>
              <p className="text-sm leading-6 text-foreground/85">{task.thought}</p>
            </div>
          )}

          {task.iterations && task.iterations.length > 0 && <TaskIterations iterations={task.iterations} />}

          {task.result && (
            <div className="rounded-2xl border border-emerald-500/20 bg-emerald-500/8 px-3 py-3">
              <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-success">
                <CheckCircle2 className="h-3 w-3" />
                {t("run.result")}
              </div>
              <p className="whitespace-pre-wrap text-sm leading-6 text-foreground/85">{task.result}</p>
            </div>
          )}

          {task.error && (
            <div className="rounded-2xl border border-red-500/20 bg-red-500/8 px-3 py-3">
              <div className="mb-1 flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-destructive">
                <XCircle className="h-3 w-3" />
                {t("run.error")}
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
  const { t } = useI18n();
  const label = t("run.iterations_count").replace("{count}", String(iterations.length));
  const [show, setShow] = useState(false);
  return (
    <div className="rounded-2xl border border-border/70 bg-background/45 px-3 py-3">
      <button
        onClick={() => setShow(!show)}
        className="flex items-center gap-1.5 text-xs font-medium text-muted-foreground transition-colors hover:text-foreground"
      >
        {show ? <ChevronUp className="h-3.5 w-3.5" /> : <ChevronDown className="h-3.5 w-3.5" />}
        {label}
      </button>
      {show && (
        <div className="mt-3 space-y-2 border-l border-border/60 pl-3">
          {iterations.map((it, i) => (
            <div key={i} className="text-xs">
              <div className="flex flex-wrap items-center gap-1.5 text-muted-foreground">
                <span className="font-mono text-xs">#{it.iteration}</span>
                {it.action && (
                  <span className="rounded-md border border-info/30 bg-info/10 px-2 py-0.5 font-mono text-xs text-info">
                    {it.action}
                  </span>
                )}
              </div>
              {it.thought && <p className="mt-1 pl-1 text-foreground/75">{it.thought.slice(0, 200)}</p>}
              {it.observation && (
                <pre className="mt-1 max-h-24 overflow-y-auto rounded-xl bg-card/70 px-3 py-2 font-mono text-xs whitespace-pre-wrap text-muted-foreground">
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
  const { t } = useI18n();
  const decisionConfig: Record<string, { icon: ReactNode; label: string; color: string }> = {
    retry: { icon: <RotateCcw className="h-3.5 w-3.5 text-warning" />, label: t("run.decision.retry"), color: "text-warning" },
    skip: { icon: <SkipForward className="h-3.5 w-3.5 text-muted-foreground" />, label: t("run.decision.skip"), color: "text-muted-foreground" },
    ask_user: { icon: <HelpCircle className="h-3.5 w-3.5 text-warning" />, label: t("run.decision.ask_user"), color: "text-warning" },
    abort: { icon: <XCircle className="h-3.5 w-3.5 text-destructive" />, label: t("run.decision.abort"), color: "text-destructive" },
  };
  const cfg = decisionConfig[decision.action] || decisionConfig.skip;

  return (
    <div className="ml-7 rounded-lg border border-dashed border-warning/35 bg-warning/10 px-4 py-3 text-sm">
      <div className="flex items-center gap-1.5 text-xs font-semibold uppercase tracking-wide text-[color:var(--wt-ai)]">
        <Brain className="h-3.5 w-3.5" />
        {t("run.orchestrator_decision")}
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
  const { t } = useI18n();
  const c = colorMap[color];
  const isRunning = status === "running";

  return (
    <div className={`rounded-lg border ${c.border} ${c.bg} px-4 py-4 transition-all ${isRunning ? `ring-2 ${c.ring}` : ""}`}>
      <div
        className={`flex items-start gap-3 ${expandable ? "cursor-pointer select-none" : ""}`}
        onClick={expandable ? onToggle : undefined}
      >
        <div className={`mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-2xl border border-white/5 bg-background/55 ${isRunning ? "animate-pulse" : ""}`}>
          {icon}
        </div>
        <div className="flex-1 min-w-0">
          <div className={`text-xs font-semibold uppercase tracking-wide ${c.label}`}>{label}</div>
          <div className="mt-1 text-base font-semibold text-foreground">{title}</div>
        </div>
        {badge && (
          <span className={`rounded-md border px-2.5 py-1 text-xs font-medium ${c.border} ${c.bg} ${c.label}`}>
            {badge}
          </span>
        )}
        {onEdit && (
          <button
            onClick={(e) => { e.stopPropagation(); onEdit(); }}
            className="opacity-0 group-hover:opacity-100 transition-opacity p-1.5 rounded-lg hover:bg-violet-500/20 text-muted-foreground hover:text-violet-400 shrink-0"
            title={t("run.edit_task_label")}
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
