import { useEffect, useMemo, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertTriangle,
  CheckCircle2,
  Filter,
  GitBranch,
  HelpCircle,
  Loader2,
  Plus,
  RefreshCw,
  Route,
  Search,
  Send,
  ShieldCheck,
  Sparkles,
  Wand2,
  XCircle,
} from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { StudioNav } from "@/components/StudioNav";
import { DraftFilterButton, DraftListItem, DraftStatusBadge } from "@/components/studio/DraftQueue";
import { DraftGraphCanvas } from "@/components/studio/DraftGraphCanvas";
import { buildDraftCanvasModel } from "@/components/studio/draftGraphModel";
import {
  canReviseDraft,
  DRAFT_FILTERS,
  getDraftResponse,
  matchesDraftFilter,
  type DraftFilter,
} from "@/components/studio/draftQueueModel";
import { PipelineDraftReview } from "@/components/studio/PipelineDraftReview";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import {
  studioPipelineDrafts,
  type StudioPipelineAssistantPayload,
  type StudioPipelineAssistantResponse,
} from "@/lib/studioPipelineDraftsApi";

function buildAssistantPayload({
  title,
  message,
  previousResponse,
  compilerMode,
}: {
  title: string;
  message: string;
  previousResponse: StudioPipelineAssistantResponse | null;
  compilerMode?: StudioPipelineAssistantPayload["compiler_mode"];
}): StudioPipelineAssistantPayload {
  return {
    pipeline_id: null,
    pipeline_name: title.trim() || "Operations runbook",
    nodes: [],
    edges: [],
    selected_node: null,
    user_message: message,
    intent: "create",
    compiler_mode: compilerMode,
    draft_mode: true,
    last_validation_errors: previousResponse?.validation?.errors || [],
    history: previousResponse
      ? [
          {
            role: "assistant",
            content: [previousResponse.reply, previousResponse.patch_summary, ...(previousResponse.validation?.errors || [])]
              .filter(Boolean)
              .join("\n"),
          },
        ]
      : [],
  };
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
  const [draftName, setDraftName] = useState(() => localize(lang, "Операционный сценарий", "Operations runbook"));
  const [selectedSkeletonSlug, setSelectedSkeletonSlug] = useState("");
  const [questionAnswers, setQuestionAnswers] = useState<Record<number, string>>({});
  const [mobilePane, setMobilePane] = useState<"queue" | "graph" | "compose" | "review">("queue");

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

  const filterCounts = useMemo(
    () =>
      DRAFT_FILTERS.reduce<Record<DraftFilter, number>>((acc, item) => {
        acc[item.value] = draftSessions.filter((session) => matchesDraftFilter(session, item.value)).length;
        return acc;
      }, { active: 0, ready: 0, needs_fix: 0, applied: 0 }),
    [draftSessions],
  );

  const visibleDrafts = useMemo(() => {
    const q = search.trim().toLowerCase();
    return draftSessions
      .filter((session) => matchesDraftFilter(session, filter))
      .filter((session) => {
        if (!q) return true;
        return `${session.title} ${session.user_goal} ${getDraftResponse(session)?.patch_summary || ""}`.toLowerCase().includes(q);
      })
      .slice(0, 30);
  }, [draftSessions, filter, search]);

  useEffect(() => {
    if (!activeDraft) return;
    setDraftName(activeDraft.title || localize(lang, "Операционный сценарий", "Operations runbook"));
    setPrompt(hasOpenQuestions ? "" : activeDraft.user_goal || "");
  }, [activeDraft, hasOpenQuestions, lang]);

  useEffect(() => {
    setQuestionAnswers({});
  }, [activeDraft?.id, openQuestions.join("\n")]);

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
        name: draftName.trim() || localize(lang, "Операционный сценарий", "Operations runbook"),
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
        setDraftName(localize(lang, "Операционный сценарий", "Operations runbook"));
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
    setDraftName(localize(lang, "Операционный сценарий", "Operations runbook"));
  }

  const questionAnswerMessage = useMemo(() => {
    if (!hasOpenQuestions) return prompt.trim();
    const answers = openQuestions
      .map((question, index) => {
        const answer = (questionAnswers[index] || "").trim();
        if (!answer) return "";
        return `Q${index + 1}: ${question}\nA${index + 1}: ${answer}`;
      })
      .filter(Boolean)
      .join("\n\n");
    const extra = prompt.trim();
    return [answers, extra ? `Additional context:\n${extra}` : ""].filter(Boolean).join("\n\n").trim();
  }, [hasOpenQuestions, openQuestions, prompt, questionAnswers]);

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
      toast({ variant: "destructive", description: localize(lang, "Черновик нельзя применить: проверьте ошибки и риски.", "Draft cannot be applied: check errors and risk.") });
      return;
    }
    applyMutation.mutate({ openEditor });
  }

  const promptPresets = [
    localize(lang, "Ежедневная проверка серверов с отчетом в Telegram и ручным резервным сценарием", "Daily server health check with Telegram report and manual fallback"),
    localize(lang, "Оповещение Docker: диагностика, подтверждение и безопасное восстановление", "Monitoring alert for Docker: diagnose, approve, safe remediation"),
    localize(lang, "Webhook для задач оператора: принять payload, запустить агента, отправить сводку", "Operator webhook: receive payload, run agent, send summary"),
  ];
  const mobilePanes = [
    { value: "queue", label: localize(lang, "Очередь", "Queue") },
    { value: "graph", label: localize(lang, "Граф", "Graph") },
    { value: "compose", label: localize(lang, "Запрос", "Request") },
    { value: "review", label: localize(lang, "Проверка", "Review") },
  ] as const;

  return (
    <div className="flex h-full flex-col">
      <StudioNav />
      <div className="flex min-h-0 flex-1 flex-col bg-background">
        <div className="flex min-h-14 items-center justify-between gap-3 border-b border-border/70 bg-card/60 px-4">
          <div className="flex min-w-0 items-center gap-3">
            <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10">
              <Wand2 className="h-4 w-4 text-primary" />
            </div>
            <div className="min-w-0">
              <h1 className="truncate text-sm font-semibold text-foreground">
                {localize(lang, "Черновики пайплайнов", "Pipeline drafts")}
              </h1>
              <p className="truncate text-[11px] text-muted-foreground">
                {localize(lang, "Сборка пайплайна по описанию", "Draft pipelines from an operations request")}
              </p>
            </div>
            <DraftStatusBadge session={activeDraft || null} lang={lang} />
          </div>

          <div className="hidden shrink-0 items-center gap-2 md:flex">
            <Badge variant="outline" className="gap-1 border-border/70 bg-background/40 text-muted-foreground">
              <GitBranch className="h-3 w-3" />
              {activeModel.nodes.length} / {activeModel.edges.length}
            </Badge>
            {activeResponse?.risk?.level === "dangerous" ? (
              <Badge variant="outline" className="gap-1 border-red-500/25 bg-red-500/10 text-red-300">
                <AlertTriangle className="h-3 w-3" />
                {localize(lang, "Опасно", "Dangerous")}
              </Badge>
            ) : null}
            <Button type="button" variant="outline" size="sm" className="h-9 gap-1.5" onClick={() => navigate("/studio")}>
              {localize(lang, "Обзор", "Overview")}
            </Button>
          </div>
        </div>

        <div className="grid grid-cols-4 gap-1 border-b border-border/70 bg-card/35 p-2 xl:hidden">
          {mobilePanes.map((item) => (
            <Button
              key={item.value}
              type="button"
              variant={mobilePane === item.value ? "secondary" : "ghost"}
              size="sm"
              className="h-9 min-w-0 px-2 text-xs"
              aria-pressed={mobilePane === item.value}
              onClick={() => setMobilePane(item.value)}
            >
              <span className="truncate">{item.label}</span>
            </Button>
          ))}
        </div>

        <div className="grid min-h-0 flex-1 grid-cols-1 xl:grid-cols-[300px_minmax(420px,1fr)_390px]">
          <aside className={cn("min-h-[320px] min-w-0 flex-col border-b border-border/70 bg-card/35 p-4 xl:flex xl:min-h-0 xl:border-b-0 xl:border-r", mobilePane === "queue" ? "flex" : "hidden")}>
            <div className="flex items-center justify-between gap-3">
              <div>
                <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                  <Filter className="h-3.5 w-3.5" />
                  {localize(lang, "Очередь черновиков", "Draft queue")}
                </div>
                <div className="mt-1 text-[11px] text-muted-foreground/80">{localize(lang, `${draftSessions.length} всего`, `${draftSessions.length} total`)}</div>
              </div>
              <Button type="button" size="sm" className="h-9 gap-1.5" onClick={handleNewDraft}>
                <Plus className="h-3.5 w-3.5" />
                {localize(lang, "Новый", "New")}
              </Button>
            </div>

            <div className="mt-3 flex items-center gap-2 rounded-lg border border-border/70 bg-background/45 px-3">
              <Search className="h-3.5 w-3.5 shrink-0 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder={localize(lang, "Поиск черновиков...", "Search drafts...")}
                aria-label={localize(lang, "Поиск черновиков", "Search drafts")}
                className="h-9 border-0 bg-transparent px-0 text-xs shadow-none focus-visible:ring-0"
              />
            </div>

            <div className="mt-3 grid grid-cols-2 gap-2">
              {DRAFT_FILTERS.map((item) => (
                <DraftFilterButton
                  key={item.value}
                  value={item.value}
                  active={filter === item.value}
                  label={localize(lang, item.labelRu, item.labelEn)}
                  count={filterCounts[item.value]}
                  onClick={() => setFilter(item.value)}
                />
              ))}
            </div>

            <ScrollArea className="mt-3 min-h-0 flex-1 pr-3">
              <div className="flex flex-col gap-2">
                {draftsLoading ? (
                  <div className="flex items-center gap-2 rounded-lg border border-border/70 bg-card/70 px-3 py-3 text-xs text-muted-foreground">
                    <Loader2 className="h-3.5 w-3.5 animate-spin" />
                    {localize(lang, "Загружаю черновики...", "Loading drafts...")}
                  </div>
                ) : visibleDrafts.length ? (
                  visibleDrafts.map((session) => (
                    <DraftListItem
                      key={session.id}
                      session={session}
                      active={activeDraftId === session.id}
                      lang={lang}
                      onSelect={() => setActiveDraft(session.id)}
                      discarding={discardMutation.isPending && discardMutation.variables === session.id}
                      onDiscard={() => discardMutation.mutate(session.id)}
                    />
                  ))
                ) : (
                  <div className="rounded-lg border border-dashed border-border/80 bg-card/50 px-3 py-5 text-xs leading-5 text-muted-foreground">
                    {localize(lang, "Нет черновиков в выбранном фильтре.", "No drafts in this filter.")}
                  </div>
                )}
              </div>
            </ScrollArea>
          </aside>

          <main className={cn("min-h-[520px] min-w-0 border-b border-border/70 xl:block xl:min-h-0 xl:border-b-0", mobilePane === "graph" ? "block" : "hidden")}>
            <DraftGraphCanvas session={activeDraft || null} lang={lang} loading={activeDraftFetching && !draftFromList} />
          </main>

          <aside className={cn("min-h-[520px] min-w-0 flex-col overflow-hidden bg-card/35 xl:flex xl:min-h-0 xl:border-l xl:border-border/70", mobilePane === "compose" || mobilePane === "review" ? "flex" : "hidden")}>
            <div className={cn("border-b border-border/70 p-4 xl:block", mobilePane === "review" ? "hidden" : "block")}>
              <div className="flex items-center justify-between gap-3">
                <div className="min-w-0">
                  <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    <Sparkles className="h-3.5 w-3.5" />
                    {localize(lang, "Описание задачи", "Request")}
                  </div>
                  <div className="mt-1 text-[11px] text-muted-foreground/80">
                    {hasOpenQuestions
                      ? localize(lang, "Ответьте на вопросы черновика", "Answer draft questions")
                      : submitWillRevise
                        ? localize(lang, "Уточнение активного черновика", "Revising active draft")
                        : localize(lang, "Создание нового черновика", "Creating new draft")}
                  </div>
                </div>
                {activeDraft ? (
                  <Button type="button" variant="ghost" size="sm" className="h-8 gap-1.5" onClick={handleNewDraft}>
                    <XCircle className="h-3.5 w-3.5" />
                    {localize(lang, "Очистить", "Clear")}
                  </Button>
                ) : null}
              </div>

              <div className="mt-3 grid gap-3">
                <label className="grid gap-1.5">
                  <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    {localize(lang, "Название пайплайна", "Pipeline name")}
                  </span>
                  <Input
                    value={draftName}
                    onChange={(event) => setDraftName(event.target.value)}
                    className="h-10 min-w-0 bg-background/70"
                    aria-label={localize(lang, "Название черновика пайплайна", "Draft pipeline name")}
                  />
                </label>
                {hasOpenQuestions ? (
                  <div className="rounded-lg border border-sky-500/25 bg-sky-500/10 p-3">
                    <div className="flex min-w-0 items-center justify-between gap-3">
                      <div className="flex min-w-0 items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-sky-100">
                        <HelpCircle className="h-3.5 w-3.5 shrink-0" />
                        <span className="truncate">{localize(lang, "Не хватает деталей", "Missing details")}</span>
                      </div>
                      <Badge variant="outline" className="shrink-0 border-sky-400/25 bg-sky-400/10 text-[10px] text-sky-100">
                        {Object.values(questionAnswers).filter((value) => value.trim()).length}/{openQuestions.length}
                      </Badge>
                    </div>
                    <div className="mt-3 grid gap-2">
                      {openQuestions.map((question, index) => (
                        <label key={`${question}-${index}`} className="grid min-w-0 gap-2 rounded-md border border-sky-400/20 bg-background/55 p-2.5">
                          <span className="flex min-w-0 gap-2 text-xs font-medium leading-5 text-sky-50">
                            <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-sky-300/25 bg-sky-300/10 text-[10px]">
                              {index + 1}
                            </span>
                            <span className="min-w-0 [overflow-wrap:anywhere]">{question}</span>
                          </span>
                          <Textarea
                            value={questionAnswers[index] || ""}
                            onChange={(event) => setQuestionAnswers((current) => ({ ...current, [index]: event.target.value }))}
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
                  <span className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                    {hasOpenQuestions
                      ? localize(lang, "Доп. сведения", "Extra details")
                      : localize(lang, "Задача для пайплайна", "Pipeline task")}
                  </span>
                  <Textarea
                    value={prompt}
                    onChange={(event) => setPrompt(event.target.value)}
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
                      disabled={createOrReviseMutation.isPending}
                      onClick={() => {
                        setPrompt(preset);
                        handleSubmit(preset);
                      }}
                    >
                      {preset}
                    </Button>
                  ))}
                </div>
              ) : null}

              <div className="mt-3 grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
                <Button
                  type="button"
                  className="h-10 gap-2"
                  disabled={createOrReviseMutation.isPending || !canSubmitComposer}
                  onClick={() => handleSubmit()}
                >
                  {createOrReviseMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
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
                    disabled={createOrReviseMutation.isPending || !prompt.trim()}
                    onClick={() => handleSubmit(undefined, "deterministic")}
                  >
                    {createOrReviseMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <GitBranch className="h-4 w-4" />}
                    {localize(lang, "Быстрый шаблон", "Quick template")}
                  </Button>
                ) : null}
                {activeResponse?.validation?.ok === false && !hasOpenQuestions ? (
                  <Button
                    type="button"
                    variant="outline"
                    className="h-10 gap-2"
                    disabled={createOrReviseMutation.isPending}
                    onClick={() =>
                      handleSubmit(
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

            <ScrollArea className={cn("min-h-0 flex-1 p-4 xl:block", mobilePane === "compose" ? "hidden" : "block")}>
              {activeResponse ? (
                <PipelineDraftReview
                  response={activeResponse}
                  lang={lang}
                  graphCounts={activeGraphCounts}
                  hideQuestions={hasOpenQuestions}
                  actions={
                    <div className="grid grid-cols-1 gap-2 sm:grid-cols-2 xl:grid-cols-1">
                      <Button className="h-10 gap-1.5" disabled={!activeCanApply || applyMutation.isPending} onClick={() => handleApply(false)}>
                        {applyMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                        {localize(lang, "Создать пайплайн", "Create pipeline")}
                      </Button>
                      <Button variant="outline" className="h-10 gap-1.5" disabled={!activeCanApply || applyMutation.isPending} onClick={() => handleApply(true)}>
                        <Route className="h-3.5 w-3.5" />
                        {localize(lang, "Открыть редактор", "Open editor")}
                      </Button>
                      <Button
                        variant="outline"
                        className="h-10 gap-1.5"
                        disabled={!activeCanValidate || validateMutation.isPending || applyMutation.isPending || useTemplateMutation.isPending}
                        onClick={() => validateMutation.mutate()}
                      >
                        {validateMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <ShieldCheck className="h-3.5 w-3.5" />}
                        {localize(lang, "Проверить dry-run", "Validate dry-run")}
                      </Button>
                      {activeTemplateRecommendations.length ? (
                        <div className="rounded-lg border border-border/70 bg-background/45 p-3">
                          <div className="mb-2 flex items-center justify-between gap-2">
                            <div className="min-w-0">
                              <div className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                                {localize(lang, "Пилотный шаблон", "Pilot template")}
                              </div>
                              <div className="mt-0.5 truncate text-[11px] text-muted-foreground/80">
                                {activeResponse?.selected_template?.name || localize(lang, "Рекомендованный шаблон", "Recommended template")}
                              </div>
                            </div>
                            {activeResponse?.selected_template?.slug ? (
                              <Badge variant="outline" className="shrink-0 border-primary/25 bg-primary/10 text-[10px] text-primary">
                                {activeResponse.selected_template.slug}
                              </Badge>
                            ) : null}
                          </div>
                          <div className="grid gap-2">
                            <Select value={selectedSkeletonSlug} onValueChange={setSelectedSkeletonSlug} disabled={!activeCanSwitchTemplate || useTemplateMutation.isPending}>
                              <SelectTrigger className="h-9 bg-card/70 text-xs" aria-label={localize(lang, "Пилотный шаблон", "Pilot template")}>
                                <SelectValue placeholder={localize(lang, "Выберите шаблон", "Select template")} />
                              </SelectTrigger>
                              <SelectContent>
                                {activeTemplateRecommendations.map((item) => (
                                  <SelectItem key={item.slug} value={item.slug}>
                                    {item.name || item.slug}
                                  </SelectItem>
                                ))}
                              </SelectContent>
                            </Select>
                            <Button
                              type="button"
                              variant="outline"
                              className="h-9 gap-1.5"
                              disabled={!activeCanSwitchTemplate || !selectedSkeletonSlug || useTemplateMutation.isPending || applyMutation.isPending}
                              onClick={() => useTemplateMutation.mutate()}
                            >
                              {useTemplateMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <GitBranch className="h-3.5 w-3.5" />}
                              {localize(lang, "Использовать шаблон", "Use template")}
                            </Button>
                          </div>
                        </div>
                      ) : null}
                    </div>
                  }
                />
              ) : (
                <div className="rounded-xl border border-dashed border-border/80 bg-background/45 p-5">
                  <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
                    <Wand2 className="h-5 w-5 text-primary" />
                  </div>
                  <h2 className="mt-4 text-sm font-semibold text-foreground">
                    {localize(lang, "Нет выбранного черновика", "No draft selected")}
                  </h2>
                  <p className="mt-2 text-xs leading-5 text-muted-foreground">
                    {localize(lang, "Создайте или выберите черновик, чтобы увидеть требования, ресурсы, риски и действия.", "Create or select a draft to inspect requirements, resources, risks, and actions.")}
                  </p>
                </div>
              )}
            </ScrollArea>
          </aside>
        </div>
      </div>
    </div>
  );
}
