import { StudioNav } from "@/components/StudioNav";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
  Save,
  Server,
  Trash2,
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
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { EmptyState, PageShell, SectionCard, StatusBadge } from "@/components/ui/page-shell";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { ShareAccessEditor } from "@/components/studio/ShareAccessEditor";
import { useToast } from "@/hooks/use-toast";
import { fetchAuthSession, studioMCP, studioShareUsers, type MCPServer, type MCPTemplate } from "@/lib/api";

function previewConnection(server: Pick<MCPServer, "transport" | "command" | "args" | "url">) {
  if (server.transport === "stdio") {
    return [server.command, ...(server.args || [])].filter(Boolean).join(" ");
  }

  return server.url || "https://...";
}

function MCPForm({
  initial,
  onSave,
  onCancel,
  isPending,
  shareUsers,
  isAdmin,
  canEdit,
}: {
  initial: Partial<MCPServer>;
  onSave: (data: Partial<MCPServer>) => void;
  onCancel: () => void;
  isPending: boolean;
  shareUsers: Array<{ id: number; username: string; email?: string }>;
  isAdmin: boolean;
  canEdit: boolean;
}) {
  const [form, setForm] = useState<Partial<MCPServer>>({
    name: "",
    description: "",
    transport: "stdio",
    command: "",
    args: [],
    env: {},
    url: "",
    is_shared: false,
    shared_user_ids: [],
    ...initial,
  });
  const readOnly = !canEdit;
  const [argsText, setArgsText] = useState((initial.args || []).join("\n"));
  const [envText, setEnvText] = useState(
    Object.entries(initial.env || {})
      .map(([key, value]) => `${key}=${value}`)
      .join("\n"),
  );

  const setField = (key: keyof MCPServer, value: unknown) => {
    setForm((current) => ({ ...current, [key]: value }));
  };
  const sharedUserIds = form.shared_user_ids || [];

  const handleSave = () => {
    const args = argsText
      .split("\n")
      .map((item) => item.trim())
      .filter(Boolean);
    const env: Record<string, string> = {};

    for (const line of envText.split("\n").map((item) => item.trim()).filter(Boolean)) {
      const separatorIndex = line.indexOf("=");
      if (separatorIndex > 0) {
        env[line.slice(0, separatorIndex)] = line.slice(separatorIndex + 1);
      }
    }

    onSave({ ...form, args, env });
  };

  return (
    <div className="space-y-4">
      <div className="flex gap-3">
        <div className="flex-1 space-y-1.5">
          <Label className="text-xs">Name</Label>
          <Input
            value={form.name || ""}
            onChange={(event) => setField("name", event.target.value)}
            placeholder="GitHub MCP"
            disabled={readOnly}
          />
        </div>
        <div className="w-36 space-y-1.5">
          <Label className="text-xs">Transport</Label>
          <Select
            value={form.transport || "stdio"}
            onValueChange={(value) => setField("transport", value)}
          >
            <SelectTrigger className="h-9 text-sm" disabled={readOnly}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="stdio">stdio</SelectItem>
              <SelectItem value="sse">SSE</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </div>

      <div className="space-y-1.5">
        <Label className="text-xs">Description</Label>
        <Input
          value={form.description || ""}
          onChange={(event) => setField("description", event.target.value)}
          placeholder="What this MCP provides"
          disabled={readOnly}
        />
      </div>

      {form.transport === "stdio" ? (
        <>
          <div className="space-y-1.5">
            <Label className="text-xs">Command</Label>
            <Input
              value={form.command || ""}
              onChange={(event) => setField("command", event.target.value)}
              placeholder="npx"
              className="font-mono text-sm"
              disabled={readOnly}
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Arguments (one per line)</Label>
            <Textarea
              value={argsText}
              onChange={(event) => setArgsText(event.target.value)}
              placeholder="-y&#10;@modelcontextprotocol/server-github"
              rows={5}
              className="font-mono text-xs"
              disabled={readOnly}
            />
          </div>

          <div className="space-y-1.5">
            <Label className="text-xs">Environment variables (KEY=value)</Label>
            <Textarea
              value={envText}
              onChange={(event) => setEnvText(event.target.value)}
              placeholder="GITHUB_PERSONAL_ACCESS_TOKEN=..."
              rows={4}
              className="font-mono text-xs"
              disabled={readOnly}
            />
          </div>
        </>
      ) : (
        <div className="space-y-1.5">
          <Label className="text-xs">SSE URL</Label>
          <Input
            value={form.url || ""}
            onChange={(event) => setField("url", event.target.value)}
            placeholder="https://mcp.example.com/sse"
            className="font-mono text-sm"
            disabled={readOnly}
          />
        </div>
      )}

      {isAdmin ? (
        <ShareAccessEditor
          title="Visibility"
          description="Admin can expose this MCP server to everyone or only selected users."
          isShared={Boolean(form.is_shared)}
          sharedUserIds={sharedUserIds}
          users={shareUsers}
          disabled={readOnly}
          onSharedChange={(value) => setField("is_shared", value)}
          onToggleUser={(userId) =>
            setField(
              "shared_user_ids",
              sharedUserIds.includes(userId)
                ? sharedUserIds.filter((id) => id !== userId)
                : [...sharedUserIds, userId],
            )
          }
        />
      ) : null}

      <div className="rounded-2xl border border-border/70 bg-background/30 px-4 py-3 text-sm text-muted-foreground">
        Templates are the fastest way to start. After loading one, you can still edit the command,
        args, URL, or environment variables before saving.
      </div>

      <div className="flex justify-end gap-2 pt-2">
        <Button variant="outline" size="sm" onClick={onCancel}>
          Cancel
        </Button>
        <Button
          size="sm"
          onClick={handleSave}
          disabled={readOnly || !form.name?.trim() || isPending}
          className="gap-1.5"
        >
          {isPending ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Save className="h-3.5 w-3.5" />}
          Save
        </Button>
      </div>
    </div>
  );
}

