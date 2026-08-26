import { useEffect, useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ClipboardList, FileText, Rocket, Target } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { PageHero, PageShell, StatusBadge } from "@/components/ui/page-shell";
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
  statusLabel,
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
  const [verificationProfile, setVerificationProfile] = useState("none");
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
    mutationFn: () =>
      marsApi.runSession(Number(session?.id), {
        allow_dirty: false,
        verification_profile: verificationProfile,
      }),
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

  const canStartInterview = Boolean(selectedWorkspace && taskBrief.trim()) && !createSession.isPending;
  const canSaveAnswers = interviewReady && !answerSession.isPending;
  const canApprovePlan = Boolean(session && planDraft.trim()) && !approvePlan.isPending;
  const canRun = Boolean(session?.status === "approved") && !runSession.isPending;
  const showStatusRail = Boolean(
    latestRunId ||
      latestRun ||
      runSession.isPending ||
      session?.status === "running" ||
      session?.status === "completed",
  );

  const wizardSteps: WizardStepMeta[] = useMemo(
    () => [
      {
        id: "brief",
        label: localize(lang, "Задача", "Task"),
        title: localize(lang, "Опишите задачу", "Describe the task"),
        description: localize(lang, "Укажите результат и ограничения.", "State the result and constraints."),
        done: Boolean(session),
        available: true,
        icon: Target,
      },
      {
        id: "interview",
        label: localize(lang, "Уточнения", "Clarify"),
        title: localize(lang, "Уточните детали", "Clarify the details"),
        description: localize(lang, "Ответьте на несколько вопросов.", "Answer a few questions."),
        done: interviewReady,
        available: Boolean(session),
        icon: ClipboardList,
      },
      {
        id: "plan",
        label: localize(lang, "План", "Plan"),
        title: localize(lang, "Проверьте план", "Review the plan"),
        description: localize(lang, "Можно поправить план до выполнения.", "Edit the plan before running."),
        done: session?.status === "approved",
        available: Boolean(session && planDraft.trim()),
        icon: FileText,
      },
      {
        id: "run",
        label: localize(lang, "Выполнение", "Run"),
        title: localize(lang, "Запустите работу", "Start the work"),
        description: localize(lang, "MARS внесёт изменения и выполнит проверки.", "MARS will make changes and run checks."),
        done: Boolean(latestRunId),
        available: session?.status === "approved" || Boolean(latestRunId),
        icon: Rocket,
      },
    ],
    [interviewReady, lang, latestRunId, planDraft, session],
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
    if (activeStep === "run") {
      return (
        <MarsRunStep
          lang={lang}
          latestRun={latestRun}
          latestRunId={latestRunId}
          sessionStatus={session?.status}
          verificationProfile={verificationProfile}
          canRun={canRun}
          runPending={runSession.isPending}
          onVerificationProfileChange={setVerificationProfile}
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
    <PageShell width="full" className="space-y-5">
      <PageHero
        kicker="MARS"
        title={localize(lang, "Разработка с MARS", "Build with MARS")}
        description={localize(
          lang,
          "Опишите задачу, согласуйте план и запустите работу.",
          "Describe the task, review the plan, and start the work.",
        )}
        actions={
          <div className="flex flex-wrap items-center gap-2">
            <StatusBadge
              label={shortProjectTitle}
              tone="neutral"
              className="h-9 px-3"
            />
            <StatusBadge
              label={session ? statusLabel(session.status, lang) : localize(lang, "Готов к работе", "Ready")}
              tone={session ? statusTone(session.status) : "success"}
              className="h-9 px-3"
            />
          </div>
        }
      />

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
          showStatusRail ? (
            <MarsOrchestratorRail
              lang={lang}
              latestRun={latestRun}
              totalProgress={totalProgress}
            />
          ) : undefined
        }
      >
        <MarsWizardNav activeStep={activeStep} steps={wizardSteps} onStepChange={setActiveStep} />
        {renderActiveStep()}
      </MarsPageLayout>
    </PageShell>
  );
}
