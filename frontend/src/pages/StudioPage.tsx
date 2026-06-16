import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
  ChevronRight,
  Copy,
  Loader2,
  MoreHorizontal,
  Play,
  Plus,
  Search,
  Trash2,
  Workflow,
  XCircle,
  Zap,
  BookOpen,
  Server,
  Bot,
  Clock,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Input } from "@/components/ui/input";
import { useToast } from "@/hooks/use-toast";
import { localize, useI18n } from "@/lib/i18n";
import { cn } from "@/lib/utils";
import { formatActivityDetail, formatActivityLabel, formatRelativeTime } from "@/components/studio/StudioActivityText";
import {
  getActiveManualTriggerOptions,
  getActiveMonitoringTriggers,
  getActiveScheduleTriggers,
  getActiveWebhookTriggers,
  toAbsoluteWebhookUrl,
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
import { getPipelineActivityState } from "@/components/pipeline/pipelineActivity";
import { EmptyState, QueryStateBlock } from "@/components/ui/page-shell";
import { getPipelineRuntimePlaceholders } from "./pipeline-editor/pipelineGraphUtils";

function RunStatusBadge({ status, lang }: { status: string; lang: string }) {
  const normalized = status.toLowerCase();
  if (normalized === "completed") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-emerald-500/20 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-400">
        <CheckCircle2 className="h-2.5 w-2.5" /> {localize(lang, "Завершен", "Completed")}
      </span>
    );
  }
  if (normalized === "failed") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-red-500/20 bg-red-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-red-400">
        <XCircle className="h-2.5 w-2.5" /> {localize(lang, "Ошибка", "Failed")}
      </span>
    );
  }
  if (normalized === "running") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-primary/20 bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
        <Loader2 className="h-2.5 w-2.5 animate-spin" /> {localize(lang, "Выполняется", "Running")}
      </span>
    );
  }
  return <span className="rounded-md border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-[10px] font-medium text-muted-foreground">{status}</span>;
}

function StatCard({
  icon: Icon,
  label,
  value,
  sub,
}: {
  icon: React.ElementType;
  label: string;
  value: string | number;
  sub?: string;
}) {
  return (
    <div className="relative overflow-hidden rounded-xl border border-border bg-card px-4 py-4 shadow-sm">
      <div className="absolute left-0 top-0 h-full w-0.5 bg-primary/40" />
      <div className="mb-2 flex items-center gap-2">
        <div className="flex h-6 w-6 items-center justify-center rounded-md bg-primary/10">
          <Icon className="h-3.5 w-3.5 text-primary" />
        </div>
        <span className="text-[11px] font-semibold uppercase tracking-[0.1em] text-muted-foreground/70">{label}</span>
      </div>
      <div className="text-2xl font-bold tracking-tight text-foreground">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground/80">{sub}</div>}
    </div>
  );
}

