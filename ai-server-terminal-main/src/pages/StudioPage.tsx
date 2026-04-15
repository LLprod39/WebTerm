import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2,
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
import { Badge } from "@/components/ui/badge";
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
} from "@/lib/api";
import { StudioNav } from "@/components/StudioNav";
import { hasFeatureAccess } from "@/lib/featureAccess";
import { getPipelineActivityState } from "@/components/pipeline/pipelineActivity";

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
      <span className="inline-flex items-center gap-1 text-[11px] text-primary">
        <CheckCircle2 className="h-3 w-3" /> Completed
      </span>
    );
  }
  if (normalized === "failed") {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-destructive">
        <XCircle className="h-3 w-3" /> Failed
      </span>
    );
  }
  if (normalized === "running") {
    return (
      <span className="inline-flex items-center gap-1 text-[11px] text-primary">
        <Loader2 className="h-3 w-3 animate-spin" /> Running
      </span>
    );
  }
  return <span className="text-[11px] text-muted-foreground">{status}</span>;
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
    <div className="rounded-lg border border-border bg-card p-4">
      <div className="mb-2 flex items-center gap-2 text-xs text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="text-2xl font-semibold text-foreground">{value}</div>
      {sub && <div className="mt-1 text-xs text-muted-foreground">{sub}</div>}
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
  const activityToneClass = "border-border bg-secondary/30 text-foreground";
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
              : Zap;

  return (
    <article
      className="group cursor-pointer rounded-lg border border-border bg-card p-4 transition-colors hover:border-primary/50 hover:bg-secondary/20"
      onClick={onOpen}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-border bg-secondary text-sm font-semibold text-foreground">
          {pipeline.icon || "W"}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start justify-between">
            <div className="min-w-0 flex-1">
              <div className="flex items-center gap-2">
                <h3 className="text-sm font-semibold text-foreground">{pipeline.name}</h3>
                {pipeline.last_run && <RunStatusBadge status={pipeline.last_run.status} />}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">
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

          <div className="mt-4 flex items-center justify-between gap-3">
            <span className="text-xs text-muted-foreground">
              Updated {formatRelativeTime(pipeline.updated_at)}
            </span>

            <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
              <Button size="sm" className="h-8 gap-1.5 px-3 text-xs" onClick={onRun} disabled={running}>
                {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                Run
              </Button>
            </div>
          </div>

          {cloning && <p className="mt-2 text-xs text-primary">Creating a copy...</p>}
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

  return (
    <div className="flex h-full flex-col">
      <StudioNav />

      <div className="flex-1 overflow-auto">
        <div className="w-full px-4 py-5 md:px-6 xl:px-8">
          <div className="w-full space-y-6">
            <section className="rounded-lg border border-border bg-card p-6">
              <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
                <div className="max-w-3xl space-y-1">
                  <h1 className="text-2xl font-semibold text-foreground">
                    {canPipelines ? "Pipelines" : "Studio"}
                  </h1>
                  <p className="text-sm text-muted-foreground">
                    {canPipelines
                      ? "Build, run, and monitor automations"
                      : "Access your Studio sections"}
                  </p>
                </div>

                <div className="flex w-full flex-col gap-2 sm:flex-row xl:w-auto">
                  {canPipelines ? (
                    <>
                      <div className="relative min-w-0 sm:flex-1 xl:w-72">
                        <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
                        <Input
                          value={search}
                          onChange={(e) => setSearch(e.target.value)}
                          placeholder="Search pipelines..."
                          aria-label="Search pipelines"
                          className="h-10 rounded-lg border-border bg-background pl-9"
                        />
                      </div>
                      <Button className="h-10 gap-1.5 px-4" onClick={() => setShowCreate(true)}>
                        <Plus className="h-4 w-4" /> New Pipeline
                      </Button>
                    </>
                  ) : (
                    sectionLinks.slice(0, 2).map((item) => (
                      <Button key={item.path} variant="outline" className="h-10 gap-1.5 px-4" onClick={() => navigate(item.path)}>
                        <item.icon className="h-4 w-4" />
                        {item.label}
                      </Button>
                    ))
                  )}
                </div>
              </div>
            </section>

            {stats.length > 0 ? (
              <div className="grid grid-cols-2 gap-3 lg:grid-cols-3 2xl:grid-cols-6">
                {stats.map((stat) => (
                  <StatCard key={stat.label} icon={stat.icon} label={stat.label} value={stat.value} sub={stat.sub} />
                ))}
              </div>
            ) : null}

            <div className="grid grid-cols-1 gap-6">
              <div className="min-w-0 space-y-6">
                {canPipelines ? (
                  <>
                    <section className="rounded-lg border border-border bg-card p-5">
                      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-center md:justify-between">
                        <div>
                          <p className="text-[11px] font-medium text-muted-foreground">Pipelines</p>
                          <h2 className="mt-1 text-lg font-semibold text-foreground">
                            {search ? `Results for "${search}"` : "All Pipelines"}
                          </h2>
                        </div>
                        <p className="text-xs text-muted-foreground">
                          {pipelines.length} workflow{pipelines.length === 1 ? "" : "s"} available
                        </p>
                      </div>

                      {isLoading ? (
                        <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading...
                        </div>
                      ) : pipelines.length === 0 ? (
                        <div className="workspace-empty border-dashed p-10 text-center">
                          <Workflow className="mx-auto mb-3 h-10 w-10 text-muted-foreground/30" />
                          <p className="text-sm font-medium text-foreground">{search ? "No matches" : "No pipelines yet"}</p>
                          <p className="mt-1 text-xs text-muted-foreground">{search ? "Try a broader query." : "Create a new pipeline to start automating tasks."}</p>
                          {!search && (
                            <Button size="sm" className="mt-4 gap-1.5" onClick={() => setShowCreate(true)}>
                              <Plus className="h-3.5 w-3.5" /> New Pipeline
                            </Button>
                          )}
                        </div>
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
                    </section>
                  </>
                ) : (
                  <section className="rounded-[24px] border border-border bg-card/85 p-5">
                    <div className="space-y-3">
                      <div>
                        <p className="text-[11px] font-medium text-muted-foreground">Studio sections</p>
                        <h2 className="mt-1 text-lg font-semibold text-foreground">Available for this user</h2>
                      </div>
                      {sectionLinks.length === 0 ? (
                        <div className="workspace-empty border-dashed p-10 text-center">
                          <Workflow className="mx-auto mb-3 h-10 w-10 text-muted-foreground/30" />
                          <p className="text-sm font-medium text-foreground">No Studio sections available</p>
                          <p className="mt-1 text-xs text-muted-foreground">Grant a Studio section in Settings to open Skills, MCP, Agents, Runs, or Notifications.</p>
                        </div>
                      ) : (
                        <div className="grid grid-cols-1 gap-3 xl:grid-cols-2">
                          {sectionLinks.map((item) => (
                            <button
                              key={item.path}
                              type="button"
                              onClick={() => navigate(item.path)}
                              className="flex items-start gap-3 rounded-2xl border border-border bg-background/45 px-4 py-4 text-left transition-colors hover:border-primary/20 hover:bg-secondary/30"
                            >
                              <item.icon className="mt-0.5 h-4 w-4 shrink-0 text-primary" />
                              <div>
                                <div className="text-sm font-medium text-foreground">{item.label}</div>
                                <div className="mt-1 text-xs leading-5 text-muted-foreground">{item.desc}</div>
                              </div>
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
