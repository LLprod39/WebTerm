import { useState } from "react";
import { StudioNav } from "@/components/StudioNav";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  Bot,
  Loader2,
  Plus,
  Save,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { useToast } from "@/hooks/use-toast";
import { StudioHero, HeroStatChip, HeroActionButton } from "@/components/studio/StudioHero";
import {
  fetchAuthSession,
  studioAgents,
  studioMCP,
  studioServers,
  studioShareUsers,
  studioSkills,
  type AgentConfig,
} from "@/lib/api";
import { hasFeatureAccess } from "@/lib/featureAccess";
import { localize, useI18n } from "@/lib/i18n";
import {
  AgentAllowedToolsSection,
  AgentCoreSettingsSection,
  AgentMcpServersSection,
  AgentServerScopeSection,
  AgentSkillsSection,
  AgentVisibilitySection,
} from "./agent-config/AgentFormAccessSections";
import { AgentConfigCard } from "./agent-config/AgentConfigCard";
import {
  MODEL_OPTIONS,
  visibleAllowedTools,
} from "./agent-config/agentConfigOptions";

function AgentForm({
  initial,
  onSave,
  onCancel,
  isPending,
  canUseMcp,
  canUseSkills,
  shareUsers,
  isAdmin,
  canEdit,
}: {
  initial: Partial<AgentConfig>;
  onSave: (payload: Partial<AgentConfig>) => void;
  onCancel: () => void;
  isPending: boolean;
  canUseMcp: boolean;
  canUseSkills: boolean;
  shareUsers: Array<{ id: number; username: string; email?: string }>;
  isAdmin: boolean;
  canEdit: boolean;
}) {
  const { lang } = useI18n();
  const navigate = useNavigate();
  const [form, setForm] = useState<Partial<AgentConfig>>({
    name: "",
    description: "",
    icon: "B",
    system_prompt: "",
    instructions: "",
    model: MODEL_OPTIONS[0],
    max_iterations: 10,
    sudo_policy: "disabled",
    skill_slugs: [],
    mcp_servers: [],
    server_scope: [],
    is_shared: false,
    shared_user_ids: [],
    ...initial,
    allowed_tools: visibleAllowedTools(initial.allowed_tools) ?? ["ssh_execute", "report"],
  });
  const readOnly = !canEdit;

  const { data: mcpList = [] } = useQuery({
    queryKey: ["studio", "mcp"],
    queryFn: studioMCP.list,
    enabled: canUseMcp,
  });

  const { data: servers = [] } = useQuery({
    queryKey: ["studio", "servers"],
    queryFn: studioServers.list,
  });

  const { data: skills = [] } = useQuery({
    queryKey: ["studio", "skills"],
    queryFn: studioSkills.list,
    enabled: canUseSkills,
  });

  const setField = (key: keyof AgentConfig, value: unknown) => {
    setForm((current) => ({ ...current, [key]: value }));
  };

  const toggleTool = (toolId: string) => {
    const current = form.allowed_tools || [];
    setField(
      "allowed_tools",
      current.includes(toolId)
        ? current.filter((item) => item !== toolId)
        : [...current, toolId],
    );
  };

  const toggleMcp = (mcpId: number) => {
    const currentIds = (form.mcp_servers || []).map((item) =>
      typeof item === "number" ? item : item.id,
    );
    const nextIds = currentIds.includes(mcpId)
      ? currentIds.filter((item) => item !== mcpId)
      : [...currentIds, mcpId];
    setField("mcp_servers", nextIds as unknown as AgentConfig["mcp_servers"]);
  };

  const toggleServerScope = (serverId: number) => {
    const currentIds = (form.server_scope || []).map((item) =>
      typeof item === "number" ? item : item.id,
    );
    const nextIds = currentIds.includes(serverId)
      ? currentIds.filter((item) => item !== serverId)
      : [...currentIds, serverId];
    setField("server_scope", nextIds as unknown as AgentConfig["server_scope"]);
  };

  const toggleSkill = (slug: string) => {
    const current = form.skill_slugs || [];
    setField(
      "skill_slugs",
      current.includes(slug)
        ? current.filter((item) => item !== slug)
        : [...current, slug],
    );
  };

  const mcpIds = (form.mcp_servers || []).map((item) => (typeof item === "number" ? item : item.id));
  const serverScopeIds = (form.server_scope || []).map((item) => (typeof item === "number" ? item : item.id));
  const sharedUserIds = form.shared_user_ids || [];

  return (
    <div className="space-y-6">
      <AgentCoreSettingsSection
        form={form}
        lang={lang}
        readOnly={readOnly}
        onFieldChange={setField}
      />

      <AgentAllowedToolsSection
        allowedTools={form.allowed_tools || []}
        lang={lang}
        readOnly={readOnly}
        onToggleTool={toggleTool}
      />

      <AgentMcpServersSection
        canUseMcp={canUseMcp}
        lang={lang}
        mcpIds={mcpIds}
        mcpList={mcpList}
        readOnly={readOnly}
        onToggleMcp={toggleMcp}
      />

      <AgentSkillsSection
        canUseSkills={canUseSkills}
        lang={lang}
        readOnly={readOnly}
        selectedSkillSlugs={form.skill_slugs || []}
        skills={skills}
        onBrowseCatalog={() => navigate("/studio/skills")}
        onToggleSkill={toggleSkill}
      />

      <AgentServerScopeSection
        lang={lang}
        readOnly={readOnly}
        serverScopeIds={serverScopeIds}
        servers={servers}
        onToggleServerScope={toggleServerScope}
      />

      <AgentVisibilitySection
        isAdmin={isAdmin}
        isShared={Boolean(form.is_shared)}
        lang={lang}
        readOnly={readOnly}
        sharedUserIds={sharedUserIds}
        users={shareUsers}
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

      {form.skill_errors?.length ? (
        <div className="rounded-xl border border-amber-500/30 bg-amber-500/5 px-4 py-3">
          <div className="text-sm font-medium text-amber-200">{localize(lang, "Предупреждения skills", "Skill warnings")}</div>
          <div className="mt-2 space-y-1">
            {form.skill_errors.map((error) => (
              <p key={error} className="text-xs text-amber-100">
                {error}
              </p>
            ))}
          </div>
        </div>
      ) : null}

      <div className="flex justify-end gap-2">
        <Button variant="outline" onClick={onCancel}>
          {localize(lang, "Отмена", "Cancel")}
        </Button>
        <Button
          onClick={() => onSave(form)}
          disabled={readOnly || !form.name?.trim() || isPending}
          className="gap-2"
        >
          {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
          {localize(lang, "Сохранить агента", "Save agent")}
        </Button>
      </div>
    </div>
  );
}

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
      toast({ description: localize(lang, "Агент создан.", "Agent created.") });
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
      toast({ description: localize(lang, "Агент обновлён.", "Agent updated.") });
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
      toast({ description: localize(lang, "Агент удалён.", "Agent deleted.") });
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
        kicker="Studio / Agents"
        title={localize(lang, "Профили агентов", "Agent Configs")}
        titleIcon={<Bot className="h-7 w-7 text-primary" />}
        description={localize(
          lang,
          "Переиспользуемые профили для pipeline-нод и задач автоматизации.",
          "Reusable agent profiles for pipeline nodes and automation tasks.",
        )}
        stats={
          <HeroStatChip
            icon={<Bot className="h-3.5 w-3.5" />}
            label={localize(lang, `${agents.length} профилей`, `${agents.length} configs`)}
          />
        }
        actions={
          <HeroActionButton
            onClick={() => setEditAgent({})}
            icon={<Plus className="h-4 w-4" />}
            label={localize(lang, "Новый агент", "New agent")}
            primary
          />
        }
      />
      <div className="flex-1 px-6 pb-8 space-y-5">
      {isLoading ? (
        <div className="flex h-40 items-center justify-center text-muted-foreground">
          <Loader2 className="mr-2 h-4 w-4 animate-spin" />
          {localize(lang, "Загружаем профили агентов...", "Loading agent configs...")}
        </div>
      ) : agents.length === 0 ? (
        <div className="flex h-56 flex-col items-center justify-center rounded-2xl border border-dashed border-border text-center">
          <Bot className="mb-3 h-10 w-10 text-muted-foreground/50" />
          <p className="text-sm font-medium text-foreground">
            {localize(lang, "Профилей агентов пока нет.", "No agent configs yet.")}
          </p>
          <p className="mt-1 text-xs text-muted-foreground">
            {localize(lang, "Создайте переиспользуемые профили для pipelines.", "Create reusable agent profiles for pipelines.")}
          </p>
          <Button className="mt-4 gap-2" size="sm" onClick={() => setEditAgent({})}>
            <Plus className="h-4 w-4" />
            {localize(lang, "Новый агент", "New agent")}
          </Button>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
          {agents.map((agent) => (
            <AgentConfigCard
              key={agent.id}
              agent={agent}
              lang={lang}
              onEdit={setEditAgent}
              onDelete={setDeleteTarget}
            />
          ))}
        </div>
      )}

      <Dialog open={editAgent !== null} onOpenChange={(nextOpen) => !nextOpen && setEditAgent(null)}>
        <DialogContent className="max-h-[calc(100dvh-2rem)] w-[calc(100vw-2rem)] max-w-4xl">
          <DialogHeader>
            <DialogTitle>
              {(editAgent as AgentConfig | null)?.id
                  ? (editAgent as AgentConfig | null)?.can_edit === false
                  ? localize(lang, "Просмотр агента", "View agent")
                  : localize(lang, "Редактировать агента", "Edit agent")
                : localize(lang, "Новый агент", "New agent")}
            </DialogTitle>
            <DialogDescription>
              {localize(
                lang,
                "Настройте модель, инструменты, ограничения, MCP-серверы и skills для переиспользуемого профиля.",
                "Configure model, tools, scopes, MCP servers, and skills for this reusable agent profile.",
              )}
            </DialogDescription>
          </DialogHeader>
          <DialogBody className="max-h-[calc(100dvh-10rem)] overflow-y-auto">
            {editAgent ? (
              <AgentForm
                initial={editAgent}
                onSave={handleSave}
                onCancel={() => setEditAgent(null)}
                isPending={createMutation.isPending || updateMutation.isPending}
                canUseMcp={canUseMcp}
                canUseSkills={canUseSkills}
                shareUsers={shareUsers}
                isAdmin={isAdmin}
                canEdit={(editAgent as AgentConfig | null)?.can_edit !== false}
              />
            ) : null}
          </DialogBody>
        </DialogContent>
      </Dialog>

      <Dialog open={deleteTarget !== null} onOpenChange={(nextOpen) => !nextOpen && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{localize(lang, "Удалить агента", "Delete agent")}</DialogTitle>
            <DialogDescription>
              {deleteTarget
                ? localize(lang, `Удалить "${deleteTarget.name}"? Действие нельзя отменить.`, `Delete "${deleteTarget.name}"? This cannot be undone.`)
                : ""}
            </DialogDescription>
          </DialogHeader>
          <DialogFooter>
            <Button variant="outline" onClick={() => setDeleteTarget(null)}>
              {localize(lang, "Отмена", "Cancel")}
            </Button>
            <Button
              variant="destructive"
              onClick={() => deleteTarget && deleteMutation.mutate(deleteTarget.id)}
              disabled={deleteMutation.isPending}
            >
              {deleteMutation.isPending ? <Loader2 className="mr-1 h-4 w-4 animate-spin" /> : null}
              {localize(lang, "Удалить", "Delete")}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </div>
    </div>
    </div>
  );
}
