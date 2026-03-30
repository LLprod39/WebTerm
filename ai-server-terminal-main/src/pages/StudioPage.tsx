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
  studioTemplates,
  studioMCP,
  studioRuns,
  studioSkills,
  studioAgents,
  fetchAuthSession,
  type PipelineListItem,
  type PipelineRun,
} from "@/lib/api";
import { StudioNav } from "@/components/StudioNav";
import { hasFeatureAccess } from "@/lib/featureAccess";

type TemplateItem = {
  slug: string;
  name: string;
  description?: string;
  icon?: string;
  category?: string;
};

function formatRelativeTime(value: string): string {
  const diffMs = Date.now() - new Date(value).getTime();
  const minutes = Math.max(1, Math.floor(diffMs / 60_000));
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.floor(hours / 24)}d ago`;
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
    <div className="rounded-2xl border border-border/80 bg-card/95 p-4">
      <div className="mb-1 flex items-center gap-2 text-[11px] text-muted-foreground">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="text-xl font-semibold text-foreground">{value}</div>
      {sub && <div className="mt-1 text-[11px] text-muted-foreground">{sub}</div>}
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

  return (
    <article
      className="group cursor-pointer rounded-2xl border border-border/80 bg-card/95 p-4 transition-colors hover:border-primary/20 hover:bg-secondary/20"
      onClick={onOpen}
    >
      <div className="flex items-start gap-3">
        <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-2xl border border-border bg-secondary text-base text-foreground">
          {pipeline.icon || "W"}
        </div>

        <div className="min-w-0 flex-1">
          <div className="flex items-start gap-3">
            <div className="min-w-0 flex-1">
              <div className="flex flex-wrap items-center gap-2">
                <h3 className="text-sm font-semibold text-foreground">{pipeline.name}</h3>
                <Badge variant="secondary" className="px-2 py-0.5">
                  {pipeline.node_count} nodes
                </Badge>
                {pipeline.last_run && <RunStatusBadge status={pipeline.last_run.status} />}
              </div>
              <p className="mt-2 text-xs leading-relaxed text-muted-foreground">
                {pipeline.description || "Pipeline without description. Open the editor to configure the workflow."}
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

          <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
            <div className="flex flex-wrap items-center gap-2 text-[11px] text-muted-foreground">
              <span className="rounded-xl border border-border bg-background/60 px-2.5 py-1">
                Updated {formatRelativeTime(pipeline.updated_at)}
              </span>
              {tags.map((tag) => (
                <span
                  key={tag}
                  className="rounded-xl border border-border/70 px-2.5 py-1 text-[11px]"
                >
                  {tag}
                </span>
              ))}
            </div>

            <div className="flex items-center gap-2" onClick={(e) => e.stopPropagation()}>
              <Button size="sm" variant="outline" className="h-8 px-3 text-xs" onClick={onOpen}>
                Open
              </Button>
              <Button size="sm" className="h-8 gap-1.5 px-3 text-xs" onClick={onRun} disabled={running}>
                {running ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Play className="h-3.5 w-3.5" />}
                Run
              </Button>
            </div>
          </div>

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

  const { data: templatesRaw = [] } = useQuery({
    queryKey: ["studio", "templates"],
    queryFn: studioTemplates.list,
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

  const templates = useMemo(
    () => (templatesRaw as TemplateItem[]).filter((item) => Boolean(item.slug && item.name)),
    [templatesRaw],
  );

  const recentRuns = useMemo(() => {
    if (!Array.isArray(runs)) return [];
    return runs.slice(0, 5);
  }, [runs]);

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
    mutationFn: (pipelineId: number) => studioPipelines.run(pipelineId),
    onSuccess: (run) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
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

  const useTemplateMutation = useMutation({
    mutationFn: (slug: string) => studioTemplates.use(slug),
    onSuccess: (pipeline) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "pipelines"] });
      toast({ description: `Created from template "${pipeline.name}".` });
      navigate(`/studio/pipeline/${pipeline.id}`);
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  return (
    <div className="flex h-full flex-col">
      <StudioNav />

      <div className="flex-1 overflow-auto">
        <div className="w-full px-4 py-5 md:px-6 xl:px-8">
          <div className="w-full space-y-6">
            <section className="rounded-[28px] border border-border/80 bg-card/95 p-5 md:p-6">
              <div className="flex flex-col gap-4 xl:flex-row xl:items-end xl:justify-between">
                <div className="max-w-3xl space-y-2">
                  <Badge variant="secondary" className="px-3">
                    Studio workspace
                  </Badge>
                  <div>
                    <h1 className="text-2xl font-semibold tracking-tight text-foreground">
                      {canPipelines ? "Pipeline Workspace" : "Studio Access"}
                    </h1>
                    <p className="mt-1 max-w-2xl text-sm leading-relaxed text-muted-foreground">
                      {canPipelines
                        ? "Build, run, and monitor automations from one place with a layout that stays stable on large screens."
                        : "Your Studio rights are now section-based. Open only the areas granted to this account."}
                    </p>
                  </div>
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
                          className="h-10 rounded-xl border-border bg-background/75 pl-9 text-sm"
                        />
                      </div>
                      <Button size="sm" className="h-10 gap-1.5 px-4 text-sm" onClick={() => setShowCreate(true)}>
                        <Plus className="h-4 w-4" /> New Pipeline
                      </Button>
                    </>
                  ) : (
                    sectionLinks.slice(0, 2).map((item) => (
                      <Button key={item.path} size="sm" variant="outline" className="h-10 gap-1.5 px-4 text-sm" onClick={() => navigate(item.path)}>
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

            <div className="grid grid-cols-1 gap-6 2xl:grid-cols-[minmax(0,1fr)_320px] 2xl:items-start">
              <div className="min-w-0 space-y-6">
                {canPipelines ? (
                  <>
                    <section className="rounded-[24px] border border-border bg-card/85 p-4 md:p-5">
                      <div className="mb-4 flex flex-col gap-2 md:flex-row md:items-end md:justify-between">
                        <div>
                          <p className="text-[11px] font-medium text-muted-foreground">Pipelines</p>
                          <h2 className="mt-1 text-lg font-semibold text-foreground">
                            {search ? `Results for "${search}"` : "All automations"}
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
                          <p className="mt-1 text-xs text-muted-foreground">{search ? "Try a broader query." : "Create a new pipeline or use a template."}</p>
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
                              onRun={() => runMutation.mutate(pipeline.id)}
                              onClone={() => cloneMutation.mutate(pipeline.id)}
                              onDelete={() => setDeleteTarget(pipeline)}
                              running={runMutation.isPending && runMutation.variables === pipeline.id}
                              cloning={cloneMutation.isPending && cloneMutation.variables === pipeline.id}
                            />
                          ))}
                        </div>
                      )}
                    </section>

                    {!search && templates.length > 0 && (
                      <section className="space-y-3 rounded-[24px] border border-border bg-card/85 p-4 md:p-5">
                        <div className="flex items-center gap-2">
                          <Zap className="h-4 w-4 text-primary" />
                          <h3 className="text-sm font-semibold text-foreground">Quick Start Templates</h3>
                        </div>
                        <div className="grid grid-cols-1 gap-2 md:grid-cols-2 xl:grid-cols-3">
                          {templates.slice(0, 6).map((template) => (
                            <button
                              key={template.slug}
                              onClick={() => useTemplateMutation.mutate(template.slug)}
                              className="flex items-center gap-3 rounded-2xl border border-border bg-background/45 px-4 py-3 text-left transition-colors hover:border-primary/20 hover:bg-secondary/40"
                            >
                              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-2xl border border-border bg-secondary text-sm text-foreground">
                                {template.icon || "Z"}
                              </div>
                              <div className="min-w-0">
                                <p className="truncate text-xs font-medium text-foreground">{template.name}</p>
                                <p className="truncate text-[11px] text-muted-foreground">{template.description || "Template"}</p>
                              </div>
                              {template.category && (
                                <Badge variant="secondary" className="ml-auto shrink-0">
                                  {template.category}
                                </Badge>
                              )}
                            </button>
                          ))}
                        </div>
                      </section>
                    )}
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

              <aside className="space-y-4 2xl:sticky 2xl:top-4">
                <div className="space-y-2 rounded-[24px] border border-border bg-card/85 p-4">
                  <h3 className="text-sm font-medium text-foreground">Quick Access</h3>
                  {sectionLinks.map((item) => (
                    <button
                      key={item.path}
                      onClick={() => navigate(item.path)}
                      className="flex w-full items-center gap-3 rounded-2xl border border-transparent px-3 py-3 text-left transition-colors hover:border-border hover:bg-secondary/40"
                    >
                      <item.icon className="h-4 w-4 shrink-0 text-primary" />
                      <div className="min-w-0">
                        <p className="text-sm font-medium text-foreground">{item.label}</p>
                        <p className="text-[11px] text-muted-foreground">{item.desc}</p>
                      </div>
                    </button>
                  ))}
                  {!sectionLinks.length ? (
                    <div className="rounded-2xl border border-dashed border-border/70 px-3 py-6 text-center text-sm text-muted-foreground">
                      No extra Studio sections are enabled yet.
                    </div>
                  ) : null}
                </div>

                {canRuns ? (
                  <div className="space-y-3 rounded-[24px] border border-border bg-card/85 p-4">
                  <div className="flex items-center justify-between">
                    <h3 className="text-sm font-medium text-foreground">Recent Runs</h3>
                    <Button size="sm" variant="ghost" className="h-7 text-[11px]" onClick={() => navigate("/studio/runs")}>
                      View all
                    </Button>
                  </div>
                  {recentRuns.length === 0 ? (
                    <p className="py-4 text-center text-sm text-muted-foreground">No runs yet</p>
                  ) : (
                    <div className="space-y-1.5">
                      {recentRuns.map((run: PipelineRun) => (
                        <div
                          key={run.id}
                          className="flex cursor-pointer items-center gap-2.5 rounded-xl border border-transparent px-2.5 py-2 transition-colors hover:border-border hover:bg-secondary/30"
                          onClick={() => navigate("/studio/runs")}
                        >
                          <RunStatusBadge status={run.status} />
                          <span className="flex-1 truncate text-sm text-foreground">{run.pipeline_name || `Run #${run.id}`}</span>
                          <span className="shrink-0 text-[11px] text-muted-foreground">
                            {run.started_at ? formatRelativeTime(run.started_at) : "—"}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}
                  </div>
                ) : null}
              </aside>
            </div>
          </div>
        </div>
      </div>

      <CreatePipelineDialog open={showCreate && canPipelines} onClose={() => setShowCreate(false)} />

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