export default function MCPHubPage() {
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [editorOpen, setEditorOpen] = useState(false);
  const [editMcp, setEditMcp] = useState<Partial<MCPServer> | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<MCPServer | null>(null);
  const [testingId, setTestingId] = useState<number | null>(null);

  const { data: session } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const isAdmin = Boolean(session?.user?.is_staff);

  const { data: mcpList = [], isLoading } = useQuery({
    queryKey: ["studio", "mcp"],
    queryFn: studioMCP.list,
  });

  const { data: shareUsers = [] } = useQuery({
    queryKey: ["studio", "share-users"],
    queryFn: studioShareUsers.list,
    enabled: isAdmin,
  });

  const { data: templates = [] } = useQuery({
    queryKey: ["studio", "mcp", "templates"],
    queryFn: studioMCP.templates,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Partial<MCPServer>) => studioMCP.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studio", "mcp"] });
      setEditorOpen(false);
      setEditMcp(null);
      toast({ description: "MCP server added." });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<MCPServer> }) =>
      studioMCP.update(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studio", "mcp"] });
      setEditorOpen(false);
      setEditMcp(null);
      toast({ description: "MCP server updated." });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => studioMCP.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studio", "mcp"] });
      setDeleteTarget(null);
      toast({ description: "MCP server removed." });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const testMutation = useMutation({
    mutationFn: (id: number) => studioMCP.test(id),
    onSuccess: (result) => {
      queryClient.invalidateQueries({ queryKey: ["studio", "mcp"] });
      setTestingId(null);
      if (result.ok) {
        toast({ description: "Connection OK." });
      } else {
        toast({
          variant: "destructive",
          description: result.error || "Connection test failed.",
        });
      }
    },
    onError: (error: Error) => {
      setTestingId(null);
      toast({ variant: "destructive", description: error.message });
    },
  });

  const handleSave = (payload: Partial<MCPServer>) => {
    const editingMcp = editMcp as MCPServer | null;
    if (editingMcp?.id) {
      if (editingMcp.can_edit === false) return;
      updateMutation.mutate({
        id: editingMcp.id,
        payload,
      });
      return;
    }

    createMutation.mutate(payload);
  };

  const openCreateDialog = () => {
    setEditMcp({});
    setEditorOpen(true);
  };

  const openEditDialog = (mcp: Partial<MCPServer>) => {
    setEditMcp(mcp);
    setEditorOpen(true);
  };

  const handleUseTemplate = (template: MCPTemplate) => {
    openEditDialog({
      name: template.name,
      description: template.description,
      transport: template.transport,
      command: template.command || "",
      args: template.args || [],
      env: template.env || {},
      url: template.url || "",
    });
  };

  return (
    <div className="flex flex-col h-full">
      <StudioNav />
      <div className="flex-1 overflow-auto">
      <PageShell width="full">
      <SectionCard
        title="MCP Hub"
        description="Manage Model Context Protocol servers used by Studio."
        icon={<Server className="h-5 w-5" />}
        actions={
            <Button type="button" className="gap-1.5" onClick={openCreateDialog}>
              <Plus className="h-4 w-4" />
              Add server
            </Button>
        }
      >
        <Tabs defaultValue="mine" className="space-y-5">
          <TabsList>
            <TabsTrigger value="mine">My servers ({mcpList.length})</TabsTrigger>
            <TabsTrigger value="templates">Templates ({templates.length})</TabsTrigger>
          </TabsList>

          <TabsContent value="mine" className="space-y-4">
            {isLoading ? (
              <div className="flex h-40 items-center justify-center text-sm text-muted-foreground">
                <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                Loading MCP servers...
              </div>
            ) : mcpList.length === 0 ? (
                <EmptyState
                  icon={<Server className="h-5 w-5" />}
                  title="No MCP servers yet"
                  description="Add a custom server or start from one of the templates."
                  actions={
                    <Button type="button" className="gap-1.5" onClick={openCreateDialog}>
                      <Plus className="h-4 w-4" />
                      Add server
                    </Button>
                  }
                />
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {mcpList.map((mcp) => {
                  const tone =
                    mcp.last_test_ok === true
                      ? "success"
                      : mcp.last_test_ok === false
                        ? "danger"
                        : "neutral";

                  return (
                    <Card key={mcp.id} className="border-border/80">
                      <CardHeader className="space-y-3 pb-3">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0">
                            <CardTitle className="flex items-center gap-2 text-base">
                              <span className="truncate">{mcp.name}</span>
                              <Badge variant="secondary" className="text-[10px] font-mono">
                                {mcp.transport}
                              </Badge>
                            </CardTitle>
                            <CardDescription className="mt-1 text-xs">
                              {mcp.description || "No description"}
                            </CardDescription>
                            <div className="mt-2 flex flex-wrap gap-1.5">
                              {mcp.is_owner ? <Badge variant="secondary">Mine</Badge> : null}
                              {!mcp.is_owner && mcp.owner_username ? <Badge variant="outline">Owner: {mcp.owner_username}</Badge> : null}
                              {mcp.is_shared ? <Badge variant="outline">Shared</Badge> : null}
                              {mcp.can_edit === false ? <Badge variant="outline">Read only</Badge> : null}
                            </div>
                          </div>

                          <div className="flex gap-1">
                            {mcp.can_edit !== false ? (
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-8 w-8 rounded-xl"
                                type="button"
                                onClick={() => {
                                  setTestingId(mcp.id);
                                  testMutation.mutate(mcp.id);
                                }}
                                disabled={testingId === mcp.id}
                              >
                                {testingId === mcp.id ? (
                                  <Loader2 className="h-4 w-4 animate-spin" />
                                ) : (
                                  <RefreshCw className="h-4 w-4" />
                                )}
                              </Button>
                            ) : null}
                            <Button
                              type="button"
                              size="icon"
                              variant="ghost"
                              className="h-8 w-8 rounded-xl"
                              onClick={() => openEditDialog(mcp)}
                              title={mcp.can_edit === false ? "View server" : "Edit server"}
                            >
                              <Pencil className="h-4 w-4" />
                            </Button>
                            {mcp.can_edit !== false ? (
                              <Button
                                size="icon"
                                variant="ghost"
                                className="h-8 w-8 rounded-xl text-destructive hover:text-destructive"
                                type="button"
                                onClick={() => setDeleteTarget(mcp)}
                              >
                                <Trash2 className="h-4 w-4" />
                              </Button>
                            ) : null}
                          </div>
                        </div>
                      </CardHeader>

                      <CardContent className="space-y-4 pt-0">
                        <div className="rounded-2xl border border-border/70 bg-background/30 px-3 py-2 font-mono text-xs text-muted-foreground">
                          {previewConnection(mcp) || "No connection data"}
                        </div>

                        <div className="flex flex-wrap items-center gap-2">
                          <StatusBadge
                            label={
                              mcp.last_test_ok === true
                                ? "Healthy"
                                : mcp.last_test_ok === false
                                  ? "Failed"
                                  : "Not tested"
                            }
                            tone={tone}
                          />
                          {mcp.is_shared ? <Badge variant="outline">Shared</Badge> : null}
                        </div>

                        {mcp.last_test_error ? (
                          <p className="text-xs leading-5 text-muted-foreground">{mcp.last_test_error}</p>
                        ) : null}

                        {mcp.last_test_at ? (
                          <p className="text-xs text-muted-foreground">
                            Tested {new Date(mcp.last_test_at).toLocaleString()}
                          </p>
                        ) : null}
                      </CardContent>
                    </Card>
                  );
                })}
              </div>
            )}
          </TabsContent>

          <TabsContent value="templates" className="space-y-4">
            {templates.length === 0 ? (
              <EmptyState
                icon={<Zap className="h-5 w-5" />}
                title="No templates available"
                description="Template suggestions will appear here when the backend provides them."
              />
            ) : (
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {templates.map((template) => (
                  <Card
                    key={template.slug}
                    className="cursor-pointer border-border/80 transition-colors hover:border-primary/40"
                    onClick={() => handleUseTemplate(template)}
                  >
                    <CardHeader className="space-y-3 pb-3">
                      <div className="flex items-start justify-between gap-3">
                        <div className="flex items-start gap-3">
                          <div className="flex h-11 w-11 items-center justify-center rounded-2xl border border-border/70 bg-background/35 text-xl">
                            {template.icon || "Z"}
                          </div>
                          <div>
                            <CardTitle className="text-base">{template.name}</CardTitle>
                            <CardDescription className="mt-1 text-xs">
                              {template.description || "No description"}
                            </CardDescription>
                          </div>
                        </div>
                        <Badge variant="secondary" className="text-[10px] font-mono">
                          {template.transport}
                        </Badge>
                      </div>
                    </CardHeader>

                    <CardContent className="space-y-4 pt-0">
                      <div className="rounded-2xl border border-border/70 bg-background/30 px-3 py-2 font-mono text-xs text-muted-foreground">
                        {template.transport === "stdio"
                          ? [template.command, ...(template.args || [])].filter(Boolean).join(" ")
                          : template.url || template.slug}
                      </div>

                      <Button
                        variant="outline"
                        className="w-full gap-1.5"
                        onClick={(event) => {
                          event.stopPropagation();
                          handleUseTemplate(template);
                        }}
                      >
                        <Zap className="h-4 w-4" />
                        Use template
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      </SectionCard>

      {editorOpen && editMcp ? (
        <SectionCard
          title={
            (editMcp as MCPServer | null)?.id
              ? (editMcp as MCPServer | null)?.can_edit === false
                ? "View MCP server"
                : "Edit MCP server"
              : "Add MCP server"
          }
          description="Configure either a local stdio command or a remote SSE endpoint."
          icon={<Pencil className="h-5 w-5" />}
        >
          <MCPForm
            initial={editMcp}
            onSave={handleSave}
            onCancel={() => {
              setEditorOpen(false);
              setEditMcp(null);
            }}
            isPending={createMutation.isPending || updateMutation.isPending}
            shareUsers={shareUsers}
            isAdmin={isAdmin}
            canEdit={(editMcp as MCPServer | null)?.can_edit !== false}
          />
        </SectionCard>
      ) : null}

      <Dialog open={deleteTarget !== null} onOpenChange={(nextOpen) => !nextOpen && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>Delete MCP server</DialogTitle>
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
              {deleteMutation.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
              Delete
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </PageShell>
      </div>
    </div>
  );
}
