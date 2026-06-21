import {
  Check,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  ClipboardList,
  FileText,
  Loader2,
  Play,
  Rocket,
  Save,
  ShieldCheck,
  Sparkles,
  Target,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import type { MarsInterviewQuestion, MarsRun } from "@/lib/api";
import { localize } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { isMultiQuestion, splitAnswer, statusTone, TASK_STARTERS } from "./MarsPageUtils";

type BriefStepProps = {
  lang: string;
  taskBrief: string;
  canStartInterview: boolean;
  pending: boolean;
  onTaskBriefChange: (value: string) => void;
  onCreateQuestions: () => void;
};

export function MarsBriefStep({
  lang,
  taskBrief,
  canStartInterview,
  pending,
  onTaskBriefChange,
  onCreateQuestions,
}: BriefStepProps) {
  return (
    <SectionCard
      title={localize(lang, "Задача", "Task")}
      description={localize(lang, "Опишите результат, а MARS задаст уточняющие вопросы перед планом.", "Describe the result; MARS asks clarifying questions before the plan.")}
      icon={<Target className="h-4 w-4" />}
      bodyClassName="space-y-4 px-5 py-5"
      actions={
        <Button size="sm" onClick={onCreateQuestions} disabled={!canStartInterview} className="h-9">
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {localize(lang, "Начать уточнение", "Start questions")}
        </Button>
      }
    >
      <div className="grid gap-4">
        <div className="grid gap-2">
          <Label className="text-xs font-semibold text-muted-foreground">{localize(lang, "Идея проекта", "Project idea")}</Label>
          <Textarea
            value={taskBrief}
            onChange={(event) => onTaskBriefChange(event.target.value)}
            rows={4}
            className="min-h-28 resize-none bg-background text-sm leading-6"
            placeholder={localize(lang, "Например: создать Telegram-бота для заявок или Python-скрипт для отчетов.", "Example: create a Telegram bot for requests or a Python reporting script.")}
          />
        </div>

        <div className="grid gap-2 lg:grid-cols-3">
          {TASK_STARTERS.map((starter) => (
            <button
              key={starter.en}
              type="button"
              onClick={() => onTaskBriefChange(localize(lang, starter.ru, starter.en))}
              className="group flex min-h-[78px] items-start gap-3 rounded-lg border border-border/80 bg-secondary/20 px-3 py-3 text-left transition-colors hover:border-primary/35 hover:bg-secondary/50"
            >
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md border border-primary/20 bg-primary/10 text-primary">
                <FileText className="h-3.5 w-3.5" />
              </span>
              <span className="min-w-0">
                <span className="line-clamp-2 text-xs leading-5 text-foreground">{localize(lang, starter.ru, starter.en)}</span>
                <span className="mt-1 inline-block text-xs text-muted-foreground underline-offset-2 group-hover:text-primary group-hover:underline">
                  {localize(lang, "Пример запроса", "Example request")}
                </span>
              </span>
            </button>
          ))}
        </div>
      </div>
    </SectionCard>
  );
}

type InterviewStepProps = {
  lang: string;
  questions: MarsInterviewQuestion[];
  activeQuestion: MarsInterviewQuestion | null;
  activeQuestionIndex: number;
  answers: Record<string, string>;
  answeredQuestionCount: number;
  requiredQuestionCount: number;
  answeredRequiredCount: number;
  minimumAnswers: number;
  interviewReady: boolean;
  interviewProgress: number;
  canSaveAnswers: boolean;
  pending: boolean;
  onAnswerChange: (questionId: string, value: string) => void;
  onToggleOption: (question: MarsInterviewQuestion, option: string) => void;
  onMoveQuestion: (direction: -1 | 1) => void;
  onJumpToFirstUnanswered: () => void;
  onSelectQuestion: (questionId: string) => void;
  onBuildPlan: () => void;
};

export function MarsInterviewStep({
  lang,
  questions,
  activeQuestion,
  activeQuestionIndex,
  answers,
  answeredQuestionCount,
  requiredQuestionCount,
  answeredRequiredCount,
  minimumAnswers,
  interviewReady,
  interviewProgress,
  canSaveAnswers,
  pending,
  onAnswerChange,
  onToggleOption,
  onMoveQuestion,
  onJumpToFirstUnanswered,
  onSelectQuestion,
  onBuildPlan,
}: InterviewStepProps) {
  const answerPreview = (questionId: string): string => {
    const answer = (answers[questionId] || "").trim();
    if (!answer) return localize(lang, "Нет ответа", "No answer");
    return answer.length > 96 ? `${answer.slice(0, 96)}...` : answer;
  };

  return (
    <SectionCard
      title={localize(lang, "Уточнения", "Clarifying questions")}
      description={localize(
        lang,
        `Ответьте минимум на ${minimumAnswers} вопросов, чтобы MARS понял результат, ограничения и проверку.`,
        `Answer at least ${minimumAnswers} questions so MARS understands the result, limits, and verification.`,
      )}
      icon={<ClipboardList className="h-4 w-4" />}
      actions={
        <div className="flex min-w-[220px] items-center gap-3">
          <Progress value={interviewProgress} className="h-2" />
          <StatusBadge label={`${answeredQuestionCount}/${questions.length}`} tone={interviewReady ? "success" : "info"} />
        </div>
      }
    >
      {activeQuestion ? (
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_300px]">
          <div className="space-y-5">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div className="flex min-w-0 items-center gap-3">
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-sm font-semibold text-primary">
                  {activeQuestionIndex + 1}
                </span>
                <div className="min-w-0">
                  <div className="text-xs font-semibold uppercase tracking-wide text-primary">
                    {localize(lang, `Вопрос ${activeQuestionIndex + 1} из ${questions.length}`, `Question ${activeQuestionIndex + 1} of ${questions.length}`)}
                  </div>
                  <div className="truncate text-xs text-muted-foreground">
                    {isMultiQuestion(activeQuestion)
                      ? localize(lang, "Можно выбрать несколько вариантов", "Pick multiple options")
                      : localize(lang, "Выберите вариант или напишите точнее", "Pick an option or clarify")}
                  </div>
                </div>
              </div>
              <StatusBadge
                label={(answers[activeQuestion.id] || "").trim() ? localize(lang, "ответ есть", "answered") : localize(lang, "нужен ответ", "needs answer")}
                tone={(answers[activeQuestion.id] || "").trim() ? "success" : "info"}
              />
            </div>

            <div>
              <Label className="block text-base font-semibold leading-6 text-foreground">
                {activeQuestion.question}
                {activeQuestion.required ? <span className="text-destructive"> *</span> : null}
              </Label>

              {activeQuestion.options?.length ? (
                <div className="mt-4 grid gap-2 sm:grid-cols-2">
                  {activeQuestion.options.map((option) => {
                    const value = answers[activeQuestion.id] || "";
                    const selectedOptions = splitAnswer(value);
                    const selected = isMultiQuestion(activeQuestion) ? selectedOptions.includes(option) : value === option;
                    return (
                      <button
                        key={option}
                        type="button"
                        onClick={() => onToggleOption(activeQuestion, option)}
                        className={cn(
                          "flex min-h-12 items-center gap-3 rounded-lg border px-3 py-2 text-left text-sm transition-colors",
                          selected
                            ? "border-primary/45 bg-primary/10 text-foreground shadow-sm"
                            : "border-border bg-secondary/20 text-muted-foreground hover:bg-secondary/50 hover:text-foreground",
                        )}
                      >
                        <span className={cn("flex h-5 w-5 shrink-0 items-center justify-center rounded-md border", selected ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground")}>
                          {selected ? <Check className="h-3.5 w-3.5" /> : <CircleDot className="h-3.5 w-3.5" />}
                        </span>
                        <span className="min-w-0 [overflow-wrap:anywhere]">{option}</span>
                      </button>
                    );
                  })}
                </div>
              ) : null}
            </div>

            <div className="grid gap-2">
              <Label>{localize(lang, "Детали для MARS", "Details for MARS")}</Label>
              <Textarea
                value={answers[activeQuestion.id] || ""}
                onChange={(event) => onAnswerChange(activeQuestion.id, event.target.value)}
                rows={4}
                className="min-h-24 resize-none bg-background text-sm leading-6"
                placeholder={activeQuestion.placeholder || localize(lang, "Добавьте детали, чтобы MARS не гадал.", "Add details so MARS does not guess.")}
              />
            </div>

            <div className="flex flex-col gap-3 border-t border-border/70 pt-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-sm text-muted-foreground">
                {interviewReady
                  ? localize(lang, "Ответов достаточно, можно собрать план.", "Enough answers; you can build the plan.")
                  : localize(lang, `До плана осталось ${Math.max(0, minimumAnswers - answeredQuestionCount)} ответов.`, `${Math.max(0, minimumAnswers - answeredQuestionCount)} more answers before the plan.`)}
              </div>
              <div className="flex flex-wrap gap-2">
                <Button variant="outline" onClick={() => onMoveQuestion(-1)} disabled={activeQuestionIndex <= 0}>
                  <ChevronLeft className="h-4 w-4" />
                  {localize(lang, "Назад", "Back")}
                </Button>
                <Button variant="secondary" onClick={() => onMoveQuestion(1)} disabled={activeQuestionIndex >= questions.length - 1}>
                  {localize(lang, "Дальше", "Next")}
                  <ChevronRight className="h-4 w-4" />
                </Button>
                <Button size="sm" onClick={onBuildPlan} disabled={!canSaveAnswers}>
                  {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {localize(lang, "Собрать план", "Build plan")}
                </Button>
              </div>
            </div>
          </div>

          <aside className="space-y-3">
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-2">
                <div className="text-sm font-semibold text-foreground">{localize(lang, "Карта вопросов", "Question map")}</div>
                <StatusBadge label={`${answeredRequiredCount}/${requiredQuestionCount || questions.length}`} tone={interviewReady ? "success" : "info"} />
              </div>
              <Progress value={interviewProgress} className="h-2" />
              <Button type="button" variant="ghost" size="sm" className="w-full justify-start" onClick={onJumpToFirstUnanswered} disabled={answeredQuestionCount === questions.length}>
                <CircleDot className="h-4 w-4" />
                {localize(lang, "Перейти к пустому", "Go to unanswered")}
              </Button>
            </div>

            <div className="max-h-[480px] space-y-2 overflow-y-auto pr-1">
              {questions.map((question, index) => {
                const answered = Boolean((answers[question.id] || "").trim());
                const active = question.id === activeQuestion.id;
                return (
                  <button
                    key={question.id}
                    type="button"
                    onClick={() => onSelectQuestion(question.id)}
                    className={cn("w-full rounded-lg border px-3 py-2 text-left transition-colors", active ? "border-primary/45 bg-primary/10" : "border-border bg-secondary/20 hover:bg-secondary/50")}
                  >
                    <div className="flex items-start gap-2">
                      <span className={cn("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-xs font-semibold", answered ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground")}>
                        {answered ? <Check className="h-3 w-3" /> : index + 1}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-medium text-foreground">{question.question}</span>
                        <span className="mt-0.5 block truncate text-xs text-muted-foreground">{answerPreview(question.id)}</span>
                      </span>
                    </div>
                  </button>
                );
              })}
            </div>
          </aside>
        </div>
      ) : (
        <div className="rounded-lg border border-dashed border-border px-4 py-10 text-center text-sm text-muted-foreground">
          {localize(lang, "Сначала опишите проект на первом шаге.", "Describe the project in the first step first.")}
        </div>
      )}
    </SectionCard>
  );
}

type PlanStepProps = {
  lang: string;
  goalText: string;
  planDraft: string;
  canApprovePlan: boolean;
  pending: boolean;
  onPlanChange: (value: string) => void;
  onApprovePlan: () => void;
};

export function MarsPlanStep({ lang, goalText, planDraft, canApprovePlan, pending, onPlanChange, onApprovePlan }: PlanStepProps) {
  return (
    <SectionCard
      title={localize(lang, "План", "Plan")}
      description={localize(lang, "Проверьте, как MARS понял задачу. Здесь можно поправить план перед выполнением.", "Review how MARS understood the task. You can edit the plan before execution.")}
      icon={<ShieldCheck className="h-4 w-4" />}
      actions={
        <Button size="sm" onClick={onApprovePlan} disabled={!canApprovePlan} className="h-9">
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          {localize(lang, "Подтвердить план", "Approve plan")}
        </Button>
      }
    >
      <div className="space-y-5">
        {goalText ? (
          <div className="rounded-lg border border-primary/25 bg-primary/10 px-4 py-3">
            <div className="mb-1 flex items-center gap-2 text-xs font-semibold text-primary">
              <Rocket className="h-3.5 w-3.5" />
              {localize(lang, "Цель", "Goal")}
            </div>
            <div className="text-sm leading-6 text-foreground">{goalText}</div>
          </div>
        ) : null}

        <div className="grid gap-2">
          <Label>{localize(lang, "Что будет сделано", "What will be done")}</Label>
          <Textarea
            value={planDraft}
            onChange={(event) => onPlanChange(event.target.value)}
            rows={16}
            className="min-h-80 resize-none bg-background font-mono text-xs leading-5"
            placeholder={localize(lang, "План появится после ответов.", "The plan appears after answers.")}
          />
        </div>
      </div>
    </SectionCard>
  );
}

type RunStepProps = {
  lang: string;
  latestRun: MarsRun | undefined;
  latestRunId: number | null;
  sessionStatus: string | undefined;
  testCommand: string;
  canRun: boolean;
  runPending: boolean;
  onTestCommandChange: (value: string) => void;
  onRun: () => void;
  onOpenRun: (runId: number) => void;
};

export function MarsRunStep({
  lang,
  latestRun,
  latestRunId,
  sessionStatus,
  testCommand,
  canRun,
  runPending,
  onTestCommandChange,
  onRun,
  onOpenRun,
}: RunStepProps) {
  return (
    <SectionCard
      title={localize(lang, "Выполнение", "Run")}
      description={localize(lang, "MARS изменит файлы, запустит проверки и покажет ход работы.", "MARS changes files, runs checks, and shows progress.")}
      icon={<Play className="h-4 w-4" />}
      actions={
        <StatusBadge
          label={latestRun?.status ? latestRun.status.replaceAll("_", " ") : sessionStatus === "approved" ? localize(lang, "готово к запуску", "ready to run") : localize(lang, "ожидает план", "waiting for plan")}
          tone={latestRun ? statusTone(latestRun.status) : sessionStatus === "approved" ? "success" : "neutral"}
        />
      }
    >
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-4">
          <div className="grid gap-2 rounded-lg border border-border/80 bg-secondary/20 px-3 py-3 text-sm text-muted-foreground sm:grid-cols-3">
            <div>{localize(lang, "Изменяет код", "Changes code")}</div>
            <div>{localize(lang, "Создает файлы", "Creates files")}</div>
            <div>{localize(lang, "Запускает проверки", "Runs checks")}</div>
          </div>

          <div className="grid gap-2">
            <Label>{localize(lang, "Как проверить результат", "How to verify the result")}</Label>
            <Input value={testCommand} onChange={(event) => onTestCommandChange(event.target.value)} placeholder="npm run build" className="bg-background font-mono text-xs" />
          </div>
        </div>

        <div className="space-y-2">
          <Button className="w-full" size="sm" onClick={onRun} disabled={!canRun}>
            {runPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {localize(lang, "Запустить выполнение", "Start run")}
          </Button>
          {latestRunId ? (
            <Button className="w-full" variant="ghost" onClick={() => onOpenRun(latestRunId)}>
              {localize(lang, "Открыть запуск", "Open run")}
            </Button>
          ) : null}
        </div>
      </div>
    </SectionCard>
  );
}
