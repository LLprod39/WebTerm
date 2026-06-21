import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AlertTriangle, CheckCircle2, Circle } from "lucide-react";

import { StudioNav } from "@/components/StudioNav";
import { Badge } from "@/components/ui/badge";
import { buildDraftCanvasModel } from "@/components/studio/draftGraphModel";
import {
  canReviseDraft,
  getDraftResponse,
  type DraftFilter,
} from "@/components/studio/draftQueueModel";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import {
  studioPipelineDrafts,
  type StudioPipelineAssistantPayload,
} from "@/lib/studioPipelineDraftsApi";

import { StudioDraftComposerPanel } from "./studio-drafts/StudioDraftComposerPanel";
import { StudioDraftGraphPanel } from "./studio-drafts/StudioDraftGraphPanel";
import { StudioDraftQueuePanel } from "./studio-drafts/StudioDraftQueuePanel";
import { StudioDraftReviewPanel } from "./studio-drafts/StudioDraftReviewPanel";
import { StudioDraftsHeader } from "./studio-drafts/StudioDraftsHeader";
import { StudioDraftsMobileTabs } from "./studio-drafts/StudioDraftsMobileTabs";
import {
  buildAssistantPayload,
  buildDraftQuestionAnswerMessage,
  getDefaultDraftName,
  getDraftFilterCounts,
  getPromptPresets,
  getVisibleDrafts,
  type StudioDraftMobilePane,
} from "./studio-drafts/studioDraftsModel";

type StudioDraftInspectorTab = "request" | "check" | "changes";

function DraftProgressStrip({
  lang,
  hasDraft,
  hasPrompt,
  hasOpenQuestions,
  validationOk,
  validationFailed,
  ready,
  applied,
}: {
  lang: string;
  hasDraft: boolean;
  hasPrompt: boolean;
  hasOpenQuestions: boolean;
  validationOk: boolean;
  validationFailed: boolean;
  ready: boolean;
  applied: boolean;
}) {
  const steps = [
    {
      label: localize(lang, "Черновик", "Draft"),
      done: hasDraft,
      active: !hasDraft && hasPrompt,
      blocked: false,
    },
    {
      label: localize(lang, "Проверка", "Validated"),
      done: validationOk,
      active: hasDraft && !validationOk && !validationFailed,
      blocked: hasOpenQuestions || validationFailed,
    },
    {
      label: localize(lang, "Готово", "Ready"),
      done: ready,
      active: validationOk && !ready,
      blocked: validationFailed,
    },
    {
      label: localize(lang, "Применён", "Applied"),
      done: applied,
      active: false,
      blocked: false,
    },
  ];

  return (
    <div className="border-b border-border/70 bg-card/35 px-4 py-2">
      <div className="flex min-w-0 flex-wrap items-center gap-2">
        {steps.map((step, index) => {
          const Icon = step.blocked ? AlertTriangle : step.done ? CheckCircle2 : Circle;
          return (
            <div key={step.label} className="flex min-w-0 items-center gap-2">
              {index > 0 ? <span className="hidden h-px w-5 bg-border sm:block" /> : null}
              <Badge
                variant={step.done ? "secondary" : "outline"}
                className={cn(
                  "h-7 gap-1.5 rounded-full px-2.5 text-xs",
                  step.blocked ? "border-amber-500/30 bg-amber-500/10 text-amber-100" : "",
                  step.active ? "border-primary/30 bg-primary/10 text-primary" : "",
                )}
              >
                <Icon className="h-3.5 w-3.5" />
                {step.label}
              </Badge>
            </div>
          );
        })}
      </div>
    </div>
  );
}

