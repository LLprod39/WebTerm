import { CheckCircle2, Circle, LoaderCircle, TriangleAlert } from "lucide-react";
import type { AgentRunReportResponse, AgentRunReportStep } from "@/lib/api";
import { StatusBadge } from "@/components/system/StatusBadge";
import { cn } from "@/lib/utils";
import { formatDuration } from "./formatters";
import { _severityRank, severityTone } from "./reportShared";

export function AgentStepsTab({ report, steps }: { report: AgentRunReportResponse; steps: AgentRunReportStep[] }) {
  const done = steps.filter(stepIsDone).length;
  const active = steps.find(stepIsActive);
  const progress = steps.length ? Math.round((done / steps.length) * 100) : 0;
  if (!steps.length) return <div className="rounded-sm border border-border bg-card p-5 text-sm text-muted-foreground"><p className="font-medium text-foreground">{report.report_state?.is_terminal ? "Шаги не сохранены" : "Агент готовит план"}</p><p className="mt-1">{report.report_state?.next_expected || "Шаги появятся после начала работы."}</p></div>;
  return <section className="overflow-hidden rounded-sm border border-border bg-card shadow-elev-1">
    <div className="border-b border-border px-4 py-3 sm:px-5"><div className="flex items-center justify-between gap-4"><div className="min-w-0"><h2 className="text-sm font-semibold text-foreground">Ход работы</h2><p className="mt-0.5 truncate text-xs text-muted-foreground">{active?.title || `${done} из ${steps.length} шагов завершено`}</p></div><span className="font-mono text-xs text-muted-foreground">{progress}%</span></div><div className="mt-2 h-1.5 overflow-hidden rounded-full bg-secondary"><div className="h-full rounded-full bg-primary" style={{ width: `${progress}%` }} /></div></div>
    <ol className="divide-y divide-border">{steps.map((step) => <CompactStep key={step.id} step={step} />)}</ol>
  </section>;
}

function CompactStep({ step }: { step: AgentRunReportStep }) {
  const problem = stepIsProblem(step); const active = stepIsActive(step); const done = stepIsDone(step);
  const Icon = problem ? TriangleAlert : active ? LoaderCircle : done ? CheckCircle2 : Circle;
  const hasDetails = Boolean(step.description || step.command || step.details || step.error);
  return <li><details open={active || problem}><summary className="flex cursor-pointer list-none items-center gap-3 px-4 py-3 sm:px-5"><Icon className={cn("h-4 w-4 shrink-0", problem ? "text-destructive" : active ? "animate-spin text-info" : done ? "text-success" : "text-muted-foreground")} /><span className="min-w-0 flex-1 truncate text-sm font-medium text-foreground">{step.title}</span><StatusBadge label={step.status_label || step.status} tone={severityTone[step.severity]} />{step.duration_ms > 0 ? <span className="hidden font-mono text-xs text-muted-foreground sm:inline">{formatDuration(step.duration_ms)}</span> : null}</summary>{hasDetails ? <div className="space-y-2 border-t border-border bg-surface-0/40 px-11 py-3 text-sm">{step.description ? <p className="text-muted-foreground">{step.description}</p> : null}{step.command ? <pre className="overflow-x-auto rounded-sm border border-border bg-background p-3 font-mono text-xs text-foreground">{step.command}</pre> : null}{step.details ? <p className="whitespace-pre-wrap text-foreground/85">{step.details}</p> : null}{step.error ? <p className="whitespace-pre-wrap text-destructive">{step.error}</p> : null}</div> : null}</details></li>;
}

function stepIsDone(step: AgentRunReportStep) { return ["done", "completed", "success"].includes(step.status) || step.severity === "success"; }
function stepIsProblem(step: AgentRunReportStep) { return step.status === "failed" || _severityRank(step.severity) >= _severityRank("warning"); }
function stepIsActive(step: AgentRunReportStep) { return ["running", "waiting", "plan_review"].includes(step.status); }
