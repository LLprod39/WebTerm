import type { Dispatch, SetStateAction } from "react";
import { GitBranch, HelpCircle, Loader2, RefreshCw, Send, Sparkles, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import type {
  StudioPipelineAssistantPayload,
  StudioPipelineAssistantResponse,
  StudioPipelineDraftSession,
} from "@/lib/studioPipelineDraftsApi";

import type { StudioDraftMobilePane } from "./studioDraftsModel";

export function StudioDraftComposerPanel({
  lang,
  mobilePane,
  activeDraft,
  activeResponse,
  hasOpenQuestions,
  openQuestions,
  questionAnswers,
  prompt,
  draftName,
  promptPresets,
  submitWillRevise,
  createPending,
  canSubmitComposer,
  onNewDraft,
  onQuestionAnswersChange,
  onPromptChange,
  onDraftNameChange,
  onSubmit,
}: {
  lang: string;
  mobilePane: StudioDraftMobilePane;
  activeDraft: StudioPipelineDraftSession | null;
  activeResponse: StudioPipelineAssistantResponse | null;
  hasOpenQuestions: boolean;
  openQuestions: string[];
  questionAnswers: Record<number, string>;
  prompt: string;
  draftName: string;
  promptPresets: string[];
  submitWillRevise: boolean;
  createPending: boolean;
  canSubmitComposer: boolean;
  onNewDraft: () => void;
  onQuestionAnswersChange: Dispatch<SetStateAction<Record<number, string>>>;
  onPromptChange: (prompt: string) => void;
  onDraftNameChange: (name: string) => void;
  onSubmit: (messageOverride?: string, compilerMode?: StudioPipelineAssistantPayload["compiler_mode"]) => void;
}) {
  return (
    <div className={cn("min-h-0 flex-1 overflow-y-auto p-4 xl:block", mobilePane === "review" ? "hidden" : "block")}>
      <div className="flex items-center justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            <Sparkles className="h-3.5 w-3.5" />
            {localize(lang, "Описание задачи", "Request")}
          </div>
          <div className="mt-1 text-xs text-muted-foreground/80">
            {hasOpenQuestions
              ? localize(lang, "Ответьте на вопросы черновика", "Answer draft questions")
              : submitWillRevise
                ? localize(lang, "Уточнение активного черновика", "Revising active draft")
                : localize(lang, "Создание нового черновика", "Creating new draft")}
          </div>
        </div>
        {activeDraft ? (
          <Button type="button" variant="ghost" size="sm" className="h-8 gap-1.5" onClick={onNewDraft}>
            <XCircle className="h-3.5 w-3.5" />
            {localize(lang, "Очистить", "Clear")}
          </Button>
        ) : null}
      </div>

      <div className="mt-3 grid gap-3">
        <label className="grid gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            {localize(lang, "Название пайплайна", "Pipeline name")}
          </span>
          <Input
            value={draftName}
            onChange={(event) => onDraftNameChange(event.target.value)}
            className="h-10 min-w-0 bg-background/70"
            aria-label={localize(lang, "Название черновика пайплайна", "Draft pipeline name")}
          />
        </label>
        {hasOpenQuestions ? (
          <div className="rounded-lg border border-sky-500/25 bg-sky-500/10 p-3">
            <div className="flex min-w-0 items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-sky-100">
                <HelpCircle className="h-3.5 w-3.5 shrink-0" />
                <span className="truncate">{localize(lang, "Не хватает деталей", "Missing details")}</span>
              </div>
              <Badge variant="outline" className="shrink-0 border-sky-400/25 bg-sky-400/10 text-xs text-sky-100">
                {Object.values(questionAnswers).filter((value) => value.trim()).length}/{openQuestions.length}
              </Badge>
            </div>
            <div className="mt-3 grid gap-2">
              {openQuestions.map((question, index) => (
                <label key={`${question}-${index}`} className="grid min-w-0 gap-2 rounded-md border border-sky-400/20 bg-background/55 p-2.5">
                  <span className="flex min-w-0 gap-2 text-xs font-medium leading-5 text-sky-50">
                    <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-sky-300/25 bg-sky-300/10 text-xs">
                      {index + 1}
                    </span>
                    <span className="min-w-0 [overflow-wrap:anywhere]">{question}</span>
                  </span>
                  <Textarea
                    value={questionAnswers[index] || ""}
                    onChange={(event) => onQuestionAnswersChange((current) => ({ ...current, [index]: event.target.value }))}
                    placeholder={localize(lang, "Ответ...", "Answer...")}
                    className="min-h-[60px] min-w-0 resize-y border-sky-400/20 bg-card/75 text-sm leading-5 [overflow-wrap:anywhere]"
                    aria-label={localize(lang, `Ответ на вопрос ${index + 1}`, `Question ${index + 1} answer`)}
                  />
                </label>
              ))}
            </div>
          </div>
        ) : null}
        <label className="grid gap-1.5">
          <span className="text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
            {hasOpenQuestions ? localize(lang, "Доп. сведения", "Extra details") : localize(lang, "Задача для пайплайна", "Pipeline task")}
          </span>
          <Textarea
            value={prompt}
            onChange={(event) => onPromptChange(event.target.value)}
            placeholder={localize(
              lang,
              hasOpenQuestions
                ? "Если нужно, добавь ограничения, окружение или комментарий."
                : "Опишите запуск, серверы, условия, подтверждения и получателя результата.",
              hasOpenQuestions
                ? "Add constraints, environment, or a note if needed."
                : "Describe the trigger, servers, conditions, approvals, and delivery target.",
            )}
            className={cn(
              "min-w-0 resize-none bg-background/70 text-sm leading-6 [overflow-wrap:anywhere]",
              hasOpenQuestions ? "min-h-[76px]" : "min-h-[132px]",
            )}
            aria-label={localize(lang, "Задача для пайплайна", "Pipeline task")}
          />
        </label>
      </div>

      {!hasOpenQuestions ? (
        <div className="mt-3 grid min-w-0 gap-2">
          {promptPresets.map((preset) => (
            <Button
              key={preset}
              type="button"
              variant="outline"
              size="sm"
              className="h-auto min-h-9 w-full min-w-0 justify-start whitespace-normal rounded-md border-border/80 bg-background/40 px-3 py-2 text-left text-xs leading-4 [overflow-wrap:anywhere]"
              disabled={createPending}
              onClick={() => {
                onPromptChange(preset);
                onSubmit(preset);
              }}
            >
              {preset}
            </Button>
          ))}
        </div>
      ) : null}

      <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
        <Button type="button" className="h-10 gap-2" disabled={createPending || !canSubmitComposer} onClick={() => onSubmit()}>
          {createPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          {hasOpenQuestions
            ? localize(lang, "Ответить на вопросы", "Answer questions")
            : submitWillRevise
              ? localize(lang, "Уточнить черновик", "Revise draft")
              : localize(lang, "Собрать граф", "Build graph")}
        </Button>
        {!hasOpenQuestions ? (
          <Button
            type="button"
            variant="outline"
            className="h-10 gap-2"
            disabled={createPending || !prompt.trim()}
            onClick={() => onSubmit(undefined, "deterministic")}
          >
            {createPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitBranch className="h-4 w-4" />}
            {localize(lang, "Быстрый шаблон", "Quick template")}
          </Button>
        ) : null}
        {activeResponse?.validation?.ok === false && !hasOpenQuestions ? (
          <Button
            type="button"
            variant="outline"
            className="h-10 gap-2"
            disabled={createPending}
            onClick={() =>
              onSubmit(
                localize(
                  lang,
                  `Пересобери черновик как валидный граф. Исправь ошибки: ${(activeResponse.validation?.errors || []).join("; ")}.`,
                  `Rebuild the draft as a valid graph. Fix errors: ${(activeResponse.validation?.errors || []).join("; ")}.`,
                ),
              )
            }
          >
            <RefreshCw className="h-4 w-4" />
            {localize(lang, "Исправить граф", "Fix graph")}
          </Button>
        ) : null}
      </div>
    </div>
  );
}
