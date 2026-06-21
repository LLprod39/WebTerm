import { useMemo, useState, type ElementType } from "react";
import { StudioNav } from "@/components/StudioNav";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  AlertTriangle,
  Bot,
  Loader2,
  Plus,
  Save,
  Server as ServerIcon,
  Share2,
  ShieldCheck,
  SlidersHorizontal,
  Trash2,
  Wrench,
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
  Sheet,
  SheetContent,
  SheetDescription,
  SheetHeader,
  SheetTitle,
} from "@/components/ui/sheet";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { useToast } from "@/hooks/use-toast";
import { StudioHero, HeroActionButton, HeroStatChip } from "@/components/studio/StudioHero";
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
import {
  MODEL_OPTIONS,
  sudoOption,
  toolLabel,
  visibleAllowedTools,
} from "./agent-config/agentConfigOptions";

type ProfileSection = "main" | "tools" | "scope" | "access";

const DEFAULT_ALLOWED_TOOLS = ["ssh_execute", "report"];

function toIdList(items: Array<number | { id: number }> | undefined) {
  return (items || [])
    .map((item) => (typeof item === "number" ? item : item.id))
    .filter((item): item is number => Number.isFinite(item))
    .sort((a, b) => a - b);
}

function createProfileDraft(initial: Partial<AgentConfig>): Partial<AgentConfig> {
  return {
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
    allowed_tools: visibleAllowedTools(initial.allowed_tools) ?? DEFAULT_ALLOWED_TOOLS,
  };
}

function profileFingerprint(profile: Partial<AgentConfig>) {
  return JSON.stringify({
    name: profile.name || "",
    description: profile.description || "",
    icon: profile.icon || "B",
    system_prompt: profile.system_prompt || "",
    instructions: profile.instructions || "",
    model: profile.model || MODEL_OPTIONS[0],
    max_iterations: Number(profile.max_iterations || 10),
    sudo_policy: profile.sudo_policy || "disabled",
    allowed_tools: [...(visibleAllowedTools(profile.allowed_tools) || [])].sort(),
    skill_slugs: [...(profile.skill_slugs || [])].sort(),
    mcp_servers: toIdList(profile.mcp_servers as Array<number | { id: number }> | undefined),
    server_scope: toIdList(profile.server_scope as Array<number | { id: number }> | undefined),
    is_shared: Boolean(profile.is_shared),
    shared_user_ids: [...(profile.shared_user_ids || [])].sort((a, b) => a - b),
  });
}

