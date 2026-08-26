import { useMemo, useState, type ElementType } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronRight,
  Plus,
  Search,
  Workflow,
  XCircle,
  Zap,
  BookOpen,
  Server,
  Bot,
  Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";
import {
  getActiveManualTriggerOptions,
  getActiveMonitoringTriggers,
  getActiveScheduleTriggers,
  getActiveWebhookTriggers,
  type TriggerInfoTarget,
} from "@/components/studio/StudioPipelineTriggers";
import {
  studioPipelines,
  studioMCP,
  studioRuns,
  studioSkills,
  studioAgents,
  fetchAuthSession,
  type PipelineListItem,
  type PipelineDetail,
} from "@/lib/api";
import { StudioNav } from "@/components/StudioNav";
import { hasFeatureAccess } from "@/lib/featureAccess";
import { EmptyState, QueryStateBlock } from "@/components/ui/page-shell";
import { getPipelineRuntimePlaceholders } from "./pipeline-editor/pipelineGraphUtils";
import { CreatePipelineDialog } from "./studio-page/CreatePipelineDialog";
import { PipelineCard } from "./studio-page/PipelineCard";
import {
  DeletePipelineDialog,
  ManualTriggerDialog,
  TriggerInfoDialog,
} from "./studio-page/StudioPipelineDialogs";

