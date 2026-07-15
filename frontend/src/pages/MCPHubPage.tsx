import { StudioNav } from "@/components/StudioNav";
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Loader2,
  Pencil,
  Plus,
  RefreshCw,
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
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { EmptyState, StatusBadge, QueryStateBlock } from "@/components/ui/page-shell";
import { SkeletonCards } from "@/components/ui/list-state";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { MCPForm } from "@/components/studio/MCPForm";
import { useToast } from "@/hooks/use-toast";
import { StudioHero, HeroStatChip, HeroActionButton } from "@/components/studio/StudioHero";
import { fetchAuthSession, studioMCP, studioShareUsers, type MCPServer, type MCPTemplate } from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
function previewConnection(server: Pick<MCPServer, "transport" | "command" | "args" | "url">) {
  if (server.transport === "stdio") {
    return [server.command, ...(server.args || [])].filter(Boolean).join(" ");
  }
  return server.url || "https://...";
}
export default function MCPHubPage() {
  const { lang } = useI18n();
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
  const { data: mcpList = [], isLoading, error: mcpError, refetch: refetchMcp } = useQuery({
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
      toast({ description: localize(lang, "MCP-сервер добавлен.", "MCP server added.") });
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
      toast({ description: localize(lang, "MCP-сервер обновлён.", "MCP server updated.") });
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
      toast({ description: localize(lang, "MCP-сервер удалён.", "MCP server removed.") });
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
        toast({ description: localize(lang, "Подключение работает.", "Connection OK.") });
      } else {
        toast({
          variant: "destructive",
          description: result.error || localize(lang, "Проверка подключения не прошла.", "Connection test failed."),
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
  const closeEditorDialog = () => {
    setEditorOpen(false);
    setEditMcp(null);
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
  const editorMcp = editMcp as MCPServer | null;
  const editorTitle = editorMcp?.id
    ? editorMcp.can_edit === false
      ? localize(lang, "Просмотр MCP-сервера", "View MCP server")
      : localize(lang, "Редактировать MCP-сервер", "Edit MCP server")
    : localize(lang, "Добавить MCP-сервер", "Add MCP server");
  const healthyCount = mcpList.filter((mcp) => mcp.last_test_ok === true).length;
  const failedCount = mcpList.filter((mcp) => mcp.last_test_ok === false).length;
  const unknownCount = Math.max(0, mcpList.length - healthyCount - failedCount);
  return (
    <div className="flex flex-col h-full">
      <StudioNav />
      <div className="flex-1 overflow-auto flex flex-col">
      <StudioHero
        kicker="Studio / MCP"
        title={localize(lang, "MCP-серверы", "MCP Registry")}
        titleIcon={<Server className="h-7 w-7 text-primary" />}
        description={localize(
          lang,
          "Подключайте инструменты для OPS-пайплайнов Studio. UI/code skills здесь не хранятся.",
          "Manage tools for Studio OPS pipelines. UI/code skills are not stored here.",
        )}
        stats={
          <>
            <HeroStatChip icon={<Server className="h-3.5 w-3.5" />} label={localize(lang, `${mcpList.length} серверов`, `${mcpList.length} servers`)} />
            <HeroStatChip icon={<Zap className="h-3.5 w-3.5" />} label={localize(lang, `${templates.length} шаблонов`, `${templates.length} templates`)} />
          </>
        }
        actions={
          <HeroActionButton
            onClick={openCreateDialog}
            icon={<Plus className="h-4 w-4" />}
            label={localize(lang, "Добавить MCP", "Add server")}
            primary
          />
        }
      />
      <div className="flex-1 px-6 pb-8 space-y-5">
        <Tabs defaultValue="mine" className="space-y-5">
          <TabsList>
            <TabsTrigger value="mine">{localize(lang, "Подключения", "My servers")} ({mcpList.length})</TabsTrigger>
            <TabsTrigger value="templates">{localize(lang, "Шаблоны", "Templates")} ({templates.length})</TabsTrigger>
          </TabsList>
          <TabsContent value="mine" className="space-y-4">
            {!isLoading && mcpList.length > 0 ? (
              <div className="grid gap-3 md:grid-cols-3">
                <div className="rounded-xl border border-success/25 bg-success/10 px-4 py-3">
                  <div className="text-2xl font-semibold text-success">{healthyCount}</div>
                  <div className="mt-1 text-sm text-foreground">{localize(lang, "Подключения работают", "Healthy connections")}</div>
                </div>
                <div className="rounded-xl border border-destructive/25 bg-destructive/10 px-4 py-3">
                  <div className="text-2xl font-semibold text-destructive">{failedCount}</div>
                  <div className="mt-1 text-sm text-foreground">{localize(lang, "Требуют проверки", "Need attention")}</div>
                </div>
                <div className="rounded-xl border border-border bg-secondary/20 px-4 py-3">
                  <div className="text-2xl font-semibold text-muted-foreground">{unknownCount}</div>
                  <div className="mt-1 text-sm text-foreground">{localize(lang, "Ещё не проверялись", "Not tested yet")}</div>
                </div>
              </div>
            ) : null}
            {isLoading ? (
              <SkeletonCards count={6} />
            ) : mcpError ? (
              <QueryStateBlock error={mcpError} onRetry={() => void refetchMcp()}>
                {null}
              </QueryStateBlock>
            ) : mcpList.length === 0 ? (
                <EmptyState
                  icon={<Server className="h-5 w-5" />}
                  title={localize(lang, "MCP-серверы ещё не подключены", "No MCP servers yet")}
                  description={localize(lang, "Выберите шаблон или добавьте stdio/SSE endpoint для интеграции с внешними инструментами.", "Start from a template or add a stdio/SSE endpoint for external tools.")}
                  actions={
                    <Button type="button" className="gap-1.5" onClick={openCreateDialog}>
                      <Plus className="h-4 w-4" />
                      {localize(lang, "Добавить MCP", "Add server")}
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
                    <div key={mcp.id} className="group overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-all duration-150 hover:border-border/80 hover:shadow-md">
                      <div className="space-y-3 p-4">
                        <div className="flex items-start justify-between gap-3">
                          <div className="min-w-0 flex-1">
                            <div className="flex items-center gap-2">
                              <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-lg bg-primary/10">
                                <Server className="h-4 w-4 text-primary" />
                              </div>
                              <div className="min-w-0">
                                <div className="flex items-center gap-1.5">
                                  <span className="truncate text-sm font-semibold text-foreground">{mcp.name}</span>
                                  <span className="rounded border border-border/50 bg-secondary/40 px-1.5 py-0.5 font-mono text-xs text-muted-foreground">{mcp.transport}</span>
                                </div>
                                <p className="mt-0.5 text-xs text-muted-foreground">{mcp.description || localize(lang, "Описание не заполнено", "No description")}</p>
                              </div>
                            </div>
                            <div className="mt-2 flex flex-wrap gap-1">
                              {mcp.is_owner ? <Badge variant="secondary" className="text-xs">{localize(lang, "Мой", "Mine")}</Badge> : null}
                              {!mcp.is_owner && mcp.owner_username ? <Badge variant="outline" className="text-xs">{localize(lang, "Владелец", "Owner")}: {mcp.owner_username}</Badge> : null}
                              {mcp.is_shared ? <Badge variant="outline" className="text-xs">{localize(lang, "Общий", "Shared")}</Badge> : null}
                              {mcp.can_edit === false ? <Badge variant="outline" className="text-xs">{localize(lang, "Только чтение", "Read only")}</Badge> : null}
                            </div>
                          </div>
                        </div>
                      </div>
                      <div className="border-t border-border/50 bg-secondary/10 px-4 py-3 space-y-2.5">
                        <div className="rounded-lg border border-border/50 bg-background/40 px-3 py-2 font-mono text-xs text-muted-foreground">
                          {previewConnection(mcp) || localize(lang, "Команда или URL не указаны", "No connection data")}
                        </div>
                        <div className="flex items-center justify-between gap-2">
                          <div className="flex flex-wrap items-center gap-1.5">
                            <StatusBadge
                              label={
                                mcp.last_test_ok === true
                                  ? localize(lang, "Проверен", "Healthy")
                                  : mcp.last_test_ok === false
                                    ? localize(lang, "Ошибка", "Failed")
                                    : localize(lang, "Не проверялся", "Not tested")
                              }
                              tone={tone}
                            />
                            {mcp.last_test_at && (
                              <span className="text-xs text-muted-foreground/60">
                                {new Date(mcp.last_test_at).toLocaleDateString()}
                              </span>
                            )}
                          </div>
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {mcp.can_edit !== false ? (
                            <Button
                              size="sm"
                              variant={mcp.last_test_ok === false ? "default" : "outline"}
                              className="h-9 gap-1.5"
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
                              {localize(lang, "Проверить", "Test")}
                            </Button>
                          ) : null}
                          <Button
                            type="button"
                            size="sm"
                            variant="outline"
                            className="h-9 gap-1.5"
                            onClick={() => openEditDialog(mcp)}
                          >
                            <Pencil className="h-4 w-4" />
                            {mcp.can_edit === false ? localize(lang, "Открыть", "View") : localize(lang, "Изменить", "Edit")}
                          </Button>
                          {mcp.can_edit !== false ? (
                            <Button
                              size="sm"
                              variant="ghost"
                              className="h-9 gap-1.5 text-destructive hover:text-destructive"
                              type="button"
                              onClick={() => setDeleteTarget(mcp)}
                            >
                              <Trash2 className="h-4 w-4" />
                              {localize(lang, "Удалить", "Delete")}
                            </Button>
                          ) : null}
                        </div>
                        {mcp.last_test_error && (
                          <p className="text-xs leading-5 text-red-400/80">{mcp.last_test_error}</p>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )}
          </TabsContent>
          <TabsContent value="templates" className="space-y-4">
            {templates.length === 0 ? (
              <EmptyState
                icon={<Zap className="h-5 w-5" />}
                title={localize(lang, "Шаблонов пока нет", "No templates available")}
                description={localize(lang, "Они появятся здесь, когда backend отдаст список готовых подключений.", "Template suggestions will appear here when the backend provides them.")}
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
                            {template.icon || <Zap className="h-5 w-5" />}
                          </div>
                          <div>
                            <CardTitle className="text-base">{template.name}</CardTitle>
                            <CardDescription className="mt-1 text-xs">
                              {template.description || localize(lang, "Описание не заполнено", "No description")}
                            </CardDescription>
                          </div>
                        </div>
                        <Badge variant="secondary" className="text-xs font-mono">
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
                        {localize(lang, "Использовать шаблон", "Use template")}
                      </Button>
                    </CardContent>
                  </Card>
                ))}
              </div>
            )}
          </TabsContent>
        </Tabs>
      <Dialog open={editorOpen && Boolean(editMcp)} onOpenChange={(nextOpen) => !nextOpen && closeEditorDialog()}>
        <DialogContent
          closeLabel={localize(lang, "Закрыть", "Close")}
          className="grid max-h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-4xl grid-rows-[auto_minmax(0,1fr)] overflow-hidden rounded-xl border-border bg-card p-0"
        >
          <DialogHeader className="pr-14">
            <div className="flex items-center gap-3">
              <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10">
                <Pencil className="h-4 w-4 text-primary" />
              </div>
              <div className="min-w-0">
                <DialogTitle>{editorTitle}</DialogTitle>
                <DialogDescription>
                  {localize(
                    lang,
                    "Настройте stdio-команду или SSE endpoint без растягивания всей страницы.",
                    "Configure a stdio command or SSE endpoint without stretching the whole page.",
                  )}
                </DialogDescription>
              </div>
            </div>
          </DialogHeader>
          <DialogBody className="min-h-0 overflow-y-auto">
            {editMcp ? (
              <MCPForm
                key={editorMcp?.id || editMcp.name || "new-mcp"}
                initial={editMcp}
                onSave={handleSave}
                onCancel={closeEditorDialog}
                isPending={createMutation.isPending || updateMutation.isPending}
                shareUsers={shareUsers}
                isAdmin={isAdmin}
                canEdit={editorMcp?.can_edit !== false}
              />
            ) : null}
          </DialogBody>
        </DialogContent>
      </Dialog>
      <DeleteDialog
        open={deleteTarget !== null}
        onOpenChange={(nextOpen) => !nextOpen && setDeleteTarget(null)}
        title={localize(lang, "Удалить MCP-сервер", "Delete MCP server")}
        description={
          deleteTarget
            ? localize(lang, `Удалить "${deleteTarget.name}"? Действие нельзя отменить.`, `Delete "${deleteTarget.name}"? This cannot be undone.`)
            : ""
        }
        confirmLabel={localize(lang, "Удалить", "Delete")}
        cancelLabel={localize(lang, "Отмена", "Cancel")}
        onConfirm={() => {
          if (deleteTarget) deleteMutation.mutate(deleteTarget.id);
        }}
      />
      </div>
      </div>
    </div>
  );
}
