// @ts-nocheck
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
  studioNotifications,
  studioPipelines,
  studioTemplates,
  studioMCP,
  studioRuns,
  studioSkills,
  studioAgents,
  type PipelineListItem,
} from "@/lib/api";
import { StudioNav } from "@/components/StudioNav";

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
      <span className="inline-flex items-center gap-1 text-[10px] text-primary">
        <CheckCircle2 className="h-3 w-3" /> Completed
      </span>
    );
  }
  if (normalized === "failed") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-destructive">
        <XCircle className="h-3 w-3" /> Failed
      </span>
    );
  }
  if (normalized === "running") {
    return (
      <span className="inline-flex items-center gap-1 text-[10px] text-primary">
        <Loader2 className="h-3 w-3 animate-spin" /> Running
      </span>
    );
  }
  return <span className="text-[10px] text-muted-foreground">{status}</span>;
}

function StatCard({ icon: Icon, label, value, sub }: { icon: React.ElementType; label: string; value: string | number; sub?: string }) {
  return (
    <div className="bg-card border border-border rounded-lg p-4">
      <div className="flex items-center gap-2 text-xs text-muted-foreground mb-1">
        <Icon className="h-3.5 w-3.5" />
        {label}
      </div>
      <div className="text-xl font-semibold text-foreground">{value}</div>
      {sub && <div className="text-[10px] text-muted-foreground mt-0.5">{sub}</div>}
    </div>
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
      setName(""); setDescription(""); setIcon("W");
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
            <Input value={icon} onChange={(e) => setIcon(e.target.value)} placeholder="W" className="w-16 text-center" />
            <Input value={name} onChange={(e) => setName(e.target.value)} placeholder="Pipeline name" autoFocus />
          </div>
          <Input value={description} onChange={(e) => setDescription(e.target.value)} placeholder="Description" />
        </div>
        <DialogFooter>
          <Button variant="outline" onClick={onClose}>Cancel</Button>
          <Button onClick={() => createMutation.mutate({ name: name.trim(), description: description.trim(), icon: icon.trim() || "W" })} disabled={!name.trim() || createMutation.isPending}>
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

  const { data: pipelines = [], isLoading } = useQuery({
    queryKey: ["studio", "pipelines", search],
    queryFn: () => studioPipelines.list(search || undefined),
  });

  const { data: templatesRaw = [] } = useQuery({
    queryKey: ["studio", "templates"],
    queryFn: studioTemplates.list,
  });

  const { data: mcpList = [] } = useQuery({
    queryKey: ["studio", "mcp"],
    queryFn: studioMCP.list,
  });

  const { data: skills = [] } = useQuery({
    queryKey: ["studio", "skills"],
    queryFn: studioSkills.list,
  });

  const { data: agents = [] } = useQuery({
    queryKey: ["studio", "agents"],
    queryFn: studioAgents.list,
  });

  const { data: runs = [] } = useQuery({
    queryKey: ["studio", "runs"],
    queryFn: () => studioRuns.list(),
  });

  const templates = useMemo(
    () => (templatesRaw as TemplateItem[]).filter((item) => Boolean(item.slug && item.name)),
    [templatesRaw],
  );

  const recentRuns = useMemo(() => {
    if (!Array.isArray(runs)) return [];
    return runs.slice(0, 5);
  }, [runs]);

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

  const completedRuns = Array.isArray(runs) ? runs.filter((r: any) => r.status === "completed").length : 0;
  const failedRuns = Array.isArray(runs) ? runs.filter((r: any) => r.status === "failed").length : 0;

  return (
    <div className="flex flex-col h-full">
      <StudioNav />

      <div className="flex-1 overflow-auto">
        <div className="p-5 max-w-7xl mx-auto space-y-5">
          {/* Stats row */}
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-3">
            <StatCard icon={Workflow} label="Pipelines" value={pipelines.length} />
            <StatCard icon={BookOpen} label="Skills" value={Array.isArray(skills) ? skills.length : 0} />
            <StatCard icon={Server} label="MCP Servers" value={Array.isArray(mcpList) ? mcpList.length : 0} />
            <StatCard icon={Bot} label="Agents" value={Array.isArray(agents) ? agents.length : 0} />
            <StatCard icon={CheckCircle2} label="Completed" value={completedRuns} sub="runs" />
            <StatCard icon={XCircle} label="Failed" value={failedRuns} sub="runs" />
          </div>

          <div className="grid grid-cols-1 xl:grid-cols-[1fr_340px] gap-5">
            {/* Left: Pipelines */}
            <div className="space-y-4">
              {/* Pipeline header */}
              <div className="flex items-center justify-between gap-3">
                <h2 className="text-sm font-semibold text-foreground">Pipelines</h2>
                <div className="flex gap-2">
                  <div className="relative">
                    <Search className="absolute left-2.5 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-muted-foreground" />
                    <Input
                      value={search}
                      onChange={(e) => setSearch(e.target.value)}
                      placeholder="Search..."
                      className="pl-8 h-8 w-44 bg-card border-border text-xs"
                    />
                  </div>
                  <Button size="sm" className="gap-1.5 h-8 text-xs" onClick={() => setShowCreate(true)}>
                    <Plus className="h-3.5 w-3.5" /> New
                  </Button>
                </div>
              </div>

              {/* Pipeline list */}
              {isLoading ? (
                <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Loading...
                </div>
              ) : pipelines.length === 0 ? (
                <div className="border border-dashed border-border rounded-lg p-10 text-center">
                  <Workflow className="h-10 w-10 mx-auto mb-3 text-muted-foreground/30" />
                  <p className="text-sm font-medium text-foreground">{search ? "No matches" : "No pipelines yet"}</p>
                  <p className="text-xs text-muted-foreground mt-1">{search ? "Try a broader query." : "Create a new pipeline or use a template."}</p>
                  {!search && (
                    <Button size="sm" className="mt-4 gap-1.5" onClick={() => setShowCreate(true)}>
                      <Plus className="h-3.5 w-3.5" /> New Pipeline
                    </Button>
                  )}
                </div>
              ) : (
                <div className="space-y-2">
                  {pipelines.map((pipeline) => (
                    <div
                      key={pipeline.id}
                      className="flex items-center gap-4 px-4 py-3 rounded-lg border border-border bg-card hover:bg-secondary/30 transition-colors cursor-pointer"
                      onClick={() => navigate(`/studio/pipeline/${pipeline.id}`)}
                    >
                      <div className="h-9 w-9 rounded-lg bg-primary/10 flex items-center justify-center text-base shrink-0">
                        {pipeline.icon || "W"}
                      </div>
                      <div className="flex-1 min-w-0">
                        <div className="flex items-center gap-2">
                          <p className="text-sm font-medium text-foreground truncate">{pipeline.name}</p>
                          <span className="text-[10px] text-muted-foreground bg-secondary rounded px-1.5 py-0.5 shrink-0">
                            {pipeline.node_count} nodes
                          </span>
                        </div>
                        <p className="text-xs text-muted-foreground truncate mt-0.5">
                          {pipeline.description || "No description"} · Updated {formatRelativeTime(pipeline.updated_at)}
                        </p>
                      </div>
                      <div className="flex items-center gap-2 shrink-0">
                        {pipeline.last_run && <RunStatusBadge status={pipeline.last_run.status} />}
                        <div className="flex gap-1" onClick={(e) => e.stopPropagation()}>
                          <Button size="sm" variant="outline" className="h-7 px-2 text-xs gap-1" onClick={() => runMutation.mutate(pipeline.id)}>
                            <Play className="h-3 w-3" /> Run
                          </Button>
                          <DropdownMenu>
                            <DropdownMenuTrigger asChild>
                              <Button variant="ghost" size="sm" className="h-7 w-7 p-0">
                                <MoreHorizontal className="h-3.5 w-3.5" />
                              </Button>
                            </DropdownMenuTrigger>
                            <DropdownMenuContent align="end">
                              <DropdownMenuItem onClick={() => navigate(`/studio/pipeline/${pipeline.id}`)}>Open Editor</DropdownMenuItem>
                              <DropdownMenuItem onClick={() => cloneMutation.mutate(pipeline.id)}>
                                <Copy className="h-3.5 w-3.5 mr-1.5" /> Clone
                              </DropdownMenuItem>
                              <DropdownMenuItem className="text-destructive" onClick={() => setDeleteTarget(pipeline)}>
                                <Trash2 className="h-3.5 w-3.5 mr-1.5" /> Delete
                              </DropdownMenuItem>
                            </DropdownMenuContent>
                          </DropdownMenu>
                        </div>
                      </div>
                    </div>
                  ))}
                </div>
              )}

              {/* Templates */}
              {!search && templates.length > 0 && (
                <div className="space-y-3">
                  <div className="flex items-center gap-2">
                    <Zap className="h-4 w-4 text-primary" />
                    <h3 className="text-sm font-semibold text-foreground">Quick Start Templates</h3>
                  </div>
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
                    {templates.slice(0, 6).map((template) => (
                      <button
                        key={template.slug}
                        onClick={() => useTemplateMutation.mutate(template.slug)}
                        className="flex items-center gap-3 px-4 py-3 rounded-lg border border-border bg-card hover:border-primary/40 hover:bg-primary/5 transition-colors text-left"
                      >
                        <div className="h-8 w-8 rounded-lg bg-secondary flex items-center justify-center text-sm shrink-0">
                          {template.icon || "Z"}
                        </div>
                        <div className="min-w-0">
                          <p className="text-xs font-medium text-foreground truncate">{template.name}</p>
                          <p className="text-[10px] text-muted-foreground truncate">{template.description || "Template"}</p>
                        </div>
                        {template.category && (
                          <Badge variant="secondary" className="text-[9px] ml-auto shrink-0">{template.category}</Badge>
                        )}
                      </button>
                    ))}
                  </div>
                </div>
              )}
            </div>

            {/* Right sidebar: Recent runs + quick links */}
            <div className="space-y-4">
              {/* Quick navigation */}
              <div className="bg-card border border-border rounded-lg p-4 space-y-2">
                <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Quick Access</h3>
                {[
                  { label: "Skill Catalog", desc: "Manage playbooks & guardrails", icon: BookOpen, path: "/studio/skills" },
                  { label: "MCP Registry", desc: "Model Context Protocol servers", icon: Server, path: "/studio/mcp" },
                  { label: "Agent Configs", desc: "Configure AI agents", icon: Bot, path: "/studio/agents" },
                  { label: "Execution History", desc: "All pipeline runs", icon: Clock, path: "/studio/runs" },
                ].map((item) => (
                  <button
                    key={item.path}
                    onClick={() => navigate(item.path)}
                    className="w-full flex items-center gap-3 px-3 py-2.5 rounded-lg hover:bg-secondary/50 transition-colors text-left"
                  >
                    <item.icon className="h-4 w-4 text-primary shrink-0" />
                    <div className="min-w-0">
                      <p className="text-xs font-medium text-foreground">{item.label}</p>
                      <p className="text-[10px] text-muted-foreground">{item.desc}</p>
                    </div>
                  </button>
                ))}
              </div>

              {/* Recent runs */}
              <div className="bg-card border border-border rounded-lg p-4 space-y-3">
                <div className="flex items-center justify-between">
                  <h3 className="text-xs font-medium text-muted-foreground uppercase tracking-wider">Recent Runs</h3>
                  <Button size="sm" variant="ghost" className="h-6 text-[10px] text-primary" onClick={() => navigate("/studio/runs")}>
                    View all
                  </Button>
                </div>
                {recentRuns.length === 0 ? (
                  <p className="text-xs text-muted-foreground text-center py-4">No runs yet</p>
                ) : (
                  <div className="space-y-1.5">
                    {recentRuns.map((run: any) => (
                      <div
                        key={run.id}
                        className="flex items-center gap-2.5 px-2.5 py-2 rounded-md hover:bg-secondary/30 transition-colors cursor-pointer"
                        onClick={() => navigate("/studio/runs")}
                      >
                        <RunStatusBadge status={run.status} />
                        <span className="text-xs text-foreground truncate flex-1">{run.pipeline_name || `Run #${run.id}`}</span>
                        <span className="text-[10px] text-muted-foreground shrink-0">
                          {run.started_at ? formatRelativeTime(run.started_at) : "—"}
                        </span>
                      </div>
                    ))}
                  </div>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      <CreatePipelineDialog open={showCreate} onClose={() => setShowCreate(false)} />

      <Dialog open={Boolean(deleteTarget)} onOpenChange={(next) => !next && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete pipeline</DialogTitle>
            <DialogDescription>
              {deleteTarget ? `Delete "${deleteTarget.name}"? This cannot be undone.` : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>Cancel</Button>
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
