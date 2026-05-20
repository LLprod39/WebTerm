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
  AlertTriangle,
  Trash2,
  Workflow,
  XCircle,
  Zap,
  BookOpen,
  Server,
  Bot,
  Clock,
  MessageSquare,
  Route,
  ShieldCheck,
  Wand2,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
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
import { cn } from "@/lib/utils";
import { StudioHero, HeroStatChip, HeroActionButton } from "@/components/studio/StudioHero";
import {
  studioPipelines,
  studioMCP,
  studioRuns,
  studioSkills,
  studioAgents,
  fetchAuthSession,
  type PipelineListItem,
  type PipelineDetail,
  type PipelineTrigger,
  type StudioPipelineAssistantResponse,
} from "@/lib/api";
import { StudioNav } from "@/components/StudioNav";
import { hasFeatureAccess } from "@/lib/featureAccess";
import { getPipelineActivityState } from "@/components/pipeline/pipelineActivity";
import { applyAssistantGraphPatch, getAssistantPatchStats } from "@/components/pipeline/assistantPatch";
import { EmptyState, QueryStateBlock } from "@/components/ui/page-shell";

type ManualTriggerOption = {
  nodeId: string;
  label: string;
};

type TriggerInfoTarget = {
  pipeline: PipelineDetail;
  webhookTriggers: PipelineTrigger[];
  scheduleTriggers: PipelineTrigger[];
  monitoringTriggers: PipelineTrigger[];
};

