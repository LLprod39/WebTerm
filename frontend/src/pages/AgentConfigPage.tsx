import { useState } from "react";
import { StudioNav } from "@/components/StudioNav";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { Bot, Loader2, Plus, Trash2 } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { DeleteDialog } from "@/components/system/ConfirmDialog";
import { Sheet, SheetContent, SheetDescription, SheetHeader, SheetTitle } from "@/components/ui/sheet";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import { StudioHero, HeroActionButton, HeroStatChip } from "@/components/studio/StudioHero";
import { fetchAuthSession, studioAgents, studioShareUsers, type AgentConfig } from "@/lib/api";
import { canManageAiRouting as canManageAiRoutingForUser, hasFeatureAccess } from "@/lib/featureAccess";
import { localize, useI18n } from "@/lib/i18n";
import { AgentForm, formatProfileDate } from "./agent-config/AgentProfileForm";
import { sudoOption, toolLabel, visibleAllowedTools } from "./agent-config/agentConfigOptions";


export default function AgentConfigPage() {
  const { lang } = useI18n();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { toast } = useToast();
  const [editAgent, setEditAgent] = useState<Partial<AgentConfig> | null>(null);
  const [deleteTarget, setDeleteTarget] = useState<AgentConfig | null>(null);

  const { data: session } = useQuery({
    queryKey: ["auth", "session"],
    queryFn: fetchAuthSession,
    staleTime: 60_000,
    retry: false,
  });
  const user = session?.user ?? null;
  const isAdmin = Boolean(user?.is_staff);
  const canManageAiRouting = canManageAiRoutingForUser(user);
  const canUseMcp = hasFeatureAccess(user, "studio_mcp");
  const canUseSkills = hasFeatureAccess(user, "studio_skills");

  const { data: agents = [], isLoading } = useQuery({
    queryKey: ["studio", "agents"],
    queryFn: studioAgents.list,
  });

  const { data: shareUsers = [] } = useQuery({
    queryKey: ["studio", "share-users"],
    queryFn: studioShareUsers.list,
    enabled: isAdmin,
  });

  const createMutation = useMutation({
    mutationFn: (payload: Partial<AgentConfig>) => studioAgents.create(payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studio", "agents"] });
      setEditAgent(null);
      toast({ description: localize(lang, "Профиль выполнения создан.", "Execution profile created.") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const updateMutation = useMutation({
    mutationFn: ({ id, payload }: { id: number; payload: Partial<AgentConfig> }) =>
      studioAgents.update(id, payload),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studio", "agents"] });
      setEditAgent(null);
      toast({ description: localize(lang, "Профиль выполнения обновлён.", "Execution profile updated.") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const deleteMutation = useMutation({
    mutationFn: (id: number) => studioAgents.delete(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["studio", "agents"] });
      setDeleteTarget(null);
      toast({ description: localize(lang, "Профиль выполнения удалён.", "Execution profile deleted.") });
    },
    onError: (error: Error) => {
      toast({ variant: "destructive", description: error.message });
    },
  });

  const handleSave = (payload: Partial<AgentConfig>) => {
    const editingAgent = editAgent as AgentConfig | null;
    if (editingAgent?.id) {
      if (editingAgent.can_edit === false) return;
      updateMutation.mutate({
        id: editingAgent.id,
        payload,
      });
      return;
    }

    createMutation.mutate(payload);
  };

  return (
    <div className="flex flex-col h-full">
      <StudioNav />
      <div className="flex-1 overflow-auto flex flex-col">
      <StudioHero
        kicker={localize(lang, "Студия / Профили выполнения", "Studio / Execution Profiles")}
        title={localize(lang, "Профили выполнения", "Execution Profiles")}
        titleIcon={<Bot className="h-7 w-7 text-primary" />}
        description={localize(
          lang,
          "Готовые наборы инструментов, области серверов и доступа для узлов сценария.",
          "Reusable tool, scope, and access configs for pipeline nodes.",
        )}
        stats={
          <HeroStatChip
            icon={<Bot className="h-3.5 w-3.5" />}
            label={localize(lang, `${agents.length} профилей`, `${agents.length} profiles`)}
          />
        }
        actions={
          <HeroActionButton
            onClick={() => setEditAgent({})}
            icon={<Plus className="h-4 w-4" />}
            label={localize(lang, "Новый профиль", "New profile")}
            primary
          />
        }
      />
      <div className="flex-1 px-6 pb-8 space-y-5">
      {isLoading ? (
        <div className="flex h-40 items-center justify-center text-muted-foreground">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          {localize(lang, "Загружаем профили выполнения...", "Loading execution profiles...")}
        </div>
      ) : agents.length === 0 ? (
        <div className="flex h-56 flex-col items-center justify-center rounded-xl border border-dashed border-border text-center">
          <Bot className="mb-3 h-10 w-10 text-muted-foreground/50" />
          <p className="text-sm font-medium text-foreground">
            {localize(lang, "Профилей выполнения пока нет.", "No execution profiles yet.")}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {localize(lang, "Сохраните модель, инструменты и доступ к серверам в одном профиле.", "Create a profile with model, tools, and scope for pipeline nodes.")}
          </p>
          <Button className="mt-4 gap-2" size="sm" onClick={() => setEditAgent({})}>
            <Plus className="h-4 w-4" />
            {localize(lang, "Новый профиль", "New profile")}
          </Button>
        </div>
      ) : (
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>{localize(lang, "Профиль", "Profile")}</TableHead>
              {canManageAiRouting ? <TableHead>{localize(lang, "Модель", "Model")}</TableHead> : null}
              <TableHead>{localize(lang, "Инструменты", "Tools")}</TableHead>
              <TableHead>{localize(lang, "Серверы", "Scope")}</TableHead>
              <TableHead>{localize(lang, "Владелец / доступ", "Owner / access")}</TableHead>
              <TableHead>{localize(lang, "Обновлён", "Updated")}</TableHead>
              <TableHead className="w-[112px] text-right">{localize(lang, "Действия", "Actions")}</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {agents.map((agent) => {
              const visibleTools = visibleAllowedTools(agent.allowed_tools) || [];
              const sudo = sudoOption(agent.sudo_policy);
              return (
                <TableRow key={agent.id}>
                  <TableCell className="min-w-[240px]">
                    <div className="flex items-start gap-3">
                      <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg border border-primary/20 bg-primary/10 text-base font-semibold text-primary">
                        {agent.icon || "B"}
                      </div>
                      <div className="min-w-0">
                        <div className="font-medium text-foreground">{agent.name}</div>
                        <div className="mt-1 line-clamp-2 max-w-md text-xs text-muted-foreground">
                          {agent.description || localize(lang, "Описание не заполнено", "No description")}
                        </div>
                      </div>
                    </div>
                  </TableCell>
                  {canManageAiRouting ? <TableCell>
                    <div className="space-y-1">
                      <div className="max-w-[180px] truncate font-mono text-xs text-foreground">{agent.model}</div>
                      <Badge variant="outline" className="text-xs">
                        {localize(lang, `${agent.max_iterations} итер.`, `${agent.max_iterations} iter`)}
                      </Badge>
                    </div>
                  </TableCell> : null}
                  <TableCell>
                    <div className="flex max-w-[220px] flex-wrap gap-1">
                      {visibleTools.slice(0, 3).map((tool) => (
                        <Badge key={tool} variant="secondary" className="text-xs">
                          {toolLabel(tool, lang)}
                        </Badge>
                      ))}
                      {visibleTools.length > 3 ? (
                        <Badge variant="outline" className="text-xs">
                          +{visibleTools.length - 3}
                        </Badge>
                      ) : null}
                      <Badge variant={agent.sudo_policy === "approved" ? "destructive" : "outline"} className="text-xs">
                        sudo: {localize(lang, sudo.labelRu, sudo.labelEn)}
                      </Badge>
                    </div>
                  </TableCell>
                  <TableCell>
                    {agent.server_scope?.length ? (
                      <Badge variant="secondary" className="text-xs">
                        {localize(lang, `${agent.server_scope.length} серверов`, `${agent.server_scope.length} servers`)}
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="text-xs">
                        {localize(lang, "Все доступные", "All accessible")}
                      </Badge>
                    )}
                  </TableCell>
                  <TableCell>
                    <div className="space-y-1 text-xs">
                      <div className="font-medium text-foreground">
                        {agent.is_owner ? localize(lang, "Мой профиль", "My profile") : agent.owner_username || localize(lang, "Неизвестно", "Unknown")}
                      </div>
                      <div className="flex flex-wrap gap-1">
                        {agent.is_shared ? <Badge variant="outline">{localize(lang, "Общий", "Shared")}</Badge> : null}
                        {agent.can_edit === false ? <Badge variant="outline">{localize(lang, "Только чтение", "Read only")}</Badge> : null}
                      </div>
                    </div>
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-xs text-muted-foreground">
                    {formatProfileDate(agent.updated_at || agent.created_at, lang)}
                  </TableCell>
                  <TableCell>
                    <div className="flex justify-end gap-1">
                      <Button
                        size="sm"
                        variant="outline"
                        className="h-8 px-2.5 text-xs"
                        onClick={() => setEditAgent(agent)}
                      >
                        {agent.can_edit === false ? localize(lang, "Открыть", "View") : localize(lang, "Изменить", "Edit")}
                      </Button>
                      {agent.can_edit !== false ? (
                        <Button
                          size="icon"
                          variant="ghost"
                          className="h-8 w-8 text-destructive hover:text-destructive"
                          aria-label={localize(lang, `Удалить профиль ${agent.name}`, `Delete profile ${agent.name}`)}
                          onClick={() => setDeleteTarget(agent)}
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </Button>
                      ) : null}
                    </div>
                  </TableCell>
                </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}

      <Sheet open={editAgent !== null} onOpenChange={(nextOpen) => !nextOpen && setEditAgent(null)}>
        <SheetContent side="right" className="flex w-[calc(100vw-1rem)] max-w-[720px] flex-col p-0 sm:w-[720px] sm:max-w-[720px]">
          <SheetHeader className="border-b border-border/70 bg-card px-5 py-4 pr-12 text-left">
            <div className="flex items-center gap-2">
              <SheetTitle className="text-lg">
                {(editAgent as AgentConfig | null)?.id
                  ? (editAgent as AgentConfig | null)?.can_edit === false
                    ? localize(lang, "Просмотр профиля", "View profile")
                    : localize(lang, "Редактировать профиль", "Edit profile")
                  : localize(lang, "Новый профиль", "New profile")}
              </SheetTitle>
              {(editAgent as AgentConfig | null)?.can_edit === false ? (
                <Badge variant="outline" className="text-xs">
                  {localize(lang, "Только чтение", "Read only")}
                </Badge>
              ) : null}
            </div>
            <SheetDescription>
              {localize(
                lang,
                "Настройте инструменты, доступ к серверам, MCP-серверы, навыки и общий доступ.",
                "Configure tools, scope, MCP servers, skills, and access for this reusable profile.",
              )}
            </SheetDescription>
          </SheetHeader>
          {editAgent ? (
            <AgentForm
              key={(editAgent as AgentConfig | null)?.id || "new"}
              initial={editAgent}
              onSave={handleSave}
              onCancel={() => setEditAgent(null)}
              isPending={createMutation.isPending || updateMutation.isPending}
              canUseMcp={canUseMcp}
              canUseSkills={canUseSkills}
              shareUsers={shareUsers}
              isAdmin={isAdmin}
              canManageAiRouting={canManageAiRouting}
              canEdit={(editAgent as AgentConfig | null)?.can_edit !== false}
            />
          ) : null}
        </SheetContent>
      </Sheet>

      <DeleteDialog
        open={deleteTarget !== null}
        onOpenChange={(nextOpen) => !nextOpen && setDeleteTarget(null)}
        title={localize(lang, "Удалить профиль", "Delete profile")}
        description={
          deleteTarget
            ? localize(lang, `Удалить профиль "${deleteTarget.name}"? Действие нельзя отменить.`, `Delete profile "${deleteTarget.name}"? This cannot be undone.`)
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
