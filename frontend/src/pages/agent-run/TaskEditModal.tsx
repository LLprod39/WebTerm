import { useRef, useState } from "react";
import { CheckCircle2, RefreshCw, Sparkles, Trash2, X } from "lucide-react";

import {
  aiRefinePipelineTask,
  updatePipelineTask,
} from "@/lib/api";
import { useI18n } from "@/lib/i18n";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";

import type { PlanTask } from "./types";

export function TaskEditModal({
  task,
  runId,
  onClose,
  onSaved,
}: {
  task: PlanTask;
  runId: number;
  onClose: () => void;
  onSaved: (tasks: PlanTask[]) => void;
}) {
  const { t } = useI18n();
  const [name, setName] = useState(task.name);
  const [description, setDescription] = useState(task.description);
  const [saving, setSaving] = useState(false);
  const [deleting, setDeleting] = useState(false);
  const [aiMsg, setAiMsg] = useState("");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");
  const aiInputRef = useRef<HTMLInputElement>(null);

  const handleSave = async () => {
    setSaving(true);
    try {
      const res = await updatePipelineTask(runId, task.id, { action: "update", name, description });
      onSaved(res.plan_tasks);
      onClose();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : t("run.save_error"));
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async () => {
    if (!confirm(`${t("run.confirm_delete_task")} "${task.name}"?`)) return;
    setDeleting(true);
    try {
      const res = await updatePipelineTask(runId, task.id, { action: "delete" });
      onSaved(res.plan_tasks);
      onClose();
    } catch (e: unknown) {
      alert(e instanceof Error ? e.message : t("run.delete_error"));
    } finally {
      setDeleting(false);
    }
  };

  const handleAiRefine = async () => {
    if (!aiMsg.trim()) return;
    setAiLoading(true);
    setAiError("");
    try {
      const res = await aiRefinePipelineTask(runId, task.id, aiMsg.trim());
      if (!res.success) {
        setAiError(res.error || t("run.ai_error"));
        return;
      }
      setName(res.task.name);
      setDescription(res.task.description);
      setAiMsg("");
      onSaved(res.plan_tasks);
    } catch (e: unknown) {
      setAiError(e instanceof Error ? e.message : t("run.ai_error"));
    } finally {
      setAiLoading(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4 backdrop-blur-sm">
      <div className="w-full max-w-2xl overflow-hidden rounded-[28px] border border-border/70 bg-card/95 shadow-[0_28px_80px_rgba(0,0,0,0.38)]">
        <div className="flex items-start justify-between gap-4 border-b border-border/70 px-5 py-4">
          <div>
            <div className="text-[10px] uppercase tracking-[0.18em] text-muted-foreground">{t("run.task_editor")}</div>
            <div className="mt-1 text-lg font-semibold text-foreground">{t("run.edit_task")}</div>
            <p className="mt-1 text-sm text-muted-foreground">{t("run.edit_task_desc")}</p>
          </div>
          <button
            onClick={onClose}
            className="rounded-xl border border-border/70 p-2 text-muted-foreground transition-colors hover:border-border hover:bg-background/80 hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        </div>

        <div className="grid gap-5 px-5 py-5 lg:grid-cols-[minmax(0,1fr)_280px]">
          <div className="space-y-4">
            <div className="space-y-2">
              <label className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">{t("run.task_name")}</label>
              <Input
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="h-11 rounded-2xl border-border/70 bg-background/70"
                placeholder={t("run.task_name")}
              />
            </div>
            <div className="space-y-2">
              <label className="text-[10px] font-medium uppercase tracking-[0.18em] text-muted-foreground">{t("run.task_desc")}</label>
              <textarea
                value={description}
                onChange={(e) => setDescription(e.target.value)}
                className="h-48 w-full resize-none rounded-[22px] border border-border/70 bg-background/70 px-4 py-3 text-sm text-foreground outline-none transition-colors focus:border-violet-500/40 focus:ring-2 focus:ring-violet-500/20"
                placeholder={t("run.task_desc")}
              />
            </div>
          </div>

          <div className="rounded-[24px] border border-violet-500/20 bg-violet-500/8 p-4">
            <div className="flex items-center gap-2 text-[10px] font-medium uppercase tracking-[0.18em] text-violet-300">
              <Sparkles className="h-3.5 w-3.5" />
              {t("run.ai_assistant")}
            </div>
            <p className="mt-2 text-sm leading-6 text-muted-foreground">{t("run.ai_assistant_desc")}</p>
            {aiError ? (
              <div className="mt-3 rounded-2xl border border-red-500/25 bg-red-500/10 px-3 py-2 text-xs text-red-300">
                {aiError}
              </div>
            ) : null}
            <div className="mt-4 space-y-3">
              <Input
                ref={aiInputRef}
                value={aiMsg}
                onChange={(e) => setAiMsg(e.target.value)}
                placeholder={t("run.ai_suggestion")}
                className="h-11 rounded-2xl border-violet-500/20 bg-background/70 text-sm"
                onKeyDown={(e) => e.key === "Enter" && !e.shiftKey && handleAiRefine()}
                disabled={aiLoading}
              />
              <Button
                size="sm"
                className="h-10 w-full rounded-xl bg-violet-600 text-white hover:bg-violet-500"
                onClick={handleAiRefine}
                disabled={aiLoading || !aiMsg.trim()}
              >
                {aiLoading ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Sparkles className="h-3.5 w-3.5" />}
                {aiLoading ? t("run.ai_applying") : t("run.ai_apply")}
              </Button>
            </div>
          </div>
        </div>

        <div className="flex flex-col gap-3 border-t border-border/70 bg-background/35 px-5 py-4 sm:flex-row sm:items-center sm:justify-between">
          <Button
            size="sm"
            variant="destructive"
            className="h-8 px-3 gap-1.5 text-xs"
            onClick={handleDelete}
            disabled={deleting || saving}
          >
            {deleting ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <Trash2 className="h-3.5 w-3.5" />}
            {t("run.delete_task")}
          </Button>
          <div className="flex flex-wrap gap-2">
            <Button size="sm" variant="ghost" className="h-10 rounded-xl px-4" onClick={onClose} disabled={saving}>
              {t("run.cancel")}
            </Button>
            <Button
              size="sm"
              className="h-10 rounded-xl bg-primary px-4 text-primary-foreground"
              onClick={handleSave}
              disabled={saving}
            >
              {saving ? <RefreshCw className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
              {t("run.save")}
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}
