import { CheckCircle2, Loader2, Save, Wand2, X } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Textarea } from "@/components/ui/textarea";
import { PipelineDraftReview } from "@/components/studio/PipelineDraftReview";
import { getAssistantPatchStats } from "@/components/pipeline/assistantPatch";
import type { PipelineNode } from "@/lib/api";
import type { StudioPipelineAssistantResponse } from "@/lib/studioPipelineDraftsApi";
import { cn } from "@/lib/utils";

import { getNodeDisplayLabel } from "./pipelineGraphUtils";
import { localize } from "./presentation";

function AssistantProposalCard({
  proposal,
  onApply,
  onApplyAndSave,
  onDiscard,
  applying,
  lang,
}: {
  proposal: StudioPipelineAssistantResponse;
  onApply: () => void;
  onApplyAndSave: () => void;
  onDiscard: () => void;
  applying?: boolean;
  lang: "en" | "ru";
}) {
  const stats = getAssistantPatchStats(proposal);
  const validationOk = proposal.validation?.ok !== false;
  const riskDangerous = proposal.risk?.level === "dangerous";
  const canApply = stats.hasChanges && validationOk && !riskDangerous && !applying;

  return (
    <div className="rounded-xl border border-border bg-background/70 p-3">
      <PipelineDraftReview
        response={proposal}
        lang={lang}
        compact
        actions={
          <div className="grid grid-cols-2 gap-2">
            <Button size="sm" className="h-8 gap-1.5" onClick={onApplyAndSave} disabled={!canApply}>
              {applying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
              {localize(lang, "Применить и сохранить", "Apply & Save")}
            </Button>
            <Button size="sm" variant="outline" className="h-8 gap-1.5" onClick={onApply} disabled={!canApply}>
              {applying ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
              {localize(lang, "Применить локально", "Apply locally")}
            </Button>
            <Button size="sm" variant="ghost" className="col-span-2 h-8" onClick={onDiscard}>
              {localize(lang, "Скрыть", "Discard")}
            </Button>
          </div>
        }
      />
    </div>
  );
}

export function PipelineAssistantPanel({
  lang,
  selectedNode,
  input,
  history,
  proposal,
  isPending,
  onInputChange,
  onSend,
  onApply,
  onApplyAndSave,
  onDiscard,
  onClose,
}: {
  lang: "en" | "ru";
  selectedNode: PipelineNode | null;
  input: string;
  history: Array<{ role: "user" | "assistant"; content: string }>;
  proposal: StudioPipelineAssistantResponse | null;
  isPending: boolean;
  onInputChange: (value: string) => void;
  onSend: (intent: "create" | "edit" | "validate" | "fix_run", message?: string) => void;
  onApply: () => void;
  onApplyAndSave: () => void;
  onDiscard: () => void;
  onClose: () => void;
}) {
  const selectedLabel = selectedNode ? getNodeDisplayLabel(selectedNode, lang) : localize(lang, "Весь граф", "Whole graph");
  const quickActions = [
    {
      intent: "create" as const,
      label: localize(lang, "Собрать", "Build"),
      prompt: localize(lang, "Собери рабочий pipeline по моему описанию. Если граф пустой, создай полный стартовый workflow.", "Build a working pipeline from my request. If the graph is empty, create a complete starter workflow."),
    },
    {
      intent: "edit" as const,
      label: localize(lang, "Улучшить", "Improve"),
      prompt: localize(lang, "Улучши текущий граф: убери лишнее, добавь недостающие шаги и понятные названия.", "Improve the current graph: remove unnecessary parts, add missing steps, and make labels clear."),
    },
    {
      intent: "validate" as const,
      label: localize(lang, "Проверить", "Validate"),
      prompt: localize(lang, "Проверь текущий pipeline и предложи минимальные исправления, чтобы его можно было сохранить и запустить.", "Validate the current pipeline and propose the smallest fixes needed to save and run."),
    },
    {
      intent: "fix_run" as const,
      label: localize(lang, "Исправить", "Fix errors"),
      prompt: localize(lang, "Исправь ошибки последней проверки или запуска и предложи безопасную правку.", "Fix the latest validation or run errors and propose a safe patch."),
    },
  ];

  return (
    <div className="flex h-full flex-col bg-card">
      <div className="flex items-start justify-between gap-3 border-b border-border px-4 py-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <span className="flex h-7 w-7 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
              <Wand2 className="h-4 w-4 text-primary" />
            </span>
            <div>
              <h3 className="text-sm font-semibold text-foreground">{localize(lang, "AI pipeline", "Pipeline AI")}</h3>
              <p className="text-[11px] text-muted-foreground">{selectedLabel}</p>
            </div>
          </div>
        </div>
        <Button size="icon" variant="ghost" className="h-9 w-9" onClick={onClose} aria-label={localize(lang, "Закрыть AI", "Close AI")}>
          <X className="h-4 w-4" />
        </Button>
      </div>

      <ScrollArea className="min-h-0 flex-1">
        <div className="space-y-3 p-3">
          <div className="grid grid-cols-2 gap-2">
            {quickActions.map((action) => (
              <Button
                key={action.label}
                type="button"
                variant="outline"
                size="sm"
                className="h-9 justify-start gap-1.5 text-xs"
                disabled={isPending}
                onClick={() => onSend(action.intent, input.trim() ? `${action.prompt}\n\n${input.trim()}` : action.prompt)}
              >
                <Wand2 className="h-3.5 w-3.5 text-primary" />
                {action.label}
              </Button>
            ))}
          </div>

          {history.length ? (
            <div className="space-y-2">
              {history.slice(-4).map((item, index) => (
                <div
                  key={`${item.role}-${index}-${item.content.slice(0, 12)}`}
                  className={cn(
                    "rounded-lg border px-3 py-2 text-xs leading-5",
                    item.role === "user"
                      ? "border-primary/20 bg-primary/10 text-primary-foreground"
                      : "border-border bg-background/70 text-muted-foreground",
                  )}
                >
                  <div className="mb-1 text-[10px] font-semibold uppercase tracking-wide text-muted-foreground">
                    {item.role === "user" ? localize(lang, "Запрос", "Request") : localize(lang, "AI", "AI")}
                  </div>
                  <div className="whitespace-pre-wrap">{item.content}</div>
                </div>
              ))}
            </div>
          ) : (
            <div className="rounded-xl border border-dashed border-border px-3 py-4 text-xs leading-5 text-muted-foreground">
              {localize(
                lang,
                "Опишите рабочий процесс: что запускает pipeline, какие серверы или MCP использовать, где нужно подтверждение и куда отправить результат.",
                "Describe the workflow: what should trigger it, which servers or MCPs it should use, where approval is required, and where to send the result.",
              )}
            </div>
          )}

          {proposal ? (
            <AssistantProposalCard
              proposal={proposal}
              lang={lang}
              onApply={onApply}
              onApplyAndSave={onApplyAndSave}
              onDiscard={onDiscard}
              applying={isPending}
            />
          ) : null}
        </div>
      </ScrollArea>

      <div className="space-y-2 border-t border-border p-3">
        <Textarea
          value={input}
          onChange={(event) => onInputChange(event.target.value)}
          placeholder={localize(lang, "Например: проверь Docker-сервис, запроси подтверждение и отправь отчёт в Telegram", "Example: check a Docker service, ask for approval, and send a Telegram report")}
          className="min-h-24 resize-none text-xs"
        />
        <Button
          className="h-10 w-full gap-1.5"
          disabled={isPending || !input.trim()}
          onClick={() => onSend("edit")}
        >
          {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Wand2 className="h-3.5 w-3.5" />}
          {localize(lang, "Подготовить правку", "Prepare change")}
        </Button>
      </div>
    </div>
  );
}
