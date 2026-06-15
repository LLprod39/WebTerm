import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  BrainCircuit,
  Check,
  ChevronLeft,
  ChevronRight,
  CircleDot,
  ClipboardList,
  FolderGit2,
  Loader2,
  Play,
  Rocket,
  Save,
  ShieldCheck,
  Sparkles,
  Square,
  Target,
} from "lucide-react";
import { useNavigate } from "react-router-dom";

import { Button } from "@/components/ui/button";
import { Checkbox } from "@/components/ui/checkbox";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { PageGrid, PageHero, PageShell, QueryStateBlock, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { Progress } from "@/components/ui/progress";
import { Textarea } from "@/components/ui/textarea";
import { localize, useI18n } from "@/lib/i18n";
import { marsApi, type MarsSession } from "@/lib/api";
import { cn } from "@/lib/utils";

const SKILL_OPTIONS = [
  { slug: "frontend-design", label: "frontend-design", tags: "UI/UX, polish" },
  { slug: "frontend-dev", label: "frontend-dev", tags: "app build" },
  { slug: "react-best-practices", label: "react-best-practices", tags: "React" },
  { slug: "frontend-testing-debugging", label: "frontend-testing-debugging", tags: "tests/debug" },
];

function mutationMessage(error: unknown): string {
  return error instanceof Error ? error.message : "Request failed";
}

function statusTone(status?: string): "neutral" | "success" | "warning" | "danger" | "info" {
  if (!status) return "neutral";
  if (status === "approved" || status === "completed") return "success";
  if (status === "failed") return "danger";
  if (status === "running" || status === "queued") return "info";
  if (status === "plan_ready") return "warning";
  return "neutral";
}

function isMultiQuestion(question: MarsSession["interview_questions"][number]): boolean {
  return question.kind.includes("multi");
}

function splitAnswer(value: string): string[] {
  return value
    .split(/[;\n]/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function joinAnswer(items: string[]): string {
  return items.join("; ");
}

export default function MarsPage() {
  const { lang } = useI18n();
  const navigate = useNavigate();

  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [taskBrief, setTaskBrief] = useState("");
  const [session, setSession] = useState<MarsSession | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [selectedSkills, setSelectedSkills] = useState<string[]>(SKILL_OPTIONS.map((skill) => skill.slug));
  const [planDraft, setPlanDraft] = useState("");
  const [allowDirty, setAllowDirty] = useState(false);
  const [testCommand, setTestCommand] = useState("");
  const [latestRunId, setLatestRunId] = useState<number | null>(null);
  const [activeQuestionId, setActiveQuestionId] = useState("");

  const workspacesQuery = useQuery({
    queryKey: ["mars", "workspaces"],
    queryFn: marsApi.listWorkspaces,
    retry: false,
  });

  const workspaces = workspacesQuery.data?.workspaces ?? [];
  const selectedWorkspace = useMemo(
    () => workspaces.find((workspace) => String(workspace.id) === selectedWorkspaceId) ?? null,
    [selectedWorkspaceId, workspaces],
  );

  useEffect(() => {
    if (workspaces.length > 0 && !workspaces.some((workspace) => String(workspace.id) === selectedWorkspaceId)) {
      setSelectedWorkspaceId(String(workspaces[0].id));
    }
  }, [selectedWorkspaceId, workspaces]);

  const latestRunQuery = useQuery({
    queryKey: ["mars", "run", latestRunId],
    queryFn: () => marsApi.getRun(Number(latestRunId)),
    enabled: latestRunId !== null,
    refetchInterval: (query) => {
      const status = query.state.data?.run.status;
      return status === "queued" || status === "running" ? 2000 : false;
    },
  });
  const latestRun = latestRunQuery.data?.run;

  const createSession = useMutation({
    mutationFn: () =>
      marsApi.createSession({
        workspace_id: Number(selectedWorkspaceId),
        task_brief: taskBrief,
        selected_skill_slugs: selectedSkills,
      }),
    onSuccess: ({ session: nextSession, recommended_skills }) => {
      setSession(nextSession);
      setAnswers(nextSession.answers || {});
      setSelectedSkills(nextSession.selected_skill_slugs.length ? nextSession.selected_skill_slugs : recommended_skills);
      setPlanDraft(nextSession.generated_plan || "");
      setActiveQuestionId(nextSession.interview_questions[0]?.id || "");
    },
  });

  const answerSession = useMutation({
    mutationFn: () => marsApi.answerSession(Number(session?.id), { answers, selected_skill_slugs: selectedSkills }),
    onSuccess: ({ session: nextSession }) => {
      setSession(nextSession);
      setPlanDraft(nextSession.generated_plan || "");
    },
  });

  const approvePlan = useMutation({
    mutationFn: () =>
      marsApi.approveSessionPlan(Number(session?.id), {
        generated_plan: planDraft,
        selected_skill_slugs: selectedSkills,
      }),
    onSuccess: ({ session: nextSession }) => {
      setSession(nextSession);
      setPlanDraft(nextSession.generated_plan || planDraft);
    },
  });

  const runSession = useMutation({
    mutationFn: () => marsApi.runSession(Number(session?.id), { allow_dirty: allowDirty, test_command: testCommand }),
    onSuccess: ({ run }) => {
      setLatestRunId(run.id);
      navigate(`/mars/runs/${run.id}`);
    },
  });

  const stopRun = useMutation({
    mutationFn: () => marsApi.stopRun(Number(latestRunId)),
    onSuccess: ({ run }) => setLatestRunId(run.id),
  });

  const firstError = [
    createSession.error,
    answerSession.error,
    approvePlan.error,
    runSession.error,
    stopRun.error,
  ].find(Boolean);

  const interviewQuestions = session?.interview_questions ?? [];
  const activeQuestion = interviewQuestions.find((question) => question.id === activeQuestionId) ?? interviewQuestions[0] ?? null;
  const activeQuestionIndex = activeQuestion ? interviewQuestions.findIndex((question) => question.id === activeQuestion.id) : -1;
  const answeredQuestionCount = interviewQuestions.filter((question) => (answers[question.id] || "").trim()).length;
  const requiredQuestionCount = interviewQuestions.filter((question) => question.required).length;
  const answeredRequiredCount = interviewQuestions.filter((question) => question.required && (answers[question.id] || "").trim()).length;
  const minimumAnswers = Math.min(5, Math.max(1, requiredQuestionCount || interviewQuestions.length));
  const interviewReady = Boolean(session && answeredQuestionCount >= minimumAnswers);
  const interviewProgress = interviewQuestions.length ? Math.round((answeredQuestionCount / interviewQuestions.length) * 100) : 0;
  const goalText = (answers.success_criteria || session?.task_brief || taskBrief || "").trim();

  const canStartInterview = Boolean(selectedWorkspace && taskBrief.trim()) && !createSession.isPending;
  const canSaveAnswers = interviewReady && !answerSession.isPending;
  const canApprovePlan = Boolean(session && planDraft.trim()) && !approvePlan.isPending;
  const canRun = Boolean(session?.status === "approved") && !runSession.isPending;
  const canStop = Boolean(latestRunId && (latestRun?.status === "queued" || latestRun?.status === "running"));

  useEffect(() => {
    if (!interviewQuestions.length) {
      setActiveQuestionId("");
      return;
    }
    if (!interviewQuestions.some((question) => question.id === activeQuestionId)) {
      setActiveQuestionId(interviewQuestions[0].id);
    }
  }, [activeQuestionId, interviewQuestions]);

  const setSkill = (slug: string, checked: boolean) => {
    setSelectedSkills((current) => {
      if (checked) return current.includes(slug) ? current : [...current, slug];
      return current.filter((item) => item !== slug);
    });
  };

  const setQuestionAnswer = (questionId: string, value: string) => {
    setAnswers((current) => ({ ...current, [questionId]: value }));
  };

  const toggleQuestionOption = (question: MarsSession["interview_questions"][number], option: string) => {
    setAnswers((current) => {
      const currentValue = current[question.id] || "";
      if (!isMultiQuestion(question)) {
        return { ...current, [question.id]: option };
      }
      const values = splitAnswer(currentValue);
      const nextValues = values.includes(option) ? values.filter((item) => item !== option) : [...values, option];
      return { ...current, [question.id]: joinAnswer(nextValues) };
    });
  };

  const answerPreview = (questionId: string): string => {
    const answer = (answers[questionId] || "").trim();
    if (!answer) return localize(lang, "Нет ответа", "No answer");
    return answer.length > 96 ? `${answer.slice(0, 96)}...` : answer;
  };

  const moveQuestion = (direction: -1 | 1) => {
    if (!activeQuestion || activeQuestionIndex < 0) return;
    const nextIndex = Math.min(interviewQuestions.length - 1, Math.max(0, activeQuestionIndex + direction));
    setActiveQuestionId(interviewQuestions[nextIndex]?.id || activeQuestion.id);
  };

  const jumpToFirstUnanswered = () => {
    const nextQuestion = interviewQuestions.find((question) => !(answers[question.id] || "").trim());
    if (nextQuestion) setActiveQuestionId(nextQuestion.id);
  };

  const stepItems = [
    { label: localize(lang, "Рабочая папка", "Workspace"), done: Boolean(selectedWorkspace) },
    { label: localize(lang, "Задача", "Task"), done: Boolean(taskBrief.trim()) },
    { label: localize(lang, "Уточнения", "Interview"), done: interviewReady },
    { label: localize(lang, "План", "Plan"), done: Boolean(session?.generated_plan) },
    { label: localize(lang, "Цель", "Goal"), done: session?.status === "approved" || session?.status === "running" || session?.status === "completed" },
    { label: localize(lang, "Запуск", "Run"), done: Boolean(latestRunId) },
  ];

  return (
    <PageShell width="full" className="space-y-5">
      <PageHero
        kicker={localize(lang, "Запуск задачи", "Task run")}
        title="MARS"
        description={localize(
          lang,
          "Опишите результат, уточните требования и запустите работу в изолированной рабочей папке.",
          "Describe the outcome, confirm requirements, and run the job in an isolated workspace.",
        )}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge
              label={session ? session.status.replaceAll("_", " ") : localize(lang, "Новая сессия", "New session")}
              tone={session ? statusTone(session.status) : "neutral"}
            />
            <StatusBadge
              label={localize(lang, `${answeredQuestionCount}/${interviewQuestions.length || 8} ответов`, `${answeredQuestionCount}/${interviewQuestions.length || 8} answers`)}
              tone={interviewReady ? "success" : "info"}
            />
          </div>
        }
      />

      {firstError ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/8 px-4 py-3 text-sm text-destructive">
          {mutationMessage(firstError)}
        </div>
      ) : null}

      <div className="grid gap-3 rounded-xl border border-border bg-card/70 p-3 sm:grid-cols-3 lg:grid-cols-6">
        {stepItems.map((item, index) => (
          <div
            key={item.label}
            className={cn(
              "flex min-h-16 items-center gap-3 rounded-lg border px-3 py-2",
              item.done ? "border-primary/25 bg-primary/10" : "border-border bg-background/70",
            )}
          >
            <div
              className={cn(
                "flex h-7 w-7 shrink-0 items-center justify-center rounded-md text-xs font-semibold",
                item.done ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground",
              )}
            >
              {item.done ? <Check className="h-4 w-4" /> : index + 1}
            </div>
            <div className="min-w-0">
              <div className="truncate text-sm font-medium text-foreground">{item.label}</div>
              <div className="text-xs text-muted-foreground">{item.done ? localize(lang, "готово", "done") : localize(lang, "ожидает", "pending")}</div>
            </div>
          </div>
        ))}
      </div>

      <PageGrid sidebar className="xl:grid-cols-[minmax(0,1fr)_360px]">
        <div className="space-y-5">
          <SectionCard
            title={localize(lang, "Задача", "Task")}
            description={localize(lang, "Коротко опишите нужный результат.", "Briefly describe the outcome you need.")}
            icon={<Target className="h-4 w-4" />}
            actions={
              <Button onClick={() => createSession.mutate()} disabled={!canStartInterview}>
                {createSession.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Sparkles className="h-4 w-4" />}
                {localize(lang, "Сформировать вопросы", "Create questions")}
              </Button>
            }
          >
            <Textarea
              value={taskBrief}
              onChange={(event) => setTaskBrief(event.target.value)}
              rows={4}
              className="resize-none bg-background text-sm"
              placeholder={localize(lang, "Например: собрать страницу мониторинга серверов.", "Example: build a server monitoring page.")}
            />
          </SectionCard>

          {session ? (
            <SectionCard
              title={localize(lang, "Уточнения", "Requirements")}
              description={localize(
                lang,
                `Ответьте минимум на ${minimumAnswers} вопросов, чтобы собрать понятный план.`,
                `Answer at least ${minimumAnswers} questions to build a useful plan.`,
              )}
              icon={<ClipboardList className="h-4 w-4" />}
              actions={
                <div className="flex min-w-[220px] items-center gap-3">
                  <Progress value={interviewProgress} className="h-2" />
                  <StatusBadge label={`${answeredQuestionCount}/${interviewQuestions.length}`} tone={interviewReady ? "success" : "info"} />
                </div>
              }
            >
              {activeQuestion ? (
                <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
                  <div className="rounded-xl border border-border bg-background/70 p-4">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                      <div className="flex items-center gap-2">
                        <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-primary text-sm font-semibold text-primary-foreground">
                          {activeQuestionIndex + 1}
                        </span>
                        <div>
                          <div className="text-xs font-semibold uppercase tracking-wide text-primary">
                            {localize(lang, `Вопрос ${activeQuestionIndex + 1} из ${interviewQuestions.length}`, `Question ${activeQuestionIndex + 1} of ${interviewQuestions.length}`)}
                          </div>
                          <div className="text-xs text-muted-foreground">
                            {isMultiQuestion(activeQuestion)
                              ? localize(lang, "Можно выбрать несколько вариантов", "Pick multiple options")
                              : localize(lang, "Выберите один вариант или напишите свой", "Pick one option or write your own")}
                          </div>
                        </div>
                      </div>
                      <StatusBadge
                        label={(answers[activeQuestion.id] || "").trim() ? localize(lang, "ответ есть", "answered") : localize(lang, "нужен ответ", "needs answer")}
                        tone={(answers[activeQuestion.id] || "").trim() ? "success" : "info"}
                      />
                    </div>

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
                              onClick={() => toggleQuestionOption(activeQuestion, option)}
                              className={cn(
                                "flex min-h-12 items-center gap-3 rounded-lg border px-3 py-2 text-left text-sm transition-colors",
                                selected
                                  ? "border-primary/50 bg-primary/15 text-foreground shadow-sm"
                                  : "border-border bg-card text-muted-foreground hover:bg-secondary/60 hover:text-foreground",
                              )}
                            >
                              <span
                                className={cn(
                                  "flex h-5 w-5 shrink-0 items-center justify-center rounded-md border",
                                  selected ? "border-primary bg-primary text-primary-foreground" : "border-border text-muted-foreground",
                                )}
                              >
                                {selected ? <Check className="h-3.5 w-3.5" /> : <CircleDot className="h-3.5 w-3.5" />}
                              </span>
                              <span className="min-w-0 [overflow-wrap:anywhere]">{option}</span>
                            </button>
                          );
                        })}
                      </div>
                    ) : null}

                    <div className="mt-4 rounded-lg border border-border bg-card p-3">
                      <div className="mb-2 flex items-center justify-between gap-3">
                        <div className="text-xs font-semibold text-muted-foreground">
                          {localize(lang, "Свой ответ или детали", "Custom answer or details")}
                        </div>
                        <StatusBadge label={localize(lang, "только для этого вопроса", "current question")} tone="neutral" />
                      </div>
                      <Textarea
                        value={answers[activeQuestion.id] || ""}
                        onChange={(event) => setQuestionAnswer(activeQuestion.id, event.target.value)}
                        rows={3}
                        className="min-h-20 resize-none bg-background text-sm"
                        placeholder={activeQuestion.placeholder || localize(lang, "Можно выбрать вариант выше или написать свой ответ.", "Select an option above or write a custom answer.")}
                      />
                    </div>

                    <div className="mt-4 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
                      <div className="text-sm text-muted-foreground">
                        {interviewReady
                          ? localize(lang, "Ответов достаточно, можно собирать план.", "Enough answers; you can build the plan.")
                          : localize(lang, `До плана осталось ${Math.max(0, minimumAnswers - answeredQuestionCount)} ответов.`, `${Math.max(0, minimumAnswers - answeredQuestionCount)} more answers before the plan.`)}
                      </div>
                      <div className="flex flex-wrap gap-2">
                        <Button variant="outline" onClick={() => moveQuestion(-1)} disabled={activeQuestionIndex <= 0}>
                          <ChevronLeft className="h-4 w-4" />
                          {localize(lang, "Назад", "Back")}
                        </Button>
                        <Button
                          variant="secondary"
                          onClick={() => moveQuestion(1)}
                          disabled={activeQuestionIndex >= interviewQuestions.length - 1}
                        >
                          {localize(lang, "Дальше", "Next")}
                          <ChevronRight className="h-4 w-4" />
                        </Button>
                      </div>
                    </div>
                  </div>

                  <aside className="space-y-3">
                    <div className="rounded-xl border border-border bg-background/70 p-3">
                      <div className="mb-2 flex items-center justify-between gap-2">
                        <div className="text-sm font-semibold text-foreground">{localize(lang, "Карта вопросов", "Question map")}</div>
                        <StatusBadge label={`${answeredQuestionCount}/${interviewQuestions.length}`} tone={interviewReady ? "success" : "info"} />
                      </div>
                      <Progress value={interviewProgress} className="h-2" />
                      <Button
                        type="button"
                        variant="ghost"
                        size="sm"
                        className="mt-2 w-full justify-start"
                        onClick={jumpToFirstUnanswered}
                        disabled={answeredQuestionCount === interviewQuestions.length}
                      >
                        <CircleDot className="h-4 w-4" />
                        {localize(lang, "Перейти к пустому", "Go to unanswered")}
                      </Button>
                    </div>

                    <div className="max-h-[440px] space-y-2 overflow-y-auto pr-1">
                      {interviewQuestions.map((question, index) => {
                        const answered = Boolean((answers[question.id] || "").trim());
                        const active = question.id === activeQuestion.id;
                        return (
                          <button
                            key={question.id}
                            type="button"
                            onClick={() => setActiveQuestionId(question.id)}
                            className={cn(
                              "w-full rounded-lg border px-3 py-2 text-left transition-colors",
                              active
                                ? "border-primary/50 bg-primary/12"
                                : "border-border bg-background hover:bg-secondary/50",
                            )}
                          >
                            <div className="flex items-start gap-2">
                              <span
                                className={cn(
                                  "mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-md text-[11px] font-semibold",
                                  answered ? "bg-primary text-primary-foreground" : "bg-secondary text-muted-foreground",
                                )}
                              >
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
              ) : null}

              <div className="mt-5 flex flex-col gap-3 rounded-lg border border-border bg-secondary/10 p-3 sm:flex-row sm:items-center sm:justify-between">
                <div className="text-sm text-muted-foreground">
                  {interviewReady
                    ? localize(lang, "Данных достаточно для плана.", "Enough details for the plan.")
                    : localize(lang, `Нужно еще ответов: ${Math.max(0, minimumAnswers - answeredQuestionCount)}.`, `More answers needed: ${Math.max(0, minimumAnswers - answeredQuestionCount)}.`)}
                </div>
                <Button variant="secondary" onClick={() => answerSession.mutate()} disabled={!canSaveAnswers}>
                  {answerSession.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  {localize(lang, "Собрать план", "Build plan")}
                </Button>
              </div>
            </SectionCard>
          ) : null}

          <SectionCard
            title={localize(lang, "Цель и план", "Goal and plan")}
            description={localize(lang, "Проверьте цель и шаги перед запуском.", "Review the goal and steps before running.")}
            icon={<ShieldCheck className="h-4 w-4" />}
            actions={
              <Button onClick={() => approvePlan.mutate()} disabled={!canApprovePlan}>
                {approvePlan.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                {localize(lang, "Подтвердить план", "Approve plan")}
              </Button>
            }
          >
            {goalText ? (
              <div className="mb-4 rounded-lg border border-primary/25 bg-primary/10 px-4 py-3">
                <div className="mb-1 flex items-center gap-2 text-xs font-semibold text-primary">
                  <Rocket className="h-3.5 w-3.5" />
                  {localize(lang, "Цель", "Goal")}
                </div>
                <div className="text-sm leading-6 text-foreground">{goalText}</div>
              </div>
            ) : null}
            <Textarea
              value={planDraft}
              onChange={(event) => setPlanDraft(event.target.value)}
              rows={13}
              className="min-h-72 resize-none bg-background font-mono text-xs leading-5"
              placeholder={localize(lang, "План появится после ответов.", "Plan appears after answers.")}
            />
          </SectionCard>
        </div>

        <div className="space-y-5 xl:sticky xl:top-5 xl:self-start">
          <SectionCard title={localize(lang, "Рабочая папка", "Workspace")} icon={<FolderGit2 className="h-4 w-4" />}>
            <QueryStateBlock loading={workspacesQuery.isLoading} error={workspacesQuery.error}>
              <div className="flex items-center justify-between gap-3 rounded-lg border border-border bg-background px-3 py-3">
                <div className="min-w-0">
                  <div className="text-xs text-muted-foreground">{localize(lang, "Изолированная папка", "Personal workspace")}</div>
                  <div className="truncate text-sm font-semibold text-foreground">{selectedWorkspace?.name || localize(lang, "Создается...", "Creating...")}</div>
                </div>
                <StatusBadge label={selectedWorkspace?.enabled ? localize(lang, "изолирована", "isolated") : localize(lang, "недоступна", "disabled")} tone={selectedWorkspace?.enabled ? "success" : "warning"} />
              </div>
            </QueryStateBlock>
          </SectionCard>

          <SectionCard title={localize(lang, "Skills", "Skills")} icon={<BrainCircuit className="h-4 w-4" />}>
            <div className="grid gap-2">
              {SKILL_OPTIONS.map((skill) => (
                <label
                  key={skill.slug}
                  className="flex min-h-11 cursor-pointer items-center gap-3 rounded-lg border border-border bg-background px-3 py-2 text-sm transition-colors hover:bg-secondary/50"
                >
                  <Checkbox checked={selectedSkills.includes(skill.slug)} onCheckedChange={(checked) => setSkill(skill.slug, checked === true)} />
                  <span className="min-w-0 flex-1">
                    <span className="block truncate font-medium text-foreground">{skill.label}</span>
                    <span className="block truncate text-xs text-muted-foreground">{skill.tags}</span>
                  </span>
                </label>
              ))}
            </div>
          </SectionCard>

          <SectionCard title={localize(lang, "Запуск", "Run")} icon={<Play className="h-4 w-4" />}>
            <div className="space-y-4">
              <div className="space-y-2">
                {stepItems.map((item) => (
                  <div key={item.label} className="flex items-center justify-between rounded-lg bg-secondary/20 px-3 py-2 text-sm">
                    <span className="text-muted-foreground">{item.label}</span>
                    <StatusBadge label={item.done ? localize(lang, "готово", "done") : localize(lang, "ожидает", "pending")} tone={item.done ? "success" : "neutral"} />
                  </div>
                ))}
              </div>

              <label className="flex items-center gap-2 rounded-lg border border-border bg-background px-3 py-2 text-sm">
                <Checkbox checked={allowDirty} onCheckedChange={(checked) => setAllowDirty(checked === true)} />
                <span>{localize(lang, "Разрешить dirty worktree", "Allow dirty worktree")}</span>
              </label>

              <div className="space-y-2">
                <Label>{localize(lang, "Verification command", "Verification command")}</Label>
                <Input
                  value={testCommand}
                  onChange={(event) => setTestCommand(event.target.value)}
                  placeholder="npm run build"
                  className="font-mono text-xs"
                />
              </div>

              <div className="grid gap-2">
                <Button onClick={() => runSession.mutate()} disabled={!canRun}>
                  {runSession.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Play className="h-4 w-4" />}
                  {localize(lang, "Запустить выполнение", "Run")}
                </Button>
                <Button variant="outline" onClick={() => stopRun.mutate()} disabled={!canStop}>
                  {stopRun.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Square className="h-4 w-4" />}
                  {localize(lang, "Остановить", "Stop")}
                </Button>
                {latestRunId ? (
                  <Button variant="ghost" onClick={() => navigate(`/mars/runs/${latestRunId}`)}>
                    {localize(lang, "Открыть run", "Open run")}
                  </Button>
                ) : null}
              </div>
            </div>
          </SectionCard>
        </div>
      </PageGrid>
    </PageShell>
  );
}