function formatRelativeTime(value: string): string {
  const diffMs = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(diffMs / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
}

function getActiveManualTriggerOptions(pipeline: PipelineDetail | null): ManualTriggerOption[] {
  if (!pipeline || !Array.isArray(pipeline.nodes)) {
    return [];
  }
  return pipeline.nodes
    .filter((node) => node.type === "trigger/manual")
    .map((node) => {
      const data = node.data && typeof node.data === "object" ? node.data : {};
      return {
        nodeId: node.id,
        label:
          typeof data.label === "string" && data.label.trim()
            ? data.label.trim()
            : `Manual Trigger ${node.id}`,
        isActive: data.is_active !== false,
      };
    })
    .filter((node) => node.isActive)
    .map(({ nodeId, label }) => ({ nodeId, label }));
}

function getActiveWebhookTriggers(pipeline: PipelineDetail | null): PipelineTrigger[] {
  if (!pipeline || !Array.isArray(pipeline.triggers)) {
    return [];
  }
  return pipeline.triggers.filter((trigger) => trigger.trigger_type === "webhook" && trigger.is_active);
}

function getActiveScheduleTriggers(pipeline: PipelineDetail | null): PipelineTrigger[] {
  if (!pipeline || !Array.isArray(pipeline.triggers)) {
    return [];
  }
  return pipeline.triggers.filter((trigger) => trigger.trigger_type === "schedule" && trigger.is_active);
}

function getActiveMonitoringTriggers(pipeline: PipelineDetail | null): PipelineTrigger[] {
  if (!pipeline || !Array.isArray(pipeline.triggers)) {
    return [];
  }
  return pipeline.triggers.filter((trigger) => trigger.trigger_type === "monitoring" && trigger.is_active);
}

function toAbsoluteWebhookUrl(webhookUrl: string): string {
  return new URL(webhookUrl, window.location.origin).toString();
}

function RunStatusBadge({ status }: { status: string }) {
  const normalized = status.toLowerCase();
  if (normalized === "completed") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-emerald-500/20 bg-emerald-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-400">
        <CheckCircle2 className="h-2.5 w-2.5" /> Completed
      </span>
    );
  }
  if (normalized === "failed") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-red-500/20 bg-red-500/10 px-1.5 py-0.5 text-[10px] font-semibold text-red-400">
        <XCircle className="h-2.5 w-2.5" /> Failed
      </span>
    );
  }
  if (normalized === "running") {
    return (
      <span className="inline-flex items-center gap-1 rounded-md border border-primary/20 bg-primary/10 px-1.5 py-0.5 text-[10px] font-semibold text-primary">
        <Loader2 className="h-2.5 w-2.5 animate-spin" /> Running
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

function formatAiDiagnostic(message: string): string {
  const text = String(message || "").trim();
  const cycleMatch = text.match(/^AI edge '([^']+)->([^']+)' would create a cycle and was dropped\.$/);
  if (cycleMatch) {
    return `Удалена связь ${cycleMatch[1]} -> ${cycleMatch[2]}: она создавала цикл в DAG.`;
  }
  const missingMatch = text.match(/^AI edge '([^']+)->([^']+)' referenced a missing node and was dropped\.$/);
  if (missingMatch) {
    return `Удалена связь ${missingMatch[1]} -> ${missingMatch[2]}: одна из нод не найдена.`;
  }
  const repairedMatch = text.match(/^AI graph repair added edge '([^']+)->([^']+)' \(([^)]+)\)\.$/);
  if (repairedMatch) {
    return `Добавлена связь ${repairedMatch[1]} -> ${repairedMatch[2]}: автоматический ремонт графа.`;
  }
  return text;
}

function PipelineCard({
  pipeline,
  onOpen,
  onRun,
  onClone,
  onDelete,
  running,
  cloning,
}: {
  pipeline: PipelineListItem;
  onOpen: () => void;
  onRun: () => void;
  onClone: () => void;
  onDelete: () => void;
  running: boolean;
  cloning: boolean;
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
                {pipeline.last_run && <RunStatusBadge status={pipeline.last_run.status} />}
              </div>
              <p className="mt-1 text-xs text-muted-foreground line-clamp-1">
                {pipeline.description || "No description"}
              </p>
            </div>

            <div onClick={(e) => e.stopPropagation()}>
              <DropdownMenu>
                <DropdownMenuTrigger asChild>
                  <Button variant="ghost" size="sm" className="h-8 w-8 p-0 text-muted-foreground" aria-label={`Actions for ${pipeline.name}`}>
                    <MoreHorizontal className="h-4 w-4" />
                  </Button>
                </DropdownMenuTrigger>
                <DropdownMenuContent align="end">
                  <DropdownMenuItem onClick={onOpen}>Open Editor</DropdownMenuItem>
                  <DropdownMenuItem onClick={onClone}>
                    <Copy className="mr-1.5 h-3.5 w-3.5" /> Clone
                  </DropdownMenuItem>
                  <DropdownMenuItem className="text-destructive" onClick={onDelete}>
                    <Trash2 className="mr-1.5 h-3.5 w-3.5" /> Delete
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
                {formatRelativeTime(pipeline.updated_at)}
              </span>
              {activityState.label && (
                <span className={cn("inline-flex items-center gap-1 rounded border px-1.5 py-0.5 text-[10px] font-medium", activityToneClass)}>
                  <ActivityIcon className={cn("h-2.5 w-2.5", activityState.icon === "running" && "animate-spin")} />
                  {activityState.label}
                </span>
              )}
            </div>

            <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
              <Button size="sm" className="h-7 gap-1.5 px-3 text-xs" onClick={onRun} disabled={running}>
                {running ? <Loader2 className="h-3 w-3 animate-spin" /> : <Play className="h-3 w-3" />}
                Run
              </Button>
            </div>
          </div>
          <p className="mt-2 line-clamp-2 text-[11px] leading-4 text-muted-foreground">
            {activityState.detail}
          </p>

          {cloning && <p className="mt-2 text-[11px] text-primary">Creating a copy...</p>}
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

  const createMutation = useMutation({
    mutationFn: (payload: { name: string; description: string; icon: string }) =>
      studioPipelines.create({ ...payload, nodes: [], edges: [] }),
    onSuccess: (pipeline) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      setName("");
      setDescription("");
      setIcon("W");
      onClose();
      toast({ description: `Pipeline "${pipeline.name}" created.` });
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
          <DialogTitle>New Pipeline</DialogTitle>
          <DialogDescription>Create an empty workflow and open the editor.</DialogDescription>
        </DialogHeader>
        <div className="space-y-3 py-2">
          <div className="flex gap-2">
            <Input value={icon} onChange={(e) => setIcon(e.target.value)} placeholder="W" className="w-16 text-center" aria-label="Pipeline icon" />
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Pipeline name" aria-label="Pipeline name" autoFocus />
          </div>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" aria-label="Pipeline description" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => createMutation.mutate({ name: name.trim(), description: description.trim(), icon: icon.trim() || "W" })}
            disabled={!name.trim() || createMutation.isPending}
          >
            {createMutation.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
            Create
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
  const [search, setSearch] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [deleteTarget, setDeleteTarget] = useState<PipelineListItem | null>(null);
  const [runTarget, setRunTarget] = useState<PipelineDetail | null>(null);
  const [runEntryNodeId, setRunEntryNodeId] = useState("");
  const [runTriggerError, setRunTriggerError] = useState("");
  const [preparingRunPipelineId, setPreparingRunPipelineId] = useState<number | null>(null);
  const [triggerInfoTarget, setTriggerInfoTarget] = useState<TriggerInfoTarget | null>(null);
  const [aiPrompt, setAiPrompt] = useState("");
  const [aiDraft, setAiDraft] = useState<StudioPipelineAssistantResponse | null>(null);
  const [aiDraftName, setAiDraftName] = useState("AI Automation Draft");

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

  const runTriggerOptions = useMemo(() => getActiveManualTriggerOptions(runTarget), [runTarget]);

  const sectionLinks = useMemo(
    () =>
      [
        canSkills
          ? { label: "Skill Catalog", desc: "Private and shared skill playbooks", icon: BookOpen, path: "/studio/skills" }
          : null,
        canMcp
          ? { label: "MCP Registry", desc: "Personal and shared MCP servers", icon: Server, path: "/studio/mcp" }
          : null,
        canAgents
          ? { label: "Agent Configs", desc: "Reusable agent profiles", icon: Bot, path: "/studio/agents" }
          : null,
        canRuns
          ? { label: "Execution History", desc: "Runs available for your access scope", icon: Clock, path: "/studio/runs" }
          : null,
        canNotifications
          ? { label: "Notifications", desc: "Admin delivery settings", icon: Zap, path: "/studio/notifications" }
          : null,
      ].filter(Boolean) as Array<{ label: string; desc: string; icon: typeof BookOpen; path: string }>,
    [canAgents, canMcp, canNotifications, canRuns, canSkills],
  );

  const stats = useMemo(
    () =>
      [
        canPipelines ? { icon: Workflow, label: "Pipelines", value: pipelines.length } : null,
        canSkills ? { icon: BookOpen, label: "Skills", value: Array.isArray(skills) ? skills.length : 0 } : null,
        canMcp ? { icon: Server, label: "MCP Servers", value: Array.isArray(mcpList) ? mcpList.length : 0 } : null,
        canAgents ? { icon: Bot, label: "Agents", value: Array.isArray(agents) ? agents.length : 0 } : null,
        canRuns ? { icon: CheckCircle2, label: "Completed", value: runs.filter((run) => run.status === "completed").length, sub: "runs" } : null,
        canRuns ? { icon: XCircle, label: "Failed", value: runs.filter((run) => run.status === "failed").length, sub: "runs" } : null,
      ].filter(Boolean) as Array<{ icon: React.ElementType; label: string; value: string | number; sub?: string }>,
    [agents, canAgents, canMcp, canPipelines, canRuns, canSkills, mcpList, pipelines.length, runs, skills],
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
      toast({ description: `Run #${run.id} started.` });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const cloneMutation = useMutation({
    mutationFn: (pipelineId: number) => studioPipelines.clone(pipelineId),
    onSuccess: (pipeline) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      toast({ description: `Cloned as "${pipeline.name}".` });
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
      toast({ description: "Pipeline deleted." });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const aiBuilderMutation = useMutation({
    mutationFn: (message: string) =>
      studioPipelines.assistant({
        pipeline_id: null,
        pipeline_name: aiDraftName.trim() || "AI Automation Draft",
        nodes: [],
        edges: [],
        selected_node: null,
        user_message: message,
        intent: "create",
        last_validation_errors: aiDraft?.validation?.errors || [],
        draft_mode: true,
        history: aiDraft
          ? [
              {
                role: "assistant",
                content: [aiDraft.reply, aiDraft.patch_summary, ...(aiDraft.validation?.errors || [])]
                  .filter(Boolean)
                  .join("\n"),
              },
            ]
          : [],
      }),
    onSuccess: (response) => {
      setAiDraft(response);
      toast({
        description: response.validation?.ok === false
          ? "AI draft needs fixes before it can be created."
          : "AI draft is ready for review.",
      });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const createAiDraftMutation = useMutation({
    mutationFn: async ({ openEditor }: { openEditor: boolean }) => {
      if (!aiDraft) {
        throw new Error("No AI draft to apply.");
      }
      const result = applyAssistantGraphPatch({
        nodes: [],
        edges: [],
        response: aiDraft,
      });
      if (!result.stats.hasChanges) {
        throw new Error("AI draft does not contain graph changes.");
      }
      const pipeline = await studioPipelines.create({
        name: aiDraftName.trim() || "AI Automation Draft",
        description: aiPrompt.trim() || aiDraft.reply || "",
        icon: "W",
        tags: ["ai-builder"],
        nodes: result.nodes,
        edges: result.edges,
      });
      return { pipeline, openEditor };
    },
    onSuccess: ({ pipeline, openEditor }) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      setAiDraft(null);
      if (openEditor) {
        navigate(`/studio/pipeline/${pipeline.id}`);
        return;
      }
      toast({ description: `Pipeline "${pipeline.name}" created.` });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  function handleAiBuilderSubmit(messageOverride?: string) {
    const message = (messageOverride || aiPrompt).trim();
    if (!message) {
      toast({ variant: "destructive", description: "Describe the automation first." });
      return;
    }
    aiBuilderMutation.mutate(message);
  }

  function handleCreateAiDraft(openEditor: boolean) {
    if (!aiDraft) return;
    if (aiDraft.validation?.ok === false) {
      toast({ variant: "destructive", description: "Fix AI draft validation errors before creating a pipeline." });
      return;
    }
    if (aiDraft.risk?.level === "dangerous") {
      toast({ variant: "destructive", description: "This draft contains a dangerous SSH command. Ask AI to add approval or rewrite it safely." });
      return;
    }
    createAiDraftMutation.mutate({ openEditor });
  }

  async function handleRunPipeline(pipeline: PipelineListItem) {
    setRunTriggerError("");
    setPreparingRunPipelineId(pipeline.id);
    try {
      const detail = await studioPipelines.get(pipeline.id);
      const manualTriggers = getActiveManualTriggerOptions(detail);
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
          description: "This pipeline has no active triggers. Add a manual, webhook, schedule, or monitoring trigger first.",
        });
        return;
      }
      if (manualTriggers.length === 1) {
        runMutation.mutate({ pipelineId: pipeline.id, entryNodeId: manualTriggers[0].nodeId });
        return;
      }
      setRunTarget(detail);
      setRunEntryNodeId(manualTriggers[0].nodeId);
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to prepare pipeline run.";
      toast({ variant: "destructive", description: message });
    } finally {
      setPreparingRunPipelineId(null);
    }
  }

  async function handleCopyWebhookUrl(webhookUrl: string) {
    try {
      await navigator.clipboard.writeText(toAbsoluteWebhookUrl(webhookUrl));
      toast({ description: "Webhook URL copied." });
    } catch (error) {
      const message = error instanceof Error ? error.message : "Failed to copy webhook URL.";
      toast({ variant: "destructive", description: message });
    }
  }

  const aiDraftStats = aiDraft ? getAssistantPatchStats(aiDraft) : null;
  const recentFailedRuns = canRuns ? runs.filter((run) => run.status === "failed").slice(0, 3) : [];
  const aiDraftCanApply =
    Boolean(aiDraft && aiDraftStats?.hasChanges) &&
    aiDraft?.validation?.ok !== false &&
    aiDraft?.risk?.level !== "dangerous";
  const aiDraftErrors = aiDraft?.validation?.errors || [];
  const aiDraftWarnings = [...(aiDraft?.warnings || []), ...(aiDraft?.validation?.warnings || [])].slice(0, 4);
  const aiDraftNodePreview = aiDraft?.graph_patch?.nodes || [];
  const aiDraftStatus = !aiDraft
    ? { label: "Ожидает запроса", className: "border-border bg-secondary/40 text-muted-foreground", icon: MessageSquare }
    : aiDraft.validation?.ok === false
      ? { label: "Нужна правка", className: "border-red-500/25 bg-red-500/10 text-red-300", icon: AlertTriangle }
      : aiDraft.risk?.level === "dangerous"
        ? { label: "Опасная команда", className: "border-amber-500/25 bg-amber-500/10 text-amber-300", icon: AlertTriangle }
        : { label: "DAG проверен", className: "border-emerald-500/25 bg-emerald-500/10 text-emerald-300", icon: ShieldCheck };
  const AiDraftStatusIcon = aiDraftStatus.icon;

  return (
    <div className="flex h-full flex-col">
      <StudioNav />

      <div className="flex-1 overflow-auto flex flex-col">
      <StudioHero
        kicker="Studio"
        title={canPipelines ? "Pipelines" : "Studio"}
        titleIcon={<Workflow className="h-7 w-7 text-primary" />}
        description="Build and automate workflows. Connect pipelines, agents, skills, and MCP servers."
        stats={
          <>
            {canPipelines && <HeroStatChip icon={<Workflow className="h-3.5 w-3.5" />} label={`${pipelines.length} pipelines`} />}
            {canSkills && Array.isArray(skills) && <HeroStatChip icon={<BookOpen className="h-3.5 w-3.5" />} label={`${skills.length} skills`} />}
            {canRuns && <HeroStatChip icon={<CheckCircle2 className="h-3.5 w-3.5" />} label={`${runs.filter((r) => r.status === "completed").length} completed`} />}
            {canRuns && runs.filter((r) => r.status === "failed").length > 0 && (
              <HeroStatChip icon={<XCircle className="h-3.5 w-3.5" />} label={`${runs.filter((r) => r.status === "failed").length} failed`} />
            )}
          </>
        }
        actions={
          canPipelines ? (
            <HeroActionButton
              onClick={() => setShowCreate(true)}
              icon={<Plus className="h-4 w-4" />}
              label="New Pipeline"
              primary
            />
          ) : sectionLinks.length > 0 ? (
            <>
              {sectionLinks.slice(0, 2).map((item) => (
                <HeroActionButton
                  key={item.path}
                  onClick={() => navigate(item.path)}
                  icon={<item.icon className="h-4 w-4 text-primary/80" />}
                  label={item.label}
                />
              ))}
            </>
          ) : undefined
        }
      />

      <div className="flex-1 px-6 pb-8 space-y-5">
        {canPipelines && (
          <section className="overflow-hidden rounded-xl border border-border/80 bg-card shadow-sm">
            <div className="flex flex-col gap-3 border-b border-border/70 bg-gradient-to-r from-primary/10 via-transparent to-transparent px-5 py-4 lg:flex-row lg:items-center lg:justify-between">
              <div className="flex min-w-0 items-start gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/25 bg-primary/10">
                  <Wand2 className="h-5 w-5 text-primary" />
                </span>
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h2 className="text-base font-semibold text-foreground">AI Automation Agent</h2>
                    <Badge variant="outline" className={cn("gap-1", aiDraftStatus.className)}>
                      <AiDraftStatusIcon className="h-3 w-3" />
                      {aiDraftStatus.label}
                    </Badge>
                  </div>
                  <p className="mt-1 max-w-3xl text-xs leading-5 text-muted-foreground">
                    Опиши цель обычным языком. Агент соберет DAG, нормализует ноды, проверит связи и не даст сохранить битый граф.
                  </p>
                </div>
              </div>
              <div className="flex shrink-0 flex-wrap gap-1.5 text-[10px] font-medium text-muted-foreground">
                {[
                  ["Понять", MessageSquare],
                  ["Собрать DAG", Route],
                  ["Проверить", ShieldCheck],
                  ["Сохранить", CheckCircle2],
                ].map(([label, Icon]) => (
                  <span key={label as string} className="inline-flex items-center gap-1 rounded-md border border-border/70 bg-background/40 px-2 py-1">
                    <Icon className="h-3 w-3 text-primary" />
                    {label as string}
                  </span>
                ))}
              </div>
            </div>

            <div className="grid gap-0 xl:grid-cols-[minmax(0,1fr)_430px]">
              <div className="min-w-0 space-y-4 p-5">
                <div className="grid grid-cols-1 gap-3 lg:grid-cols-[240px_minmax(0,1fr)]">
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Имя пайплайна</label>
                    <Input
                      value={aiDraftName}
                      onChange={(event) => setAiDraftName(event.target.value)}
                      placeholder="Pipeline name"
                      className="h-10 bg-background/70"
                      aria-label="AI draft pipeline name"
                    />
                  </div>
                  <div className="space-y-1.5">
                    <label className="text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">Задача для агента</label>
                    <Textarea
                      value={aiPrompt}
                      onChange={(event) => setAiPrompt(event.target.value)}
                      placeholder="Например: каждый день собрать логи по серверам, кратко отправить в Telegram и предусмотреть отдельный вход для задач оператора"
                      className="min-h-[128px] resize-none bg-background/70 text-[15px] leading-6"
                      aria-label="AI automation request"
                    />
                  </div>
                </div>

                <div className="flex flex-wrap gap-2">
                  {[
                    "Ежедневный health-check серверов с Telegram-отчетом",
                    "Отдельный Telegram/webhook вход для задач оператора",
                    "Проверить граф и исправить DAG ошибки",
                    "Docker monitoring с approval перед опасными действиями",
                  ].map((prompt) => (
                    <Button
                      key={prompt}
                      type="button"
                      variant="outline"
                      size="sm"
                      className="h-8 rounded-md border-border/80 bg-background/40 text-xs"
                      disabled={aiBuilderMutation.isPending}
                      onClick={() => {
                        setAiPrompt(prompt);
                        handleAiBuilderSubmit(prompt);
                      }}
                    >
                      {prompt}
                    </Button>
                  ))}
                </div>

                <div className="flex flex-wrap items-center gap-2">
                  <Button
                    className="h-10 gap-2 px-4"
                    disabled={aiBuilderMutation.isPending || !aiPrompt.trim()}
                    onClick={() => handleAiBuilderSubmit()}
                  >
                    {aiBuilderMutation.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Wand2 className="h-4 w-4" />}
                    Собрать и проверить DAG
                  </Button>
                  {aiDraft?.validation?.ok === false ? (
                    <Button
                      variant="outline"
                      className="h-10 gap-2"
                      disabled={aiBuilderMutation.isPending}
                      onClick={() =>
                        handleAiBuilderSubmit(
                          `Пересобери черновик заново как валидный DAG. Исправь ошибки: ${aiDraftErrors.join("; ")}. Не создавай циклы и не делай Telegram Input триггером.`,
                        )
                      }
                    >
                      <Route className="h-4 w-4" />
                      Пересобрать без циклов
                    </Button>
                  ) : null}
                  {aiDraft ? (
                    <Button variant="ghost" className="h-10" onClick={() => setAiDraft(null)}>
                      Сбросить
                    </Button>
                  ) : null}
                </div>
              </div>

              <aside className="border-t border-border/70 bg-background/35 p-5 xl:border-l xl:border-t-0">
                {aiDraft ? (
                  <div className="flex h-full flex-col gap-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <h3 className="text-sm font-semibold text-foreground">Проверенный черновик</h3>
                        <p className="mt-1 text-xs leading-5 text-muted-foreground">{aiDraft.patch_summary || aiDraft.reply}</p>
                      </div>
                      <Badge variant="outline" className={cn("shrink-0 gap-1", aiDraftStatus.className)}>
                        <AiDraftStatusIcon className="h-3 w-3" />
                        {aiDraftStatus.label}
                      </Badge>
                    </div>

                    <div className="grid grid-cols-3 gap-2 text-center text-[10px]">
                      {[
                        ["нод", aiDraftStats?.addedNodes || 0],
                        ["связей", aiDraftStats?.addedEdges || 0],
                        ["правок", aiDraftStats?.updatedNodes || 0],
                      ].map(([label, value]) => (
                        <div key={label as string} className="rounded-lg border border-border/70 bg-card/70 px-2 py-2">
                          <div className="text-base font-semibold text-foreground">{value as number}</div>
                          <div className="text-muted-foreground">{label as string}</div>
                        </div>
                      ))}
                    </div>

                    {aiDraftNodePreview.length ? (
                      <div className="space-y-2">
                        <div className="flex items-center gap-2 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground">
                          <Route className="h-3.5 w-3.5" />
                          План графа
                        </div>
                        <div className="flex flex-wrap items-center gap-1.5">
                          {aiDraftNodePreview.slice(0, 6).map((node, index) => (
                            <span
                              key={node.ref}
                              className="inline-flex max-w-full items-center gap-1 rounded-md border border-border/70 bg-card/70 px-2 py-1 text-[10px] text-muted-foreground"
                            >
                              <span className="max-w-[140px] truncate">{node.label || node.type}</span>
                              {index < Math.min(aiDraftNodePreview.length, 6) - 1 ? <ChevronRight className="h-2.5 w-2.5 shrink-0" /> : null}
                            </span>
                          ))}
                          {aiDraftNodePreview.length > 6 ? (
                            <span className="text-[10px] text-muted-foreground">+{aiDraftNodePreview.length - 6}</span>
                          ) : null}
                        </div>
                      </div>
                    ) : null}

                    {aiDraftWarnings.length ? (
                      <div className="rounded-lg border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-[11px] leading-5 text-amber-100">
                        {aiDraftWarnings.map((warning) => (
                          <div key={warning} className="flex gap-2">
                            <AlertTriangle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                            <span>{formatAiDiagnostic(warning)}</span>
                          </div>
                        ))}
                      </div>
                    ) : null}

                    {aiDraftErrors.length ? (
                      <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-[11px] leading-5 text-red-100">
                        {aiDraftErrors.slice(0, 4).map((error) => (
                          <div key={error} className="flex gap-2">
                            <XCircle className="mt-0.5 h-3.5 w-3.5 shrink-0" />
                            <span>{formatAiDiagnostic(error)}</span>
                          </div>
                        ))}
                      </div>
                    ) : null}

                    {aiDraft.risk?.level === "dangerous" ? (
                      <div className="rounded-lg border border-red-500/25 bg-red-500/10 px-3 py-2 text-[11px] leading-5 text-red-100">
                        Обнаружена опасная SSH-команда. Нужен approval или безопасная замена команды.
                      </div>
                    ) : null}

                    <div className="mt-auto grid grid-cols-1 gap-2 sm:grid-cols-2">
                      <Button
                        size="sm"
                        className="h-9 gap-1.5"
                        disabled={!aiDraftCanApply || createAiDraftMutation.isPending}
                        onClick={() => handleCreateAiDraft(false)}
                      >
                        {createAiDraftMutation.isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                        Создать пайплайн
                      </Button>
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-9 gap-1.5"
                        disabled={!aiDraftCanApply || createAiDraftMutation.isPending}
                        onClick={() => handleCreateAiDraft(true)}
                      >
                        <Route className="h-3.5 w-3.5" />
                        Открыть canvas
                      </Button>
                    </div>
                  </div>
                ) : (
                  <div className="flex h-full min-h-[260px] flex-col justify-between gap-4">
                    <div>
                      <div className="flex h-10 w-10 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
                        <MessageSquare className="h-5 w-5 text-primary" />
                      </div>
                      <h3 className="mt-3 text-sm font-semibold text-foreground">Черновик появится здесь</h3>
                      <p className="mt-1 text-xs leading-5 text-muted-foreground">
                        После генерации здесь будет статус проверки, список нод, предупреждения и действия сохранения.
                      </p>
                    </div>
                    <div className="grid grid-cols-2 gap-2">
                      {stats.slice(0, 4).map((stat) => (
                        <div key={stat.label} className="rounded-lg border border-border/70 bg-card/70 px-3 py-2">
                          <div className="flex items-center gap-2 text-[10px] uppercase tracking-[0.08em] text-muted-foreground">
                            <stat.icon className="h-3.5 w-3.5 text-primary" />
                            {stat.label}
                          </div>
                          <div className="mt-1 text-lg font-semibold text-foreground">{stat.value}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </aside>
            </div>

            {recentFailedRuns.length ? (
              <div className="border-t border-red-500/20 bg-red-500/5 px-5 py-2 text-xs text-red-200">
                Recent failed runs: {recentFailedRuns.map((run) => `#${run.id} ${run.pipeline_name}`).join(" · ")}
              </div>
            ) : null}
          </section>
        )}

        {canPipelines && (
          <div className="flex items-center gap-4 rounded-2xl border border-border/70 bg-background/30 p-2 pl-4 backdrop-blur-md">
            <Search className="h-4 w-4 text-muted-foreground shrink-0" />
            <Input
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder="Search pipelines..."
              aria-label="Search pipelines"
              className="h-10 border-0 bg-transparent shadow-none focus-visible:ring-0 text-sm px-0"
            />
          </div>
        )}

            <div className="grid grid-cols-1 gap-4">
              <div className="min-w-0 space-y-4">
                {canPipelines ? (
                  <>
                    <section className="rounded-xl border border-border bg-card p-4">
                      <div className="mb-3 flex items-center justify-between">
                        <h2 className="text-sm font-semibold text-foreground">
                          {search ? `Results for “${search}”` : "All Pipelines"}
                        </h2>
                        {pipelines.length > 0 && (
                          <span className="text-xs text-muted-foreground">{pipelines.length}</span>
                        )}
                      </div>

                      <QueryStateBlock loading={isLoading} loadingText="Loading pipelines...">
                      {pipelines.length === 0 ? (
                        <EmptyState
                          icon={<Workflow className="h-5 w-5" />}
                          title={search ? "No matches" : "No pipelines yet"}
                          description={search ? "Try a broader query." : "Create a new pipeline to start automating tasks."}
                          actions={!search ? (
                            <Button size="sm" className="gap-1.5" onClick={() => setShowCreate(true)}>
                              <Plus className="h-3.5 w-3.5" /> New Pipeline
                            </Button>
                          ) : undefined}
                          hint={!search ? "Add a manual trigger node to run on demand, or a schedule/webhook trigger to automate." : undefined}
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
                        <h2 className="text-xl font-semibold text-foreground">Available sections</h2>
                      </div>
                      {sectionLinks.length === 0 ? (
                        <EmptyState
                          icon={<Workflow className="h-5 w-5" />}
                          title="No Studio sections available"
                          description="Grant a Studio section in Settings to open Skills, MCP, Agents, Runs, or Notifications."
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
            <DialogTitle>Choose Manual Trigger</DialogTitle>
            <DialogDescription>
              {runTarget
                ? `Pipeline "${runTarget.name}" has multiple manual entry nodes. Choose which branch to launch.`
                : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <label className="space-y-2 text-sm">
              <span className="text-muted-foreground">Manual trigger</span>
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
              onClick={() => {
                if (runTarget) {
                  navigate(`/studio/pipeline/${runTarget.id}`);
                }
              }}
            >
              Open Editor
            </Button>
            <Button
              variant="outline"
              onClick={() => {
                setRunTarget(null);
                setRunEntryNodeId("");
                setRunTriggerError("");
              }}
            >
              Cancel
            </Button>
            <Button
              onClick={() => {
                if (!runTarget) {
                  return;
                }
                if (!runEntryNodeId) {
                  setRunTriggerError("Choose a manual trigger to start the run.");
                  return;
                }
                runMutation.mutate({ pipelineId: runTarget.id, entryNodeId: runEntryNodeId });
              }}
              disabled={runMutation.isPending}
            >
              {runMutation.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              Run
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
                ? "Webhook Trigger"
                : triggerInfoTarget?.scheduleTriggers.length
                  ? "Scheduled Trigger"
                  : "Monitoring Trigger"}
            </DialogTitle>
            <DialogDescription>
              {triggerInfoTarget?.webhookTriggers.length
                ? `Pipeline "${triggerInfoTarget.pipeline.name}" is started by incoming webhook requests. You do not need to press Run first.`
                : triggerInfoTarget?.scheduleTriggers.length
                  ? `Pipeline "${triggerInfoTarget.pipeline.name}" is started by its schedule. There is nothing to launch manually.`
                  : triggerInfoTarget
                    ? `Pipeline "${triggerInfoTarget.pipeline.name}" is started by server monitoring alerts. Save the graph and let monitoring create runs when a matching issue is detected.`
                  : ""}
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            {triggerInfoTarget?.webhookTriggers.length ? (
              <div className="rounded-xl border border-border bg-muted/20 px-3 py-2 text-xs text-muted-foreground">
                Save is enough to arm the trigger. Every POST request to the webhook URL below creates a new pipeline run.
              </div>
            ) : null}

            {triggerInfoTarget?.webhookTriggers.map((trigger) => (
              <div key={trigger.id} className="space-y-2 rounded-xl border border-border bg-background/60 p-3">
                <div className="flex items-center justify-between gap-3">
                  <div>
                    <div className="text-sm font-medium text-foreground">{trigger.name || "Webhook trigger"}</div>
                    <div className="text-[11px] text-muted-foreground">Node `{trigger.node_id}`</div>
                  </div>
                  <Button size="sm" variant="outline" onClick={() => void handleCopyWebhookUrl(trigger.webhook_url)}>
                    <Copy className="mr-1.5 h-3.5 w-3.5" />
                    Copy URL
                  </Button>
                </div>
                <div className="rounded-lg border border-border bg-card px-3 py-2 text-xs text-muted-foreground break-all">
                  {toAbsoluteWebhookUrl(trigger.webhook_url)}
                </div>
              </div>
            ))}

            {triggerInfoTarget?.scheduleTriggers.map((trigger) => (
              <div key={trigger.id} className="space-y-1 rounded-xl border border-border bg-background/60 p-3">
                <div className="text-sm font-medium text-foreground">{trigger.name || "Schedule trigger"}</div>
                <div className="text-[11px] text-muted-foreground">Node `{trigger.node_id}`</div>
                <div className="text-xs text-muted-foreground">Cron: {trigger.cron_expression || "not set"}</div>
              </div>
            ))}

            {triggerInfoTarget?.monitoringTriggers.length ? (
              <div className="rounded-xl border border-amber-500/25 bg-amber-500/10 px-3 py-2 text-xs text-amber-100">
                Monitoring triggers are armed after save. A new run appears only when server monitoring opens a matching alert.
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
                  <div className="text-sm font-medium text-foreground">{trigger.name || "Monitoring trigger"}</div>
                  <div className="text-[11px] text-muted-foreground">Node `{trigger.node_id}`</div>
                  <div className="text-xs text-muted-foreground">Servers: {serverIds}</div>
                  <div className="text-xs text-muted-foreground">Severity: {severities}</div>
                  <div className="text-xs text-muted-foreground">Alert type: {alertTypes}</div>
                  <div className="text-xs text-muted-foreground">Containers: {containers}</div>
                </div>
              );
            })}
          </div>
          <DialogFooter>
            <Button
              variant="outline"
              onClick={() => {
                if (triggerInfoTarget) {
                  navigate(`/studio/pipeline/${triggerInfoTarget.pipeline.id}`);
                }
              }}
            >
              Open Editor
            </Button>
            <Button variant="outline" onClick={() => setTriggerInfoTarget(null)}>
              Close
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <Dialog open={Boolean(deleteTarget)} onOpenChange={(next) => !next && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete pipeline</DialogTitle>
            <DialogDescription>
              {deleteTarget ? `Delete "${deleteTarget.name}"? This cannot be undone.` : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              Cancel
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending && <Loader2 className="mr-1 h-4 w-4 animate-spin" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
