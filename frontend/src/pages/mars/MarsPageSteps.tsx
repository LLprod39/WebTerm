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
      title={localize(lang, "Guided brief", "Guided brief")}
      description={localize(lang, "Коротко опишите проект, а MARS задаст правильные вопросы и соберет детали.", "Describe the project; MARS asks the right questions and gathers details.")}
      icon={<Target className="h-4 w-4" />}
      className="border-[#27323b] bg-[#111922]/88 shadow-[0_18px_60px_rgba(0,0,0,0.28)]"
      bodyClassName="space-y-4 px-5 py-5"
      actions={
        <Button size="sm" onClick={onCreateQuestions} disabled={!canStartInterview} className="h-9 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25">
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
          {localize(lang, "Начать уточнение", "Start questions")}
        </Button>
      }
    >
      <div className="grid gap-4">
        <div className="grid gap-2">
          <Label className="text-xs font-semibold text-slate-300">{localize(lang, "Идея проекта", "Project idea")}</Label>
          <Textarea
            value={taskBrief}
            onChange={(event) => onTaskBriefChange(event.target.value)}
            rows={4}
            className="min-h-28 resize-none border-[#26313a] bg-[#0f171f] text-sm leading-6 text-slate-100 placeholder:text-slate-500"
            placeholder={localize(lang, "Например: создать Telegram-бота для заявок или Python-скрипт для отчетов.", "Example: create a Telegram bot for requests or a Python reporting script.")}
          />
        </div>

        <div className="grid gap-2 lg:grid-cols-3">
          {TASK_STARTERS.map((starter) => (
            <button
              key={starter.en}
              type="button"
              onClick={() => onTaskBriefChange(localize(lang, starter.ru, starter.en))}
              className="group flex min-h-[78px] items-start gap-3 rounded-lg border border-[#26313a] bg-[#0f171f] px-3 py-3 text-left transition-colors hover:border-emerald-400/35 hover:bg-[#14201f]"
            >
              <span className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-emerald-400/10 text-emerald-300">
                <FileText className="h-3.5 w-3.5" />
              </span>
              <span className="min-w-0">
                <span className="line-clamp-2 text-xs leading-5 text-slate-300">{localize(lang, starter.ru, starter.en)}</span>
                <span className="mt-1 inline-block text-[11px] text-slate-500 underline-offset-2 group-hover:text-emerald-300 group-hover:underline">
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
      title={localize(lang, "Уточнения для ИИ", "AI clarification")}
      description={localize(
        lang,
        `Ответьте минимум на ${minimumAnswers} вопросов, чтобы ИИ точно понял результат, ограничения и проверку.`,
        `Answer at least ${minimumAnswers} questions so the AI understands the result, limits, and verification.`,
      )}
      icon={<ClipboardList className="h-4 w-4" />}
      className="border-[#27323b] bg-[#111922]/88 shadow-[0_18px_60px_rgba(0,0,0,0.28)]"
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
                <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-emerald-400/15 text-sm font-semibold text-emerald-300">
                  {activeQuestionIndex + 1}
                </span>
                <div className="min-w-0">
                  <div className="text-xs font-semibold uppercase tracking-wide text-emerald-300">
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
                            ? "border-emerald-400/45 bg-emerald-400/12 text-slate-100 shadow-sm"
                            : "border-[#26313a] bg-[#0f171f] text-slate-400 hover:bg-[#151f28] hover:text-slate-100",
                        )}
                      >
                        <span className={cn("flex h-5 w-5 shrink-0 items-center justify-center rounded-md border", selected ? "border-emerald-400 bg-emerald-400 text-[#07110f]" : "border-[#3a4652] text-slate-500")}>
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
              <Label>{localize(lang, "Детали для ИИ", "Details for the AI")}</Label>
              <Textarea
                value={answers[activeQuestion.id] || ""}
                onChange={(event) => onAnswerChange(activeQuestion.id, event.target.value)}
                rows={4}
                className="min-h-24 resize-none border-[#26313a] bg-[#0f171f] text-sm leading-6 text-slate-100 placeholder:text-slate-500"
                placeholder={activeQuestion.placeholder || localize(lang, "Добавьте детали, чтобы MARS не гадал.", "Add details so MARS does not guess.")}
              />
            </div>

            <div className="flex flex-col gap-3 border-t border-border/70 pt-4 sm:flex-row sm:items-center sm:justify-between">
              <div className="text-sm text-muted-foreground">
                {interviewReady
                  ? localize(lang, "Ответов достаточно, можно собрать ТЗ и план.", "Enough answers; you can build the spec and plan.")
                  : localize(lang, `До ТЗ осталось ${Math.max(0, minimumAnswers - answeredQuestionCount)} ответов.`, `${Math.max(0, minimumAnswers - answeredQuestionCount)} more answers before the spec.`)}
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
                  {localize(lang, "Собрать ТЗ", "Build spec")}
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
                    className={cn("w-full rounded-lg border px-3 py-2 text-left transition-colors", active ? "border-emerald-400/45 bg-emerald-400/10" : "border-[#26313a] bg-[#0f171f] hover:bg-[#151f28]")}
                  >
                    <div className="flex items-start gap-2">
                      <span className={cn("mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold", answered ? "bg-emerald-400 text-[#07110f]" : "bg-[#1b2530] text-slate-400")}>
                        {answered ? <Check className="h-3 w-3" /> : index + 1}
                      </span>
                      <span className="min-w-0 flex-1">
                        <span className="block truncate text-xs font-medium text-foreground">{question.question}</span>
                        <span className="mt-0.5 block truncate text-[11px] text-muted-foreground">{answerPreview(question.id)}</span>
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
      title={localize(lang, "ТЗ и план", "Spec and plan")}
      description={localize(lang, "Проверьте, как MARS понял задачу. Здесь можно поправить ТЗ перед созданием.", "Review how MARS understood the task. You can edit the spec before building.")}
      icon={<ShieldCheck className="h-4 w-4" />}
      className="border-[#27323b] bg-[#111922]/88 shadow-[0_18px_60px_rgba(0,0,0,0.28)]"
      actions={
        <Button size="sm" onClick={onApprovePlan} disabled={!canApprovePlan} className="h-9 bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25">
          {pending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
          {localize(lang, "Подтвердить ТЗ", "Approve spec")}
        </Button>
      }
    >
      <div className="space-y-5">
        {goalText ? (
          <div className="rounded-lg border border-emerald-400/25 bg-emerald-400/10 px-4 py-3">
            <div className="mb-1 flex items-center gap-2 text-xs font-semibold text-emerald-300">
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
            className="min-h-80 resize-none border-[#26313a] bg-[#0f171f] font-mono text-xs leading-5 text-slate-100 placeholder:text-slate-500"
            placeholder={localize(lang, "ТЗ и план появятся после ответов.", "Spec and plan appear after answers.")}
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
      title={localize(lang, "Создание", "Build")}
      description={localize(lang, "MARS начнет редактировать файлы, писать код, запускать проверки и показывать ход работы.", "MARS starts editing files, writing code, running checks, and showing progress.")}
      icon={<Play className="h-4 w-4" />}
      className="border-[#27323b] bg-[#111922]/88 shadow-[0_18px_60px_rgba(0,0,0,0.28)]"
      actions={
        <StatusBadge
          label={latestRun?.status ? latestRun.status.replaceAll("_", " ") : sessionStatus === "approved" ? localize(lang, "готов к созданию", "ready to build") : localize(lang, "ожидает ТЗ", "waiting for spec")}
          tone={latestRun ? statusTone(latestRun.status) : sessionStatus === "approved" ? "success" : "neutral"}
        />
      }
    >
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_280px]">
        <div className="space-y-4">
          <div className="grid gap-2 rounded-lg border border-[#26313a] bg-[#0f171f] px-3 py-3 text-sm text-slate-400 sm:grid-cols-3">
            <div>{localize(lang, "Редактирует код", "Edits code")}</div>
            <div>{localize(lang, "Создает файлы", "Creates files")}</div>
            <div>{localize(lang, "Запускает проверку", "Runs checks")}</div>
          </div>

          <div className="grid gap-2">
            <Label>{localize(lang, "Как проверить результат", "How to verify the result")}</Label>
            <Input value={testCommand} onChange={(event) => onTestCommandChange(event.target.value)} placeholder="npm run build" className="border-[#26313a] bg-[#0f171f] font-mono text-xs text-slate-100" />
          </div>
        </div>

        <div className="space-y-2">
          <Button className="w-full bg-emerald-500/15 text-emerald-300 hover:bg-emerald-500/25" size="sm" onClick={onRun} disabled={!canRun}>
            {runPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
            {localize(lang, "Создать проект", "Build project")}
          </Button>
          {latestRunId ? (
            <Button className="w-full" variant="ghost" onClick={() => onOpenRun(latestRunId)}>
              {localize(lang, "Открыть run", "Open run")}
            </Button>
          ) : null}
        </div>
      </div>
    </SectionCard>
  );
}
