// @ts-nocheck
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  AlertCircle,
  Bell,
  BookOpen,
  Bot,
  CheckCircle2,
  Clock,
  Copy,
  Loader2,
  MoreHorizontal,
  Play,
  Plus,
  Search,
  Server,
  Trash2,
  Workflow,
  XCircle,
  Zap,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
  type PipelineListItem,
} from "@/lib/api";

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
      <Badge variant="default" className="gap-1 text-[10px]">
        <CheckCircle2 className="h-3 w-3" />
        Completed
      </Badge>
    );
  }

  if (normalized === "failed") {
    return (
      <Badge variant="destructive" className="gap-1 text-[10px]">
        <XCircle className="h-3 w-3" />
        Failed
      </Badge>
    );
  }

  if (normalized === "running") {
    return (
      <Badge variant="secondary" className="gap-1 text-[10px]">
        <Loader2 className="h-3 w-3 animate-spin" />
        Running
      </Badge>
    );
  }

  return (
    <Badge variant="outline" className="text-[10px]">
      {status}
    </Badge>
  );
}

function PipelineCard({
  pipeline,
  onOpen,
  onRun,
  onClone,
  onDelete,
}: {
  pipeline: PipelineListItem;
  onOpen: () => void;
  onRun: () => void;
  onClone: () => void;
  onDelete: () => void;
}) {
  return (
    <Card className="border-border/80 transition-colors hover:border-primary/40">
      <CardHeader className="space-y-3 pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-border/70 bg-background/35 text-xl">
              {pipeline.icon || "W"}
            </div>
            <div className="min-w-0">
              <CardTitle className="truncate text-base">{pipeline.name}</CardTitle>
              <CardDescription className="mt-1 line-clamp-2 text-xs">
                {pipeline.description || "No description"}
              </CardDescription>
            </div>
          </div>

          <DropdownMenu>
            <DropdownMenuTrigger asChild>
              <Button variant="ghost" size="icon" className="h-8 w-8 rounded-xl">
                <MoreHorizontal className="h-4 w-4" />
              </Button>
            </DropdownMenuTrigger>
            <DropdownMenuContent align="end">
              <DropdownMenuItem onClick={onOpen}>Open</DropdownMenuItem>
              <DropdownMenuItem onClick={onRun}>Run</DropdownMenuItem>
              <DropdownMenuItem onClick={onClone}>Clone</DropdownMenuItem>
              <DropdownMenuItem className="text-destructive" onClick={onDelete}>
                Delete
              </DropdownMenuItem>
            </DropdownMenuContent>
          </DropdownMenu>
        </div>

        <div className="flex flex-wrap items-center gap-2">
          <Badge variant="secondary" className="gap-1 text-[10px]">
            <Workflow className="h-3 w-3" />
            {pipeline.node_count} nodes
          </Badge>
          {pipeline.last_run ? (
            <RunStatusBadge status={pipeline.last_run.status} />
          ) : (
            <Badge variant="outline" className="text-[10px]">
              Never run
            </Badge>
          )}
        </div>
      </CardHeader>

      <CardContent className="space-y-4 pt-0">
        {pipeline.tags.length > 0 ? (
          <div className="flex flex-wrap gap-1.5">
            {pipeline.tags.slice(0, 4).map((tag) => (
              <Badge key={tag} variant="outline" className="text-[10px]">
                {tag}
              </Badge>
            ))}
          </div>
        ) : null}

        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>Updated {formatRelativeTime(pipeline.updated_at)}</span>
          {pipeline.last_run?.triggered_by ? <span>{pipeline.last_run.triggered_by}</span> : null}
        </div>

        <div className="flex gap-2">
          <Button size="sm" className="flex-1 gap-1.5" onClick={onOpen}>
            Open
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={onRun}>
            <Play className="h-3.5 w-3.5" />
            Run
          </Button>
          <Button size="sm" variant="outline" className="gap-1.5" onClick={onClone}>
            <Copy className="h-3.5 w-3.5" />
            Clone
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

function CreatePipelineDialog({
  open,
  onClose,
}: {
  open: boolean;
  onClose: () => void;
}) {
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
    <Dialog open={open} onOpenChange={(nextOpen) => !nextOpen && onClose()}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>New pipeline</DialogTitle>
          <DialogDescription>Create an empty workflow and open it in the editor.</DialogDescription>
        </DialogHeader>

        <div className="space-y-3 py-2">
          <div className="flex gap-2">
            <Input
              value={icon}
              onChange={(event) => setIcon(event.target.value)}
              placeholder="W"
              className="w-16 text-center"
            />
            <Input
              value={name}
              onChange={(event) => setName(event.target.value)}
              placeholder="Pipeline name"
              autoFocus
            />
          </div>
          <Input
            value={description}
            onChange={(event) => setDescription(event.target.value)}
            placeholder="Description"
          />
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={onClose}>
            Cancel
          </Button>
          <Button
            onClick={() => createMutation.mutate({ name: name.trim(), description: description.trim(), icon: icon.trim() || "W" })}
            disabled={!name.trim() || createMutation.isPending}
          >
            {createMutation.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
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

  const { data: notifications } = useQuery({
    queryKey: ["studio", "notifications"],
    queryFn: studioNotifications.get,
  });

  const templates = useMemo(
    () => (templatesRaw as TemplateItem[]).filter((item) => Boolean(item.slug && item.name)),
    [templatesRaw],
  );

  const notifConfigured = Boolean(
    notifications?.telegram_bot_token?.trim() ||
      notifications?.smtp_user?.trim() ||
      notifications?.notify_email?.trim(),
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
    <div className="space-y-6 p-6">
      <div className="flex flex-col gap-4 lg:flex-row lg:items-end lg:justify-between">
        <div className="space-y-1">
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-foreground">
            <Workflow className="h-6 w-6 text-primary" />
            Studio
          </h1>
          <p className="text-sm text-muted-foreground">
            Pipelines, agent configs, MCP sources, and execution history.
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          <Button variant="outline" className="gap-1.5" onClick={() => navigate("/studio/runs")}>
            <Clock className="h-4 w-4" />
            Runs
          </Button>
          <Button variant="outline" className="gap-1.5" onClick={() => navigate("/studio/agents")}>
            <Bot className="h-4 w-4" />
            Agents
          </Button>
          <Button variant="outline" className="gap-1.5" onClick={() => navigate("/studio/skills")}>
            <BookOpen className="h-4 w-4" />
            Skills
          </Button>
          <Button variant="outline" className="gap-1.5" onClick={() => navigate("/studio/mcp")}>
            <Server className="h-4 w-4" />
            MCP
          </Button>
          <Button
            variant={notifConfigured ? "outline" : "destructive"}
            className="gap-1.5"
            onClick={() => navigate("/studio/notifications")}
          >
            {notifConfigured ? <Bell className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
            Notifications
          </Button>
          <Button className="gap-1.5" onClick={() => setShowCreate(true)}>
            <Plus className="h-4 w-4" />
            New pipeline
          </Button>
        </div>
      </div>

      <div className="space-y-6">
        <Card className="border-border/80">
          <CardHeader className="gap-3 sm:flex-row sm:items-end sm:justify-between">
            <div>
              <CardTitle>{search ? "Search results" : "Pipelines"}</CardTitle>
              <CardDescription>
                {search
                  ? `Results for "${search}".`
                  : "Open, run, duplicate, or remove pipelines from one place."}
              </CardDescription>
            </div>
            <div className="relative w-full sm:w-72">
              <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
              <Input
                value={search}
                onChange={(event) => setSearch(event.target.value)}
                placeholder="Search pipelines"
                className="pl-9"
              />
            </div>
          </CardHeader>

          <CardContent>
            {isLoading ? (
              <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Loading pipelines...
              </div>
            ) : pipelines.length === 0 ? (
              <div className="flex h-48 flex-col items-center justify-center rounded-2xl border border-dashed border-border text-center">
                <Workflow className="mb-3 h-10 w-10 text-muted-foreground/50" />
                <p className="text-sm font-medium text-foreground">
                  {search ? "Nothing matched this search." : "No pipelines yet."}
                </p>
                <p className="mt-1 text-xs text-muted-foreground">
                  {search ? "Try a broader query." : "Create a new pipeline or start from a template."}
                </p>
                {!search ? (
                  <Button className="mt-4 gap-1.5" size="sm" onClick={() => setShowCreate(true)}>
                    <Plus className="h-4 w-4" />
                    New pipeline
                  </Button>
                ) : null}
              </div>
            ) : (
              <div className="grid gap-4 md:grid-cols-2 2xl:grid-cols-3">
                {pipelines.map((pipeline) => (
                  <PipelineCard
                    key={pipeline.id}
                    pipeline={pipeline}
                    onOpen={() => navigate(`/studio/pipeline/${pipeline.id}`)}
                    onRun={() => runMutation.mutate(pipeline.id)}
                    onClone={() => cloneMutation.mutate(pipeline.id)}
                    onDelete={() => setDeleteTarget(pipeline)}
                  />
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        {!search && templates.length > 0 ? (
          <Card className="border-border/80">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <Zap className="h-5 w-5 text-primary" />
                Templates
              </CardTitle>
              <CardDescription>Use a starter pipeline and open it immediately.</CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              {templates.slice(0, 6).map((template) => (
                <button
                  key={template.slug}
                  type="button"
                  onClick={() => useTemplateMutation.mutate(template.slug)}
                  className="rounded-2xl border border-border/80 bg-background/30 p-4 text-left transition-colors hover:border-primary/40 hover:bg-background/45"
                >
                  <div className="mb-3 flex items-center justify-between gap-3">
                    <div className="flex h-10 w-10 items-center justify-center rounded-2xl border border-border/70 bg-background/40 text-xl">
                      {template.icon || "Z"}
                    </div>
                    {template.category ? (
                      <Badge variant="secondary" className="text-[10px]">
                        {template.category}
                      </Badge>
                    ) : null}
                  </div>
                  <div className="space-y-1">
                    <p className="text-sm font-medium text-foreground">{template.name}</p>
                    <p className="text-xs leading-5 text-muted-foreground">
                      {template.description || "Template without description"}
                    </p>
                  </div>
                </button>
              ))}
            </CardContent>
          </Card>
        ) : null}
      </div>

      <CreatePipelineDialog open={showCreate} onClose={() => setShowCreate(false)} />

      <Dialog open={Boolean(deleteTarget)} onOpenChange={(nextOpen) => !nextOpen && setDeleteTarget(null)}>
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
              {deleteMutation.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : <Trash2 className="mr-1 h-4 w-4" />}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
  );
}