export default function StudioPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { lang } = useI18n();
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<PipelineListItem | null>(null);
  const [runTarget, setRunTarget] = useState<PipelineDetail | null>(null);
  const [runEntryNodeId, setRunEntryNodeId] = useState("");
  const [runTriggerError, setRunTriggerError] = useState("");
  const [preparingRunPipelineId, setPreparingRunPipelineId] = useState<number | null>(null);
  const [triggerInfoTarget, setTriggerInfoTarget] = useState<TriggerInfoTarget | null>(null);

  const { data: session } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });

  const user = session?.user ?? null;
  const canPipelines = hasFeatureAccess(user, "studio_pipelines");
  const canRuns = hasFeatureAccess(user, "studio_runs");
  const canAgents = hasFeatureAccess(user, "studio_agents");
  const canSkills = hasFeatureAccess(user, "studio_skills");
  const canMcp = hasFeatureAccess(user, "studio_mcp");
  const canNotifications = hasFeatureAccess(user, "studio_notifications");

  const { data: pipelines = [], isLoading } = useQuery({
    queryKey: ["studio", "pipelines", search],
    queryFn: () => studioPipelines.list(search || undefined),
    enabled: canPipelines,
  });

  const { data: mcpList = [] } = useQuery({
    queryKey: ["studio", "mcp"],
    queryFn: studioMCP.list,
    enabled: canMcp,
  });

  const { data: skills = [] } = useQuery({
    queryKey: ["studio", "skills"],
    queryFn: studioSkills.list,
    enabled: canSkills,
  });

  const { data: agents = [] } = useQuery({
    queryKey: ["studio", "agents"],
    queryFn: studioAgents.list,
    enabled: canAgents,
  });

  const { data: runs = [] } = useQuery({
    queryKey: ["studio", "runs"],
    queryFn: () => studioRuns.list(),
    enabled: canRuns,
  });

  const runTriggerOptions = useMemo(() => getActiveManualTriggerOptions(runTarget, lang), [lang, runTarget]);

  const sectionLinks = useMemo(
    () =>
      [
        canSkills
          ? { label: localize(lang, "Сценарии", "Runbooks"), desc: localize(lang, "Готовые действия для повторяемых задач", "Reusable actions for recurring tasks"), icon: BookOpen, path: "/studio/skills" }
          : null,
        canMcp
          ? { label: localize(lang, "Интеграции MCP", "MCP integrations"), desc: localize(lang, "Инструменты для автоматизации", "Tools for automation"), icon: Server, path: "/studio/mcp" }
          : null,
        canAgents
          ? { label: localize(lang, "Профили агентов", "Agent profiles"), desc: localize(lang, "Модели и инструменты для шагов пайплайна", "Models and tools for pipeline steps"), icon: Bot, path: "/studio/agents" }
          : null,
        canRuns
          ? { label: localize(lang, "История запусков", "Run history"), desc: localize(lang, "Доступные вам запуски", "Runs available to you"), icon: Clock, path: "/studio/runs" }
          : null,
        canNotifications
          ? { label: localize(lang, "Оповещения", "Notifications"), desc: localize(lang, "Каналы для предупреждений и отчётов", "Channels for alerts and reports"), icon: Zap, path: "/studio/notifications" }
          : null,
      ].filter(Boolean) as Array<{ label: string; desc: string; icon: typeof BookOpen; path: string }>,
    [canAgents, canMcp, canNotifications, canRuns, canSkills, lang],
  );

  const stats = useMemo(
    () =>
      [
        canPipelines ? { icon: Workflow, label: localize(lang, "Пайплайны", "Pipelines"), value: pipelines.length } : null,
        canSkills ? { icon: BookOpen, label: localize(lang, "Сценарии", "Runbooks"), value: Array.isArray(skills) ? skills.length : 0 } : null,
        canMcp ? { icon: Server, label: localize(lang, "MCP", "MCP servers"), value: Array.isArray(mcpList) ? mcpList.length : 0 } : null,
        canAgents ? { icon: Bot, label: localize(lang, "Профили", "Profiles"), value: Array.isArray(agents) ? agents.length : 0 } : null,
        canRuns ? { icon: CheckCircle2, label: localize(lang, "Завершено", "Completed"), value: runs.filter((run) => run.status === "completed").length, sub: localize(lang, "запусков", "runs") } : null,
        canRuns ? { icon: XCircle, label: localize(lang, "Ошибки", "Failed"), value: runs.filter((run) => run.status === "failed").length, sub: localize(lang, "запусков", "runs") } : null,
      ].filter(Boolean) as Array<{ icon: ElementType; label: string; value: string | number; sub?: string }>,
    [agents, canAgents, canMcp, canPipelines, canRuns, canSkills, lang, mcpList, pipelines.length, runs, skills],
  );

  const runMutation = useMutation({
    mutationFn: ({ pipelineId, entryNodeId }: { pipelineId: number; entryNodeId?: string }) =>
      studioPipelines.run(pipelineId, undefined, entryNodeId),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      queryClient.invalidateQueries({ queryKey: ["studio", "runs"] });
      setRunTarget(null);
      setRunEntryNodeId("");
      setRunTriggerError("");
      toast({ description: localize(lang, `Запуск #${run.id} начат.`, `Run #${run.id} started.`) });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const cloneMutation = useMutation({
    mutationFn: (pipelineId: number) => studioPipelines.clone(pipelineId),
    onSuccess: (pipeline) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      toast({ description: localize(lang, `Копия создана: "${pipeline.name}".`, `Cloned as "${pipeline.name}".`) });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (pipelineId: number) => studioPipelines.delete(pipelineId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      setDeleteTarget(null);
      toast({ description: localize(lang, "Пайплайн удален.", "Pipeline deleted.") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  async function handleRunPipeline(pipeline: PipelineListItem) {
    setRunTriggerError("");
    setPreparingRunPipelineId(pipeline.id);
    try {
      const detail = await studioPipelines.get(pipeline.id);
      const manualTriggers = getActiveManualTriggerOptions(detail, lang);
      const webhookTriggers = getActiveWebhookTriggers(detail);
      const scheduleTriggers = getActiveScheduleTriggers(detail);
      const monitoringTriggers = getActiveMonitoringTriggers(detail);
      if (manualTriggers.length === 0) {
        if (webhookTriggers.length > 0 || scheduleTriggers.length > 0 || monitoringTriggers.length > 0) {
          setTriggerInfoTarget({
            pipeline: detail,
            webhookTriggers,
            scheduleTriggers,
            monitoringTriggers,
          });
          return;
        }
        toast({
          variant: "destructive",
          description: localize(lang, "Добавьте ручной запуск, webhook, расписание или запуск по событию мониторинга.", "Add a manual trigger, webhook, schedule, or monitoring event trigger."),
        });
        return;
      }
      const runtimeContextFields = getPipelineRuntimePlaceholders(detail.nodes || []);
      if (runtimeContextFields.length > 0) {
        toast({
          description: localize(
            lang,
            `Заполните поля context перед запуском: ${runtimeContextFields.join(", ")}.`,
            `Fill context fields before running: ${runtimeContextFields.join(", ")}.`,
          ),
        });
        navigate(`/studio/pipeline/${pipeline.id}`, { state: { openRunDialog: true } });
        return;
      }
      if (manualTriggers.length === 1) {
        runMutation.mutate({ pipelineId: pipeline.id, entryNodeId: manualTriggers[0].nodeId });
        return;
      }
      setRunTarget(detail);
      setRunEntryNodeId(manualTriggers[0].nodeId);
    } catch (error) {
      const message = error instanceof Error ? error.message : localize(lang, "Не удалось подготовить запуск пайплайна.", "Failed to prepare pipeline run.");
      toast({ variant: "destructive", description: message });
    } finally {
      setPreparingRunPipelineId(null);
    }
  }

  const recentFailedRuns = canRuns ? runs.filter((run) => run.status === "failed").slice(0, 3) : [];

  return (
    <div className="flex h-full flex-col">
      <StudioNav />

      <div className="flex min-h-0 flex-1 flex-col overflow-auto">
        <header className="border-b border-border/70 bg-card/45 px-4 py-4 sm:px-6">
          <div className="flex w-full flex-col gap-4 lg:flex-row lg:items-center lg:justify-between">
            <div className="min-w-0">
              <div className="flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                <Workflow className="h-3.5 w-3.5 text-primary" />
                Studio
              </div>
              <h1 className="mt-1 truncate text-xl font-semibold text-foreground">
                {canPipelines ? localize(lang, "Пайплайны", "Pipelines") : "Studio"}
              </h1>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
                {localize(lang, "Создавайте пайплайны, запускайте готовые сценарии и подключайте инструменты MCP.", "Build pipelines, run reusable automations, and connect MCP tools.")}
              </p>
            </div>
            <div className="flex shrink-0 flex-wrap items-center gap-2">
              {canPipelines ? (
                <Button className="h-9 gap-1.5" onClick={() => setShowCreate(true)}>
                  <Plus className="h-3.5 w-3.5" />
                  {localize(lang, "Новый пайплайн", "New pipeline")}
                </Button>
              ) : (
                sectionLinks.slice(0, 2).map((item) => (
                  <Button key={item.path} variant="outline" className="h-9 gap-1.5" onClick={() => navigate(item.path)}>
                    <item.icon className="h-3.5 w-3.5" />
                    {item.label}
                  </Button>
                ))
              )}
            </div>
          </div>
          {stats.length ? (
            <div className="mt-4 grid w-full gap-2 sm:grid-cols-2 lg:grid-cols-6">
              {stats.map((item) => (
                <div key={item.label} className="min-w-0 rounded-lg border border-border/70 bg-background/45 px-3 py-2">
                  <div className="flex items-center gap-2 text-xs text-muted-foreground">
                    <item.icon className="h-3.5 w-3.5 shrink-0 text-primary" />
                    <span className="truncate">{item.label}</span>
                  </div>
                  <div className="mt-1 flex items-baseline gap-1">
                    <span className="text-lg font-semibold text-foreground">{item.value}</span>
                    {item.sub ? <span className="text-xs text-muted-foreground">{item.sub}</span> : null}
                  </div>
                </div>
              ))}
            </div>
          ) : null}
        </header>

        <div className="flex w-full flex-1 flex-col gap-4 px-4 py-5 sm:px-6">
          {canPipelines && recentFailedRuns.length ? (
            <div className="rounded-lg border border-red-500/20 bg-red-500/5 px-4 py-2 text-xs leading-5 text-red-200">
              {localize(lang, "Последние ошибки запусков", "Recent failed runs")}: {recentFailedRuns.map((run) => `#${run.id} ${run.pipeline_name}`).join(" · ")}
            </div>
          ) : null}

          {canPipelines ? (
            <>
              <div className="flex items-center gap-3 rounded-lg border border-border/70 bg-card px-3 py-2 shadow-sm">
                <Search className="h-4 w-4 shrink-0 text-muted-foreground" />
                <Input
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={localize(lang, "Поиск пайплайнов...", "Search pipelines...")}
                  aria-label={localize(lang, "Поиск пайплайнов", "Search pipelines")}
                  className="h-9 border-0 bg-transparent px-0 text-sm shadow-none focus-visible:ring-0"
                />
              </div>

              <section className="rounded-xl border border-border bg-card p-4">
                <div className="mb-3 flex items-center justify-between gap-3">
                  <h2 className="text-sm font-semibold text-foreground">
                    {search ? localize(lang, `Результаты по "${search}"`, `Results for "${search}"`) : localize(lang, "Все пайплайны", "All pipelines")}
                  </h2>
                  {pipelines.length > 0 ? <span className="text-xs text-muted-foreground">{pipelines.length}</span> : null}
                </div>

                <QueryStateBlock loading={isLoading} loadingText={localize(lang, "Загружаю пайплайны...", "Loading pipelines...")}>
                  {pipelines.length === 0 ? (
                    <EmptyState
                      icon={<Workflow className="h-5 w-5" />}
                      title={search ? localize(lang, "Ничего не найдено", "No matches") : localize(lang, "Пайплайнов пока нет", "No pipelines yet")}
                      description={search ? localize(lang, "Попробуйте более общий запрос.", "Try a broader query.") : localize(lang, "Создайте первый пайплайн для повторяемой задачи.", "Create your first pipeline for a recurring task.")}
                      actions={!search ? (
                        <Button size="sm" className="h-10 gap-1.5" onClick={() => setShowCreate(true)}>
                          <Plus className="h-3.5 w-3.5" /> {localize(lang, "Новый пайплайн", "New pipeline")}
                        </Button>
                      ) : undefined}
                      hint={!search ? localize(lang, "Добавьте ручной запуск, расписание или webhook.", "Add a manual trigger, schedule, or webhook.") : undefined}
                    />
                  ) : (
                    <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                      {pipelines.map((pipeline) => (
                        <PipelineCard
                          key={pipeline.id}
                          pipeline={pipeline}
                          onOpen={() => navigate(`/studio/pipeline/${pipeline.id}`)}
                          onRun={() => void handleRunPipeline(pipeline)}
                          onClone={() => cloneMutation.mutate(pipeline.id)}
                          onDelete={() => setDeleteTarget(pipeline)}
                          running={
                            preparingRunPipelineId === pipeline.id ||
                            (runMutation.isPending && runMutation.variables?.pipelineId === pipeline.id)
                          }
                          cloning={cloneMutation.isPending && cloneMutation.variables === pipeline.id}
                          lang={lang}
                        />
                      ))}
                    </div>
                  )}
                </QueryStateBlock>
              </section>
            </>
          ) : (
            <section className="workspace-panel p-5">
              <div className="space-y-4">
                <div>
                  <h2 className="text-xl font-semibold text-foreground">{localize(lang, "Доступные разделы", "Available sections")}</h2>
                </div>
                {sectionLinks.length === 0 ? (
                  <EmptyState
                    icon={<Workflow className="h-5 w-5" />}
                    title={localize(lang, "Нет доступных разделов", "No sections available")}
                    description={localize(lang, "Попросите администратора выдать доступ к разделам Студии.", "Ask an administrator for access to Studio sections.")}
                  />
                ) : (
                  <div className="grid grid-cols-1 gap-2 xl:grid-cols-2">
                    {sectionLinks.map((item) => (
                      <button
                        key={item.path}
                        type="button"
                        onClick={() => navigate(item.path)}
                        className="flex items-center gap-3 rounded-lg border border-border bg-card px-4 py-3.5 text-left transition-colors hover:border-primary/30 hover:bg-secondary/30"
                      >
                        <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-primary/10 text-primary">
                          <item.icon className="h-4 w-4" />
                        </div>
                        <div className="min-w-0 flex-1">
                          <div className="text-sm font-medium text-foreground">{item.label}</div>
                          <div className="mt-0.5 text-xs text-muted-foreground">{item.desc}</div>
                        </div>
                        <ChevronRight className="h-4 w-4 shrink-0 text-muted-foreground/50" />
                      </button>
                    ))}
                  </div>
                )}
              </div>
            </section>
          )}
        </div>
      </div>

      <CreatePipelineDialog open={showCreate && canPipelines} onClose={() => setShowCreate(false)} />

      <ManualTriggerDialog
        lang={lang}
        open={Boolean(runTarget)}
        target={runTarget}
        entryNodeId={runEntryNodeId}
        error={runTriggerError}
        options={runTriggerOptions}
        running={runMutation.isPending}
        onClose={() => {
          setRunTarget(null);
          setRunEntryNodeId("");
          setRunTriggerError("");
        }}
        onEntryNodeChange={(nodeId) => {
          setRunEntryNodeId(nodeId);
          setRunTriggerError("");
        }}
        onOpenEditor={(pipelineId) => navigate(`/studio/pipeline/${pipelineId}`)}
        onRun={(pipelineId, entryNodeId) => runMutation.mutate({ pipelineId, entryNodeId })}
        onError={setRunTriggerError}
      />

      <TriggerInfoDialog
        lang={lang}
        target={triggerInfoTarget}
        onClose={() => setTriggerInfoTarget(null)}
        onOpenEditor={(pipelineId) => navigate(`/studio/pipeline/${pipelineId}`)}
      />

      <DeletePipelineDialog
        lang={lang}
        target={deleteTarget}
        deleting={deleteMutation.isPending}
        onClose={() => setDeleteTarget(null)}
        onConfirm={(pipelineId) => deleteMutation.mutate(pipelineId)}
      />
    </div>
  );
}
