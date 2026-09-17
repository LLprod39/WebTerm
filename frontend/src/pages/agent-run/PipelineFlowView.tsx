import { useState } from "react";
import {
  Activity,
  AlertTriangle,
  Brain,
  CheckCircle2,
  FileText,
  RefreshCw,
  Send,
  Target,
} from "lucide-react";

import type { AgentRunDetail } from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import {
  FlowConnector,
  FlowNode,
  OrchestratorDecisionNode,
  TaskNode,
} from "./FlowComponents";
import { TaskEditModal } from "./TaskEditModal";
import type { PlanTask } from "./types";

export function PipelineFlowView({
  run,
  planTasks,
  isActive,
  pendingQuestion,
  replyText,
  setReplyText,
  sending,
  onReply,
  onTasksUpdated,
}: {
  run: AgentRunDetail;
  planTasks: PlanTask[];
  isActive: boolean;
  pendingQuestion: string;
  replyText: string;
  setReplyText: (v: string) => void;
  sending: boolean;
  onReply: () => void;
  onTasksUpdated?: (tasks: PlanTask[]) => void;
}) {
  const { t } = useI18n();
  const tr = (key: string, vars?: Record<string, string | number>) => {
    let text = t(key);
    if (!vars) return text;
    for (const [name, value] of Object.entries(vars)) {
      text = text.split(`{${name}}`).join(String(value));
    }
    return text;
  };
  const goal = run.agent_name;
  const isCompleted = run.status === "completed";
  const isFailed = run.status === "failed";
  const [editingTask, setEditingTask] = useState<PlanTask | null>(null);

  const canEdit = planTasks.some((task) => task.status === "pending");

  return (
    <div className="rounded-sm border border-border bg-card">
      {editingTask ? (
        <TaskEditModal
          task={editingTask}
          runId={run.id}
          onClose={() => setEditingTask(null)}
          onSaved={(tasks) => {
            setEditingTask(null);
            onTasksUpdated?.(tasks);
          }}
        />
      ) : null}

      <div className="border-b border-border px-5 py-4">
        <div className="grid gap-px overflow-hidden rounded-sm border border-border bg-border sm:grid-cols-3">
          <div className="bg-card p-4">
            <div className="text-2xs font-medium uppercase tracking-[0.12em] text-muted-foreground">{t("run.goal")}</div>
            <p className="mt-2 text-sm font-medium text-foreground">{run.agent_name}</p>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">{(run as { goal?: string }).goal || goal}</p>
          </div>
          <div className="bg-card p-4">
            <div className="text-2xs font-medium uppercase tracking-[0.12em] text-muted-foreground">{t("run.plan_state")}</div>
            <p className="mt-2 text-sm font-medium text-foreground">
              {planTasks.length > 0 ? t("run.tasks_created").replace("{count}", String(planTasks.length)) : t("run.plan_preparing")}
            </p>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">
              {canEdit ? t("run.plan_editable") : t("run.plan_live")}
            </p>
          </div>
          <div className="bg-card p-4">
            <div className="text-2xs font-medium uppercase tracking-[0.12em] text-muted-foreground">{t("run.run_signal")}</div>
            <p className="mt-2 flex items-center gap-2 text-sm font-medium text-foreground">
              {isFailed ? (
                <AlertTriangle className="h-4 w-4 text-destructive" aria-hidden />
              ) : isCompleted ? (
                <CheckCircle2 className="h-4 w-4 text-success" aria-hidden />
              ) : (
                <Activity className="h-4 w-4 text-primary" aria-hidden />
              )}
              {isFailed ? t("run.status_failed") : isCompleted ? t("run.status_done") : t("run.status_active")}
            </p>
            <p className="mt-1 text-sm leading-5 text-muted-foreground">
              {isFailed ? t("run.status_failed") : isCompleted ? t("run.status_done") : t("run.plan_live")}
            </p>
          </div>
        </div>
      </div>

      <div className="px-4 py-5 sm:px-6">
        <div className="mx-auto max-w-3xl">
          <FlowNode icon={<Target className="h-4 w-4 text-info" />} label={t("run.flow_goal")} title={run.agent_name} color="blue" status="done">
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{(run as { goal?: string }).goal || goal}</p>
          </FlowNode>

          <FlowConnector />

          <FlowNode
            icon={<Brain className="h-4 w-4 text-ai" />}
            label={t("run.flow_orchestrator")}
            title={t("run.flow_planning")}
            color="violet"
            status={planTasks.length > 0 ? "done" : isActive ? "running" : "pending"}
          >
            {planTasks.length > 0 ? (
              <div className="mt-2 flex flex-wrap items-center gap-2">
                <p className="text-sm text-muted-foreground">{tr("run.plan_created", { count: planTasks.length })}</p>
                {canEdit ? (
                  <span className="rounded-md border border-ai/40 bg-ai/10 px-2.5 py-1 text-xs font-medium text-ai">
                    {t("run.pending_tasks_editable")}
                  </span>
                ) : null}
              </div>
            ) : isActive ? (
              <p className="mt-2 text-sm text-ai">{t("run.plan_breakdown")}</p>
            ) : null}
          </FlowNode>

          {planTasks.map((task, idx) => (
            <div key={task.id}>
              <FlowConnector active={task.status === "running"} />
              <TaskNode
                task={task}
                index={idx}
                onEdit={
                  task.status === "pending" || task.status === "failed" || task.status === "skipped"
                    ? () => setEditingTask(task)
                    : undefined
                }
              />
              {task.orchestrator_decision && task.status !== "done" ? (
                <>
                  <FlowConnector thin />
                  <OrchestratorDecisionNode decision={task.orchestrator_decision} />
                </>
              ) : null}
            </div>
          ))}

          {(isCompleted || isFailed || run.final_report) ? (
            <>
              <FlowConnector />
              <FlowNode
                icon={<FileText className="h-4 w-4 text-success" />}
                label={t("run.flow_synthesis")}
                title={t("run.flow_final_report")}
                color="green"
                status={run.final_report ? "done" : isActive ? "running" : "pending"}
              >
                {run.final_report ? (
                  <p className="mt-2 line-clamp-2 text-sm leading-6 text-muted-foreground">{run.final_report.slice(0, 180)}…</p>
                ) : null}
              </FlowNode>
            </>
          ) : null}

          {isActive && planTasks.length > 0 && !planTasks.some((task) => task.status === "running") ? (
            <div className="flex items-center gap-2 py-5 pl-7 text-sm text-muted-foreground">
              <Brain className="h-4 w-4 text-ai" aria-hidden />
              <span>{t("run.orchestrator_waiting")}</span>
            </div>
          ) : null}

          {pendingQuestion ? (
            <div className="mt-5 rounded-sm border border-warning/35 bg-warning/10 p-4">
              <div className="min-w-0">
                <div className="text-2xs font-medium uppercase tracking-[0.12em] text-warning">{t("run.needs_input")}</div>
                <p className="mt-2 text-sm leading-6 text-foreground">{pendingQuestion}</p>
                <div className="mt-3 flex flex-col gap-2 sm:flex-row">
                  <Input
                    value={replyText}
                    onChange={(e) => setReplyText(e.target.value)}
                    placeholder={t("run.reply_placeholder")}
                    className="h-11"
                    onKeyDown={(e) => e.key === "Enter" && onReply()}
                  />
                  <Button size="sm" className="h-11 rounded-sm px-4" onClick={onReply} disabled={sending}>
                    {sending ? <RefreshCw className="h-3.5 w-3.5 animate-spin" aria-hidden /> : <Send className="h-3.5 w-3.5" aria-hidden />}
                    {t("run.reply")}
                  </Button>
                </div>
              </div>
            </div>
          ) : null}
        </div>
      </div>
    </div>
  );
}