export default function StudioDraftsPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [searchParams, setSearchParams] = useSearchParams();
  const { toast } = useToast();
  const { lang } = useI18n();
  const [filter, setFilter] = useState<DraftFilter>("active");
  const [search, setSearch] = useState("");
  const [prompt, setPrompt] = useState("");
  const [draftName, setDraftName] = useState(() => getDefaultDraftName(lang));
  const [selectedSkeletonSlug, setSelectedSkeletonSlug] = useState("");
  const [questionAnswers, setQuestionAnswers] = useState<Record<number, string>>({});
  const [mobilePane, setMobilePane] = useState<StudioDraftMobilePane>("queue");
  const [queueCollapsed, setQueueCollapsed] = useState(false);
  const [inspectorTab, setInspectorTab] = useState<StudioDraftInspectorTab>("request");

  const defaultDraftName = useMemo(() => getDefaultDraftName(lang), [lang]);
  const promptPresets = useMemo(() => getPromptPresets(lang), [lang]);
  const activeDraftId = Number(searchParams.get("draft") || 0) || null;

  const { data: draftSessions = [], isLoading: draftsLoading } = useQuery({
    queryKey: ["studio", "pipeline-drafts"],
    queryFn: studioPipelineDrafts.list,
    staleTime: 30_000,
  });

  const draftFromList = useMemo(
    () => draftSessions.find((session) => session.id === activeDraftId) || null,
    [activeDraftId, draftSessions],
  );

  const { data: activeDraft = draftFromList, isFetching: activeDraftFetching } = useQuery({
    queryKey: ["studio", "pipeline-draft", activeDraftId],
    queryFn: () => studioPipelineDrafts.get(activeDraftId as number),
    enabled: Boolean(activeDraftId),
    initialData: draftFromList || undefined,
  });

  const activeResponse = getDraftResponse(activeDraft);
  const openQuestions = useMemo(() => (activeResponse?.questions || []).filter(Boolean), [activeResponse]);
  const openQuestionsKey = useMemo(() => openQuestions.join("\n"), [openQuestions]);
  const hasOpenQuestions = Boolean(openQuestions.length);
  const activeTemplateRecommendations = useMemo(() => activeResponse?.template_recommendations || [], [activeResponse]);
  const activeModel = useMemo(() => buildDraftCanvasModel(activeDraft), [activeDraft]);
  const activeStats = activeModel.stats;
  const activeGraphCounts = useMemo(
    () => ({ nodes: activeModel.nodes.length, edges: activeModel.edges.length }),
    [activeModel.nodes.length, activeModel.edges.length],
  );
  const activeCanApply =
    Boolean(activeDraft && (activeStats?.hasChanges || activeGraphCounts.nodes > 0 || activeGraphCounts.edges > 0)) &&
    activeResponse?.validation?.ok !== false &&
    activeResponse?.risk?.level !== "dangerous";
  const activeCanValidate = Boolean(activeDraft?.id && activeDraft.status !== "applied" && activeDraft.status !== "discarded");
  const activeCanSwitchTemplate = Boolean(
    activeDraft?.id &&
      activeTemplateRecommendations.length &&
      activeDraft.status !== "applied" &&
      activeDraft.status !== "discarded",
  );
  const submitWillRevise = canReviseDraft(activeDraft);
  const validationFailed = activeResponse?.validation?.ok === false || activeResponse?.risk?.level === "dangerous";
  const validationOk = Boolean(activeResponse && activeResponse.validation?.ok !== false && !hasOpenQuestions && activeResponse.risk?.level !== "dangerous");
  const draftApplied = activeDraft?.status === "applied";

  const filterCounts = useMemo(() => getDraftFilterCounts(draftSessions), [draftSessions]);
  const visibleDrafts = useMemo(
    () => getVisibleDrafts({ draftSessions, filter, search }),
    [draftSessions, filter, search],
  );

  useEffect(() => {
    if (!activeDraft) return;
    setDraftName(activeDraft.title || defaultDraftName);
    setPrompt(hasOpenQuestions ? "" : activeDraft.user_goal || "");
  }, [activeDraft, defaultDraftName, hasOpenQuestions]);

  useEffect(() => {
    setQuestionAnswers({});
  }, [activeDraft?.id, openQuestionsKey]);

  useEffect(() => {
    if (activeDraftId) return;
    const promptParam = searchParams.get("prompt") || "";
    const titleParam = searchParams.get("title") || "";
    if (promptParam) setPrompt(promptParam);
    if (titleParam) setDraftName(titleParam);
  }, [activeDraftId, searchParams]);

  useEffect(() => {
    const preferred = activeResponse?.selected_template?.slug || activeTemplateRecommendations[0]?.slug || "";
    setSelectedSkeletonSlug(preferred);
  }, [activeDraft?.id, activeResponse?.selected_template?.slug, activeTemplateRecommendations]);

  useEffect(() => {
    if (hasOpenQuestions) {
      setInspectorTab("request");
      setMobilePane("compose");
      return;
    }
    if (activeResponse) {
      setInspectorTab("check");
      setMobilePane((current) => (current === "compose" ? "review" : current));
    }
  }, [activeDraft?.id, activeResponse, hasOpenQuestions]);

  const setActiveDraft = (id: number | null) => {
    const next = new URLSearchParams(searchParams);
    if (id) {
      next.set("draft", String(id));
    } else {
      next.delete("draft");
    }
    setSearchParams(next, { replace: true });
  };

  const createOrReviseMutation = useMutation({
    mutationFn: ({ message, compilerMode }: { message: string; compilerMode?: StudioPipelineAssistantPayload["compiler_mode"] }) => {
      const payload = buildAssistantPayload({
        title: draftName,
        message,
        previousResponse: activeResponse,
        compilerMode,
      });
      return submitWillRevise && activeDraft?.id
        ? studioPipelineDrafts.revise(activeDraft.id, payload)
        : studioPipelineDrafts.create(payload);
    },
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipeline-drafts"] });
      queryClient.setQueryData(["studio", "pipeline-draft", session.id], session);
      setActiveDraft(session.id);
      toast({
        description: getDraftResponse(session)?.validation?.ok === false
          ? localize(lang, "Черновик требует правки перед применением.", "Draft needs fixes before apply.")
          : localize(lang, "Граф черновика обновлен.", "Draft graph updated."),
      });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const applyMutation = useMutation({
    mutationFn: async ({ openEditor }: { openEditor: boolean }) => {
      if (!activeDraft?.id) {
        throw new Error(localize(lang, "Выберите черновик для применения.", "Select a draft to apply."));
      }
      const applied = await studioPipelineDrafts.apply(activeDraft.id, {
        create_new: true,
        name: draftName.trim() || defaultDraftName,
        description: prompt.trim() || activeResponse?.reply || "",
        icon: "W",
        tags: ["ai-builder"],
      });
      return { pipeline: applied.pipeline, session: applied.draft, openEditor };
    },
    onSuccess: ({ pipeline, session, openEditor }) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      queryClient.invalidateQueries({ queryKey: ["studio", "pipeline-drafts"] });
      queryClient.setQueryData(["studio", "pipeline-draft", session.id], session);
      if (openEditor) {
        navigate(`/studio/pipeline/${pipeline.id}`);
        return;
      }
      toast({ description: localize(lang, `Пайплайн "${pipeline.name}" создан.`, `Pipeline "${pipeline.name}" created.`) });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const validateMutation = useMutation({
    mutationFn: async () => {
      if (!activeDraft?.id) {
        throw new Error(localize(lang, "Выберите черновик для проверки.", "Select a draft to validate."));
      }
      return studioPipelineDrafts.validate(activeDraft.id);
    },
    onSuccess: ({ draft, validation, dry_run }) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipeline-drafts"] });
      queryClient.setQueryData(["studio", "pipeline-draft", draft.id], draft);
      toast({
        description: validation.ok
          ? localize(lang, "Dry-run validate прошел без запуска actions.", "Dry-run validate passed without executing actions.")
          : localize(lang, "Dry-run validate нашел ошибки графа.", "Dry-run validate found graph errors."),
      });
      if (!dry_run.executed) {
        queryClient.invalidateQueries({ queryKey: ["studio", "pipeline-draft", draft.id] });
      }
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const useTemplateMutation = useMutation({
    mutationFn: async () => {
      if (!activeDraft?.id) {
        throw new Error(localize(lang, "Выберите черновик для смены шаблона.", "Select a draft before changing template."));
      }
      if (!selectedSkeletonSlug) {
        throw new Error(localize(lang, "Выберите пилотный шаблон.", "Select a pilot template."));
      }
      return studioPipelineDrafts.useTemplate(activeDraft.id, selectedSkeletonSlug);
    },
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipeline-drafts"] });
      queryClient.setQueryData(["studio", "pipeline-draft", session.id], session);
      toast({ description: localize(lang, "Черновик пересобран по шаблону.", "Template draft rebuilt.") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const discardMutation = useMutation({
    mutationFn: (draftId: number) => studioPipelineDrafts.discard(draftId),
    onSuccess: (session) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipeline-drafts"] });
      queryClient.setQueryData(["studio", "pipeline-draft", session.id], session);
      if (activeDraftId === session.id) {
        setActiveDraft(null);
        setPrompt("");
        setDraftName(defaultDraftName);
      }
      toast({ description: localize(lang, "Черновик отброшен.", "Draft discarded.") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  function handleNewDraft() {
    setActiveDraft(null);
    setPrompt("");
    setQuestionAnswers({});
    setDraftName(defaultDraftName);
  }

  const questionAnswerMessage = useMemo(
    () => buildDraftQuestionAnswerMessage({ hasOpenQuestions, openQuestions, prompt, questionAnswers }),
    [hasOpenQuestions, openQuestions, prompt, questionAnswers],
  );

  const canSubmitComposer = hasOpenQuestions ? Boolean(questionAnswerMessage) : Boolean(prompt.trim());

  function handleSubmit(messageOverride?: string, compilerMode?: StudioPipelineAssistantPayload["compiler_mode"]) {
    const message = (messageOverride || questionAnswerMessage || prompt).trim();
    if (!message) {
      toast({ variant: "destructive", description: localize(lang, "Опишите задачу для пайплайна.", "Describe the pipeline task.") });
      return;
    }
    createOrReviseMutation.mutate({ message, compilerMode });
  }

  function handleApply(openEditor: boolean) {
    if (!activeCanApply) {
      toast({
        variant: "destructive",
        description: localize(lang, "Черновик нельзя применить: проверьте ошибки и риски.", "Draft cannot be applied: check errors and risk."),
      });
      return;
    }
    applyMutation.mutate({ openEditor });
  }

  return (
    <div className="flex h-full flex-col">
      <StudioNav />
      <div className="flex min-h-0 flex-1 flex-col bg-background">
        <StudioDraftsHeader
          lang={lang}
          activeDraft={activeDraft || null}
          activeResponse={activeResponse}
          nodeCount={activeModel.nodes.length}
          edgeCount={activeModel.edges.length}
          onOverview={() => navigate("/studio")}
        />
        <DraftProgressStrip
          lang={lang}
          hasDraft={Boolean(activeDraft)}
          hasPrompt={Boolean(prompt.trim())}
          hasOpenQuestions={hasOpenQuestions}
          validationOk={validationOk}
          validationFailed={validationFailed}
          ready={activeCanApply}
          applied={draftApplied}
        />
        <StudioDraftsMobileTabs lang={lang} mobilePane={mobilePane} onMobilePaneChange={setMobilePane} />

        <div
          className={cn(
            "grid min-h-0 flex-1 grid-cols-1",
            queueCollapsed ? "xl:grid-cols-[56px_minmax(420px,1fr)_360px]" : "xl:grid-cols-[280px_minmax(420px,1fr)_360px]",
          )}
        >
          <StudioDraftQueuePanel
            lang={lang}
            mobilePane={mobilePane}
            collapsed={queueCollapsed}
            draftSessions={draftSessions}
            draftsLoading={draftsLoading}
            search={search}
            filter={filter}
            filterCounts={filterCounts}
            visibleDrafts={visibleDrafts}
            activeDraftId={activeDraftId}
            discardingDraftId={discardMutation.isPending ? discardMutation.variables ?? null : null}
            onSearchChange={setSearch}
            onFilterChange={setFilter}
            onNewDraft={handleNewDraft}
            onCollapsedChange={setQueueCollapsed}
            onSelectDraft={setActiveDraft}
            onDiscardDraft={(draftId) => discardMutation.mutate(draftId)}
          />
          <StudioDraftGraphPanel
            lang={lang}
            mobilePane={mobilePane}
            activeDraft={activeDraft || null}
            loading={activeDraftFetching && !draftFromList}
          />
          <aside
            className={cn(
              "min-h-[520px] min-w-0 flex-col overflow-hidden bg-card/35 xl:flex xl:min-h-0 xl:border-l xl:border-border/70",
              mobilePane === "compose" || mobilePane === "review" ? "flex" : "hidden",
            )}
          >
            <div className="border-b border-border/70 bg-card px-3 py-2">
              <div className="grid grid-cols-3 gap-1 rounded-lg bg-background/60 p-1">
                {[
                  { value: "request" as const, label: localize(lang, "Запрос", "Request") },
                  { value: "check" as const, label: localize(lang, "Проверка", "Check") },
                  { value: "changes" as const, label: localize(lang, "Изменения", "Changes") },
                ].map((item) => (
                  <button
                    key={item.value}
                    type="button"
                    className={cn(
                      "h-8 rounded-md px-2 text-xs font-medium transition-colors",
                      inspectorTab === item.value
                        ? "bg-card text-foreground shadow-sm"
                        : "text-muted-foreground hover:bg-card/60 hover:text-foreground",
                    )}
                    aria-pressed={inspectorTab === item.value}
                    onClick={() => {
                      setInspectorTab(item.value);
                      setMobilePane(item.value === "request" ? "compose" : "review");
                    }}
                  >
                    {item.label}
                  </button>
                ))}
              </div>
            </div>

            {inspectorTab === "request" ? (
              <StudioDraftComposerPanel
                lang={lang}
                mobilePane={mobilePane}
                activeDraft={activeDraft || null}
                activeResponse={activeResponse}
                hasOpenQuestions={hasOpenQuestions}
                openQuestions={openQuestions}
                questionAnswers={questionAnswers}
                prompt={prompt}
                draftName={draftName}
                promptPresets={promptPresets}
                submitWillRevise={submitWillRevise}
                createPending={createOrReviseMutation.isPending}
                canSubmitComposer={canSubmitComposer}
                onNewDraft={handleNewDraft}
                onQuestionAnswersChange={setQuestionAnswers}
                onPromptChange={setPrompt}
                onDraftNameChange={setDraftName}
                onSubmit={handleSubmit}
              />
            ) : (
              <StudioDraftReviewPanel
                lang={lang}
                mobilePane={mobilePane}
                mode={inspectorTab}
                activeResponse={activeResponse}
                activeGraphCounts={activeGraphCounts}
                hasOpenQuestions={hasOpenQuestions}
                activeCanApply={activeCanApply}
                applyPending={applyMutation.isPending}
                activeCanValidate={activeCanValidate}
                validatePending={validateMutation.isPending}
                useTemplatePending={useTemplateMutation.isPending}
                activeCanSwitchTemplate={activeCanSwitchTemplate}
                selectedSkeletonSlug={selectedSkeletonSlug}
                activeTemplateRecommendations={activeTemplateRecommendations}
                onApply={handleApply}
                onValidate={() => validateMutation.mutate()}
                onUseTemplate={() => useTemplateMutation.mutate()}
                onSelectedSkeletonSlugChange={setSelectedSkeletonSlug}
              />
            )}
          </aside>
        </div>
      </div>
    </div>
  );
}