function PipelineCard({
  pipeline,
  onOpen,
  onRun,
  onClone,
  onDelete,
  running,
  cloning,
  lang,
}: {
  pipeline: PipelineListItem;
  onOpen: () => void;
  onRun: () => void;
  onClone: () => void;
  onDelete: () => void;
  running: boolean;
  cloning: boolean;
  lang: string;
}) {
  const tags = Array.isArray(pipeline.tags) ? pipeline.tags.slice(0, 2) : [];
  const activityState = getPipelineActivityState({
    lastRun: pipeline.last_run,
    triggerSummary: pipeline.trigger_summary,
    graphVersion: pipeline.graph_version,
  });
  const activityToneClass =
    activityState.icon === "running"
      ? "border-primary/30 bg-primary/10 text-primary"
      : activityState.icon === "warning"
      ? "border-amber-500/30 bg-amber-500/10 text-amber-400"
      : "border-border bg-secondary/30 text-muted-foreground";
  const ActivityIcon =
    activityState.icon === "running"
      ? Loader2
      : activityState.icon === "pending"
        ? Clock
        : activityState.icon === "manual"
          ? Play
          : activityState.icon === "schedule"
            ? Clock
            : activityState.icon === "warning"
              ? XCircle
              : activityState.icon === "webhook" || activityState.icon === "monitoring"
                ? Zap
                : Zap;

  const isRunning = pipeline.last_run?.status === "running" || running;

  return (
    <article
      className={cn(
        "group cursor-pointer overflow-hidden rounded-xl border bg-card p-4 shadow-sm transition-all duration-150 hover:shadow-md",
        isRunning
          ? "border-primary/30 hover:border-primary/50 bg-primary/3"
          : "border-border hover:border-primary/25 hover:bg-secondary/15"
      )}
      onClick={onOpen}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-sm font-semibold text-primary">
          {pipeline.icon || "W"}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between">
            <div className="min-w-0 flex-1 pr-2">
              <div className="flex items-center gap-2 flex-wrap">
                <h3 className="text-sm font-semibold text-foreground">{pipeline.name}</h3>
                {pipeline.last_run && <RunStatusBadge status={pipeline.last_run.status} lang={lang} />}
              </div>
              <p className="mt-1 text-xs text-muted-foreground line-clamp-1">
                {pipeline.description || localize(lang, "Описание не задано", "No description")}
              </p>
            </div>

            <div onClick={(e) => e.stopPropagation()}>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="icon" className="h-9 w-9 text-muted-foreground" aria-label={localize(lang, `Действия для ${pipeline.name}`, `Actions for ${pipeline.name}`)}>
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={onOpen}>{localize(lang, "Открыть редактор", "Open editor")}</DropdownMenuItem>
                  <DropdownMenuItem onClick={onClone}>
                    <Copy className="mr-1.5 h-3.5 w-3.5" /> {localize(lang, "Клонировать", "Clone")}
                  </DropdownMenuItem>
                  <DropdownMenuItem className="text-destructive" onClick={onDelete}>
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" /> {localize(lang, "Удалить", "Delete")}
                  </DropdownMenuItem>
                </DropdownMenuContent>
              </DropdownMenu>
            </div>
          </div>

          {tags.length > 0 && (
            <div className="mt-2 flex flex-wrap gap-1">
              {tags.map((tag) => (
                <span key={tag} className="inline-flex items-center rounded border border-border px-1.5 py-0 text-[10px] text-muted-foreground">
                  {tag}
                </span>
              ))}
            </div>
          )}

          <div className="mt-3 flex items-center justify-between gap-3">
            <div className="flex items-center gap-2">
              <span className="text-[11px] text-muted-foreground">
                {formatRelativeTime(pipeline.updated_at, lang)}
              </span>
              {activityState.label && (
                <span className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium", activityToneClass)}>
                  <ActivityIcon className={cn("h-2.5 w-2.5", activityState.icon === "running" && "animate-spin")} />
                  {formatActivityLabel(activityState.label, lang)}
                </span>
              )}
            </div>

            <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
              <Button size="sm" className="h-9 gap-1.5 px-3 text-xs" onClick={onRun} disabled={running}>
                {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                {localize(lang, "Запуск", "Run")}
              </Button>
            </div>
          </div>
          <p className="mt-2 line-clamp-2 text-[11px] leading-4 text-muted-foreground">
            {formatActivityDetail(activityState.detail, lang)}
          </p>

          {cloning && <p className="mt-2 text-[11px] text-primary">{localize(lang, "Создаю копию...", "Creating a copy...")}</p>}
        </div>
      </div>
    </article>
  );
}

function CreatePipelineDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [icon, setIcon] = useState("W");
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const { lang } = useI18n();

  const createMutation = useMutation({
    mutationFn: (payload: { name: string; description: string; icon: string }) =>
      studioPipelines.create({ ...payload, nodes: [], edges: [] }),
    onSuccess: (pipeline) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      setName("");
      setDescription("");
      setIcon("W");
      onClose();
      toast({ description: localize(lang, `Пайплайн "${pipeline.name}" создан.`, `Pipeline "${pipeline.name}" created.`) });
      navigate(`/studio/pipeline/${pipeline.id}`);
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  return (
    <Dialog open={open} onOpenChange={(next) => !next && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>{localize(lang, "Новый пайплайн", "New pipeline")}</DialogTitle>
          <DialogDescription>{localize(lang, "Создать пустой runbook и открыть редактор.", "Create an empty runbook and open the editor.")}</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="flex gap-2">
            <Input value={icon} onChange={(e) => setIcon(e.target.value)} placeholder="W" className="h-10 w-16 text-center" aria-label={localize(lang, "Иконка пайплайна", "Pipeline icon")} />
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder={localize(lang, "Название пайплайна", "Pipeline name")} aria-label={localize(lang, "Название пайплайна", "Pipeline name")} autoFocus />
          </div>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder={localize(lang, "Краткое назначение", "Description")} aria-label={localize(lang, "Описание пайплайна", "Pipeline description")} />
        </div>
        <DialogFooter>
          <Button variant="outline" className="h-10" onClick={onClose}>
            {localize(lang, "Отмена", "Cancel")}
          </Button>
          <Button
            className="h-10"
            onClick={() => createMutation.mutate({ name: name.trim(), description: description.trim(), icon: icon.trim() || "W" })}
            disabled={!name.trim() || createMutation.isPending}
          >
            {createMutation.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            {localize(lang, "Создать", "Create")}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}

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
          ? { label: localize(lang, "Каталог runbook", "Runbook catalog"), desc: localize(lang, "Личные и общие операционные playbook", "Private and shared operations playbooks"), icon: BookOpen, path: "/studio/skills" }
          : null,
        canMcp
          ? { label: localize(lang, "Реестр MCP", "MCP registry"), desc: localize(lang, "Инструменты и интеграции для автоматизации", "Tools and integrations for automation"), icon: Server, path: "/studio/mcp" }
          : null,
        canAgents
          ? { label: localize(lang, "Профили агентов", "Agent profiles"), desc: localize(lang, "Переиспользуемые роли для OPS-задач", "Reusable profiles for OPS tasks"), icon: Bot, path: "/studio/agents" }
          : null,
        canRuns
          ? { label: localize(lang, "История запусков", "Execution history"), desc: localize(lang, "Запуски в вашей зоне доступа", "Runs available for your access scope"), icon: Clock, path: "/studio/runs" }
          : null,
        canNotifications
          ? { label: localize(lang, "Оповещения", "Notifications"), desc: localize(lang, "Каналы доставки для админ-событий", "Delivery settings for admin events"), icon: Zap, path: "/studio/notifications" }
          : null,
      ].filter(Boolean) as Array<{ label: string; desc: string; icon: typeof BookOpen; path: string }>,
    [canAgents, canMcp, canNotifications, canRuns, canSkills, lang],
  );

  const stats = useMemo(
    () =>
      [
        canPipelines ? { icon: Workflow, label: localize(lang, "Пайплайны", "Pipelines"), value: pipelines.length } : null,
        canSkills ? { icon: BookOpen, label: localize(lang, "Runbook", "Runbooks"), value: Array.isArray(skills) ? skills.length : 0 } : null,
        canMcp ? { icon: Server, label: localize(lang, "MCP", "MCP servers"), value: Array.isArray(mcpList) ? mcpList.length : 0 } : null,
        canAgents ? { icon: Bot, label: localize(lang, "Агенты", "Agents"), value: Array.isArray(agents) ? agents.length : 0 } : null,
        canRuns ? { icon: CheckCircle2, label: localize(lang, "Завершено", "Completed"), value: runs.filter((run) => run.status === "completed").length, sub: localize(lang, "запусков", "runs") } : null,
        canRuns ? { icon: XCircle, label: localize(lang, "Ошибки", "Failed"), value: runs.filter((run) => run.status === "failed").length, sub: localize(lang, "запусков", "runs") } : null,
      ].filter(Boolean) as Array<{ icon: React.ElementType; label: string; value: string | number; sub?: string }>,
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
          description: localize(lang, "У пайплайна нет активных триггеров. Сначала добавьте ручной, webhook, schedule или monitoring-триггер.", "This pipeline has no active triggers. Add a manual, webhook, schedule, or monitoring trigger first."),
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

  async function handleCopyWebhookUrl(webhookUrl: string) {
    try {
      await navigator.clipboard.writeText(toAbsoluteWebhookUrl(webhookUrl));
      toast({ description: localize(lang, "Webhook URL скопирован.", "Webhook URL copied.") });
    } catch (error) {
      const message = error instanceof Error ? error.message : localize(lang, "Не удалось скопировать webhook URL.", "Failed to copy webhook URL.");
      toast({ variant: "destructive", description: message });
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
              <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                <Workflow className="h-3.5 w-3.5 text-primary" />
                Studio
              </div>
              <h1 className="mt-1 truncate text-xl font-semibold text-foreground">
                {canPipelines ? localize(lang, "Пайплайны", "Pipelines") : "Studio"}
              </h1>
              <p className="mt-1 max-w-3xl text-sm leading-6 text-muted-foreground">
                {localize(lang, "Runbook, триггеры, проверки, запуски и инструменты MCP в одном рабочем контуре.", "Runbooks, triggers, verification, runs, and MCP tools in one workspace.")}
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
                  <div className="flex items-center gap-2 text-[11px] text-muted-foreground">
                    <item.icon className="h-3.5 w-3.5 shrink-0 text-primary" />
                    <span className="truncate">{item.label}</span>
                  </div>
                  <div className="mt-1 flex items-baseline gap-1">
                    <span className="text-lg font-semibold text-foreground">{item.value}</span>
                    {item.sub ? <span className="text-[11px] text-muted-foreground">{item.sub}</span> : null}
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
                      description={search ? localize(lang, "Попробуйте более общий запрос.", "Try a broader query.") : localize(lang, "Создайте первый runbook для повторяемой OPS-задачи.", "Create the first runbook for a repeatable OPS task.")}
                      actions={!search ? (
                        <Button size="sm" className="h-10 gap-1.5" onClick={() => setShowCreate(true)}>
                          <Plus className="h-3.5 w-3.5" /> {localize(lang, "Новый пайплайн", "New pipeline")}
                        </Button>
                      ) : undefined}
                      hint={!search ? localize(lang, "Добавьте manual trigger для запуска по запросу или schedule/webhook trigger для автоматизации.", "Add a manual trigger to run on demand, or a schedule/webhook trigger to automate.") : undefined}
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
                  <p className="enterprise-kicker mb-1">Studio</p>
                  <h2 className="text-xl font-semibold text-foreground">{localize(lang, "Доступные разделы", "Available sections")}</h2>
                </div>
                {sectionLinks.length === 0 ? (
                  <EmptyState
                    icon={<Workflow className="h-5 w-5" />}
                    title={localize(lang, "Разделы Studio недоступны", "No Studio sections available")}
                    description={localize(lang, "Выдайте доступ в Settings, чтобы открыть runbook, MCP, agents, runs или notifications.", "Grant a Studio section in Settings to open runbooks, MCP, agents, runs, or notifications.")}
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

      <Dialog
        open={Boolean(runTarget)}
        onOpenChange={(next) => {
          if (!next) {
            setRunTarget(null);
            setRunEntryNodeId("");
            setRunTriggerError("");
          }
        }}
      >
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>{localize(lang, "Выберите ручной вход", "Choose manual trigger")}</DialogTitle>
            <DialogDescription>
              {runTarget
                ? localize(lang, `В пайплайне "${runTarget.name}" несколько ручных входов. Выберите ветку для запуска.`, `Pipeline "${runTarget.name}" has multiple manual entry nodes. Choose which branch to launch.`)
                : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <label className="space-y-2 text-sm">
              <span className="text-muted-foreground">{localize(lang, "Ручной вход", "Manual trigger")}</span>
              <select
                value={runEntryNodeId}
                onChange={(event) => {
                  setRunEntryNodeId(event.target.value);
                  setRunTriggerError("");
                }}
                className="flex h-10 w-full rounded-xl border border-border bg-background px-3 text-sm text-foreground"
              >
                {runTriggerOptions.map((option) => (
                  <option key={option.nodeId} value={option.nodeId}>
                    {option.label}
                  </option>
                ))}
              </select>
            </label>
            {runTriggerError ? <p className="text-xs text-destructive">{runTriggerError}</p> : null}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              className="h-10"
              onClick={() => {
                if (runTarget) {
                  navigate(`/studio/pipeline/${runTarget.id}`);
                }
              }}
            >
              {localize(lang, "Открыть редактор", "Open editor")}
            </Button>
            <Button
              variant="outline"
              className="h-10"
              onClick={() => {
                setRunTarget(null);
                setRunEntryNodeId("");
                setRunTriggerError("");
              }}
            >
              {localize(lang, "Отмена", "Cancel")}
            </Button>
            <Button
              className="h-10"
              onClick={() => {
                if (!runTarget) {
                  return;
                }
                if (!runEntryNodeId) {
                  setRunTriggerError(localize(lang, "Выберите ручной вход для запуска.", "Choose a manual trigger to start the run."));
                  return;
                }
                runMutation.mutate({ pipelineId: runTarget.id, entryNodeId: runEntryNodeId });
              }}
              disabled={runMutation.isPending}
            >
              {runMutation.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              {localize(lang, "Запустить", "Run")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog
        open={Boolean(triggerInfoTarget)}
        onOpenChange={(next) => {
          if (!next) {
            setTriggerInfoTarget(null);
          }
        }}
      >
        <DialogContent className="max-w-lg">
          <DialogHeader>
            <DialogTitle>
              {triggerInfoTarget?.webhookTriggers.length
                ? localize(lang, "Webhook-триггер", "Webhook trigger")
                : triggerInfoTarget?.scheduleTriggers.length
                  ? localize(lang, "Запуск по расписанию", "Scheduled trigger")
                  : localize(lang, "Monitoring-триггер", "Monitoring trigger")}
            </DialogTitle>
            <DialogDescription>
              {triggerInfoTarget?.webhookTriggers.length
                ? localize(lang, `Пайплайн "${triggerInfoTarget.pipeline.name}" запускается входящими webhook-запросами. Нажимать "Запустить" не нужно.`, `Pipeline "${triggerInfoTarget.pipeline.name}" is started by incoming webhook requests. You do not need to press Run first.`)
                : triggerInfoTarget?.scheduleTriggers.length
                  ? localize(lang, `Пайплайн "${triggerInfoTarget.pipeline.name}" запускается по расписанию. Ручной запуск здесь не нужен.`, `Pipeline "${triggerInfoTarget.pipeline.name}" is started by its schedule. There is nothing to launch manually.`)
                  : triggerInfoTarget
                    ? localize(lang, `Пайплайн "${triggerInfoTarget.pipeline.name}" запускается alert-событиями мониторинга. Сохраните граф, и monitoring создаст запуск при совпадении условий.`, `Pipeline "${triggerInfoTarget.pipeline.name}" is started by server monitoring alerts. Save the graph and let monitoring create runs when a matching issue is detected.`)
                  : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {triggerInfoTarget?.webhookTriggers.length ? (
              <div className="rounded-xl border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                {localize(lang, "Достаточно сохранить граф. Каждый POST на URL ниже создаст новый запуск пайплайна.", "Save is enough to arm the trigger. Every POST request to the webhook URL below creates a new pipeline run.")}
              </div>
            ) : null}

            {triggerInfoTarget?.webhookTriggers.map((trigger) => (
              <div key={trigger.id} className="space-y-2 rounded-xl border border-border bg-background/60 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-foreground">{trigger.name || localize(lang, "Webhook-триггер", "Webhook trigger")}</div>
                    <div className="text-[11px] text-muted-foreground">Node `{trigger.node_id}`</div>
                  </div>
                  <Button size="sm" variant="outline" className="h-9" onClick={() => void handleCopyWebhookUrl(trigger.webhook_url)}>
                    <Copy className="mr-1.5 h-3.5 w-3.5" />
                    {localize(lang, "Копировать URL", "Copy URL")}
                  </Button>
                </div>
                <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground break-all">
                  {toAbsoluteWebhookUrl(trigger.webhook_url)}
                </div>
              </div>
            ))}

            {triggerInfoTarget?.scheduleTriggers.map((trigger) => (
              <div key={trigger.id} className="space-y-1 rounded-xl border border-border bg-background/60 p-3">
                <div className="text-sm font-medium text-foreground">{trigger.name || localize(lang, "Schedule-триггер", "Schedule trigger")}</div>
                <div className="text-[11px] text-muted-foreground">Node `{trigger.node_id}`</div>
                <div className="text-xs text-muted-foreground">Cron: {trigger.cron_expression || localize(lang, "не задан", "not set")}</div>
              </div>
            ))}

            {triggerInfoTarget?.monitoringTriggers.length ? (
              <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                {localize(lang, "Monitoring-триггеры активируются после сохранения. Новый запуск появится только когда мониторинг откроет подходящий alert.", "Monitoring triggers are armed after save. A new run appears only when server monitoring opens a matching alert.")}
              </div>
            ) : null}

            {triggerInfoTarget?.monitoringTriggers.map((trigger) => {
              const filters = trigger.monitoring_filters && typeof trigger.monitoring_filters === "object"
                ? (trigger.monitoring_filters as Record<string, unknown>)
                : {};
              const serverIds = Array.isArray(filters.server_ids) ? filters.server_ids.join(", ") : "any";
              const severities = Array.isArray(filters.severities) ? filters.severities.join(", ") : "any";
              const alertTypes = Array.isArray(filters.alert_types) ? filters.alert_types.join(", ") : "any";
              const containers = Array.isArray(filters.container_names) ? filters.container_names.join(", ") : "any";
              return (
                <div key={trigger.id} className="space-y-1 rounded-xl border border-border bg-background/60 p-3">
                  <div className="text-sm font-medium text-foreground">{trigger.name || localize(lang, "Monitoring-триггер", "Monitoring trigger")}</div>
                  <div className="text-[11px] text-muted-foreground">Node `{trigger.node_id}`</div>
                  <div className="text-xs text-muted-foreground">{localize(lang, "Серверы", "Servers")}: {serverIds}</div>
                  <div className="text-xs text-muted-foreground">{localize(lang, "Важность", "Severity")}: {severities}</div>
                  <div className="text-xs text-muted-foreground">{localize(lang, "Тип alert", "Alert type")}: {alertTypes}</div>
                  <div className="text-xs text-muted-foreground">{localize(lang, "Контейнеры", "Containers")}: {containers}</div>
                </div>
              );
            })}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              className="h-10"
              onClick={() => {
                if (triggerInfoTarget) {
                  navigate(`/studio/pipeline/${triggerInfoTarget.pipeline.id}`);
                }
              }}
            >
              {localize(lang, "Открыть редактор", "Open editor")}
            </Button>
            <Button variant="outline" className="h-10" onClick={() => setTriggerInfoTarget(null)}>
              {localize(lang, "Закрыть", "Close")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(deleteTarget)} onOpenChange={(next) => !next && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{localize(lang, "Удалить пайплайн", "Delete pipeline")}</DialogTitle>
            <DialogDescription>
              {deleteTarget ? localize(lang, `Удалить "${deleteTarget.name}"? Действие нельзя отменить.`, `Delete "${deleteTarget.name}"? This cannot be undone.`) : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" className="h-10" onClick={() => setDeleteTarget(null)}>
              {localize(lang, "Отмена", "Cancel")}
            </Button>
            <Button
              variant="destructive"
              className="h-10"
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              {localize(lang, "Удалить", "Delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
