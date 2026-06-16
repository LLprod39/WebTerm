import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { CheckCircle2, ClipboardList, FileText, Rocket, Target } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { PageShell, StatusBadge } from "@/components/ui/page-shell";
import { marsApi, type MarsInterviewQuestion, type MarsProject, type MarsSession } from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import {
  MarsBriefStep,
  MarsInterviewStep,
  MarsPlanStep,
  MarsRunStep,
} from "./mars/MarsPageSteps";
import { MarsOrchestratorRail, MarsPageLayout, MarsProjectRail, MarsWizardNav } from "./mars/MarsPageSidebar";
import {
  isMultiQuestion,
  joinAnswer,
  mutationMessage,
  splitAnswer,
  statusTone,
  type WizardStepId,
  type WizardStepMeta,
} from "./mars/MarsPageUtils";

export default function MarsPage() {
  const { lang } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  const [selectedWorkspaceId, setSelectedWorkspaceId] = useState("");
  const [projectSearch, setProjectSearch] = useState("");
  const [taskBrief, setTaskBrief] = useState("");
  const [session, setSession] = useState<MarsSession | null>(null);
  const [answers, setAnswers] = useState<Record<string, string>>({});
  const [planDraft, setPlanDraft] = useState("");
  const [testCommand, setTestCommand] = useState("");
  const [latestRunId, setLatestRunId] = useState<number | null>(null);
  const [activeQuestionId, setActiveQuestionId] = useState("");
  const [activeStep, setActiveStep] = useState<WizardStepId>("brief");

  const workspacesQuery = useQuery({
    queryKey: ["mars", "workspaces"],
    queryFn: marsApi.listWorkspaces,
    retry: false,
  });

  const projectsQuery = useQuery({
    queryKey: ["mars", "projects"],
    queryFn: () => marsApi.listProjects(50),
    retry: false,
  });

  const workspacesData = workspacesQuery.data?.workspaces;
  const workspaces = useMemo(() => workspacesData ?? [], [workspacesData]);
  const projectsData = projectsQuery.data?.projects;
  const projects = useMemo(() => {
    const source = projectsData ?? [];
    const query = projectSearch.trim().toLowerCase();
    if (!query) return source;
    return source.filter((project) => {
      const haystack = [
        project.session.task_brief,
        project.session.status,
        project.latest_run?.status,
      ]
        .filter(Boolean)
        .join(" ")
        .toLowerCase();
      return haystack.includes(query);
    });
  }, [projectSearch, projectsData]);
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
      }),
    onSuccess: ({ session: nextSession }) => {
      setSession(nextSession);
      setAnswers(nextSession.answers || {});
      setPlanDraft(nextSession.generated_plan || "");
      setActiveQuestionId(nextSession.interview_questions[0]?.id || "");
      setActiveStep("interview");
      void queryClient.invalidateQueries({ queryKey: ["mars", "projects"] });
    },
  });

  const answerSession = useMutation({
    mutationFn: () => marsApi.answerSession(Number(session?.id), { answers }),
    onSuccess: ({ session: nextSession }) => {
      setSession(nextSession);
      setPlanDraft(nextSession.generated_plan || "");
      setActiveStep("plan");
      void queryClient.invalidateQueries({ queryKey: ["mars", "projects"] });
    },
  });

  const approvePlan = useMutation({
    mutationFn: () =>
      marsApi.approveSessionPlan(Number(session?.id), {
        generated_plan: planDraft,
      }),
    onSuccess: ({ session: nextSession }) => {
      setSession(nextSession);
      setPlanDraft(nextSession.generated_plan || planDraft);
      setActiveStep("run");
      void queryClient.invalidateQueries({ queryKey: ["mars", "projects"] });
    },
  });

  const runSession = useMutation({
    mutationFn: () => marsApi.runSession(Number(session?.id), { allow_dirty: false, test_command: testCommand }),
    onSuccess: ({ run }) => {
      setLatestRunId(run.id);
      void queryClient.invalidateQueries({ queryKey: ["mars", "projects"] });
      navigate(`/mars/runs/${run.id}`);
    },
  });

  const firstError = [
    createSession.error,
    answerSession.error,
    approvePlan.error,
    runSession.error,
  ].find(Boolean);

  const sessionInterviewQuestions = session?.interview_questions;
  const interviewQuestions = useMemo(() => sessionInterviewQuestions ?? [], [sessionInterviewQuestions]);
  const activeQuestion = interviewQuestions.find((question) => question.id === activeQuestionId) ?? interviewQuestions[0] ?? null;
  const activeQuestionIndex = activeQuestion ? interviewQuestions.findIndex((question) => question.id === activeQuestion.id) : -1;
  const answeredQuestionCount = interviewQuestions.filter((question) => (answers[question.id] || "").trim()).length;
  const requiredQuestionCount = interviewQuestions.filter((question) => question.required).length;
  const answeredRequiredCount = interviewQuestions.filter((question) => question.required && (answers[question.id] || "").trim()).length;
  const minimumAnswers = Math.min(5, Math.max(1, requiredQuestionCount || interviewQuestions.length));
  const interviewReady = Boolean(session && answeredQuestionCount >= minimumAnswers);
  const interviewProgress = interviewQuestions.length ? Math.round((answeredQuestionCount / interviewQuestions.length) * 100) : 0;
  const totalProgress = Math.round(
    ([
      Boolean(selectedWorkspace && taskBrief.trim()),
      Boolean(session),
      interviewReady,
      Boolean(planDraft.trim()),
      session?.status === "approved" || Boolean(latestRunId),
    ].filter(Boolean).length /
      5) *
      100,
  );
  const goalText = (answers.success_criteria || session?.task_brief || taskBrief || "").trim();
  const projectTitle = (session?.task_brief || taskBrief || localize(lang, "Новый проект", "New project")).trim();
  const shortProjectTitle = projectTitle.length > 22 ? `${projectTitle.slice(0, 22).trim()}...` : projectTitle;
  const projectId = latestRunId ? `RUN-${String(latestRunId).padStart(3, "0")}` : session ? `MARS-${String(session.id).padStart(3, "0")}` : "MARS-NEW";

  const canStartInterview = Boolean(selectedWorkspace && taskBrief.trim()) && !createSession.isPending;
  const canSaveAnswers = interviewReady && !answerSession.isPending;
  const canApprovePlan = Boolean(session && planDraft.trim()) && !approvePlan.isPending;
  const canRun = Boolean(session?.status === "approved") && !runSession.isPending;

  const wizardSteps: WizardStepMeta[] = useMemo(
    () => [
      {
        id: "brief",
        label: localize(lang, "Идея", "Idea"),
        title: localize(lang, "Что создать", "What to build"),
        description: localize(lang, "Скрипт, бот, сайт, утилита или проект.", "Script, bot, site, tool, or project."),
        done: Boolean(session),
        available: true,
        icon: Target,
      },
      {
        id: "interview",
        label: localize(lang, "Уточнения", "Clarify"),
        title: localize(lang, "ИИ должен понять детали", "AI understands details"),
        description: localize(lang, "Ответьте по шагам, чтобы убрать догадки.", "Answer step by step to remove guesswork."),
        done: interviewReady,
        available: Boolean(session),
        icon: ClipboardList,
      },
      {
        id: "plan",
        label: localize(lang, "ТЗ", "Spec"),
        title: localize(lang, "Проверь, как ИИ понял", "Review AI understanding"),
        description: localize(lang, "Можно поправить ТЗ до создания.", "Edit the spec before building."),
        done: session?.status === "approved",
        available: Boolean(session && planDraft.trim()),
        icon: FileText,
      },
      {
        id: "run",
        label: localize(lang, "Создание", "Build"),
        title: localize(lang, "ИИ пишет и проверяет", "AI builds and checks"),
        description: localize(lang, "MARS меняет код, запускает проверки и показывает ход.", "MARS changes code, runs checks, and shows progress."),
        done: Boolean(latestRunId),
        available: session?.status === "approved" || Boolean(latestRunId),
        icon: Rocket,
      },
      {
        id: "final",
        label: localize(lang, "Рабочий проект", "Ready project"),
        title: localize(lang, "Готово к запуску", "Ready to launch"),
        description: localize(lang, "Итоговый отчет и ссылка на результат.", "Final report and result link."),
        done: latestRun?.status === "completed",
        available: Boolean(latestRunId),
        icon: CheckCircle2,
      },
    ],
    [interviewReady, lang, latestRun?.status, latestRunId, planDraft, session],
  );

  useEffect(() => {
    const currentStep = wizardSteps.find((step) => step.id === activeStep);
    if (currentStep && !currentStep.available) {
      setActiveStep("brief");
    }
  }, [activeStep, wizardSteps]);

  useEffect(() => {
    if (!interviewQuestions.length) {
      setActiveQuestionId("");
      return;
    }
    if (!interviewQuestions.some((question) => question.id === activeQuestionId)) {
      setActiveQuestionId(interviewQuestions[0].id);
    }
  }, [activeQuestionId, interviewQuestions]);

  const toggleQuestionOption = (question: MarsInterviewQuestion, option: string) => {
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

  const moveQuestion = (direction: -1 | 1) => {
    if (!activeQuestion || activeQuestionIndex < 0) return;
    const nextIndex = Math.min(interviewQuestions.length - 1, Math.max(0, activeQuestionIndex + direction));
    setActiveQuestionId(interviewQuestions[nextIndex]?.id || activeQuestion.id);
  };

  const jumpToFirstUnanswered = () => {
    const nextQuestion = interviewQuestions.find((question) => !(answers[question.id] || "").trim());
    if (nextQuestion) setActiveQuestionId(nextQuestion.id);
  };

  const resetProject = () => {
    setTaskBrief("");
    setSession(null);
    setAnswers({});
    setPlanDraft("");
    setTestCommand("");
    setLatestRunId(null);
    setActiveQuestionId("");
    setActiveStep("brief");
  };

  const selectProject = (project: MarsProject) => {
    const nextSession = project.session;
    setSession(nextSession);
    setTaskBrief(nextSession.task_brief);
    setAnswers(nextSession.answers || {});
    setPlanDraft(nextSession.generated_plan || "");
    setLatestRunId(project.latest_run?.id ?? null);
    setActiveQuestionId(nextSession.interview_questions[0]?.id || "");
    if (project.latest_run || nextSession.status === "running" || nextSession.status === "completed" || nextSession.status === "approved") {
      setActiveStep("run");
    } else if (nextSession.generated_plan) {
      setActiveStep("plan");
    } else if (nextSession.interview_questions.length) {
      setActiveStep("interview");
    } else {
      setActiveStep("brief");
    }
  };

  const renderActiveStep = () => {
    if (activeStep === "interview") {
      return (
        <MarsInterviewStep
          lang={lang}
          questions={interviewQuestions}
          activeQuestion={activeQuestion}
          activeQuestionIndex={activeQuestionIndex}
          answers={answers}
          answeredQuestionCount={answeredQuestionCount}
          requiredQuestionCount={requiredQuestionCount}
          answeredRequiredCount={answeredRequiredCount}
          minimumAnswers={minimumAnswers}
          interviewReady={interviewReady}
          interviewProgress={interviewProgress}
          canSaveAnswers={canSaveAnswers}
          pending={answerSession.isPending}
          onAnswerChange={(questionId, value) => setAnswers((current) => ({ ...current, [questionId]: value }))}
          onToggleOption={toggleQuestionOption}
          onMoveQuestion={moveQuestion}
          onJumpToFirstUnanswered={jumpToFirstUnanswered}
          onSelectQuestion={setActiveQuestionId}
          onBuildPlan={() => answerSession.mutate()}
        />
      );
    }
    if (activeStep === "plan") {
      return (
        <MarsPlanStep
          lang={lang}
          goalText={goalText}
          planDraft={planDraft}
          canApprovePlan={canApprovePlan}
          pending={approvePlan.isPending}
          onPlanChange={setPlanDraft}
          onApprovePlan={() => approvePlan.mutate()}
        />
      );
    }
    if (activeStep === "run" || activeStep === "final") {
      return (
        <MarsRunStep
          lang={lang}
          latestRun={latestRun}
          latestRunId={latestRunId}
          sessionStatus={session?.status}
          testCommand={testCommand}
          canRun={canRun}
          runPending={runSession.isPending}
          onTestCommandChange={setTestCommand}
          onRun={() => runSession.mutate()}
          onOpenRun={(runId) => navigate(`/mars/runs/${runId}`)}
        />
      );
    }
    return (
        <MarsBriefStep
          lang={lang}
          taskBrief={taskBrief}
          canStartInterview={canStartInterview}
          pending={createSession.isPending}
        onTaskBriefChange={setTaskBrief}
        onCreateQuestions={() => createSession.mutate()}
      />
    );
  };

  return (
    <PageShell
      width="full"
      className="-mx-4 -my-5 min-h-[calc(100vh-2rem)] space-y-5 bg-[radial-gradient(circle_at_18%_9%,rgba(20,184,166,0.13),transparent_27%),linear-gradient(180deg,#0a0f14_0%,#0b1117_100%)] px-4 py-5 md:-mx-6 md:px-6 xl:-mx-8 xl:px-8"
    >
      <section className="px-0 py-2">
        <div className="flex flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
          <div className="min-w-0">
            <div className="text-[11px] font-bold uppercase tracking-[0.22em] text-emerald-300">MARS</div>
            <h1 className="mt-2 text-2xl font-semibold tracking-tight text-slate-100">
              {localize(lang, "Project Command Center", "Project Command Center")}
            </h1>
            <p className="mt-2 max-w-3xl text-sm leading-6 text-slate-400">
              {localize(
                lang,
                "Создавайте scripts, проекты и automation через guided brief, пошаговую сборку, проверку и отчет.",
                "Create scripts, projects, and automation through a guided brief, step-by-step build, verification, and report.",
              )}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge
              label={localize(lang, `Проект: ${shortProjectTitle}`, `Project: ${shortProjectTitle}`)}
              tone="neutral"
              className="h-9 px-3"
            />
            <StatusBadge label={`ID: ${projectId}`} tone="neutral" dot={false} className="h-9 px-3" />
            <StatusBadge
              label={session ? session.status.replaceAll("_", " ") : localize(lang, "Готов к работе", "Ready")}
              tone={session ? statusTone(session.status) : "success"}
              className="h-9 px-3"
            />
          </div>
        </div>
      </section>

      {firstError ? (
        <div className="rounded-lg border border-destructive/30 bg-destructive/8 px-4 py-3 text-sm text-destructive">
          {mutationMessage(firstError)}
        </div>
      ) : null}

      <MarsPageLayout
        projectHistory={
          <MarsProjectRail
            lang={lang}
            projects={projects}
            loading={projectsQuery.isLoading}
            error={projectsQuery.error}
            search={projectSearch}
            selectedSessionId={session?.id ?? null}
            onSearchChange={setProjectSearch}
            onNewProject={resetProject}
            onSelectProject={selectProject}
            onOpenRun={(runId) => navigate(`/mars/runs/${runId}`)}
          />
        }
        statusRail={
          <MarsOrchestratorRail
            lang={lang}
            latestRun={latestRun}
            totalProgress={totalProgress}
          />
        }
      >
        <MarsWizardNav activeStep={activeStep} steps={wizardSteps} onStepChange={setActiveStep} />
        {renderActiveStep()}
      </MarsPageLayout>
    </PageShell>
  );
}
