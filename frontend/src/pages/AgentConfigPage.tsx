import { useState } from "react";
import { StudioNav } from "@/components/StudioNav";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import {
  ArrowLeft,
  BookOpen,
  Bot,
  Loader2,
  Pencil,
  Plus,
  Save,
  Trash2,
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
import { Checkbox } from "@/components/ui/checkbox";
import {
  Dialog,
  DialogBody,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Textarea } from "@/components/ui/textarea";
import { ShareAccessEditor } from "@/components/studio/ShareAccessEditor";
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

const ALL_TOOLS = [
  { id: "ssh_execute", labelRu: "SSH-команды", labelEn: "SSH Execute", descriptionRu: "Запуск команд на серверах", descriptionEn: "Run commands on servers" },
  { id: "read_console", labelRu: "Чтение консоли", labelEn: "Read Console", descriptionRu: "Чтение вывода терминала", descriptionEn: "Read terminal output" },
  { id: "open_connection", labelRu: "Открыть SSH", labelEn: "Open Connection", descriptionRu: "Открытие SSH-подключений", descriptionEn: "Open SSH connections" },
  { id: "close_connection", labelRu: "Закрыть SSH", labelEn: "Close Connection", descriptionRu: "Закрытие SSH-подключений", descriptionEn: "Close SSH connections" },
  { id: "wait_for_output", labelRu: "Ожидать вывод", labelEn: "Wait for Output", descriptionRu: "Ожидание нужного текста в терминале", descriptionEn: "Wait for terminal patterns" },
  { id: "report", labelRu: "Отчёт", labelEn: "Report", descriptionRu: "Промежуточные статусы выполнения", descriptionEn: "Send intermediate status updates" },
  { id: "ask_user", labelRu: "Спросить пользователя", labelEn: "Ask User", descriptionRu: "Пауза до ответа пользователя", descriptionEn: "Pause for user input" },
  { id: "analyze_output", labelRu: "Анализ вывода", labelEn: "Analyze Output", descriptionRu: "LLM-анализ полученного вывода", descriptionEn: "Run LLM analysis over output" },
];

function visibleAllowedTools(tools?: string[]) {
  return Array.isArray(tools) ? tools.filter((tool) => tool !== "send_ctrl_c") : undefined;
}

const MODEL_OPTIONS = [
  "gemini-2.0-flash-exp",
  "gemini-2.5-pro",
  "claude-4.5-sonnet",
  "claude-4.5-opus",
  "gpt-5.2",
];

function toolLabel(toolId: string, lang: "ru" | "en") {
  const tool = ALL_TOOLS.find((item) => item.id === toolId);
  return tool ? localize(lang, tool.labelRu, tool.labelEn) : toolId;
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
  const [form, setForm] = useState<Partial<AgentConfig>>({
    name: "",
    description: "",
    icon: "B",
    system_prompt: "",
    instructions: "",
    model: MODEL_OPTIONS[0],
    max_iterations: 10,
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
      <div className="grid gap-4 md:grid-cols-[96px_minmax(0,1fr)]">
        <div className="space-y-2">
          <Label>{localize(lang, "Иконка", "Icon")}</Label>
          <Input
            value={form.icon || "B"}
            onChange={(event) => setField("icon", event.target.value)}
            className="text-center text-lg"
            disabled={readOnly}
          />
        </div>
        <div className="space-y-2">
          <Label>{localize(lang, "Название", "Name")}</Label>
          <Input
            value={form.name || ""}
            onChange={(event) => setField("name", event.target.value)}
            placeholder={localize(lang, "Агент OPS-разбора", "Ops triage agent")}
            disabled={readOnly}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label>{localize(lang, "Описание", "Description")}</Label>
        <Input
          value={form.description || ""}
          onChange={(event) => setField("description", event.target.value)}
          placeholder={localize(
            lang,
            "Переиспользуемый агент для проверок инфраструктуры и предложений по ремонту",
            "Reusable agent for infrastructure checks and repair suggestions",
          )}
          disabled={readOnly}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <div className="space-y-2">
          <Label>{localize(lang, "Модель", "Model")}</Label>
          <Select value={form.model || MODEL_OPTIONS[0]} onValueChange={(value) => setField("model", value)}>
            <SelectTrigger disabled={readOnly}>
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              {MODEL_OPTIONS.map((model) => (
                <SelectItem key={model} value={model}>
                  {model}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        </div>

        <div className="space-y-2">
          <Label>{localize(lang, "Лимит итераций", "Max iterations")}</Label>
          <Input
            type="number"
            min={1}
            max={50}
            value={form.max_iterations || 10}
            onChange={(event) => setField("max_iterations", Number(event.target.value) || 10)}
            disabled={readOnly}
          />
        </div>
      </div>

      <div className="space-y-2">
        <Label>{localize(lang, "Системный промпт", "System prompt")}</Label>
        <Textarea
          value={form.system_prompt || ""}
          onChange={(event) => setField("system_prompt", event.target.value)}
          rows={4}
          placeholder={localize(
            lang,
            "Ты аккуратный OPS-агент. Проверяй контекст перед рискованными действиями.",
            "You are a careful operations agent. Verify before any risky action.",
          )}
          disabled={readOnly}
        />
      </div>

      <div className="space-y-2">
        <Label>{localize(lang, "Инструкции", "Instructions")}</Label>
        <Textarea
          value={form.instructions || ""}
          onChange={(event) => setField("instructions", event.target.value)}
          rows={4}
          placeholder={localize(
            lang,
            "Сначала собирай контекст. Не выполняй разрушительные команды без явного подтверждения.",
            "Always gather context first. Avoid destructive commands unless explicitly approved.",
          )}
          disabled={readOnly}
        />
      </div>

      <div className="space-y-3">
        <Label>{localize(lang, "Разрешённые инструменты", "Allowed tools")}</Label>
        <div className="grid gap-2 md:grid-cols-2">
          {ALL_TOOLS.map((tool) => (
            <label
              key={tool.id}
              className="flex cursor-pointer items-start gap-3 rounded-xl border border-border/70 bg-background/30 px-3 py-3 transition-colors hover:bg-background/40"
            >
              <Checkbox
                checked={(form.allowed_tools || []).includes(tool.id)}
                onCheckedChange={() => toggleTool(tool.id)}
                className="mt-0.5"
                disabled={readOnly}
              />
              <div>
                <div className="text-sm font-medium text-foreground">{localize(lang, tool.labelRu, tool.labelEn)}</div>
                <div className="text-xs text-muted-foreground">{localize(lang, tool.descriptionRu, tool.descriptionEn)}</div>
              </div>
            </label>
          ))}
        </div>
      </div>

      {canUseMcp && mcpList.length > 0 ? (
        <div className="space-y-3">
          <Label>{localize(lang, "MCP-серверы", "MCP servers")}</Label>
          <div className="grid gap-2">
            {mcpList.map((mcp) => (
              <label
                key={mcp.id}
                className="flex cursor-pointer items-center gap-3 rounded-xl border border-border/70 bg-background/30 px-3 py-3 transition-colors hover:bg-background/40"
              >
                <Checkbox checked={mcpIds.includes(mcp.id)} onCheckedChange={() => toggleMcp(mcp.id)} disabled={readOnly} />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-foreground">{mcp.name}</span>
                    <Badge variant="outline" className="text-[10px] font-mono">
                      {mcp.transport}
                    </Badge>
                    {mcp.last_test_ok === true ? <Badge variant="secondary">OK</Badge> : null}
                    {mcp.last_test_ok === false ? <Badge variant="destructive">ERR</Badge> : null}
                  </div>
                  <div className="text-xs text-muted-foreground">
                    {mcp.description || localize(lang, "Описание не заполнено", "No description")}
                  </div>
                </div>
              </label>
            ))}
          </div>
        </div>
      ) : null}

      {canUseSkills && skills.length > 0 ? (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-2">
            <Label>{localize(lang, "Skills", "Skills")}</Label>
            <Button
              type="button"
              variant="outline"
              size="sm"
              className="h-8 gap-1.5 rounded-md px-3 text-[11px]"
              onClick={() => navigate("/studio/skills")}
              disabled={readOnly}
            >
              <BookOpen className="h-3.5 w-3.5" />
              {localize(lang, "Открыть каталог", "Browse catalog")}
            </Button>
          </div>
          <div className="grid gap-2">
            {skills.map((skill) => (
              <label
                key={skill.slug}
                className="flex cursor-pointer items-start gap-3 rounded-xl border border-border/70 bg-background/30 px-3 py-3 transition-colors hover:bg-background/40"
              >
                <Checkbox
                  checked={(form.skill_slugs || []).includes(skill.slug)}
                  onCheckedChange={() => toggleSkill(skill.slug)}
                  className="mt-0.5"
                  disabled={readOnly}
                />
                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="text-sm font-medium text-foreground">{skill.name}</span>
                    <span className="font-mono text-[10px] text-muted-foreground">{skill.slug}</span>
                    {skill.service ? <span className="text-[10px] text-muted-foreground">{skill.service}</span> : null}
                    {skill.safety_level ? <span className="text-[10px] text-muted-foreground">{skill.safety_level}</span> : null}
                  </div>
                  <div className="text-xs text-muted-foreground">{skill.description}</div>
                </div>
              </label>
            ))}
          </div>
        </div>
      ) : null}

      {servers.length > 0 ? (
        <div className="space-y-3">
          <Label>{localize(lang, "Ограничение по серверам", "Server scope")}</Label>
          <p className="text-xs text-muted-foreground">
            {localize(
              lang,
              "Оставьте пустым, чтобы агент работал со всеми доступными серверами. Выберите серверы, чтобы жёстко ограничить профиль.",
              "Leave empty to allow all accessible servers. Select specific servers to hard-scope this agent.",
            )}
          </p>
          <div className="grid gap-2 md:grid-cols-2">
            {servers.map((server) => (
              <label
                key={server.id}
                className="flex cursor-pointer items-center gap-3 rounded-xl border border-border/70 bg-background/30 px-3 py-3 transition-colors hover:bg-background/40"
              >
                <Checkbox
                  checked={serverScopeIds.includes(server.id)}
                  onCheckedChange={() => toggleServerScope(server.id)}
                  disabled={readOnly}
                />
                <div className="min-w-0 flex-1">
                  <div className="text-sm font-medium text-foreground">{server.name}</div>
                  <div className="text-xs text-muted-foreground">{server.host}</div>
                </div>
              </label>
            ))}
          </div>
        </div>
      ) : null}

      {isAdmin ? (
        <ShareAccessEditor
          title={localize(lang, "Видимость", "Visibility")}
          description={localize(
            lang,
            "Администратор управляет тем, кто может открывать и переиспользовать этот профиль агента.",
            "Admin controls who can open and reuse this agent profile.",
          )}
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
          {agents.map((agent) => {
            const visibleTools = visibleAllowedTools(agent.allowed_tools) || [];
            return (
            <div key={agent.id} className="group overflow-hidden rounded-xl border border-border bg-card shadow-sm transition-all duration-150 hover:shadow-md">
              <div className="p-4">
                <div className="flex items-start justify-between gap-3">
                  <div className="flex min-w-0 items-start gap-3">
                    <div className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl border border-primary/20 bg-primary/10 text-lg font-semibold text-primary">
                      {agent.icon || "B"}
                    </div>
                    <div className="min-w-0">
                      <p className="text-sm font-semibold text-foreground">{agent.name}</p>
                      <p className="mt-0.5 text-xs text-muted-foreground">
                        {agent.description || localize(lang, "Описание не заполнено", "No description")}
                      </p>
                      <div className="mt-2 flex flex-wrap gap-1">
                        {agent.is_owner ? <Badge variant="secondary" className="text-[10px]">{localize(lang, "Мой", "Mine")}</Badge> : null}
                        {!agent.is_owner && agent.owner_username ? (
                          <Badge variant="outline" className="text-[10px]">{localize(lang, "Владелец", "Owner")}: {agent.owner_username}</Badge>
                        ) : null}
                        {agent.is_shared ? <Badge variant="outline" className="text-[10px]">{localize(lang, "Общий", "Shared")}</Badge> : null}
                        {agent.can_edit === false ? <Badge variant="outline" className="text-[10px]">{localize(lang, "Только чтение", "Read only")}</Badge> : null}
                      </div>
                    </div>
                  </div>
                  <div className="flex gap-1 shrink-0">
                    <Button
                      size="icon"
                      variant="ghost"
                      className="h-8 w-8 rounded-lg"
                      onClick={() => setEditAgent(agent)}
                      aria-label={agent.can_edit === false ? localize(lang, `Открыть агента ${agent.name}`, `View agent ${agent.name}`) : localize(lang, `Изменить агента ${agent.name}`, `Edit agent ${agent.name}`)}
                      title={agent.can_edit === false ? localize(lang, "Открыть агента", "View agent") : localize(lang, "Изменить агента", "Edit agent")}
                    >
                      <Pencil className="h-3.5 w-3.5" />
                    </Button>
                    {agent.can_edit !== false ? (
                      <Button
                        size="icon"
                        variant="ghost"
                        className="h-8 w-8 rounded-lg text-destructive hover:text-destructive"
                        onClick={() => setDeleteTarget(agent)}
                        aria-label={localize(lang, `Удалить агента ${agent.name}`, `Delete agent ${agent.name}`)}
                        title={localize(lang, "Удалить агента", "Delete agent")}
                      >
                        <Trash2 className="h-3.5 w-3.5" />
                      </Button>
                    ) : null}
                  </div>
                </div>
              </div>

              <div className="border-t border-border/50 bg-secondary/10 px-4 py-3 space-y-2.5">
                <div className="flex flex-wrap gap-1.5">
                  <span className="rounded border border-border/50 bg-secondary/40 px-1.5 py-0.5 font-mono text-[10px] text-muted-foreground">{agent.model}</span>
                  <span className="rounded border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                    {localize(lang, `${agent.max_iterations} итер.`, `${agent.max_iterations} iter`)}
                  </span>
                  {agent.mcp_servers?.length ? <span className="rounded border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">{agent.mcp_servers.length} MCP</span> : null}
                  {agent.skill_slugs?.length ? (
                    <span className="rounded border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {localize(lang, `${agent.skill_slugs.length} skills`, `${agent.skill_slugs.length} skills`)}
                    </span>
                  ) : null}
                  {agent.server_scope?.length ? (
                    <span className="rounded border border-border/50 bg-secondary/40 px-1.5 py-0.5 text-[10px] text-muted-foreground">
                      {localize(lang, `${agent.server_scope.length} серверов`, `${agent.server_scope.length} scoped`)}
                    </span>
                  ) : null}
                </div>
                {visibleTools.length ? (
                  <p className="text-[11px] text-muted-foreground/70">
                    {visibleTools.slice(0, 4).map((item) => toolLabel(item, lang)).join(", ")}
                    {visibleTools.length > 4 ? ` +${visibleTools.length - 4}` : ""}
                  </p>
                ) : null}
                {agent.skill_errors?.length ? (
                  <div className="rounded-lg border border-amber-500/25 bg-amber-500/8 px-2.5 py-1.5">
                    {agent.skill_errors.slice(0, 1).map((error) => (
                      <p key={error} className="text-[11px] text-amber-300">{error}</p>
                    ))}
                  </div>
                ) : null}
              </div>
            </div>
            );
          })}
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
