import { useMemo, useState, type ElementType } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { AlertTriangle, Loader2, Save, Server as ServerIcon, Share2, ShieldCheck, SlidersHorizontal, Wrench } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { ProviderBindingSelect } from "@/components/settings/ProviderBindingSelect";
import { studioMCP, studioServers, studioSkills, type AgentConfig } from "@/lib/api";
import { localize, useI18n } from "@/lib/i18n";
import {
  AgentAllowedToolsSection,
  AgentCoreSettingsSection,
  AgentMcpServersSection,
  AgentServerScopeSection,
  AgentSkillsSection,
  AgentVisibilitySection,
} from "./AgentFormAccessSections";
import { MODEL_OPTIONS, sudoOption, toolLabel, visibleAllowedTools } from "./agentConfigOptions";


type ProfileSection = "main" | "tools" | "scope" | "access";

const DEFAULT_ALLOWED_TOOLS = ["ssh_execute", "report"];

function toIdList(items: Array<number | { id: number }> | undefined) {
  return (items || [])
    .map((item) => (typeof item === "number" ? item : item.id))
    .filter((item): item is number => Number.isFinite(item))
    .sort((a, b) => a - b);
}

export function createProfileDraft(initial: Partial<AgentConfig>): Partial<AgentConfig> {
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

export function profileFingerprint(profile: Partial<AgentConfig>) {
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
    provider_binding: profile.provider_binding || {},
  });
}

export function formatProfileDate(value: string | null | undefined, lang: "ru" | "en") {
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

export function AgentForm({
  initial,
  onSave,
  onCancel,
  isPending,
  canUseMcp,
  canUseSkills,
  shareUsers,
  isAdmin,
  canManageAiRouting,
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
  canManageAiRouting: boolean;
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
            <>
              <AgentCoreSettingsSection
                form={form}
                lang={lang}
                readOnly={readOnly}
                canSelectModels={canManageAiRouting}
                onFieldChange={setField}
                isAdmin={isAdmin}
              />
              {canManageAiRouting ? <div className="space-y-2 rounded-lg border border-border/70 bg-background/45 p-4">
                <div className="text-sm font-medium text-foreground">
                  {localize(lang, "AI-провайдер запусков", "Run AI provider")}
                </div>
                <p className="text-xs leading-5 text-muted-foreground">
                  {localize(
                    lang,
                    "Studio-запуски считаются фоновыми: доступны только подключения с unattended-доступом.",
                    "Studio runs are unattended, so only connections with background access are available.",
                  )}
                </p>
                <ProviderBindingSelect
                  value={form.provider_binding?.target_id ? form.provider_binding : null}
                  onChange={(binding) => setField("provider_binding", binding || {})}
                  mode="unattended"
                  lang={lang}
                  disabled={readOnly}
                />
              </div> : null}
            </>
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