function formatProfileDate(value: string | null | undefined, lang: "ru" | "en") {
  if (!value) return localize(lang, "Нет данных", "No data");
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return localize(lang, "Нет данных", "No data");
  return new Intl.DateTimeFormat(lang === "ru" ? "ru-RU" : "en-US", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function getRiskItems(form: Partial<AgentConfig>, lang: "ru" | "en") {
  const tools = visibleAllowedTools(form.allowed_tools) || [];
  const serverScopeCount = toIdList(form.server_scope as Array<number | { id: number }> | undefined).length;
  const items: Array<{ tone: "ok" | "warn" | "danger"; label: string }> = [];

  if (form.sudo_policy === "approved") {
    items.push({ tone: "danger", label: localize(lang, "sudo разрешён на запуск", "sudo approved for runs") });
  } else if (form.sudo_policy === "ask") {
    items.push({ tone: "warn", label: localize(lang, "sudo требует подтверждения", "sudo asks for approval") });
  }

  if (tools.includes("ssh_execute")) {
    items.push({ tone: "warn", label: localize(lang, "может выполнять SSH-команды", "can run SSH commands") });
  }

  if (serverScopeCount === 0) {
    items.push({ tone: "warn", label: localize(lang, "scope: все доступные серверы", "scope: all accessible servers") });
  } else {
    items.push({ tone: "ok", label: localize(lang, `scope: ${serverScopeCount} серверов`, `scope: ${serverScopeCount} servers`) });
  }

  if (!items.length) {
    items.push({ tone: "ok", label: localize(lang, "низкий риск", "low risk") });
  }

  return items;
}

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
  const initialDraft = useMemo(() => createProfileDraft(initial), [initial]);
  const initialFingerprint = useMemo(() => profileFingerprint(initialDraft), [initialDraft]);
  const [form, setForm] = useState<Partial<AgentConfig>>(initialDraft);
  const [activeSection, setActiveSection] = useState<ProfileSection>("main");
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
  const dirty = profileFingerprint(form) !== initialFingerprint;
  const canSave = !readOnly && !isPending && Boolean(form.name?.trim()) && dirty;
  const riskItems = getRiskItems(form, lang);
  const sectionItems: Array<{ id: ProfileSection; label: string; icon: ElementType }> = [
    { id: "main", label: localize(lang, "Основное", "Basics"), icon: SlidersHorizontal },
    { id: "tools", label: localize(lang, "Инструменты", "Tools"), icon: Wrench },
    { id: "scope", label: "Scope", icon: ServerIcon },
    { id: "access", label: localize(lang, "Доступ", "Access"), icon: Share2 },
  ];

  const handleDiscard = () => {
    setForm(initialDraft);
  };

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="border-b border-border/70 bg-secondary/20 px-5 py-3">
        <div className="grid grid-cols-2 gap-1 rounded-lg bg-background/65 p-1 sm:grid-cols-4">
          {sectionItems.map((item) => {
            const Icon = item.icon;
            const active = activeSection === item.id;
            return (
              <button
                key={item.id}
                type="button"
                onClick={() => setActiveSection(item.id)}
                className={`flex h-9 items-center justify-center gap-1.5 rounded-md px-2 text-xs font-medium transition-colors ${
                  active
                    ? "bg-card text-foreground shadow-sm"
                    : "text-muted-foreground hover:bg-card/60 hover:text-foreground"
                }`}
              >
                <Icon className="h-3.5 w-3.5" />
                <span className="truncate">{item.label}</span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="min-h-0 flex-1 overflow-y-auto px-5 py-4">
        <div className="mb-4 rounded-lg border border-border/70 bg-background/45 px-3 py-3">
          <div className="flex items-center gap-2 text-sm font-medium text-foreground">
            <ShieldCheck className="h-4 w-4 text-primary" />
            {localize(lang, "Сводка риска", "Risk summary")}
          </div>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {riskItems.map((item) => (
              <Badge
                key={item.label}
                variant={item.tone === "danger" ? "destructive" : item.tone === "warn" ? "outline" : "secondary"}
                className="max-w-full text-xs"
              >
                {item.tone === "danger" ? <AlertTriangle className="mr-1 h-3 w-3" /> : null}
                {item.label}
              </Badge>
            ))}
          </div>
        </div>

        <div className="space-y-6">
          {activeSection === "main" ? (
            <AgentCoreSettingsSection
              form={form}
              lang={lang}
              readOnly={readOnly}
              onFieldChange={setField}
            />
          ) : null}

          {activeSection === "tools" ? (
            <>
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
            </>
          ) : null}

          {activeSection === "scope" ? (
            <AgentServerScopeSection
              lang={lang}
              readOnly={readOnly}
              serverScopeIds={serverScopeIds}
              servers={servers}
              onToggleServerScope={toggleServerScope}
            />
          ) : null}

          {activeSection === "access" ? (
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
          ) : null}

          {activeSection === "access" && !isAdmin ? (
            <div className="rounded-lg border border-border/70 bg-background/45 px-4 py-3 text-sm text-muted-foreground">
              {localize(lang, "Доступом к профилям управляет администратор.", "Profile access is managed by an administrator.")}
            </div>
          ) : null}

          {form.skill_errors?.length ? (
            <div className="rounded-lg border border-amber-500/30 bg-amber-500/5 px-4 py-3">
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
        </div>
      </div>

      <div className="border-t border-border/70 bg-card/95 px-5 py-3 shadow-[0_-12px_36px_hsl(var(--background)_/_0.2)]">
        <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
          <p className="text-xs text-muted-foreground">
            {readOnly
              ? localize(lang, "Профиль открыт только для чтения.", "This profile is read only.")
              : dirty
                ? localize(lang, "Есть несохранённые изменения.", "You have unsaved changes.")
                : localize(lang, "Изменений нет.", "No unsaved changes.")}
          </p>
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={dirty ? handleDiscard : onCancel}>
              {dirty ? localize(lang, "Сбросить", "Discard") : localize(lang, "Закрыть", "Close")}
            </Button>
            <Button
              onClick={() => onSave(form)}
              disabled={!canSave}
              className="gap-2"
            >
              {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
              {localize(lang, "Сохранить профиль", "Save profile")}
            </Button>
          </div>
        </div>
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
        kicker={localize(lang, "Studio / Профили выполнения", "Studio / Execution Profiles")}
        title={localize(lang, "Профили выполнения", "Execution Profiles")}
        titleIcon={<Bot className="h-7 w-7 text-primary" />}
        description={localize(
          lang,
          "Переиспользуемые конфигурации модели, инструментов, scope и доступа для pipeline-нод.",
          "Reusable model, tool, scope, and access configs for pipeline nodes.",
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
            {localize(lang, "Создайте профиль с моделью, инструментами и scope для pipeline-нод.", "Create a profile with model, tools, and scope for pipeline nodes.")}
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
              <TableHead>{localize(lang, "Модель", "Model")}</TableHead>
              <TableHead>{localize(lang, "Инструменты", "Tools")}</TableHead>
              <TableHead>Scope</TableHead>
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
                  <TableCell>
                    <div className="space-y-1">
                      <div className="max-w-[180px] truncate font-mono text-xs text-foreground">{agent.model}</div>
                      <Badge variant="outline" className="text-xs">
                        {localize(lang, `${agent.max_iterations} итер.`, `${agent.max_iterations} iter`)}
                      </Badge>
                    </div>
                  </TableCell>
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
                "Настройте модель, инструменты, scope, MCP-серверы, skills и доступ для переиспользуемого профиля.",
                "Configure model, tools, scope, MCP servers, skills, and access for this reusable profile.",
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
              canEdit={(editAgent as AgentConfig | null)?.can_edit !== false}
            />
          ) : null}
        </SheetContent>
      </Sheet>

      <Dialog open={deleteTarget !== null} onOpenChange={(nextOpen) => !nextOpen && setDeleteTarget(null)}>
        <DialogContent className="max-w-sm">
          <DialogHeader>
            <DialogTitle>{localize(lang, "Удалить профиль", "Delete profile")}</DialogTitle>
            <DialogDescription>
              {deleteTarget
                ? localize(lang, `Удалить профиль "${deleteTarget.name}"? Действие нельзя отменить.`, `Delete profile "${deleteTarget.name}"? This cannot be undone.`)
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
